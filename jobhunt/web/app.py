"""Web UI (FastAPI + Jinja2). Binds to 127.0.0.1; reachable remotely only through a tunnel, behind auth.py's login."""
from __future__ import annotations

import hmac
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from .. import calendar_feed, capture, config, db, facts, health, mail, receipts, deadlines, documents, email_tracker, followup, llm, matcher, notify, pipeline, queue, tasks, writer
from .. import messages, undo
from ..paths import SCREENSHOTS
from . import auth, takeover

HERE = Path(__file__).parent
app = FastAPI(title="jobhunt", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith(auth.OPEN_PATHS):
        return await call_next(request)
    tok = request.cookies.get(auth.COOKIE)
    if auth.valid_session(tok):
        response = await call_next(request)
        if auth.needs_renewal(tok):
            auth.set_cookie(response, request)
        return response
    if path.startswith("/api/"):
        return JSONResponse({"error": "login required"}, status_code=401)
    nxt = path + (("?" + request.url.query) if request.url.query else "")
    return RedirectResponse("/login?next=" + quote(nxt), status_code=303)
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS)), name="screenshots")
app.include_router(takeover.router)
if takeover.available():
    app.mount("/novnc", StaticFiles(directory=str(takeover.NOVNC_DIR)), name="novnc")
templates = Jinja2Templates(directory=str(HERE / "templates"))
BOOT_ID = uuid.uuid4().hex  # changes every server (re)start; the page reloads itself when it sees a new one


def _fmt_dt(s: str | None, fmt: str = "%b %d, %Y %H:%M") -> str:
    if not s:
        return ""
    dt = _parse_dt(s)
    if dt is None:
        return str(s)[:16]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)   # legacy naive values were written as UTC-ish
    dt = dt.astimezone()                        # this machine's zone = the user's zone
    return dt.strftime(fmt)


def _parse_dt(s) -> datetime | None:
    s = str(s).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s)
    except Exception:  # noqa: BLE001
        return None


def _rel(s: str | None) -> str:
    if not s:
        return ""
    try:
        dt = _parse_dt(s)
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = dt - datetime.now(timezone.utc)
        secs = int(delta.total_seconds())
        past = secs < 0
        secs = abs(secs)
        if secs < 3600:
            txt = f"{secs // 60} min"
        elif secs < 86400:
            txt = f"{secs // 3600} h"
        else:
            txt = f"{secs // 86400} d"
        return f"{txt} ago" if past else f"in {txt}"
    except Exception:  # noqa: BLE001
        return ""


def _month_sections(rows: list[dict], *fields: str) -> list[dict]:
    """Split rows into "This month" (open) and "Past months" (collapsed, one block per month, newest first),
    dated by the first of `fields` that is set, in this machine's time zone. Order within a month is kept."""
    now = datetime.now().astimezone()
    current, past, undated = [], {}, []
    for r in rows:
        dt = next((d for d in (_parse_dt(r[f]) for f in fields if r.get(f)) if d), None)
        if dt is None:
            undated.append(r); continue
        dt = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone()
        if (dt.year, dt.month) == (now.year, now.month):
            current.append(r)
        else:
            past.setdefault((dt.year, dt.month), []).append(r)
    months = [{"label": datetime(y, m, 1).strftime("%B %Y"), "rows": past[(y, m)]} for y, m in sorted(past, reverse=True)]
    if undated:
        months.append({"label": "No date", "rows": undated})
    out = []
    if current:
        out.append({"label": "This month", "sub": now.strftime("%B"), "open": True, "count": len(current),
                    "months": [{"label": now.strftime("%B %Y"), "rows": current}]})
    if months:
        out.append({"label": "Past months", "sub": "", "open": not current, "count": sum(len(m["rows"]) for m in months),
                    "months": months})
    return out


templates.env.filters["dt"] = _fmt_dt
templates.env.filters["month_sections"] = _month_sections
templates.env.filters["rel"] = _rel
templates.env.filters["fromjson"] = lambda s: db.loads(s, [])
templates.env.filters["loads"] = lambda s: db.loads(s, [])


def _pill(info: tuple[str, str, str]) -> Markup:
    label, hint, tone = info
    return Markup('<span class="pill {}" title="{}">{}</span>').format(tone, hint, label)


templates.env.globals.update(
    iv_pill=lambda s: Markup('<span class="pill {}">{}</span>').format(*reversed(messages.interview_status(s))),
    as_pill=lambda s: Markup('<span class="pill {}">{}</span>').format(*reversed(messages.assessment_status(s))),
    run_pill=lambda s: Markup('<span class="pill {}">{}</span>').format(*reversed(messages.run_status(s))),
    tones=messages.TONES,
    iv_format=lambda f: messages.INTERVIEW_FORMAT.get(f or "", f or ""),
    app_pill=lambda code: _pill(messages.app_status(code)), job_pill=lambda code: _pill(messages.job_status(code)),
    app_label=lambda code: messages.app_status(code)[0], app_hint=lambda code: messages.app_status(code)[1],
    job_label=lambda code: messages.job_status(code)[0], task_label=messages.task_label,
    event_label=messages.event_label, source_label=lambda s: messages.SOURCE_LABELS.get(s, s))
templates.env.filters["local16"] = lambda s: (deadlines.to_local(s).strftime("%Y-%m-%dT%H:%M") if deadlines.to_local(s) else "")
templates.env.filters["localtz"] = lambda s: (deadlines.tz_label(deadlines.to_local(s)) if deadlines.to_local(s) else "")


def _email_window() -> dict:
    last = email_tracker.last_sync_at()
    return {"days": email_tracker.default_days(), "last": last.isoformat() if last else ""}


def render(request: Request, name: str, **ctx):
    ctx.update({"request": request, "running": tasks.running(), "now_iso": datetime.now(timezone.utc).isoformat(), "msg": request.query_params.get("msg", ""), "boot": BOOT_ID,
                "takeover": takeover.available(), "email_window": _email_window, "min_fit": config.get_int("min_fit_score", 65),
                "min_legit": config.get_int("min_legit_score", 55), "auto_queue": config.get_int("auto_queue_score", 80)})
    return templates.TemplateResponse(request, name, ctx)


def back(url: str, msg: str = "", undo: str = "") -> RedirectResponse:
    if msg:
        url, _, frag = url.partition("#")   # the query must come before any #anchor
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg) + (("&undo=" + quote(undo)) if undo else "") + ("#" + frag if frag else "")
    return RedirectResponse(url, status_code=303)


def _autosave(request: Request) -> bool:
    return request.headers.get("x-autosave") == "1"


def back_here(request: Request, fallback: str, msg: str = "") -> RedirectResponse:
    """Redirect to the page the form was on (Referer), so actions never drag the user to another tab."""
    ref = request.headers.get("referer", "")
    path = fallback
    if ref.startswith(str(request.base_url).rstrip("/")):
        tail = ref[len(str(request.base_url).rstrip("/")):]
        if tail.startswith("/"):
            path = tail.split("?msg=")[0].split("&msg=")[0] or fallback
    return back(path, msg)


@app.on_event("startup")
def _startup():
    db.init_db()
    db.seal_secrets()   # no-op without JOBHUNT_SECRET_KEY (on the PC)
    # Background threads die with the process (dev-mode restarts, closing the window); don't leave their runs "running".
    db.execute("UPDATE runs SET status='failed', finished_at=?, summary=COALESCE(summary, 'interrupted: server restarted') "
               "WHERE status='running'", (db.now_iso(),))
    db.execute("UPDATE applications SET status='queued', last_update_at=? WHERE status='drafting'", (db.now_iso(),))
    for a in db.q("SELECT id FROM applications WHERE status IN ('applying','review')"):
        queue.set_status(a["id"], "needs_attention", "Apply was interrupted (server restarted). Check the site, then mark it submitted or retry.", source="system")
    receipts.backfill()
    notify.start_scheduler()
    health.start_autosync()


# ---- login -------------------------------------------------------------------

def _safe_next(nxt: str) -> str:
    return nxt if nxt.startswith("/") and not nxt.startswith("//") and not nxt.startswith("/login") else "/"


def _logged_in(request: Request, nxt: str) -> RedirectResponse:
    r = RedirectResponse(_safe_next(nxt), status_code=303)
    auth.set_cookie(r, request)
    return r


def _login_page(request: Request, nxt: str = "/", error: str = "", status: int = 200):
    mode = "login" if auth.password_set() else ("setup" if auth.is_local(request) else "closed")
    return templates.TemplateResponse(request, "login.html", {"request": request, "mode": mode, "next": _safe_next(nxt),
                                                              "error": error, "boot": BOOT_ID}, status_code=status)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/"):
    return _login_page(request, next)


@app.post("/login")
def login(request: Request, password: str = Form(""), confirm: str = Form(""), next: str = Form("/")):
    if not auth.password_set():
        if not auth.is_local(request):
            return _login_page(request, next, status=403)
        if len(password) < 10:
            return _login_page(request, next, "Use at least 10 characters.")
        if password != confirm:
            return _login_page(request, next, "Passwords don't match.")
        auth.set_password(password)
        return _logged_in(request, next)
    ip = auth.client_ip(request)
    if auth.locked_out(ip):
        return _login_page(request, next, "Too many wrong tries. Wait 15 minutes.", status=429)
    if not auth.check_password(password):
        auth.record_fail(ip)
        return _login_page(request, next, "Wrong password.", status=401)
    auth.clear_fails(ip)
    return _logged_in(request, next)


@app.post("/logout")
def logout():
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie(auth.COOKIE)
    return r


@app.post("/password")
def change_password(current: str = Form(""), new: str = Form(""), confirm: str = Form("")):
    if not auth.check_password(current):
        return back("/settings", "current password is wrong")
    if len(new) < 10 or new != confirm:
        return back("/settings", "new password must be 10+ characters and match")
    auth.set_password(new)   # invalidates every existing session, including this one
    return back("/login", "password changed - log in again")


@app.get("/takeover", response_class=HTMLResponse)
def takeover_page(request: Request):
    return takeover.page(request, render)


# ---- dashboard ------------------------------------------------------------

