"""Reminders that reach the phone: Web Push to installed browsers, and an optional ntfy/webhook channel.
Only Don't-miss things are ever sent (tests, interviews, invites waiting on you), on an escalating schedule,
inside the user's waking hours, and never twice for the same step."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config, db

# Escalation steps, in hours before the moment: a push fires when the item is within that many hours and that
# step has not fired yet. Tests count down to the do-by date, interviews to the start time.
TEST_STEPS = (72, 24, 3)
INTERVIEW_STEPS = (24, 1)
POLL_SECONDS = 300


# ---- channels ----------------------------------------------------------------

def vapid_keys() -> tuple[str, str]:
    """(private PEM, public key base64url). Generated once and kept in settings (encrypted on the server)."""
    priv, pub = config.get("vapid_private"), config.get("vapid_public")
    if priv and pub:
        return priv, pub
    from py_vapid import Vapid, b64urlencode
    from cryptography.hazmat.primitives import serialization
    v = Vapid()
    v.generate_keys()
    priv = v.private_pem().decode()
    raw = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    pub = b64urlencode(raw)
    db.set_setting("vapid_private", priv)
    db.set_setting("vapid_public", pub)
    return priv, pub


def subscriptions() -> list[dict]:
    return db.q("SELECT * FROM push_subscriptions ORDER BY id")


def add_subscription(sub: dict, label: str = "") -> int:
    endpoint = sub.get("endpoint") or ""
    if not endpoint:
        raise ValueError("no endpoint")
    row = db.q1("SELECT id FROM push_subscriptions WHERE endpoint=?", (endpoint,))
    data = json.dumps(sub)
    if row:
        db.update("push_subscriptions", row["id"], {"subscription": data, "label": label or None, "last_ok_at": db.now_iso()})
        return row["id"]
    return db.insert("push_subscriptions", {"endpoint": endpoint, "subscription": data, "label": label or None,
                                            "created_at": db.now_iso(), "last_ok_at": db.now_iso()})


def remove_subscription(endpoint: str) -> None:
    db.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))


def _send_push(payload: dict) -> int:
    """Send to every subscription; drop the ones the push service says are gone. Returns how many succeeded."""
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
    priv, _pub = vapid_keys()
    vapid = Vapid.from_pem(priv.encode())   # pywebpush only takes raw/DER strings, not PEM
    claims = {"sub": "mailto:" + (config.get("cand_email") or "jobhunt@example.invalid")}
    ok = 0
    for s in subscriptions():
        try:
            webpush(subscription_info=json.loads(s["subscription"]), data=json.dumps(payload),
                    vapid_private_key=vapid, vapid_claims=dict(claims), ttl=3600)
            db.update("push_subscriptions", s["id"], {"last_ok_at": db.now_iso()})
            ok += 1
        except WebPushException as e:  # noqa: BLE001
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                remove_subscription(s["endpoint"])
            else:
                db.update("push_subscriptions", s["id"], {"last_error": str(e)[:300], "last_error_at": db.now_iso()})
        except Exception as e:  # noqa: BLE001
            db.update("push_subscriptions", s["id"], {"last_error": str(e)[:300], "last_error_at": db.now_iso()})
    return ok


def _send_webhook(payload: dict) -> bool:
    """ntfy topic URL (https://ntfy.sh/your-topic) or any URL that takes a JSON POST."""
    url = (config.get("notify_webhook_url") or "").strip()
    if not url:
        return False
    try:
        if "ntfy" in url:
            headers = {"Title": payload.get("title", "jobhunt"), "Priority": "high" if payload.get("urgent") else "default",
                       "Tags": "warning" if payload.get("urgent") else "calendar"}
            if payload.get("url"):
                headers["Click"] = payload["url"]
            httpx.post(url, content=payload.get("body", ""), headers=headers, timeout=10).raise_for_status()
        else:
            r = httpx.post(url, json=payload, timeout=10)
            r.raise_for_status()
        db.set_setting("notify_webhook_error", "")
        return True
    except Exception as e:  # noqa: BLE001
        db.set_setting("notify_webhook_error", str(e)[:300])
        return False


def send(title: str, body: str, *, url: str = "/", key: str = "", urgent: bool = False, action: str = "Open", step: str = "manual") -> dict:
    base = (config.get("notify_base_url") or "").rstrip("/")
    payload = {"title": title, "body": body, "url": (base + url) if base and url.startswith("/") else url,
               "key": key, "urgent": urgent, "action": action, "tag": key or "jobhunt", "renotify": True}
    res = {"push": _send_push(payload), "webhook": _send_webhook(payload)}
    db.insert("push_log", {"key": key or title, "step": step, "sent_at": db.now_iso(),
                           "title": title, "result": json.dumps(res)})
    return res


# ---- what to send, and when --------------------------------------------------

def _aware(s) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _quiet_now() -> bool:
    """Quiet hours in the machine's local zone, e.g. 22-8. Pushes wait until morning; nothing is lost."""
    span = (config.get("notify_quiet_hours") or "22-8").strip()
    try:
        start, end = (int(p) for p in span.split("-"))
    except ValueError:
        return False
    h = datetime.now().astimezone().hour
    return (start <= h or h < end) if start > end else (start <= h < end)


def _already(key: str, step: str) -> bool:
    return db.q1("SELECT 1 FROM push_log WHERE key=? AND step=?", (key, step)) is not None


def _snoozed(key: str) -> bool:
    r = db.q1("SELECT until FROM push_snooze WHERE key=?", (key,))
    return bool(r) and (_aware(r["until"]) or datetime.min.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc)


def snooze(key: str, hours: float = 1) -> None:
    until = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="minutes")
    db.execute("INSERT INTO push_snooze(key, until) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET until=excluded.until", (key, until))


