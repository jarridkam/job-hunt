"""One-step undo for edits and deletes.

Before a change, the row as it was is stored under a short token. Restoring puts that row back exactly,
so "Undo" works for auto-saved edits in side sheets and for deletes, without a confirm dialog in the way.
A sheet session reuses its first token, so one Undo returns the row to how it was when the sheet opened.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from . import db

TABLES = {"interviews", "assessments", "applications"}
KEEP_DAYS = 7


def record(table: str, row_id: int, kind: str = "edit", token: str = "") -> str:
    """Snapshot the row before changing it. Returns the token to undo with ("" if the row is gone)."""
    if table not in TABLES:
        raise ValueError(table)
    if token and kind == "edit":
        same = db.q1("SELECT 1 FROM undo_log WHERE token=? AND tbl=? AND row_id=? AND kind='edit'", (token, table, row_id))
        if same:
            return token
    row = db.q1(f"SELECT * FROM {table} WHERE id=?", (row_id,))
    if not row:
        return ""
    token = secrets.token_urlsafe(9)
    db.insert("undo_log", {"token": token, "tbl": table, "row_id": row_id, "kind": kind,
                           "before_json": db.dumps(row), "created_at": db.now_iso()})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
    db.execute("DELETE FROM undo_log WHERE created_at < ?", (cutoff,))
    return token


def group(tokens: list[str]) -> str:
    """One token that undoes several changes at once."""
    tokens = [t for t in tokens if t]
    if not tokens:
        return ""
    token = secrets.token_urlsafe(9)
    db.insert("undo_log", {"token": token, "tbl": "group", "row_id": 0, "kind": "edit", "before_json": db.dumps(tokens), "created_at": db.now_iso()})
    return token


def restore(token: str) -> dict | None:
    """Put the row back as it was. Returns {table, row_id, kind} or None if the token is unknown or used."""
    u = db.q1("SELECT * FROM undo_log WHERE token=?", (token,))
    if u and u["tbl"] == "group":
        done = [restore(t) for t in db.loads(u["before_json"]) or []]
        db.execute("DELETE FROM undo_log WHERE token=?", (token,))
        return next((r for r in done if r), None)
    if not u or u["tbl"] not in TABLES:
        return None
    row = db.loads(u["before_json"]) or {}
    if not row:
        return None
    t = u["tbl"]
    if db.q1(f"SELECT 1 FROM {t} WHERE id=?", (u["row_id"],)):
        # UPDATE, never REPLACE: REPLACE deletes first, which would cascade to child rows.
        fields = {k: v for k, v in row.items() if k != "id"}
        db.execute(f"UPDATE {t} SET {', '.join(k + '=?' for k in fields)} WHERE id=?", (*fields.values(), u["row_id"]))
    else:
        cols = list(row.keys())
        db.execute(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", tuple(row[c] for c in cols))
    db.execute("DELETE FROM undo_log WHERE token=?", (token,))
    return {"table": u["tbl"], "row_id": u["row_id"], "kind": u["kind"]}
