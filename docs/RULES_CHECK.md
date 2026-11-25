# Rules check log

After every build phase, the app is checked against [INTERVIEWER_RULES.md](INTERVIEWER_RULES.md).
Each rule area is marked ✅ met, ⚠️ partly met, ❌ not met, or ⏳ planned for a later phase.
Every ⚠️ / ❌ gets a ticket (`orchestration.tickets`); the next check confirms it.

---

## Check after Phase 6 (2026-10-10) — first check, covers Phases 1–6

| Area | Status | Evidence / gap |
|---|---|---|
| Core behavior | ✅ | One question per turn; plan and rubric from résumé + JD + level + type; session history passed to every turn; no ideal answers before an attempt; neutral acknowledgements only (praise filtered); scores labelled practice feedback. |
| Interview preparation | ⚠️ | JD analysis, plan with minute budgets, rubric, editable plan ("Review the questions first") all built. Gap: prompts don't say "don't assume a missing résumé skill means a missing skill" — **T-42**. |
| During the interview | ⚠️ | Module-appropriate questions, follow-ups that probe vague or missing parts, backend timer moves on and wraps up, Repeat and Try again, failed transcription keeps the answer and offers typing. Gap: no **hint, pause/resume, skip** controls — **T-40**. |
| Adaptive difficulty | ⚠️ | Entry / mid / senior expectations are used in planning, turns and scoring. Gaps: challenge doesn't rise after strong answers — **T-43**; hints on request — **T-40**; "never equate nervousness/accent with lack of ability" isn't stated to the scorer — **T-42**. |
| Scoring | ⚠️ | Per-session rubric, per-criterion comments, weighted scores computed in code, temperature 0, near-empty answers score 1, retries compared on the same criteria, invented claims caught and repaired, transcription slips forgiven, disclaimer shown. Gaps: "don't penalize concise but correct", "missing evidence ≠ lack of knowledge" not in the prompt — **T-42**; uncertainty (e.g. low-confidence transcripts) not labelled — **T-41**. |
| Answer coaching | ⚠️ | Missing points, weak moments, grounded stronger version with placeholders, "what changed and why", STAR check, tips, delivery tips, Try again with before/after. Gap: no explicit "what you did well" list (only the one-line summary) — **T-41**. |
| Interviewer personalities | ✅ | Friendly / neutral / tough change tone, openings, sign-offs and voice only; the scorer never sees the persona. |
| Interview modes | ✅ | Only implemented formats that fit the job are offered at setup. Unbuilt modes (story bank, decoder, debrief) are labelled "Coming soon". |
| Final report | ⚠️ | Question scores, overall score and verdict reasoning, top 3 takeaways, highlighted weak moments, stronger versions, delivery analytics only from measured data (pace for spoken answers only). Gaps: no session-level competency feedback, no recommended exercises, unanswered planned questions and failed evaluations aren't listed — **T-41**. |
| Story bank and progress | ⏳ | Phase 7. The dashboard already shows progress (scores over time, roles, skill averages). |
| Safety and privacy | ⚠️ | Fire key only in backend `.env`; no audio stored (clips dropped after transcription); documents expire after 30 days and can be deleted; licensed-profession disclaimer; respectful-pressure rules in prompts. Gaps: no explicit "avoid discriminatory, invasive or irrelevant questions" instruction — **T-42**; expired documents are hidden but not yet purged (Phase 10). Debrief (no recordings) is Phase 8. |

**Open from this check:** T-40, T-41, T-42, T-43.

---

## Re-check after fixing the Phase 6 gaps (2026-10-10)

