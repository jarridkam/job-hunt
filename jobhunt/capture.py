"""Capture from the phone: a shared link, a pasted URL, or pasted text (recruiter text, forwarded invite).
One box, no choices. A job posting becomes a job (scored, ready to queue); a message about an application
runs through the same classifier as the inbox and lands as an application, test or interview."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from . import config, db, email_tracker, legit, llm, matcher
from .sources.base import Job, detect_ats, make_http, strip_html, looks_remote

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
MAX_PAGE = 14000


class CapturedJob(BaseModel):
    is_job_posting: bool = Field(description="True if the page or text is a single job posting (one role at one employer). False for job lists, company home pages, articles, or messages to the candidate.")
    company: str = Field(default="", description="Employer name, never the job board.")
    title: str = Field(default="", description="Job title.")
    location: str = Field(default="", description="Location as stated; 'Remote' if remote.")
    remote: bool = Field(default=False)
    apply_url: str = Field(default="", description="The apply link if one is visible, else empty.")
    description: str = Field(default="", description="The job description text, trimmed of navigation and boilerplate; keep requirements and responsibilities verbatim. Up to ~3000 characters.")
    salary_min: float | None = Field(default=None)
    salary_max: float | None = Field(default=None)
    posted_at: str = Field(default="", description="Posting date as YYYY-MM-DD if stated, else empty.")


JOB_SYSTEM = """You read a web page or pasted text for a job seeker and extract the job posting on it.
Company is the EMPLOYER, never the job board or ATS (Greenhouse, Lever, LinkedIn, Indeed). If the page is not one job posting, set is_job_posting false and leave the rest empty."""


def _fetch(url: str) -> str:
    with make_http() as http:
        r = http.get(url, follow_redirects=True, timeout=20)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        return strip_html(r.text) if "html" in ct or r.text.lstrip().startswith("<") else r.text


def _job_from(url: str, text: str, title: str) -> dict | None:
    """Store a job from a URL (page fetched) or pasted text. Returns the job row, or None when it is not a posting."""
    page = ""
    if url:
        try:
            page = _fetch(url)
        except Exception as e:  # noqa: BLE001
            page = ""
            text = f"{text}\n(page could not be fetched: {e})"
    user = f"URL: {url or '(none)'}\nSHARED TITLE: {title or '(none)'}\n\nPAGE TEXT:\n{page[:MAX_PAGE]}\n\nPASTED TEXT:\n{text[:6000]}"
    cj = llm.extract(JOB_SYSTEM, user, CapturedJob, model=config.get("model_fast"), effort="low", purpose="capture")
    if not cj.is_job_posting or not cj.title:
        return None
    ext = url or f"text:{abs(hash((cj.company.lower(), cj.title.lower())))}"
    existing = db.q1("SELECT * FROM jobs WHERE url=? OR apply_url=? OR (lower(company)=? AND lower(title)=?)",
                     (url or "-", url or "-", cj.company.lower().strip(), cj.title.lower().strip()))
    if existing:
        return existing
    ats = detect_ats(cj.apply_url or url) or detect_ats(url)
    row = {
        "source": "capture", "external_id": ext, "url": url or cj.apply_url or "", "apply_url": cj.apply_url or url or "",
        "title": cj.title.strip(), "company": (cj.company or "(unknown)").strip(), "location": cj.location,
        "remote": int(cj.remote or looks_remote(cj.location, cj.title)), "description": cj.description or page[:8000] or text[:8000],
        "salary_min": cj.salary_min, "salary_max": cj.salary_max, "posted_at": cj.posted_at or None,
        "fetched_at": db.now_iso(), "ats": ats[0] if ats else None, "raw": db.dumps({"captured": True, "shared_title": title}),
    }
    s, why = legit.score(row)
    row.update({"legit_score": s, "legit_reasons": db.dumps(why)})
    jid = db.insert("jobs", row)
    job = db.q1("SELECT * FROM jobs WHERE id=?", (jid,))
    # Score now (one call) so the result page can say "fit 78" instead of "unscored". You picked it, so no title filter.
    try:
        fs = matcher.score_job(job)
        fit = max(0, min(100, fs.fit_score))
        db.update("jobs", jid, {"fit_score": fit, "fit_summary": fs.summary, "fit_reasons": db.dumps(fs.matching_points),
                                "fit_missing": db.dumps(fs.missing)})
    except Exception:  # noqa: BLE001
        pass
    return db.q1("SELECT * FROM jobs WHERE id=?", (jid,))


def _message_from(text: str, title: str, url: str) -> dict:
    """Run pasted text through the inbox classifier and apply it like an email."""
    now = datetime.now(timezone.utc)
    uid = int(now.timestamp() * 1000) % 2_000_000_000
    body = text + (f"\n\n{url}" if url and url not in text else "")
    return email_tracker.ingest(account="capture", uid=uid, from_addr="(pasted)", subject=title or body.strip().split("\n")[0][:120],
                                body=body, received=now, folder="capture", force=True)


def capture(text: str = "", url: str = "", title: str = "") -> dict:
    """Returns {"kind": "job"|"application"|"nothing", "job": row?, "app_id"?, "classification"?, "message": str}."""
    text, url, title = (text or "").strip(), (url or "").strip(), (title or "").strip()
    bare = URL_RE.sub(" ", text).strip()                       # the words, without any links
    msgish = bool(email_tracker.PREFILTER.search(bare))        # reads like mail about an application
    if not url:
        m = URL_RE.search(text)
        if m and len(bare) < 80 and not msgish:                # a bare link, maybe with a word or two
            url = m.group(0)
    if not url and not text:
        return {"kind": "nothing", "message": "Nothing to save. Paste a link or some text."}
    tried_job = False
    if url and not msgish:
        tried_job = True
        job = _job_from(url, text, title)
        if job:
            return {"kind": "job", "job": job, "message": f"Saved {job['title']} at {job['company']}."}
    if text or title:
        res = _message_from(text or title, title, url)
        c = res.get("classification")
        if c is not None and c.kind != "other" and res.get("app_id"):
            return {"kind": "application", "app_id": res["app_id"], "classification": c, "email_id": res.get("email_id"),
                    "message": c.summary}
    if url and not tried_job:
        job = _job_from(url, text, title)
        if job:
            return {"kind": "job", "job": job, "message": f"Saved {job['title']} at {job['company']}."}
    if url:
        return {"kind": "nothing", "message": "That link is not a single job posting, and the text does not look like a message about an application."}
    return {"kind": "nothing", "message": "Could not tell what this is. If it is a job posting, share or paste the posting's link."}
