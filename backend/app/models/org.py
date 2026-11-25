"""Organizations for career agencies (T-166): coaches, candidates, assignments.

Every table cascades from users and organizations, so "Delete my data" and the
demo reset remove everything in one step.
"""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .base import created_at_column, fk

ORG_ROLES = ("admin", "coach", "candidate")


class Organization(db.Model):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Small PNG/JPEG/SVG data URL, only ever shown through <img>.
    logo_data: Mapped[str | None] = mapped_column(Text)
    primary_color: Mapped[str | None] = mapped_column(String(7))
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = created_at_column()


class OrgMember(db.Model):
    __tablename__ = "org_members"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = fk("organizations.id")
    user_id: Mapped[int] = fk("users.id")
    role: Mapped[str] = mapped_column(Enum(*ORG_ROLES, name="org_role"), nullable=False)
    # When the candidate agreed to let the org's coaches see their reports.
    # Null = not shared (never given, or withdrawn).
    consent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = created_at_column()


class OrgInvite(db.Model):
    __tablename__ = "org_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = fk("organizations.id")
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_by: Mapped[int] = fk("users.id")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = created_at_column()


class Assignment(db.Model):
    """An interview a coach asks a candidate to do."""

    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = fk("organizations.id")
    candidate_id: Mapped[int] = fk("users.id")
    coach_id: Mapped[int] = fk("users.id")
    role_title: Mapped[str] = mapped_column(String(160), nullable=False)
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date_type | None] = mapped_column(Date)
    # The interview the candidate did for it (kept if the interview is deleted).
    session_id: Mapped[int | None] = fk(
        "sessions.id", nullable=True, ondelete="SET NULL"
    )
    created_at: Mapped[datetime] = created_at_column()


class ReportComment(db.Model):
    """A coach's comment on a candidate's report."""

    __tablename__ = "report_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = fk("sessions.id")
    org_id: Mapped[int] = fk("organizations.id")
    author_id: Mapped[int] = fk("users.id")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
