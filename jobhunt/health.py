"""Nothing fails quietly. Every background job that broke, or finished with problems, becomes a Needs-you item
saying what went wrong in plain words and offering a retry. The inbox also checks itself on a timer, and Today
shows when each thing last worked, so "the app stopped working" is never a surprise three weeks later."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from . import config, db, messages

WINDOW_DAYS = 7          # older failures are history, not a to-do
INBOX_STALE_HOURS = 24   # inbox not checked for this long while connected -> Needs you

# kind -> (group key, label, retry POST url or None). Per-item kinds (draft-12) are resolved in _retry().
GROUPS = {"fetch": "jobs", "score": "jobs", "fetch_and_score": "jobs", "email": "email", "reclassify": "reclassify",
          "draft_all": "draft_all"}


def _aware(s) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _group(kind: str) -> str:
    return GROUPS.get(kind, kind)   # draft-12, prep-3, followup-7 are their own group


def _retry(kind: str) -> tuple[str | None, str]:
    """(POST url, button label) that re-runs this kind of job."""
    if kind in ("fetch", "score", "fetch_and_score", "email", "reclassify", "draft_all"):
        return f"/run/{kind}", "Try again"
    head, _, ident = kind.partition("-")
    if not ident.isdigit():
        return None, ""
    return {"draft": (f"/applications/{ident}/draft", "Try again"), "prep": (f"/interviews/{ident}/prep", "Try again"),
            "followup": (f"/applications/{ident}/followup/draft", "Try again")}.get(head, (None, ""))


def _subject(kind: str) -> str:
    """What the job was about, for per-item kinds: 'letter for Dev @ Acme'."""
    head, _, ident = kind.partition("-")
    if not ident.isdigit():
        return ""
    if head in ("draft", "followup", "apply"):
        a = db.q1("SELECT company, title FROM applications WHERE id=?", (int(ident),)) or {}
        return f"{a.get('title') or ''} @ {a.get('company') or ''}".strip(" @")
    if head == "prep":
        x = db.q1("SELECT company, stage FROM interviews WHERE id=?", (int(ident),)) or {}
        return f"{x.get('stage') or 'Interview'} · {x.get('company') or ''}".strip(" ·")
    return ""


def _cause(run: dict) -> str:
    s = (run.get("summary") or "").removeprefix("failed: ")
    return messages.friendly_error(s) if s else "It stopped without saying why. The activity log has the details."


def latest_by_group() -> dict[str, dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
    out: dict[str, dict] = {}
    for r in db.q("SELECT id, kind, status, started_at, finished_at, summary, warnings, dismissed FROM runs "
                  "WHERE started_at >= ? AND status != 'running' ORDER BY id DESC", (since,)):
        out.setdefault(_group(r["kind"]), r)
    return out


def problems() -> list[dict]:
    """Needs-you items for things that broke. Same shape as the other items, plus post/dismiss urls."""
    items: list[dict] = []
    for group, r in latest_by_group().items():
        if r.get("dismissed"):
            continue
        kind = r["kind"]
        if kind.startswith("apply-"):
            continue   # apply failures already show as "Auto-apply got stuck" on the application
        post, label = _retry(kind)
        what = messages.task_label(kind)
        subj = _subject(kind)
        if r["status"] == "failed":
            items.append({"kind": "Didn't finish", "title": what + (f": {subj}" if subj else ""),
                          "detail": f"{_cause(r)} ({_ago(r.get('finished_at') or r['started_at'])})",
                          "href": f"/runs#run-{r['id']}", "action": label or "Details", "post": post,
                          "dismiss": f"/runs/{r['id']}/dismiss", "urgent": group == "email", "problem": True})
            continue
        warns = db.loads(r.get("warnings"), []) or []
        if warns:
            first = messages.friendly_error(warns[0])
            more = f" (+{len(warns) - 1} more)" if len(warns) > 1 else ""
            href = "/companies" if group == "jobs" else f"/runs#run-{r['id']}"
            items.append({"kind": "Finished with problems", "title": f"{what}: {len(warns)} thing{'s' if len(warns) != 1 else ''} went wrong",
                          "detail": first + more, "href": href, "action": "See what" if not post else "Try again", "post": post,
                          "dismiss": f"/runs/{r['id']}/dismiss", "urgent": group == "email", "problem": True})
    # Inbox: connected but not checked lately (server was off, or every sync failed before the window).
    if config.get("email_user") and config.get("email_pass"):
        from .email_tracker import last_sync_at
        last = last_sync_at()
        stale = last is None or datetime.now(timezone.utc) - last > timedelta(hours=INBOX_STALE_HOURS)
        email_failed = any(i["post"] == "/run/email" and i["kind"] == "Didn't finish" for i in items)
        if stale and not email_failed and not config.get("health_inbox_snooze_until") > datetime.now(timezone.utc).isoformat():
            items.append({"kind": "Inbox not checked", "title": "No inbox check " + (_ago(last.isoformat()) if last else "yet"),
                          "detail": "Test invites and interview emails only show up after a check. Check now so nothing slips.",
                          "href": "/runs", "action": "Check inbox now", "post": "/run/email", "dismiss": "/health/inbox/snooze",
                          "urgent": True, "problem": True})
    # Phone alerts that stopped arriving.
    bad = db.q("SELECT label, last_error FROM push_subscriptions WHERE last_error IS NOT NULL AND "
               "(last_ok_at IS NULL OR last_ok_at < COALESCE(last_error_at, '9999'))") if _has_col("push_subscriptions", "last_error_at") else []
    if bad:
        items.append({"kind": "Phone alerts failing", "title": f"{len(bad)} device{'s' if len(bad) != 1 else ''} not getting alerts",
                      "detail": "Turn alerts off and on again on that device (Settings › Alerts on this device).",
                      "href": "/settings#alerts", "action": "Fix", "post": None, "dismiss": None, "urgent": False, "problem": True})
    werr = config.get("notify_webhook_error")
    if werr and config.get("notify_webhook_url"):
        items.append({"kind": "Phone alerts failing", "title": "Your ntfy / webhook alert didn't go through",
                      "detail": werr[:160], "href": "/settings#alerts", "action": "Fix", "post": None,
                      "dismiss": "/health/webhook/clear", "urgent": False, "problem": True})
    return items


def _has_col(table: str, col: str) -> bool:
    return any(r["name"] == col for r in db.q(f"PRAGMA table_info({table})"))


def _ago(iso: str | None) -> str:
    dt = _aware(iso)
    if not dt:
        return "never"
    secs = (datetime.now(timezone.utc) - dt).total_seconds()
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    d = int(secs // 86400)
    return "yesterday" if d == 1 else f"{d} days ago"


# ---- automatic inbox checks ------------------------------------------------------

def auto_minutes() -> int:
    return max(0, config.get_int("email_auto_minutes", 30))


def _autosync_due(now: datetime) -> bool:
    every = auto_minutes()
    if not every or not (config.get("email_user") and config.get("email_pass")):
        return False
    recent = db.q("SELECT status, started_at FROM runs WHERE kind='email' ORDER BY id DESC LIMIT 3")
    if not recent:
        return True
    if recent[0]["status"] == "running":
        return False
    # Back off when it keeps failing (bad password, no credit): one try every 4 intervals, still visible on Today.
    if len(recent) == 3 and all(r["status"] == "failed" for r in recent):
        every *= 4
    last = _aware(recent[0]["started_at"])
    return last is None or now - last >= timedelta(minutes=every)


_thread: threading.Thread | None = None


def start_autosync() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return

    def loop():
        from . import tasks
        time.sleep(45)
        while True:
            try:
                if _autosync_due(datetime.now(timezone.utc)) and not tasks.is_running("email"):
                    tasks.start("email", tasks.email_task)
            except Exception as e:  # noqa: BLE001
                db.set_setting("health_last_error", f"{db.now_iso()} {e}"[:300])
            time.sleep(60)

    _thread = threading.Thread(target=loop, name="autosync", daemon=True)
    _thread.start()
