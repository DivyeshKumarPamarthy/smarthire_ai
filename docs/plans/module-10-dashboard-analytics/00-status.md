# Status: Module 10 — Dashboard & Analytics

- Audit — existing coverage: DONE 2026-09-10, see `AUDIT.md`
  (run *before* Gate 1 rather than merely before Gate 2 — what already ships
  changes what the product problem is, and it did: six of eight candidate
  bullets turned out to be built already)
- Gate 1 — Product: APPROVED 2026-09-10
- Gate 2 — Architecture: APPROVED 2026-09-10
- Gate 3 — Program Design: APPROVED 2026-09-10
- Gate 4 — Slice plan: APPROVED 2026-09-10

**MODULE 10 IS COMPLETE.** All six slices built and verified. Full suite green.
Read "Not fully confident" at the foot before treating anything here as
finished-and-forgotten.

## Standing conventions confirmed at Gate 1

- **`01-product.md` stays free of technical vocabulary** — no file names,
  endpoints, function names or role checks. Ten such references were removed at
  approval time. Implementation specifics belong in `AUDIT.md` and the gate
  documents from Gate 2 onward.
- **The provisional-data flag is binding in the comparison view**, not
  advisory. Fewer than three graded answers in a category is a courtesy on a
  candidate's own dashboard; shown side by side against another person it is a
  fairness requirement.

## Binding decisions confirmed at Gate 2

- **Comparison is never sortable by score, on any axis.** Selection order only.
  No sort control, no sort parameter, no score-ordered default. The interface
  must not rank people on the recruiter's behalf; ranking exists once, in the
  leaderboard, labelled as such.
- **Comparison holds two to four candidates**, enforced server-side. One is not
  a comparison; five makes the axes unreadable.

## Binding decisions confirmed at Gate 3

- **The AI provider wrapper must be transparent in both directions.** It sits
  on the critical path of every AI call, so a bug there breaks transcription
  and scoring rather than merely losing a counter. Pinned by two named tests
  in `03-program-design.md`:
  `test_wrapper_reraises_the_original_exception_unchanged` (same exception
  type and message reach the caller *after* the failure is recorded — both
  halves asserted together, because either alone passes a broken
  implementation) and `test_wrapper_returns_the_providers_value_unchanged`.
  `AIQuotaExceeded` specifically must not degrade to the base `AIUnavailable`:
  Module 7's multi-key failover branches on that exact type, so flattening it
  would silently disable key rotation while every counting test still passed.

## Headline from the audit

Read `AUDIT.md` before anything else. The short version, because it should
shape every gate below:

| Dashboard | Shipped | Partial | Gap |
|---|---|---|---|
| Candidate | 6 of 8 | 2 | 0 |
| Recruiter | 2 of 7 | 1 | 4 |
| Admin | 4 of 5 | 1 | 0 |

Modules 5–9 already delivered most of this spec under other names. Module 10
is therefore **mostly an access-and-visibility module, not a computation
module**: `skill_breakdown()` and `performance_trend()` already produce exactly
what the recruiter dashboard needs, and what is missing is a recruiter-scoped
endpoint plus an explicit decision about which fields that role may see.

The one bullet requiring genuinely new product thinking is **shortlisting
insights**.

## Slices (see `04-slices.md`)

Candidate → Recruiter → Admin, each end-to-end before the next. No horizontal
building. Full suite green before any slice is marked done.

- [x] **Slice 1 — Candidate: improvement progress.** `axis_progress()` added to
      `performance_analytics.py` (93 insertions, 0 deletions — additive, and
      `test_performance_analytics.py` was not touched); `axis_progress` key
      added to the candidate performance endpoint; block rendered in
      `PerformanceAnalytics.jsx`. 14 new tests in `test_axis_progress.py`.
      **Full suite: 423 passed.**

      Verified on real data: weakest axis `technical_relevance` (28.0), axis
      progress 35 → 85 over 6 interviews (+47.8) against an overall trend of
      +41.0 — different numbers, which is the whole point. Browser check
      confirmed the screen agrees with the endpoint payload.

      *Gate 3 risk 3 (axis noise) did not materialise on this data — the line
      was readable, so the first-versus-latest retreat was not needed. Worth
      re-checking on a candidate with a shorter history.*

      *Honest limit: on this candidate the axis and overall lines look alike,
      because their technical relevance and overall score happened to move
      together. The divergence the feature exists to catch is proven by
      `test_tracks_the_named_axis_not_the_overall_score`, not by the screenshot.*

      **Reconciliation fix, made in-slice.** Putting the two figures side by
      side exposed a contradiction: `weak_areas` said technical relevance = 28
      while the chart's latest point said 85. Both correct, for three separate
      reasons — different **window** (all time vs one interview), different
      **unit** (mean of 19 individual answers vs a per-interview mean), and
      different **population** (see the finding below). The screen now names
      each figure's window in words and draws the all-time average as a dashed
      reference line on the chart, so the relationship is visible instead of
      inferred.

