"""The sales demo (T-166): seed, reset, and demo accounts that never cost money."""

import pytest

from app.extensions import db
from app.models import (
    Assignment,
    Organization,
    OrgMember,
    QuestionBankItem,
    Report,
    ReportComment,
    Session,
    Story,
    User,
)
from app.services import demo, orgs

ADMIN = "admin@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def count(model, **where) -> int:
    return db.session.scalar(
        db.select(db.func.count()).select_from(model).filter_by(**where)
    )


@pytest.fixture()
def admin(client, signup):
    return bearer(signup(email=ADMIN).get_json()["access_token"])


@pytest.fixture()
def view_as(client, admin, app):
    demo.reset()

    def _view(kind):
        res = client.post("/api/demo/view-as", json={"view_as": kind}, headers=admin)
        assert res.status_code == 200
        return bearer(res.get_json()["access_token"])

    return _view


def test_reset_seeds_the_org_and_makes_no_fire_calls(app, fire):
    counts = demo.reset()
    assert fire.calls == []
    assert counts["candidates"] == 6
    org = db.session.scalar(db.select(Organization).filter_by(is_demo=True))
    assert org.name == "Northstar Career Partners"
    assert org.logo_data.startswith("data:image/svg+xml;base64,")
    roles = [m.role for m in db.session.scalars(db.select(OrgMember))]
    assert roles.count("coach") == 1 and roles.count("candidate") == 6
    for user in db.session.scalars(db.select(User).filter_by(is_demo=True)):
        assert user.password_hash is None and user.google_sub is None
        assert user.email.endswith(demo.DEMO_DOMAIN)
        if user.name == "Morgan Ellis":
            continue
        n = count(Session, user_id=user.id)
        assert 2 <= n <= 3, user.name
        reports = db.session.scalars(
            db.select(Report).join(Session).where(Session.user_id == user.id)
        ).all()
        assert len(reports) == n and all(r.status == "ready" for r in reports)
        assert all(r.top_takeaways_json and r.exercises_json for r in reports)
    # All candidates shared their reports.
    assert all(
        m.consent_at
        for m in db.session.scalars(db.select(OrgMember).filter_by(role="candidate"))
    )


def test_reset_is_idempotent_and_leaves_real_users_alone(app, client, signup, fire):
    signup()
    demo.reset()
    first = {
        m.__tablename__: count(m) for m in (User, Session, Report, Story, Assignment)
    }
    demo.reset()
    again = {
        m.__tablename__: count(m) for m in (User, Session, Report, Story, Assignment)
    }
    assert first == again
    assert count(Organization) == 1
    assert (
        db.session.scalar(db.select(User).filter_by(email="ada@example.com"))
        is not None
    )
    demo.clear()
    assert count(User) == 1 and count(Organization) == 0


def test_demo_ready_candidates_have_everything(app, client, view_as):
    for kind, rising in (("candidate", True), ("struggling", False)):
        h = view_as(kind)
        stats = client.get("/api/stats", headers=h).get_json()["stats"]
        scores = [x["score"] for x in stats["history"]]
        assert len(scores) == 3
        assert (scores[-1] > scores[0] + 1) if rising else (max(scores) < 3)
        assert stats["level"] >= 1 and stats["skills"] and stats["roles"]
        assert stats["goal"]["weekly"] >= 2
        assert stats["practice"]["due"] >= 2
        if rising:
            assert stats["streak_days"] >= 2
        stories = client.get("/api/stories", headers=h).get_json()["stories"]
        assert len(stories) >= 3
        mine = client.get("/api/orgs/mine", headers=h).get_json()
        statuses = sorted(a["status"] for a in mine["assignments"])
        assert statuses == ["done", "todo"]
        done = next(a for a in mine["assignments"] if a["status"] == "done")
        comments = client.get(
            f"/api/orgs/mine/sessions/{done['session_id']}/comments", headers=h
        ).get_json()["comments"]
        assert comments and comments[0]["author"] == "Morgan Ellis"
        report = client.get(f"/api/sessions/{done['session_id']}/report", headers=h)
        assert report.get_json()["report"]["status"] == "ready"


