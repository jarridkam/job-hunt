"""iCalendar feed of everything with a time: interviews and assessment deadlines. Subscribed to from a phone
calendar so reminders fire even when the app is closed."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from . import config, db, deadlines

PRODID = "-//jobhunt//EN"


def token() -> str:
    """Per-install secret in the feed URL (calendar apps cannot log in)."""
    t = config.get("calendar_token")
    if not t:
        t = secrets.token_urlsafe(24)
        db.set_setting("calendar_token", t)
    return t


def _esc(s: str | None) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _utc(iso: str) -> str:
    dt = deadlines.to_local(iso)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ") if dt else ""


def _fold(line: str) -> str:
    out, s = [], line.encode()
    while len(s) > 72:
        out.append(s[:72].decode(errors="ignore")); s = b" " + s[72:]
    out.append(s.decode(errors="ignore"))
    return "\r\n".join(out)


def _event(uid: str, start: str, end: str, summary: str, description: str, url: str | None, alarms: list[int]) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:{uid}@jobhunt", f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
             f"DTSTART:{start}", f"DTEND:{end}", _fold(f"SUMMARY:{_esc(summary)}"), _fold(f"DESCRIPTION:{_esc(description)}")]
    if url:
        lines.append(_fold(f"URL:{url}"))
    for minutes in alarms:
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", _fold(f"DESCRIPTION:{_esc(summary)}"), f"TRIGGER:-PT{minutes}M", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def interview_event(x: dict) -> list[str]:
    if not x.get("starts_at"):
        return []
    start = deadlines.to_local(x["starts_at"])
    end = start + timedelta(minutes=int(x.get("duration_minutes") or 45))
    what = (x.get("stage") or "Interview") + (f" ({x['format']})" if x.get("format") else "")
    desc = " · ".join(p for p in [x.get("title"), f"with {x['interviewer']}" if x.get("interviewer") else "", x.get("location"), x.get("link")] if p)
    return _event(f"interview-{x['id']}", _utc(x["starts_at"]), end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                  f"{x.get('company') or ''}: {what}", desc, x.get("link"), [24 * 60, 60])


def assessment_event(x: dict) -> list[str]:
    if not x.get("due_at"):
        return []
    due = deadlines.to_local(x["due_at"])
    # Block out time to do it, ending at the deadline, so the phone nags before it is too late.
    start = due - timedelta(minutes=int(x.get("est_minutes") or 60))
    what = (x.get("platform") + " " if x.get("platform") else "") + (x.get("title") or "Assessment")
    buf = int(config.get_int("assessment_buffer_days", 2))
    do_by = due - timedelta(days=buf)
    desc = " · ".join(p for p in [f"Deadline {due.strftime('%a %b %d %I:%M %p')}", f"aim to finish by {do_by.strftime('%a %b %d')}" if buf else "",
                                  "deadline guessed, check the email" if x.get("due_source") == "assumed" else "",
                                  f"about {x['est_minutes']} min" if x.get("est_minutes") else "", x.get("link")] if p)
    return _event(f"assessment-{x['id']}", start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), _utc(x["due_at"]),
                  f"{x.get('company') or ''}: {what} DUE", desc, x.get("link"), [2 * 24 * 60, 24 * 60, 3 * 60])


def wrap(events: list[str], name: str = "jobhunt") -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{_esc(name)}",
             "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H", *events, "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def feed() -> str:
    ev: list[str] = []
    for x in db.q("SELECT * FROM interviews WHERE status='scheduled' AND starts_at IS NOT NULL"):
        ev += interview_event(x)
    for x in db.q("SELECT * FROM assessments WHERE status='pending' AND due_at IS NOT NULL"):
        ev += assessment_event(x)
    return wrap(ev)
