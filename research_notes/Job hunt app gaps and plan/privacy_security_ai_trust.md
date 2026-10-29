# Privacy, security and AI-transparency concerns in job-search / auto-apply tools (2023-2026), and what a trustworthy self-hosted alternative should do

Research date: 2026-10-29. Scope: Teal, Huntr, Simplify, Careerflow, LazyApply, Sonara, LoopCV, JobCopilot, Jobright, resume-builder/ATS tools; Google restricted-scope policy; self-hosted security practice. Many sources in this space are vendor blogs that sell a competing product; bias is flagged per finding.

## Key Question 1: Documented privacy incidents, criticisms, and data-collection practices for the named tools

### Takeaway
No confirmed breach was found for Teal, Huntr, Simplify, Careerflow, LazyApply, LoopCV, JobCopilot or Jobright in 2023-2026; the concrete incidents are in the adjacent resume-builder/ATS space (LiveCareer 5.1M resumes, TalentHook ~26M resumes, both 2025, both misconfigured cloud storage). The documented criticisms of the named tools are structural: broad data collection, recruiter-matching without an explicit apply, cross-context ad sharing under CCPA, US-only hosting, a product (Sonara) that shut down and left users without their application history, and account-ban risk from LinkedIn's blanket prohibition on automation.

### Cited Findings