| Area | Status | What changed |
|---|---|---|
| Interview preparation | ✅ | Plan prompt: don't assume a skill is missing because the résumé doesn't list it — ask about it (**T-42**). |
| During the interview | ✅ | **Get a hint** (one per question, noted in the score), **Skip question** (listed as unanswered), **Pause / Resume** (clock stops) — **T-40**. |
| Adaptive difficulty | ✅ | Interviewer raises the challenge one step after strong, complete answers and never after a struggle; gives fair hints on request (**T-43**); never treats nervousness, accent or limited experience as lack of ability (**T-42**). |
| Scoring | ✅ | Scorer: evidence-based comments across relevance, accuracy, reasoning, specificity, structure, ownership, impact, role alignment; missing evidence ≠ lack of knowledge; no penalty for concise-but-correct answers, accent or nervousness (**T-42**); each answer labelled "AI coach's judgment" with a confidence level and reason (**T-41**). |
| Answer coaching | ✅ | "What you did well" (1–3 specific strengths) added to each answer (**T-41**). |
| Final report | ✅ | Competency averages, 2–3 recommended exercises, "Questions you didn't get to", and "Couldn't be scored" on failed evaluations (**T-41**). |
| Safety and privacy | ⚠️ | Plan, turn and role-play prompts forbid discriminatory, invasive or irrelevant questions (**T-42**). Still planned: purge expired documents (Phase 10); debrief without recordings (Phase 8). |
| Story bank and progress | ⏳ | Phase 7. |

Core behavior, personalities and modes remain ✅. **Open from this check:** none (the ⚠️/⏳ items are scheduled phases).

---

## Live re-check against the real Fire API (2026-10-10)

Three live interviews (sessions 25–27: mixed loop with a friendly interviewer; customer-support role-play with a tough one; a behavioral loop answered with deliberately vague replies), their reports, two retries and one spoken clip. Fire spend for the whole check: ~$0.034.

| Area | Result |
|---|---|
| Ice-breaker, plan, one question at a time | ✅ Warm small-talk reply, then the first planned question; role-play intro announced by the app. |
| Hint / skip / pause / resume | ✅ Hint gave an angle, not the answer, and was noted in that question's feedback; skip moved on and the question was listed as unanswered; answering while paused was refused and the clock skipped the pause. |
| Follow-ups and adaptive challenge | ⚠️→✅ Near-identical follow-ups were asked twice when an answer dodged one — **T-44**, fixed (prompt rule + code check that moves on). |
| Candidate questions at the end | ✅ Answered from the JD, salary honestly deferred to the recruiter. ⚠️→✅ Email follow-up mentioned twice — **T-47**, fixed. |
| Scoring and AI uncertainty | ⚠️→✅ Confidence tracked answer quality ("medium" everywhere) — **T-45**, fixed: weak-but-clear answers are now "high". Near-empty retry scored 1 with no Fire call; a better retry scored higher (3.82 → 4.0). |
| Stronger versions (never invent) | ⚠️→✅ Two rewrites copied the answer — **T-46**, fixed (repair call, then gap placeholders). An off-topic answer's rewrite recombined résumé facts into an invented incident — **T-48**, fixed: answers that missed the question get the résumé outline with placeholders. |
| Report | ✅ "What you did well", AI-judgment label, competencies, recommended exercises, unanswered questions. |
| Voice | ✅ Spoken clip transcribed (filler "um" kept). Fire speech still unavailable (T-27). |
| Dashboard stats | ✅ Interviews, averages, improvement, level, streak, retries all consistent with the data. |

**Open from this check:** none besides T-27 (Fire has no speech model).

---

## Check after Phase 7 (2026-10-10) — progress and story bank

