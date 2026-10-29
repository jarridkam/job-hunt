"""Fetch -> dedupe -> legitimacy -> store, plus ATS board discovery."""
from __future__ import annotations

import re

from . import config, db, legit
from .sources.aggregators import AGGREGATORS, REMOTE_BOARDS
from .sources.base import Job, SourceContext, detect_ats, make_http
from .sources.boards import FETCHERS

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


def _store(job: Job, run_id: int) -> str:
    """Insert a job; returns 'new' | 'dup' | 'merged' | 'filtered'."""
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
    counts = {"new": 0, "dup": 0, "merged": 0, "filtered": 0}
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
        counts[_store(j, run_id)] += 1
    ctx.http.close()
    log(f"fetch done: {counts}")
    return counts