def _countdown(at: datetime | None, now: datetime) -> tuple[str, str, str]:
    """(big, sub, tone) for a deadline/start time, written for someone who forgets things:
    'Overdue' / 'Today' / 'Tomorrow' / 'Thu' / 'Nov 12', then the clock time and how far away it is."""
    if at is None:
        return "", "", "later"
    local = at.astimezone()
    today = datetime.now().astimezone().date()
    secs = (at - now).total_seconds()
    clock = local.strftime("%I:%M %p").lstrip("0")
    if secs < 0:
        return "Overdue", f"was {local.strftime('%a %b %d')} {clock}", "bad"
    days = (local.date() - today).days
    if days == 0:
        big = "Today"
    elif days == 1:
        big = "Tomorrow"
    elif days < 7:
        big = local.strftime("%A")
    else:
        big = local.strftime("%b %d")
    tone = "urgent" if secs < 24 * 3600 else "soon" if secs < 72 * 3600 else "later"
    return big, f"{clock} · {_rel(at.isoformat())}", tone


def _sender(email_id) -> str:
    return _email_bits(email_id)["domain"]


def _email_bits(email_id) -> dict:
    """Sender domain and whether the mail was found in the spam folder."""
    if not email_id:
        return {"domain": "", "spam": False}
    r = db.q1("SELECT from_addr, folder FROM emails WHERE id=?", (email_id,)) or {}
    m = re.search(r"@([\w.-]+)", r.get("from_addr") or "")
    folder = (r.get("folder") or "").lower()
    return {"domain": m.group(1).lower() if m else "", "spam": bool(folder) and folder != "inbox" and ("spam" in folder or "junk" in folder)}


def do_by(due: datetime | None, now: datetime) -> datetime | None:
    """The date to actually finish a test: N days before the deadline (Settings), never in the past when the deadline
    is still ahead. Links sometimes die early and a buffer absorbs a bad day."""
    if due is None:
        return None
    buf = timedelta(days=config.get_int("assessment_buffer_days", 2))
    target = due - buf
    if target < now < due:
        target = now.replace(hour=23, minute=59, second=0, microsecond=0)   # today, end of day
        if target > due:
            target = due
    return target


def due_items() -> list[dict]:
    """Every open test and interview, soonest first, each saying plainly whose it is and where it came from,
    so a HireVue/HackerRank email never gets mistaken for spam from some job site."""
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for x in db.q("SELECT * FROM assessments WHERE status='pending'"):
        at = _aware(x.get("due_at"))
        target = do_by(at, now)
        big, sub_, tone = _countdown(target, now)
        flags = []
        if at is None:
            big, sub_, tone = "No deadline", "the email gave none — ask the recruiter how long you have", "urgent"
            flags.append("No deadline stated. Treat it as this week; invites often expire in 5–7 days.")
        else:
            real = at.astimezone()
            if target != at:
                sub_ += f" · real deadline {real.strftime('%a %b %d')} {real.strftime('%I:%M %p').lstrip('0')}"
            if x.get("due_source") == "assumed":
                flags.append("Deadline guessed from the day it arrived. Check the email.")
            if at > now and (at - now).days >= 1:
                flags.append("Test links sometimes die before the stated date. Don't leave it to the last day.")
            if at < now:
                big = "Overdue"
                flags.insert(0, "Past the deadline, but try the link anyway; many stay open for days. "
                                "If it's closed, reply to the recruiter and ask for a new one.")
        bits = _email_bits(x.get("email_id"))
        dom = bits["domain"]
        via = ""
        if x.get("platform") or dom:
            via = ("On " + x["platform"] + ". " if x.get("platform") else "") + \
                  (f"The email came from {dom}" if dom else "") + \
                  (f" — it is {x['company']}'s test, not a job site." if dom and x.get("company") else "")
        if bits["spam"]:
            flags.insert(0, "Found in your Spam folder. The link still works; you may not have seen it.")
        out.append({"kind": "Test / assessment" + (" · was in spam" if bits["spam"] else ""), "company": x.get("company") or "", "what": x.get("title") or "Assessment",
                    "via": via, "detail": (f"About {x['est_minutes']} min. " if x.get("est_minutes") else "") + ("Not opened yet." if not x.get("opened_at") else ""),
                    "flags": flags, "spam": bits["spam"],
                    "big": big, "sub": sub_, "tone": tone, "sort": target or (now + timedelta(days=365)),
                    "href": f"/assessments/{x['id']}/open" if x.get("link") else "/upcoming#assessments", "open_new": bool(x.get("link")),
                    "action": "Open test" if x.get("link") else "Details",
                    "done_url": f"/assessments/{x['id']}/status", "done_value": "completed", "done_label": "Done"})
    for x in db.q("SELECT * FROM interviews WHERE status IN ('needs_scheduling','scheduled')"):
        at = _aware(x.get("starts_at"))
        big, sub_, tone = _countdown(at, now)
        if at is None:
            big, sub_, tone = "Pick a time", f"asked {_rel(x.get('received_at'))}" if x.get("received_at") else "", "urgent"
        elif tone == "bad":
            big, sub_ = "Happened", sub_.replace("was", "was") + " · mark it done or missed"
        dom = _sender(x.get("email_id"))
        fmt = messages.INTERVIEW_FORMAT.get(x.get("format") or "", "")
        what = (x.get("stage") or "Interview") + (f" ({fmt.lower()})" if fmt else "")
        out.append({"kind": "Interview" if at is not None else "Interview — they're waiting on you", "company": x.get("company") or "", "what": what,
                    "prep": f"/interviews/{x['id']}/prep", "prep_ready": bool(x.get("prep_json")),
                    "via": (f"Email from {dom}. " if dom else "") + (f"With {x['interviewer']}. " if x.get("interviewer") else "") + (x.get("location") or ""),
                    "detail": (x.get("title") or "") + (f" · ~{x['duration_minutes']} min" if x.get("duration_minutes") else ""),
                    "big": big, "sub": sub_, "tone": tone, "sort": at or now,
                    "href": x.get("link") or "/upcoming#interviews", "open_new": bool(x.get("link")),
                    "action": ("Schedule" if at is None else "Join") if x.get("link") else "Details",
                    "done_url": f"/interviews/{x['id']}/status", "done_value": "done", "done_label": "Done"})
    out.sort(key=lambda d: (d["tone"] != "bad" and d["big"] != "Pick a time", d["sort"]))
    return out


def _due_action(d: dict, tone: str) -> dict:
    return {"why": d["kind"].split(" · ")[0], "title": f"{d['company']} — {d['what']}".strip(" —"),
            "when": f"{d['big']} · {d['sub']}".strip(" ·"), "href": d["href"], "open_new": d["open_new"],
            "label": d["action"], "tone": tone}


def next_action(due: list[dict], needs: list[dict], setup_min: int, match_count: int) -> dict:
    """The one thing to do next, so Today has a single primary button above the fold.
    Order: a test or interview that is close, then anything urgent waiting on you, then setup, then matches."""
    for d in due:
        if d["big"] != "Happened" and (d["tone"] in ("urgent", "bad") or d["big"] in ("No deadline", "Pick a time")):
            return _due_action(d, "urgent")
    for i in needs:
        if i.get("urgent"):
            return {"why": i["kind"], "title": i["title"], "when": i.get("detail", ""), "href": i["href"],
                    "post": i.get("post"), "label": i["action"], "tone": "urgent"}
    for d in due:
        if d["tone"] == "soon":
            return _due_action(d, "soon")
    if setup_min:
        return {"why": "Setup", "title": "Finish setting up so nothing slips", "when": f"about {setup_min} min left",
                "href": "/setup", "label": f"Pick up setup · ~{setup_min} min", "tone": "later"}
    if match_count:
        return {"why": "New matches", "title": f"{match_count} jobs worth a look", "when": "scored against your resume",
                "href": "/jobs?status=match", "label": "Look at matches", "tone": "later"}
    return {"why": "All caught up", "title": "Nothing urgent", "when": "find new jobs when you're ready",
            "post": "/run/fetch_and_score", "href": "/jobs", "label": "Find & score jobs", "tone": "later"}


@app.get("/", response_class=HTMLResponse)
def today(request: Request):
    if setup_needed():
        return RedirectResponse("/setup", status_code=302)
    email_tracker.mark_missed()
    ready = {"resume": bool(documents.active_resume()), "key": bool(config.get("anthropic_api_key")),
             "titles": bool(config.get_lines("search_titles")), "name": bool(config.get("cand_first_name") and config.get("cand_email")),
             "email": bool(config.get("email_user") and config.get("email_pass"))}
    ready["all"] = all(ready.values())
    items = needs_you_items()
    needs = [i for i in items if not i["kind"].startswith(("Assessment", "Interview", "Pick an interview"))]
    top = db.q("SELECT * FROM jobs WHERE status='new' AND fit_score >= ? ORDER BY fit_score DESC LIMIT 5",
               (config.get_int("min_fit_score", 65),))
    match_count = (db.q1("SELECT COUNT(*) n FROM jobs WHERE status IN ('new','queued') AND fit_score >= ?",
                         (config.get_int("min_fit_score", 65),)) or {}).get("n", 0)
    app_counts = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM applications GROUP BY status")}
    applied_n = sum(app_counts.get(s, 0) for s in ("submitted", "screening", "assessment", "interview", "offer"))
    queue_n = sum(app_counts.get(s, 0) for s in ("queued", "drafting", "ready", "review", "needs_attention"))
    setup_n, setup_min = setup_left()
    due = due_items()
    return render(request, "today.html", ready=ready, setup_n=setup_n, setup_min=setup_min, due=due,
                  nxt=next_action(due, needs, setup_min, match_count), needs=needs, needs_total=len(items), top=top, stamps=health.stamps(),
                  match_count=match_count, applied_n=applied_n, queue_n=queue_n, running=tasks.running(),
                  last_run=db.q1("SELECT * FROM runs ORDER BY id DESC LIMIT 1"))


# ---- setup wizard -----------------------------------------------------------

def setup_state() -> dict:
    return {"name": bool(config.get("cand_first_name") and config.get("cand_email")),
            "key": bool(config.get("anthropic_api_key")), "resume": bool(documents.active_resume()),
            "titles": bool(config.get_lines("search_titles")),
            "email": bool(config.get("email_user") and config.get("email_pass")),
            "first": bool(db.q1("SELECT 1 FROM applications LIMIT 1") or db.q1("SELECT 1 FROM jobs WHERE source='capture' LIMIT 1"))}


