# Slice plan: Module 10 — Dashboard & Analytics

Gates 1–3 approved 2026-09-10. Order is fixed by the brief: **Candidate →
Recruiter → Admin**, each dashboard finished end-to-end before the next begins.
No horizontal building across all three.

The audit is why the slices are so unevenly sized. The candidate dashboard is
six-eighths built, so Slice 1 is small; the recruiter dashboard carries four of
the module's five real gaps and takes three slices.

---

- [ ] **Slice 1 — Candidate: improvement progress.**
      Add `axis_progress()` to `performance_analytics.py` and an
      `axis_progress` key to the existing candidate performance endpoint,
      additively. Render a block in `PerformanceAnalytics.jsx` plotting the
      named weak axis beside the overall trend already there.

      *Proof:* `test_axis_progress.py` green, including the case that defines
      the feature — a history where the overall score rises while the named
      axis stays flat must report the axis as flat. `test_performance_analytics.py`
      passes **unmodified**, which is the evidence the change stayed additive.
      Browser: open the dashboard as `candidate.demo@smarthire.dev` and read
      the axis line against the numbers the endpoint returns.

      *Gate 3 risk 3 lands here.* If per-interview axis averages read as noise
      on real data, retreat to first-versus-latest with no line rather than
      shipping a chart that invents a trajectory. Decide by looking, not by
      guessing.

- [ ] **Slice 2 — Candidate: full-history report.**
      `report_pdf.build_history_report()` beside the existing builder, reusing
      `_styles()`, `_kv_table()` and the colour constants. New owner-only route
      for the history PDF; download button beside the existing per-interview
      one.

      **Carries Slice 1's window-labelling requirement.** The existing
      per-interview PDF is safe — it calls `summarise()` over one interview's
      questions, so its `axis_averages` and `weakest_axis` describe that
      interview and nothing else. The history report is different by
      construction: it spans every scored interview, so it will surface the
      same cross-history `weak_areas` figure that read as a contradiction on
      the dashboard. It must state each figure's window in the document itself.

      A PDF is worse than a screen for this. The dashboard could reconcile the
      two numbers with a dashed reference line and adjacent copy; a saved file
      is read later, alone, with no such context. If the window cannot be made
      unambiguous in print, show the per-interview figures only and leave the
      lifetime average out rather than print a number that invites the wrong
      reading.

      *Proof:* generate for a real candidate, open the file, confirm every
      scored interview appears and the figures match the dashboard exactly —
      one pipeline means they cannot disagree, and this checks that. Plus: no
      figure appears without its window stated. Full suite green.
      **Candidate dashboard is complete at the end of this slice.**

---

- [ ] **Slice 3 — Recruiter: candidate performance, filtered.**
      `performance_analytics.recruiter_view()` plus
      `GET /analytics/recruiter/candidates/{user_id}/performance`. Extend
      `CandidateSessions.jsx` with the skill breakdown, trend and axis
      progress.

      *Proof:* `test_recruiter_analytics.py` asserts the withheld fields are
      genuinely absent from the payload —
      `practice_recommendations`, `learning_resources`, and anything from
      Module 6. The visibility table in `02-architecture.md` is enforced by
      test here, not merely documented. A candidate reading another
      candidate's performance gets 403.

- [ ] **Slice 4 — Recruiter: comparison.**
      `GET /analytics/recruiter/compare`, and `CandidateCompare.jsx` replacing
      the `NotAvailable` placeholder at `#compare`.

      *Proof:* the four binding constraints, each with a named test —
      rejects one candidate (400), rejects five (400), preserves selection
      order, and ignores any `sort=` parameter. Every cell carries
      `answers_graded` and `provisional`. Browser: put a thin-evidence
      candidate beside a well-evidenced one and confirm the difference is
      visible at a glance rather than buried.

      *This is the module's highest-risk surface.* Four people on identical
      axes reads as a decision tool no matter what the copy says. If the built
      screen still reads as a ranking despite the unsorted order and the
      provisional flags, say so and change it — that is a finding, not a
      failure.

- [ ] **Slice 5 — Recruiter: shortlisting insights.**
      `shortlist_insights.py` and its endpoint; `ShortlistInsights.jsx` on
      `#candidates`.

      *Proof:* `test_shortlist_insights.py` green, including the structural
      test that no insight contains `rank`, `position`, `best`, `hire` or
      `reject`, and the test that every emitted insight carries non-empty
      `evidence`.

      *Gate 3 risks 1 and 2 land here.* The thresholds are guesses and the pool
      average is skewed by abandoned test interviews. Run the rules against the
      real pool, look at what fires, and tune the named constants. If
      "consistently strong" fires for nobody because almost every candidate has
      one or two interviews, drop the insight kind rather than lowering the
      bar. **Recruiter dashboard is complete at the end of this slice.**

---

- [ ] **Slice 6 — Admin: AI monitoring.**
      `ai_metrics.py`; wrap the six `ai_provider` delegating functions;
      `GET /analytics/admin/ai`; extend the existing AI section of
      `AdminHome.jsx` with history.

      *Proof:* `test_ai_metrics.py` green — above all
      `test_wrapper_reraises_the_original_exception_unchanged` and
      `test_wrapper_returns_the_providers_value_unchanged`, since this slice
      touches the critical path of every interview. `test_voice.py` re-run
      specifically, because that is what exercises the wrapped calls end to
      end. Then force a real failure — an invalid key — and confirm it appears
      as a counted failure while the caller still receives the original
      exception.

      Label the window as beginning at the last restart. Never present it as
      uptime.

---

## Standing constraints for every slice

1. **Run the full backend suite before marking any slice done.** Currently 409
   passing plus `test_voice.py`'s 18. A slice is not done because its own tests
   pass.
2. **`test_performance_analytics.py` stays unmodified.** If a slice needs to
   change it, the change was not additive and the design is wrong.
3. **Real tests only.** No test that asserts a mock returned what the mock was
   told to return.
4. **Nothing implies recruiter ownership of a candidate** — no "your
   candidate", no assignment language. Module 9's precedent, and it has a test.
5. **Comparison is never sortable and holds two to four candidates.** Binding,
   enforced server-side, not a UI convention.
6. **Provisional flags are mandatory wherever candidates appear side by side.**
   Binding, not advisory.
7. **No Module 6 signal reaches comparison, shortlisting, or anything that
   ranks.**
8. **No new column is expected.** If a slice believes it needs one, that is a
   design change requiring a gate revision *and* a committed migration script —
   not an ad hoc `ALTER TABLE`.

## Frontend verification

This repo has no frontend test harness, as recorded in Module 6's Gate 3 and
again in Modules 8 and 9. Every slice with a UI ends in a scripted browser
walkthrough against real data — sign in, open the screen, assert the rendered
figures match the endpoint — and the screenshot goes in the slice's notes.
That is verification, not a regression suite, and the distinction should be
stated whenever a slice is reported as done.
