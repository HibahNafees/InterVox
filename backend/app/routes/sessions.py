from typing import Literal

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from ..extensions import db
from ..models import Answer, CompanyResearch, Session, User
from ..services import (
    interviewer,
    limits,
    panel,
    planning,
    practice,
    pressure,
    voice,
)
from ..services.transcription import TranscriptionError, transcribe
from ..services.timer import is_paused, timer_state
from ..services import negotiation as nego
from ..services.body import BodyIn
from ..services.work import WorkIn
from .common import current_user_id, first_error
from .documents import owned_document

bp = Blueprint("sessions", __name__)

MAX_ANSWER_CHARS = 8000
PAUSED = "The interview is paused; resume it to continue"
REVERSE_ONLY = "Open this interview from Reverse mode"
MAX_ANSWER_MS = 5 * 60 * 1000
# The browser stops recording at 5 minutes; allow a little slack for timing.
DURATION_SLACK_MS = 10 * 1000


class CreateBody(BaseModel):
    resume_id: int
    jd_id: int
    duration_min: int = Field(ge=5, le=60)
    difficulty: Literal["entry", "mid", "senior"] = "mid"
    persona: Literal["friendly", "neutral", "tough"] = "neutral"
    focus: str = Field(default=planning.MIXED, max_length=40)
    # 0 = off; 1–5 = pressure mode (see services/pressure.py).
    pressure_level: int = Field(default=0, ge=0, le=5)
    # From POST /api/company/research: adds a "Why this company" section.
    company_research_id: int | None = None
    # panel: 2–3 interviewers; negotiation: a recruiter role-play about an offer.
    format: Literal["standard", "panel", "negotiation"] = "standard"
    # How many coding problems / whether to include a design question (None = the
    # plan decides). Only used when the job offers those modules.
    coding_problems: int | None = Field(default=None, ge=0, le=10)
    # How many system design questions (0–10); true/false still mean 1/0.
    system_design: int | None = Field(default=None, ge=0, le=10)
    negotiation: nego.NegotiationIn | None = None


class PlanSectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    module: str = "behavioral"
    minutes: int = Field(ge=1, le=60)
    questions: list[str] = Field(min_length=1, max_length=10)
    scenario: planning.Scenario | None = None

    @field_validator("questions")
    @classmethod
    def non_empty(cls, v: list[str]) -> list[str]:
        v = [q.strip() for q in v if q.strip()]
        if not v:
            raise ValueError("Each section needs at least one question")
        if any(len(q) > 1000 for q in v):
            raise ValueError("Questions must be under 1000 characters")
        return v


class PlanIn(BaseModel):
    sections: list[PlanSectionIn] = Field(min_length=1, max_length=6)
    reserve: list[planning.BonusOut] = Field(default_factory=list, max_length=6)


class TurnBody(BaseModel):
    text: str = Field(default="", max_length=MAX_ANSWER_CHARS)
    duration_ms: int | None = Field(
        default=None, ge=0, le=MAX_ANSWER_MS + DURATION_SLACK_MS
    )
    input_mode: Literal["text", "voice"] = "text"
    # Ask for Fire audio of the reply (VOICE_PROVIDER=fire, or a client with no
    # speech of its own when VOICE_FIRE_FALLBACK is on: T-148).
    speak: bool = False
    # Code from the editor or the whiteboard sketch (coding / system design).
    work: WorkIn | None = None
    # Opt-in camera feedback: percentages only, never video.
    body: BodyIn | None = None
    # Time ran out mid-answer: the line the interviewer said to stop them (T-109).
    interruption: str | None = None

    @field_validator("text")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("interruption")
    @classmethod
    def known_line(cls, v: str | None) -> str | None:
        if v is not None and v not in interviewer.INTERRUPTIONS:
            raise ValueError("Unknown interruption")
        return v

    @model_validator(mode="after")
    def some_answer(self) -> "TurnBody":
        if not self.text:
            if self.interruption is None:
                raise ValueError("Type an answer first")
            # Cut off before a word: saved as no answer, scored as too short.
            self.text = interviewer.NO_ANSWER_IN_TIME
        return self


def owned_session(session_id: int) -> Session | None:
    s = db.session.get(Session, session_id)
    return s if s is not None and s.user_id == current_user_id() else None


