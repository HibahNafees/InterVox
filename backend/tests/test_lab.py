"""Chat Lab: prep chat, debate, compare; 10 calls per user per day, reserved up front."""

from app.extensions import db
from app.models import UsageLimit
from app.services.fire import FireError
from app.services.limits import month_spend_usd, today

CHAT = {"messages": [{"role": "user", "content": "What will they ask me?"}]}
DEBATE = {
    "question": "Tell me about a time you led a project.",
    "answer": "I led the Acme billing API rewrite.",
}
COMPARE = {
    "prompt": "Give me one tip for a STAR answer.",
    "sides": [
        {"model": "gpt-4o-mini", "temperature": 0},
        {"model": "claude-haiku-4-5", "temperature": 1},
    ],
}


def used(app, user_id=1):
    row = db.session.get(UsageLimit, (user_id, today()))
    return row.lab_calls if row else 0


def test_overview_lists_models_defaults_and_usage(client, auth):
    r = client.get("/api/lab", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["usage"] == {"used": 0, "cap": 10}
    d = data["defaults"]
    assert d["model"] == "gpt-4o-mini"
    assert {m["id"] for m in d["models"]} == {"gpt-4o-mini", "claude-haiku-4-5"}
    assert d["agents"]["judge"]["temperature"] == 0
    assert d["agents"]["advocate"]["temperature"] == 1
    assert d["costs"] == {"chat": 1, "compare": 2, "debate": 3}


def test_needs_sign_in(client):
    assert client.post("/api/lab/chat", json=CHAT).status_code == 401


def test_prep_chat_uses_documents_and_always_appends_the_guard(
    client, auth, docs, fire
):
    r = client.post(
        "/api/lab/chat",
        json={
            **CHAT,
            **docs,
            "settings": {
                "agents": {"prep": {"system": "Be a pirate.", "temperature": 0.9}}
            },
        },
        headers=auth,
    )
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["reply"].startswith("Lab reply")
    assert r.get_json()["usage"]["used"] == 1
    call = fire.calls[-1]
    assert call["system"].startswith("Be a pirate.")
    assert "Never invent experience" in call["system"]  # their edit can't drop it
    assert "Acme billing API" in call["system"]  # résumé
    assert "tune MySQL databases" in call["system"]  # job description
    assert call["temperature"] == 0.9
    assert call["model"] == "gpt-4o-mini"
    assert month_spend_usd() > 0


def test_debate_runs_for_against_and_a_cold_judge(client, auth, fire):
    r = client.post("/api/lab/debate", json=DEBATE, headers=auth)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["for"] and data["against"]
    assert data["verdict"]["score"] == 4
    assert data["verdict"]["tip"] == "Add the result you achieved."
    assert data["usage"]["used"] == 3
    temps = [c["temperature"] for c in fire.calls]
    assert temps == [1.0, 1.0, 0.0]
    # The skeptic answers the advocate's case.
    assert data["for"] in fire.calls[1]["prompt"]


def test_compare_sends_one_prompt_to_two_settings(client, auth, fire):
    r = client.post("/api/lab/compare", json=COMPARE, headers=auth)
    assert r.status_code == 200, r.get_json()
    assert len(r.get_json()["answers"]) == 2
    assert [(c["model"], c["temperature"]) for c in fire.calls] == [
        ("gpt-4o-mini", 0),
        ("claude-haiku-4-5", 1),
    ]
    assert r.get_json()["usage"]["used"] == 2


def test_ten_calls_a_day_and_a_debate_that_would_go_over_is_refused_whole(
    app, client, auth, fire
):
    for _ in range(3):  # 9 calls
        assert (
            client.post("/api/lab/debate", json=DEBATE, headers=auth).status_code == 200
        )
    before = len(fire.calls)
    r = client.post("/api/lab/debate", json=DEBATE, headers=auth)
    assert r.status_code == 429
    assert "1 of today's 10 left" in r.get_json()["error"]
    r = client.post("/api/lab/compare", json=COMPARE, headers=auth)
    assert r.status_code == 429
    assert len(fire.calls) == before  # refused before any Fire call
    assert client.post("/api/lab/chat", json=CHAT, headers=auth).status_code == 200
    assert client.post("/api/lab/chat", json=CHAT, headers=auth).status_code == 429
    assert used(app) == 10


def test_cap_is_per_user(client, auth, signup, fire):
    for _ in range(5):
        client.post("/api/lab/compare", json=COMPARE, headers=auth)
    other = signup(email="grace@example.com").get_json()["access_token"]
    r = client.post(
        "/api/lab/chat", json=CHAT, headers={"Authorization": f"Bearer {other}"}
    )
    assert r.status_code == 200
    assert r.get_json()["usage"] == {"used": 1, "cap": 10}


def test_monthly_budget_still_applies(app, client, auth, fire):
    app.config["FIRE_MONTHLY_BUDGET_USD"] = 0
    r = client.post("/api/lab/chat", json=CHAT, headers=auth)
    assert r.status_code == 429
    assert fire.calls == []
    assert used(app) == 0


def test_failed_calls_are_given_back(app, client, auth, fire):
    fire.lab_replies = ["For them.", FireError("The AI service had a problem")]
    r = client.post("/api/lab/debate", json=DEBATE, headers=auth)
    assert r.status_code == 502
    assert used(app) == 1  # only the advocate's call went through


def test_rejects_unknown_models_and_temperatures_over_one(client, auth, fire):
    for settings in (
        {"model": "claude-opus-4-5"},
        {"agents": {"prep": {"temperature": 1.5}}},
        {"agents": {"boss": {"temperature": 0.5}}},
    ):
        r = client.post(
            "/api/lab/chat", json={**CHAT, "settings": settings}, headers=auth
        )
        assert r.status_code == 400, settings
    bad = {**COMPARE, "sides": [{"model": "gpt-4o-mini", "temperature": 2}] * 2}
    assert client.post("/api/lab/compare", json=bad, headers=auth).status_code == 400
    assert fire.calls == []


def test_chat_keeps_only_recent_history_starting_with_the_user(client, auth, fire):
    turns = []
    for i in range(15):
        turns += [
            {"role": "user", "content": f"q{i}"},
            {"role": "assistant", "content": f"a{i}"},
        ]
    turns.append({"role": "user", "content": "last"})
    r = client.post("/api/lab/chat", json={"messages": turns}, headers=auth)
    assert r.status_code == 200
    sent = fire.calls[-1]["messages"]
    assert len(sent) <= 20 and sent[0]["role"] == "user"
    assert sent[-1]["content"] == "last"


def test_chat_must_end_with_the_user(client, auth, fire):
    r = client.post(
        "/api/lab/chat",
        json={"messages": [{"role": "assistant", "content": "Hi"}]},
        headers=auth,
    )
    assert r.status_code == 400
    assert fire.calls == []
