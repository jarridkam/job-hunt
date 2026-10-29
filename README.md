# jobhunt

Local job-search machine: finds legitimate postings that fit your background, ranks them,
drafts cover letters in your voice, auto-fills and submits applications, and tracks
applications and assessments by reading your inbox.

Everything runs on your machine. Data lives in `data/jobhunt.db` (SQLite). Nothing is sent
anywhere except the Anthropic API (for scoring/drafting), the job sources, and your IMAP server.

## Run

```
run.bat
```

Opens http://127.0.0.1:8765. First run creates the virtualenv, installs deps, and downloads Chromium.
(Manual: `uv venv --python 3.12 .venv && uv pip install -e . && .venv\Scripts\python -m playwright install chromium`, then `.venv\Scripts\python -m jobhunt.cli serve`.)

`run-dev.bat` (= `serve --dev`) restarts the server whenever a `.py` / `.html` / `.css` under `jobhunt/` changes, and every open tab reloads itself about a second later. Use it while the app is being edited. Plain `run.bat` needs a manual restart after code changes. If a start fails with "address already in use", an old server is still running: close its console window or end `python.exe` in Task Manager.

## First-time setup (10 minutes)

1. **Settings > LLM**: paste your Anthropic API key. Click *Test API key*.
2. **Documents**: upload your resume (PDF/DOCX) or paste it. If you have cover letters you wrote and liked, add them too: they become *voice samples* so drafts sound like you.
3. **Settings > Search**: click *Suggest target titles from resume*, then edit the list. Add locations (or tick remote only).
4. **Settings > You**: name, email, phone, LinkedIn, degree, work authorization, sponsorship. This is what gets typed into application forms. *Extra Q&A* is free text the LLM can use for odd questions ("willing to relocate: yes").
   - *EEO* fields (gender, race, Hispanic/Latino, veteran, disability) default to `decline`; set an answer and the filler picks the matching option on Greenhouse/Lever/Workday wordings, falling back to decline when the form has no match.
5. Optional sources: Adzuna (free key at developer.adzuna.com) and JSearch (RapidAPI free tier) widen coverage a lot. Without keys you still get company ATS boards + Remotive/RemoteOK/WeWorkRemotely.
6. **Companies**: paste job links from careers sites you care about (Greenhouse/Lever/Ashby/Workable are detected automatically), or click *Add starter boards*. Boards are also discovered automatically when aggregator results link to one.
7. **Settings > Email tracker**: Gmail IMAP with an App Password (myaccount.google.com/apppasswords). Click *Test inbox login*.

## Daily loop

1. Dashboard > **Find & score jobs**. Fetches every source, drops scams/junk (legitimacy score), LLM-scores the rest against your resume. Jobs at or above *auto-queue score* go straight to the queue.
2. **Jobs** tab: review matches, tick the ones you like, *Queue selected & draft letters*.
3. **Queue**: open each application. Read the draft, edit until it sounds like you, then **Approve & apply now**.
   - A Chromium window opens, fills the form (profile, resume upload, cover letter, yes/no questions, EEO declines).
   - Questions it cannot map are answered by the LLM from your resume/profile; if it genuinely does not know, the browser stays open for 20 minutes so you finish that bit. It still detects the success page and records the submission.
   - Approving a letter saves it as a voice sample, so the next drafts drift toward your edits.
4. **Sync inbox** (Dashboard or Assessments): reads new mail, classifies it, and
   - creates/updates **Assessments** (platform, deadline, estimated time, link), marks them *missed* when the deadline passes;
   - moves **Applications** through screening / assessment / interview / offer / rejected;
   - creates an application record when it sees a confirmation for something you applied to elsewhere.
   - Order: newest mail first, every sync, so today's invite is never stuck behind the backlog. The per-sync cap counts LLM calls only; keep clicking *Sync inbox* until the run log says 0 remaining.
   - Deadlines: an explicit date in the email is used as stated (with its time zone, e.g. "Oct 28, 12:23 PM EDT"); a relative one ("within 7 days", "expires in 48 hours") is added to the time the email arrived; if the email says nothing, the deadline is received + N days (Settings > *assume N days*, default 7) and shown as **assumed**. Assumed deadlines never auto-mark an assessment missed. Everything displays in your local zone with the email's zone alongside. *Re-read assessment emails* re-runs the classifier on stored emails after a rule change (a few cents).
   - Opened / unopened: each assessment shows whether you have opened its link. Clicking *open* in the app records it; if you opened it from Gmail instead, click *mark opened*. "email unread" means Gmail still shows the invite as unread (checked on every sync).
   - How it decides: an email is only sent to the LLM if its subject/sender/body hits a keyword (assessment, HackerRank, Codility, interview, "your application", Greenhouse, Workday ...). The LLM then classifies it (assessment invite / reminder / completed, rejection, interview, offer, other) and extracts company, role, platform, deadline, estimated minutes, link.
   - Teach it: **Settings > Email tracker** has *Extra keywords* (platforms or sender addresses it misses, so they reach the LLM) and *Hints* (facts it should trust, e.g. "a HackerRank invite from Nintendo is for the Gameplay Engineer role", "ignore LinkedIn job alerts"). Hints are appended to the classifier prompt on every sync.