# Order = value first: the AI and the inbox catch tests on day one, one tracked job shows it working,
# and the full profile (only needed for auto-apply forms) comes last.
SETUP_STEPS = [
    {"key": "ai", "state": "key", "title": "AI key", "minutes": 3, "why": "nothing gets read, scored or written without it",
     "needs": "An Anthropic API key", "needs_link": "https://platform.claude.com/settings/keys", "needs_link_text": "make one",
     "needs_note": "Needs a card on file with Anthropic. A typical day costs well under a dollar."},
    {"key": "inbox", "state": "email", "title": "Inbox", "minutes": 3, "why": "catches tests and interviews so you don't miss them",
     "needs": "A Gmail app password", "needs_link": "https://myaccount.google.com/apppasswords", "needs_link_text": "make one",
     "needs_note": "Gmail only allows it with 2-step verification on. Other providers: your IMAP login."},
    {"key": "first", "state": "first", "title": "One tracked job", "minutes": 1, "why": "shows it working on something real",
     "needs": "One job link or recruiter message", "needs_link": "", "needs_link_text": "",
     "needs_note": "Something you applied to or want to. Copy the link now."},
    {"key": "resume", "state": "resume", "title": "Resume", "minutes": 1, "why": "fit scores and letters come from it",
     "needs": "Your resume (PDF or Word)", "needs_link": "", "needs_link_text": "", "needs_note": "Or paste the text."},
    {"key": "titles", "state": "titles", "title": "Target job titles", "minutes": 1, "why": "tells the search what to look for",
     "needs": "", "needs_link": "", "needs_link_text": "", "needs_note": ""},
    {"key": "you", "state": "name", "title": "Your name and contact", "minutes": 1, "why": "application forms need it",
     "needs": "", "needs_link": "", "needs_link_text": "", "needs_note": ""},
]
SETUP_INDEX = {s["key"]: i + 1 for i, s in enumerate(SETUP_STEPS)}


def setup_steps() -> list[dict]:
    st = setup_state()
    return [dict(s, done=st[s["state"]]) for s in SETUP_STEPS]


def setup_needed() -> bool:
    """First run: nothing set up at all and the user has not said 'don't show again'."""
    st = setup_state()
    return not (st["key"] or st["resume"] or st["titles"]) and not config.get("setup_dismissed")


def setup_left() -> tuple[int, int]:
    """(steps left, minutes left)."""
    left = [s for s in setup_steps() if not s["done"]]
    return len(left), sum(s["minutes"] for s in left)


def _next_step(key: str) -> str:
    return f"/setup?step={SETUP_INDEX[key] + 1}"


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, step: int = 0):
    steps = setup_steps()
    intro = False
    if not step:
        if not any(s["done"] for s in steps):
            intro = True       # first visit: say what you need and how long, before asking for anything
            step = 1
        else:
            step = next((i + 1 for i, s in enumerate(steps) if not s["done"]), len(steps) + 1)
    step = max(1, min(step, len(steps) + 1))
    cur = steps[step - 1] if step <= len(steps) else None
    v = {k: config.get(k) for k in ("cand_first_name", "cand_last_name", "cand_email", "cand_phone", "cand_location",
                                    "search_titles", "search_locations", "email_user", "email_host")}
    first = db.q1("SELECT company, title, NULL AS fit_score, 'application' AS kind, id FROM applications ORDER BY id DESC LIMIT 1")
    cap = db.q1("SELECT company, title, fit_score, 'job' AS kind, id FROM jobs WHERE source='capture' ORDER BY id DESC LIMIT 1")
    v.update({"key_set": bool(config.get("anthropic_api_key")), "resume": documents.active_resume(),
              "email_set": bool(config.get("email_pass")), "remote_only": config.get_bool("remote_only"),
              "since_days": config.get_int("email_since_days", 60), "first": cap or first})
    _n, left_min = setup_left()
    return render(request, "setup.html", step=step, steps=steps, cur=cur, v=v, intro=intro, state=setup_state(),
                  all_done=all(s["done"] for s in steps), dismissed=bool(config.get("setup_dismissed")),
                  total_min=sum(s["minutes"] for s in steps), left_min=left_min, inbox_running=bool(tasks.is_running("email")))


@app.post("/setup/ai")
def setup_ai(anthropic_api_key: str = Form(""), action: str = Form("")):
    if anthropic_api_key.strip():
        db.set_setting("anthropic_api_key", anthropic_api_key.strip())
    if action == "test" or anthropic_api_key.strip():
        ok, msg = llm.check_key()
        if not ok or action == "test":
            return back("/setup?step=1", msg)
    return back(_next_step("ai"))


@app.post("/setup/inbox")
def setup_inbox(email_user: str = Form(""), email_pass: str = Form(""), email_host: str = Form(""), action: str = Form("")):
    db.set_setting("email_user", email_user.strip())
    if email_host.strip():
        db.set_setting("email_host", email_host.strip())
    if email_pass.strip():
        db.set_setting("email_pass", email_pass.strip())
    here = f"/setup?step={SETUP_INDEX['inbox']}"
    if action == "test" or (email_user.strip() and email_pass.strip()):
        ok, msg = email_tracker.test_connection()
        if not ok or action == "test":
            return back(here, msg)
        # Value right away: start reading while they do the rest of setup.
        if config.get("anthropic_api_key") and not tasks.is_running("email"):
            tasks.start("email", tasks.email_task)
            return back(_next_step("inbox"), "Connected. Reading your inbox in the background; tests and interviews will be on Today.")
    return back(_next_step("inbox"))


@app.post("/setup/first")
def setup_first(url: str = Form(""), text: str = Form("")):
    here = f"/setup?step={SETUP_INDEX['first']}"
    if not (url.strip() or text.strip()):
        return back(here, "Paste a link or a message first, or skip this step.")
    try:
        res = capture.capture(text=text, url=url)
    except Exception as e:  # noqa: BLE001
        return back(here, "Couldn't read that. " + messages.friendly_error(e))
    return back(here, res["message"])


@app.post("/setup/resume")
async def setup_resume(file: UploadFile | None = File(None), content: str = Form("")):
    try:
        if file is not None and file.filename:
            documents.save_upload("resume", "", file.filename, await file.read())
        elif content.strip():
            documents.add_document("resume", f"Resume {datetime.now():%Y-%m-%d}", content.strip())
    except Exception as e:  # noqa: BLE001
        return back(f"/setup?step={SETUP_INDEX['resume']}", "Couldn't read that file. " + messages.friendly_error(e))
    return back(_next_step("resume"))


@app.post("/setup/titles")
def setup_titles(search_titles: str = Form(""), search_locations: str = Form(""), remote_only: str = Form(""), action: str = Form("")):
    here = f"/setup?step={SETUP_INDEX['titles']}"
    db.set_setting("search_titles", search_titles.strip())
    db.set_setting("search_locations", search_locations.strip())
    db.set_setting("remote_only", "1" if remote_only else "0")
    if action == "suggest":
        try:
            p = matcher.suggest_search_profile()
        except Exception as e:  # noqa: BLE001
            return back(here, "Couldn't suggest titles. " + messages.friendly_error(e))
        db.set_setting("search_titles", "\n".join(p.titles))
        if not config.get("search_keywords").strip():
            db.set_setting("search_keywords", "\n".join(p.keywords))
        return back(here, f"Suggested {len(p.titles)} titles from your resume. Edit them, then continue.")
    return back(_next_step("titles"))


@app.post("/setup/you")
def setup_you(cand_first_name: str = Form(""), cand_last_name: str = Form(""), cand_email: str = Form(""),
              cand_phone: str = Form(""), cand_location: str = Form("")):
    for k, val in (("cand_first_name", cand_first_name), ("cand_last_name", cand_last_name), ("cand_email", cand_email),
                   ("cand_phone", cand_phone), ("cand_location", cand_location)):
        db.set_setting(k, val.strip())
    return back(_next_step("you"))


@app.post("/setup/dismiss")
def setup_dismiss():
    db.set_setting("setup_dismissed", "1")
    return back("/", "Okay. Setup stays under Settings if you need it.")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    counts = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
    app_counts = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM applications GROUP BY status")}
    upcoming = db.q("SELECT a.*, p.title AS app_title FROM assessments a LEFT JOIN applications p ON p.id=a.application_id "
                    "WHERE a.status='pending' ORDER BY COALESCE(a.due_at,'9999') LIMIT 8")
    interviews = db.q("SELECT * FROM interviews WHERE status IN ('needs_scheduling','scheduled') ORDER BY COALESCE(starts_at,'0') LIMIT 8")
    top = db.q("SELECT * FROM jobs WHERE status IN ('new','queued') AND fit_score IS NOT NULL ORDER BY fit_score DESC LIMIT 10")
    match_count = (db.q1("SELECT COUNT(*) n FROM jobs WHERE status IN ('new','queued') AND fit_score >= ?",
                         (config.get_int("min_fit_score", 65),)) or {}).get("n", 0)
    runs = db.q("SELECT * FROM runs ORDER BY id DESC LIMIT 6")
    attention = db.q("SELECT * FROM applications WHERE status='needs_attention' ORDER BY last_update_at DESC LIMIT 8")
    ready = {"resume": bool(documents.active_resume()), "key": bool(config.get("anthropic_api_key")),
             "titles": bool(config.get_lines("search_titles")), "name": bool(config.get("cand_first_name") and config.get("cand_email")),
             "email": bool(config.get("email_user") and config.get("email_pass"))}
    return render(request, "dashboard.html", interviews=interviews, counts=counts, app_counts=app_counts, upcoming=upcoming, top=top,
                  runs=runs, attention=attention, ready=ready, match_count=match_count, spend=llm.spend_summary())


@app.post("/credits")
def credits_set(request: Request, balance: str = Form("")):
    """User types the balance the Anthropic console shows (purchased + promotional); we count spend from now."""
    try:
        amount = float(balance.replace("$", "").replace(",", "").strip())
    except ValueError:
        return back("/", "enter a dollar amount, e.g. 187.50")
    db.set_setting("credits_start_usd", f"{amount:.2f}")
    db.set_setting("credits_as_of", db.now_iso())
    return back("/", f"balance set to ${amount:.2f}; spend is counted from now")


