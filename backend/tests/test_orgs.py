"""Organization features (T-166): orgs, invites, consent, coach views,
assignments and comments. Most tests switch ORG_FEATURE to "on" so ordinary
test users can play each role; access rules are in test_orgs_access.py."""

from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Assignment, OrgInvite, OrgMember, ReportComment, User
from app.models.base import utcnow
from app.services import orgs
from tests.conftest import JD, RESUME

JD_TEXT = "Backend engineer: design APIs, tune MySQL and join the on-call rota."


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def on(app):
    app.config["ORG_FEATURE"] = "on"


@pytest.fixture()
def people(client, signup, on):
    """An org with a coach (its admin), a candidate, and an outsider."""
    coach = bearer(
        signup(email="coach@example.com", name="Morgan").get_json()["access_token"]
    )
    cand = bearer(
        signup(email="cand@example.com", name="Casey").get_json()["access_token"]
    )
    other = bearer(
        signup(email="other@example.com", name="Olive").get_json()["access_token"]
    )
    org = client.post("/api/orgs", json={"name": "Acme Careers"}, headers=coach)
    assert org.status_code == 201
    org_id = org.get_json()["org"]["id"]
    token = client.post(f"/api/orgs/{org_id}/invites", headers=coach).get_json()[
        "token"
    ]
    res = client.post(f"/api/orgs/invites/{token}/accept", headers=cand)
    assert res.status_code == 200 and res.get_json()["consent"] is False
    cand_id = client.get("/api/auth/me", headers=cand).get_json()["user"]["id"]
    return {"coach": coach, "cand": cand, "other": other, "org": org_id, "cid": cand_id}


def interview(client, headers, fire):
    """A finished interview with a ready report for this user."""
    docs = {}
    for kind, text in (("resume", RESUME), ("job_description", JD)):
        res = client.post(
            "/api/documents", json={"kind": kind, "text": text}, headers=headers
        )
        docs["resume_id" if kind == "resume" else "jd_id"] = res.get_json()["document"][
            "id"
        ]
    s = client.post(
        "/api/sessions",
        json={**docs, "duration_min": 10, "persona": "friendly"},
        headers=headers,
    ).get_json()["session"]
    client.post(f"/api/sessions/{s['id']}/start", headers=headers)
    client.post(
        f"/api/sessions/{s['id']}/turns",
        json={
            "text": "I built the Acme billing API and cut errors by half.",
            "duration_ms": 30000,
        },
        headers=headers,
    )
    client.post(f"/api/sessions/{s['id']}/end", headers=headers)
    res = client.post(f"/api/sessions/{s['id']}/report", headers=headers)
    assert res.status_code == 202, res.get_json()
    return s["id"]


def test_create_org_makes_the_creator_its_admin(client, people):
    res = client.get(f"/api/orgs/{people['org']}", headers=people["coach"])
    assert res.get_json()["org"]["role"] == "admin"
    me = client.get("/api/auth/me", headers=people["coach"]).get_json()["user"]
    assert me["orgs"][0]["name"] == "Acme Careers"


def test_branding_is_validated_and_admin_only(client, people):
    org = people["org"]
    res = client.put(f"/api/orgs/{org}", json={"color": "red"}, headers=people["coach"])
    assert res.status_code == 400
    res = client.put(
        f"/api/orgs/{org}",
        json={"logo": "data:text/html;base64,PGI+"},
        headers=people["coach"],
    )
    assert res.status_code == 400
    res = client.put(
        f"/api/orgs/{org}",
        json={"logo": "data:image/png;base64," + "A" * 200_000},
        headers=people["coach"],
    )
    assert res.status_code == 400
    logo = "data:image/png;base64,iVBORw0KGgo="
    res = client.put(
        f"/api/orgs/{org}",
        json={"color": "#1F6F8B", "logo": logo, "name": "Acme"},
        headers=people["coach"],
    )
    assert res.get_json()["org"] | {"role": "admin"} == {
        "id": org,
        "name": "Acme",
        "logo": logo,
        "color": "#1f6f8b",
        "is_demo": False,
        "role": "admin",
    }
    # Candidates can't change branding.
    res = client.put(
        f"/api/orgs/{org}", json={"color": "#000000"}, headers=people["cand"]
    )
    assert res.status_code == 404


def test_invites_expire_and_joining_twice_is_harmless(app, client, people):
    token = client.post(
        f"/api/orgs/{people['org']}/invites", headers=people["coach"]
    ).get_json()["token"]
    preview = client.get(
        f"/api/orgs/invites/{token}", headers=people["other"]
    ).get_json()
    assert preview["org"]["name"] == "Acme Careers" and preview["member"] is False
    for _ in range(2):
        assert (
            client.post(
                f"/api/orgs/invites/{token}/accept", headers=people["other"]
            ).status_code
            == 200
        )
    assert db.session.scalar(db.select(db.func.count(OrgMember.id))) == 3
    invite = db.session.scalar(db.select(OrgInvite).filter_by(token=token))
    invite.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert (
        client.get(f"/api/orgs/invites/{token}", headers=people["other"]).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/orgs/invites/{token}/accept", headers=people["other"]
        ).status_code
        == 404
    )


