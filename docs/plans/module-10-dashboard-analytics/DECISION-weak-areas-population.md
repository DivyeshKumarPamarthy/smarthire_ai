# Decision: which interviews count toward `weak_areas`

> **RESOLVED 2026-09-11 — Option 2, completed interviews only.** Implemented as
> its own approved change, separate from any Module 10 slice, with
> `test_performance_analytics.py` rewritten to match. See "Resolution" at the
> foot of this document. The options below are kept as the record of what was
> weighed.


Raised by Slice 1 (2026-09-11). Predates Module 10. **Not a Module 10 slice** —
whichever option wins is its own approved change that deliberately alters
Module 8's contract and rewrites `test_performance_analytics.py` to match.

## The inconsistency

- `performance_trend()` plots **completed interviews only**. An unfinished
  interview is treated as missing data, by explicit design.
- `weak_areas()` averages **every graded answer**, including answers from
  interviews still `IN_PROGRESS` and never finished.

Both are reasonable alone. Together they produce two different figures for the
same axis, and Slice 1 put them on the same screen.

## What the data actually shows — read the caveat

For the demo candidate, on `technical_relevance`:

| | answers | mean |
|---|---|---|
| completed interviews | 10 | **38.2** |
| abandoned interviews | 9 | **16.7** |
| combined (what `weak_areas` reports) | 19 | **28.0** |

Across all four axes the same candidate splits 37.5 completed vs 21.4
abandoned — a 16-point gap in the same direction.

**The caveat matters more than the numbers.** Only two candidates in this
database have any graded answers at all, and only one is affected by the split.
Of that candidate's 19 unfinished interviews, 12 were created during this
working period — they are largely testing debris from building Modules 7–10,
not a candidate repeatedly walking out of interviews that were going badly.

So the honest claim is narrow: **the split demonstrably bites on the data we
have**, producing a 16-point swing on the one candidate it can be measured on.
It is *not* evidence of a behavioural pattern among real candidates, because
there is no real candidate population here yet. Anyone citing 16.7 vs 38.2 as
proof that candidates abandon interviews strategically is overreading it.

---

## Option 1 — Leave it as is

`weak_areas` keeps counting every graded answer. Slice 1's window labelling and
reference line stay as the mitigation.

**For**
- Abandoned answers are real answers. The candidate spoke them, they were
  transcribed and graded, and they demonstrate ability on that axis.
- No selection effect: a candidate cannot improve their reported weak axis by
  quitting sessions that are going badly.
- Nothing already shipped changes. Module 9 has emailed performance summaries
  built on these figures; those stay consistent with what the dashboard says.
- Zero code change, zero migration, no contract break.

**Against**
- It contradicts `performance_trend` inside the same module, and the
  contradiction is now visible on one screen. Explaining an inconsistency is
  weaker than not having one.
- "Your weakest axis is 28" is dragged down by sessions the candidate did not
  finish, which reads as unfair to the candidate who abandoned an interview for
  reasons unrelated to ability — a bad connection, a phone call.
- The explanation has to be repeated everywhere the number appears: dashboard,
  history PDF, recruiter view, comparison, shortlisting. Each surface is
  another chance to omit it.

---

## Option 2 — Completed interviews only

`weak_areas` filters to interviews with a completion time, matching
`performance_trend`.

**For**
- One population across the whole module. The two figures stop disagreeing and
  no labelling is needed to reconcile them.
- A completed interview is a completed assessment. A partial session is a
  partial measurement of anything.
- Aligns with the spirit of `aggregate_score`, which refuses to let ungraded
  work count against a candidate — though note that precedent is about
  excluding *absent* work so it cannot be scored as zero, and these answers are
  graded, so the analogy is imperfect rather than exact.

**Against — the selection-bias risk, stated plainly**

This is the serious objection. Counting only finished interviews means a
candidate's reported weakness improves when they abandon sessions that are
going badly. Quit early and the bad answers vanish from your record; finish and
they count.

The direction is visible in the data we have: on the one candidate where both
populations exist, abandoned answers average **16.7** against **38.2** for
completed ones on the same axis. Whatever caused it here, that is the exact
shape the bias would take — the weaker work sitting in the sessions that were
never finished, and completed-only quietly discarding it.

Two things keep this from being decisive. The gap is measured on **one
candidate**, and most of their unfinished interviews are testing debris rather
than a person giving up. And the bias requires a candidate who knows the rule
and acts on it, which is a strong assumption for a practice tool. But the
mechanism is real, it is not detectable once it happens, and it would work in
favour of exactly the candidates a recruiter most needs accurate data on.

**Also against**
- Changes the reported weakest axis and its score for every affected candidate.
- Contradicts performance summaries Module 9 has already emailed. A candidate
  who kept the email would see a different number on the dashboard with no
  explanation.
- Requires the contract change and the test rewrite.

---

## Option 3 — Report both, labelled

`weak_areas` returns both figures: all-time across every graded answer, and
completed-only. Every surface shows the pair.

**For**
- No information is discarded and no population is privileged by fiat.
- The gap between the two is itself meaningful — a large gap says a candidate's
  unfinished work is much weaker than their finished work, which is worth
  knowing and which both other options hide.
- Nothing already emailed becomes wrong; the all-time figure is still there.

