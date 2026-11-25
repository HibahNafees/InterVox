"""The only client for the Fire API (transcribe, chat, speech).

The key is read from app config and sent only in the Authorization header; it is
never logged or returned to the browser.
"""

import logging
from dataclasses import dataclass
from typing import Any

import requests
from flask import current_app

log = logging.getLogger(__name__)


class FireError(Exception):
    """A Fire call failed. `message` is safe to show to the user."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class FireResult:
    data: dict[str, Any]
    price_usd: float


@dataclass
class ChatResult:
    content: str
    price_usd: float


class FireClient:
    def __init__(self, api_key: str | None, base_url: str, timeout: float = 60):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.http = requests.Session()

    def _post(self, path: str, payload: dict[str, Any]) -> FireResult:
        if not self.api_key:
            raise FireError("The AI service is not configured on the server", 503)

        last_error: FireError | None = None
        for attempt in (1, 2):  # one retry, on 5xx or network failure only
            try:
                res = self.http.post(
                    f"{self.base_url}{path}",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
            except requests.Timeout:
                last_error = FireError(
                    "The AI service took too long; please try again", 504
                )
                continue
            except requests.RequestException:
                last_error = FireError(
                    "Could not reach the AI service; please try again"
                )
                continue

            if res.status_code >= 500:
                log.warning(
                    "Fire %s returned %s (attempt %d)", path, res.status_code, attempt
                )
                last_error = FireError("The AI service had a problem; please try again")
                continue
            if res.status_code in (401, 403):
                log.error("Fire %s rejected our key (%s)", path, res.status_code)
                raise FireError("The AI service rejected the server's credentials", 503)
            if res.status_code == 402:
                raise FireError("The AI service is out of credit", 503)
            if res.status_code == 429:
                raise FireError("The AI service is busy; please wait a moment", 429)
            if res.status_code >= 400:
                log.warning(
                    "Fire %s returned %s: %s", path, res.status_code, res.text[:300]
                )
                raise FireError("The AI service could not handle this request")

            try:
                data = res.json()
            except ValueError:
                raise FireError("The AI service returned an unreadable response")
            price = ((data.get("meta") or {}).get("price") or {}).get("usd") or 0.0
            return FireResult(data=data, price_usd=float(price))

        assert last_error is not None
        raise last_error

    def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        model: str | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system_prompt"] = system_prompt
        if model:
            payload["species_name"] = model
        result = self._post("/v1/chat", payload)
        content = result.data.get("content")
        if not isinstance(content, str):
            raise FireError("The AI service returned an empty reply")
        return ChatResult(content=content, price_usd=result.price_usd)

    def transcribe(self, audio_data_url: str) -> FireResult:
        return self._post("/v1/transcribe", {"audio": audio_data_url})

    def speech(
        self, text: str, voice: str | None = None, model: str | None = None
    ) -> FireResult:
        payload: dict[str, Any] = {"text": text}
        if model:
            payload["species_name"] = model
        if voice:
            payload["voice"] = voice
        return self._post("/v1/speech", payload)


DEMO_MESSAGE = "This is a demo account: live interviews and AI features are off."


def get_fire() -> FireClient:
    """The app's Fire client. Tests replace app.extensions['fire'] with a fake.

    Demo accounts (T-166) never reach Fire: the demo must cost nothing.
    """
    from .access import current_is_demo

    if current_is_demo():
        raise FireError(DEMO_MESSAGE, 403)
    ext = current_app.extensions
    if "fire" not in ext:
        cfg = current_app.config
        ext["fire"] = FireClient(
            cfg.get("FIRE_API_KEY"), cfg["FIRE_BASE_URL"], cfg["FIRE_TIMEOUT_SEC"]
        )
    return ext["fire"]