def test_candidates_cannot_invite_or_see_the_coach_dashboard(client, people):
    org = people["org"]
    assert (
        client.post(f"/api/orgs/{org}/invites", headers=people["cand"]).status_code
        == 404
    )
    assert (
        client.get(f"/api/orgs/{org}/candidates", headers=people["cand"]).status_code
        == 404
    )
    assert (
        client.get(f"/api/orgs/{org}/members", headers=people["cand"]).status_code
        == 404
    )


def test_coach_sees_nothing_until_the_candidate_consents(client, people, fire):
    org, cid = people["org"], people["cid"]
    sid = interview(client, people["cand"], fire)
    rows = client.get(
        f"/api/orgs/{org}/candidates", headers=people["coach"]
    ).get_json()["candidates"]
    assert rows == [{"id": cid, "name": "Casey", "consent": False}]
    for path in (
        f"/api/orgs/{org}/candidates/{cid}",
        f"/api/orgs/{org}/candidates/{cid}/sessions/{sid}/report",
        f"/api/orgs/{org}/candidates/{cid}/sessions/{sid}/comments",
    ):
        assert client.get(path, headers=people["coach"]).status_code == 404

    res = client.put(
        f"/api/orgs/{org}/consent", json={"share": True}, headers=people["cand"]
    )
    assert res.get_json() == {"consent": True}
    row = client.get(f"/api/orgs/{org}/candidates", headers=people["coach"]).get_json()[
        "candidates"
    ][0]
    assert row["consent"] and row["interviews"] == 1 and row["latest_score"] is not None
    assert row["trend"] == [row["latest_score"]]
    detail = client.get(
        f"/api/orgs/{org}/candidates/{cid}", headers=people["coach"]
    ).get_json()
    assert [s["session_id"] for s in detail["candidate"]["sessions"]] == [sid]
    report = client.get(
        f"/api/orgs/{org}/candidates/{cid}/sessions/{sid}/report",
        headers=people["coach"],
    ).get_json()["report"]
    assert report["status"] == "ready" and "share_token" not in report

    # Withdrawing consent hides it again at once.
    client.put(
        f"/api/orgs/{org}/consent", json={"share": False}, headers=people["cand"]
    )
    assert (
        client.get(
            f"/api/orgs/{org}/candidates/{cid}", headers=people["coach"]
        ).status_code
        == 404
    )


def test_coach_of_another_org_sees_nothing(client, signup, people, fire):
    org, cid = people["org"], people["cid"]
    sid = interview(client, people["cand"], fire)
    client.put(f"/api/orgs/{org}/consent", json={"share": True}, headers=people["cand"])
    other_org = client.post(
        "/api/orgs", json={"name": "Other"}, headers=people["other"]
    ).get_json()["org"]["id"]
    for path in (
        f"/api/orgs/{org}/candidates",
        f"/api/orgs/{org}/candidates/{cid}",
        f"/api/orgs/{org}/candidates/{cid}/sessions/{sid}/report",
        f"/api/orgs/{other_org}/candidates/{cid}",
        f"/api/orgs/{other_org}/candidates/{cid}/sessions/{sid}/report",
        f"/api/orgs/{org}",
    ):
        assert client.get(path, headers=people["other"]).status_code == 404, path


def test_needs_practice_rules():
    s = {"latest_score": 4.2, "history": [{"date": date.today().isoformat()}]}
    today = date.today()
    assert orgs.needs_practice(s, ["todo"], today) == []
    assert orgs.needs_practice({**s, "latest_score": 2.9}, [], today) == [
        "Low latest score"
    ]
    old = {
        "latest_score": 4.0,
        "history": [{"date": (today - timedelta(days=7)).isoformat()}],
    }
    assert orgs.needs_practice(old, [], today) == ["No interview in 7+ days"]
    assert orgs.needs_practice(s, ["overdue"], today) == ["Overdue assignment"]
    assert orgs.needs_practice({"latest_score": None, "history": []}, [], today) == [
        "No interview in 7+ days"
    ]


