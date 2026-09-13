"""
Module 10, Slice 6 — provider-call counters, and the wrapper around them.

Most of this file guards monitoring. Two tests guard something else entirely:
the wrapper sits on the critical path of every AI call in the platform, so a
bug in it breaks transcription and scoring rather than merely losing a counter.
Those two are the reason this file matters.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import ai_provider  # noqa: E402
from app.services.ai_metrics import AIMetricsStore  # noqa: E402
from app.services.providers.base import AIQuotaExceeded, AIUnavailable  # noqa: E402


@pytest.fixture
def store(monkeypatch):
    """A clean store, swapped in for the module-level one."""
    fresh = AIMetricsStore()
    monkeypatch.setattr(ai_provider, "ai_metrics", fresh)
    return fresh


class TestCounters:
    def test_quota_failures_are_counted_separately_from_failures(self):
        """
        The distinction the whole feature exists for. A spent quota is
        recoverable and has a known fix; before this it looked identical to an
        outage in every surface.
        """
        s = AIMetricsStore()
        s.record("speech_to_text", ok=False, quota=True, duration_ms=10)
        s.record("speech_to_text", ok=False, quota=False, duration_ms=10)
        snap = s.snapshot()
        assert snap["total_failures"] == 2
        assert snap["quota_failures"] == 1

    def test_success_rate_and_latency(self):
        s = AIMetricsStore()
        s.record("score_answer", ok=True, quota=False, duration_ms=100)
        s.record("score_answer", ok=True, quota=False, duration_ms=300)
        s.record("score_answer", ok=False, quota=False, duration_ms=200)
        snap = s.snapshot()
        assert snap["total_calls"] == 3
        assert snap["failure_rate"] == pytest.approx(33.33, abs=0.01)
        assert snap["avg_latency_ms"] == 200.0

    def test_per_operation_breakdown(self):
        s = AIMetricsStore()
        s.record("speech_to_text", ok=True, quota=False, duration_ms=50)
        s.record("score_answer", ok=False, quota=True, duration_ms=50)
        by_op = {o["operation"]: o for o in s.snapshot()["operations"]}
        assert by_op["speech_to_text"]["failures"] == 0
        assert by_op["score_answer"]["quota_failures"] == 1

    def test_reset_clears_the_window(self):
        s = AIMetricsStore()
        s.record("x", ok=True, quota=False, duration_ms=1)
        before = s.window_start
        s.reset()
        assert s.snapshot()["total_calls"] == 0
        assert s.window_start >= before

    def test_snapshot_of_an_empty_store_is_zeroes_not_a_crash(self):
        snap = AIMetricsStore().snapshot()
        assert snap["total_calls"] == 0
        assert snap["failure_rate"] == 0.0
        assert snap["avg_latency_ms"] == 0.0
        assert snap["operations"] == []


class TestWrapperTransparency:
    """
    The wrapper must be invisible to callers in both directions.

    A failure here does not lose a statistic — it breaks every interview.
    """

    def test_wrapper_reraises_the_original_exception_unchanged(self, store):
        """
        Both halves asserted together, because either alone passes a broken
        implementation: a wrapper that records then swallows would pass a
        propagation-only test, and one that re-raises without recording would
        pass a counting-only test.
        """
        # --- a spent quota ---
        quota_error = AIQuotaExceeded("429 RESOURCE_EXHAUSTED")

        def raises_quota():
            raise quota_error

        with pytest.raises(AIQuotaExceeded) as caught:
            ai_provider._measured("speech_to_text", raises_quota)

        # The exact type, not degraded to the base class. Module 7's multi-key
        # failover branches on AIQuotaExceeded specifically; flattening it to
        # AIUnavailable would silently disable key rotation while every counter
        # in this file stayed perfectly accurate.
        assert type(caught.value) is AIQuotaExceeded
        assert caught.value is quota_error
        assert "429 RESOURCE_EXHAUSTED" in str(caught.value)

        snap = store.snapshot()
        assert snap["total_failures"] == 1
        assert snap["quota_failures"] == 1

        # --- a generic failure ---
        boom = RuntimeError("boom")

        def raises_generic():
            raise boom

        with pytest.raises(RuntimeError) as caught:
            ai_provider._measured("score_answer", raises_generic)

        assert type(caught.value) is RuntimeError
        assert caught.value is boom
        assert str(caught.value) == "boom"
        # Not re-wrapped into the provider's own exception family.
        assert not isinstance(caught.value, AIUnavailable)

        snap = store.snapshot()
        assert snap["total_failures"] == 2
        assert snap["quota_failures"] == 1  # unchanged: the second was not quota

    def test_wrapper_returns_the_providers_value_unchanged(self, store):
        """
        Transparent in the success direction too. A wrapper returning a truthy
        proxy instead of the provider's actual value would break every caller
        while leaving the counters immaculate.
        """
        sentinel = {"transcript": "the exact object the provider returned"}
        assert ai_provider._measured("speech_to_text", lambda: sentinel) is sentinel

        for value in (None, "", 0, False, []):
            assert ai_provider._measured("x", lambda v=value: v) is value

        assert store.snapshot()["total_calls"] == 6
        assert store.snapshot()["total_failures"] == 0
