"""Clear out old things. Nothing is deleted: "hide" keeps tracking quietly, "close" files it away, both undo in one
step, and anything comes back by itself if the company writes (closed applications have the lowest status rank)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import db, messages, undo
from .followup import _aware

CHOICES = (14, 30, 60, 90)
MIN_DAYS = CHOICES[0]
GONE_AFTER = 30      # days with no news before something counts as most likely over
HIDE_DAYS = 60       # how long "hide" lasts; if it's still silent by then it's in the second group anyway
OPEN = ("submitted", "screening", "assessment", "interview", "ready", "needs_attention", "failed", "queued")
UNREAD = {"ready": "Letter never read", "queued": "Letter never written", "needs_attention": "Got stuck", "failed": "Didn't go through"}


def hidden_ids() -> set[int]:
    """Applications hidden from Today, unless they've written since. New mail always beats a hide."""
    now = datetime.now(timezone.utc)
    out = set()
    for a in db.q("SELECT a.id, a.followup_snooze_until AS until, (SELECT MAX(happened_at) FROM application_events e "
                  "WHERE e.application_id=a.id AND e.source='email') AS mail FROM applications a WHERE a.followup_snooze_until IS NOT NULL"):
        until, mail = _aware(a["until"]), _aware(a["mail"])
        if until and until > now and not (mail and mail > until - timedelta(days=HIDE_DAYS)):
            out.add(a["id"])
    return out


def _known(name: str | None) -> str:
    return "" if (name or "").startswith("(unknown") else name or ""


def _age(at: datetime | None, now: datetime) -> int:
    return (now - at).days if at else 0


def candidates(days: int) -> dict[str, list[dict]]:
    """Everything with no news for `days` or more, split into {"active": probably alive, "gone": most likely over}.
    Age comes from the last real sign of life, never last_update_at, which any re-read of the inbox resets."""
    now = datetime.now(timezone.utc)
    tests = db.q("SELECT id, application_id, company, title, due_at, received_at, created_at FROM assessments WHERE status='pending'")
    ivs = db.q("SELECT id, application_id, company, stage, starts_at, received_at, created_at, status FROM interviews "
               "WHERE status IN ('needs_scheduling','scheduled')")
    stale_dates, live = [], set()
    for kind, rows, field in (("test", tests, "due_at"), ("iv", ivs, "starts_at")):
        for x in rows:
            at = _aware(x[field]) or _aware(x["received_at"]) or _aware(x["created_at"])
            if _age(at, now) >= days:
                stale_dates.append((kind, x, at))
            elif x["application_id"]:
                live.add(x["application_id"])   # a date still ahead keeps its whole application off this page
    apps = db.q("SELECT a.*, (SELECT MAX(happened_at) FROM application_events e WHERE e.application_id=a.id AND COALESCE(e.source,'') != 'tidy') "
                f"AS last_event FROM applications a WHERE a.status IN ({','.join('?' * len(OPEN))})", OPEN)
    hidden, out, listed = hidden_ids(), {"active": [], "gone": []}, set()
    for a in apps:
        at = max(filter(None, [_aware(a["last_event"]), _aware(a["applied_at"]), _aware(a["followup_at"])]), default=None) or _aware(a["created_at"])
        age = _age(at, now)
        if a["id"] in live or age < days:
            continue
        scope = "gone" if age >= GONE_AFTER else "active"
        if scope == "active" and a["id"] in hidden:
            continue
        listed.add(a["id"])
        what = UNREAD.get(a["status"]) or ("Applied, no reply" if a["status"] == "submitted" else messages.app_status(a["status"])[0] + ", then nothing")
        out[scope].append({"key": f"app:{a['id']}", "company": _known(a["company"]), "title": _known(a["title"]), "what": what, "age": age})
    for kind, x, at in stale_dates:
        if x["application_id"] not in listed:   # a date can't be hidden, so a stale one always counts as over
            what = "Test never done" if kind == "test" else ("Never scheduled" if x["status"] == "needs_scheduling" else "Interview never marked")
            out["gone"].append({"key": f"{kind}:{x['id']}", "company": x["company"] or "", "title": x.get("title") or x.get("stage") or "",
                                "what": what, "age": _age(at, now)})
    for rows in out.values():
        rows.sort(key=lambda r: -r["age"])
    return out


def count(days: int = MIN_DAYS) -> int:
    c = candidates(days)
    return len(c["active"]) + len(c["gone"])


def _close_date(table: str, row_id: int) -> str:
    tok = undo.record(table, row_id)
    if table == "assessments":
        db.update(table, row_id, {"status": "missed"})
    else:
        at = (db.q1("SELECT starts_at FROM interviews WHERE id=?", (row_id,)) or {}).get("starts_at")
        db.update(table, row_id, {"status": "done" if at else "cancelled"})
    return tok


def _valid(keys: list[str]) -> set[str]:
    c = candidates(MIN_DAYS)
    return set(keys) & {r["key"] for rows in c.values() for r in rows}


def close(keys: list[str]) -> tuple[int, str]:
    """File these away. Returns (how many, one undo token for the lot)."""
    tokens, n = [], 0
    for key in _valid(keys):
        kind, _, rid = key.partition(":")
        row_id = int(rid)
        n += 1
        if kind == "test":
            tokens.append(_close_date("assessments", row_id))
        elif kind == "iv":
            tokens.append(_close_date("interviews", row_id))
        else:
            tokens.append(undo.record("applications", row_id))
            db.update("applications", row_id, {"status": "stale", "last_update_at": db.now_iso()})
            db.add_event(row_id, "stale", "Cleared out: no news for a long time", source="tidy")
            for x in db.q("SELECT id FROM assessments WHERE application_id=? AND status='pending'", (row_id,)):
                tokens.append(_close_date("assessments", x["id"]))
            for x in db.q("SELECT id FROM interviews WHERE application_id=? AND status IN ('needs_scheduling','scheduled')", (row_id,)):
                tokens.append(_close_date("interviews", x["id"]))
    return n, undo.group(tokens)


def hide(keys: list[str]) -> tuple[int, str]:
    """Keep tracking these, but stop bringing them up on Today."""
    until = (datetime.now(timezone.utc) + timedelta(days=HIDE_DAYS)).isoformat()
    tokens, n = [], 0
    for key in _valid(keys):
        kind, _, rid = key.partition(":")
        if kind != "app":
            continue
        tokens.append(undo.record("applications", int(rid)))
        db.update("applications", int(rid), {"followup_snooze_until": until})
        n += 1
    return n, undo.group(tokens)