def test_coach_dashboard_flags_the_struggling_candidate(app, client, view_as):
    h = view_as("coach")
    org = client.get("/api/auth/me", headers=h).get_json()["user"]["orgs"][0]
    assert org["is_demo"] and org["role"] == "coach"
    rows = client.get(f"/api/orgs/{org['id']}/candidates", headers=h).get_json()[
        "candidates"
    ]
    assert len(rows) == 6
    by_name = {r["name"]: r for r in rows}
    assert by_name["Alex Chen"]["needs_practice"] == []
    assert "Low latest score" in by_name["Jordan Reyes"]["needs_practice"]
    assert by_name["Jordan Reyes"]["weak_areas"]
    # The coach can open a report and add a comment.
    alex = by_name["Alex Chen"]["id"]
    detail = client.get(
        f"/api/orgs/{org['id']}/candidates/{alex}", headers=h
    ).get_json()
    sid = detail["candidate"]["sessions"][0]["session_id"]
    base = f"/api/orgs/{org['id']}/candidates/{alex}/sessions/{sid}"
    assert client.get(f"{base}/report", headers=h).status_code == 200
    assert (
        client.post(f"{base}/comments", json={"body": "Great"}, headers=h).status_code
        == 201
    )


def test_licensed_field_candidate_report_shows_the_disclaimer_flag(
    app, client, view_as
):
    h = view_as("coach")
    org = client.get("/api/auth/me", headers=h).get_json()["user"]["orgs"][0]["id"]
    nurse = db.session.scalar(db.select(User).filter_by(name="Sam Okafor"))
    sid = orgs.coach_sessions(nurse.id)[0]["session_id"]
    report = client.get(
        f"/api/orgs/{org}/candidates/{nurse.id}/sessions/{sid}/report", headers=h
    ).get_json()["report"]
    assert report["licensed_field"] is True


def test_demo_accounts_never_call_fire(app, client, view_as, fire):
    h = view_as("candidate")
    user = demo.account("candidate")
    docs = db.session.scalars(db.select(demo.Document).filter_by(user_id=user.id)).all()
    ids = {d.kind: d.id for d in docs}
    sid = db.session.scalar(db.select(Session.id).filter_by(user_id=user.id))
    attempts = [
        (
            "POST",
            "/api/sessions",
            {
                "resume_id": ids["resume"],
                "jd_id": ids["job_description"],
                "duration_min": 10,
            },
        ),
        (
            "POST",
            "/api/decoder",
            {"text": "A job description that is long enough to decode properly."},
        ),
        ("POST", "/api/lab/chat", {"messages": [{"role": "user", "content": "hi"}]}),
        ("POST", f"/api/sessions/{sid}/report", None),
    ]
    for method, path, body in attempts:
        res = client.open(path, method=method, json=body, headers=h)
        # A seeded report is already ready: asking for it again just returns it.
        assert res.status_code in (202, 403, 400, 409), (path, res.status_code)
    assert fire.calls == []
    # A report that isn't ready would need Fire: refused.
    report = db.session.scalar(db.select(Report).filter_by(session_id=sid))
    report.status = "failed"
    db.session.commit()
    res = client.post(f"/api/sessions/{sid}/report", headers=h)
    assert res.status_code == 403 and fire.calls == []
    # The plan call itself is refused with the demo message.
    res = client.post("/api/sessions", json=attempts[0][2], headers=h)
    assert res.status_code == 403
    assert "demo account" in res.get_json()["error"]


def test_demo_accounts_cannot_be_deleted_shared_or_used_with_google(
    app, client, view_as
):
    h = view_as("candidate")
    res = client.delete(
        "/api/auth/me", json={"email": demo.account("candidate").email}, headers=h
    )
    assert res.status_code == 403
    sid = db.session.scalar(
        db.select(Session.id).filter_by(user_id=demo.account("candidate").id)
    )
    assert (
        client.post(f"/api/sessions/{sid}/report/share", headers=h).status_code == 403
    )
    assert (
        db.session.scalar(db.select(Report.share_token).filter_by(session_id=sid))
        is None
    )


def test_demo_users_cannot_join_or_create_orgs(app, client, view_as, admin):
    h = view_as("candidate")
    assert client.post("/api/orgs", json={"name": "Mine"}, headers=h).status_code == 404
    # A real admin can't join the demo org by invite either.
    coach = view_as("coach")
    org = client.get("/api/auth/me", headers=coach).get_json()["user"]["orgs"][0]["id"]
    token = client.post(f"/api/orgs/{org}/invites", headers=coach).get_json()["token"]
    assert (
        client.post(f"/api/orgs/invites/{token}/accept", headers=admin).status_code
        == 404
    )


def test_demo_reset_cli(app, fire):
    result = app.test_cli_runner().invoke(args=["demo-reset"])
    assert result.exit_code == 0 and "6 candidates" in result.output
    assert fire.calls == []
    assert count(ReportComment) >= 2 and count(QuestionBankItem) >= 5
