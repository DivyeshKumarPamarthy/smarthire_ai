"""
Module 10 — what the AI provider actually did.

Shaped deliberately after metrics.py, including the lock and the
window-that-starts-at-restart, so the two behave identically and neither
surprises anyone who has read the other.

This exists because /api/health could only ever answer "is the provider
reachable right now". It records nothing, so when a spent Gemini quota stopped
every transcription for a day earlier in this project, the admin dashboard
showed green throughout and the failure surfaced as a candidate's missing
report.

`quota_failures` is counted apart from `failures` for that exact reason: a
spent quota is a self-inflicted, recoverable condition with a known fix, and it
looked identical to a generic outage in every surface that existed before this.

Counting is passive. Nothing here probes the provider — polling it to check it
is alive would spend the very quota this is meant to make visible.
"""

import threading
from datetime import datetime, timezone
from typing import Dict


class AICallStat:
    """Running totals for one operation."""

    __slots__ = ("calls", "failures", "quota_failures", "total_ms")

    def __init__(self) -> None:
        self.calls = 0
        self.failures = 0
        self.quota_failures = 0
        self.total_ms = 0.0


class AIMetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_operation: Dict[str, AICallStat] = {}
        self.window_start = datetime.now(timezone.utc)

    def record(
        self, operation: str, *, ok: bool, quota: bool, duration_ms: float
    ) -> None:
        """
        One provider call's outcome.

        A quota failure is also a failure — it is counted in both, because
        "how much broke" and "how much broke for this recoverable reason" are
        different questions and a reader needs both.
        """
        with self._lock:
            stat = self._by_operation.setdefault(operation, AICallStat())
            stat.calls += 1
            stat.total_ms += duration_ms
            if not ok:
                stat.failures += 1
                if quota:
                    stat.quota_failures += 1

    def snapshot(self) -> dict:
        with self._lock:
            operations = [
                {
                    "operation": name,
                    "calls": stat.calls,
                    "failures": stat.failures,
                    "quota_failures": stat.quota_failures,
                    "failure_rate": (
                        round(stat.failures / stat.calls * 100, 2) if stat.calls else 0.0
                    ),
                    "avg_ms": (
                        round(stat.total_ms / stat.calls, 1) if stat.calls else 0.0
                    ),
                }
                for name, stat in self._by_operation.items()
            ]
            total_ms = sum(s.total_ms for s in self._by_operation.values())
            window_start = self.window_start

        calls = sum(o["calls"] for o in operations)
        failures = sum(o["failures"] for o in operations)
        quota = sum(o["quota_failures"] for o in operations)
        operations.sort(key=lambda o: o["calls"], reverse=True)

        return {
            "window_start": window_start,
            "total_calls": calls,
            "total_failures": failures,
            "failure_rate": round(failures / calls * 100, 2) if calls else 0.0,
            "quota_failures": quota,
            "avg_latency_ms": round(total_ms / calls, 1) if calls else 0.0,
            "operations": operations,
        }

    def reset(self) -> None:
        with self._lock:
            self._by_operation.clear()
            self.window_start = datetime.now(timezone.utc)


ai_metrics = AIMetricsStore()

NOTE = (
    "Counted in this server process since it last restarted — not uptime, and "
    "not a durable history. Quota failures are counted separately because a "
    "spent quota is recoverable and otherwise looks identical to an outage."
)
