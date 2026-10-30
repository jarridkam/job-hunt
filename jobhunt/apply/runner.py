"""Playwright-driven application filling and submission.

Flow: open apply page -> pick the frame that holds the form -> discover fields -> fill from
profile -> LLM answers leftover required questions from the resume/profile (UNKNOWN => hand off)
-> upload resume + cover letter -> submit (if auto_submit) -> verify success text -> screenshot.
If anything is unresolved the browser stays open for up to `handoff_minutes` so the user can
finish (captcha, odd question); success is still detected and recorded.
"""
from __future__ import annotations

import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from .. import config, db, documents, llm, queue, work
from ..models import FormAnswers
from ..paths import BROWSER_PROFILE, SCREENSHOTS, UPLOADS
from ..sources.base import detect_ats
from .fields import COLLECT_JS, Field, classify

SUCCESS = re.compile(
    r"thank you for (?:applying|your application|submitting)|application (?:has been |was )?(?:submitted|received|sent)|"
    r"we(?:'ve| have) received your application|your application (?:is|was) (?:complete|successful)|successfully (?:submitted|applied)|"
    r"application submitted|you(?:'ve| have) applied|thanks for applying", re.I)

ANSWER_SYSTEM = """You fill in job application form questions on behalf of the candidate using ONLY the profile, resume and projects provided.
For each question return the exact text to enter. If options are listed, return one option verbatim.
Yes/no questions: answer from the profile.
NEVER answer questions about work authorization, citizenship, visa or sponsorship, salary or compensation, age or date of birth,
gender, race, ethnicity, veteran or disability status, criminal history, security clearance, or drug testing: return UNKNOWN for
those even if the profile seems to cover them; the candidate answers them personally.
For "how did you hear about us" pick an option like "Job board", "Other", "LinkedIn", or "Company website" in that order of preference.
For demographic / EEO questions (gender, race, veteran, disability) choose the option that declines to answer if one exists, otherwise UNKNOWN.
For free-text questions (why this company, describe a project, etc.) write 2-5 sincere sentences in the candidate's first-person voice using facts from the resume and projects only.
If the information truly is not available, return UNKNOWN. Never invent facts."""

DECLINE = [re.compile(r"decline|prefer not|don't wish|do not wish|rather not|choose not|not to (?:say|answer|disclose)", re.I)]
HEAR = [re.compile(r"job board", re.I), re.compile(r"^other", re.I), re.compile(r"linkedin", re.I), re.compile(r"website|careers page", re.I)]
YES = [re.compile(r"^yes\b", re.I)]
# Questions the AI must never answer on its own: these come from an explicit profile value or wait for you.
COMPLIANCE_Q = re.compile(r"authori[sz]ed|legally|citizen|visa|sponsor|salary|compensation|pay (?:rate|range|expect)|date of birth|"
                          r"\bage\b|gender|race|ethnic|hispanic|veteran|disabilit|criminal|convict|felony|clearance|drug", re.I)
COMPLIANCE_KEYS = ("work_auth", "sponsorship", "salary", "eeo")
NO = [re.compile(r"^no\b", re.I)]


class ApplyResult:
    def __init__(self):
        self.log: list[str] = []
        self.unresolved: list[str] = []
        self.submitted = False
        self.cancelled = False
        self.screenshot: str | None = None
        self.review: dict[int, dict] = {}     # field idx -> what was put in it, for the review screen
        self.fields: dict[int, Field] = {}

    def note(self, f: Field, value: str, source: str):
        """source: profile | standard | letter | file | ai | missing | you"""
        self.fields[f.idx] = f
        label = f.display.split(" | ")[0] if f.kind == "file" else f.display
        self.review[f.idx] = {"idx": f.idx, "label": label, "value": value, "source": source, "kind": f.kind,
                              "options": f.options[:60], "required": f.required}

    def add(self, s: str):
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {s}")


