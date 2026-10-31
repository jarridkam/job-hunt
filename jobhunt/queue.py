"""Application queue operations."""
from __future__ import annotations

from . import db


def enqueue(job_id: int) -> int:
    existing = db.q1("SELECT id FROM applications WHERE job_id=?", (job_id,))
    if existing:
        return existing["id"]
    job = db.q1("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        raise ValueError("job not found")
    now = db.now_iso()
    order = (db.q1("SELECT COALESCE(MAX(queue_order),0) AS m FROM applications") or {}).get("m", 0) + 1
    app_id = db.insert("applications", {
        "job_id": job_id, "company": job.get("company"), "title": job["title"], "status": "queued",
        "last_update_at": now, "created_at": now, "queue_order": order,
    })
    db.update("jobs", job_id, {"status": "queued", "decided_at": now})
    db.add_event(app_id, "queued", "Added to apply queue")
    return app_id


def skip_job(job_id: int) -> None:
    db.update("jobs", job_id, {"status": "skipped", "decided_at": db.now_iso()})
    app = db.q1("SELECT id FROM applications WHERE job_id=? AND status IN ('queued','drafting','ready')", (job_id,))
    if app:
        set_status(app["id"], "withdrawn", "Skipped by user")


def remove(app_id: int, job_status: str = "new") -> dict | None:
    """Delete an application and its events; the job goes back to `job_status` ('new', 'skipped' or 'closed'). Returns the deleted row."""
    a = db.q1("SELECT job_id, status FROM applications WHERE id=?", (app_id,))
    db.execute("DELETE FROM application_events WHERE application_id=?", (app_id,))
    db.execute("UPDATE assessments SET application_id=NULL WHERE application_id=?", (app_id,))
    db.execute("UPDATE interviews SET application_id=NULL WHERE application_id=?", (app_id,))
    db.execute("DELETE FROM messages WHERE application_id=?", (app_id,))
    db.execute("DELETE FROM applications WHERE id=?", (app_id,))
    if a and a.get("job_id"):
        db.update("jobs", a["job_id"], {"status": job_status if job_status in ("new", "skipped", "closed") else "new"})
    return a


def set_status(app_id: int, status: str, detail: str = "", source: str = "manual") -> None:
    fields = {"status": status, "last_update_at": db.now_iso()}
    if status == "submitted":
        fields["applied_at"] = db.now_iso()
    db.update("applications", app_id, fields)
    db.add_event(app_id, status, detail, source=source)
    if status == "submitted":
        from . import receipts   # local import: receipts reads documents, which imports queue indirectly
        receipts.snapshot(app_id, "auto" if source == "system" else "manual")
    app = db.q1("SELECT job_id FROM applications WHERE id=?", (app_id,))
    if app and app.get("job_id"):
        if status in ("submitted", "screening", "assessment", "interview", "offer"):
            db.update("jobs", app["job_id"], {"status": "applied"})
        elif status in ("withdrawn",):
            db.update("jobs", app["job_id"], {"status": "skipped"})


def queued(limit: int | None = None) -> list[dict]:
    sql = ("SELECT a.*, j.url, j.apply_url, j.fit_score, j.legit_score, j.location, j.ats, j.fit_summary, j.fit_reasons, j.fit_missing, "
           "j.legit_reasons FROM applications a "
           "LEFT JOIN jobs j ON j.id=a.job_id WHERE a.status IN ('queued','drafting','ready','applying','review','needs_attention','failed') "
           "ORDER BY CASE a.status WHEN 'review' THEN 0 WHEN 'needs_attention' THEN 1 WHEN 'ready' THEN 2 WHEN 'drafting' THEN 3 ELSE 4 END, "
           "j.fit_score DESC, a.queue_order")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return db.q(sql)


def with_job(app_id: int) -> dict | None:
    app = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not app:
        return None
    app["job"] = db.q1("SELECT * FROM jobs WHERE id=?", (app["job_id"],)) if app.get("job_id") else None
    app["events"] = db.q("SELECT * FROM application_events WHERE application_id=? ORDER BY happened_at DESC", (app_id,))
    app["assessments"] = db.q("SELECT * FROM assessments WHERE application_id=? ORDER BY due_at", (app_id,))
    app["interviews"] = db.q("SELECT * FROM interviews WHERE application_id=? ORDER BY COALESCE(starts_at, received_at)", (app_id,))
    return app
