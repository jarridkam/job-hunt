"""Cover letter drafting that learns the candidate's voice from approved letters."""
from __future__ import annotations

from . import config, db, documents, llm

SYSTEM = """You write cover letters in the candidate's own voice, in first person, for the candidate to send.
Rules:
- Sincere and specific. Pick 2-3 concrete things from the candidate's background that genuinely match this role and explain them like a person would, not a brochure.
- Reference something specific about the role or company from the posting. No generic praise.
- Never invent experience, numbers, or skills that are not in the resume or profile. If a requirement is missing, do not claim it; it is fine to address it honestly in one clause or skip it.
- No cliches: no "I am writing to express my interest", "passionate", "dynamic", "leverage", "synergy", "I believe I would be a great fit", "hit the ground running".
- 220-330 words. Plain paragraphs, no headers, no bullet points, no placeholders like [Company]. End with a short, natural closing and the candidate's first name.
- Match the tone of the VOICE SAMPLES if given: sentence length, formality, how they talk about themselves. Those samples are letters the candidate wrote or approved; they are the best guide to how they sound.
Output only the letter text."""


def _voice_block() -> str:
    samples = documents.voice_samples(5)
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
        user.append("REQUIREMENTS NOT CLEARLY MET (do not claim these):\n- " + "\n- ".join(missing))
    if previous:
        user.append(f"PREVIOUS DRAFT:\n{previous}")
    if instruction:
        user.append(f"REVISION INSTRUCTION FROM THE CANDIDATE:\n{instruction}")
    else:
        user.append("Write the cover letter.")
    return llm.generate(SYSTEM, "\n\n".join(user), model=config.get("model_main"), effort="high", max_tokens=4000, purpose="cover letter")


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
