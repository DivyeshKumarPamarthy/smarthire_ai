"""
The one place the AI vendor is chosen.

Everything else in the app calls `generate_questions` and `extract_resume` and
never imports a vendor SDK. Which implementation runs is a config choice:
AI_PROVIDER=ollama|gemini.

    ollama  local, no API key, no daily quota
    gemini  cloud, needs a key, free-tier daily quota

Text operations follow AI_PROVIDER. Anything that reads the recording itself —
transcription and pronunciation notes (Module 5) — is Gemini-only, because
Ollama serves no speech models and there is no local equivalent to fall back
to. That split is enforced here rather than at the call sites, so no caller has
to know which operations are portable.

There is still no text-to-speech: questions are delivered as text. The only
speech conversion in the platform runs one way, on the candidate's recording.
"""

import logging
import time
from typing import List

from app.core.config import settings
from app.services.ai_metrics import ai_metrics
from app.services.providers import gemini, ollama_provider
from app.services.providers.base import (  # re-exported: callers import these from here
    AINotConfigured,
    AIQuotaExceeded,
    AIUnavailable,
    AIUnreachable,
    AnswerScore,
    CommunicationAssessment,
    GeneratedQuestion,
    GeneratedQuestionSet,
    PronunciationNotes,
    strict_json_schema,
)

logger = logging.getLogger(__name__)

_PROVIDERS = {
    gemini.NAME: gemini,
    ollama_provider.NAME: ollama_provider,
}

__all__ = [
    "AINotConfigured",
    "AIQuotaExceeded",
    "AIUnavailable",
    "AIUnreachable",
    "AnswerScore",
    "CommunicationAssessment",
    "GeneratedQuestion",
    "GeneratedQuestionSet",
    "PronunciationNotes",
    "active_provider",
    "analyse_communication",
    "assess_pronunciation",
    "extract_resume",
    "generate_questions",
    "provider_status",
    "score_answer",
    "speech_to_text",
    "strict_json_schema",
]


def active_provider():
    """The module handling text operations, per AI_PROVIDER."""
    name = (settings.AI_PROVIDER or "").strip().lower()
    provider = _PROVIDERS.get(name)
    if provider is None:
        logger.warning(
            "Unknown AI_PROVIDER %r — falling back to %s. Valid values: %s",
            settings.AI_PROVIDER,
            gemini.NAME,
            ", ".join(_PROVIDERS),
        )
        return gemini
    return provider


def active_model() -> str:
    return (
        settings.OLLAMA_MODEL
        if active_provider() is ollama_provider
        else settings.GEMINI_MODEL
    )


def provider_status() -> dict:
    """
    For /health. Reports which provider is active, its model, and whether it can
    actually be reached — a stopped local server should be obvious here rather
    than surfacing later as a generic 503 on an upload.
    """
    provider = active_provider()
    reachable, detail = provider.is_reachable()
    speech_ok, speech_detail = gemini.is_reachable()
    return {
        "provider": provider.NAME,
        "model": active_model(),
        "reachable": reachable,
        "detail": detail,
        # Reported separately because it can be unavailable while the active
        # text provider is perfectly healthy — the common case when running
        # Ollama locally with no Gemini key. Answers are still recorded then;
        # only the transcript and analysis are missing.
        "speech_provider": gemini.NAME,
        "speech_model": settings.GEMINI_STT_MODEL,
        "speech_available": speech_ok,
        "speech_detail": speech_detail,
        "answer_analysis_enabled": settings.ANALYSE_ANSWERS,
        # Module 6 needs no provider at all — it runs in the candidate's
        # browser — so this flag is reported here purely because /health is
        # where the UI already looks to find out which features are on.
        "behavior_analysis_enabled": settings.ANALYSE_BEHAVIOR,
    }


def _measured(operation: str, call):
    """
    Run one provider call, record what it did, and get out of the way.

    Module 10. This sits on the critical path of every AI call in the platform,
    so it is written to be transparent in both directions:

      An exception propagates unchanged — same type, same message, same
      traceback — after the failure is recorded. Re-wrapping would be worse
      than useless: AIQuotaExceeded specifically must survive, because Module
      7's multi-key failover branches on that exact type and flattening it to
      the base class would silently disable key rotation while every counter
      here stayed perfectly accurate.

      A return value is passed back as-is, not copied or coerced.

    A bug in this wrapper breaks transcription and scoring, not merely
    monitoring, which is why both directions are pinned by tests.
    """
    started = time.perf_counter()
    try:
        result = call()
    except AIQuotaExceeded:
        ai_metrics.record(
            operation, ok=False, quota=True,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        raise
    except Exception:
        ai_metrics.record(
            operation, ok=False, quota=False,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        raise

    ai_metrics.record(
        operation, ok=True, quota=False,
        duration_ms=(time.perf_counter() - started) * 1000,
    )
    return result


def generate_questions(
    *, interview_type: str, domain: str, difficulty: str, count: int
) -> List[GeneratedQuestion]:
    return _measured(
        "generate_questions",
        lambda: active_provider().generate_questions(
            interview_type=interview_type, domain=domain,
            difficulty=difficulty, count=count,
        ),
    )


def extract_resume(resume_text: str):
    return _measured(
        "extract_resume", lambda: active_provider().extract_resume(resume_text)
    )


def analyse_communication(*, question: str, transcript: str) -> CommunicationAssessment:
    """Grammar and communication quality. Text only, so it follows AI_PROVIDER."""
    return _measured(
        "analyse_communication",
        lambda: active_provider().analyse_communication(
            question=question, transcript=transcript
        ),
    )


def score_answer(
    *, question: str, transcript: str, interview_type: str, domain: str, difficulty: str
) -> AnswerScore:
    """Module 5's rubric score for one answer. Text only, so it follows AI_PROVIDER."""
    return _measured(
        "score_answer",
        lambda: active_provider().score_answer(
            question=question,
            transcript=transcript,
            interview_type=interview_type,
            domain=domain,
            difficulty=difficulty,
        ),
    )


# --- speech: always Gemini, whatever AI_PROVIDER says ---------------------
#
# These two read the recording. Ollama has no speech models, so dispatching
# them by AI_PROVIDER would mean "transcription silently stops working when
# you switch to local text generation" — a surprise best avoided by routing
# them explicitly here.
#
# Module 6 (on-camera behaviour) is deliberately NOT here: it runs as an ML
# model in the candidate's browser, so no provider is involved and no video
# is sent anywhere for it. See app.services.behavior_analysis.


def speech_to_text(audio: bytes, mime_type: str = "audio/webm") -> str:
    return _measured(
        "speech_to_text", lambda: gemini.speech_to_text(audio, mime_type=mime_type)
    )


def assess_pronunciation(audio: bytes, mime_type: str = "audio/webm") -> PronunciationNotes:
    return _measured(
        "assess_pronunciation",
        lambda: gemini.assess_pronunciation(audio, mime_type=mime_type),
    )
