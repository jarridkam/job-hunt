"""Correspondence: every email a company sent about an application, and your replies, as one thread. Replies go out
as ordinary email through the same mailbox the tracker reads (Gmail app password works for SMTP too), threaded
with In-Reply-To so they land in the recruiter's existing conversation."""
from __future__ import annotations

import email.utils
import re
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from . import config, db, followup, llm

NOREPLY = re.compile(r"no-?reply|do-?not-?reply|notifications?@|mailer-daemon|postmaster", re.I)


class ReplyDraft(BaseModel):
    subject: str = Field(description="Subject line. 'Re: ...' when replying to a message.")
    body: str = Field(description="Plain-text email body, greeting to sign-off. Only what this reply needs, usually 2-5 sentences.")


SYSTEM = """You draft replies for a job seeker's correspondence with recruiters and hiring teams.
Write in the candidate's voice: plain, warm, specific, no filler, no buzzwords, no exclamation marks.
Stay on topic. Answer what the last message asked and do what it needs, and nothing else. As short as that allows.
Do not bring up anything they didn't raise: no work location or remote preferences, no relocation, salary, skills or
background, and no selling the candidate. A fact is for answering a question, not for filling space.
If scheduling is the topic, offer two or three concrete windows in the coming week during business hours, and never
during anything under ALREADY BOOKED. Check the day of the week against the date. Name the time zone in one plain
word, like "Pacific", never "Daylight" or "Standard". If they asked for a call or scheduling, sign off with the
candidate's full name and phone number; otherwise sign with their first name.
Never invent facts about the candidate; if something is unknown, say you will confirm. Plain text only."""


# ---- threads ---------------------------------------------------------------------

def inbound(app_id: int) -> list[dict]:
    """Company emails on this application (linked through the tracker's events), oldest first, one per email."""
    rows = db.q("SELECT e.id, e.from_addr, e.subject, e.received_at, e.snippet, e.body, e.message_id, e.folder, "
                "GROUP_CONCAT(ev.event_type) AS event_types FROM application_events ev JOIN emails e ON e.id=ev.email_id "
                "WHERE ev.application_id=? GROUP BY e.id ORDER BY e.received_at", (app_id,))
    for r in rows:
        kinds = [k for k in (r.pop("event_types") or "").split(",") if k]
        r["event_type"] = next((k for k in kinds if k != "created_from_email"), kinds[0] if kinds else "")
        r["direction"] = "in"
        r["at"] = r["received_at"]
        r["text"] = r.get("body") or r.get("snippet") or ""
        r["who"] = _display(r.get("from_addr"))
    return rows


def outbound(app_id: int) -> list[dict]:
    rows = db.q("SELECT * FROM messages WHERE application_id=? ORDER BY COALESCE(sent_at, created_at)", (app_id,))
    for r in rows:
        r["direction"] = "out"
        r["at"] = r.get("sent_at") or r.get("created_at")
        r["text"] = r.get("body") or ""
        r["who"] = "You"
    return rows


def thread(app_id: int) -> list[dict]:
    return sorted(inbound(app_id) + outbound(app_id), key=lambda m: m["at"] or "")


def _display(addr: str | None) -> str:
    name, a = email.utils.parseaddr(addr or "")
    return name or a or "?"


def threads() -> list[dict]:
    """Applications that have any correspondence, newest activity first, with the last message and reply hint."""
    out = []
    apps = db.q("SELECT a.id, a.company, a.title, a.status FROM applications a WHERE EXISTS "
                "(SELECT 1 FROM application_events ev WHERE ev.application_id=a.id AND ev.email_id IS NOT NULL) "
                "OR EXISTS (SELECT 1 FROM messages m WHERE m.application_id=a.id)")
    for a in apps:
        msgs = thread(a["id"])
        if not msgs:
            continue
        last = msgs[-1]
        last_in = next((m for m in reversed(msgs) if m["direction"] == "in"), None)
        a.update({"last": last, "last_at": last["at"], "n": len(msgs),
                  "awaiting_you": last["direction"] == "in" and bool(last_in) and not NOREPLY.search(last_in.get("from_addr") or "")
                                  and (last_in.get("event_type") in ("interview_invite", "recruiter_outreach"))})
        out.append(a)
    out.sort(key=lambda a: a["last_at"] or "", reverse=True)
    out.sort(key=lambda a: not a["awaiting_you"])      # stable: reply-needed first, newest first within each
    return out


def reply_target(app_id: int) -> dict:
    """Who a reply goes to and what it threads under: the newest human sender."""
    for m in reversed(inbound(app_id)):
        if m.get("from_addr") and not NOREPLY.search(m["from_addr"]):
            subj = m.get("subject") or ""
            return {"to": email.utils.parseaddr(m["from_addr"])[1] or m["from_addr"], "subject": subj if subj.lower().startswith("re:") else f"Re: {subj}".strip(),
                    "in_reply_to": m.get("message_id") or "", "email_id": m["id"]}
    return {"to": email.utils.parseaddr(followup.contact(app_id))[1], "subject": "", "in_reply_to": "", "email_id": None}


# ---- sending ---------------------------------------------------------------------

def smtp_ready() -> bool:
    return bool(config.get("email_user").strip() and config.get("email_pass").strip())


