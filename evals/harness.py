"""Eval harness: AI candidates (strong / weak / rambling) through full interviews.

Each run signs in an eval user, uploads a field's résumé and job description,
plans a 10-minute interview, answers every interviewer message with a candidate
reply, ends the session and builds the report, all through the real Flask API
(in-process test client). The clock is moved forward by each answer's length so
the backend timer behaves as in a real interview.

Live mode uses Fire for both sides and records the spend against the eval users,
so it counts toward the $1 monthly budget. Mock mode uses the test FakeFire and
canned answers (free); it checks the plumbing, not the scores.
"""

import json
import re
import secrets
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path
from string import Template
from typing import Callable

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from flask_jwt_extended import create_access_token  # noqa: E402

from app.extensions import db  # noqa: E402
from app.models import Question, Session, User  # noqa: E402
from app.services.fire import get_fire  # noqa: E402
from app.services.limits import month_spend_usd, record_fire_call  # noqa: E402
from app.services.scoring import STOPWORDS, _content_words, _stem  # noqa: E402

from fields import FIELDS  # noqa: E402

PERSONAS = {
    "strong": (
        "Strong and well prepared. Answers the actual question first, then gives one "
        "specific example from the résumé with the situation, what they personally "
        "did and the measurable result (only numbers that are in the résumé). "
        "120 to 180 words, natural spoken style."
    ),
    "weak": (
        "Underprepared and vague. Speaks only in generalities ('we just tried to "
        "do our best', 'it went fine'), says 'we' instead of 'I', hedges ('I "
        "guess', 'kind of'). NEVER state any number, percentage, metric, duration "
        "or outcome, never name a tool or a specific project, and don't use the "
        "résumé's achievements. 25 to 50 words."
    ),
    "rambling": (
        "Knows the material but rambles. Spend the first half on background, "
        "context and side stories before getting to the question; repeat points; "
        "use filler ('so, um, basically', 'anyway'); mention the actual result only "
        "in passing near the end, if at all. Never use a clear Situation-Action-Result "
        "order. At least 220 words, up to 280."
    ),
}
CANNED = {
    "strong": "At Northwind I owned webhook delivery. Failures were 3%, so I moved it "
    "to a queue with retries and dead-lettering, and failed deliveries fell to 0.2%.",
    "weak": "I guess we kind of worked on that as a team and it went fine.",
    "rambling": "So, um, basically, there's a lot of background here, and before I "
    "get to it I should say the team changed a lot, and anyway we did some queue work.",
}
# What each persona's answers must look like, or the run measures the wrong thing.
DRIFT = {
    "weak": {"max_words": 70, "numbers": False},
    "rambling": {"min_words": 140},
}
DIGIT_RE = re.compile(r"\d")
WORDS_PER_SEC = 2.4  # typical speaking pace, to give typed answers a duration
INTERVIEWER_SEC = 8  # time the interviewer takes to speak between answers
MAX_TURNS = 18
UNSAFE = re.compile(
    r"\b(stupid|idiot|dumb|pathetic|useless|incompetent|shut up|loser)\b", re.I
)
# Words in a missing point that say what kind of point it is, not its content.
GENERIC = {
    "describ",
    "detai",
    "expla",
    "menti",
    "speci",
    "provi",
    "inclu",
    "clear",
    "quant",
    "examp",
    "candi",
    "their",
    "would",
    "could",
    "any",
}


@dataclass
class Run:
    field: str
    persona: str
    session_id: int | None = None
    status: str = ""
    turns: int = 0
    overall: float | None = None
    verdict: str | None = None
    question_scores: list = field(default_factory=list)
    star_result: list = field(default_factory=list)  # behavioral answers only
    possible_false_gaps: list = field(default_factory=list)
    unsafe_lines: list = field(default_factory=list)
    answers: list = field(default_factory=list)
    # Answers to the scored questions only (main + follow-ups), for the persona check.
    scored_answers: list = field(default_factory=list)
    spend_usd: float = 0.0
    seconds: float = 0.0
    error: str = ""


def _clock_forward(session_id: int, seconds: float) -> None:
    """Pretend `seconds` passed: move the session's timestamps back."""
    d = timedelta(seconds=seconds)
    s = db.session.get(Session, session_id)
    if s.started_at:
        s.started_at -= d
    for q in db.session.scalars(db.select(Question).filter_by(session_id=session_id)):
        if q.asked_at:
            q.asked_at -= d
    db.session.commit()


