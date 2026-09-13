# Product: Module 10 — Dashboard & Analytics

## Problem

The audit changes what this module is. Six of eight candidate bullets and four
of five admin bullets already ship. Restating them as "Module 10" would be
relabelling, not building. The real problems left are three, and they are
different in kind from each other:

**1. A candidate cannot see whether they are getting better at the thing they
were told to fix.** Module 7 tells them their weakest axis and hands them a
practice recommendation. Module 8 plots whether their *overall score* moved.
Neither answers the question the advice creates: *did the axis I was told to
work on actually improve?* A candidate can lift their overall score by getting
more fluent while their technical relevance stays exactly where it was, and
today the dashboard would call that progress.

**2. A recruiter cannot compare candidates on anything but a single number.**
The leaderboard ranks on one score from one interview. To decide between two
people a recruiter needs to see where each is strong — and the platform already
computes exactly that per candidate, but only exposes it to the candidate
themselves. The comparison tab currently shows a placeholder admitting this.

**3. Nobody finds out the AI broke until a candidate does.** The admin
dashboard answers "is the AI reachable right now". It records nothing. Earlier in
this project a spent Gemini quota silently stopped every transcription for a
day; the admin dashboard showed green throughout, and the failure surfaced only
as a candidate's missing report. Point-in-time reachability is not monitoring.

## Success metric

**Primary:** among candidates who receive a weak-axis recommendation and then
complete two or more further interviews, the share whose *named weak axis*
improves. This is measurable off data already stored, needs no new
instrumentation, and it tests the advice rather than the dashboard — if the
recommendations are useless, this number stays flat and we should know.

**Secondary (recruiter):** share of recruiter sessions that open a comparison
or a candidate's skill view, rather than stopping at the leaderboard. A
recruiter who never leaves the single-number ranking is not being served by any
of this.

**Health, not success (admin):** time between an AI provider failure starting
and it being visible on the admin dashboard. Today that is unbounded.

## Announcement

Your dashboard now tracks whether you are actually improving where it told you
to. When SmartHire flags your weakest area, it follows that axis across your
later interviews and shows you the line — so "your technical relevance went
from 28 to 44 over four interviews" replaces "your score went up". You can
download your whole history as one report, not just a single interview.

Recruiters get more than a ranking. Any candidate's strengths break down by
skill area, their performance is plotted over time, and up to four candidates
can be put side by side on the same axes. Shortlisting insights point out who
is worth a closer look and say why — always with the evidence behind it, never
as an automated verdict.

Administrators get AI monitoring that remembers. Provider calls are tracked
over time — success rate, failures, quota exhaustion — so a spent quota shows
up on the dashboard when it happens instead of days later as a candidate's
missing report.

## Screens

- **Candidate — improvement progress.** A new block inside the existing
  performance history card, plotting the named weak axis over time next to the
  overall trend already shown there.
- **Candidate — full-history download.** A button beside the existing per
  interview "Download PDF", producing a report spanning every scored interview.
- **Recruiter — candidate skill view.** Adds the skill breakdown and trend to
  the candidate session view a recruiter already opens, filtered for the role.
- **Recruiter — comparison.** Replaces the comparison placeholder. Pick up to
  four candidates, see them on the same four axes.
- **Recruiter — shortlisting insights.** A panel on the candidates list
  surfacing candidates worth attention, with the reason attached.
- **Admin — AI monitoring.** Extends the existing AI status section with
  history: call counts, failure rate, quota events over a window.

## Decisions locked at this gate

1. **Improvement progress tracks the named axis, not the overall score.** The
   overall trend already exists and is not the question the advice raises.
2. **Comparison is candidate-selected and capped at four.** No ownership is
   implied — a recruiter picks from the full candidate list, exactly as the
   leaderboard already shows everyone. Four because a fifth column makes the
   axes unreadable, not for any deeper reason.
3. **Shortlisting insights explain themselves and decide nothing.** Every
   insight carries the evidence that produced it ("scored 78 across 4
   interviews, above the pool average of 39"). No automated
   accept/reject, no ranked "best candidate", no hidden weighting. A recruiter
   who cannot see why an insight fired should not be shown it.
4. **Recruiter-facing analytics are filtered, never recomputed.** The same
   rule already applied to on-camera data: a recruiter sees a subset of the
   numbers the candidate sees, so the two can never disagree. Which fields
   specifically is Gate 2's job; the rule is fixed here.
5. **AI monitoring is admin-only and counts real calls.** It records what the
   provider layer actually did. It is not a synthetic prober — polling the API
   to test it would spend the very quota it is meant to protect.
6. **The full-history report extends the existing report generator.** One
   pipeline, per the standing constraint.

## Honesty constraints

Carried from Module 5's refusal to show a pronunciation score, Module 7's
refusal to let camera data touch the rubric, and Module 8's refusal to call two
data points a trend. They bind here too, and the recruiter surfaces are where
the risk is highest, because these numbers will sit beside real people's names:

- **"Shortlisting insights" must not become a hiring recommendation.** The
  platform scores mock interviews against a disclosed rubric using an AI that
  can be wrong. An insight may say a candidate is worth a look and why; it may
  never say who to hire, rank "fit", or imply the shortlist is complete.
- **Thin evidence stays visibly thin, including in comparison.** Module 8's
  rule — fewer than three graded answers is shown but flagged provisional — is
  a candidate-facing courtesy today. Side by side against another person it
  becomes a fairness requirement: a candidate with one graded answer must not
  read as equivalent to one with twelve.
- **Improvement progress must not manufacture a trajectory.** The same
  four-interview floor Module 8 uses for its direction claim applies. Two
  points on an axis is two points, not progress.
- **Module 6 stays out of comparison and shortlisting entirely.** It is
  filtered into per-session recruiter context today, which is defensible
  because it sits beside one interview being read. Feeding forgeable,
  uncalibrated, culturally-variable gaze data into a mechanism that sorts
  candidates against each other is not, and this module will not do it.
- **AI monitoring reports what was observed, not availability.** In-process
  counts reset when the server restarts, exactly as the existing system
  metrics already do and say. A window that begins at the last restart must be
  labelled as such rather than presented as uptime.
