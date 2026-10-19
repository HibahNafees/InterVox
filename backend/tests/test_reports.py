import io

import pytest

from app.extensions import db
from app.models import Answer, Evaluation, Report, UsageLimit
from app.services.analytics import Clip, delivery, filler_counts, session_summary
from app.services.fire import FireError
from app.services.limits import today
from app.services.scoring import (
    FALLBACK_REWRITE,
    CriterionScore,
    _detach,
    _keep,
    fill_result,
    Sentence,
    grounding_problems,
    resume_fallback,
    split_sentences,
    verdict_for,
    weighted_score,
)

from tests.conftest import RESUME
from tests.fakes import SCORE, SUMMARY
from tests.test_transcription import CLIP
from tests.test_sessions import answer, started


def finished(client, auth, fire, session_id):
    """Run a short interview: main question + follow-up, then a second question."""
    started(client, auth, session_id)
    fire.turns = [
        {"action": "follow_up", "message": "What was your specific part?"},
        {"action": "next_question", "message": "How would you design a rate limiter?"},
    ]
    answer(client, auth, session_id, "Um, I built the billing API at Acme.", 60_000)
    answer(client, auth, session_id, "I owned the schema.", 20_000)
    answer(
        client,
        auth,
        session_id,
        "My answer about token buckets in Redis with a Lua script.",
        90_000,
    )
    res = client.post(f"/api/sessions/{session_id}/end", headers=auth)
    assert res.get_json()["session"]["status"] == "completed"


def build(client, auth, session_id):
    return client.post(f"/api/sessions/{session_id}/report", headers=auth)


# ---- analytics (no Fire) ---------------------------------------------------


def test_filler_counts():
    text = "Um, so uh, I think, umm, you know, we shipped. You know what I mean?"
    assert filler_counts(text) == {"um": 2, "uh": 1, "you know": 1}


def test_delivery_pace_fillers_and_tips():
    words = " ".join(["word"] * 200) + " um uh um um um um um um"
    d = delivery([Clip(words, 60_000, "voice")], budget_sec=30)
    assert d["wpm"] == 208 and d["filler_total"] == 8
    assert d["fillers_per_min"] == 8.0
    joined = " ".join(d["tips"])
    assert "slow down" in joined and "filler" in joined
    # Budgets under a minute don't trigger the "too long" tip.
    assert "budget" not in joined


def test_typed_answers_have_no_pace_or_fillers():
    d = delivery([Clip("Um, I typed this.", 60_000, "text")], budget_sec=240)
    assert d["wpm"] is None and d["fillers"] == {} and not d["spoken"]
    assert any("short" in t for t in d["tips"])  # 60 s of a 4-minute budget


def test_no_short_tip_under_a_time_limit():
    # Pressure mode's 30 s limit or a cut-off answer: the budget can't be used (T-116).
    d = delivery([Clip("I profiled the ledger queries and", 30_000, "text", True)], 300)
    assert not any("short" in t for t in d["tips"])


def test_long_answer_tip_and_summary():
    long = delivery([Clip("x " * 300, 400_000, "voice")], budget_sec=180)
    assert any("against a 3.0 min budget" in t for t in long["tips"])
    s = session_summary([long, delivery([Clip("y", 5_000, "voice")], 120)])
    assert s["over_budget"] == 1 and s["questions"] == 2 and s["avg_wpm"] == 45


def test_weighted_score_uses_rubric_weights():
    rubric = {
        "criteria": [
            {"name": "API design", "weight": 0.6},
            {"name": "Clarity", "weight": 0.4},
        ]
    }
    scores = [
        CriterionScore(name="api design", score=5),
        CriterionScore(name="Clarity", score=2),
        CriterionScore(name="Made up", score=1),
    ]
    score, rows = weighted_score(scores, rubric)
    assert score == pytest.approx(3.8)
    assert [r["name"] for r in rows] == ["API design", "Clarity"]
    # Every name changed: fall back to a plain average.
    assert weighted_score([CriterionScore(name="X", score=4)], rubric)[0] == 4


def test_untested_criteria_are_left_out_of_the_score():
    rubric = {
        "criteria": [
            {"name": "SQL", "weight": 0.5},
            {"name": "Mentoring", "weight": 0.3},
            {"name": "Clarity", "weight": 0.2},
        ]
    }
    scores = [
        CriterionScore(name="SQL", score=None),
        CriterionScore(name="Mentoring", score=4),
        CriterionScore(name="Clarity", score=2),
    ]
    score, rows = weighted_score(scores, rubric)
    assert score == pytest.approx(3.2)  # (4×0.3 + 2×0.2) / 0.5, SQL ignored
    assert [r["name"] for r in rows] == ["Mentoring", "Clarity"]


LIVE_RESUME = (
    "Acme Payments: Built the refunds API in Python/Flask serving 2M requests/day; "
    "moved reporting queries from MySQL replicas to a nightly ETL, cutting p95 "
    "latency from 1.8s to 300ms; mentored two junior engineers."
)


def test_hedges_are_cut_from_the_stronger_version():
    # Live (T-24): "I'm not sure about that one; I'd look at…" was copied verbatim.
    out = split_sentences(
        [
            Sentence(
                text="I'm not sure about that one; I'd check the pool size first."
            ),
            Sentence(text="I don't know."),
            Sentence(text="I made sure the pool was sized right."),
        ]
    )
    assert [s.text for s in out] == [
        "I'd check the pool size first.",
        "I made sure the pool was sized right.",
    ]


def test_hypothetical_answers_are_not_turned_into_experience():
    answer = "I'd use a token bucket per API key in Redis, with a Lua script."
    claimed = Sentence(text="At Acme I built a token bucket per API key in Redis.")
    kept_hypothetical = Sentence(text="I'd use a token bucket per API key in Redis.")
    assert grounding_problems([claimed, kept_hypothetical], [LIVE_RESUME, answer]) == [
        "it presents what the candidate said they would do as something they did",
        "",
    ]


@pytest.mark.parametrize(
    "text,source,problem",
    [
        # Grounded rewording of the résumé.
        (
            "At Acme Payments I built the refunds API in Python and Flask.",
            "Built the refunds API in Python/Flask",
            "",
        ),
        ("That cut latency by [add the % improvement].", None, ""),
        # Invented in the live check (T-15).
        (
            "I also collaborated closely with product teams to gather requirements.",
            None,
            "it adds details the candidate never gave",
        ),
        # Faithful sentences pass without a cited source (the model often omits it).
        ("I set up the alerts and mentored two junior engineers.", None, ""),
        (
            "I designed the endpoints to be stateless, allowing easy horizontal scaling.",
            "Built the refunds API",
            "it adds details the candidate never gave",
        ),
        (
            "I organized regular one-on-one sessions with [names] every week.",
            None,
            "it adds details the candidate never gave",
        ),
        # Unit conversions and framing aren't new facts.
        (
            "To address this, we moved reporting queries to a nightly ETL, which cut "
            "p95 latency from 1.8 seconds to 300 milliseconds.",
            "moved reporting queries from MySQL replicas to a nightly ETL",
            "",
        ),
        # A grounded start can't carry an invented clause.
        (
            "I built the refunds API in Python and Flask, ensuring it was optimized "
            "for performance.",
            "Built the refunds API in Python/Flask",
            "it adds details the candidate never gave",
        ),
        (
            "It served 5 million requests a day.",
            "serving 2M requests/day",
            "it uses numbers the candidate never gave (5)",
        ),
    ],
)
def test_grounding_flags_invented_sentences(text, source, problem):
    sentence = Sentence(text=text, source=source)
    assert grounding_problems([sentence], [LIVE_RESUME, "I set up the alerts."]) == [
        problem
    ]


