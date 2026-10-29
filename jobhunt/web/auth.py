"""Password login for the web UI.

One password (no usernames). The hash and a signing secret live in the settings table. A session is a
signed cookie "<expiry>.<sig>"; the signature covers the password hash, so changing the password logs
every device out. Until a password is set, only a direct request from this PC may open the UI (to set
one); requests arriving through a tunnel are refused.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import Request

from .. import db

COOKIE = "jh_session"
SESSION_DAYS = 30
PBKDF2_ROUNDS = 600_000
MAX_FAILS, LOCK_SECONDS = 5, 15 * 60
OPEN_PATHS = ("/login", "/static/", "/favicon.ico", "/calendar.ics", "/sw.js")
_TUNNEL_HEADERS = ("cf-connecting-ip", "x-forwarded-for", "x-forwarded-host", "tailscale-user-login", "forwarded")

_fails: dict[str, list[float]] = {}


def _secret() -> bytes:
    s = db.get_setting("auth_secret", "")
    if not s:
        s = secrets.token_hex(32)
        db.set_setting("auth_secret", s)
    return bytes.fromhex(s)


def password_set() -> bool:
    return bool(db.get_setting("auth_password_hash", ""))


def set_password(pw: str) -> None:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
    db.set_setting("auth_password_hash", f"pbkdf2${PBKDF2_ROUNDS}${salt}${h}")


def check_password(pw: str) -> bool:
    stored = db.get_setting("auth_password_hash", "")
    try:
        _, rounds, salt, h = stored.split("$")
    except ValueError:
        return False
    got = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(rounds)).hex()
    return hmac.compare_digest(got, h)


def _sign(expiry: int) -> str:
    msg = f"{expiry}|{db.get_setting('auth_password_hash', '')}".encode()
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()


def new_session() -> str:
    expiry = int(time.time()) + SESSION_DAYS * 86400
    return f"{expiry}.{_sign(expiry)}"


RENEW_BELOW_DAYS = 15


def needs_renewal(token: str | None) -> bool:
    """A valid session past its halfway point gets a fresh cookie, so anyone who uses jobhunt at least
    every couple of weeks is never logged out, and never mid-edit."""
    try:
        return int(str(token).split(".", 1)[0]) - time.time() < RENEW_BELOW_DAYS * 86400
    except ValueError:
        return False


def set_cookie(response, request: Request) -> None:
    response.set_cookie(COOKIE, new_session(), max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=is_https(request))


def valid_session(token: str | None) -> bool:
    if not token or "." not in token or not password_set():
        return False
    exp, sig = token.split(".", 1)
    if not exp.isdigit() or int(exp) < time.time():
        return False
    return hmac.compare_digest(sig, _sign(int(exp)))


def is_local(request: Request) -> bool:
    """A direct request from this PC: loopback client and no proxy/tunnel headers."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1") and not any(h in request.headers for h in _TUNNEL_HEADERS)


def client_ip(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


def locked_out(ip: str) -> bool:
    now = time.time()
    _fails[ip] = [t for t in _fails.get(ip, []) if now - t < LOCK_SECONDS]
    return len(_fails[ip]) >= MAX_FAILS


def record_fail(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.time())


def clear_fails(ip: str) -> None:
    _fails.pop(ip, None)


def is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"
