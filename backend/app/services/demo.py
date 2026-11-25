"""The sales-demo org, "Northstar Career Partners" (T-166).

`reset()` deletes every demo account and demo org (everything cascades) and
seeds them again from app/demo_data.py. It makes no Fire calls: scores, rewrites
and reports are hand-written, and the weighted scores, verdicts and delivery
analytics come from the app's own code. Dates are relative to today, so streaks
and "needs practice" flags stay current when it runs every night.
"""

import base64
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from .. import demo_data as data
from ..extensions import db
from ..models import (
    Answer,
    Assignment,
    Document,
    Evaluation,
    Organization,
    OrgMember,
    Question,
    QuestionBankItem,
    Report,
    ReportComment,
    Session,
    Story,
    User,
)
from ..models.base import utcnow
from .access import DEMO_DOMAIN
from .analytics import Clip, delivery, session_summary, word_count
from .scoring import CriterionScore, verdict_for, weighted_score

# View-as targets: the coach, the strong candidate and the struggling one.
ACCOUNTS = {
    "coach": data.COACH["email"],
    "candidate": next(c["email"] for c in data.CANDIDATES if c["key"] == "candidate"),
    "struggling": next(c["email"] for c in data.CANDIDATES if c["key"] == "struggling"),
}
READY = ("candidate", "struggling")


def email(local: str) -> str:
    return local + DEMO_DOMAIN


def account(kind: str) -> User | None:
    local = ACCOUNTS.get(kind)
    if local is None:
        return None
    return db.session.scalar(select(User).filter_by(email=email(local), is_demo=True))


def summary() -> dict:
    org = db.session.scalar(select(Organization).filter_by(is_demo=True))
    return {
        "seeded": org is not None and account("coach") is not None,
        "org": data.ORG["name"],
        "color": data.ORG["color"],
        "logo": _logo(),
        "coach": data.COACH["name"],
        "candidates": [
            {"name": c["name"], "role": c["role"], "demo_ready": c["key"] in READY}
            for c in data.CANDIDATES
        ],
    }


def _logo() -> str:
    raw = base64.b64encode(data.ORG["logo_svg"].encode()).decode()
    return "data:image/svg+xml;base64," + raw


def clear() -> None:
    """Delete every demo org and demo account (and all their data, by cascade)."""
    db.session.execute(delete(Organization).where(Organization.is_demo.is_(True)))
    db.session.execute(delete(User).where(User.is_demo.is_(True)))
    db.session.commit()


def reset() -> dict:
    clear()
    now = utcnow()
    org = Organization(
        name=data.ORG["name"],
        primary_color=data.ORG["color"],
        logo_data=_logo(),
        is_demo=True,
        created_at=now - timedelta(days=30),
    )
    db.session.add(org)
    coach = _user(data.COACH["name"], data.COACH["email"], now)
    db.session.flush()
    db.session.add(OrgMember(org_id=org.id, user_id=coach.id, role="coach"))

    counts = {"candidates": 0, "reports": 0, "stories": 0, "assignments": 0}
    for c in data.CANDIDATES:
        user = _user(c["name"], c["email"], now, goal=c.get("goal", 3))
        db.session.flush()
        db.session.add(
            OrgMember(
                org_id=org.id,
                user_id=user.id,
                role="candidate",
                consent_at=now - timedelta(days=20),
            )
        )
        sessions = _seed_candidate(user, c, now)
        counts["candidates"] += 1
        counts["reports"] += len(sessions)
        counts["stories"] += _seed_stories(user, c, sessions, now)
        _seed_bank(user, c, sessions, now)
        counts["assignments"] += _seed_assignments(org, coach, user, c, sessions, now)
    db.session.commit()
    return counts


def _user(name: str, local: str, now: datetime, goal: int = 3) -> User:
    # No password and no Google id: a demo account can't sign in by itself.
    user = User(
        email=email(local),
        name=name,
        is_demo=True,
        weekly_goal=goal,
        created_at=now - timedelta(days=30),
    )
    db.session.add(user)
    return user


