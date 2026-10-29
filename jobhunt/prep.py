"""Interview prep card: one LLM call that turns what jobhunt already knows (the posting, your resume, the letter
you sent, the fit gaps) into a page you can read in five minutes before the call."""
from __future__ import annotations

from . import config, db, documents, llm
from .models import PrepCard

SYSTEM = """You are an interview coach preparing a candidate for one specific interview. Be concrete and brief;
every line must be usable in the next hour. Use the candidate's own resume and cover letter so your answers match
what they already claimed. Likely questions must fit the stage (a recruiter screen asks about motivation, logistics
and salary; a technical interview asks about skills from the posting). Where the candidate has a gap, give a short
honest way to frame it, never a lie. Plain language, no fluff."""


def build(iid: int) -> PrepCard:
    x = db.q1("SELECT * FROM interviews WHERE id=?", (iid,))
    if not x:
        raise RuntimeError("interview not found")
    app = db.q1("SELECT * FROM applications WHERE id=?", (x.get("application_id"),)) if x.get("application_id") else None
    job = db.q1("SELECT * FROM jobs WHERE id=?", (app["job_id"],)) if app and app.get("job_id") else None
    resume = documents.active_resume() or {}
    parts = [f"COMPANY: {x.get('company') or (app or {}).get('company') or ''}",
             f"ROLE: {x.get('title') or (app or {}).get('title') or ''}",
             f"STAGE: {x.get('stage') or 'unknown'}  FORMAT: {x.get('format') or 'unknown'}  WITH: {x.get('interviewer') or 'unknown'}"]
    if job:
        parts.append(f"POSTING:\n{(job.get('description') or '')[:6000]}")
        if job.get("fit_summary"):
            parts.append(f"FIT SUMMARY: {job['fit_summary']}")
        if job.get("fit_missing"):
            parts.append(f"GAPS THE SCORER FOUND: {job['fit_missing']}")
    if app and app.get("cover_letter"):
        parts.append(f"COVER LETTER SENT:\n{app['cover_letter'][:3000]}")
    if app and app.get("notes"):
        parts.append(f"NOTES: {app['notes'][:800]}")
    if resume.get("content"):
        parts.append(f"RESUME:\n{resume['content'][:5000]}")
    if config.get("cand_salary"):
        parts.append(f"SALARY EXPECTATION: {config.get('cand_salary')}")
    card = llm.extract(SYSTEM, "\n\n".join(parts), PrepCard, model=config.get("model_main"), effort="medium",
                       max_tokens=3000, purpose="prep")
    db.update("interviews", iid, {"prep_json": card.model_dump_json(), "prep_at": db.now_iso()})
    return card
