"""Typed access to settings stored in the DB (with env fallbacks)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import db

DEFAULT_MAIN_MODEL = "claude-sonnet-5-5"
DEFAULT_FAST_MODEL = "claude-sonnet-5-5"

# Dropdown choices for model settings: (model id, label). Prices are per million tokens, input / output.
MODEL_OPTIONS: list[tuple[str, str]] = [
    ("claude-haiku-5-5", "Claude Haiku 5.5 — fastest, cheapest ($0.10 / $0.50)"),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5 — fast, strong ($2 / $10)"),
    ("claude-opus-5-5", "Claude Opus 5.5 — best quality ($4 / $20)"),
    ("claude-fable-5-1", "Claude Fable 5.1 — most capable, slow ($10 / $50)"),
]
SELECT_OPTIONS: dict[str, list[tuple[str, str]]] = {"model_main": MODEL_OPTIONS, "model_fast": MODEL_OPTIONS}

# key -> (label, default, kind, help)
SETTING_SPECS: list[tuple[str, str, str, str, str]] = [
    # LLM
    ("anthropic_api_key", "Anthropic API key", "", "password", "Stored locally in data/jobhunt.db. Env ANTHROPIC_API_KEY also works."),
    ("model_main", "Model for cover letters", DEFAULT_MAIN_MODEL, "select", "Drafting letters and answering application questions. Quality matters most here."),
    ("model_fast", "Model for bulk scoring / email classification", DEFAULT_FAST_MODEL, "select",
     "Runs on every job and email. Haiku is ~20x cheaper than Sonnet for this."),
    # Search
    ("search_titles", "Target job titles (one per line)", "", "textarea", "Jobs whose title matches one of these get scored. Use 'Suggest from resume' to fill."),
    ("search_keywords", "Extra keywords (one per line)", "", "textarea", "Used as aggregator search queries alongside titles."),
    ("search_locations", "Locations (one per line)", "", "textarea", "e.g. Austin, TX  /  United States  /  Remote"),
    ("remote_only", "Remote only", "0", "bool", ""),
    ("exclude_keywords", "Exclude if title contains (one per line)", "senior staff\nprincipal\ndirector\nvp ", "textarea", "Case-insensitive substrings."),
    ("min_legit_score", "Min legitimacy score to keep (0-100)", "55", "number", ""),
    ("min_fit_score", "Min fit score to show as a match (0-100)", "65", "number", ""),
    ("auto_queue_score", "Auto-queue jobs scoring at or above", "80", "number", "0 disables auto-queue."),
    ("max_llm_scores_per_run", "Max jobs to LLM-score per run", "150", "number", "Cost guard."),
    ("adzuna_country", "Adzuna country code", "us", "text", "us, gb, ca, au ..."),
    ("adzuna_app_id", "Adzuna app id", "", "text", "Free at developer.adzuna.com. Blank = source off."),
    ("adzuna_app_key", "Adzuna app key", "", "password", ""),
    ("jsearch_key", "JSearch (RapidAPI) key", "", "password", "Free tier at rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch. Blank = source off."),
    ("use_remote_boards", "Use Remotive / RemoteOK / WeWorkRemotely", "1", "bool", ""),
    # Candidate profile for forms
    ("cand_first_name", "First name", "", "text", ""),
    ("cand_last_name", "Last name", "", "text", ""),
    ("cand_email", "Email", "", "text", ""),
    ("cand_phone", "Phone", "", "text", ""),
    ("cand_location", "City, State", "", "text", ""),
    ("cand_linkedin", "LinkedIn URL", "", "text", ""),
    ("cand_github", "GitHub URL", "", "text", ""),
    ("cand_website", "Portfolio / website URL", "", "text", ""),
    ("cand_degree", "Degree(s)", "", "text", "e.g. B.S. Computer Science, University of X, 2025"),
    ("cand_work_auth", "Authorized to work in target country?", "", "text", "Yes / No. Left blank, forms that ask are held for you; never guessed."),
    ("cand_sponsorship", "Need visa sponsorship now or in future?", "", "text", "Yes / No. Left blank, forms that ask are held for you; never guessed."),
    # Voluntary self-identification (EEO). Kept apart from the application by law; 'decline' is always acceptable.
    ("cand_eeo_gender", "EEO: gender", "decline", "text", "Male / Female / Non-binary / decline"),
    ("cand_eeo_race", "EEO: race / ethnicity", "decline", "text", "White / Black or African American / Asian / Hispanic or Latino / ... / decline"),
    ("cand_eeo_hispanic", "EEO: Hispanic or Latino?", "decline", "text", "Yes / No / decline (asked separately on some forms)"),
    ("cand_eeo_veteran", "EEO: protected veteran?", "decline", "text", "Yes / No / decline"),
    ("cand_eeo_disability", "EEO: disability?", "decline", "text", "Yes / No / decline"),
    ("cand_salary", "Salary expectation (text)", "", "text", "Left blank = skip the field when optional."),
    ("cand_start_date", "Earliest start date", "Immediately", "text", ""),
    ("cand_extra_answers", "Extra Q&A for application forms", "", "textarea",
     "Free text the LLM can use when a form asks something not covered above. One fact per line, e.g. 'Willing to relocate: yes'"),
    ("voice_notes", "Voice / style notes for cover letters", "", "textarea",
     "How you want to sound. e.g. 'plain, direct, no buzzwords, mention I built things outside class'"),
    # Apply
    ("review_before_submit", "Let me check every application before it's sent", "1", "bool",
     "Auto-apply fills the form, then waits for you to look over each answer and press Send."),
    ("auto_submit", "Auto-submit after filling (otherwise fill and hand off to you)", "1", "bool", ""),
    ("followup_days", "Nudge me to follow up after N quiet days", "14", "number",
     "An application with no reply for this long shows up under Needs you with a drafted note."),
    # Phone alerts
    ("notify_quiet_hours", "Quiet hours (no pushes), e.g. 22-8", "22-8", "text",
     "Alerts that come due overnight wait until the morning. Leave blank for none."),
    ("notify_base_url", "Address of this app on your phone (for links in alerts)", "", "text",
     "e.g. https://jobhunt.your-tailnet.ts.net. Blank = relative links (fine when the alert opens the installed app)."),
    ("notify_webhook_url", "Also send alerts to this URL (ntfy topic or webhook)", "", "text",
     "Optional second channel. For ntfy: install the ntfy app, pick a topic, paste https://ntfy.sh/your-topic here. Any other URL gets a JSON POST."),
    ("headless", "Run browser headless", "0", "bool", "Keep off so you can watch and take over when needed."),
    # Email
    ("email_host", "IMAP host", "imap.gmail.com", "text", ""),
    ("email_user", "IMAP user (email)", "", "text", "Gmail: create an App Password at myaccount.google.com/apppasswords"),
    ("email_pass", "IMAP password / app password", "", "password", ""),
    ("email_folder", "IMAP folder", "INBOX", "text", ""),
    ("smtp_host", "SMTP host (for sending replies)", "", "text", "Blank = guessed from the IMAP host (imap.gmail.com → smtp.gmail.com). Same login as IMAP."),
    ("smtp_port", "SMTP port", "587", "number", "587 (STARTTLS) for Gmail, Outlook, most providers; 465 for SSL-only servers."),
    ("email_auto_minutes", "Check the inbox by itself every N minutes", "30", "number",
     "While jobhunt is running. 0 = only when you press Sync inbox. Only mail that looks like a job email costs an AI call."),
    ("email_since_days", "First sync: look back N days", "60", "number",
     "Only for the very first sync. After that, Sync inbox looks back to your last sync (24 hours if you synced yesterday)."),
    ("email_max_per_sync", "Max emails sent to the LLM per sync", "200", "number",
     "Cost guard. Newest mail is handled first; emails that miss every keyword are free and don't count."),
    ("email_scan_spam", "Also check the Spam / Junk folder for tests and interviews", "1", "bool",
     "Assessment invites (HackerRank, HireVue, Codility…) land in spam more often than you'd think. Only mail that looks like a test or interview is read from there."),
    ("assessment_buffer_days", "Aim to finish tests N days before the deadline", "2", "number",
     "Today shows a 'do it by' date this many days early. Links sometimes die before the stated date."),
    ("assessment_default_days", "If an invite states no deadline, assume N days from receipt", "7", "number",
     "Shown as 'assumed' so you know it is a guess. 0 = leave the deadline unknown."),
    ("email_extra_keywords", "Extra assessment / recruiter keywords (one per line)", "", "textarea",
     "Emails are only sent to the LLM if subject/sender/body hit a keyword. Add platforms or senders it misses, e.g. 'testgorilla', 'noreply@hire.lever.co', 'Pymetrics'."),
    ("email_hints", "Hints for the email classifier (one per line)", "", "textarea",
     "Facts the LLM should know when reading your inbox, e.g. 'Emails from talent@bungie.com are real recruiters', "
     "'Ignore LinkedIn job alerts', 'A HackerRank invite from Nintendo is for the Gameplay Engineer role'."),
]


def spec_defaults() -> dict[str, str]:
    return {k: d for k, _, d, _, _ in SETTING_SPECS}


def get(key: str) -> str:
    env_map = {"anthropic_api_key": "ANTHROPIC_API_KEY"}
    v = db.get_setting(key, "")
    if not v and key in env_map:
        v = os.environ.get(env_map[key], "")
    if not v:
        v = spec_defaults().get(key, "")
    return v


def get_bool(key: str) -> bool:
    return get(key).strip().lower() in ("1", "true", "yes", "on")


def get_int(key: str, default: int = 0) -> int:
    try:
        return int(float(get(key)))
    except Exception:
        return default


def get_lines(key: str) -> list[str]:
    return [ln.strip() for ln in get(key).splitlines() if ln.strip()]


@dataclass
class Candidate:
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    degree: str = ""
    work_auth: str = ""
    sponsorship: str = ""
    salary: str = ""
    start_date: str = ""
    extra_answers: str = ""
    voice_notes: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def as_prompt(self) -> str:
        lines = [
            f"Name: {self.full_name}",
            f"Email: {self.email}",
            f"Phone: {self.phone}",
            f"Location: {self.location}",
            f"LinkedIn: {self.linkedin}",
            f"GitHub: {self.github}",
            f"Website: {self.website}",
            f"Degree: {self.degree}",
            f"Authorized to work: {self.work_auth or 'not stated'}",
            f"Needs sponsorship: {self.sponsorship or 'not stated'}",
            f"Salary expectation: {self.salary or 'not stated'}",
            f"Earliest start: {self.start_date}",
        ]
        if self.extra_answers.strip():
            lines.append("Other facts:\n" + self.extra_answers.strip())
        return "\n".join(lines)


def candidate() -> Candidate:
    return Candidate(
        first_name=get("cand_first_name"), last_name=get("cand_last_name"), email=get("cand_email"),
        phone=get("cand_phone"), location=get("cand_location"), linkedin=get("cand_linkedin"),
        github=get("cand_github"), website=get("cand_website"), degree=get("cand_degree"),
        work_auth=get("cand_work_auth"), sponsorship=get("cand_sponsorship"), salary=get("cand_salary"),
        start_date=get("cand_start_date"), extra_answers=get("cand_extra_answers"), voice_notes=get("voice_notes"),
    )
