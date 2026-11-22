from datetime import date as date_type
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .base import created_at_column, fk


class Story(db.Model):
    """Story bank entry (STAR) extracted from the user's answers."""

    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = fk("users.id")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    star_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    competencies_json: Mapped[list[Any] | None] = mapped_column(JSON)
    source_answer_ids_json: Mapped[list[int] | None] = mapped_column(JSON)
    strength: Mapped[float | None] = mapped_column(Float)
    # Set once the user edits it: later merges never overwrite their wording.
    user_edited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class Debrief(db.Model):
    """Recall-only debrief of a real interview. Text only, never recordings."""

    __tablename__ = "debriefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = fk("users.id")
    company: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(255))
    round: Mapped[str | None] = mapped_column(String(120))
    recalled_qa_json: Mapped[list[Any] | None] = mapped_column(JSON)
    analysis_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # The completed "debrief" session that scores the recalled answers.
    session_id: Mapped[int | None] = fk("sessions.id", nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class QuestionBankItem(db.Model):
    """Spaced-repetition queue of questions to practice again."""

    __tablename__ = "question_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = fk("users.id")
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    competency: Mapped[str | None] = mapped_column(String(120))
    last_score: Mapped[float | None] = mapped_column(Float)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    # Where it came from (to reuse that job's résumé, JD and rubric).
    source_session_id: Mapped[int | None] = fk(
        "sessions.id", nullable=True, ondelete="SET NULL"
    )
    section: Mapped[str | None] = mapped_column(String(120))
    module: Mapped[str | None] = mapped_column(String(40))
    interval_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    reviews: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    mastered_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = created_at_column()


class UsageLimit(db.Model):
    """Per-user daily usage and estimated Fire spend (cost guard)."""

    __tablename__ = "usage_limits"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    date: Mapped[date_type] = mapped_column(Date, primary_key=True)
    minutes_used: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sessions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decoder_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lab_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Interviewer replies spoken with Fire audio today (DAILY_VOICE_REPLIES, T-154).
    voice_replies: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    fire_spend_usd: Mapped[float] = mapped_column(
        Numeric(10, 6, asdecimal=False), nullable=False, default=0
    )
