"""Fetch -> dedupe -> legitimacy -> store, plus ATS board discovery."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import config, db, legit
from .sources.aggregators import AGGREGATORS, REMOTE_BOARDS
from .sources.base import Job, SourceContext, detect_ats, make_http
from .sources.boards import FETCHERS, _feed_items

# Optional starter boards. Tokens are validated on first fetch; a wrong one just records an error.
STARTER_BOARDS = [
    ("Stripe", "greenhouse", "stripe"), ("Airbnb", "greenhouse", "airbnb"), ("Discord", "greenhouse", "discord"),
    ("Figma", "greenhouse", "figma"), ("Cloudflare", "greenhouse", "cloudflare"), ("Databricks", "greenhouse", "databricks"),
    ("Dropbox", "greenhouse", "dropbox"), ("GitLab", "greenhouse", "gitlab"), ("Coinbase", "greenhouse", "coinbase"),
    ("Twilio", "greenhouse", "twilio"), ("Duolingo", "greenhouse", "duolingo"), ("Reddit", "greenhouse", "reddit"),
    ("Brex", "greenhouse", "brex"), ("Anthropic", "greenhouse", "anthropic"), ("Datadog", "greenhouse", "datadog"),
    ("Lyft", "greenhouse", "lyft"), ("Instacart", "greenhouse", "instacart"), ("Samsara", "greenhouse", "samsara"),
    ("Plaid", "lever", "plaid"), ("Zapier", "lever", "zapier"),
    ("Notion", "ashby", "notion"), ("Linear", "ashby", "linear"), ("Ramp", "ashby", "ramp"), ("Vanta", "ashby", "vanta"),
    ("Supabase", "ashby", "supabase"), ("Deel", "ashby", "deel"),
]


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def add_company(name: str, ats: str, token: str, discovered: bool = False) -> int | None:
    token = token.strip()
    if ats not in FETCHERS or not token:
        return None
    existing = db.q1("SELECT id FROM companies WHERE ats=? AND board_token=?", (ats, token))
    if existing:
        return existing["id"]
    return db.insert("companies", {"name": name or token, "ats": ats, "board_token": token,
                                   "discovered": 1 if discovered else 0, "created_at": db.now_iso()})


def add_company_from_url(url: str, name: str = "") -> int | None:
    d = detect_ats(url)
    if not d:
        return None
    return add_company(name or d[1], d[0], d[1])


CLOSED_BOARDS = {"indeed.com": "Indeed", "linkedin.com": "LinkedIn", "glassdoor.com": "Glassdoor", "ziprecruiter.com": "ZipRecruiter", "monster.com": "Monster"}
FEED_PATHS = ("/careers/rss.xml", "/jobs/rss.xml", "/rss.xml", "/feed.xml", "/jobs.rss", "/remote-jobs.rss", "/feed", "/rss", "/jobs/feed", "/feed/job_feed")
FEED_LINK = re.compile(r"<(?:link|a)\b[^>]*>", re.I)


def _is_feed(http, url: str) -> bool:
    try:
        r = http.get(url)
        return r.status_code == 200 and bool(_feed_items(r.text))
    except Exception:  # noqa: BLE001
        return False


def find_feed(url: str) -> str | None:
    """The job feed behind a board's address: the link itself, one the page points to, or a usual place for one."""
    http = make_http()
    try:
        if _is_feed(http, url):
            return url
        try:
            page = http.get(url).text
        except Exception:  # noqa: BLE001
            page = ""
        tags = [t for t in FEED_LINK.findall(page) if re.search(r"rss|atom|feed", t, re.I)]
        hrefs = [m.group(1) for t in tags for m in [re.search(r'href=["\']([^"\']+)', t)] if m]
        for href in dict.fromkeys(urljoin(url, h) for h in hrefs):
            if _is_feed(http, href):
                return href
        for path in FEED_PATHS:
            if _is_feed(http, urljoin(url, path)):
                return urljoin(url, path)
        return None
    finally:
        http.close()