def _apply_url(job: dict) -> str:
    url = job.get("apply_url") or job.get("url") or ""
    d = detect_ats(url) or detect_ats(job.get("url"))
    ats = d[0] if d else (job.get("ats") or "")
    if ats == "greenhouse" and d:
        # The embed form URL renders the application directly, even when the company
        # redirects its job page to its own careers site.
        m = re.search(r"/jobs/(\d+)|gh_jid=(\d+)|token=(\d+)", url + " " + (job.get("url") or ""))
        gh_id = next((g for g in (m.groups() if m else ()) if g), None)
        if not gh_id and job.get("source") == "greenhouse":
            gh_id = str(job.get("external_id", "")).split(":")[-1]
        if gh_id:
            return f"https://job-boards.greenhouse.io/embed/job_app?for={d[1]}&token={gh_id}"
    if ats == "lever" and not re.search(r"/apply/?$", url):
        url = url.rstrip("/") + "/apply"
    if ats == "ashby" and not re.search(r"/application/?$", url):
        url = url.rstrip("/") + "/application"
    return url


def _upload_dir(app_id: int) -> Path:
    d = UPLOADS / f"app_{app_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _human_stem(suffix: str) -> str:
    """e.g. 'Jarrid_Kamphenel_Resume'. Uploaded files carry their name to the employer, so no timestamps or ids."""
    cand = config.candidate()
    name = re.sub(r"[^A-Za-z0-9]+", "_", f"{cand.first_name} {cand.last_name}".strip()).strip("_") or "Candidate"
    return f"{name}_{suffix}"


def _resume_file(app_id: int, src: Path) -> Path:
    dst = _upload_dir(app_id) / f"{_human_stem('Resume')}{src.suffix.lower()}"
    shutil.copyfile(src, dst)
    return dst


def _letter_file(app_id: int, text: str) -> Path:
    """Cover letter as a normal Word document (a bare .txt named by id looks automated)."""
    from docx import Document
    from docx.shared import Inches, Pt
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Inches(1)
    st = doc.styles["Normal"]
    st.font.name = "Calibri"; st.font.size = Pt(11)
    st.paragraph_format.space_after = Pt(10)
    for para in re.split(r"\n\s*\n", text.strip()):
        doc.add_paragraph(para.strip())
    p = _upload_dir(app_id) / f"{_human_stem('Cover_Letter')}.docx"
    doc.save(p)
    return p


def _best_frame(page):
    """The frame with the most form controls (the form may live in an iframe)."""
    best, best_n = page.main_frame, -1
    for fr in page.frames:
        try:
            n = fr.locator("input:not([type=hidden]), textarea, select").count()
        except Exception:  # noqa: BLE001
            continue
        if n > best_n:
            best, best_n = fr, n
    return best


def _collect(frame) -> list[Field]:
    return [Field(**r) for r in frame.evaluate(COLLECT_JS)]


def _combobox_options(frame, f: Field) -> list[str]:
    """Open a custom dropdown (react-select etc.) and read its options, then close it."""
    loc = frame.locator(f.selector).first
    try:
        loc.click()
        time.sleep(0.5)
        opts = [t.strip() for t in frame.locator('[role="option"]:visible').all_inner_texts() if t.strip()]
        loc.press("Escape")
        return opts[:80]
    except Exception:  # noqa: BLE001
        return []


def _match_option(texts: list[str], value: str) -> int | None:
    """Index of the option matching value: exact first, then word-boundary, then containment for longer values."""
    v = value.strip().lower()
    for i, t in enumerate(texts):
        if t.strip().lower() == v:
            return i
    pat = re.compile(r"(?<![a-z0-9])" + re.escape(v) + r"(?![a-z0-9])", re.I)
    for i, t in enumerate(texts):
        if pat.search(t):
            return i
    if len(v) >= 4:
        for i, t in enumerate(texts):
            if v in t.lower() or t.lower() in v:
                return i
    return None


