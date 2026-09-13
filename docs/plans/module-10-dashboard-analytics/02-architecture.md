# Architecture: Module 10 — Dashboard & Analytics

Gate 1 approved 2026-09-10. `AUDIT.md` is the input to this document: six of
eight candidate bullets, two of seven recruiter bullets and four of five admin
bullets already ship, and none of them are rebuilt here.

## What is reused unchanged

Nothing in this list is modified. It is named so that no slice quietly
duplicates it:

- **`performance_analytics.py`** — `skill_breakdown()`, `performance_trend()`,
  `weak_areas()`, `average_axes()`. Pure arithmetic over stored analyses: no
  DB session, no AI call, 17 unit tests. Already role-agnostic — it takes rows,
  not a user.
- **`report_pdf.build_interview_report()`** — the single PDF pipeline. Module
  10 adds a function beside it; it does not start a second one.
- **`metrics.py` / `GET /api/metrics`** — request counts, error rate, p95/p99.
  The in-memory-and-resets-on-restart pattern here is the model the new AI
  monitoring copies deliberately.
- **`ai_provider.provider_status()`** — point-in-time reachability, still
  reported at `/api/health`. Module 10 adds history alongside it; it does not
  replace or re-implement it.
- **`GET /analytics/leaderboard`**, **`/analytics/live`**, **`/analytics/admin`**,
  **`/analytics/recruiter`**, **`/analytics/recruiter/candidates`**,
  **`/analytics/recruiter/candidates/{id}/interviews`** — every existing route
  keeps its shape. Two are extended additively; none change meaning.
- **`behavior_analysis.recruiter_view()`** — the visibility precedent, and the
  filter that keeps Module 6 out of everything this module ranks by.
- **User management and tickets** — `PUT /users/{id}/block`,
  `PUT /users/{id}/role`, the tickets queue. The admin bullet they satisfy is
  already met.

## What is new

Three service modules and six endpoints. No new model, no new table.

| New | Why it cannot reuse something existing |
|---|---|
| `performance_analytics.axis_progress()` | Existing trend works on `Interview.overall_score`. Tracking a *named axis* needs per-interview axis averages, which no current function produces. |
| `performance_analytics.recruiter_view()` | A filter, mirroring the behaviour-report precedent. Nothing today filters rubric analytics by role. |
| `shortlist_insights.py` | New product. Rule-based and evidence-carrying, modelled on `practice_recommendations.py`. |
| `ai_metrics.py` | `metrics.py` counts HTTP requests, not provider calls, and cannot distinguish a spent quota from a 200. |
| `report_pdf.build_history_report()` | Existing builder takes one interview. A history report spans many. |

## Fit

- **All new computation is pure.** `axis_progress`, `recruiter_view` and the
  shortlist rules take rows and return dictionaries — no DB session, no AI
  call — matching how `performance_analytics.py` and `scoring.py` are already
  built and unit tested. Endpoints do the loading; services do the arithmetic.
- **AI monitoring instruments the facade, not the providers.**
  `ai_provider.py` is already the single chokepoint every AI call passes
  through — six delegating functions. Each records outcome and duration into an
  in-memory store. Instrumenting `gemini.py` and `ollama_provider.py`
  separately would mean two implementations that drift.
- **Counting is passive.** The monitor records what calls actually did. It
  never probes: polling the provider to test it would spend the quota it exists
  to protect. This is Gate 1 decision 5.
- **Recruiter analytics reuse the candidate computation, then filter.** The
  same functions produce the numbers; a filter removes what the role may not
  see. This is what guarantees recruiter and candidate can never see disagreeing
  figures — the guarantee `recruiter_view()` already provides for Module 6.

## Binding decisions added at Gate 2 approval

Same status as the provisional-data flag: not advisory, not a default a slice
may reconsider.

1. **Comparison is never sortable, on any axis.** Candidates appear in the
   order the recruiter selected them. No sort control, no sort parameter, no
   default ordering by score, and nothing in the response a client could use to
   rank. The interface must not perform ranking on a recruiter's behalf —
   sorting four people by a number an AI produced is precisely the act this
   module refuses to automate. Ranking already exists, once, in the leaderboard,
   where it is labelled as such.
2. **Comparison holds two to four candidates.** One is not a comparison and
   would just be the single-candidate view with different framing. Five makes
   the axes unreadable. Both bounds are enforced server-side with a 400, not
   only in the UI.

