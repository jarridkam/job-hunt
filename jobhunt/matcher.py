"""LLM fit scoring of jobs against the active resume."""
from __future__ import annotations

import re

from . import config, db, documents, llm, work
from .models import FitScore, SearchProfile

SCORE_SYSTEM = """You are a careful, honest job-fit evaluator working for the candidate.
Score how well a job posting fits the candidate's actual background: experience, projects, skills, degree, seniority.
Be realistic: a posting that requires 8+ years for a recent graduate is a poor fit even if skills overlap.
Do not inflate scores. 85+ means they should definitely apply; 65-84 worth applying; below 50 skip.
Also note any red flags that suggest the posting is not a legitimate job (pay-to-apply, vague company, crypto/wire transfer, unrealistic pay).
Write 'summary' to the candidate in second person, plainly."""

PROFILE_SYSTEM = """You help a job seeker decide what to search for. From the resume, produce job titles they are realistically qualified for right now
(include common synonyms used by employers), useful search keywords, and their seniority level."""


def resume_block() -> str:
    r = documents.active_resume()
    if not r:
        raise llm.LLMError("No active resume. Add one under Documents.")
    cand = config.candidate()
    extra = f"\n\nAdditional profile facts:\n{cand.as_prompt()}" if cand.full_name else ""
    projects = work.block()
    return f"CANDIDATE RESUME:\n{r['content']}{extra}" + (f"\n\n{projects}" if projects else "")


def suggest_search_profile() -> SearchProfile:
    return llm.extract(PROFILE_SYSTEM, resume_block(), SearchProfile, model=config.get("model_main"), effort="medium", purpose="suggest titles")


def _job_block(job: dict) -> str:
    desc = (job.get("description") or "")[:12000]
    sal = ""
    if job.get("salary_min") or job.get("salary_max"):
        sal = f"\nSalary: {job.get('salary_min')} - {job.get('salary_max')}"
    return (f"JOB POSTING\nTitle: {job['title']}\nCompany: {job.get('company')}\nLocation: {job.get('location')} "
            f"(remote: {'yes' if job.get('remote') else 'no'}){sal}\nSource: {job.get('source')}\n\n{desc}")


def score_job(job: dict, resume_text: str | None = None) -> FitScore:
    rb = resume_text or resume_block()
    user = f"{rb}\n\n{_job_block(job)}\n\nEvaluate the fit."
    return llm.extract(SCORE_SYSTEM, user, FitScore, model=config.get("model_fast"), effort="low", purpose="score job")


def excluded_title(title: str) -> bool:
    t = title.lower()
    return any(x.lower() in t for x in config.get_lines("exclude_keywords"))


def prefilter_title(title: str) -> bool:
    """True if the title loosely matches any target title (word overlap >= 60%)."""
    wanted = config.get_lines("search_titles")
    if not wanted:
        return True
    t = set(re.findall(r"[a-z0-9+#.]+", title.lower()))
    for w in wanted:
        ws = set(re.findall(r"[a-z0-9+#.]+", w.lower())) - {"and", "or", "of", "the", "a"}
        if not ws:
            continue
        if len(ws & t) / len(ws) >= 0.6:
            return True
    return False


def score_pending(run_id: int, limit: int | None = None) -> dict:
    """Score unscored jobs that passed the legit threshold and the title prefilter."""
    limit = limit or config.get_int("max_llm_scores_per_run", 150)
    min_legit = config.get_int("min_legit_score", 55)
    min_fit = config.get_int("min_fit_score", 65)
    auto_q = config.get_int("auto_queue_score", 80)
    rb = resume_block()
    rows = db.q("SELECT * FROM jobs WHERE fit_score IS NULL AND status='new' AND legit_score >= ? "
                "ORDER BY posted_at DESC, id DESC", (min_legit,))
    scored = skipped = queued = 0
    for job in rows:
        if scored >= limit:
            db.run_log(run_id, f"score: hit per-run limit {limit}; remaining jobs stay unscored")
            break
        if excluded_title(job["title"]) or not prefilter_title(job["title"]):
            db.update("jobs", job["id"], {"status": "low_fit", "fit_score": 0, "fit_summary": "Title outside target titles."})
            skipped += 1
            continue
        try:
            fs = score_job(job, rb)
        except Exception as e:  # noqa: BLE001
            db.run_warn(run_id, f"couldn't score {job['title']} at {job.get('company')}: {e}")
            low = str(e).lower()
            if "credit" in low or "api key" in low or "authentication" in low:
                raise   # every job will fail the same way: stop and say so once
            continue
        scored += 1
        fit = max(0, min(100, fs.fit_score))
        if not fs.seniority_ok:
            fit = min(fit, 45)
        fields = {
            "fit_score": fit, "fit_summary": fs.summary, "fit_reasons": db.dumps(fs.matching_points),
            "fit_missing": db.dumps(fs.missing),
        }
        if fs.red_flags:
            legit = max(0, (job.get("legit_score") or 50) - 15 * len(fs.red_flags))
            why = db.loads(job.get("legit_reasons"), []) + [f"-15 LLM flag: {f}" for f in fs.red_flags]
            fields.update({"legit_score": legit, "legit_reasons": db.dumps(why)})
            if legit < min_legit:
                fields["status"] = "not_legit"
        if fields.get("status") != "not_legit":
            if fit < min_fit:
                fields["status"] = "low_fit"
            elif auto_q and fit >= auto_q:
                fields["status"] = "queued"
        db.update("jobs", job["id"], fields)
        if fields.get("status") == "queued":
            from .queue import enqueue  # local import to avoid cycle
            enqueue(job["id"])
            queued += 1
        db.run_log(run_id, f"scored {fit:>3} {job['company']} - {job['title']}")
    if not rows:
        below = (db.q1("SELECT COUNT(*) n FROM jobs WHERE fit_score IS NULL AND status='new'") or {}).get("n", 0)
        db.run_log(run_id, "nothing to score" + (f" ({below} unscored jobs are below min legitimacy score {min_legit})" if below else ""))
    elif scored == 0:
        db.run_log(run_id, f"WARNING: every one of {len(rows)} jobs was dropped by the title / exclude filters, "
                           "no LLM scoring happened. Widen 'Target job titles' or trim 'Exclude if title contains' in Settings.")
    return {"scored": scored, "skipped": skipped, "queued": queued,
            "note": "all filtered out - check target titles" if rows and scored == 0 else ""}
