# AI Mock Interviewer

A mock interviewer for any job. Users upload a résumé and job description, pick a duration (10 / 30 / 45 / 60 min or custom 5–60), answer out loud, and get a scored report with "stronger version" rewrites of their answers. In the first release the interviewer replies in text; later it speaks.

Full spec: `docs/SPEC.md` (read the relevant section before starting each phase). This file is the working summary for Claude Code.

## Hard rules

1. **Minimal cost.** Free tiers and open source everywhere, except Fire API usage (transcribe, chat, speech). Never add another paid service or dependency.
2. **The Fire key never leaves the backend.** It lives only in `backend/.env` as `FIRE_API_KEY`. `.env` is in `.gitignore` from the first commit. The browser never calls Fire; every Fire call goes through Flask. Never print, log, or hard-code the key.
3. **Never store audio or video.** Each answer clip is sent to Fire for transcription and then discarded; only text is saved. Debrief is recall-only: never accept uploads of real interview recordings.
4. **Never invent experience** in "stronger version" rewrites. Use only facts from the user's résumé or answers; use placeholders like `[add the result you achieved]` for missing details.
5. **Respectful at every pressure level.** No insults, slurs, or personal attacks in pressure mode or role-plays.
6. **Scores are practice feedback**, not assessments. Show a disclaimer for licensed/specialized professions.

## Interviewer rules (check after every phase)

`docs/INTERVIEWER_RULES.md` defines how the interviewer and coach must behave (core behavior, preparation, interview controls, adaptive difficulty, scoring, coaching, personalities, modes, report, story bank, safety). **At the end of every phase, check everything built so far against it**, add a dated section to `docs/RULES_CHECK.md` (✅ / ⚠️ / ❌ / ⏳ per area, with evidence), and file a ticket for every gap before calling the phase done.

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + Tailwind; MediaRecorder API records each answer (webm/opus) |
| In-browser | Monaco (code), Excalidraw (whiteboard), MediaPipe (body language, opt-in) |
| Backend | Flask (Python), JWT auth; the only component that talks to Fire |
| Speech-to-text | Fire `POST /v1/transcribe` (Whisper Large v3 Turbo) |
| Interviewer brain | Fire `POST /v1/chat` |
| Interviewer voice | Browser Web Speech API (free, default); Fire `POST /v1/speech` (`FIRE_SPEECH_MODEL`, default `tts-kokoro`, ~$0.0003 per short reply) behind `VOICE_PROVIDER=fire` |
| Database | MySQL 8 |
| Hosting | Oracle Cloud Always Free VM (Docker Compose + Caddy); frontend on Vercel |
| Optional later | LiveKit Agents (real-time voice, peer practice); Hume EVI (emotion experiment) |

No LiveKit, local Whisper, or local TTS is needed for phases 1–10.

## Fire API