## Findings from Slices 3-6

**Gate 3 risk 1 landed, as predicted, and changed a rule.** The shortlist
`strong_in_skill` rule originally compared a candidate's *best skill* against
the pool's *average overall score*. That is not like-for-like — a best skill is
by definition a candidate's highest number — so it fired for perfectly middling
people. The rule now also requires the candidate to be at or above the pool
average overall before a skill strength is named. Caught by three failing tests
rather than by inspection.

**A test asserted its own disclaimer.** `test_response_carries_no_rank_or_position`
scanned the whole comparison payload for the word "rank" and failed on the note
that says *"this view does not rank candidates"*. The test now scans the data
and separately asserts the note does disclaim ranking.

**The comparison picker does not scale.** 85 candidate chips render as a wall,
most of them test accounts. Functional, and poor. A search or filter is the
obvious fix and was not in scope for Slice 4.

## Open finding — needs a decision before it spreads

**`weak_areas` and `performance_trend` disagree about which interviews count.**
Found in Slice 1; it predates Module 10.

- `performance_trend` plots **completed interviews only** — an unscored or
  unfinished interview is treated as missing data, by explicit design.
- `weak_areas` averages **every graded answer**, including answers from
  interviews still `IN_PROGRESS` and never finished.

For the demo candidate that is 9 of 19 answers. Completed-only, their technical
relevance averages **38.2**; including abandoned sessions it is **28.0**. The
lower figure is the one shown as their weakest axis, and the one Module 9
emails in performance summaries.

Slice 1 made this *visible* rather than fixing it, deliberately: aligning the
populations means changing `weak_areas`' contract, which is not additive, would
require touching `test_performance_analytics.py` (forbidden by standing
constraint 2), and would change what Module 9 has already emailed candidates.
That is a gate-level decision, not a slice-level one.

**The three options, with tradeoffs, are written up in
`DECISION-weak-areas-population.md`.** Summarised only:
1. Leave it — no code change, no selection effect, but the inconsistency stays
   and must be explained on every surface.
2. Completed-only — one population, but carries a selection-bias risk a
   candidate could exploit by abandoning bad sessions.
3. Report both — discards nothing, but multiplies figures on every surface and
   invites each audience to anchor on the number that suits them.

**RESOLVED 2026-09-11 — Option 2, completed-only**, implemented as a standalone
approved change with `test_performance_analytics.py` rewritten to match (24
tests, up from 17). Standing constraint 2 is restored: that file is frozen
again for every Module 10 slice. The reasoning, the observed effect and the
accepted email consequence are in `DECISION-weak-areas-population.md`.

Do not carry this into Slice 3: the recruiter view surfaces `weakest_axis` and
`axis_averages`, so whichever population is chosen will sit beside a
candidate's name. Slice 2's history PDF is affected too and now carries the
window-labelling requirement explicitly — see `04-slices.md`.

**When this is decided, it is its own change, not a Module 10 slice.** It
alters Module 8's contract deliberately and `test_performance_analytics.py`
is updated to match. That is a different act from the additive-only rule being
violated: the rule exists to catch *silent* drift in Module 8's contract, and
changing the contract on purpose with its tests rewritten is legitimate. It
should be approved and committed separately so the history shows it as a
deliberate contract change rather than a side effect of a dashboard slice.
- [x] **Slice 2 — Candidate: full-history report.**
      `report_pdf.build_history_report()` beside the existing builder, reusing
      `_styles()`, `_kv_table()` and the colour constants;
      `GET /notifications/reports/history.pdf` (owner only); download action in
      `PerformanceAnalytics.jsx`, offered even with nothing scored because the
      empty report explains itself. 14 tests in `test_history_report.py`
      covering zero, one and many interviews — built as real PDF bytes and read
      back with pypdf, so they assert what a candidate would actually see.

      **Window decision: both figures, labelled.** The population fix made this
      possible — every figure in the report now comes from completed
      interviews only, so the two numbers are no longer drawn from different
      populations. What remains is the ordinary distinction between an average
      and the results inside it, which prints fine when each heading names its
      window: "averaged across all N completed interviews" against "one row per
      interview", plus a sentence saying the two are "the difference between
      the two, not a disagreement". The agreed fallback — dropping the lifetime
      average — was not needed, and `build_history_report`'s docstring records
      why so nobody reinstates the ambiguity later.

      Verified end to end: 2-page PDF, HTTP 200, all four window labels present
      in the extracted text, downloaded through the browser.
- [x] **Slice 3 — Recruiter: candidate performance, filtered.**
      `performance_analytics.recruiter_view()`,
      `GET /analytics/recruiter/candidates/{id}/performance`,
      `RecruiterCandidatePerformance.jsx` inside the existing sessions modal.
      Visibility enforced by test, not just documented: the payload is asserted
      to contain no `practice_recommendations`, no `learning_resources` and no
      Module 6 field. A candidate reading another candidate's performance
      gets 403.