def add_board(url: str, name: str = "") -> tuple[int | None, str]:
    """Add a job board by its address. Returns (id, what to tell the user)."""
    url = url.strip()
    url = url if "://" in url else "https://" + url
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if urlparse(url).scheme not in ("http", "https") or not host:
        return None, "That doesn't look like a web address."
    if detect_ats(url):
        return add_company_from_url(url, name), "That's one company's careers page, so it went under Companies."
    for dom, label in CLOSED_BOARDS.items():
        if host == dom or host.endswith("." + dom):
            return None, f"{label} blocks outside tools, so it can't be added here. A JSearch key in Settings brings in most of its listings."
    feed = find_feed(url)
    if not feed:
        return None, f"{host} doesn't publish a job feed that jobhunt can read, so it can't be added yet."
    if not name:
        http = make_http()
        name = (ET.fromstring(http.get(feed).text.lstrip()).findtext("channel/title") or host.split(".")[0].capitalize()).strip()[:60]
        http.close()
    return add_company(name, "feed", feed), "Added. Its jobs show up after the next search."


def seed_starters() -> int:
    n = 0
    for name, ats, token in STARTER_BOARDS:
        if add_company(name, ats, token):
            n += 1
    return n


def _context(log) -> SourceContext:
    return SourceContext(
        titles=config.get_lines("search_titles"), keywords=config.get_lines("search_keywords"),
        locations=config.get_lines("search_locations"), remote_only=config.get_bool("remote_only"),
        log=log, http=make_http(),
    )


# Wording a dead job page uses. It says "this job has been filled", never "until the position is filled",
# which is in plenty of live ads.
_JOB = r"(?:job|position|role|posting|listing|opening|vacancy|requisition|opportunity)s?"
CLOSED_PAGE = re.compile(
    rf"\b{_JOB}\b[^.!?\n]{{0,40}}\b(?:no longer (?:available|open|active|accepting|exists?|posted|listed)|"
    r"(?:has|have) been (?:filled|closed|removed|taken down)|has (?:closed|expired)|is (?:now )?(?:closed|expired))\b"
    rf"|\b{_JOB} (?:was )?not found\b|\bpage not found\b|\bno longer accepting\b|\bnot accepting (?:new )?applications\b"
    r"|\bapplications? (?:are |is |have |has |now )+closed\b", re.I)


class _VisibleText(HTMLParser):
    """Page text a person would see. Job sites keep a hidden "this job has closed" notice on every open job."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    SKIP = {"script", "style", "noscript", "template", "head"}
    HIDDEN = re.compile(r"\b(?:w-condition-invisible|hidden|d-none|sr-only)\b")
    NO_SHOW = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.open_tags, self.hide_at = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        self.open_tags.append(tag)
        a = dict(attrs)
        if self.hide_at is None and (tag in self.SKIP or "hidden" in a or self.HIDDEN.search(a.get("class") or "")
                                     or self.NO_SHOW.search(a.get("style") or "")):
            self.hide_at = len(self.open_tags)

    def handle_endtag(self, tag):
        if tag not in self.open_tags:
            return
        while self.open_tags.pop() != tag:    # closes anything left unclosed inside it
            pass
        if self.hide_at is not None and len(self.open_tags) < self.hide_at:
            self.hide_at = None

    def handle_data(self, data):
        if self.hide_at is None:
            self.text.append(data)


def visible_text(page: str) -> str:
    v = _VisibleText()
    v.feed(page)
    return " ".join(" ".join(v.text).split())


def page_closed(http, url: str) -> str:
    """Why this job's page says it's gone, or "" if it looks open. A page we can't read counts as open:
    sites that block robots shouldn't cost you a real job."""
    try:
        r = http.get(url, timeout=8.0)
    except Exception:  # noqa: BLE001
        return ""
    if r.status_code in (404, 410):
        return f"page gone ({r.status_code})"
    if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
        return ""
    if "error=true" in str(r.url):    # Greenhouse sends closed jobs back to the board like this
        return "sent back to the job board"
    hit = CLOSED_PAGE.search(visible_text(r.text))
    return f'page says "{hit.group(0)}"' if hit else ""


