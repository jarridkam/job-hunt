"""Encryption for secret settings (API keys, email password, session signing key).

The key comes from the JOBHUNT_SECRET_KEY environment variable (a Fernet key). On the server it lives in
/etc/jobhunt/secret.env, outside the data folder, so a copy of the database or a backup on its own
can't be read. With no key set (running on the PC), secrets stay plaintext as before.
"""
from __future__ import annotations

import os

PREFIX = "enc:v1:"
SECRET_KEYS = frozenset({"anthropic_api_key", "adzuna_app_key", "jsearch_key", "email_pass", "auth_secret", "vapid_private"})


def _fernet():
    key = os.environ.get("JOBHUNT_SECRET_KEY", "").strip()
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def enabled() -> bool:
    return _fernet() is not None


def seal(key: str, value: str) -> str:
    f = _fernet()
    if key not in SECRET_KEYS or not value or f is None or value.startswith(PREFIX):
        return value
    return PREFIX + f.encrypt(value.encode()).decode()


def unseal(value: str) -> str:
    if not value or not value.startswith(PREFIX):
        return value
    f = _fernet()
    if f is None:
        raise RuntimeError("A setting is encrypted but JOBHUNT_SECRET_KEY is not set.")
    return f.decrypt(value[len(PREFIX):].encode()).decode()


def new_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()