def test_assignment_lifecycle(client, people, fire):
    org, cid = people["org"], people["cid"]
    body = {
        "candidate_id": cid,
        "role_title": "Backend Engineer",
        "jd_text": JD_TEXT,
        "duration_min": 10,
        "due_date": (date.today() + timedelta(days=3)).isoformat(),
    }
    for bad in (
        {**body, "duration_min": 4},
        {**body, "duration_min": 61},
        {**body, "jd_text": "short"},
    ):
        assert (
            client.post(
                f"/api/orgs/{org}/assignments", json=bad, headers=people["coach"]
            ).status_code
            == 400
        )
    # Only members of this org can be assigned.
    other_id = client.get("/api/auth/me", headers=people["other"]).get_json()["user"][
        "id"
    ]
    res = client.post(
        f"/api/orgs/{org}/assignments",
        json={**body, "candidate_id": other_id},
        headers=people["coach"],
    )
    assert res.status_code == 404
    res = client.post(
        f"/api/orgs/{org}/assignments", json=body, headers=people["coach"]
    )
    assert res.status_code == 201
    aid = res.get_json()["assignment"]["id"]

    mine = client.get("/api/orgs/mine", headers=people["cand"]).get_json()
    assert [a["status"] for a in mine["assignments"]] == ["todo"]
    assert "jd_text" not in mine["assignments"][0]
    detail = client.get(
        f"/api/orgs/mine/assignments/{aid}", headers=people["cand"]
    ).get_json()
    assert detail["assignment"]["jd_text"] == JD_TEXT
    assert (
        client.get(
            f"/api/orgs/mine/assignments/{aid}", headers=people["other"]
        ).status_code
        == 404
    )

    sid = interview(client, people["cand"], fire)
    # Someone else can't link their interview, nor link it to someone else's assignment.
    res = client.post(
        f"/api/orgs/mine/assignments/{aid}/link",
        json={"session_id": sid},
        headers=people["other"],
    )
    assert res.status_code == 404
    res = client.post(
        f"/api/orgs/mine/assignments/{aid}/link",
        json={"session_id": sid},
        headers=people["cand"],
    )
    assert res.get_json()["assignment"]["status"] == "done"

    a = db.session.get(Assignment, aid)
    a.session_id, a.due_date = None, date.today() - timedelta(days=1)
    db.session.commit()
    assert orgs.assignment_status(a) == "overdue"


def test_comments_coach_writes_candidate_reads(client, people, fire):
    org, cid = people["org"], people["cid"]
    sid = interview(client, people["cand"], fire)
    client.put(f"/api/orgs/{org}/consent", json={"share": True}, headers=people["cand"])
    path = f"/api/orgs/{org}/candidates/{cid}/sessions/{sid}/comments"
    assert (
        client.post(path, json={"body": "   "}, headers=people["coach"]).status_code
        == 400
    )
    assert (
        client.post(
            path, json={"body": "x" * 2001}, headers=people["coach"]
        ).status_code
        == 400
    )
    res = client.post(
        path, json={"body": "Open with the billing story."}, headers=people["coach"]
    )
    assert res.status_code == 201
    assert res.get_json()["comment"]["author"] == "Morgan"
    # Candidates can't comment through the coach route.
    assert (
        client.post(path, json={"body": "hi"}, headers=people["cand"]).status_code
        == 404
    )

    mine = client.get(
        f"/api/orgs/mine/sessions/{sid}/comments", headers=people["cand"]
    ).get_json()
    assert [c["body"] for c in mine["comments"]] == ["Open with the billing story."]
    assert (
        client.get(
            f"/api/orgs/mine/sessions/{sid}/comments", headers=people["other"]
        ).status_code
        == 404
    )


def test_deleting_the_candidate_removes_their_org_data(client, people, fire):
    org, cid = people["org"], people["cid"]
    sid = interview(client, people["cand"], fire)
    client.put(f"/api/orgs/{org}/consent", json={"share": True}, headers=people["cand"])
    client.post(
        f"/api/orgs/{org}/candidates/{cid}/sessions/{sid}/comments",
        json={"body": "Good"},
        headers=people["coach"],
    )
    client.post(
        f"/api/orgs/{org}/assignments",
        json={
            "candidate_id": cid,
            "role_title": "X",
            "jd_text": JD_TEXT,
            "duration_min": 10,
        },
        headers=people["coach"],
    )
    res = client.delete(
        "/api/auth/me", json={"password": "correct-horse"}, headers=people["cand"]
    )
    assert res.status_code == 200
    assert (
        db.session.scalar(db.select(db.func.count(OrgMember.id)).filter_by(user_id=cid))
        == 0
    )
    assert db.session.scalar(db.select(db.func.count(Assignment.id))) == 0
    assert db.session.scalar(db.select(db.func.count(ReportComment.id))) == 0
    assert db.session.get(User, cid) is None


def test_admin_only_mode_admin_can_run_an_org(app, client, signup):
    """With the default ORG_FEATURE=admin_only, an admin uses the feature normally."""
    admin = bearer(signup(email="admin@example.com").get_json()["access_token"])
    res = client.post("/api/orgs", json={"name": "Pilot Agency"}, headers=admin)
    assert res.status_code == 201
