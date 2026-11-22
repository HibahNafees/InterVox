import re

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..extensions import db
from ..models import User
from ..services import admin, google_auth, privacy, ratelimit
from .common import first_error

bp = Blueprint("auth", __name__)

TOO_MANY = "Too many attempts. Please wait a few minutes and try again."

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SignupBody(BaseModel):
    email: str
    password: str
    name: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v) or len(v) > 255:
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def strong_enough(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        return v

    @field_validator("name")
    @classmethod
    def non_empty_name(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("Name must be 1-120 characters")
        return v


class LoginBody(BaseModel):
    email: str
    password: str


def _token_response(user: User, status: int = 200):
    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token, user=user.to_dict()), status


@bp.post("/signup")
def signup():
    if not ratelimit.allow("signup", 5, 3600):
        return jsonify(error=TOO_MANY), 429
    try:
        body = SignupBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    if db.session.scalar(db.select(User).filter_by(email=body.email)):
        return jsonify(error="An account with this email already exists"), 409

    user = User(email=body.email, name=body.name)
    user.set_password(body.password)
    db.session.add(user)
    db.session.commit()
    return _token_response(user, 201)


@bp.post("/login")
def login():
    if not ratelimit.allow("login", 10, 300):
        return jsonify(error=TOO_MANY), 429
    try:
        body = LoginBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify(error=first_error(err)), 400

    user = db.session.scalar(
        db.select(User).filter_by(email=body.email.strip().lower())
    )
    if user is not None and not user.password_hash:
        return (
            jsonify(
                error="This account signs in with Google: use Continue with Google."
            ),
            401,
        )
    if user is None or not user.check_password(body.password):
        return jsonify(error="Incorrect email or password"), 401
    return _token_response(user)


@bp.get("/providers")
def providers():
    """Which sign-in options the login page can offer."""
    return jsonify(google_client_id=google_auth.web_client_id())


class GoogleBody(BaseModel):
    credential: str = Field(min_length=20, max_length=8192)


@bp.post("/google")
def google():
    """Sign up or log in with a Google ID token (T-156)."""
    if not google_auth.client_ids():
        return jsonify(error="Google sign-in isn't available"), 404
    if not ratelimit.allow("google", 20, 300):
        return jsonify(error=TOO_MANY), 429
    try:
        body = GoogleBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError:
        return jsonify(error="Google sign-in didn't work. Please try again."), 400
    try:
        claims = google_auth.verify(body.credential)
    except google_auth.GoogleAuthError as err:
        return jsonify(error=err.message), 401
    user, created = google_auth.find_or_create(claims)
    return _token_response(user, 201 if created else 200)


class DeleteBody(BaseModel):
    # A password account confirms with its password; a Google-only account
    # (no password, T-156) types its email instead.
    password: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=255)


@bp.delete("/me")
@jwt_required()
def delete_me():
    """ "Delete my data": the account and everything saved for it, in one step."""
    try:
        body = DeleteBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError:
        return jsonify(error="Enter your password to confirm"), 400
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return jsonify(error="Account not found"), 404
    if not ratelimit.allow("delete", 5, 900, key=str(user.id)):
        return jsonify(error=TOO_MANY), 429
    if user.password_hash:
        if not body.password:
            return jsonify(error="Enter your password to confirm"), 400
        if not user.check_password(body.password):
            return jsonify(error="Incorrect password"), 403
    elif body.email.strip().lower() != user.email:
        return jsonify(error="Type your account's email to confirm"), 403
    privacy.delete_user(user.id)
    return jsonify(ok=True)


@bp.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return jsonify(error="Account not found"), 404
    return jsonify(user={**user.to_dict(), "is_admin": admin.is_admin(user)})
