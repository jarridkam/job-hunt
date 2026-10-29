"""Company ATS boards with public JSON APIs: Greenhouse, Lever, Ashby, Workable.
These are the sources auto-apply works best on, and they never get an account banned."""
from __future__ import annotations

from datetime import datetime, timezone

from .base import Job, SourceContext, looks_remote, strip_html, title_matches


def _ts(ms_or_iso) -> str | None:
    if not ms_or_iso:
        return None
    if isinstance(ms_or_iso, (int, float)):
        return datetime.fromtimestamp(ms_or_iso / 1000, tz=timezone.utc).isoformat()
    return str(ms_or_iso)


def fetch_greenhouse(ctx: SourceContext, token: str, company_name: str) -> list[Job]:
    r = ctx.http.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"})
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        title = j.get("title", "")
        if not title_matches(title, ctx):
            continue
        loc = (j.get("location") or {}).get("name", "")
        desc = strip_html(j.get("content", ""))
        out.append(Job(
            source="greenhouse", external_id=f"{token}:{j['id']}", title=title, company=company_name,
            url=j.get("absolute_url", ""), apply_url=j.get("absolute_url", ""), location=loc,
            remote=looks_remote(loc, title), description=desc, posted_at=j.get("updated_at"),
            raw={"departments": [d.get("name") for d in j.get("departments", [])]},
        ))
    return out


def fetch_lever(ctx: SourceContext, token: str, company_name: str) -> list[Job]:
    r = ctx.http.get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
    r.raise_for_status()
    out = []
    for j in r.json():
        title = j.get("text", "")
        if not title_matches(title, ctx):
            continue
        cats = j.get("categories") or {}
        loc = cats.get("location", "") or ""
        desc = j.get("descriptionPlain") or strip_html(j.get("description", ""))
        for lst in j.get("lists", []) or []:
            desc += f"\n\n{lst.get('text','')}\n" + strip_html(lst.get("content", ""))
        out.append(Job(
            source="lever", external_id=f"{token}:{j['id']}", title=title, company=company_name,
            url=j.get("hostedUrl", ""), apply_url=j.get("applyUrl") or j.get("hostedUrl", ""), location=loc,
            remote=looks_remote(loc, j.get("workplaceType"), title), description=desc,
            posted_at=_ts(j.get("createdAt")), raw={"team": cats.get("team"), "commitment": cats.get("commitment")},
        ))
    return out


def fetch_ashby(ctx: SourceContext, token: str, company_name: str) -> list[Job]:
    r = ctx.http.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}", params={"includeCompensation": "true"})
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        title = j.get("title", "")
        if not title_matches(title, ctx):
            continue
        loc = j.get("location", "") or ""
        desc = j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", ""))
        comp = j.get("compensation") or {}
        smin = smax = None
        tiers = comp.get("compensationTiers") or comp.get("compensationTierSummary")
        if isinstance(tiers, list) and tiers:
            comps = tiers[0].get("components") or []
            for c in comps:
                if c.get("compensationType") == "Salary":
                    smin, smax = c.get("minValue"), c.get("maxValue")
        out.append(Job(
            source="ashby", external_id=f"{token}:{j['id']}", title=title, company=company_name,
            url=j.get("jobUrl", ""), apply_url=j.get("applyUrl") or j.get("jobUrl", ""), location=loc,
            remote=bool(j.get("isRemote")) or looks_remote(loc, title), description=desc,
            salary_min=smin, salary_max=smax, posted_at=j.get("publishedAt"),
            raw={"department": j.get("department"), "employmentType": j.get("employmentType")},
        ))
    return out


def fetch_workable(ctx: SourceContext, token: str, company_name: str) -> list[Job]:
    r = ctx.http.get(f"https://apply.workable.com/api/v1/widget/accounts/{token}", params={"details": "true"})
    r.raise_for_status()
    out = []
    data = r.json()
    for j in data.get("jobs", []):
        title = j.get("title", "")
        if not title_matches(title, ctx):
            continue
        loc = j.get("location") or {}
        loc_s = ", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x)
        desc = strip_html(j.get("description", "")) + "\n\n" + strip_html(j.get("requirements", ""))
        out.append(Job(
            source="workable", external_id=f"{token}:{j.get('shortcode') or j.get('id')}", title=title,
            company=company_name or data.get("name", ""), url=j.get("url", ""),
            apply_url=j.get("application_url") or j.get("url", ""), location=loc_s,
            remote=bool(j.get("telecommuting")) or looks_remote(loc_s, title), description=desc.strip(),
            posted_at=j.get("published_on"), raw={"department": j.get("department")},
        ))
    return out


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workable": fetch_workable,
}
