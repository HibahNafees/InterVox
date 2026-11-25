"""Org and demo routes are admin-only by default (T-166): 404 for everyone else.

The route table below must list every /api/orgs and /api/demo route; a test
fails if a new one is added without being covered here.
"""

import re

import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models import Assignment, Organization, OrgInvite, ReportComment, User
from app.services import demo

ADMIN = "admin@example.com"


@pytest.fixture()
def seeded(app):
    demo.reset()
    org = db.session.scalar(db.select(Organization).filter_by(is_demo=True))
    alex = demo.account("candidate")
    a = db.session.scalar(db.select(Assignment).filter_by(candidate_id=alex.id))
    c = db.session.scalar(db.select(ReportComment))
    invite = OrgInvite(
        org_id=org.id,
        token="t" * 32,
        created_by=demo.account("coach").id,
        expires_at=a.created_at.replace(year=2100),
    )
    db.session.add(invite)
    db.session.commit()
    return {
        "org": org.id,
        "uid": alex.id,
        "aid": a.id,
        "sid": c.session_id,
        "token": invite.token,
    }


def routes(ids: dict) -> list[tuple[str, str, dict | None]]:
    o, u, a, s, t = ids["org"], ids["uid"], ids["aid"], ids["sid"], ids["token"]
    report = f"/api/orgs/{o}/candidates/{u}/sessions/{s}"
    return [
        ("GET", "/api/orgs/mine", None),
        ("GET", f"/api/orgs/mine/assignments/{a}", None),
        ("POST", f"/api/orgs/mine/assignments/{a}/link", {"session_id": s}),
        ("GET", f"/api/orgs/mine/sessions/{s}/comments", None),
        ("PUT", f"/api/orgs/{o}/consent", {"share": False}),
        ("GET", f"/api/orgs/invites/{t}", None),
        ("POST", f"/api/orgs/invites/{t}/accept", None),
        ("POST", "/api/orgs", {"name": "Acme Careers"}),
        ("GET", f"/api/orgs/{o}", None),
        ("PUT", f"/api/orgs/{o}", {"color": "#000000"}),
        ("GET", f"/api/orgs/{o}/members", None),
        ("POST", f"/api/orgs/{o}/invites", None),
        ("GET", f"/api/orgs/{o}/candidates", None),
        ("GET", f"/api/orgs/{o}/candidates/{u}", None),
        ("GET", f"{report}/report", None),
        ("GET", f"{report}/comments", None),
        ("POST", f"{report}/comments", {"body": "Nice work"}),
        (
            "POST",
            f"/api/orgs/{o}/assignments",
            {
                "candidate_id": u,
                "role_title": "Engineer",
                "jd_text": "A job description long enough to pass.",
                "duration_min": 10,
            },
        ),
        ("GET", "/api/demo", None),
        ("POST", "/api/demo/view-as", {"view_as": "coach"}),
    ]


def call(client, method, path, body, headers=None):
    return client.open(path, method=method, json=body, headers=headers or {})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_route_table_covers_every_org_and_demo_route(app):
    star = {"org": "*", "uid": "*", "aid": "*", "sid": "*", "token": "*"}
    listed = {(m, p) for m, p, _ in routes(star)}
    registered = {
        (m, re.sub(r"<[^>]+>", "*", r.rule))
        for r in app.url_map.iter_rules()
        if r.rule.startswith(("/api/orgs", "/api/demo"))
        for m in r.methods - {"HEAD", "OPTIONS"}
    }
    assert registered == listed


def test_signed_out_visitor_gets_404_everywhere(client, seeded):
    for method, path, body in routes(seeded):
        res = call(client, method, path, body)
        assert res.status_code == 404, (method, path, res.status_code)
        assert res.get_json() == {"error": "Not found"}


def test_bad_or_expired_token_counts_as_signed_out(client, seeded):
    for method, path, body in routes(seeded):
        res = call(client, method, path, body, bearer("not-a-token"))
        assert res.status_code == 404, (method, path)


def test_regular_user_gets_404_everywhere(client, auth, seeded):
    for method, path, body in routes(seeded):
        res = call(client, method, path, body, auth)
        assert res.status_code == 404, (method, path, res.status_code)


def test_regular_user_who_is_a_member_still_gets_404_when_admin_only(
    app, client, auth, seeded
):
    # Even a real membership doesn't open the feature while it's admin-only.
    from app.models import OrgMember

    user = db.session.scalar(db.select(User).filter_by(email="ada@example.com"))
    db.session.add(OrgMember(org_id=seeded["org"], user_id=user.id, role="coach"))
    db.session.commit()
    res = client.get(f"/api/orgs/{seeded['org']}/candidates", headers=auth)
    assert res.status_code == 404