## Where auto-apply works

| Site type | What happens |
|---|---|
| Greenhouse, Lever, Ashby, Workable | Fills and submits. Greenhouse may show a reCAPTCHA: solve it in the open window. |
| Company sites embedding one of those | Same, via the embedded form or the ATS's direct form URL. |
| Anything else (Workday, iCIMS, Taleo, LinkedIn, Indeed) | Opens the page, fills what it can recognize, hands off to you. No LinkedIn/Indeed automation: it gets accounts banned. |

Turn off *auto-submit* in Settings to have it fill everything and let you press Submit yourself.

## Phone / remote access

The UI asks for a password. The first time, open it on the PC (http://127.0.0.1:8765) and set one; a password can only be set from the PC itself. Change it under Settings > Login password (logs out every device).

To reach it from your phone, put it behind Tailscale Funnel (free, stable https URL, your PC stays the server):

1. Install Tailscale on the PC: `winget install Tailscale.Tailscale`, then sign in from the tray icon.
2. Run `tailscale funnel --bg 8765`. The first time it prints a link to enable Funnel for your account; open it, approve, run the command again.
3. It prints `https://<pc-name>.<tailnet>.ts.net/`. Open that on your phone, log in, and add it to your home screen.

The setting survives reboots; jobhunt just has to be running. `tailscale funnel --https=443 off` turns it off. Auto-apply still opens its browser on the PC, so take-overs (captchas, odd questions) happen there.

## Credits left

Anthropic has no balance endpoint for individual accounts, so the app tracks spend itself: every call's token usage is priced locally (`llm_usage` table, prices in `jobhunt/llm.py`). On the Dashboard, type the balance the console shows (purchased + promotional, platform.claude.com/settings/billing) and click *Set balance*; from then on the card shows an estimated remaining balance, today's spend, and a per-task breakdown. Re-enter the balance after you top up. The estimate drifts only if prices change or something outside this app uses the same key.

## Cost

Scoring uses the *bulk* model, drafting uses the *main* model. Both default to `claude-sonnet-5-5`; pick others
from the dropdowns in Settings. Scoring a few hundred jobs with Sonnet costs ~$1-2; `claude-haiku-5-5`
is ~20x cheaper still. *Max jobs to LLM-score per run* is a hard cap per click.

## CLI

```
.venv\Scripts\python -m jobhunt.cli fetch     # pull jobs
.venv\Scripts\python -m jobhunt.cli score     # LLM-score unscored jobs
.venv\Scripts\python -m jobhunt.cli email     # sync inbox
.venv\Scripts\python -m jobhunt.cli apply 12  # auto-apply application #12
```

## Layout

```
jobhunt/
  db.py            SQLite schema + helpers
  config.py        settings spec (what the Settings page shows)
  llm.py           Anthropic SDK wrapper (text + structured output)
  documents.py     resumes / cover letters, PDF/DOCX text extraction
  sources/         boards.py (Greenhouse/Lever/Ashby/Workable), aggregators.py (Adzuna, JSearch, remote boards)
  legit.py         heuristic legitimacy score
  matcher.py       LLM fit scoring, title prefilter, search-profile suggestion
  writer.py        cover letter drafting + voice learning
  queue.py         application queue state
  pipeline.py      fetch -> dedupe -> legit -> store, ATS board discovery
  apply/           fields.py (form discovery/classification), runner.py (Playwright fill + submit)
  email_tracker.py IMAP sync -> assessments + application events
  tasks.py         background threads with run logs
  web/             FastAPI app + templates
```