def _fill_text(frame, f: Field, value: str, res: ApplyResult, first_ok: bool = False) -> bool:
    """first_ok: for typeahead fields (city/location), accept the first suggestion when nothing matches exactly."""
    loc = frame.locator(f.selector).first
    try:
        if f.kind == "combobox":
            loc.click()
            try:
                loc.fill("")
            except Exception:  # noqa: BLE001
                pass
            loc.type(value[:40], delay=15)
            time.sleep(0.7)
            options = frame.locator('[role="option"]:visible')
            texts = [t.strip() for t in options.all_inner_texts()]
            pick = _match_option(texts, value)
            if pick is None and texts == []:
                # typing filtered everything out; reopen and search the full list
                loc.fill("")
                time.sleep(0.4)
                options = frame.locator('[role="option"]:visible')
                texts = [t.strip() for t in options.all_inner_texts()]
                pick = _match_option(texts, value)
            if pick is None and first_ok and texts:
                pick = 0
            if pick is None:
                loc.press("Escape")
                res.add(f"no dropdown option matched {value[:40]!r} for '{f.display}'")
                return False
            options.nth(pick).click()
        elif f.kind == "select":
            pick = _match_option(f.options, value)
            if pick is None:
                return False
            loc.select_option(label=f.options[pick])
        elif f.kind in ("checkbox", "radio"):
            loc.check(force=True)
        else:
            loc.fill(value)
        res.add(f"filled '{f.display}' <- {value[:60]!r}")
        return True
    except Exception as e:  # noqa: BLE001
        res.add(f"could not fill '{f.display}': {str(e)[:120]}")
        return False


def _check_in_group(frame, f: Field, value: str, res: ApplyResult) -> bool:
    """Tick the radio/checkbox in f's group whose label matches value."""
    try:
        group = frame.locator(f.group_selector)
        n = group.count()
        labels = []
        for i in range(n):
            labels.append(group.nth(i).evaluate("""el => { const l = el.closest('label') || (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)); return l ? l.innerText.trim() : (el.value || ''); }"""))
        pick = _match_option(labels, value)
        if pick is None:
            return False
        group.nth(pick).check(force=True)
        res.add(f"chose '{labels[pick][:40]}' for '{f.display}'")
        return True
    except Exception as e:  # noqa: BLE001
        res.add(f"group '{f.display}' failed: {str(e)[:100]}")
        return False


def _degree_option(options: list[str], degree_text: str) -> str | None:
    d = degree_text.lower()
    ladder = [(r"ph\.?d|doctor", r"doctor|ph\.?d"), (r"\bm\.?s\.?\b|master|mba|m\.?eng", r"master"),
              (r"\bb\.?[sa]\.?\b|bachelor|b\.?eng|bsc|ba\b", r"bachelor"), (r"associate|a\.?[as]\.?\b", r"associate"),
              (r"high school|diploma|ged", r"high school|secondary")]
    for mine, theirs in ladder:
        if re.search(mine, d):
            return _choose_option(options, [re.compile(theirs, re.I)])
    return None


# Which EEO sub-question a field is, and how each configured answer appears on real forms (Greenhouse, Lever,
# Workday wordings). Checked in order; 'hispanic' must come before 'race' because its label mentions ethnicity.
EEO_KINDS: list[tuple[str, re.Pattern, str]] = [
    ("hispanic", re.compile(r"hispanic|latino", re.I), "cand_eeo_hispanic"),
    ("veteran", re.compile(r"veteran|military", re.I), "cand_eeo_veteran"),
    ("disability", re.compile(r"disabilit", re.I), "cand_eeo_disability"),
    ("gender", re.compile(r"gender|\bsex\b|transgender", re.I), "cand_eeo_gender"),
    ("race", re.compile(r"race|ethnic", re.I), "cand_eeo_race"),
]
EEO_SYNONYMS: dict[tuple[str, str], list[str]] = {
    (r"gender", r"male"): [r"^male$", r"^man$", r"^male\b"],
    (r"gender", r"female"): [r"^female$", r"^woman$", r"^female\b"],
    (r"gender", r"non-binary"): [r"non-?binary", r"genderqueer"],
    (r"hispanic", r"no"): [r"^no\b", r"not hispanic", r"non-hispanic"],
    (r"hispanic", r"yes"): [r"^yes\b", r"^hispanic", r"^i am hispanic"],
    (r"veteran", r"no"): [r"not a protected veteran", r"not a veteran", r"^no\b", r"i am not"],
    (r"veteran", r"yes"): [r"identify as one or more", r"^yes\b", r"i am a (?:protected )?veteran"],
    (r"disability", r"no"): [r"^no\b", r"do not have a disability", r"don't have a disability"],
    (r"disability", r"yes"): [r"^yes\b", r"i have a disability"],
    (r"race", r"white"): [r"^white\b", r"caucasian"],
    (r"race", r"black"): [r"^black\b", r"african american"],
    (r"race", r"asian"): [r"^asian\b"],
    (r"race", r"hispanic"): [r"hispanic", r"latino"],
    (r"race", r"native american"): [r"american indian", r"alaska native", r"native american"],
    (r"race", r"pacific islander"): [r"hawaiian", r"pacific islander"],
    (r"race", r"two or more"): [r"two or more", r"multiracial"],
}