def _transcript(session: Session) -> list[dict]:
    asked = interviewer.asked_questions(session)
    answers = {
        a.question_id: a
        for a in db.session.scalars(
            db.select(Answer)
            .where(Answer.question_id.in_([q.id for q in asked]))
            .filter_by(attempt_no=1)
        )
    }
    out = []
    for q in asked:
        a = answers.get(q.id)
        out.append(
            {
                "question_id": q.id,
                "section": q.section,
                "interviewer": q.asked_text or q.text,
                "segments": q.asked_segments
                or [{"who": "interviewer", "text": q.asked_text or q.text}],
                "hint": q.hint_text,
                "is_follow_up": q.follow_up_of_id is not None,
                "is_bonus": q.is_bonus,
                "answer": a.transcript if a else None,
                "work": a.work_json if a else None,
                "duration_ms": a.duration_ms if a else None,
                "input_mode": a.input_mode if a else None,
                "cut_off": bool(a and a.cut_off),
            }
        )
    return out


def session_dict(session: Session, detail: bool = False) -> dict:
    plan = session.plan_json or {}
    data = {
        "id": session.id,
        "status": session.status,
        "mode": session.mode,
        "duration_min": session.duration_min,
        "difficulty": session.difficulty,
        "persona": session.persona,
        "role_title": plan.get("role_title", ""),
        "focus": plan.get("focus", planning.MIXED),
        "resume_id": session.resume_id,
        "jd_id": session.jd_id,
        "started_at": (
            session.started_at.isoformat() + "Z" if session.started_at else None
        ),
        "ended_at": session.ended_at.isoformat() + "Z" if session.ended_at else None,
        "created_at": session.created_at.isoformat() + "Z",
    }
    if detail:
        data["analysis"] = plan.get("analysis")
        data["plan"] = planning.plan_view(session)
        data["rubric"] = session.rubric_json
        data["voice"] = voice.info(session)
        data["pressure"] = pressure.info(session)
        data["panel"] = panel.info(session)
        data["negotiation"] = nego.info(session)
        data["transcript"] = _transcript(session)
        data["interruptions"] = interviewer.INTERRUPTIONS
        data["timer"] = (
            timer_state(session, interviewer.asked_questions(session)).to_dict()
            if session.started_at
            else None
        )
    return data


@bp.post("")
@jwt_required()
def create():
    """Analyze the JD, then build the question plan and rubric (3 Fire chat calls at most)."""
    try:
        body = CreateBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    user_id = current_user_id()
    resume = owned_document(body.resume_id, "resume")
    jd = owned_document(body.jd_id, "job_description")
    if resume is None or jd is None:
        return jsonify(error="Choose your résumé and a job description first"), 404

    # Pressure works one-to-one or with a panel; a negotiation is its own role-play.
    if body.format == "negotiation" and body.pressure_level:
        return jsonify(error="Pressure mode doesn't apply to a negotiation"), 400
    if body.format == "negotiation":
        if body.negotiation is None:
            return jsonify(error="Enter the offer and what you're aiming for"), 400
        if not nego.MIN_MINUTES <= body.duration_min <= nego.MAX_MINUTES:
            return (
                jsonify(
                    error=f"A negotiation runs {nego.MIN_MINUTES} to "
                    f"{nego.MAX_MINUTES} minutes"
                ),
                400,
            )

    limits.check_can_plan(user_id)
    limits.check_can_start(user_id, body.duration_min)
    analysis = planning.analyze_jd(user_id, jd)
    summary = planning.analysis_summary(analysis)
    research = None
    if body.format == "negotiation":
        # Fixed recruiter scenario and rubric: no Fire call to plan it.
        user = db.session.get(User, user_id)
        plan = nego.plan(
            body.negotiation,
            summary["role_title"] or "this",
            user.name if user else "",
            body.persona,
            body.duration_min,
        )
        rubric = nego.RUBRIC.model_copy(deep=True)
    else:
        if body.focus != planning.MIXED and body.focus not in planning.offered_modules(
            analysis
        ):
            return jsonify(error="That interview type doesn't fit this job"), 400
        plan = planning.build_plan(
            user_id,
            resume,
            analysis,
            body.duration_min,
            body.difficulty,
            body.focus,
            coding=body.coding_problems,
            system_design=body.system_design,
            pressure_level=body.pressure_level,
        )
        rubric = planning.build_rubric(user_id, analysis, body.difficulty, body.focus)
        research = (
            db.session.get(CompanyResearch, body.company_research_id)
            if body.company_research_id
            else None
        )
        if research is not None:
            planning.add_why_us(plan, research.result_json["why_us_questions"])

    mode = (
        body.format
        if body.format != "standard"
        else "pressure" if body.pressure_level else "standard"
    )
    session = Session(
        user_id=user_id,
        resume_id=resume.id,
        jd_id=jd.id,
        mode=mode,
        pressure_level=body.pressure_level or None,
        duration_min=body.duration_min,
        difficulty=body.difficulty,
        persona=body.persona,
        status="planned",
        rubric_json=rubric.model_dump(),
        plan_json={
            "analysis": summary,
            "jd_analysis_id": analysis.id,
            "focus": body.focus,
            **({"pressure_start": body.pressure_level} if body.pressure_level else {}),
            **(
                {"negotiation": body.negotiation.model_dump()}
                if body.format == "negotiation"
                else {}
            ),
            **(
                {
                    "company": {
                        k: research.result_json[k]
                        for k in ("company", "summary", "talking_points")
                    }
                }
                if research is not None
                else {}
            ),
        },
    )
    db.session.add(session)
    db.session.flush()
    planning.save_plan(session, plan, role_title=summary["role_title"])
    return jsonify(session=session_dict(session, detail=True)), 201