- [x] **Slice 4 — Recruiter: comparison.** `GET /analytics/recruiter/compare`,
      `CandidateCompare.jsx` replacing the `NotAvailable` placeholder. All four
      binding constraints enforced server-side and tested: rejects one (400),
      rejects five (400), preserves selection order, ignores `sort=`. Every
      cell carries `answers_graded` and `provisional`. Verified in the browser
      by selecting the second candidate first — the rendered order followed the
      selection, not the list or the scores.
- [x] **Slice 5 — Recruiter: shortlisting insights.** `shortlist_insights.py`,
      its endpoint, `ShortlistInsights.jsx` on a new Insights tab. Structural
      tests assert no insight contains rank/position/hire/reject wording and
      that every emitted insight carries non-empty evidence.
- [x] **Slice 6 — Admin: AI monitoring.** `ai_metrics.py`, all six
      `ai_provider` delegating functions wrapped, `GET /analytics/admin/ai`,
      history in the admin AI section. Verified live: 4 real
      `generate_questions` calls counted at 5.6s average while the test suite
      drove them.

Sizing is uneven because the audit made it so: the candidate dashboard is
six-eighths built, the recruiter dashboard carries four of the module's five
real gaps.

## Constraints carried in from the rest of the project

1. **No recruiter-to-candidate assignment exists.** Comparison, shortlisting
   and profiles must not imply ownership. Module 9 hit this exact constraint
   and resolved it by addressing recruiter alerts to the role, wording them
   "Ana Reyes completed a TECHNICAL interview" and never "your candidate" —
   there is a test asserting that phrase never appears. Module 10 follows it.
2. **Visibility is decided per field, not by default.**
   `behavior_analysis.recruiter_view()` is the precedent: it filters a stored
   report so recruiter and candidate can never see disagreeing numbers, and it
   withholds `emotions` and the written summary on stated grounds.
3. **Download reports extends `report_pdf.py`.** One PDF pipeline.
4. **AI monitoring builds on `ai_provider.provider_status()`** already surfaced
   at `/api/health`. No parallel monitoring system.
5. **Any new column ships with a migration script** in `backend/scripts/`,
   matching `add_user_email_notifications_column.py`. No ad hoc ALTER TABLE —
   the standing rule since Module 9.
   **Finding at Gate 2: this module triggers no new column and no new table,
   so no migration script is required.** Everything computes from
   `InterviewQuestion.analysis` and `Interview.overall_score`; shortlisting
   produces insights rather than a persisted shortlist; AI monitoring is
   in-memory by decision. A later revision adding a saved shortlist or durable
   AI history writes the script then. Do not go looking for one for Module 10.
6. **Module 6 signals stay out of anything that ranks people.** They are
   measured in the candidate's own browser and are therefore forgeable. This
   rule already binds `analytics.py` and the leaderboard.

## Notes for a fresh session

- `performance_analytics.py` is pure arithmetic with no DB or AI access, and
  has 17 unit tests. It is safe to call with any candidate's rows; only the
  endpoint around it is candidate-gated.
- `GET /api/metrics` is in-memory and resets on process restart. It says so.
  Any "system health report" that implies history must reckon with that.
- The recruiter `#compare` section currently renders an explicit
  `NotAvailable` placeholder. Replacing it is a visible win.


## Not fully confident

Recorded plainly rather than left for someone to discover.

- **The shortlist thresholds are still guesses.** `STRONG_MARGIN` and
  `IMPROVING_MARGIN` are 10.0 because ten is a round number. Gate 3 flagged
  this and the plan was to tune against the real pool — but the pool has two
  candidates with scored interviews, so there is nothing to tune against. The
  rules are defensible in shape and arbitrary in magnitude. They need revisiting
  against a real population, not against this database.

- **`strong_in_skill` needed a second condition and may need a third.**
  Comparing a candidate's best skill against the pool's average *overall* was
  not like-for-like and fired for middling candidates; it now also requires the
  candidate to be at or above the pool average. The honest comparison would be
  best-skill against the pool's average best-skill, which this does not compute.

- **The comparison picker does not scale.** Eighty-five candidate chips render
  as a wall. Functional, poor, and no search or filter was in scope.

- **Comparison still reads as a decision tool.** Gate 4 asked for this to be
  reported as a finding if it happened. It is mitigated — unsorted, capped at
  four, every cell carrying its answer count — but four people on identical
  axes invites a judgement no matter what the note says. A candidate with zero
  scored interviews renders as four dashes beside someone with six, which is
  honest and still looks like losing.

- **Frontend has no regression tests.** Every UI claim here rests on scripted
  browser walkthroughs run once. They verified real behaviour against real
  endpoint payloads, but nothing will catch a future change breaking these
  screens.

- **AI monitoring dies on restart, by design.** Verified counting four real
  calls at 5.6s average. It cannot answer "what happened last Tuesday", and the
  UI says so.
