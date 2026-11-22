"""The interviewer's voice (voice stage 3).

By default the browser speaks each message with its own free voices
(VOICE_PROVIDER=browser) and Flask does nothing. With VOICE_PROVIDER=fire, Flask
asks Fire /v1/speech for each speaker segment and returns the audio in the same
response; interviewer audio is never stored. With VOICE_FIRE_FALLBACK on, a client
that has no speech of its own (the Android app) asks for Fire audio too (T-148).
"""

import logging

from flask import current_app

from ..models import Session
from .fire import FireError, get_fire
from .limits import LimitReached, check_budget, record_fire_call

log = logging.getLogger(__name__)

PROVIDERS = ("browser", "fire")
MIME = {
    "mp3": "audio/mpeg",
    "mpeg": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "webm": "audio/webm",
}


def provider() -> str:
    name = current_app.config.get("VOICE_PROVIDER", "browser")
    return name if name in PROVIDERS else "browser"


def fire_fallback() -> bool:
    """Whether a client without its own speech may ask for Fire audio."""
    return bool(
        current_app.config.get("VOICE_FIRE_FALLBACK")
        and current_app.config.get("FIRE_SPEECH_MODEL")
    )


def info(session: Session) -> dict:
    """What the browser needs to pick and style the voices."""
    return {
        "provider": provider(),
        "persona": session.persona or "neutral",
        "fire_fallback": fire_fallback(),
    }


def synthesize(
    user_id: int, session: Session, segments: list[dict]
) -> list[dict] | None:
    """Fire audio for each segment, or None to let the browser speak the text.

    Only called when the client asked (`speak`); it gets audio with
    VOICE_PROVIDER=fire, or as the fallback for a client that can't speak.

    Voice is a nice-to-have on top of the text reply: an over-budget month or a
    failed speech call never fails the turn.
    """
    if not segments or (provider() != "fire" and not fire_fallback()):
        return None
    try:
        check_budget()
    except LimitReached:
        return None
    voices = current_app.config.get("FIRE_VOICES", {})
    persona = session.persona or "neutral"
    model = current_app.config.get("FIRE_SPEECH_MODEL")
    clips = []
    for seg in segments:
        if seg["who"] == "character":
            voice = voices.get("character")
        else:
            voice = voices.get(f"panel_{seg.get('panelist')}") or voices.get(persona)
        try:
            result = get_fire().speech(seg["text"], voice, model)
        except FireError as err:
            log.warning("Fire speech failed (%s); the browser will speak", err.message)
            return None
        record_fire_call(user_id, result.price_usd)
        audio = result.data.get("audio")
        if not isinstance(audio, str) or not audio:
            log.warning("Fire speech returned no audio; the browser will speak")
            return None
        fmt = str(result.data.get("format") or "mp3").lower()
        mime = MIME.get(fmt, f"audio/{fmt}")
        clips.append({"who": seg["who"], "audio": f"data:{mime};base64,{audio}"})
    return clips
