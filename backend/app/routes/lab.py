from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import BaseModel, Field, ValidationError

from ..services import lab
from .common import current_user_id, first_error
from .documents import owned_document

bp = Blueprint("lab", __name__)


class ChatIn(BaseModel):
    messages: list[lab.Turn] = Field(min_length=1, max_length=60)
    resume_id: int | None = None
    jd_id: int | None = None
    settings: lab.Settings = Field(default_factory=lab.Settings)


class DebateIn(BaseModel):
    question: str = Field(min_length=1, max_length=lab.MAX_TEXT_CHARS)
    answer: str = Field(min_length=1, max_length=lab.MAX_TEXT_CHARS)
    settings: lab.Settings = Field(default_factory=lab.Settings)


class CompareIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=lab.MAX_TEXT_CHARS)
    sides: list[lab.Side] = Field(min_length=2, max_length=2)


def _parse(model: type[BaseModel]):
    try:
        return model.model_validate(request.get_json(silent=True) or {}), None
    except ValidationError as err:
        return None, (jsonify(error=first_error(err)), 400)


def _with_usage(user_id: int, **body):
    return jsonify(**body, usage=lab.usage(user_id))


@bp.get("")
@jwt_required()
def overview():
    """Defaults for Settings (and Reset), the model list and today's usage."""
    return _with_usage(current_user_id(), defaults=lab.defaults())


@bp.post("/chat")
@jwt_required()
def chat():
    body, error = _parse(ChatIn)
    if error:
        return error
    texts = {}
    for key, kind in (("resume_id", "resume"), ("jd_id", "job_description")):
        doc_id = getattr(body, key)
        if doc_id is not None:
            doc = owned_document(doc_id, kind)
            if doc is None:
                return jsonify(error="Document not found"), 404
            texts[kind] = doc.raw_text
    user_id = current_user_id()
    try:
        reply = lab.prep_chat(
            user_id,
            body.messages,
            body.settings,
            resume=texts.get("resume"),
            jd=texts.get("job_description"),
        )
    except lab.LabError as err:
        return jsonify(error=err.message), err.status
    return _with_usage(user_id, reply=reply)


@bp.post("/debate")
@jwt_required()
def debate():
    body, error = _parse(DebateIn)
    if error:
        return error
    user_id = current_user_id()
    result = lab.debate(
        user_id, body.question.strip(), body.answer.strip(), body.settings
    )
    return _with_usage(user_id, **result)


@bp.post("/compare")
@jwt_required()
def compare():
    body, error = _parse(CompareIn)
    if error:
        return error
    user_id = current_user_id()
    answers = lab.compare(user_id, body.prompt.strip(), body.sides)
    return _with_usage(user_id, answers=answers)
