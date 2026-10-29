# UX/UI, Mobile, Onboarding and Pricing Complaints About Job-Search Tools (2023–2026), plus ADHD-Friendly Design Guidance

Research date: 2026-10-29. Method: web search + direct fetch of Trustpilot, App Store, Chrome Web Store, Product Hunt, W3C COGA and ADHD-design pages. Reddit could not be fetched directly (fetch tool blocked for reddit.com; searches did not surface threads), so "Reddit" quotes below are absent and that is flagged as a gap. Many search hits are competitor-written "review" blogs (wobo.ai, loopcv.pro, resumly.ai, jobright.ai, resumehog, etc.); these are used only for pricing/feature claims and flagged as secondary.

## Q1. What UX/UI complaints recur in app-store / Chrome / review-site feedback for each tool?

### Takeaway
Primary-source review pages show the trackers (Teal, Huntr, Simplify) are liked for the core tracker/autofill, with complaints clustering on (a) manual upkeep and learning curve, (b) missing data in the main table view, (c) mobile apps that are read/reorder-only, and (d) billing. The auto-apply tools (LazyApply, LoopCV, Jobright, Jobscan) draw much harsher feedback dominated by refund/cancellation friction and "it didn't actually work" rather than visual UI clutter.

### Cited Findings

**Teal**
- Trustpilot 4.2/5 from 118 reviews, ~71% 5-star, ~13% 1-star (fetched 2026-10-29) — [Trustpilot: Teal](https://www.trustpilot.com/review/tealhq.com)
- Onboarding/learning curve: "there's definitely a learning curve getting everything set up the way you want it." (Bryan Tisdale, May 3 2026) — [Trustpilot: Teal](https://www.trustpilot.com/review/tealhq.com)
- Table view hides info: "Wish I could also view the notes I've left on each job in the main tracker table view." (Jul 15 2026) — [Trustpilot: Teal](https://www.trustpilot.com/review/tealhq.com)
- Praise for simplicity: "I appreciate just how simple and clean the User Interface is" (Sep 24 2026); stage tracking praised: "knowing which stage of the process each one is." (May 11 2026) — [Trustpilot: Teal](https://www.trustpilot.com/review/tealhq.com)
- Another Trustpilot reviewer said tracking "takes a lot of work to keep updated"; Jobscan's comparison says Teal's integrated tools "can feel a bit overwhelming or unintuitive for first-time users" (competitor source) — [Jobscan vs Teal](https://www.jobscan.co/blog/jobscan-vs-teal/); ResumeJudge notes some users find it "still kinda clunky" — [ResumeJudge Teal review](https://resumejudge.com/blog/tealhq-review/)
- Workaround noted in reviews: you can hide columns to simplify a busy grid — [Rezi Teal review](https://www.rezi.ai/posts/teal-review)
- Account lockout / data loss and a "NON-RECURRING" charge confusion reported in secondary review roundups — [wobo.ai Teal review](https://www.wobo.ai/blog/teal-review/)

**Huntr**
- Chrome Web Store reviews mostly positive; Oct 31 2025 reviewer: extension "cannot save to the shared board" under a coach's premium account, though "auto fill ins from webpages works amazing" — [Chrome Web Store: Huntr reviews](https://chromewebstore.google.com/detail/huntr-job-search-tracker/mihdfbecejheednfigjpdacgeilhlmnf/reviews)
- Rating counts conflict: 4.8 stars/1,300 ratings (third party) vs Huntr's own "1.1k reviews, 4.9 stars" — [wobo.ai Huntr review](https://www.wobo.ai/blog/huntr-review); [huntr.co](https://huntr.co/)
- Autofill "hit-or-miss", works on standard ATS but "struggles with custom forms"; AI cover letters "inconsistent, often requiring significant manual editing"; "no alerts or notifications" (secondary review sites) — [ResumeJudge Huntr](https://resumejudge.com/blog/huntr-review/); [Scoutify Huntr](https://scoutify.com/blog/huntr-review/)
- Praised: kanban board, contacts CRM, clipper; "for pure tracking, Huntr — cleaner board, less surrounding platform" (competitor comparison) — [LoopCV Teal vs Huntr](https://blog.loopcv.pro/teal-vs-huntr-vs-loopcv/)

**Simplify Copilot**
- Chrome Web Store 4.8/5 from 3.9K ratings, ~500K users (fetched 2026-10-29) — [Chrome Web Store: Simplify reviews](https://chromewebstore.google.com/detail/simplify-copilot-autofill/pbanhockgagggenencehbnadejlgchfc/reviews)
- Praise: "easily cut my application time in half!" (Oct 25 2026); "It's simple to use, saves time" (Oct 29 2026); "Amazing tool and free tier." — same source
- Friction: "I wish that we didn't always have to manually click the 'auto apply'" (Oct 28 2026, 4/5); "custom questions and some company portals still need manual input" (Oct 25 2026) — same source
- Firefox port complaints (lag, stalls, "would not get past the login prompt") — [Mozilla add-on reviews](https://addons.mozilla.org/en-US/firefox/addon/simplify-jobs/reviews/)
- Trustpilot only ~3.0/5 from 9 reviews, 1-star reviews about Simplify+ billing: unexpected charges, reversed refunds, unresponsive support (secondary summary) — [resumehog Simplify review](https://resumehog.com/blog/posts/simplify-copilot-review-2026-is-the-free-autofill-tool-worth-it.html)
- One hands-on test: autofill ~90% on Greenhouse/Lever, ~70% Workday, ~0 on long government forms (single third-party test) — [autoapplier Simplify review](https://www.autoapplier.com/blog/simplify-copilot)

**Jobscan**
- Trustpilot 4.3/5 from 346 reviews (fetched 2026-10-29); "user interface is easy to use, clean look, and pretty intuitive." (Aug 15 2026) — [Trustpilot: Jobscan](https://www.trustpilot.com/review/jobscan.co)
- Main complaints are billing not UI (see Q4).

**LazyApply**
- Trustpilot 2.1/5 ("Poor") from 110 reviews, 58% 1-star; company has not replied to negative reviews — [Trustpilot: LazyApply](https://www.trustpilot.com/review/lazyapply.com)
- Hidden requirement at signup: "Their platform only works with Gmail accounts. This restriction is nowhere to be found during signup or checkout." (Jun 25 2026); "It fails at automation of completing application form" (Feb 21 2026); "The chat sends you to do an email, and nothing happens when you do." (May 20 2026) — same source

**LoopCV**
- Small review sample, mostly negative on refunds: one reviewer titled it "Poor Service, a Two-Month Refund Ordeal, and a Scam-Like Experience" — [Trustpilot: LoopCV](https://www.trustpilot.com/review/loopcv.pro)

**Jobright**
- Product Hunt 4.8/5 (12 reviews, ~2 years old): "Very user-friendly UI and easy adoption experience."; request "please add an option to manually edit the text of the newly generated CV before downloading"; "Any chances of a mobile app option?" — [Product Hunt: Jobright](https://www.producthunt.com/products/jobright-ai-2/reviews)
- Google Play reviewer (May 29 2026): "The auto-fill is great, the 'AI' built into the job list is complete garbage." (quoted via secondary) — [HiringReach Jobright review](https://hiringreach.com/reviews/jobright-ai-review)
- Resume tool reportedly inserts skills/metrics not on the original resume (secondary) — [resumly Jobright review](https://www.resumly.ai/answers/jobright-review)

**Careerflow**
- Only passing mentions: billing complaints in 1-star reviews and a reviewer finding it "introduced incorrect information into resumes" (secondary roundups) — [resumly best AI job tools](https://www.resumly.ai/best/best-ai-job-search-tools)

**Sonara, JobCopilot**
- No primary review evidence found. One comparison says JobCopilot's terms make "refunds discretionary" — [resumly job application bots](https://www.resumly.ai/best/best-job-application-bots)

**LinkedIn / Indeed (native)**
- LinkedIn: aggregator reports users "frustrated over an app known for incessantly sending random, irrelevant, and annoying notifications, despite attempts to unsubscribe or turn them off"; errors loading applications; crashes — [Fibery Openion LinkedIn](https://fibery.io/openion/linkedin-77/persistent-nocaptcha-verification-issue-on-sign-in-and-sign-up-221292)
- Easy Apply "void" anecdote: "83 applications, 2 rejections, 0 interviews, 81 silent" (single user tally) — [unstar job apps ranked 2026](https://unstar.app/blog/linkedin-indeed-glassdoor-ziprecruiter-job-search-apps-ranked-2026)
- Indeed: reviewers cite fake/expired "ghost" listings, unrequested job-match emails, irrelevant matches, and notifications about jobs they'd already withdrawn from — [Trustpilot: Indeed p6](https://www.trustpilot.com/review/www.indeed.com?page=6); [ConsumerAffairs Indeed p2](https://www.consumeraffairs.com/employment/indeed.html?page=2); [ConsumerAffairs p3](https://www.consumeraffairs.com/employment/indeed.html?page=3)

### Inferences
- "Cluttered dashboard" is not the dominant complaint for trackers; "manual upkeep burden" and "hidden info behind clicks" are. A tracker that auto-captures (clipper/extension) and surfaces notes/next-step inline wins on both.
- The auto-apply category's reputation is poisoned by billing/refund behavior; a tool that is transparent about limits up front (cf. LazyApply's hidden Gmail-only rule) differentiates on trust alone.
- Notification spam from LinkedIn/Indeed is the reference point users have; a nudge must be rare and tied to a real deadline to avoid being lumped in.

### Gaps
- No Reddit threads could be retrieved (fetch blocked; `site:reddit.com` searches returned no Reddit hits). Reddit quotes for Teal/Huntr/Simplify are missing.
- No primary App Store / Play reviews for LinkedIn or Indeed were retrieved; only aggregator/consumer-complaint sites.
- No reviews at all for Sonara; Careerflow and JobCopilot only secondhand.

## Q2. How do mobile experiences rate?

### Takeaway
Mobile is the weakest layer in this category: Teal has no native app (web + Chrome extension only), Huntr's iOS app (4.7/5, 362 ratings) hasn't been updated since Sept 2024 and reviewers say it only lets you reorder existing cards, and Simplify is extension-first. Jobright is the exception with well-rated native apps (~4.8 iOS, ~4.6 Play).

### Cited Findings
- Huntr iOS: 4.7/5 from 362 ratings; last update v2.0.10 on 09/04/2024 — [App Store: Huntr](https://apps.apple.com/us/app/huntr-job-search-browser/id1372389812)
- Huntr iOS feature gap: desktop can delete postings but "The app just allows you to shuffle them around." (Aug 23 2024); "the mobile app is only useful for managing existing entries" — the extension can create entries from a posting, the app cannot, so reviewer kept a spreadsheet (Oct 2 2023) — same source
- Huntr iOS in-app web view: nav buttons sit where the iPhone home gesture is: "I just wish the web view was designed a little more user-friendly." (Dec 2019); confusion on adding entries "without filling up my board with a bunch of test company names." (Mar 2022) — same source
- Huntr "mobile app functionality is less versatile compared to the desktop and browser extension" (secondary) — [Tekpon Huntr](https://tekpon.com/software/huntr/reviews/)
- Teal: "no dedicated iOS or Android app listed on its own site"; "no iOS app on the US App Store as of September 22, 2026" — [lastroundai Teal](https://lastroundai.com/compare/teal); [resumly / fastapply best job apps](https://blog.fastapply.co/best-job-apps-to-land-a-job-fast)
- Jobright: ~4.8 stars across ~1,550 App Store ratings (Oct 2 2026) and ~4.6 across 713 Google Play reviews (secondary, single source for Play) — [HiringReach Jobright](https://hiringreach.com/reviews/jobright-ai-review); [Careery Jobright](https://careery.pro/blog/ai-job-search/jobright-ai-review/)
- Jobright Product Hunt request (2 yrs ago): "Any chances of a mobile app option?" — [Product Hunt: Jobright](https://www.producthunt.com/products/jobright-ai-2/reviews)
- Simplify is a Chrome extension (500K users) with a Firefox port that reviewers report lags and stalls — [Chrome Web Store: Simplify](https://chromewebstore.google.com/detail/simplify-copilot-autofill/pbanhockgagggenencehbnadejlgchfc/reviews); [Mozilla reviews](https://addons.mozilla.org/en-US/firefox/addon/simplify-jobs/reviews/)
- LinkedIn app: notification complaints and "something went wrong loading an application" errors (aggregator) — [Fibery Openion](https://fibery.io/openion/linkedin-77/persistent-nocaptcha-verification-issue-on-sign-in-and-sign-up-221292)

### Inferences
- The tracker incumbents treat mobile as a read-only companion; low-friction capture on the phone (paste a URL / share-sheet / forward an email) is an open gap and matches ADHD "capture it now" needs.
- A stale app (Huntr, 2 years without update) signals abandonment; users then regress to spreadsheets.

### Gaps
- Google Play ratings for Huntr and any native Teal app not confirmed (Teal apparently has none).
- No LinkedIn/Indeed store ratings retrieved.

## Q3. What onboarding steps cause drop-off; what do praised onboardings do?

### Takeaway
Direct evidence on drop-off is thin; what exists shows that praised onboardings are "clean" with a detailed beginner guide (Jobright) or let you get value before configuring (Teal's free tracker, Simplify's "simple to use"), while complaints center on heavy setup ("learning curve getting everything set up"), hidden prerequisites discovered after checkout (LazyApply Gmail-only), and free-tier credits that run out before the user sees value.

### Cited Findings
- Teal: "there's definitely a learning curve getting everything set up the way you want it." (May 3 2026) — [Trustpilot: Teal](https://www.trustpilot.com/review/tealhq.com)
- LazyApply: Gmail-only restriction "nowhere to be found during signup or checkout" (Jun 25 2026) — [Trustpilot: LazyApply](https://www.trustpilot.com/review/lazyapply.com)
- Jobright: onboarding described as clean with a detailed beginner guide; "Very user-friendly UI and easy adoption experience." — [Product Hunt: Jobright](https://www.producthunt.com/products/jobright-ai-2/reviews)
- Jobright free tier: limited daily credits that one reviewer says run out quickly (secondary) — [careerkit Jobright](https://www.careerkit.me/blog/jobright-review)
- Simplify: "It's simple to use, saves time"; "Amazing tool and free tier." (Oct 2026) — [Chrome Web Store: Simplify](https://chromewebstore.google.com/detail/simplify-copilot-autofill/pbanhockgagggenencehbnadejlgchfc/reviews)
- W3C COGA pattern 4.6.4: "Before a user performs a task consisting of multiple steps, ensure they have an estimate of the amount of effort required" — [W3C COGA Design Guide](https://www.w3.org/TR/coga-usable/design_guide.html)
- W3C COGA 4.6.3: "Provide users with five or less main choices on each screen"; 4.5.9: "Avoid timeouts and let the user save their work as they go." — same source
- Neurodivergent-UX guides: break long forms into step-by-step wizards; show "Step 2 of 4"; let users pause and return without losing context; one primary action per screen — [accessibilitychecker neurodivergent UX](https://www.accessibilitychecker.org/blog/neurodivergent-ux-design/); [Din Studio ADHD UI](https://din-studio.com/ui-ux-for-adhd-designing-interfaces-that-actually-help-students/)
- Progressive disclosure should be "triggered by user actions rather than by elapsed time since install" — [Digia progressive disclosure](https://www.digia.tech/post/progressive-disclosure-mobile-ux/)

### Inferences
- The "resume + profile + 40 fields" pattern is implied by Teal's "learning curve" and Huntr's two-resume cap, but no reviewer explicitly counts fields; treat the 40-field framing as the team's hypothesis, not a sourced complaint.
- Praised onboardings let the first session end with one tracked job, not a completed profile.

### Gaps
- No quantitative onboarding drop-off data for any tool (no public funnel numbers, no UX teardown with metrics found).
- No published UX teardown article specifically on Teal/Huntr onboarding was found; all commentary is review-site level.

## Q4. Pricing: which tiers/paywalls anger users; price points; free-tier limits; cancellation/refund complaints

### Takeaway
Price points cluster at ~$30–40/month for pro tiers (Huntr $40, Jobright Turbo ~$39.99, Teal+ reported $9→$13/week), with the anger concentrated on auto-renewal, cancel buttons that don't exist in-account, multi-month bundles charged when a user selected one month, and refund policies with 2-day windows or "discretionary" language. Free tiers are praised when generous (Teal unlimited tracking, Simplify autofill) and resented when capped by credits (Huntr 2 tailored resumes; Jobright daily credits).

### Cited Findings

**Price points (secondary sources; check vendor pages)**
- Huntr Pro ~$40/mo monthly, ~$30/mo quarterly, ~$26.66/mo biannual; free tier 100 tracked jobs (one source says 40) and only 2 tailored resumes / 2 application packets; credits don't carry over — [stork.ai Huntr](https://www.stork.ai/en/huntr); [resumeoptimizerpro Huntr alt](https://resumeoptimizerpro.com/blog/huntr-alternative); [ResumeJudge Huntr](https://resumejudge.com/blog/huntr-review/)
- Teal+ reportedly rose from $9 to $13/week in 2025; another source lists $29/mo (conflicting) — [wobo.ai Teal](https://www.wobo.ai/blog/teal-review/); [jobright Teal review](https://jobright.ai/blog/teal-review-2026-walkthrough-alternatives-and-faqs/)
- Teal free: "unlimited job tracking and unlimited resumes, free forever"; caps are on AI usage — [jobshinobi Teal vs Huntr](https://www.jobshinobi.com/compare/teal-job-tracker-vs-huntr)
- Jobright Turbo ~$39.99/mo (one source: rose 33% from $29.99; another still lists $29) — [zplatform Jobright pricing](https://zplatform.ai/ai-reviews/jobright-ai/); [careerkit Jobright](https://www.careerkit.me/blog/jobright-review)
- Simplify+: no free trial and a strict no-refund policy reported — [resumehog Simplify](https://resumehog.com/blog/posts/simplify-copilot-review-2026-is-the-free-autofill-tool-worth-it.html)

**Cancellation / refund complaints (primary)**
- Jobscan: "There is no way for you to cancel directly from your account page." (Aug 23 2026); "when I select one month only ????? So they toke 3 months payment." (Sep 29 2026); "withdrawing money from your credit card without your consent." (Jul 28 2026) — [Trustpilot: Jobscan](https://www.trustpilot.com/review/jobscan.co)
- Jobscan policy: cancellation does not auto-refund; refunds only for charges disputed within 2 calendar days of the billing period and only if unused; 3.5% fee; case-by-case — [Jobscan cancellation policy](https://www.jobscan.co/cancellation-policy)
- Jobscan: reviewers report being charged $71 after cancelling and removing payment details; one "cancelled three times and were still charged" — [Trustpilot: Jobscan](https://www.trustpilot.com/review/jobscan.co)
- Teal: "Scam. Get you to sign up for subscriptions and get you when your forget. And don't help afterwards." (May 2 2026) — [Trustpilot: Teal](https://www.trustpilot.com/review/tealhq.com)
- LazyApply: "it took two weeks to even get a response to let me know I was in the Queue." (refund, Jun 16 2026); another "had to open a chargeback to get my money back" — [Trustpilot: LazyApply](https://www.trustpilot.com/review/lazyapply.com)
- LoopCV: refund took ~2 months and never arrived; another refund denied until escalation — [Trustpilot: LoopCV](https://www.trustpilot.com/review/loopcv.pro)
- Jobright: terms (captured Aug 20 2026) say cancellation stops renewals but does not refund processed charges; refund only if approved, no stated window; one analysis claims ~72% of 1-star Trustpilot reviews involve billing (competitor-run analysis) — [trajobo Jobright](https://www.trajobo.com/guides/jobright-review); [zplatform Jobright](https://zplatform.ai/ai-reviews/jobright-ai/)
- Jobright support reportedly email-only, slowing disputes — [zplatform Jobright](https://zplatform.ai/ai-reviews/jobright-ai/)

**Positive pricing sentiment**
- "For a free tool, the value is hard to argue with." (Teal, May 3 2026) — [Trustpilot: Teal](https://www.trustpilot.com/review/tealhq.com)
- Jobscan: "it was expensive for 3 months but you get what you paid for." (Aug 15 2026) — [Trustpilot: Jobscan](https://www.trustpilot.com/review/jobscan.co)

### Inferences
- The anger is less about the number and more about dark patterns: no in-account cancel, bundle defaults, silent renewals, tiny refund windows. A one-click cancel plus renewal-reminder email would be a differentiator supported by the complaints.
- Credit-metered free tiers (Huntr, Jobright) generate "paywall mid-task" resentment; feature-gated free tiers (Teal unlimited tracking) generate goodwill.

### Gaps
- Exact current prices conflict across sources and were not verified on vendor pricing pages.
- No primary Careerflow, Sonara or JobCopilot pricing/cancellation evidence.

## Q5. ADHD-specific: what helps, what hurts, and what guidelines say

### Takeaway
Formal guidance (W3C COGA, St Andrews 2025 ADHD dos/don'ts) and ADHD coaching sources converge on: one clear next action per screen, five or fewer choices, user-controlled dismissible reminders, visible progress, auto-save/no timeouts, easy undo, and avoiding streak/shame mechanics. Body doubling and early-buffered deadlines are the most-cited behavioral aids. No controlled research on countdown timers in job-search tools was found; evidence is practitioner and guideline level.

### Cited Findings

**W3C COGA "Making Content Usable" design patterns (informative, not normative)**
- 4.6.3 Avoid Too Much Content: "Provide users with five or less main choices on each screen" — [W3C COGA Design Guide](https://www.w3.org/TR/coga-usable/design_guide.html)
- 4.6.1 Limit Interruptions: "Providing an easy way to control interruptions, reminders, and changes in content unless they are started by the user" — same
- 4.5.9: "Avoid timeouts and let the user save their work as they go."; 4.5.2: "Always let the user return to a previous point."; 4.5.10: "Provide easily-recognizable success or failure feedback with every user action." — same
- 4.6.4: give "an estimate of the amount of effort required" before multi-step tasks; 4.4.9 "In instructions, separate each step." — same
- Reminders: "Always give the option to set a reminder at the end of the task so that the user does not get interrupted"; the user "is best placed to decide how many reminders they want and of which type" — same
- Control 7.5 Provide Reminders (COGA summary): reminders "must be timely and dismissible", customisable by channel/frequency, snoozable; users with attention differences benefit — [Microsoft hve-core COGA reference](https://github.com/microsoft/hve-core/blob/main/.github/skills/accessibility/accessibility/references/frameworks/coga.md)
- Older COGA draft: "Reminders should be set only at the users request and the user should be able to personalize the reminder method." — [W3C COGA extension draft](https://w3c.github.io/coga/extension/)
- WCAG supplemental "Limit Interruptions": "Users can choose visual reminders, sounds, or none." — [W3C WCAG supplemental o5p01](https://www.w3.org/WAI/WCAG2/supplemental/patterns/o5p01-minimal-interruptions/)

**St Andrews "Designing for users with ADHD" (Lewis Wake, 12 Feb 2025)**
- Do: "Use clear and consistent layouts" ("Predictability reduces cognitive load"); "Keep navigation simple and predictable"; "Break up content into small, manageable chunks"; "Allow users to customise notifications and animations"; "Offer reminders and prompts for important actions" (gentle reminders, progress indicators, auto-saves prevent task abandonment) — [St Andrews ADHD design](https://digitalcommunications.wp.st-andrews.ac.uk/2025/02/12/designing-for-users-with-adhd/)
- Don't: "overwhelm users with too much information at once" (avoid multiple tasks/options in one view; use progressive disclosure); "rely on users remembering previous steps without guidance"; "set short time limits for actions without an option to extend" — same

**GOV.UK posters**
- The original 2016 GOV.UK "Dos and don'ts" set covers autism, screen readers, low vision, motor, deaf/HoH, dyslexia — no ADHD poster in that set — [GOV.UK accessibility blog](https://accessibility.blog.gov.uk/2016/09/02/dos-and-donts-on-designing-for-accessibility/)
- A later set (Smashing newsletter) covers "dyslexia, autism, ADHD, dyscalculia, and anxiety" with five dos/don'ts each; Canada's 2023 "Cognitive" poster also exists — [Smashing issue 412](https://www.smashingmagazine.com/the-smashing-newsletter/smashing-newsletter-issue-412); [a11y.canada.ca Cognitive poster 2023](https://a11y.canada.ca/docs/posters/Cognitive-en_2023.pdf)

**Shame-free / anti-streak design**
- "Save for Later" instead of "Quit" reduces shame-driven disengagement; keep interfaces neutral after setbacks — [Gapsy mental-health app design](https://gapsystudio.com/blog/mental-health-app-design/)
- Streak mechanics drive ADHD users away after one missed day; prefer forgiving designs where progress carries over; an ADHD-friendly app should be "fundamentally incapable of causing a shame spiral" — [Wellnest ADHD medication app design](https://wellnestapp.app/blog/adhd-medication-app-design)
- First screen should answer a single question with everything else behind a second layer; one-tap core actions — same
- Make undo and recovery easy so mistakes carry no penalty — [accessibilitychecker neurodivergent UX](https://www.accessibilitychecker.org/blog/neurodivergent-ux-design/)
- One primary action per screen, fewer notifications, visible progress to resume after interruption (vendor source) — [vp0 ADHD mobile UI guidelines](https://vp0.com/blogs/adhd-friendly-mobile-app-ui-guidelines.md)
- Staged disclosure matters most in choice-heavy UIs; turning flows into steps "gives a sense of progress and forward motion" — [Intuit Design: ADHD and design](https://design.intuit.com/adhd-and-design/)
- Core problem framed as attention being "constantly competed for" — [UX Collective: Design v ADHD](https://uxdesign.cc/design-vs-adhd-4411c3b81d1b)

**ADHD job-search community / coaching advice**
- Tracker fields that coaches recommend: date, company, role, status, next steps, link, contact; update "right after submitting" (habit pairing); set follow-up dates; limit email checking; decide the next step before a rejection arrives — [Beyond BookSmart](https://www.beyondbooksmart.com/executive-functioning-strategies-blog/job-searching-with-adhd-five-executive-function-skills-to-help-make-it-easier)
- Break tasks into smaller steps, "one task at a time", measurable goals ("apply to three jobs"), color-coded calendar for deadlines/follow-ups — [WhatInTheBrain ADHD job search](https://www.whatinthebrain.com/adhd-blog-post/job-searching-with-adhd)
- Prioritized task list plus flexible schedule for shifts in attention/energy; trackers help "spot where you're stalling" — [LifeSketch ADHD job search](https://www.lifesketch.co/blog/overcoming-job-search-procrastination-advice-for-adults-with-adhd)
- ADHD PM laid off 10 months: first tip is write down accomplishments while fresh (low-friction capture) — [ADHD PM Substack](https://adhdpm.substack.com/p/sick-post-tips-if-youve-just-been)
- "ONE Thing Rule": a long list triggers "ADHD brain freeze"; narrow to a single task — [ADHD Wisdom Tools Substack](https://adhdwisdomtools.substack.com/p/the-one-thing-rule-the-adhd-strategy); "One Step, No Shame" prompt: ask for one extremely low-pressure task when overwhelmed — [ADHD with AI Substack](https://adhdwithai.substack.com/p/the-one-step-no-shame-prompt)
- Body doubling: ADDitude calls it effective in person or virtually; ADDA: partner should be "quiet and independent"; agree duration and check-ins in advance — [ADDitude body double](https://www.additudemag.com/getting-things-done-with-adhd/); [ADDA body double](https://add.org/the-body-double/)
- Deadlines: set them two days early for buffer; break search into weekly targets; "as deadlines get closer, avoidance usually gets louder" (reorganizing files instead of applying) — [Coaching with Brooke](https://www.coachingwithbrooke.com/post/5-ways-to-actually-meet-deadlines-when-you-have-adhd); [Neural Revolution ADHD deadlines](https://www.neural-revolution.com/feeds/blog/adhd-deadlines)
- Pomodoro plus an accountability partner is more likely to stick than a timer alone — [ADHD Care Connect body doubling](https://www.adhdcareconnect.com/resources/adhd-body-doubling-accountability-strategies)

**Research state**
- HCI literature review notes ADHD is under-researched versus other conditions in assistive tech — [arXiv 2005.09993](https://arxiv.org/pdf/2005.09993)
- No Nielsen Norman Group article on ADHD users was found in search.

### Inferences
- Design spec implied by the sources: a "today" screen with one next action and the nearest deadline; everything else (tables, stats) behind progressive disclosure; reminders opt-in, snoozable, per-channel; auto-save; no streaks or "you missed X" framing; capture in one tap from phone share-sheet or email forward.
- Countdowns: guidelines support visible time awareness ("time awareness" is a named COGA need) but warn against hard time limits without extend/pause; so a countdown should be informational and never lock the task.
- Body doubling could be approximated in-app by a timed focus session with a check-in, but the strongest evidence is for a human partner.

### Gaps
- No controlled studies on countdown timers, single-focus views or progressive disclosure specifically for ADHD job seekers; evidence is guidelines and practitioner advice.
- No r/ADHD threads retrievable; CHADD material not surfaced; ADDitude has no job-search-specific tracker article found.
- No source quantifies the harm of "shame-inducing stats" (e.g., applications-vs-interviews ratios) beyond the streak discussion.

## Q6 (cross-cutting). What designs do users praise, and what about dark mode / accessibility?

### Takeaway
Praise goes to: stage/kanban tracking (Teal, Huntr), one-click autofill with a generous free tier (Simplify), clean simple UI (Teal, Jobscan, Jobright), and capture from the page via extension (Huntr clipper). Dark mode and formal accessibility (screen reader, contrast) are essentially absent from the reviews found.

### Cited Findings
- Kanban/CRM praise: Huntr "kanban board, contact directory, and outreach templates make it the most complete CRM-for-job-search" (competitor comparison) — [jobscoutly Teal vs Huntr](https://jobscoutly.com/blog/teal-vs-huntr/)
- Teal "visual status view" credited with making things "less overwhelming when applying widely" — [resumehog Teal vs Huntr](https://resumehog.com/blog/posts/job-tracker-review-comparing-teal-and-huntr-for-your-2026-search.html)
- Simplify praise: "easily cut my application time in half!" — [Chrome Web Store: Simplify](https://chromewebstore.google.com/detail/simplify-copilot-autofill/pbanhockgagggenencehbnadejlgchfc/reviews)
- Teal "simple and clean" UI; Jobscan "clean look, and pretty intuitive" — [Trustpilot: Teal](https://www.trustpilot.com/review/tealhq.com); [Trustpilot: Jobscan](https://www.trustpilot.com/review/jobscan.co)
- Spreadsheets/Notion remain the baseline competitor: "value proposition weakens when free alternatives (Notion, spreadsheets) can handle basic tracking" — [Scoutify Huntr](https://scoutify.com/blog/huntr-review/)
- St Andrews: dark-mode/reader-view plugins reduce distraction, so content should be simple HTML that works with them; let users customise animations — [St Andrews ADHD design](https://digitalcommunications.wp.st-andrews.ac.uk/2025/02/12/designing-for-users-with-adhd/)

### Inferences
- Nobody in this category is winning on accessibility or dark mode; it is cheap differentiation and directly supports the ADHD "minimise distractions" guidance.

### Gaps
- No reviews mention dark mode, screen-reader support, or WCAG for any of the named tools.
- No UX teardown article with screenshots of Teal/Huntr/Simplify onboarding was found.