def _eeo_value(f: Field) -> str | None:
    """Pick the option matching the configured answer for this self-identification question, else decline."""
    text = f"{f.group_label} {f.label}"
    kind = setting = None
    for k, pat, key in EEO_KINDS:
        if pat.search(text):
            kind, setting = k, key
            break
    want = (config.get(setting) if setting else "").strip().lower()
    if kind and want and want != "decline":
        pats = EEO_SYNONYMS.get((kind, want)) or [re.escape(want)]
        v = _choose_option(f.options, [re.compile(p, re.I) for p in pats])
        if v:
            return v
    return _choose_option(f.options, DECLINE)


def _choose_option(options: list[str], prefs: list[re.Pattern]) -> str | None:
    for pat in prefs:
        for o in options:
            if pat.search(o):
                return o
    return None


def _answer_with_llm(fields: list[Field], job: dict, res: ApplyResult) -> dict[int, str]:
    if not fields:
        return {}
    r = documents.active_resume()
    cand = config.candidate()
    qs = []
    for i, f in enumerate(fields, 1):
        opts = f" Options: {' / '.join(f.options[:40])}" if f.options else ""
        qs.append(f"{i}. {f.question or f.name} (type: {f.kind}{', required' if f.required else ''}){opts}")
    projects = work.block(6000)
    user = (f"CANDIDATE PROFILE:\n{cand.as_prompt()}\n\nRESUME:\n{(r or {}).get('content','')[:9000]}\n\n"
            + (f"{projects}\n\n" if projects else "") +
            f"JOB: {job.get('title')} at {job.get('company')}\n\nQUESTIONS (answer each, in order):\n" + "\n".join(qs))
    try:
        out = llm.extract(ANSWER_SYSTEM, user, FormAnswers, model=config.get("model_main"), effort="medium", purpose="form answers", max_tokens=6000)
    except Exception as e:  # noqa: BLE001
        res.add(f"LLM answer step failed: {e}")
        return {}
    answers = {}
    for f, a in zip(fields, out.answers):
        if a.answer.strip().upper() == "UNKNOWN" or a.confidence == "low":
            continue
        if COMPLIANCE_Q.search(f"{f.group_label} {f.label} {f.question or ''}"):
            res.add(f"not letting the AI answer '{f.display}' (compliance question): left for you")
            continue
        answers[f.idx] = a.answer.strip()
    return answers


def _set(frame, f: Field, value: str, res: ApplyResult, first_ok: bool = False) -> bool:
    if f.kind in ("radio", "checkbox") and f.group:
        return _check_in_group(frame, f, value, res)
    return _fill_text(frame, f, value, res, first_ok=first_ok)


