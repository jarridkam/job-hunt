"""Background task runner (threads) with run logging."""
from __future__ import annotations

import threading
import traceback
from typing import Callable

from . import db

_lock = threading.Lock()
_running: dict[str, int] = {}  # kind -> run_id


def is_running(kind: str) -> int | None:
    with _lock:
        return _running.get(kind)


def running() -> dict[str, int]:
    with _lock:
        return dict(_running)


def start(kind: str, fn: Callable[[int], object], *, exclusive: bool = True) -> int | None:
    """Run fn(run_id) in a thread. Returns run_id, or None if an exclusive run of this kind is active."""
    with _lock:
        if exclusive and kind in _running:
            return None
        run_id = db.start_run(kind)
        _running[kind] = run_id

    def _go():
        try:
            result = fn(run_id)
            db.finish_run(run_id, str(result) if result is not None else "ok")
        except Exception as e:  # noqa: BLE001
            db.run_log(run_id, "FAILED: " + "".join(traceback.format_exception_only(type(e), e)).strip())
            db.run_log(run_id, traceback.format_exc()[-1500:])
            db.finish_run(run_id, f"failed: {e}", failed=True)
        finally:
            with _lock:
                if _running.get(kind) == run_id:
                    _running.pop(kind, None)

    threading.Thread(target=_go, name=f"jobhunt-{kind}", daemon=True).start()
    return run_id


# ---- task bodies ------------------------------------------------------------

def fetch_task(run_id: int):
    from .pipeline import fetch_all
    return fetch_all(run_id)


def score_task(run_id: int):
    from .matcher import score_pending
    return score_pending(run_id)


def fetch_and_score_task(run_id: int):
    from .matcher import score_pending
    from .pipeline import fetch_all
    a = fetch_all(run_id)
    b = score_pending(run_id)
    return {"fetch": a, "score": b}


def email_task(run_id: int, days: int | None = None):
    from .email_tracker import sync
    return sync(run_id, days)


def reclassify_task(run_id: int):
    from .email_tracker import reclassify_assessment_emails
    return reclassify_assessment_emails(run_id)


def followup_task(app_id: int):
    def _run(run_id: int):
        from . import followup
        note = followup.draft(app_id)
        return f"drafted: {note.subject}"
    return _run


def prep_task(iid: int):
    def _run(run_id: int):
        from . import prep
        card = prep.build(iid)
        return f"prep card: {len(card.likely_questions)} questions"
    return _run


def draft_task(app_id: int, instruction: str = ""):
    def _run(run_id: int):
        from . import queue, writer
        app = queue.with_job(app_id)
        if not app or not app.get("job"):
            raise RuntimeError("application/job not found")
        before = app.get("status") or "queued"
        db.update("applications", app_id, {"status": "drafting", "last_update_at": db.now_iso()})
        try:
            text = writer.draft(app["job"], instruction=instruction, previous=app.get("cover_letter") or "")
        except Exception:
            db.update("applications", app_id, {"status": before if before != "drafting" else ("ready" if app.get("cover_letter") else "queued"),
                                               "last_update_at": db.now_iso()})
            raise
        db.update("applications", app_id, {"cover_letter": text, "cover_letter_approved": 0, "status": "ready",
                                           "cover_letter_source": "ai", "letter_check_json": None, "letter_check_at": None,
                                           "last_update_at": db.now_iso()})
        db.add_event(app_id, "drafted", "Cover letter drafted" + (f" (revision: {instruction[:80]})" if instruction else ""))
        try:
            from .facts import check_letter
            s = check_letter(app_id)
            db.run_log(run_id, f"fact check: {s['ok']}/{s['n']} claims supported" + (f", {len(s['flagged'])} flagged" if s["flagged"] else ""))
        except Exception as e:  # noqa: BLE001
            db.run_log(run_id, f"fact check skipped: {e}")
        return f"drafted {len(text.split())} words"
    return _run


def draft_all_task(run_id: int):
    from . import queue, writer
    n = 0
    for app in queue.queued():
        if app["status"] != "queued" or app.get("cover_letter"):
            continue
        full = queue.with_job(app["id"])
        if not full or not full.get("job"):
            continue
        try:
            text = writer.draft(full["job"])
        except Exception as e:  # noqa: BLE001
            db.run_warn(run_id, f"letter for {app.get('title')} at {app.get('company')} failed: {e}")
            continue
        db.update("applications", app["id"], {"cover_letter": text, "status": "ready", "last_update_at": db.now_iso()})
        db.add_event(app["id"], "drafted", "Cover letter drafted (batch)")
        db.run_log(run_id, f"drafted #{app['id']} {app.get('company')} - {app.get('title')}")
        n += 1
    return f"drafted {n}"


def apply_task(app_id: int):
    def _run(run_id: int):
        from .apply import apply_to
        from .messages import friendly_error
        from . import queue
        try:
            res = apply_to(app_id, run_id)
        except Exception as e:
            # Before or during the browser: say so on the application instead of leaving it "applying".
            queue.set_status(app_id, "needs_attention", "Auto-apply couldn't start: " + friendly_error(e), source="system")
            raise
        if res.closed:
            return "job closed, removed it"
        return "submitted" if res.submitted else "needs attention"
    return _run