@app.post("/run/{kind}")
def run_kind(request: Request, kind: str, days: int = Form(0)):
    if kind == "email" and days > 0:
        rid = tasks.start("email", lambda run_id: tasks.email_task(run_id, days))
        return back_here(request, "/", f"Checking email from the last {days} day{'s' if days != 1 else ''}." if rid
                         else "Already checking your email")
    fn = {"fetch": tasks.fetch_task, "score": tasks.score_task, "fetch_and_score": tasks.fetch_and_score_task,
          "email": tasks.email_task, "draft_all": tasks.draft_all_task, "reclassify": tasks.reclassify_task}.get(kind)
    if not fn:
        return back("/", "unknown task")
    rid = tasks.start(kind, fn)
    return back_here(request, "/", f"Started: {messages.task_label(kind)}. Progress shows in the top right." if rid else f"{messages.task_label(kind)} is already running")


@app.get("/runs", response_class=HTMLResponse)
def runs(request: Request):
    return render(request, "runs.html", runs=db.q("SELECT * FROM runs ORDER BY id DESC LIMIT 40"))


@app.post("/runs/{run_id}/dismiss")
def run_dismiss(request: Request, run_id: int):
    db.update("runs", run_id, {"dismissed": 1})
    return back_here(request, "/", "Hidden. It's still in the activity log.")


