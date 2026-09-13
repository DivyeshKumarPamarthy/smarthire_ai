# Audit: what Module 10's spec already has

Read before Gate 2, as instructed. Every file named in the brief was read in
full. The finding that matters: **the candidate dashboard is essentially
already built**, the admin dashboard is nearly so, and almost all of the real
work is on the recruiter side.

Legend: **HAVE** = shipped and working · **PART** = exists but does not cover
the bullet · **GAP** = nothing addresses it.

---

## Candidate Dashboard — 6 of 8 already shipped

| Spec bullet | Verdict | Where it already lives |
|---|---|---|
| Overall performance score | **HAVE** | `GET /analytics/candidate` → `latest_score`, `latest_score_rating`, `best_score`; rendered in CandidateHome "Your score" |
| Interview history | **HAVE** | CandidateHome `#history` + `InterviewReview.jsx` modal |
| Score breakdown | **HAVE** | `Module7Report.jsx` (4 weighted axes + evidence sub-metrics) and `AnalysisReport.jsx` per answer |
| Skill-wise analytics | **HAVE** | `performance_analytics.skill_breakdown()` → `GET /analytics/candidate/performance` → `PerformanceAnalytics.jsx` |
| Weak-area identification | **HAVE** | `performance_analytics.weak_areas()`, same endpoint and component |
| Performance trends | **HAVE** | `performance_analytics.performance_trend()`, plotted as inline SVG |
| AI feedback & improvement progress | **PART** | *Feedback* is shipped (`practice_recommendations`, keyed to the weakest axis). *Improvement progress* is not: the trend shows whether the **overall score** moved, but nothing tracks whether the axis a candidate was told to work on actually improved. |
| Download reports | **PART** | `report_pdf.build_interview_report()` covers **one interview**. There is no report spanning a candidate's history — which is what a dashboard-level "download reports" implies. |

**Reusable as-is:** `performance_analytics.py` (226 lines, 17 tests) is pure
arithmetic over stored analyses — no DB, no AI. Every function it exposes is
role-agnostic and can be called with any candidate's rows.

---

## Recruiter Dashboard — 4 real gaps, and this is where the work is

| Spec bullet | Verdict | Where it already lives / what is missing |
|---|---|---|
| Candidate performance overview | **HAVE** | `GET /analytics/recruiter` (pool counts, top technologies, average score) + `GET /analytics/recruiter/candidates` (per-candidate rows, ordered by activity) |
| Candidate profiles & reports | **PART** | `CandidateSessions.jsx` shows one candidate's completed interviews with score and filtered attention. **Missing:** no résumé/profile detail view, and no recruiter access to the PDF report — `/notifications/reports/interview/{id}.pdf` is owner-only. |
| Candidate comparison | **GAP** | `RecruiterHome` `#compare` is an explicit `NotAvailable` placeholder saying so. Nothing behind it. |
| Skill-wise analytics | **GAP** | The service exists but `GET /analytics/candidate/performance` is `require_roles(CANDIDATE)` and reads `current_user` only. No recruiter-facing skill view of any kind. |
| Candidate ranking | **HAVE** | `GET /analytics/leaderboard` + `Leaderboard.jsx`, shared by recruiter and admin |
| Performance trends | **GAP** | Same as skill-wise: `performance_trend()` exists but is candidate-scoped and candidate-gated. |
| Shortlisting insights | **GAP** | Nothing. No shortlist concept, no column, no endpoint. |

**Important:** the three "GAP" analytics bullets are *access* gaps, not
algorithm gaps. `skill_breakdown()` and `performance_trend()` already compute
exactly what the recruiter view needs; what is missing is a recruiter-scoped
endpoint that feeds them another user's rows, plus the visibility decision
about what a recruiter may see.

---

## Admin Dashboard — 4 of 5 shipped

| Spec bullet | Verdict | Where it already lives |
|---|---|---|
| User & recruiter management | **HAVE** | `GET /users`, `PUT /users/{id}/block` (with self-block guard), `PUT /users/{id}/role` + AdminHome `#users` |
| Interview activity monitoring | **HAVE** | `GET /analytics/admin` (by status/type/difficulty, 14-day series) + `GET /analytics/live` + AdminHome `#activity` |
| AI performance monitoring | **PART** | `GET /api/health` → `ai_provider.provider_status()`, rendered in AdminHome `#ai`. This is a **point-in-time reachability check**: is the provider configured and reachable, and which model. It records no history — no AI call success/failure rate, no quota-exhaustion count, no AI latency. The Gemini 429s that broke transcription earlier in this project were invisible here. |
| System activity/health reports | **HAVE** (reports **PART**) | `GET /api/metrics` — per-endpoint requests, errors, error rate, avg/max, plus p95/p99 latency, in AdminHome `#api`. In-memory and resets on restart, which it documents. No downloadable form. |
| Platform usage analytics | **HAVE** | `GET /analytics/admin` counts + 14-day interview series |

Also present and adjacent: `api/tickets.py` (`/reasons`, create, list,
`PUT /{id}/status`) with an AdminHome `#tickets` queue — a moderation surface
the spec does not name but which overlaps "user management".

---

## The visibility precedent this module must follow

`behavior_analysis.recruiter_view()` is the existing pattern and it is
deliberate: it **filters** a stored report rather than recomputing one, so a
recruiter can never see a number that disagrees with the candidate's own.
`RECRUITER_VISIBLE_FIELDS` admits `eye_contact_percent`, `look_aways`,
`engagement`, `gaze_breakdown` and `confidence_percent`; it withholds
`emotions` and the written `summary`, on the stated grounds that *"a percentage
carries its own uncertainty visibly; a word like 'nervous' beside someone's
name does not"*.

Any new recruiter- or admin-facing shape in Module 10 needs the same explicit
decision, made per field rather than by default.

---

## What this audit means for scope

- **Candidate slice is small.** Two partial bullets, both additive: axis-level
  improvement tracking, and a history-spanning PDF that extends
  `report_pdf.py` rather than starting a second pipeline.
- **Recruiter slice is the bulk of the module.** Four gaps, of which three are
  solved by exposing existing computation through a recruiter-scoped,
  visibility-filtered endpoint. Only *shortlisting insights* is genuinely new
  product.
- **Admin slice is one real gap** — AI monitoring with history — plus
  optionally a downloadable form of metrics already collected.
- **Nothing in this audit should be rebuilt.** `performance_analytics.py`,
  `report_pdf.py`, `metrics.py`, the leaderboard, the live monitor, the user
  management endpoints and the tickets queue are all working and stay.
