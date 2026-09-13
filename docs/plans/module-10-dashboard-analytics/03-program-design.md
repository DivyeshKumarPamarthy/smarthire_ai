# Program Design: Module 10 — Dashboard & Analytics

Gate 2 approved 2026-09-10, with two binding additions: comparison is never
sortable, and holds two to four candidates. Both are enforced server-side here,
not only in the UI.

## Files

**Backend — new**
- `app/services/shortlist_insights.py` — rule-based insights, each carrying the
  evidence that produced it. Pure: rows in, dictionaries out. Modelled on
  `practice_recommendations.py`, which makes the same deterministic-and-auditable
  trade for the same reason.
- `app/services/ai_metrics.py` — in-memory provider-call counters. Deliberately
  a near-twin of `metrics.py`, including the thread lock and the reset-on-restart
  window, so the two behave identically and neither surprises anyone who has
  read the other.
- `tests/test_axis_progress.py`, `tests/test_shortlist_insights.py`,
  `tests/test_ai_metrics.py`, `tests/test_recruiter_analytics.py` — see the test
  plan.

**Backend — changed, additively**
- `app/services/performance_analytics.py` — add `axis_progress()` and
  `recruiter_view()`. Existing functions untouched; their 17 tests must keep
  passing unmodified, which is the check that this stayed additive.
- `app/services/report_pdf.py` — add `build_history_report()` beside the
  existing builder, reusing `_styles()`, `_kv_table()` and the colour constants.
- `app/services/ai_provider.py` — wrap the six delegating functions so each
  records its outcome. No signature changes; callers are untouched.
- `app/api/analytics.py` — four new routes.
- `app/api/notifications.py` — one new route, the history PDF, beside the
  existing per-interview one.
- `app/schemas/analytics.py` — response shapes for the new routes.

**Frontend — changed**
- `src/components/PerformanceAnalytics.jsx` — one new block for axis progress.
- `src/components/CandidateSessions.jsx` — recruiter skill/trend view.
- `src/components/CandidateCompare.jsx` — **new**, replaces the `NotAvailable`
  placeholder at `#compare`.
- `src/components/ShortlistInsights.jsx` — **new**, a panel on `#candidates`.
- `src/pages/recruiter/RecruiterHome.jsx`, `src/pages/admin/AdminHome.jsx`,
  `src/pages/candidate/CandidateHome.jsx` — wire the above in.
- `src/lib/api.js` — five client methods.

## Types & signatures

```python
# app/services/performance_analytics.py  (additions only)

# Same floor performance_trend() already uses. Named once, referenced by both,
# so the two can never drift into claiming different things about the same
# history.
MIN_INTERVIEWS_FOR_TREND = 4          # existing constant, reused

def axis_progress(rows_by_interview, weakest_axis) -> dict:
    """
    Movement on one named axis across a candidate's scored interviews.

    rows_by_interview: [(interview_id, completed_at, [analysis, ...]), ...]
    Returns {available, axis, points: [{interview_id, completed_at, score}],
             first, latest, change, direction, interviews, reason}

    direction is "insufficient_data" below MIN_INTERVIEWS_FOR_TREND. The
    overall trend already refuses to call two points a trajectory; an axis
    must not be laxer than the score it feeds.
    """

RECRUITER_VISIBLE_PERFORMANCE = (
    "skills", "trend", "axis_progress",
)
RECRUITER_VISIBLE_WEAK_AREA_FIELDS = (
    "available", "reason", "axis_averages", "weakest_axis",
    "weakest_axis_score", "weakest_category", "weakest_category_score",
    "graded_answers", "provisional", "method_note",
)
# Absent by decision, not omission: practice_recommendations and
# learning_resources. Coaching addressed to the candidate; a recruiter reading
# someone's remediation plan turns self-improvement into a mark against them.

def recruiter_view(performance: dict) -> dict:
    """
    Filter a computed performance payload for a recruiter.

    Filters, never recomputes — the same guarantee behavior_analysis.recruiter_view()
    provides, and for the same reason: two code paths computing the same figure
    can disagree about a person.
    """
```

```python
# app/services/shortlist_insights.py

MIN_INTERVIEWS_FOR_INSIGHT = 2      # one interview is an anecdote
STRONG_MARGIN = 10.0                # points above pool average
IMPROVING_MARGIN = 10.0             # points of upward movement

class Insight(TypedDict):
    kind: str        # consistently_strong | improving | strong_in_skill | thin_evidence
    candidate_id: int
    headline: str
    evidence: str    # the numbers that produced it, always populated
    provisional: bool

def pool_baseline(candidates) -> dict:
    """{average, scored_candidates} — what "above average" is measured against."""

def insights_for(candidate_summary, baseline) -> List[Insight]:
    """
    Zero or more insights for one candidate. Never a ranking, never a score,
    never an accept/reject. Each carries `evidence` — an insight whose reason
    cannot be shown is not emitted at all.
    """
```

