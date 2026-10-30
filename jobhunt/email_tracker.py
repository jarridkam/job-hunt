"""IMAP inbox sync -> assessments and application status events."""
from __future__ import annotations

import email
import email.utils
import imaplib
import math
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from . import config, db, deadlines, llm
from .models import EmailClassification
from .sources.base import strip_html

# Strong signals: anywhere in subject / sender / body.
PREFILTER = re.compile(
    r"assessment|hackerrank|codility|codesignal|karat|hirevue|testgorilla|pymetrics|virtual job tryout|take[- ]home|"
    r"coding (?:challenge|test|exercise)|online test|aptitude|interview|your application|application (?:received|status|update)|"
    r"thank you for (?:applying|your interest)|unfortunately|not (?:moving|be moving) forward|we regret|next steps?|"
    r"screening|phone screen|recruit|hiring|talent acquisition|"
    r"greenhouse|lever\.co|ashby|workable|myworkday|icims|smartrecruiters|jobvite|indeedapply|linkedin\.com/comm/jobs",
    re.I)
# Weak words: only count when they appear in the subject or sender, otherwise every marketing email with
# "offer" or "role" in the body burns an LLM call.
# Spam folder: only mail that is unmistakably a test or interview gets read (the rest of spam stays unread).
SPAM_SWEEP = re.compile(
    r"hackerrank|codility|codesignal|karat|hirevue|testgorilla|pymetrics|modernhire|modern hire|talview|micro1|"
    r"plum\.io|shl\.com|harver|vervoe|coderbyte|codingame|woven|byteboard|assessment|coding (?:challenge|test)|"
    r"online test|take[- ]home|interview|phone screen|greenhouse|lever\.co|ashby|myworkday|icims|smartrecruiters",
    re.I)

# Mail the user forwarded to themselves (or tagged) is always read: that is the "forward it to jobhunt" capture path.
FORWARDED = re.compile(r"^\s*(?:fwd?|fw|tr|wg)\s*:|\[jobhunt\]|#jobhunt", re.I)

PREFILTER_HEAD = re.compile(r"applied|application|candidate|position|offer|role|careers?|jobs?@|no-?reply@.*(?:hr|talent|careers|jobs)", re.I)

STATUS_RANK = {"stale": 0, "queued": 0, "drafting": 0, "ready": 0, "applying": 0, "needs_attention": 0, "failed": 0,
               "submitted": 1, "screening": 2, "assessment": 3, "interview": 4, "offer": 5, "rejected": 6, "withdrawn": 6}

KIND_TO_STATUS = {
    "application_received": "submitted", "assessment_invite": "assessment", "assessment_reminder": "assessment",
    "assessment_expired": "assessment", "interview_invite": "interview", "interview_scheduled": "interview",
    "interview_reminder": "interview", "offer": "offer", "rejection": "rejected",
}

CLASSIFY_SYSTEM = """You classify emails for a job seeker's application tracker.
Decide what the email is (assessment invite/reminder/completed/expired, application received, rejection, interview invite/scheduled/reminder/cancelled, offer, recruiter outreach, or other).
Interviews: 'interview_invite' = a person asks the candidate to pick or propose a time (recruiter screens and phone screens count; a self-schedule link counts). 'interview_scheduled' = a confirmed time exists; put it in interview_at with its zone in interview_tz. 'interview_reminder' = reminder of an already booked interview. 'interview_cancelled' = cancelled or rescheduled-away. A one-way recorded/AI video interview with a deadline (HireVue, micro1, Modern Hire) is an ASSESSMENT, not an interview. An information session or webinar is 'other'.
'assessment_expired' = the email says the assessment link or deadline has expired / was not completed in time. 'assessment_invite' with a deadline already in the past is also fine; the tracker marks it missed.
Company is the EMPLOYER, never the job board or tool that sent the mail (an "Indeed Application: X" confirmation names the employer in the body; HireVue/HackerRank/Modern Hire invites are sent on behalf of the employer).
Extract company, role, assessment platform, estimated time in minutes, and the main action link.
The action link is the candidate's own invite URL: the href behind the 'Start assessment' / 'Begin' / 'Take the test' button in the LINKS list, never a generic homepage, login page, help page, or unsubscribe link.
Deadlines: if the email gives a calendar date, put it in due_at (with its time zone in due_tz if stated). If it only says something relative ('within 7 days', 'in the next 48 hours', 'expires in 3 days', 'by the end of the week'), leave due_at empty and fill due_in_days / due_in_hours instead; the tracker adds them to the email's received time. Never invent a deadline the email does not state.
Newsletters, job alerts, marketing, and generic job-board digests are 'other'. Be conservative: if unsure between a real assessment and a marketing email, use 'other' with low confidence."""