- Capabilities list: https://fire.prosaga.net/v1/capabilities (check it for exact request/response shapes before writing a client).
- `POST /v1/transcribe`: JSON `{"audio": "data:audio/webm;base64,..."}` or an https URL; up to ~25 MB per clip; returns `{"text": ...}`. No timestamps.
- `POST /v1/chat`: all interviewer turns, plans, rubrics, scoring, rewrites.
- `POST /v1/speech`: interviewer audio (voice stage 3 onward).
- All calls live in `backend/app/services/fire.py` (one client: transcribe, chat, speech). Timeouts, one retry on 5xx, clear error messages to the frontend.
- Cap answers at 5 minutes (well under the 25 MB clip limit).
- Chat model is `FIRE_CHAT_MODEL` (default `gpt-4o-mini`; Fire's own default, Claude Sonnet, is far pricier).
- Track Fire spend per user in `usage_limits` from each response's `meta.price.usd`. **Total Fire budget: $1/month** (`FIRE_MONTHLY_BUDGET_USD=1`); new sessions pause when it's reached.

## Voice stages

| Stage | User | Interviewer | Fire calls per turn |
|---|---|---|---|
| 1. Text (dev only) | types | text | chat |
| 2. Speak in, text out (first release) | speaks | text | transcribe + chat |
| 3. Turn-based voice | speaks | speaks | transcribe + chat + speech |
| 4. Real-time (optional) | speaks | speaks, can interrupt | LiveKit agent |

Turn-based limits to design around: 1–3 s pause per turn (show a thinking indicator; later a pre-recorded "Mm-hm"); no mid-answer interruptions (nudges and pressure happen between answers); no timestamps (measure answer duration in the browser; pace = words ÷ duration); Whisper keeps "um"/"uh" (verified live 2026-10-09 with a synthesized clip), so filler counts are usable.

## Repo layout

```
/frontend          React app (Vite)
  /src/pages       Setup, Interview, Report, Dashboard, StoryBank, Decoder, Debrief
  /src/components  Recorder (record button + silence auto-stop), Timer, Transcript, ...
  /src/lib         api client
/backend           Flask API
  /app/routes      auth, documents, sessions, turns, reports, stories, debriefs, decoder
  /app/services    fire.py, parsing.py, planning.py, interviewer.py, timer.py, scoring.py, analytics.py, reports.py, stories.py, limits.py
  /app/prompts     one file per prompt (plan, rubric, interviewer_turn, score (incl. rewrite), report_summary, story_extract, decoder, ...)
  /app/modules     behavioral, resume_deepdive, technical, coding, system_design, case, roleplay, scenario, portfolio
  /app/modes       standard, reverse, pressure, panel, negotiation
  /app/models      SQLAlchemy models
  /migrations
  .env             FIRE_API_KEY, DB creds (never committed)
  .env.example     same keys, empty values
/evals             AI-candidate harness (strong / weak / rambling, across job fields): run.py, harness.py, fields.py
docker-compose.yml
Caddyfile
.gitignore         must include .env
```

## Core concepts

- **JD analysis** → field, seniority, competencies, which format modules fit.
- **Question plan** → sections with minute budgets that sum to the chosen duration, plus a reserve list of bonus questions. Editable by the user before starting.
- **Rubric** → per-session, built from JD competencies + universal criteria (structure, clarity, relevance).
- **Format modules** → reusable interviewer behaviors; any job = a mix of modules. New field = new mix, not new code.
- **A turn** = browser uploads clip + duration → Flask: Fire transcribe → save text → Fire chat (with timer state) → return next interviewer message (text, and audio from stage 3).
- **Timer lives in the backend**, not the LLM. Each chat call includes elapsed/remaining time per section so the interviewer moves on or wraps up between answers.
- **Reports generate after the session**, question by question in a background thread (`REPORTS_INLINE` runs them in-request for tests). One Fire chat call per question scores it and writes the stronger version; one more writes the verdict reasoning and top 3 takeaways. Weighted scores, verdict thresholds and delivery analytics (pace, fillers, time vs budget) are computed in Python. A failed run keeps finished questions; re-requesting only pays for the rest. "Try again" saves `attempt_no` > 1 and scores that answer alone (daily cap `DAILY_RETRIES`).

## Modes

standard · reverse (AI is the candidate) · pressure (levels 1–5, between-answer pressure, composure score) · debrief (recall-only, text saved, no audio) · panel (2–3 voices, stage 3+) · negotiation (recruiter role-play) · peer (needs optional real-time stage)

## Database tables

users · documents · jd_analyses · sessions · questions · answers (attempt_no for retries, started_ms/ended_ms/duration_ms) · evaluations · reports · stories · debriefs · peer_rooms · question_bank (spaced repetition) · usage_limits (incl. decoder_runs, fire_spend_usd)

Flexible LLM output is stored in JSON columns. No table stores audio/video. Documents auto-delete after 30 days unless saved.

## Usage and cost guards

- Per-user daily caps in `usage_limits` (start: 60 interview minutes, one 60-min session, 5 decoder runs) plus a $1/month total Fire spend ceiling.
- Default durations shown first: 10 and 30 minutes.
- Text-reply mode (stage 2) stays available as the cheaper option after spoken replies ship.

## Conventions

- Python: type hints, black formatting, one service function per responsibility.
- All prompts live in `/backend/app/prompts` as plain text templates, never inline.
- LLM responses that feed the app must be JSON validated with Pydantic; retry once on invalid JSON.
- Secrets only in `.env` (never committed); provide `.env.example`.
- Every feature gets at least one test; Fire calls are mocked in tests.
- Commit after each working feature.

## Build phases

1. Foundation (repo, `.env` + `.gitignore`, auth, schema, React shell)
2. Text-only brain — voice stage 1 (upload → JD analysis → plan → rubric via Fire chat; typed answers)
3. Speak in, text out — voice stage 2, first release (recorder, silence auto-stop, Fire transcribe → chat, timer, all durations)
4. Report and recommendations (scores, rewrites, delivery analytics, Try again)
5. Any-job support (modules, role-play, per-role rubrics)
6. Turn-based voice — voice stage 3 (Fire speech, persona voices, latency tricks)
7. Progress and story bank
8. Signature modes (decoder, debrief, reverse, pressure)
9. Extras (coding, whiteboard, panel, body language, gap analysis, company research, negotiation, cheat sheet, thank-you email)
10. Deploy and harden (Oracle VM, Vercel, caps, eval harness, privacy controls)
11. Optional: real-time voice with LiveKit (interruptions, peer practice)
12. Optional: Hume EVI experiment

**Current phase:** 10 done and LIVE (2026-10-11) as **InterVox**: frontend https://www.intervox.site (custom domain, Namecheap DNS; apex redirects to www) and https://intervox-pi.vercel.app (both Vercel, auto-deploy main; live `CORS_ORIGINS` lists all three, T-138), API https://intervox.duckdns.org on the devbox (Oracle refused the sign-up): `/srv/intervox`, `docker compose -f docker-compose.yml -f deploy/compose.devbox.yml`, nginx site `intervox` + certbot, root cron backup at 03:00 (`deploy/backup.sh`, `/root/backups`). Server deploys go through master: ticket `pending_review` with a deploy plan → user runs `pm approve T-n` → master pulls and rebuilds (website-only changes need no server deploy). Live budget: `FIRE_MONTHLY_BUDGET_USD=1.45` for October 2026 only, back to 1 in November. Privacy: daily purge of expired documents (`flask purge-expired`), Delete my data (`DELETE /api/auth/me`, spend kept in `anon_spend`), revocable read-only report links (`/shared/:token`), all in `services/privacy.py`. Admin usage page (`/admin`, `ADMIN_EMAILS`, `services/admin.py`). Hardening: login/signup/delete rate limits (`services/ratelimit.py`), `APP_ENV=production` refuses unsafe settings, `TRUST_PROXY` behind Caddy, gunicorn. Deploy: `docker-compose.yml` (MySQL 8.4, api, purge, Caddy) + `Caddyfile` + `deploy/env.example` + `deploy/backup.sh`; `frontend/vercel.json`. Eval harness: `evals/run.py --mock|--live` (AI candidates through the real API, simulated clock, budget guard, persona-drift checks; results in `evals/results/`, gitignored); a live run costs ~$0.02 per candidate. SQLite tests enforce foreign keys like MySQL. Scoring weights are fixed in code: role 70%, communication 30% (`planning.share_weights`). Open tickets: none (2026-10-13; API live at `6df2fde`, website at `f0d404a`; T-72 closed). Phases 1–9 done earlier (see docs/RULES_CHECK.md). Since launch: Run button (Python via Pyodide, JavaScript; in-browser Web Worker), 1–10 chosen coding/design questions (4/5-min floors; plan-decided rounds need 8/10 min), light-default theme with a dark switch, recorder fixes (latest-callback ref, 8 s early pause, stable Cancel). 2026-10-12/13 (T-89–T-135): many scorer/rewrite guards decided in code (gap check per point, off-subject match in `scoring.cap_off_subject`, `fill_result`, `restore_context`, `drop_named_subject`), pressure time-up cut-in (`answers.cut_off`), deleted-account tokens refused (JWT user lookup), panel + pressure together (`pressure.is_on`), no pressure on coding/system design questions (`pressure.exempt`), reverse-mode candidate voice (browser), panel handover without "Thanks." under pressure. T-136/T-137: delete an interview from the dashboard (`DELETE /api/sessions/<id>`; spend, caps and stories kept); every confirmation uses `components/ConfirmDialog.jsx` (`useDialogs().confirm/notify`, never `window.confirm`/`alert`); Your interviews collapses to 3 + Show all (N), remembered in localStorage. T-141/T-142: after an off-topic answer the interviewer leaves the question neutrally ("Let's leave <topic> there."); a general question (not a résumé item) answered about something else is caught by a narrow `subject_check` call (`scoring.off_general_subject`, only on a clear "no"; Relevance capped at 2, skeleton rewrite). Project report: `docs/project-report.md` + `docs/InterVox-Project-Report.pdf` (keep current when features change). Website-only changes go live via Vercel with no server deploy.

## Running locally

```bash
# Backend (python3-venv isn't installed on devbox, so bootstrap pip into the venv)
cd backend
python3 -m venv --without-pip .venv && python3 -m pip --python .venv/bin/python install pip
.venv/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env            # fill in DATABASE_URL, SECRET_KEY, JWT_SECRET_KEY
# On devbox: MySQL 8 is installed; DB creds are in the vault (ai_providers slug
# mock-interviewer-db) and the Fire key under slug fireapi. backend/.env is already filled.
FLASK_APP=wsgi.py .venv/bin/flask db upgrade
FLASK_APP=wsgi.py .venv/bin/flask run -p 5000
.venv/bin/python -m pytest      # tests use in-memory SQLite; Fire is always mocked
.venv/bin/black app tests

# Frontend (Vite proxies /api to Flask on :5000)
cd frontend && npm install && npm run dev
npm test && npm run lint
```

Schema changes: edit `app/models`, then `flask db migrate -m "..."` and review the generated file.
