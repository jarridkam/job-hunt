"""What they received: a frozen copy of everything that went out with an application, taken the moment it is
marked submitted. Postings get edited or pulled, resumes get revised, and a recruiter who calls three weeks later
asks "which role was this?" This is the answer: JD as it was, the exact resume and letter, every form answer with
where it came from, and one line on why you applied."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import db, documents

SOURCE_LABELS = {"profile": "profile", "standard": "standard", "letter": "letter", "file": "file", "ai": "AI-drafted",
                 "you": "your edit", "missing": "left blank"}


def _first_sentence(s: str | None) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    return (m.group(1) if m else s)[:200]


def why_line(app: dict, job: dict | None) -> str:
    """One line, from what the matcher said, or from the letter's opening. Yours to overwrite."""
    if job:
        s = _first_sentence(job.get("fit_summary"))
        if s:
            return s
        reasons = db.loads(job.get("fit_reasons"), []) or []
        if reasons:
            return "; ".join(str(r) for r in reasons[:2])[:200]
    letter = (app.get("cover_letter") or "").strip()
    if letter:
        paras = [p for p in re.split(r"\n\s*\n", letter) if p.strip()]
        body = paras[1] if len(paras) > 1 and len(paras[0]) < 60 else paras[0]
        return _first_sentence(body)
    return ""


def _resume_part(app: dict) -> dict | None:
    r = db.q1("SELECT * FROM documents WHERE id=?", (app["resume_doc_id"],)) if app.get("resume_doc_id") else documents.active_resume()
    if not r:
        return None
    content = r.get("content") or ""
    return {"doc_id": r["id"], "title": r.get("title"), "file": Path(r["file_path"]).name if r.get("file_path") else None,
            "sha": hashlib.sha256(content.encode()).hexdigest()[:12], "words": len(content.split()), "content": content[:20000]}


def build(app_id: int, how: str = "auto") -> dict | None:
    """how: auto (auto-apply submitted it) | manual (you said 'I applied') | reconstructed (backfilled later)."""
    app = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not app:
        return None
    job = db.q1("SELECT * FROM jobs WHERE id=?", (app["job_id"],)) if app.get("job_id") else None
    answers = db.loads(app.get("review_json"), []) or []
    for a in answers:
        a["source_label"] = SOURCE_LABELS.get(a.get("source"), a.get("source"))
    existing = db.loads(app.get("receipt_json"), {}) or {}
    return {
        "taken_at": db.now_iso(), "how": how, "submitted_at": app.get("applied_at") or db.now_iso(),
        "job": {"title": job.get("title"), "company": job.get("company"), "location": job.get("location"), "remote": job.get("remote"),
                "url": job.get("url"), "apply_url": job.get("apply_url"), "ats": job.get("ats"), "posted_at": job.get("posted_at"),
                "salary_min": job.get("salary_min"), "salary_max": job.get("salary_max"), "fit_score": job.get("fit_score"),
                "description": (job.get("description") or "")[:30000]} if job else None,
        "resume": _resume_part(app) if (app.get("job_id") or app.get("cover_letter") or app.get("resume_doc_id")) else None,   # inbox-only apps: we never sent anything
        "letter": (app.get("cover_letter") or "").strip() or None,
        "letter_source": app.get("cover_letter_source") or ("you" if app.get("cover_letter_approved") else None),
        "answers": answers,
        "screenshot": app.get("screenshot_path"),
        "why": existing.get("why") or why_line(app, job),
        "why_by": existing.get("why_by") or ("you" if existing.get("why") else "auto"),
    }


def snapshot(app_id: int, how: str = "auto", *, keep_existing: bool = True) -> dict | None:
    """Freeze the receipt. An existing receipt is kept (the first submission is the one they received) unless
    it was only reconstructed and a real one is now possible."""
    cur = db.loads((db.q1("SELECT receipt_json FROM applications WHERE id=?", (app_id,)) or {}).get("receipt_json"), None)
    if cur and keep_existing and not (cur.get("how") == "reconstructed" and how != "reconstructed"):
        return cur
    r = build(app_id, how)
    if r is None:
        return None
    db.update("applications", app_id, {"receipt_json": db.dumps(r)})
    return r


def get(app_id: int) -> dict | None:
    return db.loads((db.q1("SELECT receipt_json FROM applications WHERE id=?", (app_id,)) or {}).get("receipt_json"), None)


def set_why(app_id: int, text: str) -> None:
    r = get(app_id) or build(app_id, "reconstructed") or {}
    r["why"] = text.strip()[:300]
    r["why_by"] = "you"
    db.update("applications", app_id, {"receipt_json": db.dumps(r)})


SUBMITTED_STATES = ("submitted", "screening", "assessment", "interview", "offer", "rejected")


def backfill() -> int:
    """Applications already sent before receipts existed get one reconstructed from what is still around, marked as such."""
    n = 0
    for a in db.q(f"SELECT id FROM applications WHERE receipt_json IS NULL AND status IN ({','.join('?' * len(SUBMITTED_STATES))})", SUBMITTED_STATES):
        if snapshot(a["id"], "reconstructed"):
            n += 1
    return n