@app.post("/health/inbox/snooze")
def health_inbox_snooze(request: Request):
    db.set_setting("health_inbox_snooze_until", (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat())
    return back_here(request, "/", "OK, not asking again for 12 hours.")


@app.post("/health/webhook/clear")
def health_webhook_clear(request: Request):
    db.set_setting("notify_webhook_error", "")
    return back_here(request, "/", "Cleared.")


@app.get("/runs/{run_id}")
def run_detail(run_id: int):
    return JSONResponse(db.q1("SELECT * FROM runs WHERE id=?", (run_id,)) or {})


# ---- needs you ---------------------------------------------------------------

def needs_you_items() -> list[dict]:
    """Everything waiting on the user, most urgent first: {kind, title, detail, href, action, urgent}."""
    items: list[dict] = health.problems()
    last_note = lambda app_id: ((db.q1("SELECT detail FROM application_events WHERE application_id=? "  # noqa: E731
                                       "ORDER BY happened_at DESC, id DESC LIMIT 1", (app_id,)) or {}).get("detail") or "")
    for a in db.q("SELECT id, company, title, status FROM applications WHERE status IN ('review','needs_attention','failed') "
                  "ORDER BY CASE status WHEN 'review' THEN 0 ELSE 1 END, last_update_at DESC"):
        if a["status"] == "review":
            items.append({"kind": "Check before sending", "title": f"{a['title']} @ {a['company']}",
                          "detail": "Auto-apply filled the form and is waiting for you to check it and press Send.",
                          "href": f"/applications/{a['id']}", "action": "Check & send", "urgent": True})
        else:
            items.append({"kind": "Auto-apply got stuck", "title": f"{a['title']} @ {a['company']}",
                          "detail": last_note(a["id"]) or messages.app_status(a["status"])[1],
                          "href": f"/applications/{a['id']}", "action": "Open", "urgent": False})
    now = datetime.now(timezone.utc)
    for x in db.q("SELECT * FROM interviews WHERE status IN ('needs_scheduling','scheduled') ORDER BY COALESCE(starts_at,'0')"):
        at = _aware(x.get("starts_at"))
        hours = (at - now).total_seconds() / 3600 if at else None
        what = f"{x.get('stage') or 'Interview'} · {x.get('company') or ''}".strip(" ·")
        if at is None:
            items.append({"kind": "Pick an interview time", "title": what,
                          "detail": (f"{x['interviewer']} asked" if x.get("interviewer") else "They asked") + " for your availability. Reply or use their scheduling link, then set the time on Upcoming.",
                          "href": x.get("link") or "/upcoming#interviews", "action": "Schedule" if x.get("link") else "Open", "urgent": True})
        elif hours < -2:
            items.append({"kind": "Interview happened", "title": what,
                          "detail": f"It was {_rel(x['starts_at'])}. Mark it done or missed on Upcoming.",
                          "href": "/upcoming#interviews", "action": "Open", "urgent": False})
        elif hours <= 48:
            items.append({"kind": "Interview " + _rel(x["starts_at"]), "title": what,
                          "detail": (f"{messages.INTERVIEW_FORMAT.get(x.get('format') or '', 'Interview')} " if x.get("format") else "")
                                    + (f"with {x['interviewer']}. " if x.get("interviewer") else "")
                                    + (f"~{x['duration_minutes']} min. " if x.get("duration_minutes") else "")
                                    + (x.get("location") or ""),
                          "href": x.get("link") or "/upcoming#interviews", "action": "Join" if x.get("link") else "Open",
                          "urgent": hours < 24})
    for x in db.q("SELECT * FROM assessments WHERE status='pending' ORDER BY COALESCE(due_at, '9999')"):
        due = _parse_dt(x["due_at"]) if x.get("due_at") else None
        if due is not None and due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        hours = (due - now).total_seconds() / 3600 if due else None
        if hours is not None and hours > 72:
            continue
        when = ("overdue" if hours is not None and hours < 0 else f"due {_rel(x['due_at'])}" if hours is not None else "no deadline given")
        items.append({"kind": "Assessment " + when, "title": f"{x.get('platform') or ''} {x.get('title') or ''} · {x.get('company') or ''}".strip(" ·"),
                      "detail": (f"About {x['est_minutes']} min. " if x.get("est_minutes") else "") + "Do it, then mark it done on Upcoming.",
                      "href": f"/assessments/{x['id']}/open" if x.get("link") else "/upcoming#assessments", "action": "Open test" if x.get("link") else "Open",
                      "urgent": hours is not None and hours < 24})
    for a in db.q("SELECT id, company, title FROM applications WHERE status='ready' AND cover_letter IS NOT NULL "
                  "AND cover_letter_approved=0 ORDER BY last_update_at DESC"):
        items.append({"kind": "Letter ready to read", "title": f"{a['title']} @ {a['company']}",
                      "detail": "Read it, edit until it sounds like you, then approve and apply.",
                      "href": f"/applications/{a['id']}", "action": "Read letter", "urgent": False})
    quiet = followup.stale()
    for a in quiet[:3]:
        items.append({"kind": "Follow up?", "title": f"{a['title']} @ {a['company']}",
                      "detail": f"Applied, then nothing for {a['quiet_days']} days. A short note often gets an answer; or let it go.",
                      "href": f"/applications/{a['id']}#followup", "action": "Draft a note", "urgent": False})
    if len(quiet) > 3:
        items.append({"kind": "Follow up?", "title": f"{len(quiet) - 3} more have gone quiet",
                      "detail": "Oldest first under Pipeline › Quiet. Do one a day; it adds up.",
                      "href": "/applications?status=quiet", "action": "See them", "urgent": False})
    items.sort(key=lambda i: not i["urgent"])
    return items


def needs_you_count() -> int:
    return len(needs_you_items())


@app.get("/todo")
def todo():
    return RedirectResponse("/", status_code=302)


@app.get("/api/status")
def api_status():
    """Polled by the page footer script: what is running, and the last run of each kind."""
    running = tasks.running()
    recent = db.q("SELECT id, kind, status, started_at, finished_at, summary, substr(log, -600) AS log_tail "
                  "FROM runs ORDER BY id DESC LIMIT 8")
    live = []
    if running:
        ids = ",".join(str(int(i)) for i in running.values())
        live = db.q(f"SELECT id, kind, started_at, substr(log, -400) AS tail FROM runs WHERE id IN ({ids}) ORDER BY id")
    for r in live + recent:
        r["label"] = messages.task_label(r["kind"])
    for r in recent:
        if r["status"] == "failed" and r.get("summary"):
            r["summary"] = messages.friendly_error(r["summary"].removeprefix("failed: "))
    return JSONResponse({"running": running, "live": live, "recent": recent, "now": db.now_iso(), "boot": BOOT_ID,
                         "needs_you": needs_you_count()})


# ---- jobs ------------------------------------------------------------------

JOB_SORTS = {"fit": ("Best fit", "COALESCE(fit_score,-1) DESC, legit_score DESC, id DESC"),
             "posted": ("Newest posted", "COALESCE(posted_at, fetched_at) DESC, id DESC"),
             "found": ("Newest found", "fetched_at DESC, id DESC"),
             "legit": ("Most legit", "COALESCE(legit_score,-1) DESC, COALESCE(fit_score,-1) DESC"),
             "company": ("Company A-Z", "lower(company), lower(title)")}


@app.get("/jobs", response_class=HTMLResponse)
def jobs(request: Request, status: str = "match", min_fit: int = 0, qtext: str = "", sort: str = "fit", min_legit: int = 0,
         remote: int = 0, days: int = 0):
    where, params = [], []
    if status == "match":
        where.append("status IN ('new','queued') AND fit_score >= ?"); params.append(config.get_int("min_fit_score", 65))
    elif status == "unscored":
        where.append("status='new' AND fit_score IS NULL")
    elif status != "all":
        where.append("status=?"); params.append(status)
    if min_fit:
        where.append("fit_score >= ?"); params.append(min_fit)
    if qtext:
        where.append("(lower(title) LIKE ? OR lower(company) LIKE ? OR lower(location) LIKE ?)"); params += [f"%{qtext.lower()}%"] * 3
    if min_legit:
        where.append("legit_score >= ?"); params.append(min_legit)
    if remote:
        where.append("remote=1")
    if days:
        where.append("COALESCE(posted_at, fetched_at) >= ?"); params.append((datetime.now(timezone.utc) - timedelta(days=days)).isoformat()[:10])
    sort = sort if sort in JOB_SORTS else "fit"
    sql = "SELECT * FROM jobs" + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {JOB_SORTS[sort][1]} LIMIT 300"
    rows = db.q(sql, tuple(params))
    counts = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
    scored = (db.q1("SELECT COUNT(*) n FROM jobs WHERE fit_score IS NOT NULL") or {}).get("n", 0)
    unscored = (db.q1("SELECT COUNT(*) n FROM jobs WHERE status='new' AND fit_score IS NULL") or {}).get("n", 0)
    return render(request, "jobs.html", jobs=rows, status=status, min_fit=min_fit, qtext=qtext, counts=counts, sort=sort, sorts=JOB_SORTS,
                  min_legit=min_legit, remote=remote, days=days,
                  scored=scored, unscored=unscored, min_fit_setting=config.get_int("min_fit_score", 65))


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int):
    job = db.q1("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        return back("/jobs", "job not found")
    appl = db.q1("SELECT * FROM applications WHERE job_id=?", (job_id,))
    return render(request, "job.html", job=job, appl=appl)


@app.post("/jobs/{job_id}/queue")
def job_queue(job_id: int, draft: int = Form(0)):
    app_id = queue.enqueue(job_id)
    if draft:
        tasks.start(f"draft-{app_id}", tasks.draft_task(app_id))
        return back(f"/applications/{app_id}", "Added to your queue. Writing the letter now.")
    return back(f"/applications/{app_id}", "Added to your queue")


@app.post("/jobs/{job_id}/skip")
def job_skip(job_id: int, next: str = Form("/jobs")):
    queue.skip_job(job_id)
    return back(next, "Skipped")


@app.post("/jobs/{job_id}/rescore")
def job_rescore(job_id: int):
    job = db.q1("SELECT * FROM jobs WHERE id=?", (job_id,))
    try:
        fs = matcher.score_job(job)
    except Exception as e:  # noqa: BLE001
        return back(f"/jobs/{job_id}", "Couldn't score this job. " + messages.friendly_error(e))
    db.update("jobs", job_id, {"fit_score": fs.fit_score, "fit_summary": fs.summary, "fit_reasons": db.dumps(fs.matching_points),
                               "fit_missing": db.dumps(fs.missing), "status": "new" if job["status"] in ("low_fit",) else job["status"]})
    return back(f"/jobs/{job_id}", f"scored {fs.fit_score}")


@app.post("/jobs/bulk")
def jobs_bulk(action: str = Form(...), ids: list[int] = Form([])):
    n = 0
    for jid in ids:
        if action == "queue":
            queue.enqueue(jid); n += 1
        elif action == "skip":
            queue.skip_job(jid); n += 1
    if action == "queue" and n:
        tasks.start("draft_all", tasks.draft_all_task)
        return back("/queue", f"Added {n} to your queue. Writing their letters now.")
    return back("/jobs", f"Skipped {n} job{'s' if n != 1 else ''}" if action == "skip" else "Nothing selected")


# ---- queue / applications ----------------------------------------------------

@app.get("/queue", response_class=HTMLResponse)
def queue_page(request: Request):
    return render(request, "queue.html", apps=queue.queued())


@app.post("/queue/remove")
def queue_remove(ids: list[int] = Form([])):
    n = 0
    for app_id in ids:
        a = db.q1("SELECT status FROM applications WHERE id=?", (app_id,))
        if a and a["status"] in ("queued", "drafting", "ready", "needs_attention", "failed"):
            queue.remove(app_id); n += 1
    return back("/queue", f"Removed {n} from your queue" if n else "Nothing selected")


APP_SORTS = {"updated": ("Latest activity", "a.last_update_at DESC"),
             "applied": ("Applied date", "COALESCE(a.applied_at, a.created_at) DESC"),
             "deadline": ("Next deadline", "CASE WHEN next_at IS NULL THEN 1 ELSE 0 END, next_at"),
             "fit": ("Best fit", "COALESCE(j.fit_score,-1) DESC"),
             "posted": ("Posted date", "COALESCE(j.posted_at,'') DESC"),
             "company": ("Company A-Z", "lower(a.company), lower(a.title)")}


@app.get("/applications", response_class=HTMLResponse)
def applications(request: Request, status: str = "applied", sort: str = "updated", qtext: str = ""):
    # next_at: the next open test deadline or interview; that is what "deadline" sorts by.
    sql = ("SELECT a.*, j.url, j.fit_score, j.fit_summary, j.fit_reasons, j.fit_missing, j.posted_at, "
           "(SELECT MIN(x) FROM (SELECT due_at x FROM assessments WHERE application_id=a.id AND status='pending' AND due_at IS NOT NULL "
           " UNION ALL SELECT starts_at FROM interviews WHERE application_id=a.id AND status='scheduled' AND starts_at IS NOT NULL)) AS next_at "
           "FROM applications a LEFT JOIN jobs j ON j.id=a.job_id ")
    params: tuple = ()
    if status == "applied":
        sql += "WHERE a.status IN ('submitted','screening','assessment','interview','offer','rejected') "
    elif status == "active":
        sql += "WHERE a.status IN ('submitted','screening','assessment','interview','offer') "
    elif status == "quiet":
        ids = [a["id"] for a in followup.stale(limit=500)] or [0]
        sql += f"WHERE a.id IN ({','.join('?' * len(ids))}) "; params = tuple(ids)
    elif status != "all":
        sql += "WHERE a.status=? "; params = (status,)
    else:
        sql += "WHERE 1=1 "
    if qtext:
        sql += "AND (lower(a.company) LIKE ? OR lower(a.title) LIKE ? OR lower(COALESCE(a.notes,'')) LIKE ?) "
        params = tuple(params) + (f"%{qtext.lower()}%",) * 3
    sort = sort if sort in APP_SORTS else "updated"
    sql += "ORDER BY " + APP_SORTS[sort][1]
    rows = db.q(sql, params)
    if status == "quiet" and sort == "updated":
        order = {a["id"]: i for i, a in enumerate(followup.stale(limit=500))}
        rows.sort(key=lambda r: order.get(r["id"], 999))
    counts = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM applications GROUP BY status")}
    applied_n = sum(counts.get(s, 0) for s in ("submitted", "screening", "assessment", "interview", "offer", "rejected"))
    return render(request, "applications.html", apps=rows, status=status, counts=counts, applied_n=applied_n, sort=sort, sorts=APP_SORTS, qtext=qtext,
                  quiet_n=len(followup.stale(limit=500)))


@app.post("/applications/new")
def application_new(company: str = Form(...), title: str = Form(""), status: str = Form("submitted"), applied_at: str = Form(""),
                     url: str = Form(""), notes: str = Form("")):
    now = db.now_iso()
    app_id = db.insert("applications", {"job_id": None, "company": company, "title": title, "status": status,
                                        "applied_at": applied_at or now, "last_update_at": now, "created_at": now,
                                        "notes": (notes + ("\n" + url if url else "")).strip()})
    db.add_event(app_id, status, "Added manually", source="manual")
    return back("/applications", "added")


@app.get("/applications/{app_id}", response_class=HTMLResponse)
def application_detail(request: Request, app_id: int):
    a = queue.with_job(app_id)
    if not a:
        return back("/queue", "not found")
    drafting = tasks.is_running(f"draft-{app_id}")
    applying = tasks.is_running(f"apply-{app_id}")
    nxt = db.q1("SELECT id FROM applications WHERE status IN ('queued','ready','needs_attention') AND id != ? "
                "ORDER BY CASE status WHEN 'ready' THEN 0 WHEN 'needs_attention' THEN 1 ELSE 2 END, id LIMIT 1", (app_id,))
    review = db.loads(a.get("review_json"), []) if a.get("status") == "review" else []
    fu = None
    if a.get("status") == "submitted":
        quiet = next((s for s in followup.stale(limit=500) if s["id"] == app_id), None)
        fu = {"stale": quiet is not None, "quiet_days": (quiet or {}).get("quiet_days"), "contact": followup.contact(app_id),
              "draft": db.loads(a.get("followup_draft")), "busy": f"followup-{app_id}" in tasks.running(),
              "sent_at": a.get("followup_at"), "snoozed": a.get("followup_snooze_until"), "days": followup.days_setting()}
    receipt = db.loads(a.get("receipt_json"), None)
    check = facts.summary(db.loads(a.get("letter_check_json"), None)) if a.get("letter_check_json") else None
    return render(request, "application.html", check=check, a=a, fu=fu, drafting=drafting, applying=applying, next_id=(nxt or {}).get("id"),
                  review=review, receipt=receipt,
                  statuses=["queued", "ready", "needs_attention", "submitted", "screening", "assessment", "interview",
                            "offer", "rejected", "withdrawn", "failed"])


def remember_answers(review: list[dict], edits: dict, remember: set[str]) -> int:
    """Answers you changed on the review screen, ticked "remember", go into your profile's extra Q&A so the next
    form that asks the same thing is answered the same way without you. One 'Question: answer' line each; a
    repeated question replaces its old line."""
    by_idx = {str(r["idx"]): r for r in review}
    lines = [ln for ln in config.get("cand_extra_answers").splitlines() if ln.strip()]
    added = 0
    for idx in remember:
        r, value = by_idx.get(idx), (edits.get(idx) or "").strip()
        if not r or not value or value == (r.get("value") or "") or r.get("kind") == "file":
            continue
        q = re.sub(r"\s+", " ", (r.get("label") or "").split(" | ")[0]).strip(" :*")
        if not q:
            continue
        lines = [ln for ln in lines if not ln.lower().startswith(q.lower() + ":")]
        lines.append(f"{q}: {value}")
        added += 1
    if added:
        db.set_setting("cand_extra_answers", "\n".join(lines))
    return added


@app.post("/applications/{app_id}/review")
async def application_review(request: Request, app_id: int):
    """The review page's answer to a paused auto-apply: send (with any edited answers) or cancel."""
    form = await request.form()
    a = db.q1("SELECT status FROM applications WHERE id=?", (app_id,))
    if not a or a["status"] != "review" or not tasks.is_running(f"apply-{app_id}"):
        return back(f"/applications/{app_id}", "This application isn't waiting for a check any more")
    action = form.get("action")
    if action not in ("approve", "cancel"):
        return back(f"/applications/{app_id}", "Press Send application or Don't send")
    edits = {k[2:]: str(v) for k, v in form.items() if k.startswith("f_")}
    if action == "approve":
        remember = {k[9:] for k, v in form.items() if k.startswith("remember_") and v}
        n = remember_answers(db.loads(db.q1("SELECT review_json FROM applications WHERE id=?", (app_id,))["review_json"], []), edits, remember)
    db.update("applications", app_id, {"review_decision": db.dumps({"action": action, "edits": edits})})
    return back(f"/applications/{app_id}", ("Sending it now…" + (f" Remembered {n} answer{'s' if n != 1 else ''} for next time." if n else ""))
                if action == "approve" else "Cancelled. Nothing was sent.")


@app.post("/applications/{app_id}/draft")
def application_draft(app_id: int, instruction: str = Form("")):
    rid = tasks.start(f"draft-{app_id}", tasks.draft_task(app_id, instruction))
    return back(f"/applications/{app_id}", "Writing your letter…" if rid else "Already writing this letter")


@app.post("/applications/{app_id}/save")
def application_save(app_id: int, cover_letter: str = Form(""), notes: str = Form(""), approve: int = Form(0), apply_now: int = Form(0)):
    fields = {"cover_letter": cover_letter, "notes": notes, "last_update_at": db.now_iso()}
    before = db.q1("SELECT cover_letter, cover_letter_source FROM applications WHERE id=?", (app_id,)) or {}
    if (cover_letter or "").strip() != (before.get("cover_letter") or "").strip():
        # You changed the words: the old fact check no longer describes this text.
        fields.update({"cover_letter_source": "edited" if before.get("cover_letter_source") == "ai" or before.get("cover_letter") else "you",
                       "letter_check_json": None, "letter_check_at": None})
    if approve or apply_now:
        fields["cover_letter_approved"] = 1
        fields["status"] = "ready"
    db.update("applications", app_id, fields)
    if approve or apply_now:
        writer.learn_from_approved(app_id)
        db.add_event(app_id, "approved", "Cover letter approved by you", source="manual")
    if apply_now:
        rid = tasks.start(f"apply-{app_id}", tasks.apply_task(app_id))
        return back(f"/applications/{app_id}", "Applying now. You'll be asked to check everything before it's sent." if rid else "Already applying")
    return back(f"/applications/{app_id}", "saved" + (" and approved" if approve else ""))


@app.post("/applications/{app_id}/check")
def application_check(app_id: int):
    try:
        s = facts.check_letter(app_id)
    except Exception as e:  # noqa: BLE001
        return back(f"/applications/{app_id}#letter", "Couldn't check the letter. " + messages.friendly_error(e))
    return back(f"/applications/{app_id}#letter", f"Checked {s['n']} claims: " + ("all supported by your resume." if s["clean"] else f"{len(s['flagged'])} need a look."))


@app.post("/applications/{app_id}/apply")
def application_apply(app_id: int):
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not a or not (a.get("cover_letter") or "").strip():
        return back(f"/applications/{app_id}", "Write and approve a cover letter first")
    if not a.get("cover_letter_approved"):
        db.update("applications", app_id, {"cover_letter_approved": 1})
        writer.learn_from_approved(app_id)
    rid = tasks.start(f"apply-{app_id}", tasks.apply_task(app_id))
    return back(f"/applications/{app_id}", "Applying now. You'll be asked to check everything before it's sent." if rid else "Already applying")


@app.post("/applications/{app_id}/followup/draft")
def application_followup_draft(app_id: int):
    rid = tasks.start(f"followup-{app_id}", tasks.followup_task(app_id))
    return back(f"/applications/{app_id}#followup", "Drafting a follow-up note…" if rid else "Already drafting it")


@app.post("/applications/{app_id}/followup")
def application_followup(app_id: int, action: str = Form(...), note: str = Form("")):
    """What you did about a quiet application: sent a note, snoozed the nudge, or let it go."""
    now = db.now_iso()
    if action == "sent":
        db.update("applications", app_id, {"followup_at": now, "followup_snooze_until": None, "last_update_at": now})
        db.add_event(app_id, "followup_sent", (note.strip()[:300] or "Follow-up note sent"), source="manual")
        return back(f"/applications/{app_id}", "Logged. The nudge comes back if they stay quiet.")
    if action == "snooze":
        until = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="minutes")
        db.update("applications", app_id, {"followup_snooze_until": until})
        return back(f"/applications/{app_id}", "Okay, I'll ask again in a week.")
    if action == "giveup":
        queue.set_status(app_id, "withdrawn", "Let it go after no reply", source="manual")
        return back("/applications", "Marked withdrawn. One less thing.")
    return back(f"/applications/{app_id}", "unknown action")


