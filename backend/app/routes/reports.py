from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError

from ..extensions import db
from ..models import Answer, Question, Session
from ..services import access, afterwards, limits, privacy, reports, scoring
from .common import current_user_id, first_error
from .sessions import TurnBody, owned_session

bp = Blueprint("reports", __name__)
shared_bp = Blueprint("shared", __name__)


@bp.get("/<int:session_id>/report")
@jwt_required()
def get_report(session_id: int):
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    report = reports.get_report(session)
    if report is None:
        return jsonify(error="No report yet"), 404
    return jsonify(report=reports.report_dict(session, report))


@bp.post("/<int:session_id>/report")
@jwt_required()
def create_report(session_id: int):
    """Start (or resume) building the report; poll GET for progress."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.mode == "reverse":
        return jsonify(error="Reverse interviews have their own feedback"), 409
    if session.status != "completed":
        return jsonify(error="Finish the interview to get your report"), 409
    report = reports.request_report(session)
    return jsonify(report=reports.report_dict(session, report)), 202


@bp.post("/<int:session_id>/report/share")
@jwt_required()
def share_report(session_id: int):
    """A read-only link to the report (for a mentor or friend); revocable."""
    session = owned_session(session_id)
    report = reports.get_report(session) if session else None
    if report is None or report.status != "ready":
        return jsonify(error="Share the report once it's ready"), 409
    if access.current_is_demo():
        return jsonify(error="Demo reports can't be shared"), 403
    return jsonify(share_token=privacy.share_report(report))


@bp.delete("/<int:session_id>/report/share")
@jwt_required()
def revoke_share(session_id: int):
    session = owned_session(session_id)
    report = reports.get_report(session) if session else None
    if report is None:
        return jsonify(error="No report yet"), 404
    privacy.revoke_share(report)
    return jsonify(ok=True)


@shared_bp.get("/reports/<token>")
def shared_report(token: str):
    """The public, read-only view of a shared report (no login)."""
    report = privacy.shared_report(token)
    if report is None:
        return jsonify(error="This link was turned off or never existed"), 404
    data = reports.report_dict(db.session.get(Session, report.session_id), report)
    data.pop("share_token", None)
    if data.get("debrief"):
        # Which saved job posting it was is the owner's business.
        data["debrief"] = {**data["debrief"], "jd": None}
    return jsonify(report={**data, "shared": True})


@bp.post("/<int:session_id>/questions/<int:question_id>/retry")
@jwt_required()
def retry(session_id: int, question_id: int):
    """ "Try again" on a question: score the new answer and show before/after."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    if session.status != "completed":
        return jsonify(error="Finish the interview before retrying questions"), 409
    question = db.session.get(Question, question_id)
    first = db.session.scalar(
        db.select(Answer).filter_by(question_id=question_id, attempt_no=1)
    )
    if (
        question is None
        or question.session_id != session.id
        or question.follow_up_of_id is not None
        or first is None
    ):
        return jsonify(error="Question not found"), 404
    try:
        body = TurnBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    user_id = current_user_id()
    limits.check_can_retry(user_id)
    answer = reports.retry(
        user_id,
        session,
        question,
        body.text,
        body.duration_ms,
        body.input_mode,
        body.work.model_dump() if body.work else None,
    )
    evals = reports.evaluations_for([first.id, answer.id])
    before = evals.get(first.id)
    return (
        jsonify(
            attempt={
                "attempt_no": answer.attempt_no,
                "answer": answer.transcript,
                "work": answer.work_json,
                "input_mode": answer.input_mode,
                "evaluation": scoring.evaluation_dict(evals.get(answer.id)),
            },
            before_score=before.score if before else None,
        ),
        201,
    )


@bp.get("/<int:session_id>/cheatsheet")
@jwt_required()
def cheat_sheet(session_id: int):
    """One-page prep sheet from the user's own stories, numbers and weak spots."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    report = reports.get_report(session)
    if report is None or report.status != "ready":
        return jsonify(error="The report isn't ready yet"), 409
    return jsonify(sheet=afterwards.cheat_sheet(session, report))


@bp.post("/<int:session_id>/thank-you")
@jwt_required()
def thank_you(session_id: int):
    """A drafted thank-you email (one Fire call, then kept)."""
    session = owned_session(session_id)
    if session is None:
        return jsonify(error="Interview not found"), 404
    report = reports.get_report(session)
    if report is None or report.status != "ready":
        return jsonify(error="The report isn't ready yet"), 409
    limits.check_budget()
    return jsonify(email=afterwards.thank_you(current_user_id(), session, report))