def test_feature_off_hides_everything_even_from_admins(app, client, signup, seeded):
    admin = bearer(signup(email=ADMIN).get_json()["access_token"])
    app.config["ORG_FEATURE"] = "off"
    for method, path, body in routes(seeded):
        assert call(client, method, path, body, admin).status_code == 404, path


def test_unknown_feature_value_fails_closed(app, client, signup, seeded):
    admin = bearer(signup(email=ADMIN).get_json()["access_token"])
    app.config["ORG_FEATURE"] = "yes please"
    assert client.get("/api/demo", headers=admin).status_code == 404


def test_admin_can_open_the_demo(client, signup, seeded):
    admin = bearer(signup(email=ADMIN).get_json()["access_token"])
    assert client.get("/api/demo", headers=admin).get_json()["demo"]["seeded"]
    for kind in ("coach", "candidate", "struggling"):
        res = client.post("/api/demo/view-as", json={"view_as": kind}, headers=admin)
        assert res.status_code == 200
        assert res.get_json()["user"]["email"].endswith(demo.DEMO_DOMAIN)
    res = client.post("/api/demo/view-as", json={"view_as": "nobody"}, headers=admin)
    assert res.status_code == 400


def test_feature_on_opens_orgs_but_not_the_demo(app, client, auth, seeded):
    app.config["ORG_FEATURE"] = "on"
    assert client.get("/api/orgs/mine", headers=auth).status_code == 200
    # Another org's data still 404s.
    res = client.get(f"/api/orgs/{seeded['org']}/candidates", headers=auth)
    assert res.status_code == 404
    assert client.get("/api/demo", headers=auth).status_code == 404
    res = client.post("/api/demo/view-as", json={"view_as": "coach"}, headers=auth)
    assert res.status_code == 404


def _demo_token(client, signup, kind="coach"):
    admin = bearer(signup(email=ADMIN).get_json()["access_token"])
    res = client.post("/api/demo/view-as", json={"view_as": kind}, headers=admin)
    return bearer(res.get_json()["access_token"])


def test_demo_token_works_while_its_admin_is_an_admin(app, client, signup, seeded):
    coach = _demo_token(client, signup)
    res = client.get(f"/api/orgs/{seeded['org']}/candidates", headers=coach)
    assert res.status_code == 200
    me = client.get("/api/auth/me", headers=coach).get_json()["user"]
    assert me["is_demo"] and me["demo_role"] == "coach"

    app.config["ADMIN_EMAILS"] = set()
    res = client.get(f"/api/orgs/{seeded['org']}/candidates", headers=coach)
    assert res.status_code == 404
    assert client.get("/api/auth/me", headers=coach).status_code == 401


def test_demo_account_token_without_an_admin_is_refused(app, client, seeded):
    coach = demo.account("coach")
    forged = bearer(create_access_token(identity=str(coach.id)))
    assert client.get("/api/auth/me", headers=forged).status_code == 401
    assert client.get("/api/stats", headers=forged).status_code == 401
    res = client.get(f"/api/orgs/{seeded['org']}/candidates", headers=forged)
    assert res.status_code == 404
    # Naming a regular user as the "admin" doesn't help either.
    user = User(email="eve@example.com", name="Eve")
    db.session.add(user)
    db.session.commit()
    forged = bearer(
        create_access_token(
            identity=str(coach.id), additional_claims={"viewer_admin": user.id}
        )
    )
    assert client.get("/api/auth/me", headers=forged).status_code == 401


def test_demo_accounts_cannot_sign_in_from_the_login_page(client, seeded):
    for kind in ("coach", "candidate"):
        res = client.post(
            "/api/auth/login",
            json={"email": demo.account(kind).email, "password": "anything-at-all"},
        )
        assert res.status_code == 401
        assert res.get_json()["error"] == "Incorrect email or password"


def test_demo_session_cannot_open_the_demo_itself(client, signup, seeded):
    coach = _demo_token(client, signup)
    assert client.get("/api/demo", headers=coach).status_code == 404
    res = client.post("/api/demo/view-as", json={"view_as": "coach"}, headers=coach)
    assert res.status_code == 404


def test_regular_user_me_is_unchanged(client, auth):
    me = client.get("/api/auth/me", headers=auth).get_json()["user"]
    assert set(me) == {
        "id",
        "email",
        "name",
        "has_password",
        "google",
        "created_at",
        "is_admin",
    }


def test_admin_me_lists_orgs_and_demo(client, signup, seeded):
    admin = bearer(signup(email=ADMIN).get_json()["access_token"])
    me = client.get("/api/auth/me", headers=admin).get_json()["user"]
    assert me["is_admin"] and me["can_use_demo"] and me["orgs"] == []
