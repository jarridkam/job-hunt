"""SQLite storage. One connection per call; WAL mode; dict rows."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import secrets_box
from .paths import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,               -- resume | cover_letter
    title TEXT NOT NULL,
    content TEXT NOT NULL,            -- plain text
    file_path TEXT,                   -- original upload (used for form uploads)
    status TEXT NOT NULL DEFAULT 'active',  -- active | archived
    source TEXT NOT NULL DEFAULT 'user',    -- user | learned (approved drafts saved back)
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ats TEXT NOT NULL,                -- greenhouse | lever | ashby | workable
    board_token TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    discovered INTEGER NOT NULL DEFAULT 0,
    last_fetch_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(ats, board_token)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT,
    apply_url TEXT,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    remote INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    salary_min REAL,
    salary_max REAL,
    posted_at TEXT,
    fetched_at TEXT NOT NULL,
    ats TEXT,                         -- detected ATS of apply_url
    legit_score INTEGER,
    legit_reasons TEXT,
    fit_score INTEGER,
    fit_reasons TEXT,
    fit_missing TEXT,
    fit_summary TEXT,
    status TEXT NOT NULL DEFAULT 'new',   -- new | queued | skipped | applied | low_fit | not_legit
    raw TEXT,
    UNIQUE(source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_fit ON jobs(fit_score);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,                   -- NULL for applications discovered from email only
    company TEXT,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    -- queued | drafting | ready | applying | needs_attention | submitted | failed
    -- | screening | assessment | interview | offer | rejected | withdrawn
    cover_letter TEXT,
    cover_letter_approved INTEGER NOT NULL DEFAULT 0,
    resume_doc_id INTEGER,
    applied_at TEXT,
    last_update_at TEXT NOT NULL,
    notes TEXT,
    submit_log TEXT,
    screenshot_path TEXT,
    queue_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS application_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    happened_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'system',  -- system | email | manual
    detail TEXT,
    email_id INTEGER,
    FOREIGN KEY(application_id) REFERENCES applications(id)
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER,
    company TEXT,
    title TEXT,
    platform TEXT,
    link TEXT,
    due_at TEXT,
    est_minutes INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | completed | missed
    received_at TEXT,
    completed_at TEXT,
    email_id INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER,
    company TEXT,
    title TEXT,            -- role
    stage TEXT,            -- Recruiter screen | Technical | ...
    format TEXT,           -- phone | video | onsite | recorded
    starts_at TEXT,        -- ISO with offset, NULL until a time is set
    time_source TEXT,      -- stated | manual
    tz TEXT,
    duration_minutes INTEGER,
    link TEXT,
    location TEXT,
    interviewer TEXT,
    status TEXT NOT NULL DEFAULT 'needs_scheduling',  -- needs_scheduling | scheduled | done | cancelled | missed
    received_at TEXT,
    email_id INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL,
    uid INTEGER NOT NULL,
    from_addr TEXT,
    subject TEXT,
    received_at TEXT,
    snippet TEXT,
    classification TEXT,              -- JSON
    processed_at TEXT,
    UNIQUE(account, uid)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',  -- running | done | failed
    started_at TEXT NOT NULL,
    finished_at TEXT,
    summary TEXT,
    log TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_at ON llm_usage(at);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    to_addr TEXT NOT NULL,
    from_addr TEXT,
    subject TEXT,
    body TEXT NOT NULL,
    in_reply_to TEXT,
    message_id TEXT,
    status TEXT NOT NULL DEFAULT 'sent',   -- sent | failed
    sent_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_app ON messages(application_id);
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL UNIQUE,
    subscription TEXT NOT NULL,       -- JSON from PushManager.subscribe()
    label TEXT,
    created_at TEXT NOT NULL,
    last_ok_at TEXT,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS push_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,                -- assessment:ID | interview:ID
    step TEXT NOT NULL,               -- 72 | 24 | 3 | nodeadline | pick | manual
    sent_at TEXT NOT NULL,
    title TEXT,
    result TEXT
);
CREATE INDEX IF NOT EXISTS idx_push_log_key ON push_log(key, step);
CREATE TABLE IF NOT EXISTS push_snooze (
    key TEXT PRIMARY KEY,
    until TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


MIGRATIONS = [
    "ALTER TABLE runs ADD COLUMN warnings TEXT",                 # JSON list: things that went wrong inside a run that still finished
    "ALTER TABLE runs ADD COLUMN dismissed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE push_subscriptions ADD COLUMN last_error_at TEXT",
    "ALTER TABLE applications ADD COLUMN letter_check_json TEXT",   # fact check of the cover letter (facts.py)
    "ALTER TABLE applications ADD COLUMN letter_check_at TEXT",
    "ALTER TABLE applications ADD COLUMN cover_letter_source TEXT",  # ai | edited | you
    "ALTER TABLE emails ADD COLUMN message_id TEXT",   # for In-Reply-To when you answer from Messages
    "ALTER TABLE applications ADD COLUMN receipt_json TEXT",   # what they received: frozen JD, resume, letter, answers, why
    "ALTER TABLE emails ADD COLUMN folder TEXT",
    "ALTER TABLE applications ADD COLUMN followup_at TEXT",
    "ALTER TABLE applications ADD COLUMN followup_snooze_until TEXT",
    "ALTER TABLE applications ADD COLUMN followup_draft TEXT",
    "ALTER TABLE interviews ADD COLUMN prep_json TEXT",
    "ALTER TABLE interviews ADD COLUMN prep_at TEXT",
    "ALTER TABLE emails ADD COLUMN body TEXT",
    "ALTER TABLE assessments ADD COLUMN due_source TEXT",
    "ALTER TABLE assessments ADD COLUMN due_tz TEXT",
    "ALTER TABLE assessments ADD COLUMN opened_at TEXT",
    "ALTER TABLE emails ADD COLUMN seen INTEGER",
    "ALTER TABLE applications ADD COLUMN review_json TEXT",      # what auto-apply filled in, shown for checking
    "ALTER TABLE applications ADD COLUMN review_decision TEXT",  # set by the review page: approve/cancel + edits
]


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        for stmt in MIGRATIONS:  # columns added after the first release; "duplicate column" means already applied
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        conn.commit()
    finally:
        conn.close()


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def q(sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    with tx() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def q1(sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    rows = q(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | dict = ()) -> int:
    with tx() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid or cur.rowcount


def insert(table: str, row: dict[str, Any]) -> int:
    cols = ", ".join(row.keys())
    marks = ", ".join("?" for _ in row)
    with tx() as conn:
        cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(row.values()))
        return cur.lastrowid


def update(table: str, row_id: int, fields: dict[str, Any]) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with tx() as conn:
        conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*fields.values(), row_id))


# ---- settings -------------------------------------------------------------

def get_setting(key: str, default: str = "") -> str:
    row = q1("SELECT value FROM settings WHERE key = ?", (key,))
    return secrets_box.unseal(row["value"]) if row and row["value"] is not None else default


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, secrets_box.seal(key, value)),
    )


def all_settings() -> dict[str, str]:
    return {r["key"]: secrets_box.unseal(r["value"]) for r in q("SELECT key, value FROM settings")}


def seal_secrets() -> int:
    """Encrypt any secret settings still stored as plaintext (first start with a key). Returns how many."""
    if not secrets_box.enabled():
        return 0
    n = 0
    for r in q("SELECT key, value FROM settings"):
        if r["key"] in secrets_box.SECRET_KEYS and r["value"] and not r["value"].startswith(secrets_box.PREFIX):
            set_setting(r["key"], r["value"]); n += 1
    return n


# ---- runs -----------------------------------------------------------------

def start_run(kind: str) -> int:
    return insert("runs", {"kind": kind, "started_at": now_iso()})


def run_log(run_id: int, line: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    execute("UPDATE runs SET log = log || ? WHERE id = ?", (f"[{stamp}] {line}\n", run_id))


def run_warn(run_id: int, line: str) -> None:
    """Log a problem that did not stop the run; it shows on Today until a later run of the same kind is clean."""
    run_log(run_id, "WARN: " + line)
    r = q1("SELECT warnings FROM runs WHERE id=?", (run_id,)) or {}
    w = loads(r.get("warnings"), []) or []
    if len(w) < 50:
        w.append(line[:300])
        update("runs", run_id, {"warnings": dumps(w)})


def finish_run(run_id: int, summary: str, failed: bool = False) -> None:
    update("runs", run_id, {"status": "failed" if failed else "done", "finished_at": now_iso(), "summary": summary})


def add_event(application_id: int, event_type: str, detail: str = "", source: str = "system",
              email_id: int | None = None, happened_at: str | None = None) -> int:
    return insert("application_events", {
        "application_id": application_id, "event_type": event_type, "detail": detail,
        "source": source, "email_id": email_id, "happened_at": happened_at or now_iso(),
    })


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def loads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default
