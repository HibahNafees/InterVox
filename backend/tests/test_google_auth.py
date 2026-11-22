"""Sign in with Google (T-156). Google's token check is mocked: no network."""

import pytest

from app.extensions import db
from app.models import User
from app.services import google_auth

WEB_ID = "web-123.apps.googleusercontent.com"
TOKEN = "header.payload.signature-from-google"


@pytest.fixture()
def google(app, monkeypatch):
    """Configure a client id and fake Google's verdict on each token."""
    app.config["GOOGLE_CLIENT_IDS"] = [WEB_ID]
    claims = {
        "sub": "g-1001",
        "email": "Grace@Example.com",
        "email_verified": True,
        "name": "Grace Hopper",
    }
    seen = []

    def verify(token, request, audience=None, clock_skew_in_seconds=0):
        seen.append(audience)
        if token != TOKEN:
            raise ValueError("Wrong signature")
        return dict(claims)

    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", verify)
    return claims, seen


def sign_in(client, credential=TOKEN):
    return client.post("/api/auth/google", json={"credential": credential})


def test_providers_hide_google_until_configured(app, client):
    assert client.get("/api/auth/providers").get_json() == {"google_client_id": None}
    assert sign_in(client).status_code == 404
    app.config["GOOGLE_CLIENT_IDS"] = [WEB_ID]
    assert client.get("/api/auth/providers").get_json() == {"google_client_id": WEB_ID}


def test_first_google_sign_in_creates_a_passwordless_account(client, google):
    _, seen = google
    res = sign_in(client)
    assert res.status_code == 201
    body = res.get_json()
    assert body["access_token"]
    assert body["user"]["email"] == "grace@example.com"
    assert body["user"]["name"] == "Grace Hopper"
    assert body["user"]["has_password"] is False and body["user"]["google"] is True
    assert seen == [[WEB_ID]]  # the token must be for our client id
    user = db.session.scalar(db.select(User))
    assert user.password_hash is None and user.google_sub == "g-1001"
    me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.get_json()["user"]["email"] == "grace@example.com"


def test_the_same_google_account_logs_back_in(client, google):
    first = sign_in(client).get_json()["user"]["id"]
    again = sign_in(client)
    assert again.status_code == 200
    assert again.get_json()["user"]["id"] == first
    assert db.session.query(User).count() == 1


def test_google_sign_in_links_an_existing_email_account(client, signup, google):
    claims, _ = google
    claims["email"] = "ada@example.com"
    made = signup().get_json()["user"]["id"]
    res = sign_in(client)
    assert res.status_code == 200
    assert res.get_json()["user"]["id"] == made
    user = db.session.get(User, made)
    assert user.google_sub == "g-1001"
    assert user.check_password("correct-horse")  # the password still works


def test_bad_or_unverified_tokens_are_refused(client, google):
    claims, _ = google
    assert sign_in(client, "x" * 30).status_code == 401
    assert sign_in(client, "short").status_code == 400
    claims["email_verified"] = False
    res = sign_in(client)
    assert res.status_code == 401
    assert "verified" in res.get_json()["error"]
    assert db.session.query(User).count() == 0


def test_password_login_on_a_google_account_points_to_google(client, google):
    sign_in(client)
    res = client.post(
        "/api/auth/login", json={"email": "grace@example.com", "password": "anything1"}
    )
    assert res.status_code == 401
    assert "Continue with Google" in res.get_json()["error"]


def test_google_only_account_deletes_by_typing_its_email(client, google):
    token = sign_in(client).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = client.delete(
        "/api/auth/me", json={"email": "other@example.com"}, headers=headers
    )
    assert r.status_code == 403
    r = client.delete("/api/auth/me", json={"password": "guess"}, headers=headers)
    assert r.status_code == 403
    r = client.delete(
        "/api/auth/me", json={"email": " Grace@Example.com "}, headers=headers
    )
    assert r.status_code == 200
    assert db.session.query(User).count() == 0
