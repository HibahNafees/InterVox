"""Usage caps and Fire spend tracking (usage_limits)."""

from datetime import date, datetime, timezone

from flask import current_app
from sqlalchemy import case, func

from ..extensions import db
from ..models import AnonSpend, Answer, JdDecode, Question, Session, UsageLimit

LONG_SESSION_MIN = 60


class LimitReached(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def today() -> date:
    return datetime.now(timezone.utc).date()


def _row(user_id: int) -> UsageLimit:
    row = db.session.get(UsageLimit, (user_id, today()))
    if row is None:
        row = UsageLimit(
            user_id=user_id,
            date=today(),
            minutes_used=0,
            llm_calls=0,
            sessions_count=0,
            decoder_runs=0,
            lab_calls=0,
            fire_spend_usd=0,
        )
        db.session.add(row)
    return row


def record_fire_call(user_id: int | None, price_usd: float) -> None:
    """Add one Fire call's charged price to today's row for this user (or to the
    signed-out tally, which counts toward the same monthly budget)."""
    if user_id is None:
        row = db.session.get(AnonSpend, today())
        if row is None:
            row = AnonSpend(date=today(), llm_calls=0, fire_spend_usd=0)
            db.session.add(row)
    else:
        row = _row(user_id)
    row.llm_calls += 1
    row.fire_spend_usd = float(row.fire_spend_usd or 0) + price_usd
    db.session.commit()


def month_spend_usd() -> float:
    """Total Fire spend across all users this calendar month."""
    start = today().replace(day=1)
    total = db.session.scalar(
        db.select(func.coalesce(func.sum(UsageLimit.fire_spend_usd), 0)).where(
            UsageLimit.date >= start
        )
    )
    anon = db.session.scalar(
        db.select(func.coalesce(func.sum(AnonSpend.fire_spend_usd), 0)).where(
            AnonSpend.date >= start
        )
    )
    return float(total or 0) + float(anon or 0)


def check_budget() -> None:
    """New Fire work pauses once the monthly budget is used up."""
    if month_spend_usd() >= current_app.config["FIRE_MONTHLY_BUDGET_USD"]:
        raise LimitReached(
            "This month's AI budget is used up, so new interviews are paused "
            "until next month."
        )


def check_can_start(user_id: int, duration_min: int) -> None:
    """Daily caps for a new session (checked before it starts)."""
    check_budget()
    cfg = current_app.config
    row = db.session.get(UsageLimit, (user_id, today()))
    used = row.minutes_used if row else 0
    if used + duration_min > cfg["DAILY_INTERVIEW_MINUTES"]:
        left = max(0, cfg["DAILY_INTERVIEW_MINUTES"] - int(used))
        raise LimitReached(
            f"That would go over today's {cfg['DAILY_INTERVIEW_MINUTES']} interview "
            f"minutes ({left} left). Try a shorter interview or come back tomorrow."
        )
    if duration_min >= LONG_SESSION_MIN:
        start = datetime.combine(today(), datetime.min.time())
        long_today = db.session.scalar(
            db.select(func.count(Session.id)).where(
                Session.user_id == user_id,
                Session.duration_min >= LONG_SESSION_MIN,
                Session.started_at >= start,
            )
        )
        if long_today >= cfg["DAILY_LONG_SESSIONS"]:
            raise LimitReached(
                "You've already done a 60-minute interview today; try a shorter one."
            )


def check_can_plan(user_id: int) -> None:
    """Each plan costs Fire calls, so cap how many a user can generate per day."""
    start = datetime.combine(today(), datetime.min.time())
    made = db.session.scalar(
        db.select(func.count(Session.id)).where(
            Session.user_id == user_id, Session.created_at >= start
        )
    )
    cap = current_app.config["DAILY_PLANS"]
    if made >= cap:
        raise LimitReached(
            f"You've generated {cap} interview plans today; try again tomorrow."
        )


def record_session_start(user_id: int, duration_min: int) -> None:
    row = _row(user_id)
    row.sessions_count += 1
    row.minutes_used += duration_min
    db.session.commit()


def check_can_retry(user_id: int) -> None:
    """Each "Try again" costs a scoring call (and a transcription if spoken)."""
    check_budget()
    start = datetime.combine(today(), datetime.min.time())
    made = db.session.scalar(
        db.select(func.count(Answer.id))
        .join(Question, Question.id == Answer.question_id)
        .join(Session, Session.id == Question.session_id)
        .where(
            Session.user_id == user_id,
            Answer.attempt_no > 1,
            Answer.created_at >= start,
        )
    )
    cap = current_app.config["DAILY_RETRIES"]
    if made >= cap:
        raise LimitReached(f"You've used today's {cap} retries; try again tomorrow.")


def check_can_decode(user_id: int | None, ip_hash: str | None) -> None:
    """Decoder caps: per user per day, or per visitor and overall when signed out."""
    check_budget()
    cfg = current_app.config
    if user_id is not None:
        if _row(user_id).decoder_runs >= cfg["DAILY_DECODER_RUNS"]:
            raise LimitReached(
                f"You've used today's {cfg['DAILY_DECODER_RUNS']} decoder runs. "
                "Come back tomorrow."
            )
        return
    start = datetime.combine(today(), datetime.min.time())
    runs = (
        db.select(func.count())
        .select_from(JdDecode)
        .where(JdDecode.user_id.is_(None), JdDecode.created_at >= start)
    )
    if (
        db.session.scalar(runs.where(JdDecode.ip_hash == ip_hash))
        >= cfg["ANON_DECODER_RUNS"]
    ):
        raise LimitReached(
            "That's today's free decodes. Sign up (free) to decode more job descriptions."
        )
    if db.session.scalar(runs) >= cfg["ANON_DECODER_DAILY"]:
        raise LimitReached(
            "The free decoder is busy today. Sign up (free) or try again tomorrow."
        )


def record_decode(user_id: int | None) -> None:
    if user_id is not None:
        _row(user_id).decoder_runs += 1
        db.session.commit()


def lab_calls_used(user_id: int) -> int:
    row = db.session.get(UsageLimit, (user_id, today()))
    return row.lab_calls if row else 0


def reserve_lab_calls(user_id: int, calls: int) -> None:
    """Take `calls` of today's Chat Lab calls before any Fire call is made.

    One conditional UPDATE, so two tabs can't both squeeze past the cap; a request
    that would go over is refused whole, never half-answered."""
    check_budget()
    cap = current_app.config["LAB_DAILY_CALLS"]
    _row(user_id)
    db.session.commit()
    taken = db.session.execute(
        db.update(UsageLimit)
        .where(
            UsageLimit.user_id == user_id,
            UsageLimit.date == today(),
            UsageLimit.lab_calls + calls <= cap,
        )
        .values(lab_calls=UsageLimit.lab_calls + calls)
        .execution_options(synchronize_session=False)
    ).rowcount
    db.session.commit()
    if not taken:
        left = max(0, cap - lab_calls_used(user_id))
        raise LimitReached(
            f"That needs {calls} Chat Lab call{'s' if calls != 1 else ''} and you have "
            f"{left} of today's {cap} left. Come back tomorrow."
        )


def release_lab_calls(user_id: int, calls: int) -> None:
    """Give back reserved calls that were never made (a Fire call failed first)."""
    if calls <= 0:
        return
    db.session.execute(
        db.update(UsageLimit)
        .where(UsageLimit.user_id == user_id, UsageLimit.date == today())
        .values(
            lab_calls=case(
                (UsageLimit.lab_calls > calls, UsageLimit.lab_calls - calls), else_=0
            )
        )
        .execution_options(synchronize_session=False)
    )
    db.session.commit()
