"""Resume / cover letter storage and text extraction."""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from . import db
from .paths import UPLOADS, resolve


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if suffix == ".docx":
        import docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    return path.read_text(encoding="utf-8", errors="replace")


def clean_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def save_upload(kind: str, title: str, filename: str, data: bytes, notes: str = "") -> int:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "upload"
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    dest = UPLOADS / f"{stamp}_{safe}"
    dest.write_bytes(data)
    text = clean_text(extract_text(dest))
    return add_document(kind, title or Path(filename).stem, text, file_path=str(dest), notes=notes)


def add_document(kind: str, title: str, content: str, *, file_path: str | None = None,
                 status: str = "active", source: str = "user", notes: str = "") -> int:
    now = db.now_iso()
    if kind == "resume" and status == "active":
        # Only one active resume at a time keeps "which resume do I send" unambiguous.
        db.execute("UPDATE documents SET status='archived', updated_at=? WHERE kind='resume' AND status='active'", (now,))
    return db.insert("documents", {
        "kind": kind, "title": title, "content": content, "file_path": file_path,
        "status": status, "source": source, "notes": notes, "created_at": now, "updated_at": now,
    })


def set_status(doc_id: int, status: str) -> None:
    doc = db.q1("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not doc:
        return
    now = db.now_iso()
    if doc["kind"] == "resume" and status == "active":
        db.execute("UPDATE documents SET status='archived', updated_at=? WHERE kind='resume' AND status='active'", (now,))
    db.update("documents", doc_id, {"status": status, "updated_at": now})


def active_resume() -> dict | None:
    return db.q1("SELECT * FROM documents WHERE kind='resume' AND status='active' ORDER BY updated_at DESC LIMIT 1")


def resume_file_for_upload() -> Path | None:
    r = active_resume()
    src = resolve(r.get("file_path")) if r else None
    if src:
        return src
    if r:
        # Pasted text resume: write a .txt so forms still get a file.
        p = UPLOADS / f"resume_{r['id']}.txt"
        p.write_text(r["content"], encoding="utf-8")
        return p
    return None


def voice_samples(limit: int = 5) -> list[dict]:
    """Cover letters the user wrote or approved, newest first. Active ones first, then archived."""
    rows = db.q(
        "SELECT * FROM documents WHERE kind='cover_letter' "
        "ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC LIMIT ?",
        (limit,),
    )
    return rows


def all_documents() -> list[dict]:
    return db.q("SELECT * FROM documents ORDER BY kind, CASE status WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC")


def archive_old_learned(keep: int = 12) -> None:
    rows = db.q("SELECT id FROM documents WHERE kind='cover_letter' AND source='learned' ORDER BY updated_at DESC")
    for r in rows[keep:]:
        db.execute("DELETE FROM documents WHERE id=?", (r["id"],))
