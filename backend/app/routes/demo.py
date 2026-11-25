"""The sales demo (T-166): admin-only, 404 for everyone else.

A demo account can't log in. An admin opens it here and gets a short-lived
token that names the admin (viewer_admin); every request made with it is
checked against ADMIN_EMAILS again (services/access.py).
"""

from datetime import timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from pydantic import BaseModel, ValidationError

from ..models import User
from ..services import demo
from ..services.access import demo_route

bp = Blueprint("demo", __name__)

DEMO_TOKEN_HOURS = 2


class ViewAsBody(BaseModel):
    # "coach", "candidate" (the strong one) or "struggling".
    view_as: str


@bp.get("")
@demo_route
def info(user: User):
    return jsonify(demo=demo.summary())


@bp.post("/view-as")
@demo_route
def view_as(user: User):
    try:
        body = ViewAsBody.model_validate(request.get_json(silent=True) or {})
    except ValidationError:
        return jsonify(error="Choose coach or candidate"), 400
    if body.view_as not in demo.ACCOUNTS:
        return jsonify(error="Choose coach or candidate"), 400
    target = demo.account(body.view_as)
    if target is None:
        return jsonify(error="The demo isn't set up yet: run flask demo-reset"), 409
    token = create_access_token(
        identity=str(target.id),
        additional_claims={"viewer_admin": user.id},
        expires_delta=timedelta(hours=DEMO_TOKEN_HOURS),
    )
    return jsonify(access_token=token, user=target.to_dict())