def _fmt(at: datetime) -> str:
    local = at.astimezone()
    days = (local.date() - datetime.now().astimezone().date()).days
    day = "today" if days == 0 else "tomorrow" if days == 1 else local.strftime("%a %b %d")
    return f"{day} {local.strftime('%I:%M %p').lstrip('0')}"


def due_pushes() -> list[dict]:
    """Everything that should go out right now: [{key, step, title, body, url, urgent, action}]."""
    from .web.app import do_by   # buffered do-by date lives with the Today page
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for x in db.q("SELECT * FROM assessments WHERE status='pending'"):
        key = f"assessment:{x['id']}"
        due = _aware(x.get("due_at"))
        label = f"{x.get('company') or ''} test" + (f" on {x['platform']}" if x.get("platform") else "")
        if due is None:
            if not _already(key, "nodeadline"):
                out.append({"key": key, "step": "nodeadline", "title": f"{label}: no deadline given", "urgent": True,
                            "body": "Ask the recruiter how long you have, and do it this week.", "url": "/", "action": "Open"})
            continue
        target = do_by(due, now) or due
        hours = (target - now).total_seconds() / 3600
        for step in TEST_STEPS:
            if hours <= step and not _already(key, str(step)) and hours > -24:
                when = _fmt(target) if hours > 0 else "now"
                out.append({"key": key, "step": str(step), "title": f"{label}: do it by {when}", "urgent": step <= 24,
                            "body": (f"About {x['est_minutes']} min. " if x.get("est_minutes") else "")
                                    + f"Real deadline {_fmt(due)}. Links can die early.",
                            "url": f"/assessments/{x['id']}/open" if x.get("link") else "/", "action": "Open test" if x.get("link") else "Open"})
                break   # one step per poll; the closer ones come on later polls if still open
    for x in db.q("SELECT * FROM interviews WHERE status IN ('needs_scheduling','scheduled')"):
        key = f"interview:{x['id']}"
        label = f"{x.get('stage') or 'Interview'} · {x.get('company') or ''}"
        at = _aware(x.get("starts_at"))
        if at is None:
            if not _already(key, "pick"):
                out.append({"key": key, "step": "pick", "title": f"Pick a time: {label}", "urgent": True,
                            "body": "They asked for your availability. Reply today, before the slot goes.",
                            "url": x.get("link") or "/upcoming#interviews", "action": "Schedule" if x.get("link") else "Open"})
            continue
        hours = (at - now).total_seconds() / 3600
        for step in INTERVIEW_STEPS:
            if hours <= step and not _already(key, str(step)) and hours > -1:
                out.append({"key": key, "step": str(step), "title": f"{label} {_fmt(at)}", "urgent": True,
                            "body": (f"With {x['interviewer']}. " if x.get("interviewer") else "") + (x.get("location") or "")
                                    + (" Prep card is ready." if x.get("prep_json") else " Tap for the prep card."),
                            "url": x.get("link") if (x.get("link") and step <= 1) else f"/interviews/{x['id']}/prep",
                            "action": "Join" if (x.get("link") and step <= 1) else "Prep"})
                break
    return out


def tick() -> int:
    """One scheduler pass. Returns how many notifications went out."""
    if not (subscriptions() or (config.get("notify_webhook_url") or "").strip()):
        return 0
    if _quiet_now():
        return 0
    n = 0
    for p in due_pushes():
        if _snoozed(p["key"]):
            continue
        res = send(**p)
        if res["push"] or res["webhook"]:
            n += 1
    return n


_thread: threading.Thread | None = None


def start_scheduler() -> None:
    """Background loop; safe to call more than once."""
    global _thread
    if _thread and _thread.is_alive():
        return

    def loop():
        time.sleep(20)   # let the server finish starting
        while True:
            try:
                tick()
            except Exception as e:  # noqa: BLE001
                db.set_setting("notify_last_error", f"{db.now_iso()} {e}"[:300])
            time.sleep(POLL_SECONDS)

    _thread = threading.Thread(target=loop, name="notify", daemon=True)
    _thread.start()