def _store(job: Job, run_id: int, http=None) -> str:
    """Insert a job; returns 'new' | 'dup' | 'merged' | 'filtered' | 'closed'."""
    if config.get_bool("remote_only") and not job.remote:
        return "filtered"
    ats = detect_ats(job.apply_url) or detect_ats(job.url)
    if db.q1("SELECT id FROM jobs WHERE source=? AND external_id=?", (job.source, job.external_id)):
        return "dup"
    # Cross-source dedupe on company + title.
    same = db.q1("SELECT * FROM jobs WHERE lower(company)=? AND lower(title)=? ORDER BY id LIMIT 1",
                 (job.company.lower().strip(), job.title.lower().strip())) if job.company else None
    if same:
        if ats and not same.get("ats"):
            db.update("jobs", same["id"], {"apply_url": job.apply_url, "ats": ats[0]})
            return "merged"
        return "dup"
    row = {
        "source": job.source, "external_id": job.external_id, "url": job.url, "apply_url": job.apply_url,
        "title": job.title.strip(), "company": job.company.strip(), "location": job.location, "remote": int(job.remote),
        "description": job.description, "salary_min": job.salary_min, "salary_max": job.salary_max,
        "posted_at": job.posted_at, "fetched_at": db.now_iso(), "ats": ats[0] if ats else None, "raw": db.dumps(job.raw),
    }
    s, why = legit.score(row)
    row.update({"legit_score": s, "legit_reasons": db.dumps(why)})
    if s < config.get_int("min_legit_score", 55):
        row["status"] = "not_legit"
    # Company boards only list open jobs. Everything else can be weeks stale, so read the page itself.
    gone = ""
    if http and (job.source not in FETCHERS or job.source == "board"):
        gone = page_closed(http, job.url) or (page_closed(http, job.apply_url) if job.apply_url != job.url else "")
    if gone:
        # Kept, hidden, so the next search doesn't check it all over again.
        row["status"] = "closed"
        db.insert("jobs", row)
        db.run_log(run_id, f"skipped closed job: {job.company} {job.title}: {gone}")
        return "closed"
    db.insert("jobs", row)
    if ats and job.source not in FETCHERS:
        # Discovered a company board via an aggregator link: pull the whole board next run.
        cid = add_company(job.company, ats[0], ats[1], discovered=True)
        if cid:
            db.run_log(run_id, f"discovered {ats[0]} board '{ats[1]}' for {job.company}")
    return "new"


def fetch_all(run_id: int) -> dict:
    log = lambda m: db.run_log(run_id, m)  # noqa: E731
    ctx = _context(log)
    if not ctx.titles:
        raise RuntimeError("No target titles set. Fill Settings > Target job titles (or click Suggest from resume).")
    counts = {"new": 0, "dup": 0, "merged": 0, "filtered": 0, "closed": 0}
    jobs: list[Job] = []

    for c in db.q("SELECT * FROM companies WHERE enabled=1 ORDER BY name"):
        fetcher = FETCHERS.get(c["ats"])
        if not fetcher:
            continue
        try:
            got = fetcher(ctx, c["board_token"], c["name"])
            jobs.extend(got)
            db.update("companies", c["id"], {"last_fetch_at": db.now_iso(), "last_error": None})
            log(f"{c['ats']}/{c['board_token']}: {len(got)} matching")
        except Exception as e:  # noqa: BLE001
            msg = str(e)[:200]
            db.update("companies", c["id"], {"last_error": msg})
            db.run_warn(run_id, f"{c['name']} job board ({c['ats']}) couldn't be read: {msg}")

    for f in AGGREGATORS:
        try:
            jobs.extend(f(ctx))
        except Exception as e:  # noqa: BLE001
            db.run_warn(run_id, f"{f.__name__.removeprefix('fetch_')} search failed: {str(e)[:200]}")
    if config.get_bool("use_remote_boards"):
        for f in REMOTE_BOARDS:
            try:
                jobs.extend(f(ctx))
            except Exception as e:  # noqa: BLE001
                db.run_warn(run_id, f"{f.__name__.removeprefix('fetch_')} board failed: {str(e)[:200]}")

    for j in jobs:
        if not j.title or not (j.apply_url or j.url):
            continue
        counts[_store(j, run_id, ctx.http)] += 1
    ctx.http.close()
    log(f"fetch done: {counts}")
    return counts