def _prefilter():
    """Returns hit(subject, from_addr, body) -> bool. Built-in keywords plus whatever the user added in Settings
    (user keywords count anywhere, like the strong list)."""
    extra = [re.escape(k) for k in config.get_lines("email_extra_keywords")]
    strong = re.compile(PREFILTER.pattern + "|" + "|".join(extra), re.I) if extra else PREFILTER

    def hit(subject: str, from_addr: str, body: str) -> bool:
        head = f"{subject}\n{from_addr}"
        return bool(strong.search(f"{head}\n{body[:4000]}") or PREFILTER_HEAD.search(head))

    return hit


def _classify_system() -> str:
    hints = config.get_lines("email_hints")
    if not hints:
        return CLASSIFY_SYSTEM
    facts = "\n".join(f"- {h}" for h in hints)
    return f"{CLASSIFY_SYSTEM}\n\nFacts from the job seeker (trust these):\n{facts}"


def _norm(s: str | None) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|labs|group)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _body(msg: email.message.Message) -> str:
    plain, html_part = "", ""
    for part in msg.walk():
        ct = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception:  # noqa: BLE001
            continue
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if ct == "text/plain" and not plain:
            plain = text
        elif ct == "text/html" and not html_part:
            html_part = text
    if html_part and (not plain or len(plain) < 200 or "http" not in plain):
        # Keep the link targets: buttons like "Start assessment" are <a href=...> whose URL never appears in the
        # visible text. Rendered as 'Start assessment <https://...>' so both the LLM and _links can see them.
        html_part = _A.sub(lambda m: f" {_TAGS.sub(' ', m.group(2)).strip()} {{{{{m.group(1)}}}}} ", html_part)
        out = strip_html(html_part).replace("{{", "<").replace("}}", ">")   # placeholder survives the tag stripper
    else:
        out = plain
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


_A = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")


def _links(text: str) -> list[str]:
    """Links with the words next to them, action links first, e.g. 'Start assessment <https://...>'."""
    out, seen = [], set()
    for m in re.finditer(r"(?:([^\n<>]{0,60}?)\s*)?<?(https?://[^\s<>\"')\]]+)>?", text):
        label, url = (m.group(1) or "").strip(" -:|"), m.group(2)
        if url in seen or any(x in url.lower() for x in ("unsubscribe", "privacy", "facebook.com", "twitter.com", "linkedin.com/company")):
            continue
        seen.add(url)
        out.append(f"{label} <{url}>" if label else url)
    hot = re.compile(r"start|begin|take|launch|complete|assessment|interview|invite|accept|schedule|apply", re.I)
    out.sort(key=lambda s: 0 if hot.search(s) else 1)
    return out[:30]


UNKNOWN_ROLE = "(unknown role)"


