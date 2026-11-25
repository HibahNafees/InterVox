"""Organization API (T-166). Every route is wrapped in @org_route: anyone who
may not use the feature (ORG_FEATURE, ADMIN_EMAILS) gets a plain 404, and so
does a member asking for another org's data."""

import re
from datetime import date

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..extensions import db
from ..models import Assignment, Organization, OrgMember, Session, User
from ..services import orgs, reports
from ..services.access import not_found, org_route
from .common import first_error

bp = Blueprint("orgs", __name__)

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_RE = re.compile(r"^data:image/(png|jpeg|webp|svg\+xml);base64,[A-Za-z0-9+/=]+$")
MAX_LOGO_CHARS = 140_000  # ~100 KB image


def _bad(err: ValidationError):
    return jsonify(error=first_error(err)), 400


class OrgBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Enter the organization's name")
        return v


class BrandingBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = None
    logo: str | None = None  # "" removes the logo

    @field_validator("color")
    @classmethod
    def valid_color(cls, v: str | None) -> str | None:
        if v is not None and not COLOR_RE.match(v):
            raise ValueError("Color must look like #1f6f8b")
        return v.lower() if v else v

    @field_validator("logo")
    @classmethod
    def valid_logo(cls, v: str | None) -> str | None:
        if v and (len(v) > MAX_LOGO_CHARS or not LOGO_RE.match(v)):
            raise ValueError("Logo must be a PNG, JPEG, WebP or SVG image under 100 KB")
        return v


class ConsentBody(BaseModel):
    share: bool


class AssignmentBody(BaseModel):
    candidate_id: int
    role_title: str = Field(min_length=1, max_length=160)
    jd_text: str = Field(min_length=20, max_length=20000)
    duration_min: int = Field(ge=5, le=60)
    due_date: date | None = None


class LinkBody(BaseModel):
    session_id: int


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Write a comment first")
        return v


# --- the signed-in user's own memberships ------------------------------------


@bp.get("/mine")
@org_route
def mine(user: User):
    return jsonify(
        orgs=orgs.memberships(user.id),
        assignments=[orgs.assignment_dict(a) for a in orgs.my_assignments(user.id)],
    )


def _my_assignment(user: User, assignment_id: int) -> Assignment | None:
    a = db.session.get(Assignment, assignment_id)
    if a is None or a.candidate_id != user.id:
        return None
    if orgs.member(a.org_id, user.id) is None:
        return None
    return a


@bp.get("/mine/assignments/<int:assignment_id>")
@org_route
def my_assignment(user: User, assignment_id: int):
    a = _my_assignment(user, assignment_id)
    if a is None:
        return not_found()
    return jsonify(assignment=orgs.assignment_dict(a, with_jd=True))


@bp.post("/mine/assignments/<int:assignment_id>/link")
@org_route
def link_assignment(user: User, assignment_id: int):
    """Tie the interview the candidate just set up to the assignment."""
    a = _my_assignment(user, assignment_id)
    if a is None:
        return not_found()
    try:
        body = LinkBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return _bad(err)
    session = db.session.get(Session, body.session_id)
    if session is None or session.user_id != user.id:
        return not_found()
    a.session_id = session.id
    db.session.commit()
    return jsonify(assignment=orgs.assignment_dict(a))


@bp.get("/mine/sessions/<int:session_id>/comments")
@org_route
def my_comments(user: User, session_id: int):
    """Coach comments on the candidate's own report."""
    session = db.session.get(Session, session_id)
    if session is None or session.user_id != user.id:
        return not_found()
    return jsonify(comments=orgs.comments(session_id))


@bp.put("/<int:org_id>/consent")
@org_route
def consent(user: User, org_id: int):
    m = orgs.member(org_id, user.id)
    if m is None or m.role != "candidate":
        return not_found()
    try:
        body = ConsentBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return _bad(err)
    orgs.set_consent(m, body.share)
    return jsonify(consent=body.share)


# --- invites -----------------------------------------------------------------


@bp.get("/invites/<token>")
@org_route
def invite_preview(user: User, token: str):
    invite = orgs.valid_invite(token)
    if invite is None:
        return not_found()
    org = db.session.get(Organization, invite.org_id)
    m = orgs.member(org.id, user.id)
    return jsonify(org=orgs.org_dict(org), member=m is not None)


@bp.post("/invites/<token>/accept")
@org_route
def invite_accept(user: User, token: str):
    invite = orgs.valid_invite(token)
    if invite is None:
        return not_found()
    org = db.session.get(Organization, invite.org_id)
    # Real accounts never join the demo org; demo accounts join nothing.
    if org.is_demo or user.is_demo:
        return not_found()
    m = orgs.accept_invite(invite, user)
    return jsonify(
        org=orgs.org_dict(org), role=m.role, consent=m.consent_at is not None
    )


# --- org management ----------------------------------------------------------


@bp.post("")
@org_route
def create(user: User):
    if user.is_demo:
        return not_found()
    try:
        body = OrgBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return _bad(err)
    org = orgs.create_org(user, body.name)
    return jsonify(org={**orgs.org_dict(org), "role": "admin"}), 201


