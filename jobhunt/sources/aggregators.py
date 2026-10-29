"""Aggregators and remote boards. Keys optional; sources without keys are skipped."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from .. import config
from .base import Job, SourceContext, looks_remote, strip_html, title_matches


def fetch_adzuna(ctx: SourceContext) -> list[Job]:
    app_id, app_key = config.get("adzuna_app_id").strip(), config.get("adzuna_app_key").strip()
    if not app_id or not app_key:
        ctx.log("adzuna: no key, skipped")
        return []
    country = config.get("adzuna_country").strip() or "us"
    out, seen = [], set()
    wheres = ctx.locations or [""]
    for query in ctx.queries[:8]:
        for where in wheres[:3]:
            for page in (1, 2):
                params = {"app_id": app_id, "app_key": app_key, "what": query, "results_per_page": 50,
                          "content-type": "application/json", "max_days_old": 30, "sort_by": "date"}
                if where and where.lower() != "remote":
                    params["where"] = where
                try:
                    r = ctx.http.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}", params=params)
                    r.raise_for_status()
                except Exception as e:  # noqa: BLE001
                    ctx.log(f"adzuna '{query}' p{page}: {e}")
                    break
                results = r.json().get("results", [])
                for j in results:
                    jid = str(j.get("id"))
                    if jid in seen:
                        continue
                    seen.add(jid)
                    loc = (j.get("location") or {}).get("display_name", "")
                    out.append(Job(
                        source="adzuna", external_id=jid, title=j.get("title", ""),
                        company=(j.get("company") or {}).get("display_name", ""), url=j.get("redirect_url", ""),
                        apply_url=j.get("redirect_url", ""), location=loc, remote=looks_remote(loc, j.get("title")),
                        description=strip_html(j.get("description", "")), salary_min=j.get("salary_min"),
                        salary_max=j.get("salary_max"), posted_at=j.get("created"),
                        raw={"category": (j.get("category") or {}).get("label"), "contract_type": j.get("contract_type")},
                    ))
                if len(results) < 50:
                    break
    ctx.log(f"adzuna: {len(out)} jobs")
    return out


def fetch_jsearch(ctx: SourceContext) -> list[Job]:
    key = config.get("jsearch_key").strip()
    if not key:
        ctx.log("jsearch: no key, skipped")
        return []
    out, seen = [], set()
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
    locs = ctx.locations or [""]
    for query in ctx.queries[:6]:
        for where in locs[:2]:
            qtext = f"{query} in {where}" if where and where.lower() != "remote" else query
            params = {"query": qtext, "page": "1", "num_pages": "2", "date_posted": "month"}
            if ctx.remote_only or (where and where.lower() == "remote"):
                params["remote_jobs_only"] = "true"
            try:
                r = ctx.http.get("https://jsearch.p.rapidapi.com/search", params=params, headers=headers)
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                ctx.log(f"jsearch '{qtext}': {e}")
                continue
            for j in r.json().get("data", []) or []:
                jid = str(j.get("job_id"))
                if jid in seen:
                    continue
                seen.add(jid)
                loc = ", ".join(x for x in [j.get("job_city"), j.get("job_state"), j.get("job_country")] if x)
                apply_url = j.get("job_apply_link", "")
                # Prefer a direct ATS link when the aggregator offers several apply options.
                for opt in j.get("apply_options") or []:
                    link = opt.get("apply_link", "")
                    if re.search(r"greenhouse\.io|lever\.co|ashbyhq\.com|workable\.com", link):
                        apply_url = link
                        break
                out.append(Job(
                    source="jsearch", external_id=jid, title=j.get("job_title", ""), company=j.get("employer_name", ""),
                    url=j.get("job_apply_link", ""), apply_url=apply_url, location=loc,
                    remote=bool(j.get("job_is_remote")) or looks_remote(loc), description=j.get("job_description", "") or "",
                    salary_min=j.get("job_min_salary"), salary_max=j.get("job_max_salary"),
                    posted_at=j.get("job_posted_at_datetime_utc"),
                    raw={"publisher": j.get("job_publisher"), "employer_website": j.get("employer_website"),
                         "employment_type": j.get("job_employment_type")},
                ))
    ctx.log(f"jsearch: {len(out)} jobs")
    return out


def fetch_remotive(ctx: SourceContext) -> list[Job]:
    out, seen = [], set()
    for query in ctx.queries[:8]:
        try:
            r = ctx.http.get("https://remotive.com/api/remote-jobs", params={"search": query, "limit": 100})
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            ctx.log(f"remotive '{query}': {e}")
            continue
        for j in r.json().get("jobs", []):
            jid = str(j.get("id"))
            if jid in seen:
                continue
            seen.add(jid)
            out.append(Job(
                source="remotive", external_id=jid, title=j.get("title", ""), company=j.get("company_name", ""),
                url=j.get("url", ""), apply_url=j.get("url", ""),
                location=j.get("candidate_required_location", "") or "Remote", remote=True,
                description=strip_html(j.get("description", "")), posted_at=j.get("publication_date"),
                raw={"salary": j.get("salary"), "job_type": j.get("job_type"), "tags": j.get("tags")},
            ))
    ctx.log(f"remotive: {len(out)} jobs")
    return out


def fetch_remoteok(ctx: SourceContext) -> list[Job]:
    try:
        r = ctx.http.get("https://remoteok.com/api")
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001
        ctx.log(f"remoteok: {e}")
        return []
    out = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first element is a legal notice
        title = j.get("position", "")
        if not title_matches(title, ctx):
            continue
        epoch = j.get("epoch")
        posted = datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat() if epoch else j.get("date")
        out.append(Job(
            source="remoteok", external_id=str(j.get("id")), title=title, company=j.get("company", ""),
            url=j.get("url", ""), apply_url=j.get("apply_url") or j.get("url", ""),
            location=j.get("location", "") or "Remote", remote=True, description=strip_html(j.get("description", "")),
            salary_min=j.get("salary_min") or None, salary_max=j.get("salary_max") or None, posted_at=posted,
            raw={"tags": j.get("tags")},
        ))
    ctx.log(f"remoteok: {len(out)} jobs")
    return out


def fetch_weworkremotely(ctx: SourceContext) -> list[Job]:
    try:
        r = ctx.http.get("https://weworkremotely.com/remote-jobs.rss")
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"weworkremotely: {e}")
        return []
    out = []
    for item in root.iter("item"):
        raw_title = (item.findtext("title") or "").strip()
        # "Company: Job Title"
        company, _, title = raw_title.partition(":")
        title = title.strip() or raw_title
        if not title_matches(title, ctx):
            continue
        link = (item.findtext("link") or "").strip()
        region = (item.findtext("region") or "").strip()
        out.append(Job(
            source="weworkremotely", external_id=link or raw_title, title=title, company=company.strip(),
            url=link, apply_url=link, location=region or "Remote", remote=True,
            description=strip_html(item.findtext("description") or ""), posted_at=item.findtext("pubDate"),
            raw={"category": item.findtext("category")},
        ))
    ctx.log(f"weworkremotely: {len(out)} jobs")
    return out


REMOTE_BOARDS = [fetch_remotive, fetch_remoteok, fetch_weworkremotely]
AGGREGATORS = [fetch_adzuna, fetch_jsearch]