@app.post("/applications/{app_id}/status")
def application_status(app_id: int, status: str = Form(...), detail: str = Form(""), applied_at: str = Form("")):
    queue.set_status(app_id, status, detail or "Set manually", source="manual")
    if applied_at:
        db.update("applications", app_id, {"applied_at": applied_at})
    return back(f"/applications/{app_id}", f"Marked as {messages.app_status(status)[0]}")


@app.post("/applications/{app_id}/notes")
def application_notes(app_id: int, request: Request, notes: str = Form(""), next: str = Form(""), undo_token: str = Form("")):
    tok = undo.record("applications", app_id, token=undo_token)
    db.update("applications", app_id, {"notes": notes.strip() or None})
    if _autosave(request):
        return JSONResponse({"ok": bool(tok), "undo": tok})
    dest = next if next.startswith("/applications") else f"/applications/{app_id}"
    return back(dest, "Note saved", undo=tok)


@app.post("/applications/{app_id}/why")
def application_why(app_id: int, why: str = Form("")):
    receipts.set_why(app_id, why)
    return back(f"/applications/{app_id}#received", "saved")


@app.post("/applications/{app_id}/receipt")
def application_receipt(app_id: int):
    """Take (or retake) the snapshot by hand, e.g. after marking an old application as applied."""
    receipts.snapshot(app_id, "manual", keep_existing=False)
    return back(f"/applications/{app_id}#received", "Snapshot taken")


@app.post("/applications/{app_id}/delete")
def application_delete(request: Request, app_id: int):
    a = queue.remove(app_id)
    in_queue = bool(a) and a.get("status") in ("queued", "drafting", "ready", "applying", "needs_attention", "failed")
    return back("/queue" if in_queue else "/applications", "removed")


# ---- assessments -------------------------------------------------------------

@app.get("/assessments")
def assessments():
    return RedirectResponse("/upcoming#assessments", status_code=302)


def _aware(s) -> datetime | None:
    d = _parse_dt(s) if s else None
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def coming_up(days: int = 14, limit: int = 12) -> list[dict]:
    """Interviews and assessments in time order for the next `days`: {kind, title, detail, at, when_text, href, action, urgent}.
    Invites with no time yet come first (they need an answer), then scheduled things by start time."""
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for x in db.q("SELECT * FROM interviews WHERE status IN ('needs_scheduling','scheduled') ORDER BY COALESCE(starts_at,'0')"):
        at = _aware(x.get("starts_at"))
        if at is not None and (at - now).total_seconds() > days * 86400:
            continue
        if at is not None and (at - now).total_seconds() < -3 * 3600:
            continue   # already happened; the table below handles marking it done
        what = f"{x.get('stage') or 'Interview'}" + (f" ({messages.INTERVIEW_FORMAT.get(x.get('format') or '', '')})" if x.get("format") else "")
        who = f" with {x['interviewer']}" if x.get("interviewer") else ""
        out.append({"kind": "Interview" if at is not None else "Pick an interview time",
                    "title": f"{what} · {x.get('company') or ''}", "detail": (x.get("title") or "") + who,
                    "at": x.get("starts_at") if at is not None else None,
                    "when_text": "needs a time" if at is None else "",
                    "href": x.get("link") or "/upcoming#interviews", "action": ("Join" if at is not None else "Schedule") if x.get("link") else "Open",
                    "urgent": at is None or (at - now).total_seconds() < 24 * 3600, "sort": at or now})
    for x in db.q("SELECT * FROM assessments WHERE status='pending' ORDER BY COALESCE(due_at,'9999')"):
        at = _aware(x.get("due_at"))
        if at is not None and (at - now).total_seconds() > days * 86400:
            continue
        out.append({"kind": "Assessment due", "title": f"{x.get('platform') or ''} {x.get('title') or ''} · {x.get('company') or ''}".strip(" ·"),
                    "detail": (f"About {x['est_minutes']} min" if x.get("est_minutes") else "") + (" · deadline assumed" if x.get("due_source") == "assumed" else ""),
                    "at": x.get("due_at") if at is not None else None, "when_text": "no deadline given",
                    "href": f"/assessments/{x['id']}/open" if x.get("link") else "/upcoming#assessments", "action": "Open test" if x.get("link") else "Open",
                    "urgent": at is not None and (at - now).total_seconds() < 24 * 3600, "sort": at or (now + timedelta(days=days))})
    out.sort(key=lambda i: (i["at"] is not None and i["kind"] != "Assessment due" or i["at"] is not None, i["sort"]))
    return out[:limit]


@app.get("/upcoming", response_class=HTMLResponse)
def upcoming(request: Request):
    email_tracker.mark_missed()
    now = datetime.now(timezone.utc)
    interviews = db.q("SELECT i.*, p.title AS app_title, p.status AS app_status FROM interviews i "
                      "LEFT JOIN applications p ON p.id=i.application_id "
                      "ORDER BY CASE i.status WHEN 'needs_scheduling' THEN 0 WHEN 'scheduled' THEN 1 ELSE 2 END, COALESCE(i.starts_at, i.received_at)")
    for x in interviews:
        at = _aware(x.get("starts_at"))
        x["past"] = at is not None and at < now
    assessments = db.q("SELECT a.*, p.title AS app_title, p.status AS app_status, e.seen AS email_seen, e.folder AS email_folder FROM assessments a "
                       "LEFT JOIN applications p ON p.id=a.application_id LEFT JOIN emails e ON e.id=a.email_id "
                       "ORDER BY CASE a.status WHEN 'pending' THEN 0 WHEN 'missed' THEN 1 ELSE 2 END, COALESCE(a.due_at,'9999')")
    apps = db.q("SELECT id, company, title FROM applications ORDER BY company")
    cal_url = str(request.base_url).rstrip("/") + "/calendar.ics?token=" + calendar_feed.token()
    for x in assessments:
        f = (x.get("email_folder") or "").lower()
        x["spam"] = bool(f) and f != "inbox" and ("spam" in f or "junk" in f)
        t = do_by(_aware(x.get("due_at")), now)
        x["do_by"] = t.isoformat() if t and x.get("status") == "pending" and _aware(x.get("due_at")) and t != _aware(x.get("due_at")) else None
    return render(request, "upcoming.html", soon=coming_up(), interviews=interviews, assessments=assessments, apps=apps, cal_url=cal_url,
                  formats=list(messages.INTERVIEW_FORMAT.items()), default_days=config.get_int("assessment_default_days", 7))


