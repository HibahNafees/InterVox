"""Who may reach the organization feature and the sales demo (T-166).

ORG_FEATURE decides it:
  off         nobody
  admin_only  admins (ADMIN_EMAILS), and demo accounts opened by an admin
  on          every signed-in user (scoped by org membership)

The demo itself (View as demo coach/candidate) is admin-only in every mode.
A demo account has no password: its only way in is a short-lived token minted
from an admin session, carrying `viewer_admin` = that admin's id. A demo token
without it, or whose admin is no longer an admin, is refused everywhere.
"""

from functools import wraps

from flask import current_app, has_request_context, jsonify
from flask_jwt_extended import get_current_user, get_jwt, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt import PyJWTError

from ..extensions import db
from ..models import User
from . import admin

MODES = ("off", "admin_only", "on")
# Demo account emails: a reserved domain no one can own or sign in with.
DEMO_DOMAIN = "@demo.intervox.invalid"


def mode() -> str:
    m = current_app.config.get("ORG_FEATURE", "admin_only")
    # An unknown value fails closed.
    return m if m in MODES else "off"


def viewer_admin(claims: dict) -> User | None:
    """The admin who opened this demo token, if still an admin."""
    aid = claims.get("viewer_admin")
    if not isinstance(aid, int):
        return None
    user = db.session.get(User, aid)
    if user is None or user.is_demo or not admin.is_admin(user):
        return None
    return user


def demo_token_ok(user: User, claims: dict) -> bool:
    """A demo account's token is valid only if an admin opened it."""
    return not user.is_demo or viewer_admin(claims) is not None


def can_use_orgs(user: User | None, claims: dict) -> bool:
    m = mode()
    if user is None or m == "off":
        return False
    if user.is_demo:
        return viewer_admin(claims) is not None
    if m == "on":
        return True
    return admin.is_admin(user)


def can_use_demo(user: User | None) -> bool:
    """View-as buttons and the /demo page: admins only, unless the feature is off."""
    return (
        user is not None
        and not user.is_demo
        and mode() != "off"
        and admin.is_admin(user)
    )


def _caller() -> tuple[User | None, dict]:
    """The signed-in user and token claims, or (None, {}) for anyone else.

    A missing, expired, invalid or refused token all count as signed out.
    """
    try:
        verify_jwt_in_request(optional=True)
    except (JWTExtendedException, PyJWTError):
        return None, {}
    user = get_current_user()
    return (user, get_jwt()) if user is not None else (None, {})


def not_found():
    return jsonify(error="Not found"), 404


def org_route(fn):
    """Every org route: 404 unless the caller may use the feature."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, claims = _caller()
        if not can_use_orgs(user, claims):
            return not_found()
        return fn(user, *args, **kwargs)

    return wrapper


def demo_route(fn):
    """Demo routes (view-as, the /demo page): 404 unless an admin's own session."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, _claims = _caller()
        if not can_use_demo(user):
            return not_found()
        return fn(user, *args, **kwargs)

    return wrapper


def current_is_demo() -> bool:
    """True when the current request is made with a demo account's token."""
    if not has_request_context():
        return False
    try:
        verify_jwt_in_request(optional=True)
    except (JWTExtendedException, PyJWTError):
        return False
    user = get_current_user()
    return bool(user is not None and user.is_demo)
