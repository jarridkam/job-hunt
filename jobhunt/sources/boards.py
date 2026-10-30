"""Company ATS boards with public JSON APIs: Greenhouse, Lever, Ashby, Workable.
These are the sources auto-apply works best on, and they never get an account banned."""
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from .base import Job, SourceContext, detect_ats, domain, looks_remote, strip_html, title_matches


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


# ---- job boards you trust: any site with an RSS or Atom feed -------------------------------------------------

HIRING = re.compile(r"^(?P<co>.+?) is hiring (?:an? |a )?(?P<title>.+?)(?: to work from (?P<loc>.+))?$", re.I)
AT = re.compile(r"^(?P<title>.+?) (?:at|@) (?P<co>[^,]+)$")
COLON = re.compile(r"^(?P<co>[^:]{2,60}):\s+(?P<title>.+)$")
ANYWHERE = re.compile(r"anywhere|worldwide|\bglobal|±", re.I)
MAX_DETAILS = 30    # job pages opened per fetch, only for jobs that match your titles
ATOM = "{http://www.w3.org/2005/Atom}"


def _feed_items(text: str) -> list[dict]:
    """Items from RSS or Atom. Raises if the text isn't a feed."""
    root = ET.fromstring(text.lstrip("﻿ \r\n\t"))
    out = []
    for i in root.iter("item"):
        out.append({"title": i.findtext("title") or "", "link": (i.findtext("link") or "").strip(), "id": i.findtext("guid") or "",
                    "body": i.findtext("description") or "", "at": i.findtext("pubDate")})
    for e in root.iter(ATOM + "entry"):
        link = e.find(ATOM + "link")
        out.append({"title": e.findtext(ATOM + "title") or "", "link": link.get("href", "") if link is not None else "",
                    "id": e.findtext(ATOM + "id") or "", "body": e.findtext(ATOM + "summary") or e.findtext(ATOM + "content") or "",
                    "at": e.findtext(ATOM + "updated")})
    if root.tag not in ("rss", "RDF") and not root.tag.endswith(("}RDF", "}feed")):
        raise ValueError("not a feed")
    return out


def _split_title(raw: str) -> tuple[str, str, str]:
    """(title, company, location) from however the board phrases it. Unknown parts stay empty."""
    raw = " ".join(strip_html(raw).split())
    for rx in (HIRING, AT, COLON):
        m = rx.match(raw)
        if m:
            g = m.groupdict()
            return g["title"].strip(), g["co"].strip(), (g.get("loc") or "").strip()
    return raw, "", ""


def _job_page(ctx: SourceContext, url: str) -> dict:
    """The fuller description and real apply link from a job's own page. Empty if the page gives neither."""
    try:
        r = ctx.http.get(url)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return {}
    out: dict = {}
    for m in re.finditer(r'<script[^>]+ld\+json[^>]*>(.*?)</script>', r.text, re.S | re.I):
        try:
            d = json.loads(m.group(1), strict=False)
        except ValueError:
            continue
        for x in d if isinstance(d, list) else [d]:
            if isinstance(x, dict) and x.get("@type") == "JobPosting":
                out["description"] = strip_html(html.unescape(x.get("description") or ""))
                org = x.get("hiringOrganization")
                out["company"] = org.get("name", "") if isinstance(org, dict) else ""
    if not out.get("description"):   # some boards write JSON with stray quotes in it; the text is still there
        m = re.search(r'ld.json.*?"description":\s*"(.*?)",?\s*\n\s*"', r.text, re.S | re.I)
        out["description"] = strip_html(html.unescape(html.unescape(m.group(1)))) if m else ""
    links = re.findall(r'href="(https?://[^"]+)"', r.text)
    buttons = [m.group(1) for t in re.findall(r"<a\b[^>]*\bapply[^>]*>", r.text, re.I) for m in [re.search(r'href="(https?://[^"]+)"', t)] if m]
    here = domain(url)
    pick = next((h for h in links if detect_ats(h)), None) or next((h for h in buttons if domain(h) != here), None)
    if pick:
        out["apply_url"] = html.unescape(pick)
    return out


def fetch_feed(ctx: SourceContext, token: str, company_name: str) -> list[Job]:
    r = ctx.http.get(token)
    r.raise_for_status()
    out = []
    for i in _feed_items(r.text):
        title, company, loc = _split_title(i["title"])
        if not i["link"] or not title_matches(title, ctx):
            continue
        extra = _job_page(ctx, i["link"]) if len(out) < MAX_DETAILS else {}
        body = strip_html(i["body"])
        desc = extra.get("description") or body
        out.append(Job(
            source="board", external_id=i["id"] or i["link"], title=title, company=company or extra.get("company") or "", url=i["link"],
            apply_url=extra.get("apply_url") or i["link"], location=loc, remote=bool(ANYWHERE.search(loc)) or looks_remote(loc, title, desc[:300]),
            description=desc, posted_at=i["at"], raw={"board": company_name},
        ))
    return out


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workable": fetch_workable,
    "feed": fetch_feed,
}
