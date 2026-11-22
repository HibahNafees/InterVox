"""Sign in with Google (T-156).

The browser (Google Identity Services) or the Android app (Credential Manager via
@capgo/capacitor-social-login) gets a Google ID token; Flask checks its signature,
audience and issuer against Google's public keys, then finds or creates the user.
No Google secret is involved: the client id is public.
"""

from flask import current_app
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import User

_transport = google_requests.Request()


class GoogleAuthError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def client_ids() -> list[str]:
    return list(current_app.config.get("GOOGLE_CLIENT_IDS") or [])


def web_client_id() -> str | None:
    """The id the browser and the app sign in with (the first one listed)."""
    ids = client_ids()
    return ids[0] if ids else None


def verify(credential: str) -> dict:
    """The token's claims, or GoogleAuthError if it isn't a valid Google sign-in."""
    try:
        claims = id_token.verify_oauth2_token(
            credential, _transport, audience=client_ids(), clock_skew_in_seconds=10
        )
    except ValueError as err:
        current_app.logger.info("Google ID token rejected: %s", err)
        raise GoogleAuthError("Google sign-in didn't work. Please try again.")
    if not claims.get("sub") or not claims.get("email"):
        raise GoogleAuthError("Google didn't share an email address.")
    if claims.get("email_verified") is not True:
        raise GoogleAuthError("That Google account's email isn't verified yet.")
    return claims


def find_or_create(claims: dict) -> tuple[User, bool]:
    """(user, created). The same Google account always maps to the same user; an
    existing account with the same verified email is linked to it."""
    sub = str(claims["sub"])
    email = str(claims["email"]).strip().lower()
    user = db.session.scalar(db.select(User).filter_by(google_sub=sub))
    if user:
        return user, False
    user = db.session.scalar(db.select(User).filter_by(email=email))
    if user:
        user.google_sub = sub
        db.session.commit()
        return user, False
    name = (str(claims.get("name") or "").strip() or email.split("@")[0])[:120]
    user = User(email=email, name=name, google_sub=sub)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Two sign-ins at once: the other request made the account first.
        db.session.rollback()
        user = db.session.scalar(db.select(User).filter_by(google_sub=sub))
        if user is None:
            raise
        return user, False
    return user, True