MIGRATION = (
    "When a junior engineer I mentored shipped a migration that locked a table in "
    "production, I rolled it back within ten minutes and paired with him on a "
    "runbook for online migrations."
)


def test_grounding_flags_a_story_tied_to_an_unrelated_resume_fact():
    # T-111: asked about building the refunds API, they told the migration story;
    # the rewrite claimed it happened while building the refunds API.
    stitched = Sentence(
        text="During the development of the refunds API, I faced a challenge when a "
        "junior engineer I mentored shipped a migration that locked a table."
    )
    told = Sentence(
        text="At Acme Payments, a junior engineer I mentored shipped a migration "
        "that locked a table in production."
    )
    resume_only = Sentence(text="I built the refunds API in Python and Flask.")
    problems = grounding_problems(
        [stitched, told, resume_only], [LIVE_RESUME, MIGRATION], LIVE_RESUME
    )
    assert "ties what the candidate said" in problems[0]
    assert "refunds" in problems[0]
    # Their employer, or a résumé fact on its own, is fine.
    assert problems[1:] == ["", ""]


def test_stitch_check_needs_the_resume():
    stitched = Sentence(
        text="During the development of the refunds API, a junior engineer I "
        "mentored shipped a migration that locked a table."
    )
    assert grounding_problems([stitched], [LIVE_RESUME, MIGRATION]) == [""]


def test_verdicts():
    assert [verdict_for(s) for s in (4.2, 3.0, 2.9)] == ["hire", "lean hire", "no hire"]


# ---- report generation ---------------------------------------------------