| Area | Status | Evidence / gap |
|---|---|---|
| Story bank and progress | ✅ | Stories extracted from completed sessions (one Fire call each, after the report); STAR summary in the user's words, competencies tagged; every STAR part checked against the source answers and dropped to a visible gap if unsupported ("do not convert assumptions into facts"); hypotheticals, opinions and role-play lines never become stories; duplicates detected (model `same_as` + word-overlap check) and merged keeping the stronger telling; user edits never overwritten; coverage view flags evidence gaps ("no story yet for conflict…"); stories suggested for a job at setup; users can edit, rename or delete. Progress: scores over time, per-skill averages with change since the first interview, practice streak, weekly goal, question bank with spaced repetition, weak-spot interviews from due questions. |
| Core behavior | ✅ | Weak-spot interviews reuse the same interviewer, controls and rubric; ice-breaker and "any questions?" still apply. |
| Scoring | ✅ | Practice interviews are scored with the source job's rubric, so scores stay comparable; retries count as spaced-repetition reviews. |
| Final report | ✅ | Unchanged; the story bank updates only after a report is safe, and a failed extraction never fails the report (retried on the next report request). |
| Safety and privacy | ⚠️ | Stories and bank items belong to the user (ownership-checked APIs; cascade on account deletion). Still planned: purge expired documents (Phase 10); debrief without recordings (Phase 8). |

Live check (sessions 1–28 backfilled + one weak-spot interview, ~$0.013): stories grounded in the candidate's words with gaps left empty, the same ETL experience merged across three interviews, the practiced questions rescheduled in the queue.
Other areas unchanged since the previous check (✅). **Open from this check:** none.

---

## Check after Phase 8 (2026-10-10) — decoder, debrief, reverse, pressure

