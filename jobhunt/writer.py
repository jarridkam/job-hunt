"""Cover letter drafting that learns the candidate's voice from approved letters."""
from __future__ import annotations

import re

from . import config, db, documents, llm, work

SYSTEM = """You write cover letters in the candidate's own voice, in first person, for the candidate to send.
Rules:
- This letter is about what the candidate can do. Sincere and specific. Pick 1-2 concrete things that genuinely match this role and explain them like a person would, not a brochure.
- Draw on everything: the resume, the checked projects, and personal work. A side project that shows the skill counts as much as a job. Choose whatever is closest to what this posting asks for, even if it isn't on the resume.
- Reference something specific about the role or company from the posting. No generic praise.
- Never invent experience, numbers, or skills that are not in the resume, profile or projects.
- Never mention what the candidate hasn't done. No gaps, no "I haven't", "I don't have", "I'm new to", "this is a stretch", no confessions or apologies, not even framed as honesty. If a requirement isn't met, leave it out and write about the nearest real thing instead, without pointing out that it's different. Being candid means plain and direct, not listing shortcomings.
- Don't raise obstacles such as visas, work permits or the distance of a move. State only what the candidate is ready to do.
- No cliches: no "I am writing to express my interest", "passionate", "dynamic", "leverage", "synergy", "I believe I would be a great fit", "hit the ground running".
- Keep it as short as it can be while still telling them what they asked for: 90-150 words, 2-3 short paragraphs. Respect the reader's time. Cut pleasantries, restating the posting, and anything they could get from the resume. If the posting asks for something specific in the letter, include it, even if that runs longer.
- Plain paragraphs, no headers, no bullet points, no placeholders like [Company]. End with one short closing line and the candidate's first name.
- Match the tone of the VOICE SAMPLES if given: sentence length, formality, how they talk about themselves. Those samples are letters the candidate wrote or approved; they are the best guide to how they sound.
Output only the letter text."""


# A letter that lists what you can't do. Old approved letters like this don't get copied, and a fresh draft like this is redone.
CONFESSES = re.compile(r"quick honesty|i'?ll be (honest|up ?front)|to be (honest|up ?front)|i haven'?t|i have not|i'?ve never|i have never|"
                       r"i don'?t have|i do not have|i lack|i'?m new to|a stretch|no direct experience|not something i'?ve", re.I)


def _voice_block() -> str:
    samples = [s for s in documents.voice_samples(12) if not CONFESSES.search(s["content"])][:5]
    if not samples:
        return ""
    parts = []
    for i, s in enumerate(samples, 1):
        parts.append(f"--- VOICE SAMPLE {i} ({s['title']}) ---\n{s['content'][:3500]}")
    return "\n\n".join(parts)


def draft(job: dict, instruction: str = "", previous: str = "") -> str:
    r = documents.active_resume()
    if not r:
        raise llm.LLMError("No active resume. Add one under Documents.")
    cand = config.candidate()
    fit_points = db.loads(job.get("fit_reasons"), [])
    missing = db.loads(job.get("fit_missing"), [])
    user = [f"CANDIDATE PROFILE:\n{cand.as_prompt()}", f"RESUME:\n{r['content']}"]
    projects = work.block()
    if projects:
        user.append(projects)
    if cand.voice_notes.strip():
        user.append(f"HOW THE CANDIDATE WANTS TO SOUND:\n{cand.voice_notes.strip()}")
    voice = _voice_block()
    if voice:
        user.append(f"VOICE SAMPLES:\n{voice}")
    user.append(f"JOB POSTING:\nTitle: {job['title']}\nCompany: {job.get('company')}\nLocation: {job.get('location')}\n\n"
                f"{(job.get('description') or '')[:10000]}")
    if fit_points:
        user.append("STRONGEST MATCHES (from a prior analysis):\n- " + "\n- ".join(fit_points))
    if missing:
        user.append("REQUIREMENTS NOT CLEARLY MET (do not claim these, and do not mention them at all):\n- " + "\n- ".join(missing))
    if previous:
        user.append(f"PREVIOUS DRAFT:\n{previous}")
    if instruction:
        user.append(f"REVISION INSTRUCTION FROM THE CANDIDATE:\n{instruction}")
    else:
        user.append("Write the cover letter.")
    prompt = "\n\n".join(user)
    letter = llm.generate(SYSTEM, prompt, model=config.get("model_main"), effort="high", max_tokens=4000, purpose="cover letter")
    if CONFESSES.search(letter):
        prompt += f"\n\nTHIS DRAFT BROKE THE RULES by mentioning what the candidate hasn't done. Rewrite it around what they can do:\n{letter}"
        letter = llm.generate(SYSTEM, prompt, model=config.get("model_main"), effort="high", max_tokens=4000, purpose="cover letter")
    return letter


def learn_from_approved(app_id: int) -> None:
    """Save the approved (user-edited) letter as a voice sample so future drafts sound more like them."""
    app = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not app or not (app.get("cover_letter") or "").strip():
        return
    title = f"Approved: {app.get('company') or ''} - {app.get('title') or ''}".strip(" -")
    existing = db.q1("SELECT id FROM documents WHERE kind='cover_letter' AND source='learned' AND title=?", (title,))
    now = db.now_iso()
    if existing:
        db.update("documents", existing["id"], {"content": app["cover_letter"], "updated_at": now})
    else:
        documents.add_document("cover_letter", title, app["cover_letter"], status="archived", source="learned",
                               notes="Auto-saved when you approved this letter. Used as a voice sample.")
    documents.archive_old_learned(12)