# ---- interviews -------------------------------------------------------------

@app.post("/interviews/new")
def interview_new(company: str = Form(""), stage: str = Form(""), format: str = Form(""), starts_at: str = Form(""),
                  duration_minutes: int = Form(0), interviewer: str = Form(""), link: str = Form(""), location: str = Form(""),
                  application_id: int = Form(0)):
    at = deadlines.from_local_input(starts_at)
    db.insert("interviews", {"application_id": application_id or None, "company": company, "stage": stage or None,
                             "format": format or None, "starts_at": at, "time_source": "manual" if at else None,
                             "tz": deadlines.tz_label(deadlines.to_local(at)) if at else None,
                             "duration_minutes": duration_minutes or None, "interviewer": interviewer or None,
                             "link": link or None, "location": location or None,
                             "status": "scheduled" if at else "needs_scheduling", "received_at": db.now_iso(), "created_at": db.now_iso()})
    return back("/upcoming#interviews", "added")


@app.post("/interviews/{iid}/status")
def interview_status(iid: int, status: str = Form(...)):
    if status not in ("needs_scheduling", "scheduled", "done", "cancelled", "missed"):
        return back("/upcoming#interviews", "unknown status")
    db.update("interviews", iid, {"status": status})
    return back("/upcoming#interviews", "marked " + messages.interview_status(status)[0].lower())


@app.post("/interviews/{iid}/edit")
def interview_edit(iid: int, request: Request, starts_at: str = Form(""), duration_minutes: int = Form(0), stage: str = Form(""),
                   format: str = Form(""), interviewer: str = Form(""), link: str = Form(""), location: str = Form(""),
                   notes: str = Form(""), application_id: int = Form(0), new_role: str = Form(""), undo_token: str = Form("")):
    x = db.q1("SELECT * FROM interviews WHERE id=?", (iid,))
    if not x:
        return JSONResponse({"ok": False, "error": "This interview was deleted."}, status_code=404) if _autosave(request) \
            else back("/upcoming#interviews", "not found")
    tok = undo.record("interviews", iid, token=undo_token)
    fields = {"duration_minutes": duration_minutes or None, "stage": stage or None, "format": format or None,
              "interviewer": interviewer or None, "link": link or None, "location": location or None, "notes": notes or None}
    shown = deadlines.to_local(x.get("starts_at")).strftime("%Y-%m-%dT%H:%M") if deadlines.to_local(x.get("starts_at")) else ""
    if (starts_at or "") != shown:   # only a real edit counts as manual
        at = deadlines.from_local_input(starts_at)
        fields.update({"starts_at": at, "time_source": "manual" if at else None,
                       "tz": deadlines.tz_label(deadlines.to_local(at)) if at else None})
        if x["status"] in ("needs_scheduling", "scheduled"):
            fields["status"] = "scheduled" if at else "needs_scheduling"
    db.update("interviews", iid, fields)
    if _autosave(request):
        return JSONResponse({"ok": True, "undo": tok})
    if new_role.strip() or (application_id and application_id != x.get("application_id")):
        email_tracker.relink("interviews", iid, application_id or None, new_role)
        return back("/upcoming#interviews", "Saved. The interview is now linked to " + (new_role.strip() or "that application"))
    return back("/upcoming#interviews", "Saved", undo=tok)


# ---- calendar + prep ------------------------------------------------------------

def _ics(body: str, filename: str) -> Response:
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---- messages (correspondence) ------------------------------------------------------

def _messages_page(request: Request, app_id: int | None, draft_body: str = "", draft_subject: str = ""):
    items = mail.threads()
    cur = db.q1("SELECT id, company, title, status FROM applications WHERE id=?", (app_id,)) if app_id else None
    target = mail.reply_target(app_id) if cur else {}
    if draft_subject and not target.get("in_reply_to"):
        target["subject"] = draft_subject    # a reply keeps the recruiter's subject so it threads; a first message takes the draft's
    return render(request, "messages.html", items=items, cur=cur, msgs=mail.thread(app_id) if cur else [], target=target,
                  draft_body=draft_body, smtp_ready=mail.smtp_ready(), from_addr=config.get("email_user").strip())


@app.get("/messages", response_class=HTMLResponse)
def messages_list(request: Request):
    return _messages_page(request, None)


@app.get("/messages/{app_id}", response_class=HTMLResponse)
def messages_thread(request: Request, app_id: int):
    if not db.q1("SELECT id FROM applications WHERE id=?", (app_id,)):
        return back("/messages", "not found")
    return _messages_page(request, app_id)


@app.post("/messages/{app_id}/send")
def messages_send(app_id: int, to: str = Form(""), subject: str = Form(""), body: str = Form(""), in_reply_to: str = Form("")):
    try:
        mail.send(app_id, to, subject, body, in_reply_to)
    except Exception as e:  # noqa: BLE001
        return back(f"/messages/{app_id}", "Not sent. " + messages.friendly_error(e))
    return back(f"/messages/{app_id}", f"Sent to {to.strip()}")


@app.post("/messages/{app_id}/draft", response_class=HTMLResponse)
def messages_draft(request: Request, app_id: int, instruction: str = Form("")):
    try:
        d = mail.draft(app_id, instruction)
    except Exception as e:  # noqa: BLE001
        return back(f"/messages/{app_id}", "Couldn't draft. " + messages.friendly_error(e))
    return _messages_page(request, app_id, draft_body=d.body, draft_subject=d.subject)


# ---- capture (share target / paste) ------------------------------------------------

@app.get("/capture", response_class=HTMLResponse)
def capture_page(request: Request, url: str = "", text: str = "", title: str = ""):
    """One box. Arriving from the phone's share sheet (manifest share_target) fills it; the form then saves."""
    return render(request, "capture.html", url=url, text=text, title=title, result=None)


@app.post("/capture", response_class=HTMLResponse)
def capture_save(request: Request, url: str = Form(""), text: str = Form(""), title: str = Form("")):
    try:
        res = capture.capture(text=text, url=url, title=title)
    except Exception as e:  # noqa: BLE001
        return render(request, "capture.html", url=url, text=text, title=title,
                      result={"kind": "error", "message": "Couldn't read that. " + messages.friendly_error(e)})
    if res["kind"] == "job":
        return RedirectResponse(f"/jobs/{res['job']['id']}?msg=" + quote(res["message"]), status_code=303)
    if res["kind"] == "application" and res.get("app_id"):
        return RedirectResponse(f"/applications/{res['app_id']}?msg=" + quote(res["message"]), status_code=303)
    return render(request, "capture.html", url=url, text=text, title=title, result=res)


# ---- phone alerts (Web Push) ---------------------------------------------------