def test_report_scores_each_question_then_summarizes(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    before = len(fire.calls)
    res = build(client, auth, sid)
    assert res.status_code == 202, res.get_json()
    report = res.get_json()["report"]
    assert fire.kinds()[before:] == ["score", "gap", "score", "gap", "summary"]

    assert report["status"] == "ready"
    assert report["progress"] == {"scored": 2, "total": 2, "set_aside": 0}
    # Role 70% (API design 4) + communication 30% split equally (3, 4, 2) → 3.7,
    # computed here, not by the AI.
    assert report["overall_score"] == pytest.approx(3.7)
    assert report["verdict"] == "lean hire"
    assert report["takeaways"] == SUMMARY_TAKEAWAYS
    # The untested criterion isn't shown or counted.
    ev0 = report["questions"][0]["evaluation"]
    assert [c["name"] for c in ev0["criteria"]] == [
        "API design",
        "Structure",
        "Clarity",
        "Relevance",
    ]
    assert report["verdict_reason"].startswith("Solid ownership")

    first = report["questions"][0]
    assert first["text"] == "Walk me through your Acme project."
    assert [e["is_follow_up"] for e in first["exchange"]] == [False, True]
    ev = first["evaluation"]
    assert ev["stronger_version"] == (
        "At Acme I built the billing API. That led to [add the result you achieved]."
    )
    # Only quotes the candidate actually said survive (for highlighting).
    assert [w["quote"] for w in ev["weak_moments"]] == []
    second = report["questions"][1]["evaluation"]
    assert [w["quote"] for w in second["weak_moments"]] == ["My answer"]
    # Delivery covers the main answer plus its follow-up.
    assert first["delivery"]["duration_sec"] == 80
    assert first["delivery"]["words"] == 12
    assert report["analytics"]["questions"] == 2

    # The scorer sees the résumé, the rubric and the follow-up exchange.
    score_prompt = fire.calls[before]["prompt"]
    assert RESUME in score_prompt and "I owned the schema." in score_prompt
    # Typed answers are marked as not spoken (spoken ones may have mishearings).
    assert '"spoken": false' in score_prompt and "transcription error" in score_prompt
    assert '"name": "API design"' in score_prompt

    # Asking again doesn't pay twice.
    again = build(client, auth, sid)
    assert again.status_code == 202 and len(fire.calls) == before + 5
    got = client.get(f"/api/sessions/{sid}/report", headers=auth)
    assert got.get_json()["report"]["overall_score"] == pytest.approx(3.7)


SUMMARY_TAKEAWAYS = ["Quantify results.", "Lead with the point.", "Keep answers tight."]


def test_failed_question_is_resumed_without_rescoring(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = [FireError("The AI service is busy", 429)]
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "failed"
    assert report["progress"] == {"scored": 1, "total": 2, "set_aside": 0}
    assert report["questions"][0]["evaluation"] is None
    assert report["questions"][0]["delivery"]["words"] == 12  # analytics still shown

    before = len(fire.calls)
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "ready"
    assert fire.kinds()[before:] == ["score", "gap", "summary"]
    assert Evaluation.query.count() == 2


def test_invalid_scorer_json_is_retried_once(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = ['{"criteria": []}']
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "ready"
    assert fire.kinds().count("score") == 3


def test_long_nested_texts_are_trimmed_not_rejected(client, auth, planned, fire):
    # T-105: a long recalled answer overflowed a nested quote on every retry.
    sid = planned["id"]
    finished(client, auth, fire, sid)
    long = {
        **SCORE,
        "said": {"situation": "x " * 500, "actions": ["did it"] * 12},
        "weak_moments": [{"quote": "", "why": "empty quote"}],
        "missing_points": [
            {"point": "A result", "covered": False, "evidence": "y " * 400}
        ],
    }
    fire.scores = [long, long]
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "ready"
    assert fire.kinds().count("score") == 2  # no invalid-JSON retries


def test_empty_rewrite_falls_back_instead_of_failing(client, auth, planned, fire):
    # T-105: the scorer had nothing to rewrite and returned [], failing every time.
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = [{**SCORE, "stronger_version": []}]
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "ready"
    assert report["questions"][0]["evaluation"]["stronger_version"]


def test_unscorable_question_is_set_aside_so_the_report_finishes(
    client, auth, planned, fire
):
    # T-105: at temperature 0 the same answer got the same unusable reply, so
    # "Finish the report" failed again every time.
    sid = planned["id"]
    finished(client, auth, fire, sid)
    bad = '{"criteria": []}'
    fire.scores = [bad, bad]
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "failed"
    assert report["progress"] == {"scored": 1, "total": 2, "set_aside": 0}

    fire.scores = [bad, bad]
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "ready"
    assert report["progress"] == {"scored": 1, "total": 2, "set_aside": 1}
    assert report["questions"][0]["set_aside"] is True
    assert report["questions"][1]["set_aside"] is False
    assert report["takeaways"] and report["overall_score"] is not None

    # Asking again doesn't spend anything on it.
    before = len(fire.calls)
    assert build(client, auth, sid).get_json()["report"]["status"] == "ready"
    assert "score" not in fire.kinds()[before:]


def test_a_crash_while_scoring_doesnt_stop_the_other_questions(
    client, auth, planned, fire
):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = [RuntimeError("bug")]
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "failed"
    assert report["progress"]["scored"] == 1  # the other one was still scored
    fire.scores = [RuntimeError("bug")]
    assert build(client, auth, sid).get_json()["report"]["status"] == "ready"


def test_rewrite_keeps_the_sentence_a_back_reference_needs(client, auth, planned, fire):
    # T-127 (live): the rewrite opened "I moved those queries…" without the
    # sentence that said which queries.
    sid = planned["id"]
    started(client, auth, sid)
    fire.turns = [{"action": "wrap_up", "message": "Thanks, that's all."}]
    first = "Checkout got slow at peak because reporting queries hit the main database."
    answer(
        client,
        auth,
        sid,
        f"{first} I moved those queries to a nightly ETL at Acme on the billing API.",
        60_000,
    )
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    fire.scores = [
        {
            **SCORE,
            "stronger_version": [
                {
                    "text": "On the Acme billing API, I moved those queries to a nightly ETL.",
                    "source": None,
                },
                {"text": "That led to [add the result you achieved].", "source": None},
            ],
        }
    ]
    report = build(client, auth, sid).get_json()["report"]
    rewrite = report["questions"][0]["evaluation"]["stronger_version"]
    assert rewrite.startswith(first), rewrite


def test_restore_context_only_adds_a_missing_antecedent():
    from app.services.scoring import restore_context

    said = [
        "Checkout got slow because reporting queries ran on the replicas. "
        "I moved those queries to an ETL."
    ]
    whole = "Reporting queries slowed checkout, so I moved those queries to an ETL."
    assert restore_context(whole, said) == whole  # introduced in the same sentence
    assert restore_context("Those changes helped.", ["I shipped it."]) == (
        "Those changes helped."
    )  # nothing to bring back
    assert restore_context("I moved those queries to an ETL.", said) == (
        "Checkout got slow because reporting queries ran on the replicas. "
        "I moved those queries to an ETL."
    )


def test_result_placeholder_is_filled_with_the_result_they_gave(
    client, auth, planned, fire
):
    # T-107: the answer said what happened, the rewrite asked them to add it.
    sid = planned["id"]
    started(client, auth, sid)
    fire.turns = [{"action": "wrap_up", "message": "Thanks, that's all."}]
    answer(
        client,
        auth,
        sid,
        "I built the billing API at Acme, and failed payments fell from 4% to 1%.",
        60_000,
    )
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    fire.scores = [
        {
            **SCORE,
            "star": {
                **SCORE["star"],
                "result": True,
                "result_quote": "failed payments fell from 4% to 1%",
            },
        }
    ]
    report = build(client, auth, sid).get_json()["report"]
    rewrite = report["questions"][0]["evaluation"]["stronger_version"]
    assert "[add the result" not in rewrite
    assert rewrite.endswith("Failed payments fell from 4% to 1%.")


def test_fill_result_only_replaces_result_placeholders():
    quote = "we haven't had a locking incident since"
    assert (
        fill_result(
            "I rolled it back. Since then, [add the result you achieved].", quote
        )
        == "I rolled it back. We haven't had a locking incident since."
    )
    assert (
        fill_result("I did it. [add the result]", None) == "I did it. [add the result]"
    )
    # T-126 (live): score.txt's own example placeholder counts as a result one.
    live = "As a result, p95 fell from 1.8 seconds to 300 milliseconds"
    told = f"I moved the queries to an ETL. {live}. [add what changed because of your work]"
    assert fill_result(told, live) == f"I moved the queries to an ETL. {live}."
    notes = "[Add: Mentioning collaboration.] [Add: Broader context.]"
    assert fill_result(f"{told} {notes}", live) == (
        f"I moved the queries to an ETL. {live}. {notes}"
    )
    # T-123: no result placeholder and no result: it goes at the end.
    assert (
        fill_result("At [add the company].", quote)
        == "At [add the company]. We haven't had a locking incident since."
    )
    live = "p95 on the main app went from 1.8 seconds to 300 milliseconds."
    moved = "I moved the reporting queries to a nightly ETL."
    assert (
        fill_result(moved, live)
        == f"{moved} P95 on the main app went from 1.8 seconds to 300 milliseconds."
    )
    told = "I moved them to an ETL, and p95 fell from 1.8 s to 300 ms."
    assert fill_result(told, live) == told
    # T-121: already in the rewrite, so the placeholder just goes.
    assert (
        fill_result(
            "I paired with him. [add the result you achieved]. And we haven't had "
            "a locking incident since.",
            quote,
        )
        == "I paired with him. And we haven't had a locking incident since."
    )


def test_paragraph_items_are_checked_sentence_by_sentence():
    item = Sentence(
        text="I built the refunds API. I also added caching strategies everywhere.",
        source="Built the refunds API",
    )
    parts = split_sentences([item])
    assert [p.text for p in parts] == [
        "I built the refunds API.",
        "I also added caching strategies everywhere.",
    ]
    assert grounding_problems(parts, [LIVE_RESUME]) == [
        "",
        "it adds details the candidate never gave",
    ]


FULL_RESUME = (
    "Sam Rivera — Backend Engineer\n"
    + LIVE_RESUME
    + "\nBright Labs (2019–2021): Wrote internal REST services in Django; "
    "added Redis caching; on-call rotation.\nSkills: Python, Flask, MySQL."
)


@pytest.mark.parametrize(
    "question,expected",
    [
        (
            "Can you describe a time when you had to mentor junior engineers?",
            "At Acme Payments, I mentored two junior engineers. [Describe one",
        ),
        (
            "Walk me through a Django service you wrote.",
            "At Bright Labs, I wrote internal REST services in Django. [Describe",
        ),
        (
            "Tell me about an on-call incident.",
            '[Build this from your résumé: "on-call rotation".] [Describe',
        ),
        ("How do you handle conflict with a product manager?", FALLBACK_REWRITE),
    ],
)
def test_fallback_starts_from_the_matching_resume_line(question, expected):
    assert resume_fallback(question, FULL_RESUME).startswith(expected)


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "This change cut latency to 300ms.",
            "[What you changed] cut latency to 300ms.",
        ),
        (
            "These keys ensured no double refunds.",
            "The keys ensured no double refunds.",
        ),
        ("For instance, I moved the queries.", "I moved the queries."),
        ("To address this, we added alerts.", "We added alerts."),
        ("They designed the tables.", "They designed the tables."),
        ("This was at Acme.", "This was at Acme."),
    ],
)
def test_detach_rewrites_openers_that_point_at_a_dropped_sentence(text, expected):
    assert _detach(text) == expected


def test_kept_sentences_are_detached_only_after_a_gap():
    sentences = [
        Sentence(text="I built the API."),
        Sentence(text="This change cut latency."),
        Sentence(text="It served 9 million users."),
        Sentence(text="This change cut latency."),
    ]
    kept = _keep(sentences, ["", "", "it uses numbers", ""])
    assert [s.text for s in kept] == [
        "I built the API.",
        "This change cut latency.",
        "[What you changed] cut latency.",
    ]


def invented(*sentences: dict) -> dict:
    return {**SCORE, "stronger_version": list(sentences)}


GOOD = {
    "text": "At Acme I built the billing API.",
    "source": "Built the Acme billing API",
}
MADE_UP = {"text": "It handled 9 million requests a day.", "source": None}


