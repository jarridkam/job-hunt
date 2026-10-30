"""Heuristic legitimacy score (0-100) for a posting. Cheap, no LLM.
The LLM fit pass adds red_flags on top; both feed the final decision."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .sources.base import detect_ats, domain

SCAM = [
    r"pay(?:ment)? (?:for|to) (?:training|apply|start|background)", r"registration fee", r"processing fee",
    r"wire transfer", r"western union", r"gift ?cards?", r"\btelegram\b", r"whats ?app (?:only|me|us)",
    r"text (?:me|us) at \+?\d", r"earn \$?\d{3,}[ ,]?\d* ?(?:per|a|/) ?(?:day|week)\b", r"no experience (?:needed|necessary|required)[^.]{0,60}\$",
    r"crypto(?:currency)? (?:trading|investment)", r"reship", r"package (?:handler|processing) from home",
    r"mystery shopper", r"personal assistant[^.]{0,80}(?:check|cheque)", r"upfront (?:cost|payment|investment)",
    r"work ?from ?home[^.]{0,40}\$\d{2,}/?(?:hr|hour)", r"send (?:your|a copy of your) (?:ssn|social security|passport|driver)",
    r"interview (?:via|on|over) (?:telegram|whatsapp|signal|google hangouts|text)",
]
SPAM_TITLE = [r"urgent(?:ly)? hiring", r"immediate start!+", r"!!+", r"\$\$+", r"work from home.{0,20}\$", r"hiring now"]
STAFFING = [r"\bstaffing\b", r"\brecruit(?:ing|ers?|ment)\b", r"\btalent\b", r"\bconsult(?:ing|ants?)\b", r"\bsolutions\b inc", r"\bplacement"]
GENERIC_MAIL = re.compile(r"[\w.+-]+@(?:gmail|yahoo|hotmail|outlook|aol|proton|icloud)\.com", re.I)


def _age_days(posted_at: str | None) -> float | None:
    if not posted_at:
        return None
    s = str(posted_at).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return None


def score(job: dict) -> tuple[int, list[str]]:
    """job: dict with title, company, description, apply_url, url, posted_at, salary_min, salary_max, source, location."""
    s, why = 50, []
    title = (job.get("title") or "")
    desc = (job.get("description") or "")
    blob = f"{title}\n{desc}".lower()
    company = (job.get("company") or "").strip()

    ats = detect_ats(job.get("apply_url")) or detect_ats(job.get("url"))
    if not ats and job.get("source") in ("greenhouse", "lever", "ashby", "workable"):
        ats = (job["source"], "")   # came straight from its API; big companies link these from their own domain
    if ats:
        s += 25
        why.append(f"+25 hosted on {ats[0]}")
    elif job.get("source") == "board":
        s += 20
        why.append("+20 from a job board you trust")
    elif job.get("source") in ("remotive", "weworkremotely", "remoteok"):
        s += 8
        why.append("+8 curated remote board")

    n = len(desc)
    if n > 1500:
        s += 15; why.append("+15 detailed description")
    elif n > 600:
        s += 8; why.append("+8 reasonable description")
    elif n < 200:
        s -= 15; why.append("-15 very short description")

    if not company:
        s -= 20; why.append("-20 no company name")
    elif any(re.search(p, company.lower()) for p in STAFFING):
        s -= 8; why.append("-8 staffing/recruiting firm")

    age = _age_days(job.get("posted_at"))
    if age is not None:
        if age <= 14:
            s += 10; why.append("+10 posted in last 2 weeks")
        elif age <= 45:
            s += 4; why.append("+4 posted in last 45 days")
        else:
            s -= 10; why.append(f"-10 stale ({int(age)} days)")

    if job.get("location") or job.get("remote"):
        s += 5; why.append("+5 location given")

    hits = [p for p in SCAM if re.search(p, blob)]
    if hits:
        s -= 40; why.append(f"-40 scam language: {hits[0]}")
    if any(re.search(p, title.lower()) for p in SPAM_TITLE):
        s -= 15; why.append("-15 spammy title")
    if GENERIC_MAIL.search(desc):
        s -= 12; why.append("-12 contact via free email domain")

    smin, smax = job.get("salary_min") or 0, job.get("salary_max") or 0
    if smax and smax > 600_000:
        s -= 15; why.append("-15 implausible salary")
    if smin and smax and smin > smax:
        s -= 5; why.append("-5 inconsistent salary")

    d = domain(job.get("apply_url"))
    if d and re.search(r"\.(tk|ml|ga|cf|gq|xyz|top|click|work|buzz)$", d):
        s -= 20; why.append(f"-20 suspicious apply domain {d}")

    s = max(0, min(100, s))
    return s, why