class PracticeBody(BaseModel):
    duration_min: int = Field(default=10, ge=5, le=30)


@bp.post("/practice")
@jwt_required()
def practice_session():
    """A weak-spot interview from the question bank (no Fire call to plan it)."""
    try:
        body = PracticeBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400
    user_id = current_user_id()
    limits.check_can_start(user_id, body.duration_min)
    session = practice.build_session(user_id, body.duration_min)
    if session is None:
        return (
            jsonify(
                error="Nothing to practice yet: questions you score under 4 show up here."
            ),
            404,
        )
    return jsonify(session=session_dict(session, detail=True)), 201


@bp.get("")
@jwt_required()
def list_sessions():
    rows = db.session.scalars(
        db.select(Session)
        .filter_by(user_id=current_user_id())
        .order_by(Session.created_at.desc())
        .limit(50)
    )
    return jsonify(sessions=[session_dict(s) for s in rows])


@bp.get("/<int:session_id>")
@jwt_required()
def get_session(session_id: int):
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    return jsonify(session=session_dict(session, detail=True))


@bp.delete("/<int:session_id>")
@jwt_required()
def delete_session(session_id: int):
    """Delete an interview with its questions, answers and report (T-136).

    Its Fire spend and daily minutes stay counted in usage_limits, and the
    story bank keeps any stories drawn from it.
    """
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    db.session.delete(session)
    db.session.commit()
    return jsonify(ok=True)


@bp.put("/<int:session_id>/plan")
@jwt_required()
def edit_plan(session_id: int):
    """Replace the question plan before the interview starts."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status != "planned":
        return (
            jsonify(error="The plan can't change once the interview has started"),
            409,
        )
    if session.mode == "negotiation":
        return jsonify(error="A negotiation's plan can't be edited"), 409
    try:
        body = PlanIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    total = sum(s.minutes for s in body.sections)
    if total != session.duration_min:
        return (
            jsonify(
                error=f"Section minutes add up to {total}; "
                f"they must add up to {session.duration_min}"
            ),
            400,
        )
    names = [s.name.strip() for s in body.sections]
    if len(set(names)) != len(names):
        return jsonify(error="Section names must be different"), 400

    try:
        plan = planning.PlanOut.model_validate(body.model_dump())
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400
    planning.save_plan(session, plan)
    return jsonify(session=session_dict(session, detail=True))


@bp.post("/<int:session_id>/start")
@jwt_required()
def start(session_id: int):
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.mode == "reverse":
        return jsonify(error=REVERSE_ONLY), 409
    if session.status != "planned":
        return jsonify(error="This interview has already started"), 409
    user_id = current_user_id()
    limits.check_can_start(user_id, session.duration_min)
    user = db.session.get(User, user_id)
    first = interviewer.start(session, user.name)
    limits.record_session_start(user_id, session.duration_min)
    speak = bool((request.get_json(silent=True) or {}).get("speak"))
    speech = voice.synthesize(user_id, session, first.asked_segments) if speak else None
    return jsonify(session=session_dict(session, detail=True), speech=speech)


@bp.post("/<int:session_id>/turns")
@jwt_required()
def turn(session_id: int):
    """Typed answer to the current question → the interviewer's next message."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.mode == "reverse":
        return jsonify(error=REVERSE_ONLY), 409
    if session.status != "active":
        return jsonify(error="This interview is not in progress"), 409
    if is_paused(session):
        return jsonify(error=PAUSED), 409
    try:
        body = TurnBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    user_id = current_user_id()
    result = interviewer.take_turn(
        session,
        user_id,
        body.text,
        body.duration_ms,
        body.input_mode,
        body.work.model_dump(exclude_none=True) if body.work else None,
        body.body.model_dump() if body.body else None,
        body.interruption,
    )
    # The interruption was already said in the browser when time ran out.
    to_say = [s for s in result["segments"] if not s.get("interruption")]
    speech = voice.synthesize(user_id, session, to_say) if body.speak else None
    return jsonify(
        turn=result, session=session_dict(session, detail=True), speech=speech
    )