**Breaches / incidents (adjacent resume-builder and ATS space)**
- LiveCareer (resume builder): a misconfigured Azure storage container exposed over 5.1 million files, mostly resumes from 2016-2025, with names, contact details, home addresses and work histories; no authentication, encryption or download restrictions; the company issued no public statement as of publication (July 2025) — [Cybernews](https://cybernews.com/security/livecareer-resume-data-leak/); also [SC World](https://www.scworld.com/brief/over-5m-job-seekers-data-accidentally-exposed-by-livecareer)
- TalentHook (recruiting software/ATS): open instance exposed ~26 million resumes with names, emails, phones, employment histories; found Jan 2025, disclosed Apr 2025 — [Cybernews](https://cybernews.com/security/talenthook-data-leak-exposes-millions/)
- HireClick (Feb 2025): a secondary blog reports ~5.7M resumes exposed via a misconfigured S3 bucket; single-source, lower reliability — [Daily Security Review](https://dailysecurityreview.com/security-spotlight/job-seeker-data-breach-exposes-5-1-million-resumes-through-misconfigured-cloud-storage/)
- Pattern worth noting for extensions generally: the "Save image as Type" Chrome extension (1M+ users) was sold to new owners in Nov 2025 and then turned into spyware/affiliate hijacker; Google removed it only after Microsoft Edge did (2026) — [PCWorld](https://www.pcworld.com/article/3092299/my-most-useful-chrome-extension-was-stealing-my-data-for-years.html). Not a job tool, but the "ownership transfer then malicious update" pattern applies to any extension a job seeker installs.
- Extension Auditor lists a job-related extension "Optimum Talent Job Tracker" (~1,000 users) as removed from the Chrome Web Store as malware; no removal date given and unconfirmed elsewhere — [Extension Auditor](https://www.extensionauditor.com/scan/optimum-talent-job-tracker-glkjdijkmgjhcohpaaepkagebhahokgj)

**Simplify (privacy policy last updated Aug 19, 2026)**
- Collects resume, education/employment history, work-authorization status, saved application answers, optional demographic self-ID, date of birth, phone, location, imported contacts; extension collects job postings viewed, the structure and values of application forms, and keeps a local copy of profile/resume/recent answers; a support report may include a recording of the user's interaction with the application page — [Simplify privacy policy](https://simplify.jobs/privacy)
- Recruiter matching: Simplify may present the user to employers or recruiters when it sees a potential fit "even if you haven't applied"; it does not give them database access or bulk exports; saved answers and self-ID data are excluded from matching — [Simplify privacy policy](https://simplify.jobs/privacy)
- States it does not sell personal information for money, but in the last 12 months "shared" identifiers, internet/network activity and conversion events with ad platforms (Google, Meta) for cross-context behavioral advertising (the CCPA "sharing" definition); honors Global Privacy Control — [Simplify privacy policy](https://simplify.jobs/privacy)
- Gmail (if connected): identifies/categorizes job-related emails, stores only metadata and short previews (sender, subject, snippet, category) not full content or attachments; Google data not used for ads, not sold, not used to train generalized AI models — [Simplify privacy policy](https://simplify.jobs/privacy)
- Retention: active data deleted or anonymized on account deletion; backups/logs/provider copies "isolated, then deleted or expire over time"; payment/tax records kept as legally required; export is by emailed request, not self-service — [Simplify privacy policy](https://simplify.jobs/privacy)
- A third-party review (LoopCV, competitor) claims Simplify's privacy policy had not been updated since June 2021 and that data is hosted in the US regardless of user location (GDPR concern) — [LoopCV directory](https://www.loopcv.pro/directory/simplify/). Contradicted by the current policy date (Aug 2026), so the "stale policy" claim is out of date.

**Teal (privacy policy last updated Aug 12, 2026)**
- Google connection (optional) accesses name/email/profile image, Google Contacts and Other Contacts, Calendar events/attendees/availability, and authorization credentials; read-only; Gmail is not named in the policy; states compliance with Google API Services User Data Policy Limited Use — [Teal privacy policy](https://www.tealhq.com/privacy-policy)
- Resume and job-description content is processed by Teal's AI and may be sent to third-party AI providers such as OpenAI; career content "may be used to improve AI models in anonymized, aggregated form"; Google Workspace data is not used to train generalized models — [Teal privacy policy](https://www.tealhq.com/privacy-policy)
- Does not sell personal information; no mention of sharing with employers/recruiters; deletes/anonymizes from active systems within 30 days of deletion request; disconnecting Google removes credentials but does not delete previously imported data (needs account deletion or email request) — [Teal privacy policy](https://www.tealhq.com/privacy-policy)
- Chrome Web Store listing states data is not sold to third parties — [Teal - Chrome Web Store](https://chromewebstore.google.com/detail/teal-job-search-companion/opafjjlpbiaicbbgifbejoochmmeikep)

**Huntr (privacy policy last modified Feb 8, 2024)**
- Says it does not share data with third-party organizations or employers without consent and "will never sell personal data"; carve-out for hosting partners/service providers; non-personal aggregated data may be disclosed without restriction and provided to business partners — [Huntr privacy](https://huntr.co/privacy); Chrome listing: data not sold outside approved use cases — [Huntr - Chrome Web Store privacy tab](https://chromewebstore.google.com/detail/huntr-job-search-tracker/mihdfbecejheednfigjpdacgeilhlmnf/privacy)

**Sonara (privacy policy last updated Jul 21, 2026)**
- Policy says it may share collected information with affiliates, service providers, job boards, potential employers and recruiters, "and others"; its AI searches and applies on the user's behalf — [Sonara privacy policy](https://www.sonara.ai/privacy-policy)
- The original Sonara "shut down without warning in February 2024" and locked users out of their application data mid-search; later acquired by BOLD (resume-builder company); Sonara did not respond to the publisher's Oct 16, 2026 checks — [Resumly (competitor, vendor bias)](https://www.resumly.ai/best/best-job-application-bots); LoopCV (competitor) confirms Sonara "ceased operating as an independent product" and that former users had to rebuild application history from email/exports/memory, but gives no date — [LoopCV blog, Jul 3, 2026](https://blog.loopcv.pro/what-happened-to-sonara/)

**Jobright (privacy policy)**
- Employers/recruiters can view candidates only in anonymized or limited form; name and direct contact released only when the candidate applies, accepts an invite, or turns on visibility; employers may not re-identify or resell; Gmail access, if connected, limited to finding employers' verification-code emails — [Jobright privacy](https://jobright.ai/legal/privacy)

**LoopCV**
- Does not share personal information publicly without consent but may share with third parties "when needed to complete applications"; data copy or account deletion by emailing support; product also emails recruiters directly as a separate outreach channel — [LoopCV privacy](https://www.loopcv.pro/privacy/)

**LazyApply**
- Chrome extension that fills and submits forms on boards such as Greenhouse, Dice, ZipRecruiter using the stored profile (name, email, work history, resume PDF, screening answers); runs inside the user's logged-in browser — [LoopCV review (competitor)](https://blog.loopcv.pro/lazyapply-review/); [Resumly (competitor)](https://www.resumly.ai/best/best-job-application-bots)
- Appears on Josef Kadlec's public "Complete List of Blacklisted LinkedIn Plugins"; reviewers report LinkedIn warnings after ~150 applications in a day — [scale.jobs (competitor)](https://scale.jobs/blog/lazyapply-risk-profile-banned-linkedin); [Backdoor (competitor)](https://backdoorai.app/blog/auto-apply-linkedin-ban)
- Trustpilot rating cited as 2.3 — [NoxJobs (competitor)](https://noxjobs.com/compare/lazyapply-review-2-3-trustpilot-rating)

**LinkedIn's own policy (primary)**
- LinkedIn does not allow "any third party software," including crawlers, bots, browser plug-ins or extensions that scrape data, change the site's appearance, or automate activity; members using them violate the User Agreement and "risk having their accounts restricted or shut down"; tools may stop working without notice — [LinkedIn Help](https://www.linkedin.com/help/linkedin/answer/a1341387)

**JobCopilot**
- A JobCopilot Trustpilot reviewer (2026) reported almost submitting "a W-4 and government ID to a fake company" via the tool — cited by [Resumly (competitor)](https://www.resumly.ai/best/best-job-application-bots); unverified beyond that citation
- PitchHired (competitor, Aug 11, 2026) names "job-board credential sharing" as JobCopilot's main risk and rates both JobCopilot and Sonara a poor fit where "privacy, account safety, or exact company targeting matters"; advises avoiding sensitive identity documents — [PitchHired](https://pitchhired.com/blog/jobcopilot-vs-sonara)
- JobCopilot's own marketing says it "connects directly with over 500,000 company career sites" (FAQ says 300,000) and "auto-applies through official channels"; it does not state whether it needs job-board logins — [JobCopilot blog, May 14, 2025](https://jobcopilot.com/loopcv-best-alternative/)

### Inferences
- The realistic threat for a job seeker is not a hacker targeting their tracker; it is (a) a vendor's misconfigured cloud bucket leaking resumes wholesale (LiveCareer, TalentHook), (b) quiet recruiter-matching and ad-platform "sharing" baked into policies, (c) a vendor shutting down and taking the application history with it (Sonara), and (d) a platform ban for using automation against LinkedIn's terms.
- Policies that were last updated in 2024 (Huntr) or that say "may share with ... others" (Sonara) give far less assurance than Simplify's and Jobright's more specific 2026 policies. Teal's clause allowing resume content to improve AI models in aggregated form is the kind of clause a privacy-conscious user would want to be able to opt out of.
- A self-hosted tool removes the vendor shutdown and recruiter-sharing risks entirely, but inherits the LinkedIn/ToS ban risk if it automates on LinkedIn.

### Gaps
- No primary-source (news or regulator) report of a breach, GDPR/CCPA complaint, or enforcement action against Teal, Huntr, Simplify, Careerflow, LazyApply, LoopCV, JobCopilot or Jobright was found. Absence of evidence, not evidence of absence.
- Careerflow was not covered by any search result; its privacy policy was not retrieved.
- JobCopilot's privacy policy was not retrieved; claims about credential sharing come only from a competitor.
- The Simplify Trustpilot complaint alleging published personal information (3 helpful votes) could not be verified.
- Sonara's February 2024 shutdown date rests on a single competitor source.

## Key Question 2: What permissions do their Chrome extensions and Gmail integrations request, and what do users say?

### Takeaway
Autofill extensions necessarily read and write application-form fields on every site, so they request broad host access; Simplify's extension was flagged by an automated scanner for cookies, webRequest and webNavigation permissions with `<all_urls>` access (Medium risk, 73/100). Gmail integrations in this category are typically scoped narrowly on paper (Simplify: metadata + snippets only; Jobright: verification-code emails only), but any Gmail read scope is a Google "restricted" scope with annual verification and, if data touches a server, a paid CASA security assessment.

### Cited Findings
- Simplify Copilot extension: automated scanner CRXPlorer rates it Medium risk, security score 73/100, flagging cookies, webRequest and webNavigation permissions with `<all_urls>` host access as broader than autofill needs (heuristic, not a confirmed vulnerability) — [CRXPlorer](https://crxplorer.com/extension/pbanhockgagggenencehbnadejlgchfc/simplify-copilot-autofill-job-applications-job-tracker-ai-resumes); listing at [Chrome Web Store](https://chromewebstore.google.com/detail/simplify-copilot-autofill/pbanhockgagggenencehbnadejlgchfc)
- Simplify's own policy confirms the extension collects "the structure and values of application forms" and job postings viewed, and that support reports may include a recording of the interaction — [Simplify privacy policy](https://simplify.jobs/privacy)
- User-facing guidance from a job-search vendor: check chrome://extensions, treat "all websites" access as a red flag unless documented, and restrict site access to on-click where functionality allows — [JobWizard (vendor)](https://jobwizard.ai/blog/chrome-extension-safety-job-applications-permissions-resume-data-review-before-submit)
- Google scope policy: Gmail scopes including gmail.readonly, gmail.compose, gmail.insert, gmail.modify, gmail.metadata, gmail.settings.basic, gmail.settings.sharing and full https://mail.google.com/ are classed as restricted; apps requesting them need restricted-scope verification and, if they store/transmit the data on servers, an annual security assessment — [Nylas developer guide](https://developer.nylas.com/docs/provider-guides/google/google-verification-security-assessment-guide/) (third-party summary; Google's own page defers the list to its FAQ)
- Google (primary): "If you store or transmit restricted scope data on servers, then you need to complete a security assessment" by Google-empanelled assessors; reverification and reassessment at least every 12 months after the Letter of Assessment; adding a new restricted scope may require reassessment; privacy policy must disclose how Google user data is accessed, used, stored and shared and meet Limited Use — [Google restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- Google (primary): exemptions from verification include personal use ("used only by you or a few people you know personally"), development/testing/staging, internal Workspace use, and service-account-only apps; apps in testing show a tester warning screen, have a user cap, and limited refresh-token lifetimes (cap number not stated on this page) — [Google restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- Google Workspace guide: restricted scopes require basic verification, additional verification and a security assessment; advises seeking non-sensitive alternatives; internal-only apps need no further Google review — [Google Workspace OAuth consent guide](https://developers.google.com/workspace/guides/configure-oauth-consent)
- Third-party summaries: unverified apps capped at ~100 users with a warning screen; CASA assessment cost reported from a few thousand dollars to tens of thousands, 4-12 weeks — [Deepstrike](https://deepstrike.io/blog/google-casa-security-assessment-2025); [Agentic Fabriq](https://www.agenticfabriq.com/blog/google-oauth-verification-casa)
- Example: CellCog reported Google approved its OAuth app on Sep 13, 2026 for seven Gmail/Analytics scopes after a CASA Tier 2 assessment — [CellCog](https://cellcog.ai/blog/casa-security-assessment/)
- Google's "less secure apps" (plain password IMAP) shutdown: Workspace accounts lost password-based IMAP access on May 1, 2025 (dates slipped from Jun 15, 2024 -> Mar 14, 2025 -> May 1, 2025); OAuth is the recommended path; app passwords remain an allowed exception requiring 2-Step Verification, and Workspace admins can disable them — [Google Workspace Updates blog, Sep 2023](https://workspaceupdates.googleblog.com/2023/09/winding-down-google-sync-and-less-secure-apps-support.html); [Google Admin Help](https://support.google.com/a/answer/6260879?hl=en); [Google transition guide](https://knowledge.workspace.google.com/admin/sync/transition-from-less-secure-apps-to-oauth)

### Inferences
- For a single-user personal agent, Google's personal-use exemption means an OAuth client in "testing" with the owner as the sole test user is legitimate and avoids CASA entirely; the costs are the tester warning screen and shorter refresh-token lifetimes (Google documents 7-day expiry for testing-mode refresh tokens in its OAuth docs; not retrieved here, flagged as a gap). An app password over IMAP is the simpler alternative for a personal Gmail account with 2SV on, at the cost of a long-lived secret that grants full mailbox access and must be encrypted at rest.
- Commercial tools that keep Gmail metadata server-side (Simplify) are exactly the "store or transmit on servers" case, which is why their policies carry explicit Limited Use language.

### Gaps
- The exact permission manifests for Teal, Huntr, LazyApply and Careerflow extensions were not retrieved (Chrome Web Store pages could not be fetched in full).
- Google's own page listing the current restricted Gmail scopes and the 100-user cap number was not retrieved in full; the scope list comes from a third-party summary.
- No primary Reddit/HN threads specifically about these tools' permissions were surfaced by search.

## Key Question 3: Do any tools require sharing LinkedIn/Indeed passwords? Consequences?

### Takeaway
No retrieved primary source shows a named tool asking for the user's LinkedIn or Indeed password. Browser-extension tools (LazyApply, Simplify) run inside the user's already-logged-in browser; cloud agents (JobCopilot, Sonara, LoopCV) claim to apply via company career sites "through official channels" or via email. The documented consequence of automation is LinkedIn account restriction, not credential theft.

### Cited Findings
- LazyApply works while "your own browser stays open and logged in"; for server-side agents "your job-board accounts stay out of the loop" (no detail given) — [Resumly (competitor)](https://www.resumly.ai/best/best-job-application-bots)
- LazyApply "uses your LinkedIn login when you run it on LinkedIn" and its homepage claims profiles will never be blocked, with no explanation — [LoopCV review (competitor)](https://blog.loopcv.pro/lazyapply-review/)
- PitchHired characterizes JobCopilot's main risk as "job-board credential sharing" and says the tool asks users to trust it with job-board access — [PitchHired (competitor)](https://pitchhired.com/blog/jobcopilot-vs-sonara). JobCopilot's own page does not say whether it needs logins — [JobCopilot](https://jobcopilot.com/loopcv-best-alternative/)
- LinkedIn: automation tools violate the User Agreement; accounts risk restriction or shutdown — [LinkedIn Help](https://www.linkedin.com/help/linkedin/answer/a1341387)
- Competitor blogs claim bans are rarely reversed (under 10% of appeals succeed) — [Backdoor (promotional, unverified)](https://backdoorai.app/blog/auto-apply-linkedin-ban)
- Massive (cloud auto-apply) routes applications through a proxy email domain, which Adzuna's review flagged as a deliverability risk; some users saw employer replies as blank screens — cited by [Resumly](https://www.resumly.ai/best/best-job-application-bots)

### Inferences
- The "password sharing" concern in this category is mostly about cloud agents needing to act as the user on ATS portals (Workday, Greenhouse accounts created per employer) rather than LinkedIn itself. A self-hosted agent that stores per-ATS credentials faces the same design problem and must encrypt them at rest and keep them off any shared host.
- Proxy email domains (Massive) show a second failure mode: inserting the vendor between the applicant and the employer's replies.

### Gaps
- No terms-of-service or onboarding screenshot confirming that LazyApply, JobCopilot, Sonara or LoopCV collect LinkedIn/Indeed passwords was found. Treat "credential sharing" claims as unconfirmed competitor characterizations.
- Indeed's automation policy was not retrieved.

## Key Question 4: How do tools explain AI decisions (fit scores, generated answers)? Good and bad transparency; reactions to hallucinated content

### Takeaway
Transparency is shallow across the category: Jobright shows three sub-scores (experience, skill, industry) but no reasoning or weights, and reviewers disagree on whether that counts as transparent; no retrieved tool labels which form answers were AI-generated or shows confidence. The best-documented failure modes are wrong answers in sensitive fields (visa sponsorship, salary, demographics), resumes with invented skills and metrics, and generic near-identical letters that recruiters now filter.

### Cited Findings

**Fit-score transparency**
- Jobright App Store listing: match score compares skills, experience and salary range in the resume to the job on a 0-100 scale; weighting not explained — [Jobright - App Store](https://apps.apple.com/us/app/jobright-ai-job-search/id6738236788)
- FavTutor (2026): calls the score "not a black box"; opening a job shows e.g. Experience Level 100%, Skill 69%, Industry Experience 80% — [FavTutor](https://favtutor.com/jobright-ai-review/)
- HireCarta (2026): same three components, but "there's no way to see why you got those scores"; calls them opaque — [HireCarta](https://hirecarta.com/blog/jobright-review)
- Resumly lists "fit scores & gap analysis" via semantic matching but does not explain calculation — [Resumly](https://www.resumly.ai/best/best-job-application-bots)
- JobCopilot's dashboard shows "what's been submitted, where, and how" and "what roles were skipped, and why" (explains skips, not matches); offers editing of past responses, i.e., review after the fact — [JobCopilot](https://jobcopilot.com/loopcv-best-alternative/); PitchHired says JobCopilot offers a review-before-submit mode and calls it the safer option, while Sonara runs with less hands-on review so users must spot-check after submission — [PitchHired](https://pitchhired.com/blog/jobcopilot-vs-sonara)
- Resumly claims its Autopilot "asks instead of guessing" when a form needs a fact only the user knows (vendor claim, unverified) — [Resumly](https://www.resumly.ai/best/best-job-application-bots)

**Hallucinated / wrong AI content**
- LazyApply: reviewers report it populating H-1B visa sponsorship status incorrectly across an entire batch — [scale.jobs (competitor)](https://scale.jobs/blog/lazyapply-risk-profile-banned-linkedin); testers reported wrong answers in salary and visa fields; one said it "fails 90% of the time" — [Resumly](https://www.resumly.ai/best/best-job-application-bots)
- Jobright: "multiple Reddit users reported the resume AI inserting skills and metrics they do not have" (2026, as cited by a competitor) — [Resumly](https://www.resumly.ai/best/best-job-application-bots)
- AIApply: early-2026 reviews describe applications sent in the wrong language, location or seniority despite correct settings — [Resumly](https://www.resumly.ai/best/best-job-application-bots)
- Massive: Adzuna's review documented the resume AI hallucinating skills the user lacked — cited by [Resumly](https://www.resumly.ai/best/best-job-application-bots)
- Vendor-described bot failure modes: picking a default response, misreading eligibility, applying an old answer to a new requirement, attaching the wrong resume file; employers rate-limit or flag suspicious submission patterns — [JobWizard (vendor)](https://jobwizard.ai/blog/ai-auto-apply-for-jobs-reddit-what-goes-wrong-safer-autofill-review-subm)
- First-hand experiment (Oct 3, 2025): author let three unnamed AI agents submit 819 applications in a month; the AI filled demographic fields (gender, military, disability) and motivation questions; he reviewed early applications then spot-checked because "you can never quite be sure how an AI is going to characterize your experience"; agents applied to organizations he did not want (including political ones); result 71 responses (8.6%), 5 interviews (0.6%), two with companies he declined; he judged a non-AI approach would likely have done better — [Job Search with AI (Substack)](https://jobsearchwithai.substack.com/p/i-let-ai-apply-to-819-jobs-for-me)
- Embarrassing public example: an IIT graduate's AI-generated cover letter went viral (July 2023) after he left technical jargon from the generator in the letter — [Analytics Vidhya](https://www.analyticsvidhya.com/blog/2023/07/iit-grads-ai-generated-cover-letter-leaves-everyone-in-stitches/)

**Recruiter-side reaction and detection**
- Forbes (Oct 20, 2024) reports 80% of hiring managers dislike seeing AI-generated CVs and cover letters (underlying survey not verified) — [Forbes](https://www.forbes.com/sites/bryanrobinson/2024/10/20/why-80-of-hiring-managers-discard-ai-generated-job-applications-from-career-seekers/)
- Recruiters describe being buried under near-identical AI letters and resumes with facts that do not match across documents; "AI tends to fabricate skills and experiences that match the job description perfectly" — [Sprad](https://sprad.io/blog/ai-job-application-mistakes-12-ways-candidates-damage-their-chances-and-how-to-fix-them); [ResumeToJobs](https://resumetojobs.com/blog/recruiters-reject-ai-generated-applications-2026)
- HR teams are deploying AI cover-letter detectors (Pangram markets one) to filter "noise" — [Pangram (vendor)](https://www.pangram.com/blog/ai-cover-letter-checker)
- Fast Company warns the risk of AI-polished exaggeration "isn't just not getting the job. It's losing your reputation" — [Fast Company](https://www.fastcompany.com/91317926/)
- Analogous transparency fix outside hiring: after Cursor's support bot invented a policy (Apr 2025), the company began labeling AI-generated support emails as such — [The Register](https://www.theregister.com/2025/04/18/cursor_ai_support_bot_lies/)

### Inferences
- "Good" transparency in this category currently means: per-job sub-scores (Jobright), explicit reasons for skipped roles (JobCopilot), review-before-submit mode, and asking the user rather than guessing on unknown facts (Resumly's claim). None of the retrieved tools documents labeling AI-generated answers, showing a confidence level, or linking a fit score to the specific resume lines and job requirements that drove it.
- The highest-harm errors are in categorical compliance fields (visa, work authorization, demographics, salary) where a wrong default is both embarrassing and potentially disqualifying or legally consequential. A personal agent should never auto-fill these from inference; they should come from an explicit, user-set profile value or be left blank and flagged.
- Cross-document consistency (resume vs cover letter vs form answers) is a recruiter red flag; a personal agent should generate from one canonical fact base and show diffs.

### Gaps
- No primary Reddit or Hacker News threads were retrieved (the `site:reddit.com` filter was not honored by the search tool); Reddit claims are relayed through competitor blogs.
- No documentation of any tool showing per-answer "AI-generated" labels or confidence; could not confirm whether Teal's or Careerflow's resume match scores show reasoning.
- The Forbes 80% figure could not be traced to its survey.

## Key Question 5: Concrete security checklist for a single-user self-hosted FastAPI/SQLite app on a small VPS (2025-2026 practice)

### Takeaway
The sourced consensus for a single-user VPS is: key-only SSH with no root login, default-deny firewall exposing only 22/80/443, fail2ban, unattended security updates, Caddy for automatic TLS and HTTP->HTTPS redirect, encrypted database at rest (SQLCipher whole-file or Fernet per-field, with MultiFernet for rotation), secrets kept out of git and logs with revoke-then-rotate on exposure, tamper-resistant audit logging, encrypted backups, and Playwright run as non-root with the sandbox decision made explicitly rather than copying `--no-sandbox`.

### Cited Findings

**VPS baseline**
- Common checklist items: disable root SSH login, key-only auth, non-root sudo user, default-deny firewall, automatic security updates, AppArmor, file-integrity monitoring; allow only SSH, 80, 443 — [USAVPS 2026 checklist](https://usavps.com/blog/post/vps-security-hardening-checklist-linux/); [dchost](https://www.dchost.com/blog/en/vps-security-hardening-checklist-sshd_config-fail2ban-auto-updates-and-no-root-ssh/); [GitHub gist with audit script](https://gist.github.com/rodbland2021/af83034b6ab46255fb8ae762d3b02638)
- fail2ban sshd jail examples: maxretry 3, bantime 3600, findtime 600; or bantime 86400 — [Retzor 2025](https://retzor.com/blog/vps-security-hardening-25-point-checklist-for-2025/); [VPS.DO](https://vps.do/vps-security-hardening-checklist-10-steps-to-protect-your-server-in-2025/). One source notes fail2ban matters less once password SSH auth is off but remains useful for app login pages — [selfvps](https://selfvps.net/en/post/vps-security-hardening-2026/)
- "Database not exposed to public internet"; security headers and A+ TLS configuration — [USAVPS 2026 audit checklist](https://usavps.com/blog/post/vps-security-audit-checklist-hardening-2026/)

**TLS (Caddy, primary docs)**
- Caddy serves all sites over HTTPS by default, obtains certificates from Let's Encrypt (fallback ZeroSSL) via HTTP-01 (port 80) and TLS-ALPN (port 443) challenges, renews automatically, and redirects HTTP to HTTPS without extra config; requires A/AAAA records pointing at the server, ports 80/443 open, and a writable persistent data directory; use Let's Encrypt staging while testing to avoid rate limits — [Caddy automatic HTTPS docs](https://caddyserver.com/docs/automatic-https)

**Encryption at rest**
- SQLCipher: fork of SQLite with 256-bit AES of the whole database file at the pager layer; standard SQLite API; passphrase goes through PBKDF2; vendor-cited overhead ~5-15%; encryption applies only to new databases, existing plaintext DBs must be converted via ATTACH + sqlcipher_export(); SQLCipher 4 will not open 1.x-3.x databases by default — [Zetetic SQLCipher](https://www.zetetic.net/sqlcipher/about/); [sqlcipher GitHub](https://github.com/sqlcipher/sqlcipher)
- Fernet (cryptography.io, primary): AES-128-CBC with PKCS7 + HMAC-SHA256, CSPRNG IVs; "a message encrypted using it cannot be manipulated or read without the key"; `Fernet.generate_key()` yields URL-safe base64 32-byte keys; MultiFernet encrypts with the first key, tries each key on decrypt, and `rotate()` re-encrypts under the primary key; optional `ttl` on decrypt; token timestamp is stored in plaintext; data must fit in memory, unsuitable for very large files — [cryptography.io Fernet docs](https://cryptography.io/en/latest/fernet/)
- OWASP: use authenticated encryption (AES-256-GCM); do not store encryption keys alongside the data unless envelope-encrypted; encrypt backups and restrict access to backup storage — [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

**Secrets handling**
- OWASP: never hardcode secrets; environment variables "are generally accessible to all processes and may be included in logs or system dumps," so prefer runtime retrieval or mounted secret files; add pre-commit secret detection; on exposure "immediate revocation" first, then rotate and scrub history; rotate regularly and automate; do not rotate user passwords on a schedule, only on suspicion of compromise; least privilege per secret, no shared "big secrets"; audit who requested/used/updated each secret, protect logs from tampering, never log plaintext secrets, keep clocks synced — [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

**Gmail access: app password vs OAuth**
- Google: OAuth is the recommended method; app passwords remain an allowed exception (require 2-Step Verification; Workspace admins can disable) — [Google transition guide](https://knowledge.workspace.google.com/admin/sync/transition-from-less-secure-apps-to-oauth); [Google Admin Help](https://support.google.com/a/answer/6260879?hl=en)
- Personal-use OAuth apps are exempt from verification; testing-mode apps carry a warning screen, user cap and limited refresh-token lifetime — [Google restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)

**Playwright / browser automation**
- Playwright's `chromiumSandbox` defaults to false; removing `--no-sandbox` does not turn the sandbox on; official Docker images run as root, which rules out the sandbox; for sandboxed runs use a non-root user with a seccomp profile permitting user namespaces; `--no-sandbox`, `--disable-setuid-sandbox`, `--ignore-certificate-errors` and `ignoreDefaultArgs: true` are flagged as dangerous and should be documented exceptions, never global defaults; raise `/dev/shm` with `--shm-size=1g` rather than `--disable-dev-shm-usage`; pin the image tag to the npm Playwright version — [qaskills, Aug 8, 2026](https://qaskills.sh/blog/playwright-browser-launch-args-hardening)
- Kubernetes default seccomp blocks user namespaces so containers commonly force `--no-sandbox`; compensating control is a stronger runtime (gVisor/Kata); treat page content as hostile, use least-privilege short-lived credentials, never print cookies/tokens, note there is no egress policy by default and downloads are unscanned — [Orka issue #911](https://github.com/orka-agents/orka/issues/911)
- Run the browser automation server in a container as non-root with a minimal mounted filesystem — [awesome-testing, Nov 2025](https://www.awesome-testing.com/2025/11/playwright-mcp-security)
- Chromium's sandbox needs user-namespace permissions; without it, untrusted web content runs with the automation process's privileges — [OrchordsBrowserPilot issue #106](https://github.com/ORCHORDS/OrchordsBrowserPilot/issues/106)

### Inferences (synthesized checklist for the jobhunt app)
Each item below follows from the cited sources above; items marked (gap) are standard practice not directly sourced in this research.
1. Host: non-root user, SSH keys only, `PermitRootLogin no`, ufw default deny with 22/80/443, fail2ban sshd jail plus a jail on the app's login endpoint, unattended-upgrades. Bind FastAPI/uvicorn to 127.0.0.1 only; Caddy is the only public listener.
2. TLS: Caddy with a real domain; HTTP->HTTPS redirect is automatic; add security headers (HSTS, CSP, X-Frame-Options) in the Caddyfile.
3. Auth: single-user login with a strong passphrase hashed with Argon2id (gap: OWASP Password Storage cheat sheet not fetched), session cookies Secure/HttpOnly/SameSite, optional TOTP, and rate limiting on the login route (e.g., slowapi) in addition to fail2ban.
4. Encryption at rest: either SQLCipher for the whole file (simplest, SQL keeps working, ~5-15% overhead, migration via sqlcipher_export) or Fernet for the sensitive columns (Gmail app password, ATS credentials, API keys, resume text) with MultiFernet to rotate. Keep the key outside the DB and outside the repo (file with 0600 perms or systemd credential), never in an env var that ends up in logs. Encrypt backups with the same discipline and store the key separately from backups.
5. Gmail: for a single user, prefer an OAuth client in testing mode with gmail.readonly (or gmail.metadata if only subjects/senders are needed) because it is revocable per-app in Google Account settings and scope-limited; an app password is acceptable for IMAP if OAuth refresh-token expiry in testing mode is a nuisance, but it grants full mailbox access and must be Fernet-encrypted and rotated. Never request https://mail.google.com/ full scope when read-only suffices (Google's own advice).
6. ATS/job-board credentials: store encrypted, one secret per site, never on LinkedIn (ToS ban risk documented); prefer "review-before-submit" so credentials are used interactively rather than by an unattended bot.
7. Audit log: append-only table of every AI generation, every form fill, every email read, every credential use, with timestamp and the model/prompt version; protect from deletion (separate table or file with restricted perms); never log secret values.
8. Export/delete everything: a one-click full export (SQLite dump + attachments as a zip) and a delete-all that also wipes backups within a stated window; this directly answers the Sonara shutdown and Teal "disconnect doesn't delete imported data" problems.
9. Dependencies: pin with hashes (pip-tools/uv lock), enable Dependabot/pip-audit, pin the Playwright Docker image tag.
10. Playwright: run as a dedicated non-root user; decide explicitly on `chromiumSandbox: true` (needs user namespaces) vs. documented exception; separate browser profile dir per site; no `--ignore-certificate-errors`; block downloads; consider an egress allowlist; treat scraped page text as untrusted input to the LLM (prompt-injection surface).
11. AI transparency (product-level, from KQ4): show the fit-score breakdown and the matching resume lines/job requirements; label every AI-drafted answer in the UI and in exports; never infer visa/work-authorization/demographic/salary fields, read them from explicit profile values or leave blank and flag; require review-before-submit by default; generate all documents from a single fact base and show diffs; add a per-application "what the AI wrote" view so the user can see exactly what a recruiter received.

### Gaps
- No single authoritative 2025-2026 checklist for FastAPI-specific hardening or SQLite-on-VPS was found; items 3, 9 and parts of 10 are standard practice assembled from general knowledge, not from fetched sources.
- OWASP ASVS and the Password Storage / Session Management cheat sheets were not fetched; the Secrets Management sheet was.
- Playwright's official security documentation was not located; all Playwright guidance is community-sourced.
- Google's documented 7-day refresh-token expiry for OAuth apps in "testing" publishing status was not retrieved in this session.
