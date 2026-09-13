from typing import List

from typing_extensions import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "SmartHire AI API"
    API_PREFIX: str = "/api"

    # PostgreSQL. Falls back to a local SQLite file so the app still boots
    # before Postgres is configured.
    DATABASE_URL: str = "sqlite:///./smarthire.db"

    # Which deployment this is. Only "development" tolerates the insecure
    # defaults below; anything else refuses to start without real secrets.
    ENVIRONMENT: str = "development"

    # The default is deliberately a recognisable non-secret rather than a
    # random value generated at import. A random per-process default would
    # "work" in production while silently invalidating every token on each
    # restart, which is a far worse failure than refusing to boot.
    #
    # ENVIRONMENT=production makes this a hard startup error — see
    # _assert_production_secrets below. Generate one with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    JWT_SECRET_KEY: str = "insecure-dev-key-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/auth/github/callback"

    # Which provider handles question generation and résumé extraction.
    #   ollama  local, no key, no quota
    #   gemini  cloud, needs a key, free-tier daily quota
    # There is no speech provider: the interviewer stores the candidate's
    # recording as-is and does not transcribe or synthesise anything.
    AI_PROVIDER: str = "gemini"

    # --- local Ollama ---
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    # A 7B model on CPU can take well over a minute for a long résumé.
    OLLAMA_TIMEOUT_SECONDS: int = 300
    # How long Ollama keeps the model resident in RAM after a request. Ollama's
    # own default is 5 minutes, after which the next request pays a ~40s reload.
    # A longer window keeps a demo responsive at the cost of holding the RAM.
    OLLAMA_KEEP_ALIVE: str = "30m"

    # --- Google Gemini ---
    GEMINI_API_KEY: str = ""

    # Additional keys, comma-separated, tried in order when the one before them
    # is out of quota. Module 5 spends one request per answer against a free
    # tier measured in tens per day, and there is no local speech model to fall
    # back on, so a single key puts a hard ceiling on how many interviews can
    # be transcribed in a day.
    #
    # These must be keys you are entitled to use — a second project spun up
    # purely to multiply the free allowance is against Google's terms, and the
    # supported ways to raise the ceiling are billing on the project or
    # ANALYSE_ANSWERS=false to run interviews without transcription.
    GEMINI_API_KEYS: str = ""

    # Used for question generation AND résumé extraction. A "lite" model is
    # chosen for its larger free-tier daily request allowance — the heavier
    # Flash models exhaust in the low tens of requests per day, which a single
    # demo can burn through.
    #
    # NOTE: free-tier quotas and model availability shift without warning, and
    # models get retired for new projects. Verify the real per-project limit for
    # whatever model is set here in Google AI Studio → Rate limits, rather than
    # trusting any number written in this repo.
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"

    # Module 5. Transcription and the pronunciation notes both read the
    # recording itself, which needs native audio understanding — deliberately
    # NOT a "lite" model, as the lite tiers do not reliably accept audio.
    #
    # This is a per-answer call, so an 8-question interview is 8 requests
    # against the Gemini free tier even when AI_PROVIDER=ollama is handling
    # every text operation. Ollama has no speech models, so there is no local
    # alternative; set ANALYSE_ANSWERS=false to run interviews without it.
    GEMINI_STT_MODEL: str = "gemini-3.6-flash"

    # --- Module 9: outgoing email ---
    # Nothing is sent until SMTP_HOST is set. That is deliberate rather than a
    # placeholder: a half-configured mailer that raises on every interview
    # completion would take down the thing it was meant to report on, so an
    # unconfigured mailer logs what it would have sent and returns cleanly.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    # The From: address. Falls back to SMTP_USER, which is what most providers
    # require the sender to be anyway.
    SMTP_FROM: str = ""
    # STARTTLS on the standard submission port. Set false only for a local
    # test server such as `python -m smtpd`.
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT_SECONDS: int = 20

    # Master switch for Module 5. Off means answers are recorded and stored
    # exactly as before, with no transcription and no analysis — useful when
    # the Gemini quota is spent and an interview still has to run.
    ANALYSE_ANSWERS: bool = True

    # Master switch for Module 6 (on-camera behaviour). Unlike the switch
    # above this costs no quota — the tracking is an ML model in the
    # candidate's browser — but it is still worth being able to turn off: it
    # spends the candidate's CPU alongside an active recording, and an
    # operator may simply not want gaze tracking in their deployment.
    # Off means no tracking runs and behavior_report stays null.
    ANALYSE_BEHAVIOR: bool = True

    # Résumé upload (Module 2). Files are stored on disk under this directory;
    # the size cap is enforced server-side, not just in the browser.
    RESUME_UPLOAD_DIR: str = "uploads/resumes"
    MAX_RESUME_MB: int = 5

    # Recorded interview answers (Module 3, feature 9). Same arrangement as
    # résumés: bytes on disk, a row in the database pointing at them.
    ANSWER_AUDIO_DIR: str = "uploads/answers"
    MAX_ANSWER_AUDIO_MB: int = 8

    # Session webcam video. Same arrangement again — bytes on disk, a row
    # pointing at them — but the cap is much larger because video is:
    # a ten-minute WebM session runs to tens of megabytes where the audio for
    # the same interview is a couple.
    #
    # This is a person's face, kept on disk. Only the candidate who recorded it
    # can fetch it back (see the recording endpoints), and every playback is
    # written to recording_accesses.
    VIDEO_RECORDING_DIR: str = "uploads/recordings"
    MAX_VIDEO_RECORDING_MB: int = 200

    FRONTEND_URL: str = "http://localhost:5455"
    # Annotated with NoDecode so pydantic-settings does NOT try to JSON-decode
    # the environment value. Without it the env source calls json.loads() on
    # the raw string and raises SettingsError before any field validator runs —
    # which is why a validator alone does not fix this, and why the obvious
    # dashboard value of `https://smarthire-web.onrender.com` crashed the app
    # at startup. NoDecode hands the raw string to _parse_origins below.
    BACKEND_CORS_ORIGINS: Annotated[List[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5453",
        "http://localhost:5455"
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_origins(cls, value):
        """
        Accept a JSON array, a comma-separated string, or a single bare URL.

        pydantic-settings parses a List[str] field from the environment as
        JSON, so a hosting dashboard set to
        `https://smarthire-web.onrender.com` — the obvious thing to type —
        makes the application fail to start with

            SettingsError: error parsing value for field "BACKEND_CORS_ORIGINS"

        Fixed here rather than by contorting the value in the dashboard into
        `["https://..."]`, because that shape is unobvious, easy to get wrong
        under quoting rules that differ between hosts, and would have to be
        remembered every time the variable is set anywhere.

        mode="before" so this runs on the raw environment string, ahead of the
        JSON parsing that would otherwise reject it.
        """
        if not isinstance(value, str):
            # Already a list — the default, or a .env file parsed as TOML/JSON.
            return value

        text = value.strip()
        if not text:
            return []

        # A JSON array is still valid input and stays supported: anything
        # already setting this the documented way keeps working.
        if text.startswith("["):
            import json

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                pass
            else:
                return [str(item).strip() for item in parsed if str(item).strip()]

        # Otherwise treat it as comma-separated. A single URL with no commas
        # is just the one-element case and needs no special handling.
        return [part.strip() for part in text.split(",") if part.strip()]

    @property
    def google_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    @property
    def github_enabled(self) -> bool:
        return bool(self.GITHUB_CLIENT_ID and self.GITHUB_CLIENT_SECRET)

    @property
    def email_enabled(self) -> bool:
        """True once there is a host to talk to. See SMTP_HOST above."""
        return bool(self.SMTP_HOST)

    @property
    def email_from(self) -> str:
        return self.SMTP_FROM or self.SMTP_USER

    @property
    def gemini_api_keys(self) -> list[str]:
        """
        Every configured key, in the order they should be tried.

        GEMINI_API_KEY stays first so existing single-key setups behave exactly
        as before. Deduplicated because the same key listed twice would be
        retried against a quota it has already exhausted, turning one failure
        into two slow ones.
        """
        keys: list[str] = []
        for raw in [self.GEMINI_API_KEY, *self.GEMINI_API_KEYS.split(",")]:
            key = raw.strip()
            if key and key not in keys:
                keys.append(key)
        return keys

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_keys)


INSECURE_JWT_DEFAULT = "insecure-dev-key-change-me"


def _assert_production_secrets(config: "Settings") -> None:
    """
    Refuse to start a production deployment on development secrets.

    A forgotten environment variable is the realistic way this platform ends up
    signing tokens with a key that is committed in the repository for anyone to
    read — and it fails silently, because the app works perfectly with a known
    key. Anyone able to read config.py could then mint a token for any account,
    including an administrator.

    So it is a startup error rather than a warning. A deployment that will not
    boot gets fixed in minutes; a warning in a log nobody reads does not.
    """
    if config.ENVIRONMENT.strip().lower() == "development":
        return

    problems = []
    if config.JWT_SECRET_KEY == INSECURE_JWT_DEFAULT:
        problems.append(
            "JWT_SECRET_KEY is still the development default. Generate one "
            'with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )

    if problems:
        raise RuntimeError(
            f"Refusing to start with ENVIRONMENT={config.ENVIRONMENT!r}:\n  - "
            + "\n  - ".join(problems)
        )


settings = Settings()
_assert_production_secrets(settings)