def _eval_user(field_key: str, persona: str) -> User:
    email = f"eval+{field_key}-{persona}@example.com"
    user = db.session.scalar(db.select(User).filter_by(email=email))
    if user is None:
        user = User(email=email, name=f"Eval {persona}")
        user.set_password(secrets.token_urlsafe(24))
        db.session.add(user)
        db.session.commit()
    return user


def live_candidate(user_id: int, resume: str, persona: str) -> Callable:
    template = Template((ROOT / "prompts" / "candidate.txt").read_text())

    def reply(message: str, history: list[tuple[str, str]]) -> str:
        lines = "\n".join(f"Interviewer: {q}\nCandidate: {a}" for q, a in history)
        prompt = template.substitute(
            resume=resume,
            style=PERSONAS[persona],
            history=lines or "(this is the start)",
            message=message,
        )
        from flask import current_app

        result = get_fire().chat(
            [{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
            model=current_app.config.get("FIRE_CHAT_MODEL"),
        )
        record_fire_call(user_id, result.price_usd)
        return result.content.strip().strip('"')

    return reply


def mock_candidate(persona: str) -> Callable:
    return lambda message, history: CANNED[persona]


def _possible_false_gaps(question: dict) -> list[dict]:
    """Gaps whose distinctive words appear in the candidate's own answers.

    A cheap flag for T-72, for a person to review: the scorer said the point
    was missing, but the answer uses the same words."""
    said = " ".join(x["answer"] for x in question["exchange"])
    said_stems = {_stem(w) for w in _content_words(said)}
    asked = {_stem(w) for w in _content_words(question["text"])}
    out = []
    for m in (question["evaluation"] or {}).get("missing_points") or []:
        if m.get("covered"):
            continue
        words = [
            w
            for w in _content_words(m["point"])
            if w not in STOPWORDS and _stem(w) not in GENERIC | asked
        ]
        hits = sorted({w for w in words if _stem(w) in said_stems})
        if len(hits) >= 2 and len(hits) >= 0.75 * len(words):
            out.append(
                {
                    "question_id": question["question_id"],
                    "point": m["point"],
                    "words": hits,
                }
            )
    return out


def run_one(app, field_key: str, persona: str, live: bool) -> Run:
    run = Run(field=field_key, persona=persona)
    started = time.monotonic()
    spend_before = month_spend_usd()
    f = FIELDS[field_key]
    client = app.test_client()
    user = _eval_user(field_key, persona)
    auth = {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}

    def post(path: str, body: dict | None = None):
        r = client.post(f"/api{path}", json=body or {}, headers=auth)
        if r.status_code >= 400:
            raise RuntimeError(f"POST {path}: {r.status_code} {r.get_json()}")
        return r.get_json()

    try:
        resume_id = post("/documents", {"kind": "resume", "text": f["resume"]})[
            "document"
        ]["id"]
        jd_id = post("/documents", {"kind": "job_description", "text": f["jd"]})[
            "document"
        ]["id"]
        session = post(
            "/sessions",
            {
                "resume_id": resume_id,
                "jd_id": jd_id,
                "duration_min": 10,
                "persona": "neutral",
                "coding_problems": 0,
                "system_design": False,
            },
        )["session"]
        run.session_id = sid = session["id"]
        session = post(f"/sessions/{sid}/start")["session"]
        reply = (
            live_candidate(user.id, f["resume"], persona)
            if live
            else mock_candidate(persona)
        )
        history: list[tuple[str, str]] = []
        while session["status"] != "completed" and run.turns < MAX_TURNS:
            message = session["transcript"][-1]["interviewer"]
            if UNSAFE.search(message or ""):
                run.unsafe_lines.append(message)
            answer = reply(message, history)
            history.append((message, answer))
            run.answers.append(answer)
            duration = len(answer.split()) / WORDS_PER_SEC
            _clock_forward(sid, duration + INTERVIEWER_SEC)
            session = post(
                f"/sessions/{sid}/turns",
                {"text": answer, "duration_ms": int(duration * 1000)},
            )["session"]
            run.turns += 1
        for line in session["transcript"]:
            if UNSAFE.search(line.get("interviewer") or ""):
                run.unsafe_lines.append(line["interviewer"])
        if session["status"] != "completed":
            post(f"/sessions/{sid}/end")
        run.status = "completed"
        post(f"/sessions/{sid}/report")
        report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()[
            "report"
        ]
        run.status = f"report {report['status']}"
        run.overall = report["overall_score"]
        run.verdict = report["verdict"]
        for q in report["questions"]:
            e = q["evaluation"] or {}
            run.question_scores.append(e.get("score"))
            run.scored_answers += [
                x["answer"] for x in q.get("exchange") or [] if x.get("answer")
            ]
            if e.get("star"):
                run.star_result.append(bool(e["star"].get("result")))
            run.possible_false_gaps += _possible_false_gaps(q)
    except Exception as err:  # keep going with the other runs
        db.session.rollback()
        run.error = str(err)[:500]
    run.spend_usd = round(month_spend_usd() - spend_before, 6)
    run.seconds = round(time.monotonic() - started, 1)
    return run


def persona_drift(r: Run) -> str:
    """Why the candidate didn't behave like its persona ("" if it did).

    Judges only the answers to scored questions: small talk and the wrap-up
    ("any questions for me?") are short for every persona, and a question for the
    interviewer may name a number ("the Grade 4 team") without being a metric (T-161).
    """
    rule = DRIFT.get(r.persona)
    answers = r.scored_answers or (r.answers[1:-1] if len(r.answers) > 2 else r.answers)
    if not rule or not answers:
        return ""
    avg = sum(len(a.split()) for a in answers) / len(answers)
    if "max_words" in rule and avg > rule["max_words"]:
        return f"answers average {avg:.0f} words (max {rule['max_words']})"
    if "min_words" in rule and avg < rule["min_words"]:
        return f"answers average {avg:.0f} words (min {rule['min_words']})"
    if rule.get("numbers") is False:
        n = sum(bool(DIGIT_RE.search(a)) for a in answers)
        if n:
            return f"{n} of {len(answers)} answers state numbers"
    return ""


def checks(runs: list[Run]) -> list[tuple[str, bool]]:
    """Expectations a sound interviewer and scorer should meet."""
    out = []
    by = {(r.field, r.persona): r for r in runs}
    for r in runs:
        if r.persona in DRIFT and r.answers:
            drift = persona_drift(r)
            out.append(
                (
                    f"{r.field}/{r.persona}: candidate stayed in persona {drift and '(' + drift + ')'}".rstrip(),
                    not drift,
                )
            )
        out.append((f"{r.field}/{r.persona}: finished without errors", not r.error))
        out.append(
            (
                f"{r.field}/{r.persona}: no disrespectful interviewer lines",
                not r.unsafe_lines,
            )
        )
    for field_key in sorted({r.field for r in runs}):
        strong = by.get((field_key, "strong"))
        for other in ("weak", "rambling"):
            o = by.get((field_key, other))
            if strong and o and strong.overall is not None and o.overall is not None:
                out.append(
                    (
                        f"{field_key}: strong ({strong.overall}) scores above {other} ({o.overall})",
                        strong.overall > o.overall,
                    )
                )
            if o and o.verdict:
                out.append(
                    (
                        f"{field_key}/{other}: verdict is not hire ({o.verdict})",
                        o.verdict != "hire",
                    )
                )
        if strong and strong.verdict:
            out.append(
                (
                    f"{field_key}/strong: verdict is not no hire ({strong.verdict})",
                    strong.verdict != "no hire",
                )
            )
    return out


def summarize(runs: list[Run]) -> str:
    lines = [
        f"{'run':<20} {'turns':>5} {'overall':>7} {'verdict':<10} {'STAR result':>11} {'gaps?':>5} {'spend':>8}",
    ]
    for r in runs:
        star = f"{sum(r.star_result)}/{len(r.star_result)}" if r.star_result else "-"
        lines.append(
            f"{r.field + '/' + r.persona:<20} {r.turns:>5} {str(r.overall):>7} "
            f"{str(r.verdict):<10} {star:>11} {len(r.possible_false_gaps):>5} ${r.spend_usd:.4f}"
            + (f"  ERROR: {r.error}" if r.error else "")
        )
    total = sum(r.spend_usd for r in runs)
    lines.append(f"total spend ${total:.4f}")
    return "\n".join(lines)


def save(runs: list[Run], results: list[tuple[str, bool]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / time.strftime("eval-%Y%m%d-%H%M%S.json")
    path.write_text(
        json.dumps(
            {"runs": [asdict(r) for r in runs], "checks": results},
            indent=2,
            default=str,
        )
    )
    return path