def _norm_role(s: str | None) -> str:
    """'Software Engineer I (ID: 3141336)' -> 'software engineer i'."""
    s = re.sub(r"\(.*?\)|\b(?:job\s*)?(?:id|req(?:uisition)?)\b[:#\s]*[\w-]*\d[\w-]*", " ", (s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def match_application(company: str, role: str = "") -> dict | None:
    """The application an email is about. A company can have several (Amazon: Software Engineer I and
    IT Support Engineer I), so when the email names a role it must match that application's title; a
    different role means a new application. With no role named, the company's most recently active
    application wins, since follow-ups usually concern whatever was applied to last."""
    if not company:
        return None
    nc = _norm(company)
    same_company = []
    for a in db.q("SELECT id, company, title, status, last_update_at FROM applications"):
        ac = _norm(a.get("company"))
        if not ac:
            continue
        score = SequenceMatcher(None, nc, ac).ratio()
        if nc in ac or ac in nc:
            score = max(score, 0.9)
        if score >= 0.82:
            same_company.append(a)
    if not same_company:
        return None
    if role.strip():
        nr = _norm_role(role)
        best, best_score = None, 0.0
        for a in same_company:
            score = SequenceMatcher(None, nr, _norm_role(a.get("title"))).ratio()
            if score > best_score:
                best, best_score = a, score
        if best_score >= 0.88:
            return best
        unnamed = [a for a in same_company if (a.get("title") or UNKNOWN_ROLE) == UNKNOWN_ROLE]
        return unnamed[0] if unnamed else None
    def last_activity(a):  # when something last happened (emails, applying), not when the row was last edited
        ev = db.q1("SELECT MAX(happened_at) t FROM application_events WHERE application_id=?", (a["id"],)) or {}
        return str(ev.get("t") or a.get("last_update_at") or "")
    return max(same_company, key=last_activity)


def _connect() -> tuple[imaplib.IMAP4_SSL, str]:
    host, user, pw = config.get("email_host").strip(), config.get("email_user").strip(), config.get("email_pass")
    pw = pw.replace(" ", "").strip()  # Google shows app passwords with spaces; IMAP wants them without
    if not (host and user and pw):
        raise RuntimeError("Email not configured (Settings > IMAP host/user/password).")
    m = imaplib.IMAP4_SSL(host)
    try:
        m.login(user, pw)
    except imaplib.IMAP4.error as e:
        raise RuntimeError(
            "IMAP login failed. For Gmail use a 16-character App Password from myaccount.google.com/apppasswords "
            f"(needs 2-Step Verification on), not your normal password. Server said: {e}") from e
    folder = config.get("email_folder") or "INBOX"
    m.select(f'"{folder}"', readonly=True)
    return m, user


def spam_folders(m: imaplib.IMAP4_SSL) -> list[str]:
    """The server's junk folder(s): the one flagged \\Junk (Gmail: [Gmail]/Spam), else any named Spam/Junk."""
    try:
        typ, boxes = m.list()
    except Exception:  # noqa: BLE001
        return []
    found, fallback = [], []
    for raw in boxes or []:
        line = raw.decode(errors="ignore") if isinstance(raw, bytes) else str(raw)
        mm = re.match(r'\((?P<flags>[^)]*)\)\s+"?(?P<delim>[^"\s]+)"?\s+"?(?P<name>.+?)"?$', line)
        if not mm:
            continue
        name = mm.group("name").strip('"')
        if "\\junk" in mm.group("flags").lower():
            found.append(name)
        elif re.search(r"(^|/|\.)(spam|junk)( e-?mail)?$", name, re.I):
            fallback.append(name)
    return found or fallback


def test_connection() -> tuple[bool, str]:
    try:
        m, user = _connect()
        typ, data = m.uid("search", None, "ALL")
        n = len(data[0].split()) if data and data[0] else 0
        m.logout()
        return True, f"Connected as {user}. {n} messages in folder."
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def last_sync_at() -> datetime | None:
    """When the inbox was last synced successfully (from the PC or the CLI)."""
    r = db.q1("SELECT finished_at FROM runs WHERE kind='email' AND status='done' ORDER BY id DESC LIMIT 1")
    if not r or not r.get("finished_at"):
        return None
    try:
        dt = datetime.fromisoformat(str(r["finished_at"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def default_days() -> int:
    """Days back to look: whole days since the last sync (at least 1). First sync ever uses the Settings value."""
    last = last_sync_at()
    if last is None:
        return max(1, config.get_int("email_since_days", 60))
    return max(1, math.ceil((datetime.now(timezone.utc) - last).total_seconds() / 86400))


def sync(run_id: int, days: int | None = None) -> dict:
    log = lambda s: db.run_log(run_id, s)  # noqa: E731
    days = max(1, int(days or default_days()))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    m, account = _connect()
    stats = {"seen": 0, "classified": 0, "assessments": 0, "events": 0, "skipped": 0, "remaining": 0, "from_spam": 0}
    log(f"window: since {cutoff.astimezone():%b %d %H:%M} ({days} day{'s' if days != 1 else ''})")
    _sync_folder(m, account, config.get("email_folder") or "INBOX", cutoff, log, stats, spam=False)
    if config.get_bool("email_scan_spam"):
        for folder in spam_folders(m):
            try:
                m.select(f'"{folder}"', readonly=True)
            except Exception as e:  # noqa: BLE001
                db.run_warn(run_id, f"couldn't open your {folder} folder to look for tests: {e}")
                continue
            _sync_folder(m, account, folder, cutoff, log, stats, spam=True)
        try:
            m.select(f'"{config.get("email_folder") or "INBOX"}"', readonly=True)
        except Exception:  # noqa: BLE001
            pass
    _refresh_read_flags(m, account, log)
    m.logout()
    missed = mark_missed()
    if stats.get("failed"):
        db.run_warn(run_id, f"{stats['failed']} email(s) couldn't be read and will be retried next check: {stats.get('last_error', '')}")
    stats.pop("fail_streak", None); stats.pop("last_error", None)
    log(f"email sync done: {stats}; {missed} assessment(s) marked missed")
    return stats


def _account_key(account: str, folder: str, spam: bool) -> str:
    """IMAP UIDs are per folder, and emails.(account, uid) is unique, so spam-folder mail is keyed under
    'user#folder'. INBOX keeps the bare account so existing rows still match."""
    return f"{account}#{folder}" if spam else account


def _sync_folder(m: imaplib.IMAP4_SSL, account: str, folder: str, cutoff: datetime, log, stats: dict, *, spam: bool) -> None:
    """One folder pass. Looks at everything in the window, skips what we already stored, and works NEWEST FIRST so
    today's assessment invite is handled before the backlog. The cap limits LLM calls, not emails looked at.
    In the spam folder only mail that looks like a test or interview is read at all."""
    key = _account_key(account, folder, spam)
    # IMAP SINCE only takes a date, so search from the day before the cutoff and drop older mail below.
    since = (cutoff - timedelta(days=1)).strftime("%d-%b-%Y")
    typ, data = m.uid("search", None, f"SINCE {since}")
    uids = [int(u) for u in (data[0].split() if data and data[0] else [])]
    done = {r["uid"] for r in db.q("SELECT uid FROM emails WHERE account=?", (key,))}
    uids = sorted((u for u in uids if u not in done), reverse=True)
    cap = config.get_int("email_max_per_sync", 200)
    log(f"{folder}: {len(uids)} unprocessed message(s); newest first, stopping after {cap} LLM classifications"
        + (" (spam: only test/interview-looking mail is read)" if spam else ""))
    prefilter, system = _prefilter(), _classify_system()
    for i, uid in enumerate(uids):
        if stats["classified"] >= cap:
            stats["remaining"] = len(uids) - i
            log(f"LLM cap reached; {stats['remaining']} message(s) left for the next sync")
            break
        stats["seen"] += 1
        if spam:
            try:
                typ, hdr = m.uid("fetch", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
                head = (hdr[0][1] if hdr and hdr[0] else b"").decode(errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            if not SPAM_SWEEP.search(head):
                continue   # ordinary spam: never fetched, never stored
        try:
            typ, raw = m.uid("fetch", str(uid), "(FLAGS BODY.PEEK[])")
            msg = email.message_from_bytes(raw[0][1])
            read_flag = 1 if b"\\Seen" in (raw[0][0] or b"") else 0
        except Exception as e:  # noqa: BLE001
            log(f"uid {uid}: fetch failed {e}")
            continue
        subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", "")))) if msg.get("Subject") else ""
        from_addr = msg.get("From", "")
        date_hdr = msg.get("Date", "")
        try:
            received = email.utils.parsedate_to_datetime(date_hdr)
            if received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            received = datetime.now(timezone.utc)
        if received < cutoff:
            continue  # inside the IMAP date but before the cutoff time
        body = _body(msg)
        if db.q1("SELECT id FROM emails WHERE account=? AND uid=?", (key, uid)):
            continue
        res = ingest(account=key, uid=uid, from_addr=from_addr, subject=subject, body=body, received=received,
                     folder=folder, seen=read_flag, log=log, stats=stats, prefilter=prefilter, system=system,
                     message_id=(msg.get("Message-ID") or "").strip() or None)
        if res.get("error"):
            stats["fail_streak"] = stats.get("fail_streak", 0) + 1
            if stats["fail_streak"] >= 3:
                raise RuntimeError(f"Stopped reading email after 3 failures in a row: {res['error']}")
        else:
            stats["fail_streak"] = 0
        c = res.get("classification")
        if spam and c is not None and res.get("app_id"):
            stats["from_spam"] += 1
            log(f"IN SPAM: {subject[:70]!r} -> {c.kind} ({c.company})")


def ingest(*, account: str, uid: int, from_addr: str, subject: str, body: str, received: datetime, folder: str = "",
           seen: int = 0, log=None, stats: dict | None = None, prefilter=None, system: str | None = None,
           force: bool = False, message_id: str | None = None) -> dict:
    """Store one message, classify it if it looks relevant, and apply the result (application / test / interview).
    Returns {email_id, classification (or None), app_id (or None), skipped (bool)}. `force` skips the keyword
    prefilter: used for pasted text and for mail the user forwarded to themselves."""
    log = log or (lambda m: None)
    stats = stats if stats is not None else {"seen": 0, "classified": 0, "assessments": 0, "events": 0, "skipped": 0, "remaining": 0, "from_spam": 0}
    prefilter = prefilter or _prefilter()
    system = system or _classify_system()
    forwarded = bool(FORWARDED.search(subject or ""))
    email_id = db.insert("emails", {"account": account, "uid": uid, "from_addr": from_addr, "subject": subject,
                                    "received_at": received.isoformat(), "snippet": body[:300], "seen": seen, "folder": folder,
                                    "message_id": message_id})
    out = {"email_id": email_id, "classification": None, "app_id": None, "skipped": False}
    if not (force or forwarded) and not prefilter(subject, from_addr, body):
        stats["skipped"] += 1
        db.update("emails", email_id, {"processed_at": db.now_iso(), "classification": db.dumps({"kind": "other", "prefilter": False})})
        out["skipped"] = True
        return out
    note = ("NOTE: the candidate forwarded or pasted this themselves. Classify the ORIGINAL message inside it "
            "(the forwarded headers give the real sender and date); ignore the forwarding wrapper.\n" if forwarded or force else "")
    user = (f"{note}EMAIL DATE: {received.isoformat()}\nFROM: {from_addr}\nSUBJECT: {subject}\n\nBODY:\n{body[:7000]}\n\n"
            f"LINKS:\n" + "\n".join(_links(body)))
    try:
        c = llm.extract(system, user, EmailClassification, model=config.get("model_fast"), effort="low", purpose="email")
    except Exception as e:  # noqa: BLE001
        # Forget the row so the next sync reads this email again; a lost test invite is the worst outcome here.
        db.execute("DELETE FROM emails WHERE id=?", (email_id,))
        stats["failed"] = stats.get("failed", 0) + 1
        stats["last_error"] = str(e)
        log(f"uid {uid}: couldn't read {subject[:60]!r}, will retry next check: {e}")
        out["error"] = str(e)
        return out
    stats["classified"] += 1
    out["classification"] = c
    db.update("emails", email_id, {"processed_at": db.now_iso(), "classification": c.model_dump_json(), "body": body[:20000]})
    if c.kind in ("other",) or (c.kind == "recruiter_outreach" and c.confidence != "high" and not force):
        return out
    if forwarded:
        log(f"FORWARDED: {subject[:70]!r} -> {c.kind} ({c.company})")
    out["app_id"] = _apply_classification(c, email_id, received, subject, log, stats)
    return out


def _apply_classification(c: EmailClassification, email_id: int, received: datetime, subject: str, log, stats) -> int | None:
    app = match_application(c.company, c.role)
    now = db.now_iso()
    if not app and c.kind != "recruiter_outreach":
        status = KIND_TO_STATUS.get(c.kind, "submitted")
        app_id = db.insert("applications", {
            "job_id": None, "company": c.company or "(unknown)", "title": c.role or UNKNOWN_ROLE, "status": status,
            "applied_at": received.isoformat(), "last_update_at": now, "created_at": now,
            "notes": f"Created from email: {subject[:120]}",
        })
        db.add_event(app_id, "created_from_email", c.summary, source="email", email_id=email_id, happened_at=received.isoformat())
        app = {"id": app_id, "status": status}
        log(f"new application from email: {c.company} - {c.role} ({c.kind})")
    if not app:
        return None
    app_id = app["id"]
    if c.role and (app.get("title") or UNKNOWN_ROLE) == UNKNOWN_ROLE:
        db.update("applications", app_id, {"title": c.role})
    detail = c.summary + (f" [{c.link}]" if c.link else "")
    db.add_event(app_id, c.kind, detail, source="email", email_id=email_id, happened_at=received.isoformat())
    stats["events"] += 1
    new_status = KIND_TO_STATUS.get(c.kind)
    cur = db.q1("SELECT status FROM applications WHERE id=?", (app_id,))["status"]
    if new_status and STATUS_RANK.get(new_status, 0) >= STATUS_RANK.get(cur, 0) and new_status != cur:
        db.update("applications", app_id, {"status": new_status, "last_update_at": now})
        job_id = (db.q1("SELECT job_id FROM applications WHERE id=?", (app_id,)) or {}).get("job_id")
        if job_id:
            db.update("jobs", job_id, {"status": "applied"})
    db.update("applications", app_id, {"last_update_at": now})
    _apply_assessment(c, app_id, email_id, received, now, log, stats)
    _apply_interview(c, app_id, email_id, received, now, log, stats)
    return app_id


ASSESSMENT_KINDS = ("assessment_invite", "assessment_reminder", "assessment_completed", "assessment_expired")
INTERVIEW_KINDS = ("interview_invite", "interview_scheduled", "interview_reminder", "interview_cancelled")


def _find_interview(app_id: int) -> dict | None:
    """The open interview this email is about: the newest one for the application that is not over yet."""
    return db.q1("SELECT * FROM interviews WHERE application_id=? AND status IN ('needs_scheduling','scheduled') "
                 "ORDER BY id DESC LIMIT 1", (app_id,))


def _apply_interview(c: EmailClassification, app_id: int, email_id: int, received: datetime, now: str, log, stats) -> None:
    if c.kind not in INTERVIEW_KINDS:
        return
    stats.setdefault("interviews", 0)
    when = received.isoformat()
    # Classifications stored before interview_at existed put the booked time in due_at.
    at, at_tz = (c.interview_at, c.interview_tz) if c.interview_at else (c.due_at if c.kind != "interview_invite" else "", c.due_tz)
    start_iso, _src, tz = deadlines.resolve(at, 0, 0, at_tz, received)
    fields = {"company": c.company, "title": c.role or None, "stage": c.interview_stage or None,
              "format": c.interview_format or None, "link": c.link or None,
              "duration_minutes": c.est_minutes or None, "interviewer": c.interviewer or None}
    existing = _find_interview(app_id)
    if c.kind == "interview_cancelled":
        if existing:
            db.update("interviews", existing["id"], {"status": "cancelled", "notes": c.summary})
            log(f"interview cancelled: {c.company}")
        return
    if existing:
        # Newest-first processing: an older email only fills blanks. A stated time always beats "needs scheduling".
        newer = when > (existing["received_at"] or "")
        upd = {k: v for k, v in fields.items() if v and (newer or not existing[k])}
        if start_iso and (newer or not existing["starts_at"]) and existing.get("time_source") != "manual":
            upd.update({"starts_at": start_iso, "time_source": "stated", "tz": tz or None, "status": "scheduled"})
        if newer:
            upd["received_at"] = when
        if upd:
            db.update("interviews", existing["id"], upd)
    else:
        fields.update({"application_id": app_id, "received_at": when, "email_id": email_id, "created_at": now,
                       "starts_at": start_iso, "time_source": "stated" if start_iso else None, "tz": tz or None,
                       "status": "scheduled" if start_iso else "needs_scheduling"})
        db.insert("interviews", fields)
        stats["interviews"] += 1
        log(f"interview: {c.company} {fields['stage'] or ''} at {start_iso or 'time not set yet'}")


def rebuild_interviews() -> int:
    """Drop every email-derived interview and rebuild from stored classifications, newest email first
    (the same order sync uses, so the fill-blanks rule behaves the same). Manual ones are kept."""
    db.execute("DELETE FROM interviews WHERE email_id IS NOT NULL")
    rows = db.q("SELECT id, received_at, classification FROM emails WHERE classification IS NOT NULL ORDER BY received_at DESC")
    stats = {"interviews": 0}
    for r in rows:
        data = db.loads(r["classification"]) or {}
        if data.get("kind") not in INTERVIEW_KINDS:
            continue
        c = EmailClassification.model_validate(data)
        # The event sync wrote for this email says which application it belongs to (titles may have been edited since).
        app = db.q1("SELECT application_id AS id FROM application_events WHERE email_id=? AND application_id IS NOT NULL "
                    "ORDER BY id DESC LIMIT 1", (r["id"],)) or match_application(c.company, c.role)
        if not app:
            continue
        _apply_interview(c, app["id"], r["id"], datetime.fromisoformat(r["received_at"]), db.now_iso(), lambda s: None, stats)
    return stats["interviews"]


def _status_from_events(app_id: int) -> str:
    """The furthest stage an application's email events show (applied < screening < assessment < ...)."""
    best = "submitted"
    for e in db.q("SELECT event_type FROM application_events WHERE application_id=?", (app_id,)):
        s = KIND_TO_STATUS.get(e["event_type"])
        if s and STATUS_RANK.get(s, 0) > STATUS_RANK.get(best, 0):
            best = s
    return best


def relink_assessment(aid: int, app_id: int | None = None, new_role: str = "") -> int | None:
    return relink("assessments", aid, app_id, new_role)


def relink(table: str, row_id: int, app_id: int | None = None, new_role: str = "") -> int | None:
    """Move an assessment or interview (and the email events behind it) to another application, or to a new
    application for new_role at the same company. Both applications' statuses are recomputed. Returns the target app id."""
    assert table in ("assessments", "interviews")
    x = db.q1(f"SELECT * FROM {table} WHERE id=?", (row_id,))
    if not x:
        return None
    old = x.get("application_id")
    now = db.now_iso()
    if new_role.strip():
        app_id = db.insert("applications", {
            "job_id": None, "company": x.get("company") or "(unknown)", "title": new_role.strip(),
            "status": "assessment" if table == "assessments" else "interview",
            "applied_at": x.get("received_at") or now, "last_update_at": now, "created_at": now,
            "notes": "Split off when you re-linked an " + ("assessment." if table == "assessments" else "interview.")})
    if not app_id or app_id == old:
        return old
    db.update(table, row_id, {"application_id": app_id})
    if table == "interviews" and old:
        # One interview thread = several emails (invite, confirmation, reminder); move them all together.
        marks = ",".join("?" * len(INTERVIEW_KINDS))
        db.execute(f"UPDATE application_events SET application_id=? WHERE application_id=? AND event_type IN ({marks})",
                   (app_id, old, *INTERVIEW_KINDS))
    elif x.get("email_id") and old:
        db.execute("UPDATE application_events SET application_id=? WHERE application_id=? AND email_id=?",
                   (app_id, old, x["email_id"]))
    for a in (old, app_id):
        if not a:
            continue
        cur = (db.q1("SELECT status FROM applications WHERE id=?", (a,)) or {}).get("status")
        if cur in KIND_TO_STATUS.values() or cur == "submitted":   # only email-driven stages; leave manual ones
            db.update("applications", a, {"status": _status_from_events(a), "last_update_at": now})
    return app_id


def _find_assessment(app_id: int, platform: str | None) -> dict | None:
    """The open assessment this email is about. One application can have several (HireVue + HackerRank at AT&T),
    so match on platform when the email names one; an unnamed platform matches any open one."""
    rows = db.q("SELECT * FROM assessments WHERE application_id=? AND status='pending' ORDER BY id DESC", (app_id,))
    p = _norm(platform)
    for r in rows:
        if not p or not r["platform"] or _norm(r["platform"]) == p:
            return r
    return None


def _apply_assessment(c: EmailClassification, app_id: int, email_id: int, received: datetime, now: str, log, stats) -> None:
    if c.kind not in ASSESSMENT_KINDS:
        return
    existing = _find_assessment(app_id, c.platform)
    when = received.isoformat()
    due_iso, due_source, due_tz = deadlines.resolve(c.due_at, getattr(c, "due_in_days", 0), getattr(c, "due_in_hours", 0),
                                                    getattr(c, "due_tz", ""), received,
                                                    config.get_int("assessment_default_days", 7))
    fields = {"company": c.company, "title": c.role or "Assessment", "platform": c.platform or None,
              "link": c.link or None, "due_at": due_iso, "due_source": due_source if due_iso else None,
              "due_tz": due_tz or None, "est_minutes": c.est_minutes or None}

    if c.kind in ("assessment_invite", "assessment_reminder"):
        if existing:
            # Emails are processed newest-first, so an older email must only fill blanks, never overwrite.
            newer = when > (existing["received_at"] or "")
            upd = {k: v for k, v in fields.items() if v and (newer or not existing[k])}
            if newer:
                upd["received_at"] = when
            real = due_source in ("stated", "relative")
            had_real = (existing.get("due_source") or "") in ("stated", "relative")
            if due_iso and real and not had_real:          # upgrade a guess to a real deadline
                upd.update({"due_at": due_iso, "due_source": due_source, "due_tz": due_tz or None})
            elif due_iso and not real and had_real:        # never downgrade a real deadline to a guess
                for k in ("due_at", "due_source", "due_tz"):
                    upd.pop(k, None)
            if upd:
                db.update("assessments", existing["id"], upd)
        else:
            fields.update({"application_id": app_id, "status": "pending", "received_at": when,
                           "email_id": email_id, "created_at": now})
            db.insert("assessments", fields)
            stats["assessments"] += 1
            log(f"assessment: {c.company} {c.platform} due {c.due_at or '?'} (~{c.est_minutes or '?'} min)")
    elif c.kind == "assessment_completed":
        if existing:
            db.update("assessments", existing["id"], {"status": "completed", "completed_at": when})
    elif c.kind == "assessment_expired":
        if existing:
            db.update("assessments", existing["id"], {"status": "missed", "due_at": existing["due_at"] or due_iso or when})
        else:
            # Never saw the invite (older than the sync window, or filtered); record it as missed anyway.
            fields.update({"application_id": app_id, "due_at": due_iso if due_source != "assumed" else when, "status": "missed",
                           "received_at": when, "email_id": email_id, "created_at": now})
            db.insert("assessments", fields)
            stats["assessments"] += 1
        log(f"assessment expired: {c.company} {c.platform}")


def rebuild_assessments() -> int:
    """Drop every email-derived assessment and rebuild from stored classifications in date order.
    Used after a change to the matching rules; costs nothing (no LLM calls)."""
    db.execute("DELETE FROM assessments WHERE email_id IS NOT NULL")
    rows = db.q("SELECT id, received_at, classification FROM emails WHERE classification IS NOT NULL ORDER BY received_at")
    stats = {"assessments": 0}
    n = 0
    for r in rows:
        data = db.loads(r["classification"]) or {}
        if data.get("kind") not in ASSESSMENT_KINDS:
            continue
        c = EmailClassification.model_validate(data)
        app = match_application(c.company, c.role)
        if not app:
            continue
        received = datetime.fromisoformat(r["received_at"])
        _apply_assessment(c, app["id"], r["id"], received, db.now_iso(), lambda s: None, stats)
        n += 1
    mark_missed()
    return stats["assessments"]


def reclassify_assessment_emails(run_id: int) -> dict:
    """Re-run the classifier on every stored assessment and interview email (so new fields get filled), then rebuild.
    Uses the stored body when we have it; otherwise fetches the message again over IMAP by UID."""
    log = lambda s: db.run_log(run_id, s)  # noqa: E731
    rows = db.q("SELECT id, uid, account, folder, from_addr, subject, received_at, body, classification FROM emails "
                "WHERE classification LIKE '%assessment_%' OR classification LIKE '%interview_%' ORDER BY received_at")
    log(f"{len(rows)} stored assessment/interview email(s) to re-read")
    system = _classify_system()
    m = None
    done = failed = 0
    for r in rows:
        body = r["body"] or ""
        if not body:
            try:
                if m is None:
                    m, _ = _connect()
                if r.get("folder") and r["folder"] != (config.get("email_folder") or "INBOX"):
                    m.select(f'"{r["folder"]}"', readonly=True)
                typ, raw = m.uid("fetch", str(r["uid"]), "(BODY.PEEK[])")
                m.select(f'"{config.get("email_folder") or "INBOX"}"', readonly=True)
                body = _body(email.message_from_bytes(raw[0][1]))
                db.update("emails", r["id"], {"body": body[:20000]})
            except Exception as e:  # noqa: BLE001
                log(f"email {r['id']}: refetch failed {e}")
                failed += 1
                continue
        user = (f"EMAIL DATE: {r['received_at']}\nFROM: {r['from_addr']}\nSUBJECT: {r['subject']}\n\nBODY:\n{body[:7000]}\n\n"
                f"LINKS:\n" + "\n".join(_links(body)))
        try:
            c = llm.extract(system, user, EmailClassification, model=config.get("model_fast"), effort="low", purpose="email")
        except Exception as e:  # noqa: BLE001
            log(f"email {r['id']}: classify failed {e}")
            failed += 1
            continue
        db.update("emails", r["id"], {"classification": c.model_dump_json()})
        done += 1
        log(f"{r['subject'][:60]!r}: {c.kind} due_at={c.due_at or '-'} +{c.due_in_days}d +{c.due_in_hours}h tz={c.due_tz or '-'}"
            + (f" interview_at={c.interview_at} {c.interview_tz} {c.interview_format} {c.interview_stage}" if c.interview_at or c.interview_stage else ""))
    if m is not None:
        m.logout()
    n = rebuild_assessments()
    k = rebuild_interviews()
    log(f"rebuilt {n} assessment(s), {k} interview(s)")
    return {"reclassified": done, "failed": failed, "assessments": n, "interviews": k}


def _refresh_read_flags(m: imaplib.IMAP4_SSL, account: str, log) -> None:
    """Re-check Gmail's read flag for invite emails behind still-pending assessments (cheap: FLAGS only)."""
    rows = db.q("SELECT e.id, e.uid FROM assessments a JOIN emails e ON e.id = a.email_id "
                "WHERE a.status = 'pending' AND e.account = ? AND COALESCE(e.seen, 0) = 0", (account,))
    for r in rows:   # INBOX only; spam-folder invites are read when the user opens them from here
        try:
            typ, data = m.uid("fetch", str(r["uid"]), "(FLAGS)")
            if data and data[0] and b"\\Seen" in data[0]:
                db.update("emails", r["id"], {"seen": 1})
        except Exception as e:  # noqa: BLE001
            log(f"flags uid {r['uid']}: {e}")


MISSED_GRACE_HOURS = 72


def mark_missed() -> int:
    now = datetime.now(timezone.utc)
    # Assumed deadlines are guesses: show them as overdue in the UI but never flip the status on their account.
    rows = db.q("SELECT id, due_at FROM assessments WHERE status='pending' AND due_at IS NOT NULL AND due_at != '' "
                "AND COALESCE(due_source,'') != 'assumed'")
    n = 0
    for r in rows:
        try:
            due = datetime.fromisoformat(r["due_at"])
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            continue
        # Grace period: test links often keep working after the stated deadline, so a test stays on Today,
        # openable, for MISSED_GRACE_HOURS before it is filed as missed. Nothing ever blocks opening it.
        if due < now - timedelta(hours=MISSED_GRACE_HOURS):
            db.update("assessments", r["id"], {"status": "missed"})
            n += 1
    return n