def _fill_form(frame, app: dict, job: dict, letter: str, res: ApplyResult) -> None:
    cand = config.candidate()
    resume_path = documents.resume_file_for_upload()
    fields = _collect(frame)
    res.add(f"found {len(fields)} fields")
    leftover: list[Field] = []
    cover_textarea_filled = False
    seen_groups: set[str] = set()
    yes_no = lambda flag: (YES if flag.strip().lower().startswith("y") else NO)  # noqa: E731

    for f in fields:
        if f.group:
            if f.group in seen_groups:
                continue
            seen_groups.add(f.group)
        key = classify(f)
        if f.kind == "combobox" and not f.options:
            f.options = _combobox_options(frame, f)
        v: str | None = None
        if key == "first_name": v = cand.first_name
        elif key == "last_name": v = cand.last_name
        elif key == "full_name": v = cand.full_name
        elif key == "email": v = cand.email
        elif key == "phone": v = cand.phone
        elif key == "linkedin": v = cand.linkedin
        elif key == "github": v = cand.github
        elif key == "website": v = cand.website or cand.github
        elif key == "location": v = cand.location
        elif key == "salary": v = cand.salary
        elif key == "start_date": v = cand.start_date
        elif key == "degree":
            if f.options:
                v = _degree_option(f.options, cand.degree)
                if not v:
                    leftover.append(f)
                    continue
            else:
                v = cand.degree
        elif key == "optin":
            v = _choose_option(f.options, NO) or ("" if f.kind == "checkbox" else "No")
            if not v:
                continue
        elif key == "pronouns":
            continue
        elif key == "resume":
            if f.kind == "file" and resume_path:
                try:
                    upload = _resume_file(app["id"], resume_path)
                    frame.locator(f.selector).first.set_input_files(str(upload))
                    res.add(f"uploaded resume {upload.name} -> '{f.display}'")
                    res.note(f, upload.name, "file")
                    time.sleep(1.0)
                except Exception as e:  # noqa: BLE001
                    res.add(f"resume upload failed: {str(e)[:100]}")
                    if f.required:
                        res.unresolved.append("resume upload")
            continue
        elif key == "cover_letter":
            if f.kind == "file":
                if not cover_textarea_filled:
                    try:
                        doc = _letter_file(app["id"], letter)
                        frame.locator(f.selector).first.set_input_files(str(doc))
                        res.add("uploaded cover letter document")
                        res.note(f, doc.name, "file")
                    except Exception as e:  # noqa: BLE001
                        res.add(f"cover letter upload failed: {str(e)[:100]}")
                continue
            v = letter
            cover_textarea_filled = True
        elif key == "work_auth":
            v = (_choose_option(f.options, yes_no(cand.work_auth)) or cand.work_auth) if cand.work_auth.strip() else ""
        elif key == "sponsorship":
            v = (_choose_option(f.options, yes_no(cand.sponsorship)) or cand.sponsorship) if cand.sponsorship.strip() else ""
        elif key == "hear_about":
            v = _choose_option(f.options, HEAR) or "Job board"
        elif key == "eeo":
            v = _eeo_value(f)
            if not v:
                continue
        elif key == "consent":
            if f.kind == "checkbox" and _fill_text(frame, f, "on", res):
                res.note(f, "Agreed", "standard")
            continue
        else:
            if f.required or f.kind == "textarea":
                leftover.append(f)
            continue

        if v:
            if _set(frame, f, v, res, first_ok=(key == "location")):
                res.note(f, v, "letter" if key == "cover_letter" else
                         "standard" if key in ("hear_about", "eeo", "optin") else "profile")
            elif f.required:
                leftover.append(f)
        elif key in COMPLIANCE_KEYS:
            # Blank in your profile: this is yours to answer, never the AI's. Shown under "Needs you" at review.
            res.add(f"'{f.display}' is blank in your profile; left for you")
            res.note(f, "", "missing")
            if f.required:
                res.unresolved.append(f.display)
        elif f.required:
            leftover.append(f)

    if leftover:
        res.add(f"{len(leftover)} unmapped field(s): " + "; ".join(x.display for x in leftover) + " -> asking LLM")
        answers = _answer_with_llm(leftover, job, res)
        for f in leftover:
            v = answers.get(f.idx)
            if not v or not _set(frame, f, v, res):
                res.unresolved.append(f.display)
                res.note(f, v or "", "missing")
                continue
            res.note(f, v, "ai")
        try:
            from ..facts import check_answers
            items = [res.review[f.idx] for f in leftover if f.idx in res.review]
            n = check_answers(items)
            if n:
                res.add(f"fact check: {n} AI answer(s) make claims not backed by your profile; marked for you")
        except Exception as e:  # noqa: BLE001
            res.add(f"fact check skipped: {str(e)[:120]}")


def _page_text(page) -> str:
    out = []
    for fr in page.frames:
        try:
            out.append(fr.inner_text("body")[:20000])
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(out)


