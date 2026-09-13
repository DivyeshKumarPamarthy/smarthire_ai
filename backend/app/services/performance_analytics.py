"""
Module 8 — rolling a candidate's whole history up into skills, trends and
weak areas.

Everything here is pure arithmetic over analyses that Module 5 already stored
on each InterviewQuestion. No AI call, no database access: the caller loads the
rows and passes them in, so the same numbers come out wherever they are asked
for and every figure can be traced back to an answer the candidate actually
gave.

Two rules run through all of it, both about not overclaiming:

  A figure is only reported when enough answers stand behind it. One graded
  answer in a category is an anecdote, not a skill level, and presenting it
  beside a category with twelve would invite exactly the wrong comparison. The
  sample size travels with every number so the caller can say so on screen.

  Nothing here forecasts. "Weak area" means the axis a candidate has actually
  scored lowest on across their history, not a prediction about how they will
  do next time — the data supports the first claim and not the second.

ROW SHAPE, and the contract change of 2026-09-11:

  `skill_breakdown` and `weak_areas` take (category, analysis, completed_at)
  and count **completed interviews only**. They previously took
  (category, analysis) and counted every graded answer, including answers from
  interviews a candidate started and abandoned.

  That was inconsistent with `performance_trend`, which has always plotted
  completed interviews only, and the inconsistency became visible once Module
  10 put both figures on one screen: the same candidate's technical relevance
  read 28.0 from one function and 38.2 from the other. See
  docs/plans/module-10-dashboard-analytics/DECISION-weak-areas-population.md
  for the options weighed and why completed-only won.

  The third element is required rather than optional on purpose. Making it
  default would let a caller silently get the old population back, which is the
  exact failure this change exists to remove.
"""

from typing import Dict, List, Optional, Sequence

from app.services.practice_recommendations import WEAK_AXIS_RESOURCES
from app.services.scoring import WEIGHTS, rating_label

# Below this many graded answers a per-category figure is reported but flagged
# as provisional: it is shown, because hiding a candidate's only data point is
# its own kind of dishonesty, but it must never be presented as established.
MIN_ANSWERS_FOR_CONFIDENT_SKILL = 3

# A direction ("improving", "declining") compares two halves of the history
# against each other, which needs enough interviews for each half to mean
# something.
MIN_INTERVIEWS_FOR_TREND = 4

# Score points between the two halves below which the change is called flat
# rather than dressed up as movement.
TREND_FLAT_BAND = 3.0


def _graded_score(analysis: Optional[dict]) -> Optional[dict]:
    """The score block of an analysis, or None when the answer was not graded."""
    if not analysis or not analysis.get("available"):
        return None
    score = analysis.get("score") or {}
    return score if score.get("available") else None


def _mean(values: Sequence[float]) -> Optional[float]:
    return round(sum(values) / len(values), 1) if values else None


def _from_completed_interviews(rows: Sequence[tuple]) -> List[tuple]:
    """
    Drop answers belonging to interviews that were never finished.

    Shared by skill_breakdown and weak_areas rather than written twice, because
    weak_areas derives its weakest *category* from skill_breakdown's output: if
    the two ever filtered differently, a candidate's weakest axis and weakest
    category would be computed over different populations — the same split this
    change exists to remove, reproduced inside one function.
    """
    return [(category, analysis) for category, analysis, completed_at in rows
            if completed_at is not None]


def skill_breakdown(rows: Sequence[tuple]) -> List[dict]:
    """
    Per-category averages of each rubric axis.

    `rows` is a sequence of (category, analysis, completed_at) triples — one
    per answered question across the candidate's interviews. Answers from
    interviews that were never completed are excluded; see the module
    docstring.

    Categories are the question categories Module 3 assigns ("data
    interpretation", "logical reasoning", and so on), which is the closest
    thing the platform has to a skill label. Sorted weakest first, because the
    reason to look at this table is to find what to work on.
    """
    buckets: Dict[str, Dict[str, List[float]]] = {}

    for category, analysis in _from_completed_interviews(rows):
        score = _graded_score(analysis)
        if score is None or not category:
            continue
        bucket = buckets.setdefault(category, {axis: [] for axis in WEIGHTS})
        bucket.setdefault("overall", [])
        for axis in WEIGHTS:
            value = score.get(axis)
            if isinstance(value, (int, float)):
                bucket[axis].append(value)
        overall = score.get("overall")
        if isinstance(overall, (int, float)):
            bucket["overall"].append(overall)

    out: List[dict] = []
    for category, bucket in buckets.items():
        graded = len(bucket["overall"])
        if graded == 0:
            continue
        out.append(
            {
                "category": category,
                "answers_graded": graded,
                "overall": _mean(bucket["overall"]),
                "axes": {
                    axis: _mean(bucket[axis])
                    for axis in WEIGHTS
                    if bucket[axis]
                },
                # Surfaced rather than filtered on, so the UI can show a thin
                # result as provisional instead of the caller silently dropping
                # a category the candidate knows they answered.
                "provisional": graded < MIN_ANSWERS_FOR_CONFIDENT_SKILL,
            }
        )

    out.sort(key=lambda row: (row["overall"] is None, row["overall"]))
    return out