```python
# app/services/ai_metrics.py   (shaped after metrics.py on purpose)

class AICallStat:
    calls: int
    failures: int
    quota_failures: int
    total_ms: float

class AIMetricsStore:
    window_start: datetime
    def record(self, operation: str, *, ok: bool, quota: bool, duration_ms: float) -> None: ...
    def snapshot(self) -> dict: ...
    def reset(self) -> None: ...

ai_metrics = AIMetricsStore()
```

```python
# app/api/analytics.py  (new routes)

@router.get("/recruiter/candidates/{user_id}/performance",
            response_model=RecruiterCandidatePerformance,
            dependencies=[Depends(require_roles(Role.RECRUITER, Role.ADMIN))])

@router.get("/recruiter/compare", response_model=CandidateComparison,
            dependencies=[Depends(require_roles(Role.RECRUITER, Role.ADMIN))])
def compare_candidates(
    user_ids: str = Query(..., description="2-4 comma-separated candidate ids"),
    ...
)
# No sort parameter exists, and none may be added. Candidates are returned in
# the order supplied. Enforced by test.

@router.get("/recruiter/shortlist-insights", response_model=ShortlistInsights,
            dependencies=[Depends(require_roles(Role.RECRUITER, Role.ADMIN))])

@router.get("/admin/ai", response_model=AIMonitoring,
            dependencies=[Depends(require_roles(Role.ADMIN))])
```

```python
# app/services/report_pdf.py  (addition)

def build_history_report(user, interviews, performance: dict) -> bytes:
    """
    A candidate's whole scored history as one PDF.

    Reuses _styles(), _kv_table() and the colour constants — same visual
    language as the per-interview report, because a candidate holding both
    should recognise them as the same document family.
    """
```

## Call stack

**Candidate axis progress**
1. `GET /analytics/candidate/performance` (existing route) loads the two
   queries it already runs.
2. `weak_areas()` → weakest axis → `axis_progress(rows_by_interview, axis)`.
3. Returned under a new `axis_progress` key; existing keys unchanged, so the
   component keeps rendering through the slice.

**Recruiter view of one candidate**
1. `GET /analytics/recruiter/candidates/{id}/performance` resolves the
   candidate, 404 if not a candidate — the check
   `/recruiter/candidates/{id}/interviews` already performs.
2. Same `performance_analytics` functions over that candidate's rows.
3. `recruiter_view()` filters → response.

**Comparison**
1. `GET /analytics/recruiter/compare?user_ids=…` parses ids, rejects <2 or >4
   with 400.
2. Per candidate: same computation, same filter.
3. Emitted in the order supplied, each cell carrying `answers_graded` and
   `provisional`.

**AI monitoring**
1. Any AI call → `ai_provider.<fn>()` → wrapper times it, classifies the
   outcome (`ok` / `quota` / `failure` — quota detected from `AIQuotaExceeded`,
   which `_classify()` already raises) → `ai_metrics.record()`.
2. `GET /analytics/admin/ai` → `snapshot()`.

## Test plan

`tests/test_axis_progress.py` (pure):
- `test_tracks_the_named_axis_not_the_overall_score` — the whole point: a
  history where overall rises while the named axis is flat must report the axis
  as flat.
- `test_orders_points_oldest_first`
- `test_no_direction_below_four_interviews` — same floor as the overall trend.
- `test_improving_and_declining_are_reported`
- `test_ungraded_answers_are_skipped_not_zeroed`
- `test_unavailable_when_the_axis_was_never_graded`

`tests/test_shortlist_insights.py` (pure):
- `test_every_insight_carries_evidence` — iterate every emitted insight across
  several fixtures and assert `evidence` is non-empty. The Gate 1 rule that an
  insight which cannot show its reason is not shown at all.
- `test_no_insight_from_a_single_interview`
- `test_strong_candidate_is_surfaced_with_the_margin_stated`
- `test_improving_candidate_is_surfaced`
- `test_thin_evidence_is_flagged_not_silently_promoted`
- `test_never_emits_a_rank_or_a_recommendation` — structural: no insight
  contains `rank`, `position`, `best`, `hire` or `reject`.
- `test_empty_pool_produces_no_insights_rather_than_an_error`