def test_invented_rewrite_is_repaired_once(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = [invented(GOOD, MADE_UP), invented(GOOD)]
    before = len(fire.calls)
    report = build(client, auth, sid).get_json()["report"]
    assert fire.kinds()[before:] == [
        "score",
        "gap",
        "repair",
        "score",
        "gap",
        "summary",
    ]
    repair = fire.calls[before + 2]["prompt"]
    assert "Sentence 2: it uses numbers the candidate never gave (9)." in repair
    assert "Sentence 1:" not in repair
    first = report["questions"][0]["evaluation"]["stronger_version"]
    assert (
        first
        == "I built the Acme billing API. The result was [add the result you achieved]."
    )
    # "What changed" described the rejected rewrite, so it isn't shown.
    assert report["questions"][0]["evaluation"]["changes"] == []
    assert report["questions"][1]["evaluation"]["changes"] == SCORE["changes"]
    second = report["questions"][1]["evaluation"]["stronger_version"]
    assert second == "At Acme I built the billing API."


def test_still_invented_sentences_are_dropped(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.scores = [invented(GOOD, MADE_UP), invented(MADE_UP)]
    fire.repairs = [invented(MADE_UP, GOOD), invented(MADE_UP)]
    report = build(client, auth, sid).get_json()["report"]
    assert fire.kinds().count("repair") == 2
    evs = [q["evaluation"]["stronger_version"] for q in report["questions"]]
    # Never shown: the invented sentence. Nothing grounded left → a placeholder.
    assert evs == ["At Acme I built the billing API.", FALLBACK_REWRITE]
    # Sentences were dropped, so no "what changed" list describes unseen text.
    assert [q["evaluation"]["changes"] for q in report["questions"]] == [[], []]


def test_placeholder_only_rewrite_falls_back_to_the_resume(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    bare = {"text": "[add the result you achieved] [name the tool you used]"}
    fire.scores = [invented(bare), invented(GOOD)]
    report = build(client, auth, sid).get_json()["report"]
    first = report["questions"][0]["evaluation"]["stronger_version"]
    assert first.startswith("I built the Acme billing API in Python and MySQL.")


def test_all_criteria_untested_is_retried(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    none = [{**c, "score": None} for c in SCORE["criteria"]]
    fire.scores = [{**SCORE, "criteria": none}]
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "ready"
    assert fire.kinds().count("score") == 3


def test_report_needs_a_finished_interview(client, auth, planned, fire):
    sid = planned["id"]
    assert client.get(f"/api/sessions/{sid}/report", headers=auth).status_code == 404
    assert build(client, auth, sid).status_code == 409
    started(client, auth, sid)
    assert build(client, auth, sid).status_code == 409


def test_report_respects_monthly_budget(app, client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    row = db.session.get(UsageLimit, (1, today()))
    row.fire_spend_usd = 5
    db.session.commit()
    res = build(client, auth, sid)
    assert res.status_code == 429 and "budget" in res.get_json()["error"]
    assert Report.query.count() == 0


def test_reports_are_private(client, auth, planned, fire, signup):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    token = signup(email="eve@example.com").get_json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/sessions/{sid}/report", headers=other).status_code == 404
    assert build(client, other, sid).status_code == 404


# ---- Try again -------------------------------------------------------------


def retry(
    client,
    auth,
    sid,
    qid,
    text="A tighter answer with a result: we cut p95 latency in half.",
    **extra,
):
    return client.post(
        f"/api/sessions/{sid}/questions/{qid}/retry",
        json={"text": text, "duration_ms": 45_000, "input_mode": "voice", **extra},
        headers=auth,
    )


def test_try_again_shows_before_and_after(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    qid = report["report"]["questions"][0]["question_id"]

    better = {**SCORE_ALL_FIVE}
    fire.scores = [better]
    res = retry(client, auth, sid, qid)
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["before_score"] == pytest.approx(3.7)
    assert body["attempt"]["attempt_no"] == 2
    assert body["attempt"]["evaluation"]["score"] == 5

    # The retry is scored alone, against the planned wording of the question.
    prompt = fire.calls[-1]["prompt"]
    assert "Walk me through your Acme project." in prompt
    assert "I owned the schema." not in prompt

    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    q = report["report"]["questions"][0]
    assert [a["attempt_no"] for a in q["attempts"]] == [2]
    assert q["evaluation"]["score"] == pytest.approx(3.7)  # original kept
    # The interview transcript still shows only the original answers.
    s = client.get(f"/api/sessions/{sid}", headers=auth).get_json()["session"]
    assert "A tighter answer with a result: we cut p95 latency in half." not in [
        t["answer"] for t in s["transcript"]
    ]

    assert retry(client, auth, sid, qid).get_json()["attempt"]["attempt_no"] == 3


SCORE_ALL_FIVE = {
    "criteria": [
        {"name": n, "score": 5}
        for n in ("API design", "Structure", "Clarity", "Relevance")
    ],
    "summary": "Clear and complete.",
    "stronger_version": [GOOD],
}


def test_try_again_validation(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    fire.turns = [{"action": "follow_up", "message": "What was your part?"}]
    answer(client, auth, sid)
    s = client.get(f"/api/sessions/{sid}", headers=auth).get_json()["session"]
    root, follow = s["transcript"][0]["question_id"], s["transcript"][1]["question_id"]
    assert retry(client, auth, sid, root).status_code == 409  # still running
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    assert retry(client, auth, sid, follow).status_code == 404  # follow-ups: no
    assert retry(client, auth, sid, 999).status_code == 404
    assert retry(client, auth, sid, root, text="  ").status_code == 400


def test_failed_retry_is_not_kept(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    qid = Answer.query.first().question_id
    fire.scores = [FireError("The AI service is busy", 429)]
    res = retry(client, auth, sid, qid)
    assert res.status_code == 429
    assert Answer.query.filter(Answer.attempt_no > 1).count() == 0
    # The failed call's spend is still recorded.
    assert db.session.get(UsageLimit, (1, today())).llm_calls > 0


def test_try_again_daily_cap(app, client, auth, planned, fire):
    app.config["DAILY_RETRIES"] = 1
    sid = planned["id"]
    finished(client, auth, fire, sid)
    qid = Answer.query.first().question_id
    assert retry(client, auth, sid, qid).status_code == 201
    res = retry(client, auth, sid, qid)
    assert res.status_code == 429 and "retries" in res.get_json()["error"]
    clip = client.post(
        f"/api/sessions/{sid}/transcribe",
        data={"audio": (io.BytesIO(CLIP), "a.webm", "audio/webm")},
        headers=auth,
    )
    assert clip.status_code == 429


def test_transcribe_works_after_the_interview_for_retries(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.transcripts = ["A spoken retry."]
    res = client.post(
        f"/api/sessions/{sid}/transcribe",
        data={"audio": (io.BytesIO(CLIP), "a.webm", "audio/webm")},
        headers=auth,
    )
    assert res.status_code == 200 and res.get_json()["text"] == "A spoken retry."


def test_spoken_retry_is_flagged_for_transcription_slips(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    qid = report["report"]["questions"][0]["question_id"]
    assert retry(client, auth, sid, qid).status_code == 201
    assert '"spoken": true' in fire.calls[-1]["prompt"]


# Live (T-29): the rewrite added an impact the candidate never claimed.
EMOTION_ANSWER = (
    "I worked with Python and OpenCV to make the learning experience more engaging. "
    "We reached about 85 to 90% accuracy in testing."
)


@pytest.mark.parametrize(
    "text, problem",
    [
        (
            "I reached about 85 to 90% accuracy, which significantly improved user "
            "engagement.",
            "it claims an impact the candidate never stated (engagement, significantly)",
        ),
        (
            "That increased retention for our learners.",
            "it claims an impact the candidate never stated (retention)",
        ),
        ("We reached about 85 to 90% accuracy in testing.", ""),
        ("That made learning more engaging: [add the result you measured].", ""),
    ],
)
def test_grounding_flags_invented_impact(text, problem):
    assert grounding_problems([Sentence(text=text)], [EMOTION_ANSWER]) == [problem]


def test_try_again_is_scored_on_the_first_attempts_criteria(
    client, auth, planned, fire
):
    # Live (T-29): the first answer was scored on 3 criteria and the retry on 6, so
    # the suggested stronger version scored lower than the original.
    sid = planned["id"]
    fire.scores = [
        {
            **SCORE_ALL_FIVE,
            "criteria": [
                {"name": "API design", "score": None},
                {"name": "Structure", "score": 3},
                {"name": "Clarity", "score": 4},
                {"name": "Relevance", "score": 4},
            ],
        }
    ]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    qid = report["report"]["questions"][0]["question_id"]

    # The scorer first drops a criterion, is told to score it, then complies.
    partial = {
        **SCORE_ALL_FIVE,
        "criteria": [
            {"name": "Structure", "score": 5},
            {"name": "Clarity", "score": 5},
        ],
    }
    fire.scores = [partial, {**SCORE_ALL_FIVE, "criteria": SCORE_ALL_FIVE["criteria"]}]
    body = retry(client, auth, sid, qid).get_json()

    prompt = fire.calls[-2]["prompt"]
    assert "This answer is a retry" in prompt
    assert '"name": "API design"' not in prompt  # not scored the first time
    assert "missing: Relevance" in fire.calls[-1]["messages"][-1]["content"]
    criteria = body["attempt"]["evaluation"]["criteria"]
    assert [c["name"] for c in criteria] == ["Structure", "Clarity", "Relevance"]
    assert body["attempt"]["evaluation"]["score"] == 5


def test_scoring_runs_at_temperature_zero(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    scoring = [c for c in fire.calls if c["prompt"].startswith("Score one question")]
    assert scoring and {c["temperature"] for c in scoring} == {0}


def test_near_empty_answer_scores_one_without_a_fire_call(client, auth, planned, fire):
    # Live (T-33): "Thank you." scored 3.6 and "so" 3.27, with feedback taken from
    # the résumé.
    sid = planned["id"]
    started(client, auth, sid)
    fire.turns = [{"action": "next_question", "message": "How would you design it?"}]
    answer(client, auth, sid, "Thank you.", 1_800)
    answer(
        client,
        auth,
        sid,
        "I'd put a token bucket per API key in Redis with a Lua script.",
    )
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    before = len(fire.calls)
    report = build(client, auth, sid).get_json()["report"]

    short = report["questions"][0]["evaluation"]
    assert short["score"] == 1
    assert {c["score"] for c in short["criteria"]} == {1}
    assert short["summary"].startswith("This answer was too short to score (2 words)")
    assert short["weak_moments"] == []
    scored = [c for c in fire.calls[before:] if c["prompt"].startswith("Score one")]
    assert len(scored) == 1  # only the real answer cost a Fire call
    assert "Thank you." not in scored[0]["prompt"]


def test_retry_is_judged_against_the_first_attempt(client, auth, planned, fire):
    # Live (T-29): re-reading the suggested rewrite scored the same, judged blind.
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    qid = report["report"]["questions"][0]["question_id"]
    fire.scores = [SCORE_ALL_FIVE]
    retry(client, auth, sid, qid)
    prompt = fire.calls[-1]["prompt"]
    assert "First attempt (JSON):" in prompt
    assert "Um, I built the billing API at Acme." in prompt
    assert '"comment": "Wandered a little."' in prompt
    assert "Rewording the same content is not an improvement" in prompt


def test_rewrite_must_fix_the_gaps_not_polish(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    prompt = next(
        c["prompt"] for c in fire.calls if c["prompt"].startswith("Score one")
    )
    assert "not a polished copy" in prompt
    assert "First attempt" not in prompt  # only retries compare


def test_too_short_retry_scores_one(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    report = client.get(f"/api/sessions/{sid}/report", headers=auth).get_json()
    qid = report["report"]["questions"][0]["question_id"]
    calls = len(fire.calls)
    body = retry(client, auth, sid, qid, text="so").get_json()
    assert body["attempt"]["evaluation"]["score"] == 1
    assert len(fire.calls) == calls


def test_fairness_rules_reach_every_prompt(client, auth, planned, fire):
    # docs/INTERVIEWER_RULES.md, Safety and Scoring (T-42).
    sid = planned["id"]
    finished(client, auth, fire, sid)
    build(client, auth, sid)
    prompts = {
        kind: next(c["prompt"] for c in fire.calls if marker in c["prompt"])
        for kind, marker in (
            ("plan", "question plan"),
            ("turn", "live practice interview"),
            ("score", "Score one question"),
        )
    }
    assert "Never ask about age, family" in prompts["plan"]
    assert "Don't assume the candidate lacks a skill" in prompts["plan"]
    assert "Never ask about age, family" in prompts["turn"]
    assert "nervousness, an accent" in prompts["turn"]
    assert "Missing evidence is not lack of knowledge" in prompts["score"]
    assert "don't penalize a concise answer" in prompts["score"]
    assert "an accent" in prompts["score"]


def test_off_topic_answer_is_not_thanked_as_an_answer(client, auth, planned, fire):
    # T-141: an off-topic reply to a follow-up got "Thanks for walking me through
    # that." and the next question, as if it had answered.
    sid = planned["id"]
    finished(client, auth, fire, sid)
    turn = next(
        c["prompt"] for c in fire.calls if "live practice interview" in c["prompt"]
    )
    assert "or you already steered them back once" in turn
    assert "Let's leave <the topic of your question> there." in turn
    assert "after an answer about a different topic, use the neutral line" in turn


def test_interviewer_adapts_the_challenge(client, auth, planned, fire):
    # docs/INTERVIEWER_RULES.md, Adaptive Difficulty (T-43).
    sid = planned["id"]
    started(client, auth, sid)
    answer(client, auth, sid, "I designed the billing API and owned its schema.")
    prompt = next(
        c["prompt"] for c in fire.calls if "live practice interview" in c["prompt"]
    )
    assert "raise the challenge one step" in prompt
    assert "Never make it harder after a struggle" in prompt


def test_report_covers_strengths_confidence_competencies_and_exercises(
    client, auth, planned, fire
):
    # docs/INTERVIEWER_RULES.md, Answer Coaching and Final Report (T-41).
    sid = planned["id"]
    finished(client, auth, fire, sid)
    report = build(client, auth, sid).get_json()["report"]

    e = report["questions"][0]["evaluation"]
    assert e["strengths"] == ["Owned the billing API end to end."]  # blanks dropped
    assert e["confidence"] == "medium"
    assert e["confidence_note"] == "Part of the answer may have been misheard."
    prompt = next(
        c["prompt"] for c in fire.calls if c["prompt"].startswith("Score one")
    )
    assert '"strengths"' in prompt and '"confidence"' in prompt

    assert report["exercises"] == SUMMARY["exercises"]
    names = [c["name"] for c in report["competencies"]]
    assert names[0] == "API design"  # job criteria first
    assert set(names) == {"API design", "Structure", "Clarity", "Relevance"}
    structure = next(c for c in report["competencies"] if c["name"] == "Structure")
    assert structure == {
        "name": "Structure",
        "kind": "universal",
        "score": 3.0,
        "questions": 2,
    }


def test_report_lists_questions_never_answered(client, auth, planned, fire):
    sid = planned["id"]
    started(client, auth, sid)
    answer(client, auth, sid, "I built the billing API at Acme and owned the schema.")
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    report = build(client, auth, sid).get_json()["report"]
    assert [q["text"] for q in report["unanswered"]] == [
        "How would you design a rate limiter?",
        "How do you index a slow query?",
    ]
    assert report["unanswered"][0]["asked"] is True  # asked, then ended
    assert report["unanswered"][1]["asked"] is False


COPY_ANSWER = "I built the billing API at Acme and owned the schema for it."


def copy_score() -> dict:
    return {
        **SCORE,
        "stronger_version": [{"text": COPY_ANSWER, "source": COPY_ANSWER}],
        "changes": [],
    }


def one_answer_report(client, auth, sid):
    started(client, auth, sid)
    answer(client, auth, sid, COPY_ANSWER)
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    return build(client, auth, sid).get_json()["report"]["questions"][0]["evaluation"]


def test_rewrite_that_copies_the_answer_is_repaired(client, auth, planned, fire):
    # Live re-check (T-46): the stronger version repeated the answer word for word.
    fire.scores = [copy_score()]
    e = one_answer_report(client, auth, planned["id"])
    repair = next(
        c["prompt"] for c in fire.calls if 'Fix a "stronger version"' in c["prompt"]
    )
    assert (
        "repeats the candidate's answer" in repair and "A measurable result" in repair
    )
    assert e["stronger_version"] == (
        "I built the Acme billing API. The result was [add the result you achieved]."
    )


def test_rewrite_still_copying_gets_gap_placeholders(client, auth, planned, fire):
    fire.scores = [copy_score()]
    fire.repairs = [
        {"stronger_version": [{"text": COPY_ANSWER, "source": COPY_ANSWER}]}
    ]
    e = one_answer_report(client, auth, planned["id"])
    assert e["stronger_version"] == f"{COPY_ANSWER} [Add: A measurable result.]"


def test_confidence_is_about_the_judgment_not_the_answer(client, auth, planned, fire):
    # Live re-check (T-45): every answer came back "medium" for being weak.
    one_answer_report(client, auth, planned["id"])
    prompt = next(
        c["prompt"] for c in fire.calls if c["prompt"].startswith("Score one")
    )
    assert "how RELIABLE your judgment is, not how good the answer is" in prompt
    assert 'Most answers are "high"' in prompt


def test_copy_check_measures_the_rewrite_not_all_answers():
    # Live re-check (T-46): one short answer copied back slipped past a ratio
    # taken over all the answers together.
    from app.services.scoring import copy_ratio

    answers = ["Communication matters a lot to me.", "I learned a lot from that."]
    assert copy_ratio("I learned a lot from that.", answers) == 1.0
    assert (
        copy_ratio("I led the [add the project] and cut costs by [add %].", answers)
        == 0
    )


def test_off_topic_answer_gets_the_resume_outline_not_a_story(
    client, auth, planned, fire
):
    # Live re-check (T-48): for an answer that missed the question, the AI stitched
    # résumé facts into an incident that never happened.
    fire.scores = [
        {
            **SCORE,
            "criteria": [
                {"name": "API design", "score": 1},
                {"name": "Structure", "score": 2},
                {"name": "Clarity", "score": 3},
                {"name": "Relevance", "score": 2},
            ],
            "stronger_version": [
                {"text": "At Acme I built the billing API during a critical outage."}
            ],
        }
    ]
    e = one_answer_report(client, auth, planned["id"])
    assert "critical outage" not in e["stronger_version"]
    assert "[" in e["stronger_version"]  # an outline with placeholders to fill in
    assert not any('Fix a "stronger version"' in c["prompt"] for c in fire.calls)


def _report_for(client, auth, sid, text):
    started(client, auth, sid)
    answer(client, auth, sid, text)
    client.post(f"/api/sessions/{sid}/end", headers=auth)
    return build(client, auth, sid).get_json()["report"]["questions"][0]["evaluation"]


def test_small_talk_answer_scores_1_without_a_fire_call(client, auth, planned, fire):
    # User report (T-61): "Hi, nice meeting you guys. I'm doing good. How are you
    # guys doing?" to a project question scored 3.56 with invented content.
    e = _report_for(
        client,
        auth,
        planned["id"],
        "Hi, nice meeting you guys. I'm doing good. How are you guys doing?",
    )
    assert e["score"] == 1
    assert "didn't answer the question" in e["summary"]
    assert "small talk is fine" in e["summary"]
    assert all(c["score"] == 1 for c in e["criteria"])
    assert not any("Score one question" in c["prompt"] for c in fire.calls)


def test_scorer_flagged_non_answer_scores_1(client, auth, planned, fire):
    fire.scores = [{**SCORE, "answers_question": False, "answer_quote": None}]
    e = _report_for(
        client, auth, planned["id"], "I really enjoy hiking on weekends with my dog."
    )
    assert e["score"] == 1 and e["strengths"] == []
    # An off-topic answer isn't small talk (T-71).
    assert "small talk" not in e["summary"] and "clarify" in e["summary"]
    prompt = next(
        c["prompt"] for c in fire.calls if "Score one question" in c["prompt"]
    )
    assert '"answers_question"' in prompt


def test_false_non_answer_verdict_is_overruled_by_the_answer_check(
    client, auth, planned, fire
):
    # T-112: an answer listing the steps asked for was scored 1 once, 4.2 on a re-run.
    fire.scores = [{**SCORE, "answers_question": False, "answer_quote": None}]
    fire.answer_checks = [{"attempts": True, "quote": "the billing API at Acme"}]
    e = _report_for(
        client, auth, planned["id"], "My answer is about the billing API at Acme work."
    )
    assert e["score"] > 1
    scores = [c["prompt"] for c in fire.calls if "Score one question" in c["prompt"]]
    assert len(scores) == 2
    assert "A separate check found" not in scores[0]
    assert 'their words: "the billing API at Acme"' in scores[1]


def test_answer_check_quote_must_be_in_the_answer(client, auth, planned, fire):
    fire.scores = [{**SCORE, "answers_question": False, "answer_quote": None}]
    fire.answer_checks = [
        {"attempts": True, "quote": "I scaled the Kafka cluster to ten brokers"}
    ]
    e = _report_for(
        client, auth, planned["id"], "I really enjoy hiking on weekends with my dog."
    )
    assert e["score"] == 1
    assert sum("Score one question" in c["prompt"] for c in fire.calls) == 1


def test_failed_answer_check_keeps_the_scorers_verdict(client, auth, planned, fire):
    fire.scores = [{**SCORE, "answers_question": False, "answer_quote": None}]
    fire.answer_checks = [FireError("The AI service is busy", 429)] * 2
    e = _report_for(
        client, auth, planned["id"], "I really enjoy hiking on weekends with my dog."
    )
    assert e["score"] == 1


def test_score_prompt_does_not_anchor_on_false_or_null(client, auth, planned, fire):
    # T-68: the example JSON said "result": false / "covered": false and the model
    # copied it (0 of 30 results, 0 of 429 points ever credited). T-69: role
    # criteria came back null on questions that test them.
    _report_for(
        client, auth, planned["id"], "My answer is about the billing API at Acme work."
    )
    prompt = next(
        c["prompt"] for c in fire.calls if "Score one question" in c["prompt"]
    )
    assert '"result": true | false' in prompt and '"covered": true | false' in prompt
    assert '"said"' in prompt and "churn fell" in prompt
    assert "tests SQL" in prompt


def test_invented_evidence_quote_scores_1(client, auth, planned, fire):
    fire.scores = [
        {
            **SCORE,
            "answers_question": True,
            "answer_quote": "I implemented real-time facial emotion detection with OpenCV",
        }
    ]
    e = _report_for(
        client, auth, planned["id"], "My answer is about the billing API at Acme work."
    )
    assert e["score"] == 1


def test_real_evidence_quote_keeps_the_score(client, auth, planned, fire):
    fire.scores = [
        {**SCORE, "answers_question": True, "answer_quote": "the billing API at Acme"}
    ]
    e = _report_for(
        client, auth, planned["id"], "My answer is about the billing API at Acme work."
    )
    assert e["score"] > 1


def test_coverage_and_result_follow_the_quoted_evidence(client, auth, planned, fire):
    # T-68: the model said "not covered" / "no result" while quoting the words.
    fire.scores = [
        {
            **SCORE,
            "missing_points": [
                {
                    "point": "A result",
                    "covered": False,
                    "evidence": "zero double refunds since launch",
                },
                {
                    "point": "Their role",
                    "covered": True,
                    "evidence": "I led a team of forty people",
                },
                {"point": "Trade-offs", "covered": False, "evidence": None},
                {"point": "Measurable outcomes", "covered": False, "evidence": None},
            ],
            "star": {
                **SCORE["star"],
                "result": False,
                "result_quote": "we have had zero double refunds since launch",
            },
        }
    ]
    e = _report_for(
        client,
        auth,
        planned["id"],
        "I built the refunds API at Acme and we have had zero double refunds since launch.",
    )
    assert [m["covered"] for m in e["missing_points"]] == [True, False, False, True]
    assert e["star"]["result"] is True


def test_star_and_points_follow_what_the_candidate_said(client, auth, planned, fire):
    # T-68: the model copied the result but still marked STAR result false and
    # listed "the situation" and "a result" as missing.
    fire.scores = [
        {
            **SCORE,
            "said": {
                "situation": "our checkout kept timing out at peak",
                "task": None,
                "actions": ["I added a queue in front of the payment call"],
                "result": "timeouts went to zero that quarter",
                "other": [],
            },
            "missing_points": [
                {"point": "The initial situation", "covered": False, "evidence": None},
                {"point": "The steps they took", "covered": False, "evidence": None},
                {"point": "A concrete result", "covered": False, "evidence": None},
                {"point": "Who they worked with", "covered": False, "evidence": None},
            ],
            "star": {
                "situation": False,
                "task": False,
                "action": False,
                "result": False,
                "note": "",
            },
        }
    ]
    e = _report_for(
        client,
        auth,
        planned["id"],
        "Our checkout kept timing out at peak. I added a queue in front of the "
        "payment call, and timeouts went to zero that quarter.",
    )
    assert [m["covered"] for m in e["missing_points"]] == [True, True, True, False]
    star = e["star"]
    assert star["situation"] and star["action"] and star["result"]
    assert not star["task"]


def test_invented_said_quotes_are_not_credited(client, auth, planned, fire):
    fire.scores = [
        {
            **SCORE,
            "said": {"result": "revenue grew forty percent in one year"},
            "missing_points": [
                {"point": "A concrete result", "covered": False, "evidence": None}
            ],
        }
    ]
    e = _report_for(
        client, auth, planned["id"], "My answer is about the billing API at Acme work."
    )
    assert e["missing_points"][0]["covered"] is False
    assert e["star"]["result"] is False


# ---- gap check (T-72) ---------------------------------------------------------


def test_gap_check_decides_covered_points_from_real_quotes(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.gap_checks = [
        {
            "points": [
                # The scorer called this a gap; the candidate said it.
                {"n": 1, "covered": True, "quote": "I built the billing API at Acme"},
                # The scorer credited it; the check says it was never said.
                {"n": 2, "covered": False, "quote": None},
            ]
        },
        {
            "points": [
                # "Covered" with words the candidate never said: still a gap.
                {"n": 1, "covered": True, "quote": "revenue grew forty percent"},
            ]
        },
    ]
    report = build(client, auth, sid).get_json()["report"]
    first, second = (q["evaluation"]["missing_points"] for q in report["questions"])
    assert first[0]["covered"] is True
    assert first[0]["evidence"] == "I built the billing API at Acme"
    assert first[1]["covered"] is False and first[1]["evidence"] is None
    assert second[0]["covered"] is False and second[0]["evidence"] is None
    # The check sees the follow-up answers too.
    gap_prompt = next(
        c["prompt"] for c in fire.calls if "Check which points" in c["prompt"]
    )
    assert "I owned the schema." in gap_prompt and "2. Their own role" in gap_prompt


def test_failed_gap_check_keeps_the_scorers_verdicts(client, auth, planned, fire):
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.gap_checks = [FireError("The AI service is busy", 429)] * 2
    report = build(client, auth, sid).get_json()["report"]
    assert report["status"] == "ready"
    points = report["questions"][0]["evaluation"]["missing_points"]
    assert [p["point"] for p in points] == ["A measurable result", "Their own role"]


def _relevant(score):
    return {
        **SCORE,
        "criteria": [
            {**c, "score": 4, "comment": "On topic."} if c["name"] == "Relevance" else c
            for c in SCORE["criteria"]
        ],
    }


def test_story_about_another_subject_caps_relevance(client, auth, planned, fire):
    # T-114: asked about building the refunds API, they told a migration story.
    fire.scores = [
        {
            **_relevant(SCORE),
            "summary": "The candidate described a relevant challenge clearly. "
            "They did not state the result.",
        }
    ]
    fire.gap_checks = [
        {
            "points": [],
            "named_subject": "building the billing API",
            "story_subject": "a table-locking migration",
        }
    ]
    e = _report_for(
        client,
        auth,
        planned["id"],
        "A migration I reviewed locked a table in production, so I rolled it back and wrote a runbook.",
    )
    relevance = next(c for c in e["criteria"] if c["name"] == "Relevance")
    assert relevance["score"] == 2
    assert "building the billing API" in relevance["comment"]
    assert "table-locking migration" in relevance["comment"]
    assert e["tips"][0].startswith("Tell a story about what the question names")
    assert "(building the billing API)" in e["tips"][0]
    # T-118: the summary doesn't call the story relevant.
    assert e["summary"] == (
        "The story was about a table-locking migration, but the question asked "
        "about building the billing API. They did not state the result."
    )
    prompt = next(
        c["prompt"] for c in fire.calls if "Check which points" in c["prompt"]
    )
    assert '"named_subject"' in prompt and '"story_subject"' in prompt


@pytest.mark.parametrize(
    "check",
    [
        {"points": [], "named_subject": None},
        # Their answer mentions it: on subject, whatever the story was.
        {"points": [], "named_subject": "the billing API", "story_subject": "x"},
        # A category, not a résumé item (live: "optimizing a backend process").
        {
            "points": [],
            "named_subject": "optimizing a backend process",
            "story_subject": "x",
        },
        # Only generic question words are named.
        {"points": [], "named_subject": "a challenging project", "story_subject": "x"},
    ],
)
def test_relevance_stands_without_a_named_subject_mismatch(
    client, auth, planned, fire, check
):
    fire.scores = [_relevant(SCORE)]
    fire.gap_checks = [check]
    e = _report_for(
        client, auth, planned["id"], "My answer is about the billing API at Acme work."
    )
    assert next(c for c in e["criteria"] if c["name"] == "Relevance")["score"] == 4
    assert e["summary"] == SCORE["summary"]


GENERAL_GAP = {
    "points": [],
    "named_subject": "optimizing a PostgreSQL database schema",
    "story_subject": "idempotency in a payments API",
}
IDEMPOTENCY = "I would make every write idempotent with a key stored in PostgreSQL."


def test_general_question_answered_about_something_else(client, auth, planned, fire):
    # T-142 (live): asked how they'd optimize a PostgreSQL schema, they described
    # idempotency keys "stored in PostgreSQL" and kept Relevance 4.
    fire.scores = [_relevant(SCORE)]
    fire.gap_checks = [GENERAL_GAP]
    fire.subject_checks = [{"asks_for": "x", "quote": None, "on_subject": False}]
    e = _report_for(client, auth, planned["id"], IDEMPOTENCY)
    relevance = next(c for c in e["criteria"] if c["name"] == "Relevance")
    assert relevance["score"] == 2
    assert "optimizing a PostgreSQL database schema" in relevance["comment"]
    assert e["summary"].startswith(
        "The story was about idempotency in a payments API, but the question asked "
        "about optimizing a PostgreSQL database schema."
    )
    # The rewrite says how to answer the question, not how to retell their story.
    assert e["stronger_version"].startswith(
        "[Answer what the question asks about, optimizing a PostgreSQL database "
        "schema, directly"
    )
    # The narrow check sees the main question and their words, not the follow-ups.
    prompt = next(
        c["prompt"]
        for c in fire.calls
        if "talked about what the question asks about" in c["prompt"]
    )
    assert "It asks about: optimizing a PostgreSQL database schema" in prompt
    assert IDEMPOTENCY in prompt


@pytest.mark.parametrize(
    "reply",
    [
        {"asks_for": "x", "quote": "some changes to the tables", "on_subject": True},
        # A failed check never costs them the question.
        FireError("Fire is down", 502),
    ],
)
def test_general_subject_stands_when_they_talked_about_it(
    client, auth, planned, fire, reply
):
    fire.scores = [_relevant(SCORE)]
    fire.gap_checks = [GENERAL_GAP]
    fire.subject_checks = [reply]
    e = _report_for(client, auth, planned["id"], IDEMPOTENCY)
    assert next(c for c in e["criteria"] if c["name"] == "Relevance")["score"] == 4
    assert e["summary"] == SCORE["summary"]


@pytest.mark.parametrize(
    "check",
    [
        {"points": [], "named_subject": None},
        # A résumé item: decided in code, no extra call (T-114).
        {
            "points": [],
            "named_subject": "building the billing API",
            "story_subject": "x",
        },
        # Only question words are named.
        {"points": [], "named_subject": "a challenging project", "story_subject": "x"},
    ],
)
def test_subject_check_runs_only_for_general_subjects(
    client, auth, planned, fire, check
):
    fire.scores = [_relevant(SCORE)]
    fire.gap_checks = [check]
    _report_for(client, auth, planned["id"], "My answer is about the billing API.")
    assert "subject_check" not in fire.kinds()


def test_naming_the_metric_is_on_subject():
    # T-120 (live): "cutting p95 latency" was asked; "p95 dropped from 1.8 seconds"
    # was flagged off-subject because WORD_RE split p95 into p / 95.
    from app.services.scoring import CriterionScore, GapCheckOut, cap_off_subject

    resume = "Moved reporting to a nightly ETL, cutting p95 latency from 1.8s to 300ms."
    check = GapCheckOut(named_subject="cutting p95 latency", story_subject="queries")

    def criteria():
        return [CriterionScore(name="Relevance", score=4, comment="On topic.")]

    on = criteria()
    said = "I compared outputs for a week; p95 dropped from 1.8 seconds to 300 ms."
    assert cap_off_subject(on, check, [said], resume) is None
    assert on[0].score == 4
    off = criteria()
    other = "I mentored a junior engineer through a migration rollback."
    assert cap_off_subject(off, check, [other], resume) == (
        "cutting p95 latency",
        "queries",
    )
    assert off[0].score == 2


def test_word_endings_and_percentages_count_as_naming_the_subject():
    # T-128: "the retry rate went from 4% to 1%" answers "reducing failed payment
    # retries"; five-letter stems (retry/retri) and single digits kept them apart.
    from app.services.scoring import CriterionScore, GapCheckOut, cap_off_subject

    resume = "Reduced failed payment retries from 4% to 1% with idempotency keys."
    said = "I added backoff, and the retry rate went from 4% to 1%."
    for subject in ("reducing failed payment retries", "payment retries from 4% to 1%"):
        on = [CriterionScore(name="Relevance", score=4)]
        check = GapCheckOut(named_subject=subject, story_subject="x")
        assert cap_off_subject(on, check, [said], resume) is None, subject
        assert on[0].score == 4


def test_off_subject_rewrite_keeps_to_their_story():
    # T-129 (live): the rewrite claimed a role on the named subject and added a
    # résumé result they never tied to the story.
    from app.services.scoring import drop_named_subject, subject_item

    resume = (
        "Acme (2021–now): Built the refunds API; reduced failed payment retries "
        "from 4% to 1% with idempotency keys; mentored two junior engineers."
    )
    said = ["A junior engineer I mentored shipped a migration that locked a table."]
    story = "A junior engineer I mentored shipped a migration that locked a table."
    rewrite = (
        "At Acme, I was responsible for the reliability of the refunds API. "
        f"{story} I also added idempotency keys that reduced payment retries to 1%."
    )
    item = subject_item("building the refunds API", resume)
    assert drop_named_subject(rewrite, item, resume, said) == story
    assert drop_named_subject(story, item, resume, said) == story
    only = "I was responsible for the refunds API."
    assert drop_named_subject(only, item, resume, said) == ""


def test_gap_check_drops_gaps_that_dont_fit_the_question(client, auth, planned, fire):
    # T-108: advice for a different question isn't listed as a missing point.
    sid = planned["id"]
    finished(client, auth, fire, sid)
    fire.gap_checks = [
        {
            "points": [
                {"n": 1, "covered": False, "quote": None, "fits": True},
                {"n": 2, "covered": False, "quote": None, "fits": False},
            ]
        },
        # Never drop every point.
        {"points": [{"n": 1, "covered": False, "quote": None, "fits": False}]},
    ]
    report = build(client, auth, sid).get_json()["report"]
    first, second = (q["evaluation"]["missing_points"] for q in report["questions"])
    assert [p["point"] for p in first] == ["A measurable result"]
    assert len(second) == 1
    gap_prompt = next(
        c["prompt"] for c in fire.calls if "Check which points" in c["prompt"]
    )
    assert '"fits"' in gap_prompt