def performance_trend(interviews: Sequence) -> dict:
    """
    Scored interviews in completion order, plus whether the candidate is
    actually moving.

    `interviews` is a sequence of Interview rows. Only those with a score and a
    completion time can appear: an unscored interview is missing data, and
    plotting it as a gap or a zero would both misrepresent it.

    The direction compares the mean of the earlier half against the later half
    rather than fitting a line — with the handful of interviews a candidate
    typically has, a regression slope reads as more precision than the data
    carries.
    """
    scored = [
        iv
        for iv in interviews
        if iv.overall_score is not None and iv.completed_at is not None
    ]
    scored.sort(key=lambda iv: iv.completed_at)

    points = [
        {
            "interview_id": iv.id,
            "completed_at": iv.completed_at,
            "score": round(iv.overall_score, 1),
            "rating": rating_label(iv.overall_score),
            "interview_type": iv.interview_type.value,
            "domain": iv.domain,
            "difficulty": iv.difficulty.value,
        }
        for iv in scored
    ]

    result = {
        "points": points,
        "interviews_scored": len(points),
        "average": _mean([p["score"] for p in points]),
        "best": max((p["score"] for p in points), default=None),
        "direction": "insufficient_data",
        "change": None,
    }

    if len(points) < MIN_INTERVIEWS_FOR_TREND:
        return result

    half = len(points) // 2
    earlier = _mean([p["score"] for p in points[:half]])
    later = _mean([p["score"] for p in points[-half:]])
    change = round(later - earlier, 1)

    result["change"] = change
    if abs(change) < TREND_FLAT_BAND:
        result["direction"] = "steady"
    elif change > 0:
        result["direction"] = "improving"
    else:
        result["direction"] = "declining"

    return result


def weak_areas(rows: Sequence[tuple]) -> dict:
    """
    The axis and the category a candidate has actually scored lowest on.

    Deliberately named for what it is. This is not a forecast of future
    performance — it is the weakest thing in the record so far, which is the
    honest claim the stored answers support and the useful one for deciding
    what to practise.

    Counts completed interviews only — see the module docstring for the change
    and the reasoning behind it.

    Returns available=False when nothing has been graded, so the caller can say
    "no data yet" rather than naming a weakest axis out of four zeros.
    """
    totals: Dict[str, List[float]] = {axis: [] for axis in WEIGHTS}

    for _category, analysis in _from_completed_interviews(rows):
        score = _graded_score(analysis)
        if score is None:
            continue
        for axis in WEIGHTS:
            value = score.get(axis)
            if isinstance(value, (int, float)):
                totals[axis].append(value)

    axis_averages = {axis: _mean(values) for axis, values in totals.items() if values}
    if not axis_averages:
        return {
            "available": False,
            "reason": (
                "No answer from a completed interview has been scored yet, so "
                "there is nothing to compare."
            ),
        }

    weakest_axis = min(axis_averages, key=axis_averages.get)
    graded_answers = max(len(values) for values in totals.values())

    skills = skill_breakdown(rows)
    # skill_breakdown sorts weakest first, so the head is the weakest category
    # — but only report one that is not itself provisional, or the "weakest
    # skill" would often be whichever category the candidate has answered once.
    weakest_skill = next((row for row in skills if not row["provisional"]), None)

    entry = WEAK_AXIS_RESOURCES[weakest_axis]
    return {
        "available": True,
        "axis_averages": axis_averages,
        "weakest_axis": weakest_axis,
        "weakest_axis_score": axis_averages[weakest_axis],
        "weakest_category": weakest_skill["category"] if weakest_skill else None,
        "weakest_category_score": weakest_skill["overall"] if weakest_skill else None,
        "graded_answers": graded_answers,
        "practice_recommendations": [entry["recommendation"]],
        "learning_resources": entry["resources"],
        "provisional": graded_answers < MIN_ANSWERS_FOR_CONFIDENT_SKILL,
        "method_note": (
            "Based on the answers you have given so far, not a prediction of "
            "future performance."
        ),
    }