| Area | Status | Evidence / gap |
|---|---|---|
| Interview modes | ✅ | Reverse, pressure and debrief follow their own rules and are offered only where built; peer practice stays unoffered (optional stage). |
| Interviewer personalities / pressure | ✅ | Pressure levels 1–5 add skepticism, pushback, announced time limits and curveballs between answers, always with an explicit respect rule; the scorer never sees the pressure, so standards are unchanged; the candidate can ease off or stop any time; composure is reported against their normal interviews. |
| Scoring | ✅ | Debriefs use the same scorer and grounded rewrites (generic rubric, or the job's); reverse mode scores the user's questioning and judgment with evidence from the transcript and labels it practice feedback. |
| Safety and privacy | ✅ | Debrief is recall-only: no upload control exists, spoken recall is transcribed and discarded, and a visible notice explains why. The decoder labels its output as interpretation, keeps only flags that quote the posting, and doesn't store the posting. Reverse mode flags unfair interviewer questions (age, family…) and the AI candidate declines them; the hidden profile never reaches the browser before the decision. Signed-out decoder use is capped per visitor and overall, and counted in the monthly budget. Still planned: purge expired documents (Phase 10). |
| Final report | ✅ | Debrief reports add likely next-round questions and "Practice the next round"; pressure reports add composure. |
| Story bank and progress | ✅ | Debriefs feed the story bank and practice queue (real-interview evidence) but aren't counted as mock interviews; reverse sessions aren't either. |

Live check (~$0.019): decoder quotes verified and "stakeholders" ×4 counted exactly; pressure level 3 announced 60 s limits and pushed back on a vague answer, easing to 1 removed the clock, composure 111%; debrief scored, predicted five next-round questions and built a practice interview; reverse candidate kept its profile hidden, backed down when probed, declined an illegal question, and the verdict flagged it.
Other areas unchanged (✅). **Open from this check:** none.

## Check after Phase 9 (2026-10-10) — extras

| Area | Status | Evidence / gap |
|---|---|---|
| Interview preparation | ✅ | Résumé gap analysis keeps "covered" only when it quotes the résumé and words gaps neutrally ("not on your résumé" ≠ missing skill). Company research reads only the company's own public page (untrusted data), and its "Why us?" questions join the plan as a 2-minute section the user can untick; section minutes still sum to the duration. |
| Interview modes | ✅ | Coding and system design are planned only when the job analysis lists them. Panel (2–3 interviewers, one per section) and negotiation follow their own rules; pressure is refused with panel or negotiation. Peer practice stays unoffered. |
| During the interview | ✅ | Code editor and whiteboard appear only in their sections and their contents reach the interviewer, which probes edge cases, complexity, bottlenecks and failures without giving the solution. Panel interviewers introduce themselves and hand over; the lead signs off. Hint, skip, pause, repeat and Try again work in every format; Try again was missing the editor/whiteboard (T-53, fixed). |
| Interviewer personalities | ✅ | Persona applies to every panelist and sets the recruiter's firmness in a negotiation; the rubric and scorer are the same whatever the persona. |
| Scoring | ✅ | Code and whiteboard text are judged with the explanation; a code-only answer is still scored (the code counts toward the length guard). Negotiation uses a fixed, visible rubric (anchoring, justification, composure, clarity) and verdicts worded for a negotiation. Body language never reaches the scorer or Fire. |
| Answer coaching | ✅ | Questions-for-them coach rates the candidate's own questions with a better version; thank-you email uses placeholders for anything unknown; cheat sheet uses only the user's own stories, numbers and weak spots. |
| Final report | ✅ | Shows code and sketches under the answers, a negotiation header with offer and target, and body language only after 8+ camera samples, labeled as a rough guide and not part of the score. |
| Safety and privacy | ✅ | Camera is off by default; MediaPipe runs in the browser and only percentages per answer are saved; whiteboard drawings never leave the browser (text description only). Company research blocks private, loopback and link-local addresses, non-standard ports, credentials in URLs and unchecked redirects (SSRF), and caps size and time. Recruiter keeps its room to move private. Still planned: purge expired documents (Phase 10). |
| Live behavior with Fire | ✅ | See the live check below. |

Browser check found and fixed T-51 (Monaco's CDN loader broke the whiteboard) and T-52 (body-language sampling could freeze slow devices).
Other areas unchanged (✅).

### Live check against the real Fire API (2026-10-10, ~$0.05 incl. two negotiation re-runs)

Panel (15 min, with company research): stripe.com/about summarized faithfully (no invented facts) and its two "Why us?" questions became a section; Priya opened and introduced the panel, then handed to Elena (behavioral), Marcus (technical, design) and back to Elena, each with a natural handover; Priya took the candidate's questions and signed off. Coding (10 min): a role-fit problem with an example; follow-ups on edge cases, complexity and trade-offs; the scorer read the code and caught that it solved a different problem. Design (10 min): follow-ups came from the sketch text (cache invalidation, load when the cache fails). Negotiation (5 min): the recruiter held, then moved in small steps after a justified number and agreed a bonus and review; scored on anchoring, justification, composure and clarity.

Found and fixed: T-55 (editor code went out with unrelated later questions; now it resets per main question), T-56 (off-topic coding/design answers got a behavioral placeholder rewrite), T-57 (negotiation closed with the interview's "you'll hear back by email"), T-58 (the recruiter once conceded almost the whole gap on the first ask). **Open from this check:** none.

## Check after Phase 10 (2026-10-11) — deploy and harden

| Area | Status | Evidence / gap |
|---|---|---|
| Safety and privacy | ✅ | Retention is enforced: documents past 30 days are deleted daily (`flask purge-expired`, compose `purge` service), not just hidden. "Delete my data" (Account page, password + confirmation) removes the account and every user table by cascade; the spend moves to the not-tied-to-a-user tally so the monthly cap still counts it. Shared report links are read-only, revocable and hide the token and all actions. Fire key stays in the server `.env`; production refuses weak secrets, SQLite, a localhost CORS origin or a missing key. Login/signup/delete brute-force limits; the real client address comes through Caddy (spoofed `X-Forwarded-For` doesn't bypass it). Caddy and Vercel send security headers; the frontend allows only its own microphone/camera. |
| Core behavior / during the interview | ✅ | Live eval (4 full interviews, simulated clock): every session finished within its 10 minutes, wrapped up and signed off; no disrespectful interviewer line (checked automatically on every message). |
| Scoring | ⚠️ | Strong scored above weak and rambling (3.86 vs 3.66 / 3.67), but the weak candidate didn't behave weakly (used résumé numbers), so separation isn't measured yet: harness fixed (T-73), re-run pending (T-74). The run also adds examples to T-72 (a covered trade-off listed as a gap; an unrelated quote credited as a result; "seemed to resonate well" accepted as a measurable result). |
| Final report | ✅ | Share view shows the same report read-only (no Try again, transcript, thank-you or debrief actions); the admin page shows daily usage, Fire spend and budget left. |
| Interview preparation, adaptive difficulty, coaching, personalities, modes, story bank | ✅ | Unchanged in Phase 10. |

Deploy stack smoke-tested locally with Docker (MySQL 8.4, gunicorn, Caddy): migrations, signup/login, upload, admin, share 404, rate limit and the body-size cap all behaved through Caddy. Real deploy waits for the Oracle, DuckDNS and Vercel accounts (docs/DEPLOY.md). Live eval spend: $0.0744 (month ≈ $0.452 of $1).

**Open from this check:** T-72 (false gaps in missing points), T-74 (eval re-run with fixed personas).

### Eval re-run with fixed personas (2026-10-11, T-74, $0.0768)

Backend weak 2.11 (no hire) vs strong 3.86; sales weak 2.51 (no hire) vs strong 3.54: the scorer separates genuinely weak answers. Sales rambling (3.56) edged out sales strong (3.54), which exposed three scorer defects (T-75, fixed): communication criteria carried only 15% of the score (now fixed at 30% in code, `planning.share_weights`), skills a question doesn't test were marked down for "not mentioning" them (now left out, `scoring.drop_untested`), and "I can't recall the result" / "it was mixed" counted as STAR results (now rejected, `scoring.states_outcome`). Replaying the stored evaluations through the new code: backend strong 4.06 > rambling 3.75 > weak 2.14; sales strong 3.65 > rambling 3.59 > weak 2.56. The sales rambling candidate drifted from its persona (135 words); the persona now asks for 220+ words with background first. Scoring row: ✅ (separation verified), with T-72 (false gaps) still open.

## Check after Chat Lab (2026-11-18, T-146)

| Area | Status | Evidence / gap |
|---|---|---|
| Never invent experience (hard rule 4) | ✅ | The prep coach uses only the résumé/JD the user picks and their messages; `prompts/lab_guard.txt` (placeholders for missing facts, ignore instructions in the candidate's text) is appended after every agent prompt, including user-edited ones, so an edit can't drop it (`test_prep_chat_uses_documents_and_always_appends_the_guard`). |
| Respectful at every level (hard rule 5) | ✅ | The guard forbids insults and personal attacks even when arguing against hiring; the default skeptic prompt asks for a fair case. |
| Scores are practice feedback (hard rule 6) | ✅ | The debate score shows "Practice feedback from an AI, not a hiring decision. Real hiring decisions are made by people." |
| Cost (hard rule 1) | ✅ | 10 calls/user/day reserved atomically before any Fire call (debate 3, compare 2, chat 1); monthly budget checked first; models limited to GPT-4o mini (default) and Claude Haiku 4.5; temperature ≤ 1; prompt/answer/system text ≤ 4,000 chars, documents ≤ 6,000, last 20 chat turns, replies ≤ 700 tokens. Tested: cap, per-user, budget, refusal before any call, failed calls given back. |
| Privacy (hard rule 3) | ✅ | Nothing from the lab is stored; the browser keeps the conversation and the settings (localStorage). |
| Fire key (hard rule 2) | ✅ | Every lab call goes through Flask (`services/lab.py` → `fire.py`). |
| Live behavior | ✅ | Live check on 2026-11-18 after deploy, with a temporary account deleted afterwards ($0.0019 total): the prep chat gave 3 role-fit questions and a STAR outline built only from the résumé, then asked for a real example instead of inventing one; the debate gave a fair case for and a fair case against (no personal attacks) and the judge scored 3/5 with three reasons and one tip; compare answered with GPT-4o mini at 0 and Claude Haiku 4.5 at 1 side by side; temperature 2 was refused (400); at 9 of 10 calls a compare was refused (429) with no call made and usage stayed at 9. |

**Open from this check:** none.

## Check after the agency demo (2026-11-25, T-166)

Organizations (admin, coach, candidate), the coach dashboard, assignments, coach comments, consent, branding, and the seeded "Northstar Career Partners" demo. Admin-only by default (`ORG_FEATURE=admin_only`).

| Area | Status | Evidence / gap |
|---|---|---|
| Consent (safety and privacy) | ✅ | A coach sees a candidate's reports only while `org_members.consent_at` is set. Joining an org and sharing reports are separate steps (Join page checkbox, off by default), and the candidate can stop sharing on the Account page. Before consent, or after it is withdrawn, every coach route for that candidate returns 404 (`test_coach_sees_nothing_until_the_candidate_consents`). |
| Data separation | ✅ | Every org route is scoped to an org the caller belongs to; another org's coach gets 404 for candidates, reports and comments (`test_coach_of_another_org_sees_nothing`). Real accounts can't join the demo org, and demo accounts can't join or create orgs. |
| Access (admin-only) | ✅ | Every `/api/orgs` and `/api/demo` route returns 404 to signed-out visitors, regular users, bad tokens, and everyone when `ORG_FEATURE=off`. A table test checks every registered route, so a new route can't go untested (`tests/test_orgs_access.py`). Demo accounts have no password, can't log in, and only open through an admin's 2-hour View as token, which is re-checked against `ADMIN_EMAILS` on every request. A regular user's `/auth/me` and pages are unchanged, and the website never calls org APIs for them (`Orgs.test.jsx`). |
| Cost (hard rule 1) | ✅ | Demo accounts never reach Fire: `fire.get_fire()` refuses them (403 "demo account"), and report generation is refused for their unfinished reports. The seed is hand-written and makes no Fire calls (`FakeFire.calls == []` in `test_demo.py`). No change to caps or budget for current users. |
| Deletion and retention | ⚠️ | All new tables cascade from users and orgs, so Delete my data removes memberships, assignments and comments (`test_deleting_the_candidate_removes_their_org_data`). The JD a candidate starts from an assignment is a normal 30-day document. Gaps: a candidate can't leave an org (only stop sharing), invite links can't be revoked early, and coach comments can't be edited or deleted: **T-167** (needed before `ORG_FEATURE=on`). |
| Scores are practice feedback (hard rule 6) | ✅ | The coach dashboard says "Scores are practice feedback from an AI interviewer, not hiring assessments". Coach report views reuse the read-only report, including the licensed-profession disclaimer (demo nurse: `licensed_field` true). |
| Never invent experience (hard rule 4) | ✅ | Demo stronger versions use only the fictional résumé and answer facts, with `[placeholders]` for missing results. Every person and employer is fictional and marked with a Demo badge. |
| Final report | ✅ | Seeded reports have question scores with per-criterion comments, takeaways, recommended exercises, stronger versions and delivery analytics. Weighted scores, verdicts and delivery come from the app's own code (`weighted_score`, `verdict_for`, `analytics.delivery`). |
| Interviewer behavior, adaptive difficulty, personalities, modes, story bank | ✅ | Unchanged. Coaches only read reports; they don't change scoring. |

Local end-to-end check (headless Chromium): View as demo coach → dashboard (2 flagged), Jordan's page, report with comment → Back to admin → View as demo candidate → assignments, streak, goal, practice queue, report with the coach's comment; Start and Setup show the demo message. A regular account sees no Coach/Demo links, and curl gets 404 on `/api/orgs/...` and `/api/demo` both signed out and as a regular user.

**Open from this check:** T-167.