def _smtp():
    host = (config.get("smtp_host") or "").strip() or config.get("email_host").strip().replace("imap.", "smtp.", 1)
    port = config.get_int("smtp_port", 587)
    user, pw = config.get("email_user").strip(), config.get("email_pass").replace(" ", "").strip()
    if not (host and user and pw):
        raise RuntimeError("Email not configured (Settings > IMAP user/password; SMTP uses the same login).")
    if port == 465:
        s = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        s = smtplib.SMTP(host, port, timeout=30)
        s.ehlo(); s.starttls(); s.ehlo()
    s.login(user, pw)
    return s, user


def send(app_id: int, to: str, subject: str, body: str, in_reply_to: str = "") -> int:
    """Send and record. Raises with a plain message on failure (nothing is recorded as sent then)."""
    to = email.utils.parseaddr(to)[1] or to.strip()    # a pasted "Name <address>" still sends
    subject, body = subject.strip() or "(no subject)", body.strip()
    if not to or "@" not in to:
        raise RuntimeError("Who is this going to? Add an email address.")
    if not body:
        raise RuntimeError("The message is empty.")
    cand = config.candidate()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = to
    msg["Date"] = email.utils.format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = email.utils.make_msgid(domain=None)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    s, user = _smtp()
    msg["From"] = email.utils.formataddr((cand.full_name or user, user)) if cand.full_name else user
    try:
        s.send_message(msg)
    finally:
        try:
            s.quit()
        except Exception:  # noqa: BLE001
            pass
    now = db.now_iso()
    mid = db.insert("messages", {"application_id": app_id, "to_addr": to, "from_addr": user, "subject": subject, "body": body,
                                 "in_reply_to": in_reply_to or None, "message_id": msg["Message-ID"], "status": "sent",
                                 "sent_at": now, "created_at": now})
    db.add_event(app_id, "message_sent", f"To {to}: {subject}", source="manual")
    db.update("applications", app_id, {"last_update_at": now})
    return mid


def test_send() -> tuple[bool, str]:
    """A note to yourself, so Settings can say whether sending works."""
    try:
        s, user = _smtp()
        msg = EmailMessage()
        msg["Subject"] = "jobhunt can send email"
        msg["From"] = msg["To"] = user
        msg.set_content("Replies you write in jobhunt's Messages tab go out from this address.")
        s.send_message(msg); s.quit()
        return True, f"Sent a test email to {user}."
    except smtplib.SMTPAuthenticationError as e:
        return False, f"SMTP login failed. Gmail needs the same App Password as IMAP, with 2-Step Verification on. Server said: {e.smtp_error.decode(errors='ignore') if isinstance(e.smtp_error, bytes) else e}"
    except Exception as e:  # noqa: BLE001
        return False, f"Couldn't send: {e}"


# ---- AI draft --------------------------------------------------------------------

def _booked() -> list[str]:
    """Interviews still ahead, in local time, so offered windows never clash with them."""
    out = []
    now = datetime.now(timezone.utc)
    for x in db.q("SELECT company, starts_at, duration_minutes FROM interviews WHERE status='scheduled' AND starts_at IS NOT NULL ORDER BY starts_at"):
        try:
            at = datetime.fromisoformat(x["starts_at"].replace("Z", "+00:00"))
        except ValueError:
            continue
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        if at > now:
            out.append(f"- {at.astimezone().strftime('%A %B %d, %I:%M %p')} ({x['duration_minutes'] or 60} min, {x['company']})")
    return out


def draft(app_id: int, instruction: str = "") -> ReplyDraft:
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not a:
        raise RuntimeError("application not found")
    cand = config.candidate()
    msgs = thread(app_id)[-8:]
    convo = "\n\n".join(f"[{m['direction'].upper()} · {m['who']} · {(m['at'] or '')[:16]}]\nSUBJECT: {m.get('subject') or ''}\n{(m['text'] or '')[:2500]}" for m in msgs)
    today = datetime.now().astimezone()
    zone = (today.tzname() or "").split(" ")[0]
    parts = [f"CANDIDATE: {cand.full_name} (first name {cand.first_name or '?'}), phone {cand.phone or 'unknown'}",
             f"NOW: {today.strftime('%A %B %d %Y, %I:%M %p')}. Candidate's time zone: {zone}.",
             f"COMPANY: {a.get('company')}", f"ROLE: {a.get('title')}", f"APPLICATION STATUS: {a.get('status')}"]
    if config.get("voice_notes"):
        parts.append(f"VOICE: {config.get('voice_notes')}")
    if config.get("cand_extra_answers"):
        parts.append(f"FACTS ABOUT THE CANDIDATE (use only to answer a direct question):\n{config.get('cand_extra_answers')[:1500]}")
    booked = _booked()
    if booked:
        parts.append("ALREADY BOOKED:\n" + "\n".join(booked))
    parts.append(f"CONVERSATION SO FAR (oldest first):\n{convo or '(none yet; this is a first message)'}")
    parts.append("INSTRUCTION: " + (instruction.strip() or "Reply to the last message from the company."))
    return llm.extract(SYSTEM, "\n\n".join(parts), ReplyDraft, model=config.get("model_main"), effort="low", max_tokens=1200, purpose="reply")