@app.get("/sw.js")
def service_worker():
    """Served from the root so its scope covers the whole app."""
    body = (HERE / "static" / "sw.js").read_text(encoding="utf-8")
    return Response(body, media_type="application/javascript", headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/push/state")
def push_state():
    _priv, pub = notify.vapid_keys()
    return JSONResponse({"vapid_public": pub, "subscriptions": len(notify.subscriptions()),
                         "webhook": bool((config.get("notify_webhook_url") or "").strip())})


@app.post("/push/subscribe")
async def push_subscribe(request: Request):
    data = await request.json()
    sub = data.get("subscription") or data
    try:
        sid = notify.add_subscription(sub, label=str(data.get("label") or "")[:80])
    except ValueError:
        return JSONResponse({"ok": False, "error": "no endpoint"}, status_code=400)
    return JSONResponse({"ok": True, "id": sid, "subscriptions": len(notify.subscriptions())})


@app.post("/push/unsubscribe")
async def push_unsubscribe(request: Request):
    data = await request.json()
    notify.remove_subscription(str(data.get("endpoint") or ""))
    return JSONResponse({"ok": True, "subscriptions": len(notify.subscriptions())})


@app.post("/push/snooze")
async def push_snooze(request: Request):
    data = await request.json()
    key = str(data.get("key") or "")
    if not key:
        return JSONResponse({"ok": False}, status_code=400)
    notify.snooze(key, float(data.get("hours") or 1))
    return JSONResponse({"ok": True})


@app.post("/push/test")
def push_test():
    res = notify.send("jobhunt is set up", "This is what a Don't-miss alert looks like. Tests: 3 days, 1 day, 3 hours before. Interviews: the day before and an hour before.",
                      url="/", key="test", action="Open Today")
    bits = []
    if res["push"]:
        bits.append(f"pushed to {res['push']} device{'s' if res['push'] != 1 else ''}")
    if res["webhook"]:
        bits.append("sent to your webhook")
    if not bits:
        err = config.get("notify_webhook_error") or ""
        bits.append("nothing went out. Turn on alerts on your phone first, or set a webhook." + (f" Webhook error: {err}" if err else ""))
    return back("/settings", "; ".join(bits))


@app.get("/calendar.ics")
def calendar_ics(token: str = ""):
    """Subscribable feed; the token in the URL is the only auth, since calendar apps cannot log in."""
    if not token or not hmac.compare_digest(token, calendar_feed.token()):
        return Response("not found", status_code=404)
    return Response(calendar_feed.feed(), media_type="text/calendar; charset=utf-8")


@app.post("/calendar/reset")
def calendar_reset():
    db.set_setting("calendar_token", "")
    calendar_feed.token()
    return back("/upcoming#calendar", "New calendar link made. Re-subscribe on your phone; the old link is dead.")


@app.get("/interviews/{iid}.ics")
def interview_ics(iid: int):
    x = db.q1("SELECT * FROM interviews WHERE id=?", (iid,))
    if not x or not x.get("starts_at"):
        return back("/upcoming#interviews", "That interview has no time yet")
    return _ics(calendar_feed.wrap(calendar_feed.interview_event(x)), f"interview-{iid}.ics")


@app.get("/assessments/{aid}.ics")
def assessment_ics(aid: int):
    x = db.q1("SELECT * FROM assessments WHERE id=?", (aid,))
    if not x or not x.get("due_at"):
        return back("/upcoming#assessments", "That assessment has no deadline")
    return _ics(calendar_feed.wrap(calendar_feed.assessment_event(x)), f"assessment-{aid}.ics")


@app.get("/interviews/{iid}/prep", response_class=HTMLResponse)
def interview_prep(request: Request, iid: int):
    x = db.q1("SELECT * FROM interviews WHERE id=?", (iid,))
    if not x:
        return back("/upcoming#interviews", "not found")
    card = db.loads(x.get("prep_json")) if x.get("prep_json") else None
    return render(request, "prep.html", x=x, card=card, busy=f"prep-{iid}" in tasks.running())


@app.post("/interviews/{iid}/prep")
def interview_prep_start(iid: int):
    rid = tasks.start(f"prep-{iid}", tasks.prep_task(iid))
    return back(f"/interviews/{iid}/prep", "Writing your prep card… about 30 seconds." if rid else "Already writing it")


@app.post("/interviews/{iid}/delete")
def interview_delete(iid: int):
    tok = undo.record("interviews", iid, kind="delete")
    db.execute("DELETE FROM interviews WHERE id=?", (iid,))
    return back("/upcoming#interviews", "Interview deleted", undo=tok)


@app.post("/assessments/new")
def assessment_new(company: str = Form(""), title: str = Form(""), platform: str = Form(""), link: str = Form(""),
                   due_at: str = Form(""), est_minutes: int = Form(0), application_id: int = Form(0)):
    db.insert("assessments", {"application_id": application_id or None, "company": company, "title": title or "Assessment",
                              "platform": platform, "link": link, "due_at": deadlines.from_local_input(due_at),
                              "due_source": "manual" if due_at else None, "est_minutes": est_minutes or None,
                              "status": "pending", "received_at": db.now_iso(), "created_at": db.now_iso()})
    return back("/upcoming#assessments", "added")


@app.get("/assessments/{aid}/open")
def assessment_open(aid: int):
    """Click-through: remember that the assessment link was opened, then go there."""
    a = db.q1("SELECT link, opened_at FROM assessments WHERE id=?", (aid,))
    if not a or not a.get("link"):
        return back("/upcoming#assessments", "no link on this assessment")
    if not a.get("opened_at"):
        db.update("assessments", aid, {"opened_at": db.now_iso()})
    return RedirectResponse(a["link"], status_code=302)


@app.post("/assessments/{aid}/opened")
def assessment_opened(aid: int, value: str = Form("1")):
    db.update("assessments", aid, {"opened_at": db.now_iso() if value == "1" else None})
    return back("/upcoming#assessments", "marked opened" if value == "1" else "marked unopened")


@app.post("/assessments/{aid}/status")
def assessment_status(aid: int, status: str = Form(...)):
    fields = {"status": status}
    if status == "completed":
        fields["completed_at"] = db.now_iso()
    db.update("assessments", aid, fields)
    return back("/upcoming#assessments", f"marked {status}")


@app.post("/assessments/{aid}/edit")
def assessment_edit(aid: int, request: Request, due_at: str = Form(""), est_minutes: int = Form(0), notes: str = Form(""),
                    link: str = Form(""), application_id: int = Form(0), new_role: str = Form(""), undo_token: str = Form("")):
    if not db.q1("SELECT 1 FROM assessments WHERE id=?", (aid,)):
        return JSONResponse({"ok": False, "error": "This test was deleted."}, status_code=404) if _autosave(request) \
            else back("/upcoming#assessments", "not found")
    tok = undo.record("assessments", aid, token=undo_token)
    fields = {"est_minutes": est_minutes or None, "notes": notes, "link": link or None}
    cur = (db.q1("SELECT due_at FROM assessments WHERE id=?", (aid,)) or {}).get("due_at")
    shown = deadlines.to_local(cur).strftime("%Y-%m-%dT%H:%M") if deadlines.to_local(cur) else ""
    if (due_at or "") != shown:   # only treat it as a manual change if the user actually edited the field
        new_due = deadlines.from_local_input(due_at)
        fields.update({"due_at": new_due, "due_source": "manual" if new_due else None,
                       "due_tz": deadlines.tz_label(deadlines.to_local(new_due)) if new_due else None})
    db.update("assessments", aid, fields)
    if _autosave(request):
        return JSONResponse({"ok": True, "undo": tok})
    cur_app = (db.q1("SELECT application_id FROM assessments WHERE id=?", (aid,)) or {}).get("application_id")
    if new_role.strip() or (application_id and application_id != cur_app):
        email_tracker.relink_assessment(aid, application_id or None, new_role)
        return back("/upcoming#assessments", "Saved. The assessment is now linked to " + (new_role.strip() or "that application"))
    return back("/upcoming#assessments", "Saved", undo=tok)


@app.post("/assessments/{aid}/delete")
def assessment_delete(aid: int):
    tok = undo.record("assessments", aid, kind="delete")
    db.execute("DELETE FROM assessments WHERE id=?", (aid,))
    return back("/upcoming#assessments", "Test deleted", undo=tok)


@app.post("/undo/{token}")
def undo_change(token: str, request: Request):
    r = undo.restore(token)
    if _autosave(request):
        return JSONResponse({"ok": bool(r)}, status_code=200 if r else 404)
    if not r:
        return back_here(request, "/", "Nothing to undo. It may already be undone.")
    return back_here(request, "/", "Restored" if r["kind"] == "delete" else "Undone")


# ---- documents ---------------------------------------------------------------

@app.get("/documents", response_class=HTMLResponse)
def docs(request: Request):
    return render(request, "documents.html", docs=documents.all_documents())


@app.post("/documents/upload")
async def doc_upload(kind: str = Form(...), title: str = Form(""), notes: str = Form(""), file: UploadFile = File(...)):
    data = await file.read()
    try:
        documents.save_upload(kind, title, file.filename or "upload", data, notes)
    except Exception as e:  # noqa: BLE001
        return back("/documents", "Upload failed. " + messages.friendly_error(e))
    return back("/documents", "uploaded")


@app.post("/documents/paste")
def doc_paste(kind: str = Form(...), title: str = Form(""), content: str = Form(...), notes: str = Form("")):
    documents.add_document(kind, title or f"{kind} {datetime.now():%Y-%m-%d}", content.strip(), notes=notes)
    return back("/documents", "saved")


@app.post("/documents/{doc_id}/status")
def doc_status(doc_id: int, status: str = Form(...)):
    documents.set_status(doc_id, status)
    return back("/documents", f"{status}")


@app.post("/documents/{doc_id}/delete")
def doc_delete(doc_id: int):
    db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    return back("/documents", "deleted")


@app.get("/documents/{doc_id}", response_class=HTMLResponse)
def doc_view(request: Request, doc_id: int):
    d = db.q1("SELECT * FROM documents WHERE id=?", (doc_id,))
    return render(request, "document.html", d=d)


@app.post("/documents/{doc_id}/update")
def doc_update(doc_id: int, title: str = Form(...), content: str = Form(...), notes: str = Form("")):
    db.update("documents", doc_id, {"title": title, "content": content, "notes": notes, "updated_at": db.now_iso()})
    return back(f"/documents/{doc_id}", "saved")


# ---- companies ---------------------------------------------------------------

@app.get("/companies", response_class=HTMLResponse)
def companies(request: Request):
    return render(request, "companies.html", rows=db.q("SELECT * FROM companies ORDER BY enabled DESC, name"))


@app.post("/companies/add")
def company_add(name: str = Form(""), url_or_token: str = Form(...), ats: str = Form("auto")):
    cid = pipeline.add_company_from_url(url_or_token, name) if ats == "auto" else pipeline.add_company(name, ats, url_or_token)
    return back("/companies", "added" if cid else "could not detect ATS from that URL. Paste a job link from the company's careers site, or choose the ATS and give its board token.")


@app.post("/companies/seed")
def company_seed():
    return back("/companies", f"added {pipeline.seed_starters()} starter boards (tokens validate on first fetch)")


@app.post("/companies/{cid}/toggle")
def company_toggle(cid: int):
    c = db.q1("SELECT enabled FROM companies WHERE id=?", (cid,))
    db.update("companies", cid, {"enabled": 0 if c["enabled"] else 1})
    return back("/companies")


@app.post("/companies/{cid}/delete")
def company_delete(cid: int):
    db.execute("DELETE FROM companies WHERE id=?", (cid,))
    return back("/companies", "deleted")


# ---- settings ----------------------------------------------------------------

@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    vals = {k: config.get(k) for k, *_ in config.SETTING_SPECS}
    subs = notify.subscriptions()
    own = messages.label_overrides()
    labels = [(code, info[0], own.get(code, "")) for code, info in messages.APP_STATUS.items()] + \
             [("job:" + code, info[0], own.get("job:" + code, "")) for code, info in messages.JOB_STATUS.items()]
    return render(request, "settings.html", specs=config.SETTING_SPECS, vals=vals, options=config.SELECT_OPTIONS, labels=labels,
                  push_subs=subs, push_n=len(subs))


@app.post("/settings")
async def settings_save(request: Request):
    form = await request.form()
    for key, _label, _default, kind, _help in config.SETTING_SPECS:
        if kind == "bool":
            db.set_setting(key, "1" if form.get(key) else "0")
        elif key in form:
            v = str(form.get(key, ""))
            if kind == "password" and not v.strip():
                continue  # keep existing secret when left blank
            db.set_setting(key, v)
    return back("/settings", "saved")


@app.post("/settings/labels")
async def settings_labels(request: Request):
    form = await request.form()
    own = {k[2:]: str(v).strip()[:40] for k, v in form.items() if k.startswith("l_") and str(v).strip()}
    db.set_setting("status_labels", db.dumps(own))
    return back("/settings#labels", "Status names saved")


@app.post("/settings/suggest")
def settings_suggest():
    try:
        p = matcher.suggest_search_profile()
    except Exception as e:  # noqa: BLE001
        return back("/settings", "Couldn't suggest titles. " + messages.friendly_error(e))
    db.set_setting("search_titles", "\n".join(p.titles))
    if not config.get("search_keywords").strip():
        db.set_setting("search_keywords", "\n".join(p.keywords))
    return back("/settings", f"suggested {len(p.titles)} titles ({p.seniority}). {p.summary}")


@app.post("/settings/test_key")
def settings_test_key():
    ok, msg = llm.check_key()
    return back("/settings", msg)


@app.post("/settings/test_smtp")
def settings_test_smtp():
    ok, msg = mail.test_send()
    return back("/settings", msg)


@app.post("/settings/test_email")
def settings_test_email():
    ok, msg = email_tracker.test_connection()
    return back("/settings", msg)