## Visibility decisions — per field, per role

Gate 1 fixed the rule; this is the field-level application of it. Decided
explicitly, not by default.

### Recruiter view of a candidate's performance

| Field | Recruiter | Reasoning |
|---|---|---|
| `skill_breakdown` — category, overall, axes | **SHOW** | Derived from the rubric score a recruiter already sees on the leaderboard and in the session list. Showing the breakdown of a number they already have reveals nothing new about the person. |
| `answers_graded`, `provisional` | **SHOW — mandatory** | Not optional. Binding per Gate 1: thin evidence must stay visibly thin, and in a side-by-side it is a fairness requirement rather than a courtesy. |
| `performance_trend` — points, average, best, direction | **SHOW** | Every point is a completed interview with a score, both already recruiter-visible. |
| `weak_areas` — `axis_averages`, `weakest_axis`, `weakest_axis_score` | **SHOW** | Arithmetic over scores they can already see. Withholding it would not protect the candidate; it would only make the recruiter compute it by hand. |
| `weak_areas` — `graded_answers`, `method_note` | **SHOW** | The caveat must travel with the number, as it does for Module 6. |
| `practice_recommendations` | **WITHHOLD** | Coaching addressed *to the candidate* — "do 3 mock interviews focused on cutting hedging language". A recruiter reading someone's personal remediation plan turns self-improvement advice into a mark against them. The weakness itself is already shown as a number; the number carries its own uncertainty, a prescription does not. |
| `learning_resources` | **WITHHOLD** | Same reasoning. Also useless to a recruiter — it is a reading list, not evidence. |
| `axis_progress` | **SHOW** | Whether someone is improving is directly relevant and is computed from scores already visible. |
| Anything from Module 6 | **WITHHOLD** | Gate 1, locked. Already filtered into per-session context, which is defensible beside one interview being read. Feeding forgeable, uncalibrated gaze data into a mechanism that sorts people against each other is not. |

### Admin view of AI monitoring

| Field | Admin | Reasoning |
|---|---|---|
| Call counts, failures, failure rate, quota events, latency, per-operation breakdown | **SHOW** | Operational data about the platform, containing nothing about any individual. |
| Candidate identity on a failed call | **WITHHOLD** | An admin debugging a spent quota needs the count and the operation, not whose interview it was. Recording who was affected would make this a log of individuals' sessions for no operational gain. |
| Prompt or transcript content | **WITHHOLD** | Never. Monitoring counts outcomes; it does not retain what was sent. |

### Candidate view

Unchanged and unfiltered — a candidate sees everything about themselves,
including the recommendations withheld from recruiters. The full-history report
is generated for the signed-in owner only.

## Endpoints

**Candidate**
- `GET /analytics/candidate/performance` — **extended**, additive. Gains an
  `axis_progress` key. Existing keys unchanged, so the current component keeps
  working during the slice.
- `GET /notifications/reports/history.pdf` — **new**. The whole scored history
  as one PDF, owner only. Placed beside the existing per-interview report
  because that is where the PDF route already lives; the `/notifications`
  prefix is inherited oddity, not a new decision, and moving it would break a
  working frontend call for no user benefit.

**Recruiter** (all `require_roles(RECRUITER, ADMIN)`, matching every existing
recruiter route)
- `GET /analytics/recruiter/candidates/{user_id}/performance` — **new**. One
  candidate's skills, trend, weak areas and axis progress, filtered.
- `GET /analytics/recruiter/compare?user_ids=1,2,3` — **new**. Two to four
  candidates on the same axes. Rejects one candidate and rejects a fifth with
  400 rather than silently truncating or rendering a "comparison" of one.
  **Returns candidates in the order they were requested, and exposes no sort
  parameter of any kind.**
- `GET /analytics/recruiter/shortlist-insights` — **new**. Candidates worth
  attention, each with the evidence that produced the insight.

**Admin**
- `GET /analytics/admin/ai` — **new**, `require_roles(ADMIN)`. Provider call
  history. Separate from `/api/health` on purpose: health is a cheap liveness
  check hit frequently and must stay light.

## Data

**No new column. No new table. Therefore no migration script.**

Worth stating plainly because the standing rule since Module 9 is that any new
column ships with a committed script in `backend/scripts/`. That rule is not
triggered here:

