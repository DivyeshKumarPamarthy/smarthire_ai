"""
Module 10, Slice 5 — shortlisting insights.

Pure rules over summary dictionaries. The tests that matter most are the
structural ones: an insight that cannot show its reason must not exist, and
nothing here may become a ranking or a hiring recommendation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import shortlist_insights as si  # noqa: E402


def candidate(user_id=1, name="Ana Reyes", average=60.0, scored=4,
              direction="steady", change=1.0, skill="sql", skill_score=42.5,
              skill_answers=4):
    return {
        "user_id": user_id,
        "name": name,
        "average_score": average,
        "interviews_scored": scored,
        "trend_direction": direction,
        "trend_change": change,
        "best_skill": skill,
        "best_skill_score": skill_score,
        "best_skill_answers": skill_answers,
    }


POOL = si.pool_baseline([40.0, 45.0, 35.0, 50.0])   # average 42.5


class TestEvidenceAndStructure:
    def _all_insights(self):
        cases = [
            candidate(average=90.0, skill_score=95.0),
            candidate(user_id=2, average=70.0, direction="improving", change=25.0),
            candidate(user_id=3, scored=1),
            candidate(user_id=4, average=20.0),
            candidate(user_id=5, average=80.0, skill_answers=1),
        ]
        out = []
        for c in cases:
            out.extend(si.insights_for(c, POOL))
        return out

    def test_every_insight_carries_evidence(self):
        """
        Gate 1: an insight whose reason cannot be shown is not shown at all.
        A recruiter who cannot check it should not be handed it.
        """
        insights = self._all_insights()
        assert insights
        for insight in insights:
            assert insight["evidence"].strip(), insight

    def test_every_insight_names_the_candidate_and_its_kind(self):
        for insight in self._all_insights():
            assert insight["candidate_name"]
            assert insight["kind"]
            assert isinstance(insight["candidate_id"], int)

    def test_never_emits_a_rank_or_a_recommendation(self):
        """
        Structural. This platform scores mock interviews with an AI that can be
        wrong; it may say someone is worth a look and why, never who to hire.
        """
        banned = ("rank", "position", "best candidate", "hire", "reject",
                  "shortlist them", "top candidate", "fit score")
        for insight in self._all_insights():
            blob = f"{insight['kind']} {insight['headline']} {insight['evidence']}".lower()
            for word in banned:
                assert word not in blob, f"{word!r} in {insight}"

    def test_no_insight_claims_ownership_of_a_candidate(self):
        """Module 9's precedent: this schema has no recruiter assignment."""
        for insight in self._all_insights():
            blob = f"{insight['headline']} {insight['evidence']}".lower()
            assert "your candidate" not in blob


class TestRules:
    def test_no_insight_from_a_single_interview(self):
        insights = si.insights_for(candidate(scored=1), POOL)
        assert [i["kind"] for i in insights] == ["thin_evidence"]

    def test_thin_evidence_is_flagged_not_silently_promoted(self):
        [insight] = si.insights_for(candidate(scored=1), POOL)
        assert insight["provisional"] is True
        assert "1 scored interview" in insight["evidence"]

    def test_no_insight_at_all_with_nothing_scored(self):
        assert si.insights_for(candidate(scored=0, average=None), POOL) == []

    def test_strong_candidate_is_surfaced_with_the_margin_stated(self):
        insights = si.insights_for(candidate(average=90.0), POOL)
        strong = [i for i in insights if i["kind"] == "consistently_strong"]
        assert strong
        assert "42.5" in strong[0]["evidence"]      # the baseline
        assert "90" in strong[0]["evidence"]        # their figure

    def test_an_average_candidate_gets_no_insight(self):
        """Most candidates are unremarkable; inventing something is noise."""
        assert si.insights_for(candidate(average=44.0), POOL) == []

    def test_improving_candidate_is_surfaced(self):
        insights = si.insights_for(
            candidate(average=44.0, direction="improving", change=30.0), POOL
        )
        assert [i["kind"] for i in insights] == ["improving"]
        assert "30" in insights[0]["evidence"]

    def test_small_improvement_is_not_surfaced(self):
        insights = si.insights_for(
            candidate(average=44.0, direction="improving", change=2.0), POOL
        )
        assert insights == []

    def test_a_skill_strength_is_flagged_provisional_on_thin_evidence(self):
        insights = si.insights_for(
            candidate(average=44.0, skill_score=90.0, skill_answers=1), POOL
        )
        skill = [i for i in insights if i["kind"] == "strong_in_skill"]
        assert skill and skill[0]["provisional"] is True


class TestPoolBaseline:
    def test_too_small_a_pool_is_not_comparable(self):
        """One candidate "above average" relative to two others means nothing."""
        baseline = si.pool_baseline([50.0, 60.0])
        assert baseline["available"] is False

    def test_no_comparative_insight_without_a_usable_baseline(self):
        thin = si.pool_baseline([50.0, 60.0])
        insights = si.insights_for(candidate(average=99.0), thin)
        assert [i["kind"] for i in insights] == []

    def test_unscored_candidates_do_not_drag_the_average(self):
        baseline = si.pool_baseline([40.0, 50.0, 60.0, None, None])
        assert baseline["average"] == 50.0
        assert baseline["scored_candidates"] == 3

    def test_empty_pool_produces_no_insights_rather_than_an_error(self):
        baseline = si.pool_baseline([])
        assert baseline["available"] is False
        assert si.insights_for(candidate(scored=0, average=None), baseline) == []


class TestSkillStrengthIsLikeForLike:
    """
    A candidate's best skill is by definition their highest number. Comparing
    it against the pool's average *overall* score is not like-for-like, and
    without a second condition it fires for people who are below the pool.
    """

    def test_a_below_average_candidate_is_not_called_strong_in_a_skill(self):
        insights = si.insights_for(
            candidate(average=30.0, skill_score=90.0, skill_answers=6), POOL
        )
        assert [i for i in insights if i["kind"] == "strong_in_skill"] == []

    def test_an_above_average_candidate_with_a_standout_skill_is(self):
        insights = si.insights_for(
            candidate(average=60.0, skill_score=90.0, skill_answers=6), POOL
        )
        skill = [i for i in insights if i["kind"] == "strong_in_skill"]
        assert skill and skill[0]["provisional"] is False
