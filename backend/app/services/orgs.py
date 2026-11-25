"""Organizations for career agencies (T-166).

Data is separated per org: every lookup here is scoped by an org id the caller
is a member of. A coach sees a candidate's mock-interview reports only while
that candidate has given consent (org_members.consent_at); withdrawing it hides
them again at once.
"""

import secrets
from datetime import date, timedelta

from sqlalchemy import select

from ..extensions import db
from ..models import (
    Assignment,
    Organization,
    OrgInvite,
    OrgMember,
    Report,
    ReportComment,
    Session,
    User,
)
from ..models.base import utcnow
from . import stats

INVITE_DAYS = 14
STAFF = ("admin", "coach")
# Interviews a coach can see: mock interviews, like the progress dashboard.
COACH_MODES = ("standard", "pressure", "panel")
# "Needs practice": a low latest score, or nothing for a week.
LOW_SCORE = 3.0
IDLE_DAYS = 7


def org_dict(org: Organization) -> dict:
    return {
        "id": org.id,
        "name": org.name,
        "logo": org.logo_data,
        "color": org.primary_color,
        "is_demo": org.is_demo,
    }


def memberships(user_id: int) -> list[dict]:
    rows = db.session.execute(
        select(OrgMember, Organization)
        .join(Organization, Organization.id == OrgMember.org_id)
        .where(OrgMember.user_id == user_id)
        .order_by(OrgMember.id)
    ).all()
    return [
        {
            **org_dict(o),
            "role": m.role,
            "consent": m.consent_at is not None if m.role == "candidate" else None,
        }
        for m, o in rows
    ]


def member(org_id: int, user_id: int) -> OrgMember | None:
    return db.session.scalar(
        select(OrgMember).filter_by(org_id=org_id, user_id=user_id)
    )


def staff(org_id: int, user_id: int) -> OrgMember | None:
    m = member(org_id, user_id)
    return m if m is not None and m.role in STAFF else None


def create_org(user: User, name: str) -> Organization:
    org = Organization(name=name)
    db.session.add(org)
    db.session.flush()
    db.session.add(OrgMember(org_id=org.id, user_id=user.id, role="admin"))
    db.session.commit()
    return org


# --- invites and consent ---------------------------------------------------


def create_invite(org_id: int, user_id: int) -> OrgInvite:
    invite = OrgInvite(
        org_id=org_id,
        token=secrets.token_urlsafe(24),
        created_by=user_id,
        expires_at=utcnow() + timedelta(days=INVITE_DAYS),
    )
    db.session.add(invite)
    db.session.commit()
    return invite


def valid_invite(token: str) -> OrgInvite | None:
    invite = db.session.scalar(select(OrgInvite).filter_by(token=token))
    if invite is None or invite.expires_at <= utcnow():
        return None
    return invite


def accept_invite(invite: OrgInvite, user: User) -> OrgMember:
    """Join as a candidate. Reports stay private until consent is given."""
    existing = member(invite.org_id, user.id)
    if existing is not None:
        return existing
    m = OrgMember(org_id=invite.org_id, user_id=user.id, role="candidate")
    db.session.add(m)
    invite.used_count += 1
    db.session.commit()
    return m


def set_consent(m: OrgMember, share: bool) -> None:
    m.consent_at = utcnow() if share else None
    db.session.commit()


def consenting_candidate(org_id: int, user_id: int) -> OrgMember | None:
    m = member(org_id, user_id)
    if m is None or m.role != "candidate" or m.consent_at is None:
        return None
    return m


# --- assignments -------------------------------------------------------------


def assignment_status(a: Assignment, today: date | None = None) -> str:
    today = today or utcnow().date()
    session = db.session.get(Session, a.session_id) if a.session_id else None
    if session is not None and session.status == "completed":
        return "done"
    if session is not None and session.status in ("planned", "active"):
        return "in_progress"
    if a.due_date is not None and a.due_date < today:
        return "overdue"
    return "todo"


def assignment_dict(a: Assignment, with_jd: bool = False) -> dict:
    coach = db.session.get(User, a.coach_id)
    out = {
        "id": a.id,
        "org_id": a.org_id,
        "candidate_id": a.candidate_id,
        "role_title": a.role_title,
        "duration_min": a.duration_min,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "status": assignment_status(a),
        "session_id": a.session_id,
        "coach_name": coach.name if coach else None,
        "created_at": a.created_at.isoformat() + "Z",
    }
    if with_jd:
        out["jd_text"] = a.jd_text
    return out


def assignments_for(org_id: int, candidate_id: int) -> list[Assignment]:
    return list(
        db.session.scalars(
            select(Assignment)
            .filter_by(org_id=org_id, candidate_id=candidate_id)
            .order_by(Assignment.due_date.is_(None), Assignment.due_date, Assignment.id)
        )
    )


def my_assignments(user_id: int) -> list[Assignment]:
    return list(
        db.session.scalars(
            select(Assignment)
            .filter_by(candidate_id=user_id)
            .order_by(Assignment.due_date.is_(None), Assignment.due_date, Assignment.id)
        )
    )


