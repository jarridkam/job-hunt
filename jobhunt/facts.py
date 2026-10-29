"""Fact check for anything the AI writes in your name. Every claim in a cover letter or form answer is pulled
out and matched against one fact base (your profile, your resume, your extra Q&A). Supported claims pass;
unsupported or contradicted ones are shown to you, quoted, before anything is sent."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from . import config, db, documents, llm


class Claim(BaseModel):
    quote: str = Field(description="The exact words from the text that make a factual claim about the candidate (short).")
    kind: Literal["experience", "skill", "number", "education", "credential", "availability", "other"]
    status: Literal["supported", "unsupported", "contradicted"] = Field(
        description="supported = the fact base states it or it follows directly; unsupported = not in the fact base; contradicted = the fact base says otherwise.")
    evidence: str = Field(default="", description="The line of the fact base that supports or contradicts it, else empty.")
    note: str = Field(default="", description="For unsupported/contradicted only: what is wrong in one short clause, e.g. 'resume says 2 years, not 5'.")


class ClaimCheck(BaseModel):
    claims: list[Claim]


SYSTEM = """You audit text written on behalf of a job candidate. List every factual claim it makes ABOUT THE CANDIDATE
(years of experience, skills, tools, projects, employers, degrees, certifications, numbers, availability, location,
work authorization). Opinions, intentions and statements about the company are not claims. For each claim decide,
using ONLY the fact base, whether it is supported, unsupported, or contradicted. Be strict on numbers and named
technologies; a skill is supported if the resume shows it used, not merely a related one. Quote the text exactly."""


def fact_base() -> str:
    cand = config.candidate()
    r = documents.active_resume()
    parts = [f"PROFILE:\n{cand.as_prompt()}"]
    if r:
        parts.append(f"RESUME:\n{r['content'][:12000]}")
    return "\n\n".join(parts)


def check(text: str, label: str = "cover letter") -> ClaimCheck:
    user = f"FACT BASE:\n{fact_base()}\n\nTEXT TO AUDIT ({label}):\n{text[:8000]}"
    return llm.extract(SYSTEM, user, ClaimCheck, model=config.get("model_fast"), effort="low", max_tokens=3000, purpose="fact check")


def summary(cc: dict | ClaimCheck | None) -> dict:
    claims = (cc.get("claims") if isinstance(cc, dict) else cc.claims) if cc else []
    rows = [c if isinstance(c, dict) else c.model_dump() for c in claims]
    flagged = [c for c in rows if c["status"] != "supported"]
    return {"n": len(rows), "flagged": flagged, "ok": len(rows) - len(flagged), "clean": not flagged,
            "tone": "good" if not flagged else ("broken" if any(c["status"] == "contradicted" for c in flagged) else "wait")}


def check_letter(app_id: int) -> dict:
    a = db.q1("SELECT cover_letter FROM applications WHERE id=?", (app_id,))
    text = (a or {}).get("cover_letter") or ""
    if not text.strip():
        raise RuntimeError("No letter to check.")
    cc = check(text, "cover letter")
    db.update("applications", app_id, {"letter_check_json": cc.model_dump_json(), "letter_check_at": db.now_iso()})
    return summary(cc)


def check_answers(items: list[dict]) -> int:
    """Audit the AI-written answers of a review list in one call; each gets item['check'] = {status, note, quote}.
    Returns how many were flagged. Items that are not AI-written are left alone."""
    ai = [r for r in items if r.get("source") == "ai" and (r.get("value") or "").strip()]
    if not ai:
        return 0
    text = "\n\n".join(f"Q{i + 1}: {r['label']}\nA{i + 1}: {r['value']}" for i, r in enumerate(ai))
    cc = check(text, "form answers; prefix each quote with its A-number, e.g. 'A2: ...'")
    flagged = 0
    for r in ai:
        r["check"] = {"status": "supported", "note": "", "quote": ""}
    for c in cc.claims:
        if c.status == "supported":
            continue
        q = c.quote.strip()
        idx = None
        if q[:1] == "A" and ":" in q[:5]:
            try:
                idx = int(q[1:q.index(":")]) - 1
            except ValueError:
                idx = None
            q = q[q.index(":") + 1:].strip()
        if idx is None:
            idx = next((i for i, r in enumerate(ai) if q and q[:40].lower() in (r["value"] or "").lower()), None)
        if idx is None or idx >= len(ai):
            continue
        r = ai[idx]
        if r["check"]["status"] == "supported" or c.status == "contradicted":
            r["check"] = {"status": c.status, "note": c.note or "not in your profile or resume", "quote": q}
    for r in ai:
        if r["check"]["status"] != "supported":
            flagged += 1
    return flagged
