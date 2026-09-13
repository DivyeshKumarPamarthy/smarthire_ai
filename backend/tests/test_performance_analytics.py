"""
Module 8 — skills, trends and weak areas.

Pure unit tests: the service takes rows in and returns numbers, with no
database and no AI call, so everything here is exact rather than approximate.

The cases that matter most are the ones about *not overclaiming* — a single
graded answer must not be presented as a settled skill level, and a handful of
interviews must not be dressed up as a trajectory. Those are the ways this
screen could quietly mislead a candidate about their own record.

REWRITTEN 2026-09-11 for a deliberate contract change. `skill_breakdown` and
`weak_areas` now take (category, analysis, completed_at) and count **completed
interviews only**; they previously took (category, analysis) and counted every
graded answer, including answers from abandoned interviews.

This file is normally treated as frozen — Module 10's slices are required to
leave it untouched, because an edit here is the signal that a change meant to
be additive was not. This rewrite is the sanctioned exception: the contract is
being changed on purpose and the tests are updated to match, which is a
different act from a contract drifting silently. The reasoning is in
docs/plans/module-10-dashboard-analytics/DECISION-weak-areas-population.md.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import performance_analytics as pa  # noqa: E402


COMPLETED = datetime(2026, 9, 1, tzinfo=timezone.utc)


def answer(category, *, communication=50, confidence=50, technical=50, professionalism=50,
           overall=50.0, graded=True, analysed=True, completed_at=COMPLETED):
    """
    One (category, analysis, completed_at) row as Module 5 stores it.

    `completed_at=None` means the answer belongs to an interview the candidate
    never finished. It defaults to a completed interview so the tests that are
    not about the population stay readable.
    """
    if not analysed:
        return (category, None, completed_at)
    return (
        category,
        {
            "available": True,
            "score": {
                "available": graded,
                "communication": communication,
                "confidence": confidence,
                "technical_relevance": technical,
                "professionalism": professionalism,
                "overall": overall,
            },
        },
        completed_at,
    )


def interview(id_, score, days_ago, *, itype="HR", domain="python", difficulty="EASY"):
    return SimpleNamespace(
        id=id_,
        overall_score=score,
        completed_at=(
            None if days_ago is None
            else datetime.now(timezone.utc) - timedelta(days=days_ago)
        ),
        interview_type=SimpleNamespace(value=itype),
        domain=domain,
        difficulty=SimpleNamespace(value=difficulty),
    )


class TestSkillBreakdown:
    def test_averages_each_axis_within_a_category(self):
        rows = [
            answer("sql", communication=60, technical=40, overall=50.0),
            answer("sql", communication=80, technical=60, overall=70.0),
        ]
        [skill] = pa.skill_breakdown(rows)
        assert skill["category"] == "sql"
        assert skill["answers_graded"] == 2
        assert skill["overall"] == 60.0
        assert skill["axes"]["communication"] == 70.0
        assert skill["axes"]["technical_relevance"] == 50.0

    def test_weakest_category_comes_first(self):
        rows = [
            answer("strong", overall=90.0),
            answer("weak", overall=20.0),
            answer("middling", overall=55.0),
        ]
        assert [s["category"] for s in pa.skill_breakdown(rows)] == ["weak", "middling", "strong"]

    def test_skill_breakdown_sorts_weakest_first(self):
        """
        The ordering is a contract, not an implementation detail.

        `shortlist_insights` reads the *tail* of this list as a candidate's
        strongest skill (`best = skills[-1]` in the shortlist endpoint). If this
        sort were ever inverted, that code would keep working silently and
        start publishing someone's weakest area as their headline strength in
        front of a recruiter.

        Asserted here separately from test_weakest_category_comes_first on
        purpose: that test is named for the weakest-first property and someone
        changing the sort might reasonably update it. This one names the
        consumer, so the coupling cannot be edited away without reading why it
        exists.
        """
        rows = [
            answer("middling", overall=55.0),
            answer("strongest", overall=95.0),
            answer("weakest", overall=5.0),
        ]
        ordered = pa.skill_breakdown(rows)

        assert [s["category"] for s in ordered] == ["weakest", "middling", "strongest"]
        # The two ends, stated as the consumers read them.
        assert ordered[0]["category"] == "weakest"
        assert ordered[-1]["category"] == "strongest", (
            "shortlist_insights takes skills[-1] as the strongest skill"
        )

    def test_skill_breakdown_tail_is_strongest_even_with_two_categories(self):
        """The smallest list where head and tail differ — the boundary case."""
        rows = [answer("high", overall=80.0), answer("low", overall=20.0)]
        ordered = pa.skill_breakdown(rows)
        assert ordered[0]["category"] == "low"
        assert ordered[-1]["category"] == "high"

    def test_thin_evidence_is_flagged_not_hidden(self):
        """
        One answer is the candidate's real data and must still appear — but it
        cannot be presented as settled beside a category with three.
        """
        rows = [answer("thin", overall=10.0)] + [answer("thick", overall=80.0) for _ in range(3)]
        by_category = {s["category"]: s for s in pa.skill_breakdown(rows)}
        assert by_category["thin"]["provisional"] is True
        assert by_category["thick"]["provisional"] is False

    def test_ungraded_and_unanalysed_answers_are_ignored(self):
        """A skipped or failed answer is missing data, never a zero."""
        rows = [
            answer("sql", overall=80.0),
            answer("sql", graded=False),
            answer("sql", analysed=False),
        ]
        [skill] = pa.skill_breakdown(rows)
        assert skill["answers_graded"] == 1
        assert skill["overall"] == 80.0

    def test_no_graded_answers_gives_no_rows(self):
        assert pa.skill_breakdown([answer("sql", graded=False)]) == []


class TestPerformanceTrend:
    def test_points_are_ordered_oldest_first(self):
        trend = pa.performance_trend([
            interview(1, 50.0, days_ago=1),
            interview(2, 30.0, days_ago=9),
            interview(3, 40.0, days_ago=5),
        ])
        assert [p["interview_id"] for p in trend["points"]] == [2, 3, 1]

    def test_unscored_interviews_never_appear(self):
        """An unscored interview is missing data — plotting it as zero would lie."""
        trend = pa.performance_trend([
            interview(1, 50.0, days_ago=1),
            interview(2, None, days_ago=2),
            interview(3, 60.0, days_ago=None),  # scored but never completed
        ])
        assert trend["interviews_scored"] == 1
        assert [p["interview_id"] for p in trend["points"]] == [1]

    def test_no_direction_is_claimed_below_the_threshold(self):
        trend = pa.performance_trend([
            interview(i, 50.0, days_ago=10 - i) for i in range(3)
        ])
        assert trend["direction"] == "insufficient_data"
        assert trend["change"] is None

    def test_improving_is_reported_when_later_half_is_higher(self):
        scores = [20.0, 25.0, 70.0, 75.0]
        trend = pa.performance_trend([
            interview(i, s, days_ago=10 - i) for i, s in enumerate(scores)
        ])
        assert trend["direction"] == "improving"
        assert trend["change"] == pytest.approx(50.0)

    def test_declining_is_reported_when_later_half_is_lower(self):
        scores = [80.0, 75.0, 30.0, 25.0]
        trend = pa.performance_trend([
            interview(i, s, days_ago=10 - i) for i, s in enumerate(scores)
        ])
        assert trend["direction"] == "declining"
        assert trend["change"] < 0

    def test_small_movement_is_called_steady_not_dressed_up(self):
        scores = [50.0, 51.0, 51.0, 52.0]
        trend = pa.performance_trend([
            interview(i, s, days_ago=10 - i) for i, s in enumerate(scores)
        ])
        assert trend["direction"] == "steady"

    def test_empty_history(self):
        trend = pa.performance_trend([])
        assert trend["interviews_scored"] == 0
        assert trend["average"] is None
        assert trend["direction"] == "insufficient_data"


class TestWeakAreas:
    def test_identifies_the_lowest_axis(self):
        rows = [answer("sql", communication=80, confidence=70, technical=20, professionalism=90)]
        weak = pa.weak_areas(rows)
        assert weak["available"] is True
        assert weak["weakest_axis"] == "technical_relevance"
        assert weak["weakest_axis_score"] == 20.0

    def test_recommendations_follow_the_weakest_axis(self):
        rows = [answer("sql", communication=90, confidence=20, technical=90, professionalism=90)]
        weak = pa.weak_areas(rows)
        assert weak["weakest_axis"] == "confidence"
        assert weak["practice_recommendations"]
        assert weak["learning_resources"]

    def test_weakest_category_skips_thinly_evidenced_ones(self):
        """
        A category answered once must not be named as the weakest skill just
        for being lowest — that would send the candidate off practising
        whatever they happened to answer badly a single time.
        """
        rows = [answer("one-off", overall=5.0)] + [
            answer("real", overall=40.0) for _ in range(3)
        ]
        weak = pa.weak_areas(rows)
        assert weak["weakest_category"] == "real"

    def test_unavailable_when_nothing_is_graded(self):
        weak = pa.weak_areas([answer("sql", graded=False)])
        assert weak["available"] is False
        assert "reason" in weak

    def test_states_that_it_is_not_a_prediction(self):
        """
        The spec calls this "weak-area prediction". The data supports a claim
        about answers already given and not a forecast, so the payload has to
        say which of the two it is.
        """
        weak = pa.weak_areas([answer("sql")])
        assert "not a prediction" in weak["method_note"]


class TestCompletedInterviewsOnly:
    """
    The contract change of 2026-09-11, tested directly.

    These are the tests that would have caught the split in the first place:
    before this change `skill_breakdown` and `weak_areas` counted answers from
    abandoned interviews while `performance_trend` refused to plot them, and
    nothing asserted that the three agreed about which interviews exist.
    """

    ABANDONED = None  # an interview the candidate started and never finished

    def test_skill_breakdown_excludes_abandoned_answers(self):
        rows = [
            answer("sql", overall=80.0),
            answer("sql", overall=10.0, completed_at=self.ABANDONED),
        ]
        [skill] = pa.skill_breakdown(rows)
        assert skill["answers_graded"] == 1
        assert skill["overall"] == 80.0

    def test_weak_areas_excludes_abandoned_answers(self):
        rows = [
            answer("sql", technical=80),
            answer("sql", technical=10, completed_at=self.ABANDONED),
        ]
        assert pa.weak_areas(rows)["axis_averages"]["technical_relevance"] == 80.0

    def test_an_abandoned_only_category_does_not_appear_at_all(self):
        """Not zero, not provisional — absent. It was never assessed."""
        rows = [
            answer("finished", overall=70.0),
            answer("walked_out", overall=5.0, completed_at=self.ABANDONED),
        ]
        assert [s["category"] for s in pa.skill_breakdown(rows)] == ["finished"]

    def test_all_answers_abandoned_reads_as_no_data(self):
        rows = [answer("sql", overall=40.0, completed_at=self.ABANDONED)]
        assert pa.skill_breakdown(rows) == []
        weak = pa.weak_areas(rows)
        assert weak["available"] is False
        assert "completed interview" in weak["reason"]

    def test_weakest_axis_and_weakest_category_share_one_population(self):
        """
        The trap this change had to avoid. `weak_areas` derives its weakest
        *category* from `skill_breakdown`, so if the two filtered differently a
        candidate's weakest axis and weakest category would be computed over
        different sets of answers — the same split, reproduced inside a single
        function.
        """
        rows = (
            [answer("finished", technical=70, overall=70.0) for _ in range(3)]
            + [answer("abandoned", technical=1, overall=1.0,
                      completed_at=self.ABANDONED) for _ in range(3)]
        )
        weak = pa.weak_areas(rows)
        assert weak["weakest_category"] == "finished"
        assert weak["axis_averages"]["technical_relevance"] == 70.0

    def test_the_three_functions_agree_about_which_interviews_exist(self):
        """
        performance_trend has always excluded unfinished interviews. After this
        change all three agree, which is the whole point of making it.
        """
        rows = [
            answer("sql", overall=80.0),
            answer("sql", overall=10.0, completed_at=self.ABANDONED),
        ]
        trend = pa.performance_trend([
            interview(1, 80.0, days_ago=1),
            interview(2, 10.0, days_ago=None),  # never completed
        ])
        assert trend["interviews_scored"] == 1
        assert pa.skill_breakdown(rows)[0]["answers_graded"] == 1
        assert pa.weak_areas(rows)["graded_answers"] == 1

    def test_completion_is_required_not_optional(self):
        """
        A two-element row must fail loudly. Accepting it would let a caller
        silently reinstate the old all-time population, which is precisely the
        failure this change removes.
        """
        with pytest.raises(ValueError):
            pa.skill_breakdown([("sql", {"available": True})])
