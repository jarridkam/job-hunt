"""Pydantic schemas for LLM structured outputs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FitScore(BaseModel):
    fit_score: int = Field(description="0-100. 100 = ideal match for experience, skills, degree, and seniority.")
    seniority_ok: bool = Field(description="False if the role clearly needs far more years than the candidate has.")
    summary: str = Field(description="One or two sentences on why this is or is not a fit, written to the candidate.")
    matching_points: list[str] = Field(description="Concrete things from the candidate's background that match the posting.")
    missing: list[str] = Field(description="Hard requirements the candidate does not clearly meet.")
    red_flags: list[str] = Field(description="Anything suspicious about the posting (scam signals, vague company, pay-to-apply).")


class PrepGap(BaseModel):
    gap: str = Field(description="The gap, in a few words.")
    framing: str = Field(description="One or two honest sentences for how to answer if asked.")


class PrepQuestion(BaseModel):
    question: str
    pointer: str = Field(description="One line: which resume item or letter claim to answer with.")


class PrepCard(BaseModel):
    company_brief: str = Field(description="One or two sentences: what the company does and why this role exists, from the posting.")
    role_brief: str = Field(description="One or two sentences: what the job actually is day to day.")
    your_claims: list[str] = Field(description="3-6 short bullets: the specific things the resume and cover letter claimed that the interviewer will have read.")
    gaps: list[PrepGap] = Field(description="0-4 gaps between the posting and the candidate, each with an honest framing.")
    likely_questions: list[PrepQuestion] = Field(description="5-8 questions this stage is likely to ask, most likely first.")
    ask_them: list[str] = Field(description="3-4 good questions for the candidate to ask, specific to this company and role.")
    checklist: list[str] = Field(description="3-6 pre-call items: logistics (link, time zone, quiet place, resume open), plus anything from the invite.")


class FollowUpNote(BaseModel):
    subject: str
    body: str = Field(description="The note, plain text with line breaks, signed with the candidate's name.")


class SearchProfile(BaseModel):
    titles: list[str] = Field(description="8-15 job titles this candidate should search for, most likely first.")
    keywords: list[str] = Field(description="5-10 skill/domain keywords for search queries.")
    seniority: str = Field(description="entry | junior | mid | senior")
    summary: str = Field(description="Two sentences describing the candidate's strongest positioning.")


class FormAnswer(BaseModel):
    answer: str = Field(description="The value to enter. Use the exact option text when options are given. Use UNKNOWN if the profile does not contain the information.")
    confidence: Literal["high", "medium", "low"]


class FormAnswers(BaseModel):
    answers: list[FormAnswer]


class EmailClassification(BaseModel):
    kind: Literal[
        "assessment_invite", "assessment_reminder", "assessment_completed", "assessment_expired",
        "application_received", "rejection", "interview_invite", "interview_scheduled", "interview_reminder",
        "interview_cancelled", "offer", "recruiter_outreach", "other",
    ]
    company: str = Field(description="Company the email is about, or empty string.")
    role: str = Field(description="Job title if mentioned, else empty string.")
    platform: str = Field(description="Assessment platform if any: HackerRank, Codility, CodeSignal, Karat, HireVue, Plum, SHL, pymetrics, etc. Empty if none.")
    due_at: str = Field(description="Deadline ONLY if the email states an explicit calendar date, as ISO 8601 YYYY-MM-DDTHH:MM (use 23:59 when no time is given). Empty string if the deadline is only relative or absent.")
    due_in_days: int = Field(default=0, description="If the deadline is relative to the email ('within 7 days', 'in the next 3 days', 'expires in 5 days', 'by end of week' = days until Sunday), that number of days. 0 if none or if an explicit date was given.")
    due_in_hours: int = Field(default=0, description="Relative deadline stated in hours ('within 48 hours' = 48). 0 if none.")
    due_tz: str = Field(default="", description="Time zone attached to the deadline if the email states one, e.g. 'PST', 'ET', 'UTC', 'IST', 'America/New_York'. Empty if none.")
    est_minutes: int = Field(description="Estimated time to complete in minutes if stated (assessment length or interview length), else 0.")
    interview_at: str = Field(default="", description="For interview_scheduled/interview_reminder/interview_cancelled ONLY: the interview's start date and time as ISO 8601 YYYY-MM-DDTHH:MM, exactly as the email states it. Empty for everything else, and empty when no date is given.")
    interview_tz: str = Field(default="", description="Time zone stated next to the interview time, e.g. 'PST', 'ET', 'CST', 'America/Chicago'. Empty if none.")
    interview_format: Literal["phone", "video", "onsite", "recorded", ""] = Field(default="", description="How the interview happens: phone call, live video call, in person, or a one-way recorded/AI interview. Empty if not an interview email.")
    interview_stage: str = Field(default="", description="Short label for which interview this is: 'Recruiter screen', 'Phone screen', 'Hiring manager', 'Technical', 'Panel', 'Final'. Empty if unknown or not an interview email.")
    interviewer: str = Field(default="", description="Name (and title) of the recruiter or interviewer if given, else empty string.")
    link: str = Field(description="The main action link (assessment/interview/offer), else empty string.")
    summary: str = Field(description="One sentence.")
    confidence: Literal["high", "medium", "low"]
