"""Interviewer voice (stage 3): speaker segments and the optional Fire speech."""

from app.extensions import db
from app.models import UsageLimit
from app.services.fire import FireError
from app.services.interviewer import ROLEPLAY_EXIT

from tests.test_modules import SALES_ANALYSIS, SALES_PLAN, create
from tests.test_sessions import answer, started

ROLEPLAY, WARM_UP = SALES_PLAN["sections"][1], SALES_PLAN["sections"][0]


def roleplay_first(client, auth, docs, fire):
    fire.analysis = SALES_ANALYSIS
    fire.plan = {**SALES_PLAN, "sections": [ROLEPLAY, WARM_UP]}
    return create(client, auth, docs).get_json()["session"]["id"]


def use_fire_voice(app, **voices):
    app.config["VOICE_PROVIDER"] = "fire"
    app.config["FIRE_VOICES"] = voices


def test_browser_voice_is_the_default_and_never_calls_fire(
    app, client, auth, planned, fire
):
    app.config["VOICE_FIRE_FALLBACK"] = False
    sid = planned["id"]
    res = client.post(f"/api/sessions/{sid}/start", json={"speak": True}, headers=auth)
    body = res.get_json()
    assert body["speech"] is None
    assert body["session"]["voice"] == {
        "provider": "browser",
        "persona": "friendly",
        "fire_fallback": False,
    }
    first = body["session"]["transcript"][0]
    assert first["segments"] == [{"who": "interviewer", "text": first["interviewer"]}]

    r = client.post(
        f"/api/sessions/{sid}/turns",
        json={"text": "I led it.", "speak": True},
        headers=auth,
    )
    assert r.get_json()["speech"] is None
    assert fire.spoken == []


def test_roleplay_lines_are_the_characters_and_app_lines_the_interviewers(
    client, auth, docs, fire
):
    sid = roleplay_first(client, auth, docs, fire)
    segments = started(client, auth, sid)["transcript"][0]["segments"]
    assert [s["who"] for s in segments] == ["interviewer", "character"]
    assert "Let's switch to a role-play." in segments[0]["text"]
    assert segments[1]["text"] == ROLEPLAY["questions"][0]

    fire.turns = [{"action": "follow_up", "message": "Who else uses it?"}]
    turn = answer(client, auth, sid, "Teams like yours.").get_json()["turn"]
    assert turn["segments"] == [{"who": "character", "text": "Who else uses it?"}]

    fire.turns = [{"goal_reached": True, "action": "follow_up", "message": "Deal."}]
    r = answer(client, auth, sid, "Thursday with your finance lead?").get_json()
    assert r["turn"]["segments"] == [
        {"who": "character", "text": "Deal."},
        {"who": "interviewer", "text": f"{ROLEPLAY_EXIT} {WARM_UP['questions'][0]}"},
    ]
    # Saved with the question, so a reload (or "Repeat") voices it the same way.
    assert r["session"]["transcript"][-1]["segments"] == r["turn"]["segments"]


def test_fire_voice_speaks_each_segment_with_its_voice_and_counts_spend(
    app, client, auth, docs, fire
):
    use_fire_voice(app, neutral="v-interviewer", character="v-dana")
    sid = roleplay_first(client, auth, docs, fire)
    res = client.post(f"/api/sessions/{sid}/start", json={"speak": True}, headers=auth)
    speech = res.get_json()["speech"]
    assert [c["who"] for c in speech] == ["interviewer", "character"]
    assert speech[0]["audio"] == "data:audio/mpeg;base64,QUJD"
    assert [v for _, v in fire.spoken] == ["v-interviewer", "v-dana"]
    # The cheap speech model is pinned, not left to Fire's default.
    assert fire.speech_models == ["tts-kokoro", "tts-kokoro"]
    assert db.session.scalar(db.select(UsageLimit.fire_spend_usd)) > 0


def test_fire_voice_only_when_asked(app, client, auth, docs, fire):
    use_fire_voice(app)
    sid = roleplay_first(client, auth, docs, fire)
    started(client, auth, sid)
    fire.turns = [{"action": "follow_up", "message": "Why?"}]
    assert answer(client, auth, sid).get_json()["speech"] is None
    assert fire.spoken == []


