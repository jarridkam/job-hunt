"""Turn what the classifier found (explicit date, relative 'within N days', stated time zone) into a real deadline."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

# Zone abbreviations recruiters actually write. Fixed-offset abbreviations (PST vs PDT) map to the region so DST is right.
TZ_MAP: dict[str, str] = {
    "PT": "America/Los_Angeles", "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles", "PACIFIC": "America/Los_Angeles",
    "MT": "America/Denver", "MST": "America/Denver", "MDT": "America/Denver", "MOUNTAIN": "America/Denver",
    "CT": "America/Chicago", "CST": "America/Chicago", "CDT": "America/Chicago", "CENTRAL": "America/Chicago",
    "ET": "America/New_York", "EST": "America/New_York", "EDT": "America/New_York", "EASTERN": "America/New_York",
    "AKST": "America/Anchorage", "AKDT": "America/Anchorage", "HST": "Pacific/Honolulu",
    "UTC": "UTC", "GMT": "UTC", "Z": "UTC",
    "BST": "Europe/London", "IST": "Asia/Kolkata", "CET": "Europe/Berlin", "CEST": "Europe/Berlin",
    "AEST": "Australia/Sydney", "AEDT": "Australia/Sydney", "JST": "Asia/Tokyo", "SGT": "Asia/Singapore",
}


def zone_from_label(label: str) -> tzinfo | None:
    """'PST' / 'Pacific Time' / 'America/New_York' / 'UTC-5' / '+05:30' -> tzinfo, or None if unrecognised."""
    s = (label or "").strip()
    if not s:
        return None
    s = re.sub(r"\s*\(.*?\)", "", s).strip()                        # 'Pacific Time (US & Canada)' -> 'Pacific Time'
    key = re.sub(r"\s*(?:standard |daylight )?time\b", "", s, flags=re.I).strip().upper()
    for name in (TZ_MAP.get(key), s):
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001  (unknown key, or no tz database installed)
            continue
    m = re.fullmatch(r"(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?", key)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        off = timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0)) * sign
        return timezone(off)
    return None


def tz_label(dt: datetime) -> str:
    """Short label for display: 'PDT', 'UTC+05:30', ..."""
    if dt.tzinfo is None:
        return ""
    name = dt.tzname() or ""
    if name and len(name) <= 5 and not name.startswith(("UTC", "GMT")):
        return name
    if name and " " in name:   # Windows gives 'Pacific Daylight Time' for the local zone -> 'PDT'
        return "".join(w[0] for w in name.split() if w[:1].isupper())
    off = dt.utcoffset() or timedelta(0)
    if off == timedelta(0):
        return "UTC"
    sign = "+" if off >= timedelta(0) else "-"
    off = abs(off)
    hh, mm = divmod(int(off.total_seconds()) // 60, 60)
    return f"UTC{sign}{hh:02d}:{mm:02d}"


def resolve(due_at: str, due_in_days: int, due_in_hours: int, due_tz: str, received: datetime,
            default_days: int = 0) -> tuple[str | None, str, str]:
    """Returns (ISO deadline with offset or None, source, zone label).

    source: 'stated' (explicit date in the email), 'relative' (received + N days/hours),
            'assumed' (no deadline in the email; default_days after receipt), 'none'.
    The zone is the one the email names; otherwise the sender's own offset from the Date header, which is the
    best guess for "by Friday 5pm" with no zone given.
    """
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    zone = zone_from_label(due_tz) or received.tzinfo

    if due_at:
        s = due_at.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            dt = None
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=zone)
            if len(s) == 10:  # date only -> end of that day
                dt = dt.replace(hour=23, minute=59)
            return dt.isoformat(timespec="minutes"), "stated", tz_label(dt)

    hours = int(due_in_days or 0) * 24 + int(due_in_hours or 0)
    if hours > 0:
        dt = (received + timedelta(hours=hours)).astimezone(zone)
        return dt.isoformat(timespec="minutes"), "relative", tz_label(dt)

    if default_days > 0:
        dt = (received + timedelta(days=default_days)).astimezone(zone)
        return dt.isoformat(timespec="minutes"), "assumed", tz_label(dt)
    return None, "none", ""


def to_local(iso: str | None) -> datetime | None:
    """Aware datetime in this machine's zone. Naive input is treated as UTC."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def from_local_input(value: str) -> str | None:
    """datetime-local form value (naive, user's zone) -> ISO with this machine's offset."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone().isoformat(timespec="minutes")
    except ValueError:
        return None
