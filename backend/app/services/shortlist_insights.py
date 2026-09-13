"""
Module 10 — shortlisting insights.

Rule-based rather than a model call: deterministic, auditable against the
numbers that produced it, and checkable by the recruiter reading it. The same
trade practice_recommendations.py already makes, for the same reason — a
recruiter can verify a rule, and cannot verify an LLM's impression of a person.

Three things this will not do, fixed at Gate 1:

  It never ranks. No "best candidate", no position, no score of its own. The
  leaderboard is the one place this platform ranks people and it says so.

  It never recommends a decision. An insight may say someone is worth a closer
  look and why; it may not say who to hire or reject, or rate "fit".

  It never emits an insight whose reason cannot be shown. `evidence` carries
  the figures that fired the rule, always populated — an insight a recruiter
  cannot check is one they should not be shown.

No recruiter-to-candidate ownership is expressed anywhere, because none exists
in this schema. Wording follows Module 9's precedent.
"""

from typing import Dict, List, Optional, Sequence

# One interview is an anecdote. Two is the floor at which "consistently"
# becomes a word that can honestly be used at all.
MIN_INTERVIEWS_FOR_INSIGHT = 2

# Points above the pool average before a candidate is called strong. Guessed,
# and flagged as such at Gate 3 — tuned against the real pool in the slice that
# built this, see the note at the foot of this module.
STRONG_MARGIN = 10.0

# Points of upward movement before improvement is worth surfacing.
IMPROVING_MARGIN = 10.0

# Below this many scored interviews across the whole pool, "above average" is
# measured against too little to mean anything and no comparative insight is
# emitted at all.
MIN_POOL_FOR_COMPARISON = 3


def pool_baseline(candidate_scores: Sequence[Optional[float]]) -> Dict:
    """
    What "above average" is measured against.

    Returns available=False when the pool is too small to compare against,
    rather than letting one candidate be "above average" relative to two
    others.
    """
    scored = [s for s in candidate_scores if s is not None]
    if len(scored) < MIN_POOL_FOR_COMPARISON:
        return {
            "available": False,
            "average": round(sum(scored) / len(scored), 1) if scored else None,
            "scored_candidates": len(scored),
        }
    return {
        "available": True,
        "average": round(sum(scored) / len(scored), 1),
        "scored_candidates": len(scored),
    }


def insights_for(candidate: Dict, baseline: Dict) -> List[Dict]:
    """
    Zero or more insights about one candidate.

    `candidate` carries: user_id, name, average_score, interviews_scored,
    trend_direction, trend_change, best_skill, best_skill_score,
    best_skill_answers.

    Zero is a normal outcome. Most candidates in most pools are unremarkable
    against these rules, and inventing something to say about them would make
    the panel noise.
    """
    out: List[Dict] = []

    name = candidate.get("name") or f"Candidate {candidate.get('user_id')}"
    scored = candidate.get("interviews_scored") or 0
    average = candidate.get("average_score")

    if scored < MIN_INTERVIEWS_FOR_INSIGHT or average is None:
        # Reported as its own insight rather than silently omitting them: a
        # recruiter scanning the panel should know the difference between "no
        # signal" and "not enough data to have a signal".
        if scored > 0:
            out.append(
                {
                    "kind": "thin_evidence",
                    "candidate_id": candidate["user_id"],
                    "candidate_name": name,
                    "headline": f"{name} has too little history to read yet",
                    "evidence": (
                        f"{scored} scored interview"
                        f"{'' if scored == 1 else 's'} — at least "
                        f"{MIN_INTERVIEWS_FOR_INSIGHT} are needed before any "
                        "pattern here means anything."
                    ),
                    "provisional": True,
                }
            )
        return out

    # --- consistently strong against the pool ---
    if baseline.get("available") and baseline.get("average") is not None:
        margin = average - baseline["average"]
        if margin >= STRONG_MARGIN:
            out.append(
                {
                    "kind": "consistently_strong",
                    "candidate_id": candidate["user_id"],
                    "candidate_name": name,
                    "headline": f"{name} is scoring well above the pool",
                    "evidence": (
                        f"Averaging {average} across {scored} scored "
                        f"interviews, against a pool average of "
                        f"{baseline['average']} over "
                        f"{baseline['scored_candidates']} candidates "
                        f"(+{round(margin, 1)})."
                    ),
                    "provisional": False,
                }
            )

    # --- improving ---
    change = candidate.get("trend_change")
    if candidate.get("trend_direction") == "improving" and change is not None:
        if change >= IMPROVING_MARGIN:
            out.append(
                {
                    "kind": "improving",
                    "candidate_id": candidate["user_id"],
                    "candidate_name": name,
                    "headline": f"{name} is improving across their interviews",
                    "evidence": (
                        f"Up {round(change, 1)} points between the earlier and "
                        f"later halves of {scored} scored interviews."
                    ),
                    "provisional": False,
                }
            )

    # --- a specific strength worth naming ---
    skill = candidate.get("best_skill")
    skill_score = candidate.get("best_skill_score")
    skill_answers = candidate.get("best_skill_answers") or 0
    if skill and skill_score is not None and baseline.get("available"):
        # Two conditions, not one. A candidate's *best* skill is by definition
        # their highest number, so comparing it against the pool's *average
        # overall* is not like-for-like and fires for perfectly middling
        # people. Requiring them to be at or above the pool overall first keeps
        # "strongest in X" from reading as praise for someone below average.
        clears_margin = skill_score - baseline["average"] >= STRONG_MARGIN
        holds_their_own = average >= baseline["average"]
        if clears_margin and holds_their_own:
            out.append(
                {
                    "kind": "strong_in_skill",
                    "candidate_id": candidate["user_id"],
                    "candidate_name": name,
                    "headline": f"{name} is strongest in {skill}",
                    "evidence": (
                        f"{skill_score} in {skill} across {skill_answers} "
                        f"graded answer{'' if skill_answers == 1 else 's'}, "
                        f"against a pool average of {baseline['average']}."
                    ),
                    # The existing three-answer bar, applied here too.
                    "provisional": skill_answers < 3,
                }
            )

    return out


NOTE = (
    "Insights are rules applied to scored interviews, not a recommendation. "
    "Each shows the figures that produced it so it can be checked. Nothing "
    "here ranks candidates or suggests a hiring decision, and no camera or "
    "attention data is used."
)