- Improvement progress, the history report, recruiter analytics and comparison
  are all computed from `InterviewQuestion.analysis` and `Interview.overall_score`,
  which already store everything needed.
- Shortlisting produces *insights*, not a persisted shortlist — Gate 1
  decision 3. A saved shortlist would need a table; deciding nothing needs none.
- AI monitoring is in-memory by decision, mirroring `metrics.py`.

If a later revision adds a persisted shortlist or durable AI history, that
revision writes the migration script. This one does not need to.

### AI metrics shape (in-memory)

```json
{
  "window_start": "2026-09-10T09:00:00Z",
  "total_calls": 412,
  "total_failures": 19,
  "failure_rate": 4.6,
  "quota_failures": 12,
  "avg_latency_ms": 1840.2,
  "operations": [
    {"operation": "speech_to_text", "calls": 208, "failures": 12,
     "quota_failures": 12, "failure_rate": 5.8, "avg_ms": 2600.4}
  ]
}
```

`quota_failures` is counted separately from `failures` because that distinction
is the entire point: a spent quota is a self-inflicted, recoverable condition
with a known fix, and it looked identical to a generic outage in every existing
surface. `window_start` is labelled as beginning at the last restart, never
presented as uptime.

## Flow

**Candidate improvement progress**
1. Endpoint loads the candidate's `(category, analysis)` rows and interviews —
   the same two queries the endpoint already runs.
2. `axis_progress()` groups graded answers by interview, averages each axis per
   interview, orders by completion time, and reports movement on the weakest
   axis only when at least four scored interviews exist — the same floor
   `performance_trend()` already uses for its direction claim.
3. Returned under a new key; the existing component renders a new block.

**Recruiter view of a candidate**
1. Endpoint resolves the candidate, 404s if they are not a candidate — the
   check `/recruiter/candidates/{id}/interviews` already performs.
2. The same `performance_analytics` functions run over that candidate's rows.
3. `recruiter_view()` filters the result per the table above.

**Comparison**
1. Endpoint parses `user_ids`, rejects fewer than two or more than four.
2. Runs the same computation per candidate, filters each, returns them aligned
   on the four rubric axes with `answers_graded` and `provisional` attached to
   every cell.
3. Emits them in the caller's selection order. There is no sort parameter, and
   the response carries no rank, position or ordering hint that a client could
   render as one.

**AI monitoring**
1. Each `ai_provider` delegating function records `(operation, outcome,
   duration)` — outcome distinguishing success, quota failure and other
   failure — into `ai_metrics`.
2. `GET /analytics/admin/ai` returns the snapshot.

## External

None. No new backend dependency, no new frontend dependency, no new
environment variable. Everything is arithmetic over data already stored, plus
counters in memory.

## Consequences worth stating

- **AI monitoring dies with the process.** A restart loses the window, exactly
  as `/api/metrics` already does. Acceptable because the failure this exists to
  catch — a quota spent hours ago and still spent — is visible in any window
  that is currently open. It would not be acceptable for capacity planning or
  an incident post-mortem, and the UI must not imply it serves those.
- **Comparison invites over-reading.** Four candidates on identical axes looks
  like a decision tool. Three mitigations, all binding rather than advisory:
  the provisional flag, so a candidate with one graded answer never renders as
  equivalent to one with twelve; **no sorting on any axis**, so the interface
  never performs ranking on the recruiter's behalf; and **a floor of two**, so
  a single candidate cannot be dressed up as a comparison. A recruiter may
  still form a judgement — that is their job — but they must do the ordering
  themselves rather than be handed one. This is the single highest-risk surface
  in the module.
- **Shortlist insights are rules, not a model.** Deterministic and auditable
  against the numbers that produced them, the same trade `practice_recommendations.py`
  already makes. They will be less nuanced than an LLM's take, and that is the
  point: a recruiter can check a rule.
- **The recruiter filter is a subset, never a recomputation.** If a later change
  makes the recruiter path compute its own numbers, the two views can disagree
  about the same person — the precise failure `recruiter_view()` was written to
  prevent.
- **Every recruiter surface is pool-wide.** No ownership is expressed anywhere,
  because none exists in the schema. Wording follows Module 9's precedent, where
  a test asserts "your candidate" never appears.
