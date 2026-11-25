from app.extensions import db

EXPECTED_TABLES = {
    "saved_decodes",
    "users",
    "documents",
    "jd_analyses",
    "sessions",
    "questions",
    "answers",
    "evaluations",
    "reports",
    "stories",
    "debriefs",
    "peer_rooms",
    "question_bank",
    "usage_limits",
    # Phase 8: decoded job descriptions (hash + interpretation, no JD text) and
    # signed-out Fire spend.
    "jd_decodes",
    "anon_spend",
    # Phase 9: résumé gap analysis (cached per résumé + job pair).
    "gap_analyses",
    "company_research",
    # Organizations for career agencies (T-166).
    "organizations",
    "org_members",
    "org_invites",
    "assignments",
    "report_comments",
}


def test_all_tables_exist(app):
    assert set(db.metadata.tables) == EXPECTED_TABLES


def test_no_audio_or_video_columns(app):
    banned = ("audio", "video", "recording", "blob")
    for table in db.metadata.tables.values():
        for col in table.columns:
            assert not any(b in col.name for b in banned), f"{table.name}.{col.name}"
            assert col.type.__class__.__name__ not in ("LargeBinary", "BLOB")


def test_deleting_user_cascades(app, signup):
    from app.models import Document, User

    signup()
    user = User.query.one()
    db.session.add(Document(user_id=user.id, kind="resume", raw_text="hi"))
    db.session.commit()
    with db.engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.exec_driver_sql("DELETE FROM users WHERE id = ?", (user.id,))
        count = conn.exec_driver_sql("SELECT COUNT(*) FROM documents").scalar()
    assert count == 0