def test_failed_speech_still_returns_the_text_reply(app, client, auth, docs, fire):
    use_fire_voice(app)
    sid = roleplay_first(client, auth, docs, fire)
    started(client, auth, sid)
    fire.speech_error = FireError("No speech model")
    fire.turns = [{"action": "follow_up", "message": "Why?"}]
    r = client.post(
        f"/api/sessions/{sid}/turns", json={"text": "Hi.", "speak": True}, headers=auth
    )
    assert r.status_code == 200
    assert r.get_json()["speech"] is None
    assert r.get_json()["turn"]["message"] == "Why?"


def test_no_fire_speech_once_the_monthly_budget_is_used(app, client, auth, docs, fire):
    use_fire_voice(app)
    sid = roleplay_first(client, auth, docs, fire)
    started(client, auth, sid)
    app.config["FIRE_MONTHLY_BUDGET_USD"] = 0
    fire.turns = [{"action": "follow_up", "message": "Why?"}]
    r = client.post(
        f"/api/sessions/{sid}/turns", json={"text": "Hi.", "speak": True}, headers=auth
    )
    assert r.get_json()["speech"] is None
    assert fire.spoken == []


def test_fire_fallback_speaks_for_a_client_without_speech(
    app, client, auth, planned, fire
):
    """T-148: the Android app has no browser voice, so it asks for Fire audio."""
    sid = planned["id"]
    res = client.post(f"/api/sessions/{sid}/start", json={"speak": True}, headers=auth)
    body = res.get_json()
    assert body["session"]["voice"]["provider"] == "browser"
    assert body["session"]["voice"]["fire_fallback"] is True
    assert body["speech"][0]["audio"].startswith("data:audio/mpeg;base64,")
    assert fire.speech_models == ["tts-kokoro"]
    assert db.session.scalar(db.select(UsageLimit.fire_spend_usd)) > 0


def test_fire_fallback_still_only_when_asked(app, client, auth, planned, fire):
    sid = planned["id"]
    assert started(client, auth, sid)
    assert answer(client, auth, sid).get_json()["speech"] is None
    assert fire.spoken == []


def test_fire_fallback_off_or_without_a_speech_model(app, client, auth, planned, fire):
    app.config["FIRE_SPEECH_MODEL"] = ""
    sid = planned["id"]
    res = client.post(f"/api/sessions/{sid}/start", json={"speak": True}, headers=auth)
    body = res.get_json()
    assert body["session"]["voice"]["fire_fallback"] is False
    assert body["speech"] is None
    assert fire.spoken == []


def voice_replies_used() -> int:
    return db.session.scalar(db.select(UsageLimit.voice_replies)) or 0


def test_daily_voice_cap_turns_replies_text_only(app, client, auth, planned, fire):
    """T-154: after DAILY_VOICE_REPLIES Fire-voiced replies, the rest are text."""
    app.config["DAILY_VOICE_REPLIES"] = 2
    sid = planned["id"]
    res = client.post(f"/api/sessions/{sid}/start", json={"speak": True}, headers=auth)
    assert res.get_json()["speech"] and res.get_json()["voice_capped"] is False
    fire.turns = [
        {"action": "follow_up", "message": "Why?"},
        {"action": "follow_up", "message": "And then?"},
    ]
    say = {"text": "I led it.", "speak": True}
    second = client.post(f"/api/sessions/{sid}/turns", json=say, headers=auth)
    assert second.get_json()["speech"] and second.get_json()["voice_capped"] is False
    assert voice_replies_used() == 2
    spoken = len(fire.spoken)

    third = client.post(f"/api/sessions/{sid}/turns", json=say, headers=auth)
    body = third.get_json()
    assert third.status_code == 200
    assert body["turn"]["message"] == "And then?"  # the text reply still comes
    assert body["speech"] is None and body["voice_capped"] is True
    assert len(fire.spoken) == spoken  # no Fire speech call once capped
    assert voice_replies_used() == 2


def test_failed_speech_gives_the_voice_reply_back(app, client, auth, planned, fire):
    sid = planned["id"]
    fire.speech_error = FireError("No speech model")
    res = client.post(f"/api/sessions/{sid}/start", json={"speak": True}, headers=auth)
    assert res.get_json()["speech"] is None
    assert res.get_json()["voice_capped"] is False
    assert voice_replies_used() == 0


def test_text_only_turns_do_not_use_voice_replies(app, client, auth, planned, fire):
    sid = planned["id"]
    assert started(client, auth, sid)
    assert answer(client, auth, sid).get_json()["voice_capped"] is False
    assert voice_replies_used() == 0