`tests/test_ai_metrics.py` (pure):
- `test_quota_failures_are_counted_separately_from_failures` — the distinction
  the whole feature exists for.
- `test_success_rate_and_latency`
- `test_per_operation_breakdown`
- `test_reset_clears_the_window`
- `test_snapshot_of_an_empty_store_is_zeroes_not_a_crash`
- **`test_wrapper_reraises_the_original_exception_unchanged`** — the one test
  in this module that protects something other than monitoring.

  The wrapper sits on the critical path of every AI call, so a bug in it breaks
  transcription and scoring rather than merely losing a counter. This asserts
  that a provider call which raises still raises **the same exception object's
  type and message** to the caller, after `record()` has run.

  Covers at minimum:
  - `AIQuotaExceeded` — must arrive as `AIQuotaExceeded`, not as a generic
    `AIUnavailable` and not swallowed. Module 7's multi-key failover and every
    caller's 429 handling branch on this exact type; degrading it to the base
    class silently disables key rotation.
  - A generic `RuntimeError("boom")` — must arrive as `RuntimeError` with
    message `"boom"` intact, not re-wrapped in an `AIUnavailable`.

  And asserts both halves together, because either alone would pass a broken
  implementation: the failure **is recorded** (`failures` incremented, and
  `quota_failures` too for the quota case) **and** the exception still
  propagates. A wrapper that records and swallows, or one that re-raises
  without recording, fails this test.

  A companion assertion guards the success path for the same reason:
  `test_wrapper_returns_the_providers_value_unchanged` — the wrapper is
  transparent in both directions, returning the provider's exact return value
  rather than a copy or a truthiness check.

`tests/test_recruiter_analytics.py` (HTTP, real server):
- `test_recruiter_can_read_a_candidates_performance`
- `test_practice_recommendations_are_not_in_the_recruiter_payload` — asserts
  the withheld fields are absent. The visibility decision, enforced.
- `test_learning_resources_are_not_in_the_recruiter_payload`
- `test_no_module_6_field_reaches_comparison_or_shortlist`
- `test_candidate_cannot_read_another_candidates_performance` — 403.
- `test_compare_rejects_one_candidate` — 400.
- `test_compare_rejects_five_candidates` — 400.
- `test_compare_preserves_selection_order` — request 3,1,2 → response 3,1,2.
- `test_compare_exposes_no_sort_parameter` — a `sort=` query is ignored, and
  the order is still the selection order. Binding decision, enforced.
- `test_every_comparison_cell_carries_answers_graded_and_provisional`
- `test_admin_ai_endpoint_requires_admin` — recruiter gets 403.

`tests/test_performance_analytics.py` — **unchanged**. Its 17 tests passing
untouched is the evidence that the additions stayed additive.

Frontend: no component test infrastructure exists in this repo, as recorded in
Module 6's Gate 3. Verified by scripted browser walkthrough per slice, the same
method used for Modules 8 and 9.

## Least confident decisions

1. **The shortlist thresholds are guesses.** "10 points above pool average" is
   a plausible-sounding number with nothing behind it, and the current pool
   average of 39.7 is skewed by a long tail of abandoned test interviews. Plan:
   implement the rules with the thresholds as named constants, run them against
   the real pool in the recruiter slice, and tune once there is something to
   look at. Module 6's thresholds needed exactly this treatment and guessing
   them cost a slice.
2. **Whether "consistently strong" is even computable here.** It wants several
   interviews per candidate; most candidates in this database have one or two.
   The rule may fire for almost nobody, which is honest but not useful. If so
   the fallback is fewer insight kinds rather than a lower bar.
3. **Axis progress may be too noisy to be worth showing.** Per-interview axis
   averages come from a handful of answers each, so a single bad answer can
   move an axis several points. The four-interview floor helps; it may not be
   enough. If the line reads as noise on real data, reporting first-versus-latest
   only — with no line — is the honest retreat.
4. **The history PDF's length is unbounded.** A candidate with forty interviews
   generates a long document. Acceptable for now; if it becomes a problem the
   fix is a summary-plus-recent-N rather than pagination controls.
5. **Instrumenting `ai_provider` adds a timing wrapper to every AI call.** The
   overhead is a `perf_counter` pair against calls that take seconds, so it is
   irrelevant in proportion — but it is on the critical path of every
   interview, and a bug in the wrapper would break transcription rather than
   just monitoring. The wrapper must never swallow, re-wrap or alter an
   exception, nor change a return value — pinned by
   `test_wrapper_reraises_the_original_exception_unchanged` and
   `test_wrapper_returns_the_providers_value_unchanged` in the test plan above.
