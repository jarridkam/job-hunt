"""Stale applications: applied, then silence. Finds them, drafts a short follow-up note, remembers what you did."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config, db, llm
from .models import FollowUpNote

SYSTEM = """You write a short follow-up note from a job applicant to the employer, after applying and hearing nothing.
Rules: 4-6 sentences, plain and warm, no begging, no buzzwords. Name the role and roughly when they applied. One
sentence of specific interest in the company or role (from the posting). One sentence restating the single strongest
relevant qualification from the resume or cover letter. Close by asking whether the role is still open and offering
to share anything else. Sign with the candidate's name only. Subject line under 8 words."""


def days_setting() -> int:
    return config.get_int("followup_days", 14)


def _aware(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def stale(limit: int = 50) -> list[dict]:
    """Applications with status Applied whose last sign of life (any event, else applied date) is older than the
    threshold, not snoozed, not followed up within the threshold. Oldest first. Each row gets `quiet_days`."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_setting())
    out = []
    rows = db.q("SELECT a.*, (SELECT MAX(happened_at) FROM application_events e WHERE e.application_id=a.id) AS last_event "
                "FROM applications a WHERE a.status='submitted' ORDER BY COALESCE(a.applied_at, a.created_at)")
    for a in rows:
        if (a.get("company") or "").startswith("(unknown") or (a.get("title") or "").startswith("(unknown"):
            continue   # created from an email we could not read properly; nothing to write to
        last = max(filter(None, [_aware(a.get("last_event")), _aware(a.get("applied_at")), _aware(a.get("followup_at"))]), default=None)
        if last is None or last > cutoff:
            continue
        snooze = _aware(a.get("followup_snooze_until"))
        if snooze and snooze > now:
            continue
        a["quiet_days"] = (now - last).days
        out.append(a)
    out.sort(key=lambda a: -a["quiet_days"])
    return out[:limit]


def contact(app_id: int) -> str:
    """Best reply-to address we have: the sender of the newest email on this application that is not a no-reply."""
    rows = db.q("SELECT e.from_addr FROM application_events ev JOIN emails e ON e.id=ev.email_id "
                "WHERE ev.application_id=? ORDER BY ev.happened_at DESC", (app_id,))
    for r in rows:
        addr = (r.get("from_addr") or "").lower()
        if addr and "noreply" not in addr.replace("-", "").replace("_", "") and "donotreply" not in addr.replace("-", ""):
            return r["from_addr"]
    return ""


def draft(app_id: int) -> FollowUpNote:
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not a:
        raise RuntimeError("application not found")
    job = db.q1("SELECT * FROM jobs WHERE id=?", (a["job_id"],)) if a.get("job_id") else None
    cand = config.candidate()
    applied = _aware(a.get("applied_at")) or _aware(a.get("created_at"))
    parts = [f"CANDIDATE: {cand.full_name}", f"COMPANY: {a.get('company')}", f"ROLE: {a.get('title')}",
             f"APPLIED: {applied.strftime('%B %d') if applied else 'a few weeks ago'}",
             f"DAYS SINCE: {(datetime.now(timezone.utc) - applied).days if applied else '?'}"]
    if job and job.get("description"):
        parts.append(f"POSTING:\n{job['description'][:3000]}")
    if a.get("cover_letter"):
        parts.append(f"COVER LETTER SENT:\n{a['cover_letter'][:2500]}")
    if config.get("voice_notes"):
        parts.append(f"VOICE: {config.get('voice_notes')}")
    note = llm.extract(SYSTEM, "\n\n".join(parts), FollowUpNote, model=config.get("model_main"), effort="low",
                       max_tokens=1200, purpose="followup")
    db.update("applications", app_id, {"followup_draft": note.model_dump_json()})
    return note
