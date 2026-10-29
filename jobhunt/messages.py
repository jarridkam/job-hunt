"""Plain-English wording for statuses, background tasks and errors. The DB keeps short codes
(needs_attention, low_fit ...); everything the user reads goes through here."""
from __future__ import annotations

# Five tones, used for every status in the app so one colour always means one thing:
#   wait     amber  your move (read, decide, take the test, pick a time)
#   progress blue   jobhunt is working on it, nothing for you to do
#   good     green  went well / moving forward
#   closed   grey   over, nothing more will happen
#   broken   red    something failed or was missed
#   ''       none   neutral (new, unscored)
TONES = {"wait": "Your move", "progress": "In progress", "good": "Going well", "closed": "Closed", "broken": "Broken or missed"}

# code -> (label, what it means / what to do next, tone)
APP_STATUS: dict[str, tuple[str, str, str]] = {
    "queued": ("Waiting for a letter", "A cover letter will be drafted next.", "progress"),
    "drafting": ("Writing letter…", "The cover letter is being drafted. This takes under a minute.", "progress"),
    "ready": ("Ready to apply", "Read the letter, then Approve & apply.", "wait"),
    "applying": ("Applying…", "The browser is filling the form.", "progress"),
    "review": ("Check before sending", "Look over what will be submitted, fix anything, then send it.", "wait"),
    "needs_attention": ("Needs you", "Auto-apply got stuck. See the note, then retry or finish it yourself.", "wait"),
    "failed": ("Didn't go through", "Something went wrong. See the note, then retry.", "broken"),
    "submitted": ("Applied", "Sent. Waiting to hear back.", "good"),
    "screening": ("Recruiter screen", "A recruiter reached out or a phone screen is scheduled.", "good"),
    "assessment": ("Assessment", "They sent a test or take-home. Check Upcoming for the deadline.", "wait"),
    "interview": ("Interviewing", "You have an interview in progress.", "good"),
    "offer": ("Offer!", "You have an offer.", "good"),
    "rejected": ("Let go", "They went another way. It happens to everyone; it says nothing about the next one.", "closed"),
    "withdrawn": ("Stepped back", "You decided not to continue.", "closed"),
}

JOB_STATUS: dict[str, tuple[str, str, str]] = {
    "new": ("New", "Not acted on yet.", ""),
    "queued": ("In your queue", "Added to the apply queue.", "progress"),
    "applied": ("Applied", "You applied to this one.", "good"),
    "skipped": ("Passed", "You passed on this job.", "closed"),
    "low_fit": ("Not a match", "Scored below your minimum fit, or outside your target titles.", "closed"),
    "not_legit": ("Looks off", "Failed the legitimacy check. Tap its legit score to see why.", "broken"),
}

ASSESSMENT_STATUS = {"pending": ("To do", "wait"), "completed": ("Done", "good"), "missed": ("Missed", "broken")}
RUN_STATUS = {"running": ("Working", "progress"), "done": ("Done", "good"), "failed": ("Failed", "broken")}

TASK_LABELS = {
    "fetch": "Finding jobs", "score": "Scoring jobs", "fetch_and_score": "Finding & scoring jobs",
    "draft_all": "Drafting letters", "email": "Checking your email", "reclassify": "Re-reading emails",
}


EVENT_LABELS = {"queued": "Added to queue", "drafted": "Letter drafted", "approved": "Letter approved",
                "applying": "Started applying", "review": "Waiting for your check",
                "interview_invite": "Interview invite", "interview_scheduled": "Interview scheduled",
                "interview_reminder": "Interview reminder", "interview_cancelled": "Interview cancelled",
                "application_received": "Application received", "assessment_invite": "Assessment invite",
                "assessment_reminder": "Assessment reminder", "assessment_completed": "Assessment completed",
                "assessment_expired": "Assessment expired", "created_from_email": "Found in your email",
                "recruiter_outreach": "Recruiter reached out", "rejection": "Let go", "offer": "Offer",
                "followup_sent": "You followed up", "message_sent": "You replied"}
INTERVIEW_STATUS = {"needs_scheduling": ("Pick a time", "wait"), "scheduled": ("Scheduled", "good"), "done": ("Done", "closed"),
                    "cancelled": ("Cancelled", "closed"), "missed": ("Missed", "broken")}
INTERVIEW_FORMAT = {"phone": "Phone", "video": "Video", "onsite": "In person", "recorded": "Recorded"}
SOURCE_LABELS = {"manual": "you", "system": "jobhunt", "email": "email"}


def interview_status(code: str | None) -> tuple[str, str]:
    return INTERVIEW_STATUS.get(code or "", ((code or "").replace("_", " ").capitalize(), ""))


def assessment_status(code: str | None) -> tuple[str, str]:
    return ASSESSMENT_STATUS.get(code or "", ((code or "").replace("_", " ").capitalize(), ""))


def run_status(code: str | None) -> tuple[str, str]:
    return RUN_STATUS.get(code or "", ((code or "").replace("_", " ").capitalize(), ""))


def event_label(code: str) -> str:
    return EVENT_LABELS.get(code) or app_status(code)[0]


def task_label(kind: str) -> str:
    if kind.startswith("draft-"):
        return "Drafting a letter"
    if kind.startswith("apply-"):
        return "Applying"
    if kind.startswith("prep-"):
        return "Writing an interview prep card"
    if kind.startswith("followup-"):
        return "Drafting a follow-up note"
    return TASK_LABELS.get(kind, kind.replace("_", " ").capitalize())


def app_status(code: str | None) -> tuple[str, str, str]:
    return APP_STATUS.get(code or "", ((code or "").replace("_", " ").capitalize(), "", ""))


def job_status(code: str | None) -> tuple[str, str, str]:
    return JOB_STATUS.get(code or "", ((code or "").replace("_", " ").capitalize(), "", ""))


def friendly_error(e: BaseException | str) -> str:
    """One sentence a non-developer can act on. Unknown errors keep their text, trimmed."""
    msg = str(e).strip()
    low = msg.lower()
    name = type(e).__name__ if isinstance(e, BaseException) else ""
    if "no anthropic api key" in low:
        return "No Anthropic API key yet. Add it in Settings."
    if "credit balance" in low:
        return "Your Anthropic credit has run out. Top up at platform.claude.com/settings/billing."
    if name == "AuthenticationError" or "invalid x-api-key" in low or "authentication_error" in low or "invalid api key" in low:
        return "Anthropic rejected your API key. Check it in Settings (Test API key)."
    if "rate_limit" in low or "429" in low:
        return "Anthropic is rate-limiting this key. Wait a minute and try again."
    if "overloaded" in low or "529" in low:
        return "Anthropic is overloaded right now. Try again in a few minutes."
    if name in ("APIConnectionError", "ConnectError", "ConnectTimeout") or "getaddrinfo" in low or "connection error" in low:
        return "Couldn't reach the internet service. Check your connection and try again."
    if "no active resume" in low:
        return "Add your resume under Documents first."
    if "model refused" in low:
        return "The AI declined this one. Try rewording your note, or write it yourself."
    if "max_tokens" in low or "truncated" in low:
        return "The AI's answer was cut off. Try again."
    if "timeout" in low and ("page" in low or "navigat" in low or name == "TimeoutError"):
        return "The job site took too long to load. Try again later."
    if "authenticationfailed" in low or "invalid credentials" in low or ("imap" in low and "login" in low):
        return "Your email login failed. Gmail needs an App Password (Settings > Email tracker)."
    return msg if len(msg) <= 200 else msg[:197] + "…"
