import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before the Config class reads os.environ below.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    CORS_ORIGINS = [
        o.strip()
        for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ]
    FIRE_API_KEY = os.environ.get("FIRE_API_KEY")
    FIRE_BASE_URL = os.environ.get("FIRE_BASE_URL", "https://fire.prosaga.net")
    FIRE_MONTHLY_BUDGET_USD = float(os.environ.get("FIRE_MONTHLY_BUDGET_USD", "1"))
    # Cheap model by default: the whole app runs on a $1/month Fire budget.
    FIRE_CHAT_MODEL = os.environ.get("FIRE_CHAT_MODEL", "gpt-4o-mini")
    FIRE_TIMEOUT_SEC = float(os.environ.get("FIRE_TIMEOUT_SEC", "60"))
    # Open with a short small-talk question before the plan (never scored).
    ICEBREAKER = os.environ.get("ICEBREAKER", "1") == "1"
    # End with "Do you have any questions for me?" (answered, never scored).
    CANDIDATE_QUESTIONS = os.environ.get("CANDIDATE_QUESTIONS", "1") == "1"
    # Interviewer voice: "browser" (free Web Speech API in the browser) or "fire"
    # (Fire /v1/speech, billed per turn).
    VOICE_PROVIDER = os.environ.get("VOICE_PROVIDER", "browser")
    # With the browser voice, a client that can't speak (the Android app's WebView
    # has no Web Speech synthesis) may still ask for Fire audio (T-148). Same budget
    # guard as VOICE_PROVIDER=fire; set to 0 to keep those clients text-only.
    VOICE_FIRE_FALLBACK = os.environ.get("VOICE_FIRE_FALLBACK", "1") == "1"
    # Pinned so a change to Fire's default speech model can't raise the cost;
    # Kokoro is Fire's cheapest one.
    FIRE_SPEECH_MODEL = os.environ.get("FIRE_SPEECH_MODEL", "tts-kokoro")
    # Fire voice ids by speaker: "friendly", "neutral", "tough", "character", and
    # the panel interviewers "panel_hm", "panel_peer", "panel_hr".
    # Unset ones use the speech model's default voice.
    FIRE_VOICES = {
        k: os.environ[f"FIRE_VOICE_{k.upper()}"]
        for k in (
            "friendly",
            "neutral",
            "tough",
            "character",
            "panel_hm",
            "panel_peer",
            "panel_hr",
        )
        if os.environ.get(f"FIRE_VOICE_{k.upper()}")
    }
    # Who can open the admin usage page (comma-separated emails).
    ADMIN_EMAILS = {
        e.strip().lower()
        for e in os.environ.get("ADMIN_EMAILS", "").split(",")
        if e.strip()
    }
    # Per-user daily caps (usage_limits).
    DAILY_INTERVIEW_MINUTES = int(os.environ.get("DAILY_INTERVIEW_MINUTES", "60"))
    DAILY_LONG_SESSIONS = int(os.environ.get("DAILY_LONG_SESSIONS", "1"))
    DAILY_PLANS = int(os.environ.get("DAILY_PLANS", "10"))
    DAILY_RETRIES = int(os.environ.get("DAILY_RETRIES", "20"))
    DAILY_DECODER_RUNS = int(os.environ.get("DAILY_DECODER_RUNS", "5"))
    # Chat Lab calls per user per day: a chat costs 1, a compare 2, a debate 3.
    LAB_DAILY_CALLS = int(os.environ.get("LAB_DAILY_CALLS", "10"))
    # Signed-out decoder use: per visitor (IP) and across all visitors, per day.
    ANON_DECODER_RUNS = int(os.environ.get("ANON_DECODER_RUNS", "3"))
    ANON_DECODER_DAILY = int(os.environ.get("ANON_DECODER_DAILY", "30"))
    # Tests build reports in the request instead of a background thread.
    REPORTS_INLINE = False
    MAX_UPLOAD_BYTES = 5 * 1024 * 1024
    # A 5-minute answer at the browser's 32 kbps is ~1.2 MB; Fire accepts ~25 MB.
    MAX_AUDIO_BYTES = 10 * 1024 * 1024
    MAX_CONTENT_LENGTH = 11 * 1024 * 1024
    # Login/signup brute-force limits (services/ratelimit.py).
    RATE_LIMITS = os.environ.get("RATE_LIMITS", "1") == "1"
    # Behind Caddy: trust one proxy hop for the client address (X-Forwarded-For),
    # used by rate limits and the signed-out decoder cap.
    TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") == "1"
    # "production" refuses to start with weak or missing secrets.
    APP_ENV = os.environ.get("APP_ENV", "development")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret-that-is-long-enough-for-hs256"
    ADMIN_EMAILS = {"admin@example.com"}
    RATE_LIMITS = False  # tests sign up many users from one address
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS: dict = {}
    FIRE_API_KEY = None
    # Pinned: a raised budget in the dev .env must not change the tests (T-115).
    FIRE_MONTHLY_BUDGET_USD = 1.0
    REPORTS_INLINE = True
    # Most tests start straight at the first planned question.
    ICEBREAKER = False
    CANDIDATE_QUESTIONS = False