**Against — complexity**
- Every surface carries two numbers instead of one: dashboard weak-areas block,
  history PDF, recruiter performance view, comparison cells, shortlist evidence
  strings. Comparison is the worst case — four candidates × four axes × two
  populations is thirty-two figures on one screen, against a binding
  requirement that the same screen already show `answers_graded` and
  `provisional` per cell.
- The history PDF cannot lean on adjacent copy the way a screen can, so the
  pair has to be legible in print, alone, months later.
- "Weakest axis" stops being a single answer. Which of the two picks it? If
  they disagree — plausible, given a 16-point gap — the module has to decide
  anyway, and the decision is merely deferred to a worse place.

**Against — anchoring**

Showing a candidate two numbers for the same axis invites them to keep the
flattering one. Here that is the completed-only figure, higher by 16 points,
and it comes with a ready-made justification: *"the real number is 38, the
other one counts sessions I abandoned."* The dashboard would be handing them
the excuse along with the data.

This cuts the other way for recruiters, who have the opposite incentive and may
anchor on the lower figure. The same pair of numbers would then be read as two
different stories by the two audiences — which is precisely the failure
`recruiter_view()` exists to prevent, reintroduced through the front door.

---

## Note for whoever decides — the audience changes the stakes

Not a recommendation, and not part of any option. It cuts across all three.

This number is slated to reach recruiters in Slice 3 (`weakest_axis`,
`axis_averages` in the filtered performance view), Slice 4 (comparison cells)
and Slice 5 (shortlist evidence). A candidate reading their own weak axis and a
recruiter sizing that candidate up are not the same audience for the same
figure, and the populations carry different risks depending on who is reading:

- **To a candidate**, the all-time figure is harsher than their finished work
  warrants, and the completed-only figure is more encouraging than it should
  be. Either error is survivable — it is their own practice tool, and the
  consequence is practising the wrong thing for a week.
- **To a recruiter**, the completed-only figure is the one that can be
  influenced by the candidate's own behaviour, and it is the one that will sit
  beside their name in a comparison. An inflated weak-axis score that a
  candidate can produce by quitting is a worse failure in a recruiter's hands
  than a harsh score is in a candidate's.

That asymmetry argues for deciding this **before Slice 3**, not after — and it
leaves open a fourth shape nobody has costed: different populations for
different audiences, all-time to the recruiter and completed-only to the
candidate. That would violate the filter-never-recompute rule that
`recruiter_view()` is built on, so it is noted as a possibility and not
proposed.


---

# Resolution — Option 2, completed interviews only

Decided 2026-09-11. Implemented as a standalone change, not folded into a
Module 10 slice.

## Why, given the selection-bias objection was real

The bias argument against Option 2 was not dismissed; it was outweighed:

- **The evidence for it is n=1 and contaminated.** The 16.7-versus-38.2 gap
  sits on one candidate whose 19 unfinished interviews are mostly testing
  debris from building Modules 7–10. It shows the split *bites*; it does not
  show candidates abandon strategically, because there is no real candidate
  population here to show anything about.
- **The bias needs a candidate who knows the rule.** Nothing in the product
  tells anyone that quitting removes answers from their record.
- **The inconsistency is certain; the bias is speculative.** One is visible on
  screen today for every candidate with an abandoned session. The other
  requires a behaviour nobody has yet exhibited.
- **Timing settled it.** Slice 3 puts this figure in front of recruiters. A
  contract change is cheap now and expensive once it is filtered into a
  recruiter view, a comparison grid and shortlist evidence strings.

If a real candidate population later shows people abandoning sessions that were
going badly, this is worth reopening — the mechanism does not stop being real
just because it is currently unevidenced.

## What actually changed

`skill_breakdown` and `weak_areas` now take
`(category, analysis, completed_at)` and count completed interviews only.
The third element is **required**: passing a two-element row raises
`ValueError` rather than defaulting, so a caller cannot silently reinstate the
old population.

Both functions filter through one shared helper. They had to: `weak_areas`
derives its weakest *category* from `skill_breakdown`, so filtering one and not
the other would have reproduced the very same split inside a single function.

## Observed effect on the demo candidate

| | before (all-time) | after (completed-only) |
|---|---|---|
| graded answers counted | 19 | 10 |
| technical relevance | 28.0 | 38.2 |
| **weakest axis** | technical_relevance | **confidence (35.5)** |
| practice recommendation | write a one-page explanation | cut hedging language |
| weakest category | database optimization | **none reported** |

Two consequences worth having on the record:

1. **The weakest axis changed**, and with it the advice the candidate is given.
   That is the change working, not a fault — the old answer was partly produced
   by sessions they never finished.
2. **`weakest_category` is now `None`.** With 10 answers spread over seven
   categories, none clears the three-answer bar for a non-provisional result,
   and the existing rule declines to name a weakest category off thinner
   evidence than that. The candidate loses that line until they complete more
   interviews. Correct, and worse-looking than before — an honest absence
   replacing a figure that was resting on abandoned work.

It also shrank the display contradiction Slice 1 was written to explain: the
gap between the lifetime figure and the latest per-interview point fell from
57 points to 34.5. Slice 1's window labelling and reference line stay, because
the two windows are still different — just less alarmingly so.

## Known, accepted consequence

Module 9 has already emailed performance summaries built on the old all-time
figure. Those emails cannot be corrected and will not match what the dashboard
shows from now on. Accepted as a one-time cost of fixing this while the
affected population is one demo account rather than real candidates.