def create_assignment(
    org_id: int,
    coach_id: int,
    candidate_id: int,
    role_title: str,
    jd_text: str,
    duration_min: int,
    due_date: date | None,
) -> Assignment:
    a = Assignment(
        org_id=org_id,
        coach_id=coach_id,
        candidate_id=candidate_id,
        role_title=role_title,
        jd_text=jd_text,
        duration_min=duration_min,
        due_date=due_date,
    )
    db.session.add(a)
    db.session.commit()
    return a


# --- coach views -------------------------------------------------------------


WEAK_BELOW = 3.5


def _weak_areas(s: dict) -> list[str]:
    """Up to three lowest skills, only those below 3.5."""
    skills = [
        k for k in s["skills"] if k["score"] is not None and k["score"] < WEAK_BELOW
    ]
    return [k["name"] for k in sorted(skills, key=lambda k: k["score"])[:3]]


def _last_practice(s: dict) -> date | None:
    return date.fromisoformat(s["history"][-1]["date"]) if s["history"] else None


def needs_practice(
    s: dict, statuses: list[str], today: date | None = None
) -> list[str]:
    """Why a coach should nudge this candidate (empty = on track)."""
    today = today or utcnow().date()
    reasons = []
    if s["latest_score"] is not None and s["latest_score"] < LOW_SCORE:
        reasons.append("Low latest score")
    last = _last_practice(s)
    if last is None or (today - last).days >= IDLE_DAYS:
        reasons.append(f"No interview in {IDLE_DAYS}+ days")
    if "overdue" in statuses:
        reasons.append("Overdue assignment")
    return reasons


def candidate_rows(org_id: int) -> list[dict]:
    rows = db.session.execute(
        select(OrgMember, User)
        .join(User, User.id == OrgMember.user_id)
        .where(OrgMember.org_id == org_id, OrgMember.role == "candidate")
        .order_by(User.name)
    ).all()
    out = []
    for m, u in rows:
        base = {"id": u.id, "name": u.name, "consent": m.consent_at is not None}
        if m.consent_at is None:
            # Without consent the coach sees only that they joined.
            out.append(base)
            continue
        s = stats.user_stats(u.id)
        statuses = [assignment_status(a) for a in assignments_for(org_id, u.id)]
        last = _last_practice(s)
        out.append(
            {
                **base,
                "role": (s["roles"][0]["role"] if s["roles"] else None),
                "interviews": s["interviews"],
                "latest_score": s["latest_score"],
                "improvement": s["improvement"],
                "trend": [h["score"] for h in s["history"]],
                "weak_areas": _weak_areas(s),
                "last_interview": last.isoformat() if last else None,
                "assignments_open": sum(1 for st in statuses if st != "done"),
                "needs_practice": needs_practice(s, statuses),
            }
        )
    return out


def coach_sessions(user_id: int) -> list[dict]:
    rows = db.session.execute(
        select(Session, Report)
        .join(Report, Report.session_id == Session.id)
        .where(
            Session.user_id == user_id,
            Session.mode.in_(COACH_MODES),
            Report.status == "ready",
        )
        .order_by(Session.created_at.desc())
    ).all()
    return [
        {
            "session_id": s.id,
            "role_title": (s.plan_json or {}).get("role_title") or "Interview",
            "date": (s.started_at or s.created_at).date().isoformat(),
            "duration_min": s.duration_min,
            "overall_score": r.overall_score,
            "verdict": r.verdict,
            "comments": db.session.scalar(
                select(db.func.count(ReportComment.id)).filter_by(session_id=s.id)
            ),
        }
        for s, r in rows
    ]


def candidate_detail(org_id: int, user: User) -> dict:
    s = stats.user_stats(user.id)
    return {
        "id": user.id,
        "name": user.name,
        "is_demo": user.is_demo,
        "stats": {
            k: s[k]
            for k in (
                "interviews",
                "average_score",
                "best_score",
                "latest_score",
                "improvement",
                "history",
                "roles",
                "skills",
                "streak_days",
                "level",
                "goal",
                "practice",
            )
            if k in s
        },
        "weak_areas": _weak_areas(s),
        "sessions": coach_sessions(user.id),
        "assignments": [assignment_dict(a) for a in assignments_for(org_id, user.id)],
    }


def coach_session(user_id: int, session_id: int) -> Session | None:
    """A candidate's interview a coach may open (mock interview with a ready report)."""
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != user_id or s.mode not in COACH_MODES:
        return None
    return s


# --- comments ----------------------------------------------------------------


def comment_dict(c: ReportComment) -> dict:
    author = db.session.get(User, c.author_id)
    return {
        "id": c.id,
        "body": c.body,
        "author": author.name if author else "Coach",
        "created_at": c.created_at.isoformat() + "Z",
    }


def comments(session_id: int, org_id: int | None = None) -> list[dict]:
    q = select(ReportComment).filter_by(session_id=session_id)
    if org_id is not None:
        q = q.filter_by(org_id=org_id)
    return [comment_dict(c) for c in db.session.scalars(q.order_by(ReportComment.id))]


def add_comment(org_id: int, session_id: int, author_id: int, body: str) -> dict:
    c = ReportComment(
        org_id=org_id, session_id=session_id, author_id=author_id, body=body
    )
    db.session.add(c)
    db.session.commit()
    return comment_dict(c)