@bp.post("/<int:session_id>/transcribe")
@jwt_required()
def transcribe_answer(session_id: int):
    """Spoken answer clip (multipart field "audio") → text. The clip is not stored.

    The browser then sends the text to /turns (or a report's "Try again"), so a
    failed chat call can be retried without paying to transcribe the clip again.
    """
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status == "completed":
        limits.check_can_retry(current_user_id())
    elif session.status != "active":
        return jsonify(error="This interview is not in progress"), 409
    elif is_paused(session):
        return jsonify(error=PAUSED), 409
    clip = request.files.get("audio")
    if clip is None:
        return jsonify(error="audio is required"), 400
    limit = current_app.config["MAX_AUDIO_BYTES"]
    audio = clip.read(limit + 1)
    if len(audio) > limit:
        return (
            jsonify(
                error="That recording is too long; answers are capped at 5 minutes"
            ),
            413,
        )
    try:
        text = transcribe(current_user_id(), audio, clip.mimetype)
    except TranscriptionError as err:
        return jsonify(error=err.message), err.status
    return jsonify(text=text)


def _live(session_id: int, allow_paused: bool = False):
    """(session, None) for an active interview, else (None, error response)."""
    session = owned_session(session_id)
    if session is None:
        return None, (jsonify(error="Interview not found"), 404)
    if session.mode == "reverse":
        return None, (jsonify(error=REVERSE_ONLY), 409)
    if session.status != "active":
        return None, (jsonify(error="This interview is not in progress"), 409)
    if is_paused(session) and not allow_paused:
        return None, (jsonify(error=PAUSED), 409)
    return session, None


@bp.post("/<int:session_id>/hint")
@jwt_required()
def hint(session_id: int):
    """One hint for the current question (one small Fire call, then cached)."""
    session, err = _live(session_id)
    if err:
        return err
    try:
        text = interviewer.hint(session, current_user_id())
    except ValueError as e:
        return jsonify(error=str(e)), 409
    return jsonify(hint=text, session=session_dict(session, detail=True))


@bp.post("/<int:session_id>/skip")
@jwt_required()
def skip(session_id: int):
    """Skip the current question (no Fire call); it's listed as unanswered."""
    session, err = _live(session_id)
    if err:
        return err
    result = interviewer.skip(session)
    return jsonify(turn=result, session=session_dict(session, detail=True), speech=None)


@bp.post("/<int:session_id>/pause")
@jwt_required()
def pause(session_id: int):
    session, err = _live(session_id, allow_paused=True)
    if err:
        return err
    interviewer.pause(session)
    return jsonify(session=session_dict(session, detail=True))


@bp.post("/<int:session_id>/resume")
@jwt_required()
def resume(session_id: int):
    session, err = _live(session_id, allow_paused=True)
    if err:
        return err
    interviewer.resume(session)
    return jsonify(session=session_dict(session, detail=True))


class PressureBody(BaseModel):
    level: int = Field(ge=0, le=5)


@bp.post("/<int:session_id>/pressure")
@jwt_required()
def ease_pressure(session_id: int):
    """Lower or stop the pressure at any time (it can't be raised mid-interview)."""
    session, err = _live(session_id, allow_paused=True)
    if err:
        return err
    if not pressure.is_on(session):
        return jsonify(error="This isn't a pressure interview"), 409
    try:
        body = PressureBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify(error=first_error(e)), 400
    pressure.lower(session, body.level)
    return jsonify(session=session_dict(session, detail=True))


@bp.post("/<int:session_id>/end")
@jwt_required()
def end(session_id: int):
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status == "planned":
        session.status = "abandoned"
        db.session.commit()
    elif session.status == "active":
        interviewer.end(session)
    return jsonify(session=session_dict(session, detail=True))