def _rubric(c: dict) -> dict:
    role = [
        {"name": n, "kind": k, "weight": w, "description": n} for n, k, w in c["rubric"]
    ]
    universal = [
        {"name": n, "kind": "universal", "weight": 0.1, "description": n}
        for n in data.UNIVERSAL
    ]
    return {"criteria": role + universal}


def _comment(name: str, score: int) -> str:
    return data.BAND_COMMENTS.get(name, data.ROLE_COMMENTS).get(
        score, data.ROLE_COMMENTS[score]
    )


def _seed_candidate(user: User, c: dict, now: datetime) -> list[Session]:
    resume = Document(
        user_id=user.id,
        kind="resume",
        title=f"Résumé: {c['name']}",
        raw_text=c["resume"],
        expires_at=None,  # saved: the purge never touches it
        created_at=now - timedelta(days=25),
    )
    jd = Document(
        user_id=user.id,
        kind="job_description",
        title=f"Job description: {c['role']}",
        raw_text=c["jd"],
        expires_at=None,
        created_at=now - timedelta(days=25),
    )
    db.session.add_all([resume, jd])
    db.session.flush()
    rubric = _rubric(c)
    out = []
    for spec in c["sessions"]:
        out.append(_seed_session(user, c, spec, rubric, resume, jd, now))
    return out


def _seed_session(user, c, spec, rubric, resume, jd, now) -> Session:
    start = (now - timedelta(days=spec["days_ago"])).replace(
        hour=min(now.hour, 10) if spec["days_ago"] == 0 else 10,
        minute=0,
        second=0,
        microsecond=0,
    )
    qs = spec["questions"]
    budget = spec["minutes"] * 60 // len(qs)
    sections: dict[str, dict] = {}
    for item in qs:
        sec = sections.setdefault(
            item["section"],
            {
                "name": item["section"],
                "module": item["module"],
                "minutes": 0,
                "questions": [],
            },
        )
        sec["questions"].append(item["text"])
    for sec in sections.values():
        sec["minutes"] = round(spec["minutes"] * len(sec["questions"]) / len(qs))
    session = Session(
        user_id=user.id,
        resume_id=resume.id,
        jd_id=jd.id,
        mode="standard",
        duration_min=spec["minutes"],
        difficulty=c["seniority"],
        persona=spec["persona"],
        plan_json={
            "role_title": c["role"],
            "sections": list(sections.values()),
            "reserve": [],
            "analysis": {
                "role_title": c["role"],
                "field": c["role"],
                "seniority": c["seniority"],
                "licensed_field": c["licensed"],
                "competencies": [
                    {"name": n, "description": n} for n, _k, _w in c["rubric"]
                ],
            },
        },
        rubric_json=rubric,
        status="completed",
        started_at=start,
        ended_at=start + timedelta(minutes=spec["minutes"]),
        created_at=start - timedelta(minutes=5),
    )
    db.session.add(session)
    db.session.flush()

    per_question, scores = [], []
    at = start
    for n, item in enumerate(qs):
        at += timedelta(seconds=30)
        question = Question(
            session_id=session.id,
            section=item["section"],
            order_no=n + 1,
            text=item["text"],
            budget_sec=budget,
            asked_at=at,
            asked_text=item["text"],
            asked_segments=[{"who": "interviewer", "text": item["text"]}],
        )
        db.session.add(question)
        db.session.flush()
        # Speaking time from the word count at this candidate's pace.
        ms = round(word_count(item["answer"]) * 60_000 / c.get("wpm", 145))
        answer = Answer(
            question_id=question.id,
            transcript=item["answer"],
            started_ms=0,
            ended_ms=ms,
            duration_ms=ms,
            attempt_no=1,
            input_mode="voice",
            created_at=at + timedelta(milliseconds=ms),
        )
        db.session.add(answer)
        db.session.flush()
        at += timedelta(milliseconds=ms)

        crit = [
            CriterionScore(name=name, score=s, comment=_comment(name, s))
            for name, s in item["scores"].items()
            if s is not None
        ]
        score, rows = weighted_score(crit, rubric)
        d = delivery([Clip(item["answer"], ms, "voice", False)], budget)
        per_question.append(d)
        scores.append(score)
        db.session.add(
            Evaluation(
                answer_id=answer.id,
                score=score,
                rubric_scores_json={"criteria": rows},
                missing_points_json=item["missing"],
                stronger_version=item["stronger"],
                changes_json=[],
                delivery_json=d,
                feedback_json={
                    "summary": item["summary"],
                    "weak_moments": item["weak"],
                    "star": item["star"],
                    "tips": item["tips"],
                    "strengths": item["strengths"],
                    "confidence": "high",
                    "confidence_note": "",
                },
                created_at=session.ended_at,
            )
        )
    overall = round(sum(scores) / len(scores), 2)
    db.session.add(
        Report(
            session_id=session.id,
            overall_score=overall,
            verdict=verdict_for(overall),
            verdict_reason=spec["reason"],
            status="ready",
            started_at=session.ended_at,
            top_takeaways_json=spec["takeaways"],
            exercises_json=[],
            analytics_json=session_summary(per_question),
            stories_at=session.ended_at,  # never re-run the story-bank update
            created_at=session.ended_at,
        )
    )
    db.session.flush()
    return session


