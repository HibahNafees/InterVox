"""Chat Lab: a prep chat, a hiring-manager debate and a side-by-side model compare.

Each agent's system prompt and temperature come from the user's settings (defaults
in prompts/lab_*.txt); prompts/lab_guard.txt is always appended and can't be edited.
Every request reserves its calls (chat 1, compare 2, debate 3) against the daily
LAB_DAILY_CALLS cap before any Fire call. Nothing from the lab is stored.
"""

from typing import Literal

from flask import current_app
from pydantic import BaseModel, Field, model_validator

from .fire import get_fire
from .limits import (
    lab_calls_used,
    record_fire_call,
    release_lab_calls,
    reserve_lab_calls,
)
from .llm import PROMPTS_DIR, chat_json, render

# Fire accepts temperatures 0-1 for every chat model, so 1 is the ceiling for all.
MODELS: dict[str, dict] = {
    "gpt-4o-mini": {"label": "GPT-4o mini (cheapest)", "max_temperature": 1.0},
    "claude-haiku-4-5": {"label": "Claude Haiku 4.5", "max_temperature": 1.0},
}
DEFAULT_MODEL = "gpt-4o-mini"

AGENTS: dict[str, float] = {
    "prep": 0.5,
    "advocate": 1.0,
    "skeptic": 1.0,
    "judge": 0.0,
}
CALLS = {"chat": 1, "compare": 2, "debate": 3}

MAX_SYSTEM_CHARS = 4000
MAX_TEXT_CHARS = 4000
MAX_DOC_CHARS = 6000
MAX_HISTORY = 20
REPLY_TOKENS = 700
ARGUMENT_TOKENS = 400


class LabError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _prompt(name: str) -> str:
    return (PROMPTS_DIR / f"lab_{name}.txt").read_text().strip()


def defaults() -> dict:
    """What Settings' Reset goes back to, plus the model list for the picker."""
    return {
        "model": DEFAULT_MODEL,
        "models": [{"id": k, **v} for k, v in MODELS.items()],
        "agents": {
            name: {"system": _prompt(name), "temperature": temp}
            for name, temp in AGENTS.items()
        },
        "costs": CALLS,
    }


def usage(user_id: int) -> dict:
    return {
        "used": lab_calls_used(user_id),
        "cap": current_app.config["LAB_DAILY_CALLS"],
    }


class AgentSetting(BaseModel):
    system: str | None = Field(default=None, max_length=MAX_SYSTEM_CHARS)
    temperature: float | None = Field(default=None, ge=0)


class Settings(BaseModel):
    model: str = DEFAULT_MODEL
    agents: dict[str, AgentSetting] = Field(default_factory=dict)

    @model_validator(mode="after")
    def known_and_in_range(self) -> "Settings":
        if self.model not in MODELS:
            raise ValueError(f"Unknown model: {self.model}")
        top = MODELS[self.model]["max_temperature"]
        for name, agent in self.agents.items():
            if name not in AGENTS:
                raise ValueError(f"Unknown agent: {name}")
            if agent.temperature is not None and agent.temperature > top:
                raise ValueError(f"Temperature can't be above {top:g} for this model")
        return self

    def system(self, name: str) -> str:
        """The agent's prompt (theirs or the default) with the fixed guard after it."""
        own = (self.agents.get(name) or AgentSetting()).system
        return f"{(own or '').strip() or _prompt(name)}\n\n{_prompt('guard')}"

    def temperature(self, name: str) -> float:
        own = (self.agents.get(name) or AgentSetting()).temperature
        return AGENTS[name] if own is None else own


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class Verdict(BaseModel):
    score: int = Field(ge=1, le=5)
    reasons: list[str] = Field(min_length=1, max_length=4)
    tip: str = Field(min_length=1, max_length=400)