def _submit(page, frame, res: ApplyResult) -> bool:
    btn = frame.get_by_role("button", name=re.compile(r"submit application|submit|send application|apply now|apply$", re.I)).first
    if not btn.count():
        btn = frame.locator('button[type="submit"], input[type="submit"]').first
    if not btn.count():
        res.add("no submit button found")
        return False
    btn.scroll_into_view_if_needed()
    btn.click()
    res.add("clicked submit")
    deadline = time.time() + 25
    while time.time() < deadline:
        time.sleep(1.5)
        body = _page_text(page)
        if SUCCESS.search(body):
            return True
        try:
            err = frame.locator('[aria-invalid="true"], .error, .field-error, [class*="error" i]').first
            if err.count() and re.search(r"required|invalid|must|please", (err.inner_text() or ""), re.I):
                res.add(f"validation error: {err.inner_text()[:120]}")
                return False
        except Exception:  # noqa: BLE001
            pass
    if re.search(r"captcha|verify you are human|i'm not a robot", _page_text(page), re.I):
        res.add("captcha present; needs you")
    return False


CONFIRM_URL = re.compile(r"confirm|thank|success|submitted|complete|received", re.I)


def _looks_submitted(page, start_url: str) -> bool:
    """Success text, or the page moved to a confirmation-looking URL (many ATSs show no recognisable text)."""
    if SUCCESS.search(_page_text(page)):
        return True
    url = page.url
    return url.split("#")[0] != start_url.split("#")[0] and bool(CONFIRM_URL.search(url.split("?")[0]))


def _wait_for_user(page, minutes: int, res: ApplyResult) -> bool:
    res.add(f"handing off: browser stays open {minutes} min for you to finish")
    start_url = page.url
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(3)
        try:
            if page.is_closed():
                res.add("browser closed before a confirmation was seen")
                return False
            if _looks_submitted(page, start_url):
                time.sleep(2)  # let the confirmation page finish rendering for the screenshot
                return True
        except Exception:  # noqa: BLE001
            return False
    return False


def _await_review(page, app_id: int, res: ApplyResult, minutes: int) -> dict:
    """Publish what was filled, then wait for the review page's decision (or for the user to submit in the
    browser themselves). Returns {"action": approve|cancel|submitted|closed|timeout, "edits": {idx: value}}."""
    items = sorted(res.review.values(), key=lambda r: r["idx"])
    db.update("applications", app_id, {"review_json": db.dumps(items), "review_decision": None})
    missing = sum(1 for r in items if r["source"] == "missing")
    queue.set_status(app_id, "review", f"Filled {len(items)} fields" + (f", {missing} need you" if missing else "")
                     + ". Waiting for you to check and send.", source="system")
    res.add(f"waiting up to {minutes} min for your review")
    start_url = page.url
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(2)
        try:
            if page.is_closed():
                return {"action": "closed"}
            if _looks_submitted(page, start_url):
                return {"action": "submitted"}
        except Exception:  # noqa: BLE001
            return {"action": "closed"}
        row = db.q1("SELECT review_decision FROM applications WHERE id=?", (app_id,)) or {}
        if row.get("review_decision"):
            db.update("applications", app_id, {"review_decision": None})
            return db.loads(row["review_decision"], {}) or {"action": "timeout"}
    return {"action": "timeout"}


def _apply_edits(frame, edits: dict, res: ApplyResult) -> None:
    for key, value in (edits or {}).items():
        f = res.fields.get(int(key))
        value = (value or "").strip()
        if not f or f.kind == "file" or value == (res.review.get(f.idx) or {}).get("value", ""):
            continue
        if value and _set(frame, f, value, res):
            res.add(f"you changed '{f.display}'")
            res.note(f, value, "you")
            if f.display in res.unresolved:
                res.unresolved.remove(f.display)


def _shot(page, app_id: int, tag: str) -> str:
    p = SCREENSHOTS / f"app{app_id}_{tag}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        page.screenshot(path=str(p), full_page=True)
    except Exception:  # noqa: BLE001
        return ""
    return str(p)