def _answer_id(session: Session, index: int) -> int | None:
    q = db.session.scalar(
        select(Question).filter_by(session_id=session.id, order_no=index + 1)
    )
    if q is None:
        return None
    return db.session.scalar(select(Answer.id).filter_by(question_id=q.id))


def _seed_stories(user, c, sessions, now) -> int:
    for s in c.get("stories", []):
        session = sessions[s["session"]]
        db.session.add(
            Story(
                user_id=user.id,
                title=s["title"],
                star_json=s["star"],
                competencies_json=s["competencies"],
                source_answer_ids_json=[_answer_id(session, s["question"])],
                strength=s["strength"],
                created_at=session.ended_at,
            )
        )
    return len(c.get("stories", []))


def _seed_bank(user, c, sessions, now) -> None:
    for s_idx, q_idx, text, competency, due_days in c.get("bank", []):
        session = sessions[s_idx]
        q = db.session.scalar(
            select(Question).filter_by(session_id=session.id, order_no=q_idx + 1)
        )
        e = db.session.scalar(
            select(Evaluation)
            .join(Answer, Answer.id == Evaluation.answer_id)
            .where(Answer.question_id == q.id)
        )
        db.session.add(
            QuestionBankItem(
                user_id=user.id,
                question_text=text,
                competency=competency,
                last_score=e.score if e else None,
                next_review_at=now + timedelta(days=due_days),
                source_session_id=session.id,
                section=q.section,
                module=_module(c, s_idx, q_idx),
                interval_days=1,
                created_at=session.ended_at,
            )
        )


def _module(c: dict, s_idx: int, q_idx: int) -> str:
    return c["sessions"][s_idx]["questions"][q_idx]["module"]


def _seed_assignments(org, coach, user, c, sessions, now) -> int:
    n = 0
    done = [
        s
        for s, spec in zip(sessions, c["sessions"])
        if spec.get("assignment") == "done"
    ]
    for s in done:
        db.session.add(
            Assignment(
                org_id=org.id,
                candidate_id=user.id,
                coach_id=coach.id,
                role_title=c["role"],
                jd_text=c["jd"],
                duration_min=s.duration_min,
                due_date=(s.started_at + timedelta(days=2)).date(),
                session_id=s.id,
                created_at=s.started_at - timedelta(days=3),
            )
        )
        n += 1
        if c.get("comment"):
            db.session.add(
                ReportComment(
                    session_id=s.id,
                    org_id=org.id,
                    author_id=coach.id,
                    body=c["comment"],
                    created_at=s.ended_at + timedelta(hours=3),
                )
            )
    for a in c.get("assignments", []):
        db.session.add(
            Assignment(
                org_id=org.id,
                candidate_id=user.id,
                coach_id=coach.id,
                role_title=a["role"],
                jd_text=a["jd"],
                duration_min=a["minutes"],
                due_date=(now + timedelta(days=a["due_in_days"])).date(),
                created_at=now - timedelta(days=1),
            )
        )
        n += 1
    return n