@bp.get("/<int:org_id>")
@org_route
def get_org(user: User, org_id: int):
    m = orgs.member(org_id, user.id)
    if m is None:
        return not_found()
    org = db.session.get(Organization, org_id)
    return jsonify(org={**orgs.org_dict(org), "role": m.role})


@bp.put("/<int:org_id>")
@org_route
def update_org(user: User, org_id: int):
    m = orgs.member(org_id, user.id)
    if m is None or m.role != "admin":
        return not_found()
    try:
        body = BrandingBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return _bad(err)
    org = db.session.get(Organization, org_id)
    if body.name is not None:
        org.name = body.name.strip() or org.name
    if body.color is not None:
        org.primary_color = body.color
    if body.logo is not None:
        org.logo_data = body.logo or None
    db.session.commit()
    return jsonify(org={**orgs.org_dict(org), "role": m.role})


@bp.get("/<int:org_id>/members")
@org_route
def members(user: User, org_id: int):
    if orgs.staff(org_id, user.id) is None:
        return not_found()
    rows = db.session.execute(
        db.select(OrgMember, User)
        .join(User, User.id == OrgMember.user_id)
        .where(OrgMember.org_id == org_id)
        .order_by(OrgMember.role, User.name)
    ).all()
    return jsonify(
        members=[
            {
                "id": u.id,
                "name": u.name,
                "role": m.role,
                "consent": m.consent_at is not None if m.role == "candidate" else None,
            }
            for m, u in rows
        ]
    )


@bp.post("/<int:org_id>/invites")
@org_route
def create_invite(user: User, org_id: int):
    if orgs.staff(org_id, user.id) is None:
        return not_found()
    invite = orgs.create_invite(org_id, user.id)
    return (
        jsonify(token=invite.token, expires_at=invite.expires_at.isoformat() + "Z"),
        201,
    )


# --- coach dashboard ---------------------------------------------------------


@bp.get("/<int:org_id>/candidates")
@org_route
def candidates(user: User, org_id: int):
    m = orgs.staff(org_id, user.id)
    if m is None:
        return not_found()
    org = db.session.get(Organization, org_id)
    return jsonify(
        org={**orgs.org_dict(org), "role": m.role},
        candidates=orgs.candidate_rows(org_id),
    )


def _coach_candidate(user: User, org_id: int, candidate_id: int) -> User | None:
    """The candidate, if the caller coaches in this org and they gave consent."""
    if orgs.staff(org_id, user.id) is None:
        return None
    if orgs.consenting_candidate(org_id, candidate_id) is None:
        return None
    return db.session.get(User, candidate_id)


@bp.get("/<int:org_id>/candidates/<int:candidate_id>")
@org_route
def candidate(user: User, org_id: int, candidate_id: int):
    c = _coach_candidate(user, org_id, candidate_id)
    if c is None:
        return not_found()
    return jsonify(candidate=orgs.candidate_detail(org_id, c))


def _coach_report_session(user: User, org_id: int, candidate_id: int, session_id: int):
    c = _coach_candidate(user, org_id, candidate_id)
    if c is None:
        return None
    return orgs.coach_session(c.id, session_id)


@bp.get("/<int:org_id>/candidates/<int:candidate_id>/sessions/<int:session_id>/report")
@org_route
def candidate_report(user: User, org_id: int, candidate_id: int, session_id: int):
    session = _coach_report_session(user, org_id, candidate_id, session_id)
    report = reports.get_report(session) if session else None
    if report is None or report.status != "ready":
        return not_found()
    data = reports.report_dict(session, report)
    # Read-only for coaches: never the candidate's share link.
    data.pop("share_token", None)
    return jsonify(report=data)


@bp.get(
    "/<int:org_id>/candidates/<int:candidate_id>/sessions/<int:session_id>/comments"
)
@org_route
def candidate_comments(user: User, org_id: int, candidate_id: int, session_id: int):
    if _coach_report_session(user, org_id, candidate_id, session_id) is None:
        return not_found()
    return jsonify(comments=orgs.comments(session_id, org_id))


@bp.post(
    "/<int:org_id>/candidates/<int:candidate_id>/sessions/<int:session_id>/comments"
)
@org_route
def add_comment(user: User, org_id: int, candidate_id: int, session_id: int):
    if _coach_report_session(user, org_id, candidate_id, session_id) is None:
        return not_found()
    try:
        body = CommentBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return _bad(err)
    return (
        jsonify(comment=orgs.add_comment(org_id, session_id, user.id, body.body)),
        201,
    )


@bp.post("/<int:org_id>/assignments")
@org_route
def assign(user: User, org_id: int):
    if orgs.staff(org_id, user.id) is None:
        return not_found()
    try:
        body = AssignmentBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return _bad(err)
    m = orgs.member(org_id, body.candidate_id)
    if m is None or m.role != "candidate":
        return not_found()
    a = orgs.create_assignment(
        org_id,
        user.id,
        body.candidate_id,
        body.role_title.strip(),
        body.jd_text.strip(),
        body.duration_min,
        body.due_date,
    )
    return jsonify(assignment=orgs.assignment_dict(a)), 201
