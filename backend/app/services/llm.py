"""Prompt templates + JSON-validated Fire chat calls."""

import json
import logging
import re
from pathlib import Path
from string import Template
from typing import TypeVar

from flask import current_app
from pydantic import BaseModel, ValidationError

from .fire import FireError, get_fire
from .limits import record_fire_call


class UnusableReply(FireError):
    """Fire answered, but twice not in the required shape. At temperature 0 asking
    again gives the same reply, so callers shouldn't retry forever (T-105)."""


log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")

M = TypeVar("M", bound=BaseModel)


def render(template: str, /, **values: object) -> str:
    """Fill prompts/<template>.txt. Templates use $placeholders so JSON braces are safe.

    `template` is positional-only, so a prompt may use any placeholder name
    (e.g. $name) without clashing with it."""
    text = (PROMPTS_DIR / f"{template}.txt").read_text()
    return Template(text).substitute(
        {
            k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
            for k, v in values.items()
        }
    )


def _parse(content: str, schema: type[M], context: dict | None = None) -> M:
    text = FENCE_RE.sub("", content.strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    return schema.model_validate_json(text, context=context)


def chat_json(
    user_id: int,
    prompt: str,
    schema: type[M],
    system: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.4,
    context: dict | None = None,
    model: str | None = None,
) -> M:
    """Ask Fire chat for JSON matching `schema`; retry once if it's invalid.

    `context` reaches the schema's validators; `model` overrides FIRE_CHAT_MODEL
    (the Chat Lab's model picker). Every call's price is recorded against the user,
    including failed parses.
    """
    fire = get_fire()
    model = model or current_app.config.get("FIRE_CHAT_MODEL")
    messages = [{"role": "user", "content": prompt}]
    for attempt in (1, 2):
        result = fire.chat(
            messages,
            system_prompt=system,
            max_tokens=max_tokens,
            temperature=temperature,
            model=model,
        )
        record_fire_call(user_id, result.price_usd)
        try:
            return _parse(result.content, schema, context)
        except ValidationError as err:
            log.warning(
                "Invalid JSON from Fire for %s (attempt %d)", schema.__name__, attempt
            )
            messages = messages + [
                {"role": "assistant", "content": result.content},
                {
                    "role": "user",
                    "content": "That reply was not valid JSON for the required shape "
                    f"({err.error_count()} problems, first: {err.errors()[0]['msg']}). "
                    "Reply again with only the corrected JSON object.",
                },
            ]
    raise UnusableReply("The AI returned an unusable answer; please try again")