class _Calls:
    """Reserve a request's calls up front; give back any never made."""

    def __init__(self, user_id: int, kind: str):
        self.user_id = user_id
        self.left = CALLS[kind]
        reserve_lab_calls(user_id, self.left)

    def __enter__(self) -> "_Calls":
        return self

    def made(self) -> None:
        self.left -= 1

    def __exit__(self, *exc) -> None:
        release_lab_calls(self.user_id, self.left)


def _chat(
    user_id: int,
    calls: _Calls,
    messages: list[dict],
    system: str,
    temperature: float,
    model: str,
    max_tokens: int,
) -> str:
    result = get_fire().chat(
        messages,
        system_prompt=system,
        max_tokens=max_tokens,
        temperature=temperature,
        model=model,
    )
    record_fire_call(user_id, result.price_usd)
    calls.made()  # a failed call is given back; its spend (if any) still counts
    return result.content.strip()


def prep_chat(
    user_id: int,
    history: list[Turn],
    settings: Settings,
    resume: str | None = None,
    jd: str | None = None,
) -> str:
    """The coach's next reply. The browser keeps the conversation; we keep nothing."""
    if not history or history[-1].role != "user":
        raise LabError("Send a message first")
    history = history[-MAX_HISTORY:]
    if history[0].role != "user":
        history = history[1:]
    system = settings.system("prep")
    for label, text in (("résumé", resume), ("job description", jd)):
        if text:
            system += f"\n\nThe candidate's {label}:\n{text[:MAX_DOC_CHARS]}"
    with _Calls(user_id, "chat") as calls:
        return _chat(
            user_id,
            calls,
            [t.model_dump() for t in history],
            system,
            settings.temperature("prep"),
            settings.model,
            REPLY_TOKENS,
        )


def debate(user_id: int, question: str, answer: str, settings: Settings) -> dict:
    """For, against, then a temperature-0 judge (by default) scores it out of 5."""
    case = render("lab_debate_case", question=question, answer=answer)
    with _Calls(user_id, "debate") as calls:
        advocate = _chat(
            user_id,
            calls,
            [{"role": "user", "content": case}],
            settings.system("advocate"),
            settings.temperature("advocate"),
            settings.model,
            ARGUMENT_TOKENS,
        )
        skeptic = _chat(
            user_id,
            calls,
            [
                {
                    "role": "user",
                    "content": render(
                        "lab_skeptic_case",
                        question=question,
                        answer=answer,
                        advocate=advocate,
                    ),
                }
            ],
            settings.system("skeptic"),
            settings.temperature("skeptic"),
            settings.model,
            ARGUMENT_TOKENS,
        )
        verdict = chat_json(
            user_id,
            render(
                "lab_judge_task",
                question=question,
                answer=answer,
                advocate=advocate,
                skeptic=skeptic,
            ),
            Verdict,
            system=settings.system("judge"),
            max_tokens=ARGUMENT_TOKENS,
            temperature=settings.temperature("judge"),
            model=settings.model,
        )
        calls.made()
    return {"for": advocate, "against": skeptic, "verdict": verdict.model_dump()}


class Side(BaseModel):
    model: str = DEFAULT_MODEL
    temperature: float = Field(default=0.7, ge=0)

    @model_validator(mode="after")
    def known_and_in_range(self) -> "Side":
        if self.model not in MODELS:
            raise ValueError(f"Unknown model: {self.model}")
        top = MODELS[self.model]["max_temperature"]
        if self.temperature > top:
            raise ValueError(f"Temperature can't be above {top:g} for this model")
        return self


def compare(user_id: int, prompt: str, sides: list[Side]) -> list[str]:
    """The same prompt under two settings, answered one after the other."""
    system = f"{_prompt('compare')}\n\n{_prompt('guard')}"
    with _Calls(user_id, "compare") as calls:
        return [
            _chat(
                user_id,
                calls,
                [{"role": "user", "content": prompt}],
                system,
                side.temperature,
                side.model,
                REPLY_TOKENS,
            )
            for side in sides
        ]
