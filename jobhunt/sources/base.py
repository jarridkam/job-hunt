from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jobhunt/0.1 (personal job search tool)"


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    apply_url: str
    location: str = ""
    remote: bool = False
    description: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    posted_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceContext:
    titles: list[str]
    keywords: list[str]
    locations: list[str]
    remote_only: bool
    log: Callable[[str], None]
    http: httpx.Client

    @property
    def queries(self) -> list[str]:
        seen, out = set(), []
        for t in self.titles + self.keywords:
            k = t.lower().strip()
            if k and k not in seen:
                seen.add(k)
                out.append(t.strip())
        return out


def make_http() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA, "Accept": "application/json, text/html;q=0.8, */*;q=0.5"},
                        timeout=30.0, follow_redirects=True)


_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", re.I)


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = _BR.sub("\n", s)
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


ATS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)\.greenhouse\.io/([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board\?(?:.*&)?for=([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)", re.I)),
    ("workable", re.compile(r"([A-Za-z0-9_-]+)\.workable\.com", re.I)),
]


def detect_ats(url: str | None) -> tuple[str, str] | None:
    """Return (ats, board_token) if the URL is hosted on a supported ATS."""
    if not url:
        return None
    for ats, pat in ATS_PATTERNS:
        m = pat.search(url)
        if m:
            token = m.group(1)
            if ats == "workable" and token in ("apply", "www", "jobs"):
                continue
            return ats, token
    return None


def domain(url: str | None) -> str:
    try:
        return urlparse(url or "").netloc.lower()
    except Exception:
        return ""


def looks_remote(*parts: str | None) -> bool:
    blob = " ".join(p or "" for p in parts).lower()
    return bool(re.search(r"\bremote\b|work from home|\bwfh\b|anywhere", blob))


def title_matches(title: str, ctx: SourceContext) -> bool:
    """Cheap filter for board sources that list every opening in a company."""
    t = title.lower()
    for want in ctx.titles:
        w = want.lower().strip()
        if not w:
            continue
        # all significant words of the wanted title appear in the job title
        words = [x for x in re.split(r"[^a-z0-9+#.]+", w) if len(x) > 1]
        if words and all(x in t for x in words):
            return True
    return False