def apply_to(app_id: int, run_id: int | None = None, handoff_minutes: int = 20) -> ApplyResult:
    from playwright.sync_api import sync_playwright

    res = ApplyResult()
    app = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not app or not app.get("job_id"):
        raise ValueError("application has no job")
    job = db.q1("SELECT * FROM jobs WHERE id=?", (app["job_id"],))
    letter = (app.get("cover_letter") or "").strip()
    if not letter:
        raise ValueError("No cover letter. Draft and approve one first.")
    cand = config.candidate()
    if not (cand.first_name and cand.email):
        raise ValueError("Fill your name and email in Settings first.")
    url = _apply_url(job)
    queue.set_status(app_id, "applying", f"Opening {url}", source="system")
    auto = config.get_bool("auto_submit")
    headless = config.get_bool("headless")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(BROWSER_PROFILE), headless=headless, viewport={"width": 1280, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:  # noqa: BLE001
                pass
            res.add(f"opened {url}")
            frame = _best_frame(page)
            if not frame.locator('input[type="file"], textarea, input[type="email"]').first.count():
                for getter in (page.get_by_role("button", name=re.compile(r"^apply|apply (now|for this)", re.I)),
                               page.get_by_role("link", name=re.compile(r"^apply|apply (now|for this)", re.I))):
                    b = getter.first
                    if b.count():
                        b.click()
                        res.add("clicked Apply to reveal the form")
                        try:
                            page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:  # noqa: BLE001
                            pass
                        break
                frame = _best_frame(page)
            if not frame.locator("input, textarea, select").first.count():
                res.add("no form found on this page")
                res.unresolved.append("no application form detected (external site?)")
            else:
                if frame != page.main_frame:
                    res.add(f"form is inside iframe {frame.url[:80]}")
                _fill_form(frame, app, job, letter, res)

            res.screenshot = _shot(page, app_id, "filled")
            if config.get_bool("review_before_submit") and res.review:
                d = _await_review(page, app_id, res, handoff_minutes + 10)
                act = d.get("action")
                if act == "submitted":
                    res.submitted = True
                elif act == "cancel":
                    res.cancelled = True
                    res.add("you cancelled at review")
                elif act == "approve":
                    _apply_edits(frame, d.get("edits") or {}, res)
                    queue.set_status(app_id, "applying", "You approved it. Sending...", source="manual")
                    res.submitted = _submit(page, frame, res)
                    if not res.submitted and not headless:
                        res.add("could not confirm submission; handing off")
                        res.submitted = _wait_for_user(page, handoff_minutes, res)
                else:
                    res.add("review " + ("timed out" if act == "timeout" else "ended: browser closed"))
            elif res.unresolved:
                res.add("unresolved: " + "; ".join(res.unresolved))
                if not headless:
                    res.submitted = _wait_for_user(page, handoff_minutes, res)
            elif auto:
                res.submitted = _submit(page, frame, res)
                if not res.submitted and not headless:
                    res.add("could not confirm submission; handing off")
                    res.submitted = _wait_for_user(page, handoff_minutes, res)
            elif not headless:
                res.submitted = _wait_for_user(page, handoff_minutes, res)
            else:
                res.add("auto_submit off and headless on: filled only")
            if res.submitted:
                res.screenshot = _shot(page, app_id, "submitted") or res.screenshot
        except Exception as e:  # noqa: BLE001
            res.add(f"ERROR: {e}")
            res.screenshot = _shot(page, app_id, "error") or res.screenshot
        finally:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass

    log = "\n".join(res.log)
    final = sorted(res.review.values(), key=lambda r: r["idx"])   # includes your review-screen edits (source "you")
    db.update("applications", app_id, {"submit_log": log, "screenshot_path": res.screenshot,
                                       "review_json": db.dumps(final) if final else None})
    if res.submitted:
        queue.set_status(app_id, "submitted", "Submitted via auto-apply", source="system")
    elif res.cancelled:
        queue.set_status(app_id, "ready", "Cancelled before sending. Nothing was submitted.", source="manual")
    elif res.unresolved:
        queue.set_status(app_id, "needs_attention", "Unresolved: " + "; ".join(res.unresolved)[:300], source="system")
    else:
        queue.set_status(app_id, "needs_attention", "Submission not confirmed. Check the screenshot/log.", source="system")
    if run_id:
        db.run_log(run_id, f"apply #{app_id}: {'submitted' if res.submitted else 'needs attention'}")
    return res
