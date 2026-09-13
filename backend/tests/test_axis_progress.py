"""
Module 10, Slice 1 — movement on one named rubric axis.

Pure unit tests: rows in, numbers out, no database and no AI.

The test that defines the feature is
`test_tracks_the_named_axis_not_the_overall_score`. Everything else here is
guarding the edges around it.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import performance_analytics as pa  # noqa: E402


def graded(**axes):
    """One answer's analysis, shaped exactly as Module 5 stores it."""
    score = {
        "available": True,
        "communication": 50,
        "confidence": 50,
        "technical_relevance": 50,
        "professionalism": 50,
        "overall": 50.0,
    }
    score.update(axes)
    return {"available": True, "score": score}


UNGRADED = {"available": True, "score": {"available": False}}
UNANALYSED = None


def interview(id_, days_ago, analyses):
    completed = (
        None if days_ago is None
        else datetime.now(timezone.utc) - timedelta(days=days_ago)
    )
    return (id_, completed, analyses)


class TestTheDefiningCase:
    def test_tracks_the_named_axis_not_the_overall_score(self):
        """
        A candidate becomes more fluent while the technical relevance they were
        told to fix does not move. The overall score rises; the axis does not.
        A dashboard that called that progress would be lying to the person it
        is supposed to help.
        """
        rows = [
            interview(1, 40, [graded(communication=20, technical_relevance=30, overall=25.0)]),
            interview(2, 30, [graded(communication=45, technical_relevance=30, overall=38.0)]),
            interview(3, 20, [graded(communication=70, technical_relevance=31, overall=52.0)]),
            interview(4, 10, [graded(communication=90, technical_relevance=29, overall=64.0)]),
        ]

        technical = pa.axis_progress(rows, "technical_relevance")
        assert technical["direction"] == "steady"
        assert abs(technical["change"]) < pa.TREND_FLAT_BAND

        # The same history, read on the axis that actually moved.
        communication = pa.axis_progress(rows, "communication")
        assert communication["direction"] == "improving"


class TestOrderingAndShape:
    def test_points_are_ordered_oldest_first(self):
        rows = [
            interview(1, 5, [graded(confidence=70)]),
            interview(2, 50, [graded(confidence=10)]),
            interview(3, 25, [graded(confidence=40)]),
        ]
        progress = pa.axis_progress(rows, "confidence")
        assert [p["interview_id"] for p in progress["points"]] == [2, 3, 1]

    def test_first_and_latest_are_the_raw_endpoints(self):
        rows = [
            interview(1, 30, [graded(confidence=20)]),
            interview(2, 20, [graded(confidence=55)]),
            interview(3, 10, [graded(confidence=80)]),
        ]
        progress = pa.axis_progress(rows, "confidence")
        assert progress["first"] == 20.0
        assert progress["latest"] == 80.0

    def test_an_interviews_axis_score_averages_its_graded_answers(self):
        rows = [interview(1, 5, [graded(confidence=40), graded(confidence=60)])]
        progress = pa.axis_progress(rows, "confidence")
        assert progress["points"][0]["score"] == 50.0


class TestDirection:
    def _history(self, values):
        return [
            interview(i, 50 - i * 5, [graded(confidence=v)])
            for i, v in enumerate(values)
        ]

    def test_no_direction_below_four_interviews(self):
        """
        The same floor performance_trend uses. An axis must not be laxer about
        claiming a trajectory than the score it feeds.
        """
        progress = pa.axis_progress(self._history([10, 50, 90]), "confidence")
        assert progress["direction"] == "insufficient_data"
        assert progress["change"] is None
        assert progress["available"] is True  # points are still shown

    def test_improving_is_reported(self):
        progress = pa.axis_progress(self._history([20, 25, 70, 75]), "confidence")
        assert progress["direction"] == "improving"
        assert progress["change"] > 0

    def test_declining_is_reported(self):
        progress = pa.axis_progress(self._history([80, 75, 30, 25]), "confidence")
        assert progress["direction"] == "declining"
        assert progress["change"] < 0

    def test_small_movement_is_called_steady(self):
        progress = pa.axis_progress(self._history([50, 51, 51, 52]), "confidence")
        assert progress["direction"] == "steady"


class TestMissingData:
    def test_ungraded_answers_are_skipped_not_zeroed(self):
        rows = [interview(1, 5, [graded(confidence=80), UNGRADED, UNANALYSED])]
        progress = pa.axis_progress(rows, "confidence")
        assert progress["points"][0]["score"] == 80.0

    def test_an_interview_with_nothing_graded_is_absent_not_zero(self):
        """Missing data and a score of zero are different facts."""
        rows = [
            interview(1, 20, [graded(confidence=60)]),
            interview(2, 10, [UNGRADED]),
        ]
        progress = pa.axis_progress(rows, "confidence")
        assert progress["interviews"] == 1
        assert [p["interview_id"] for p in progress["points"]] == [1]

    def test_incomplete_interviews_never_appear(self):
        rows = [
            interview(1, 10, [graded(confidence=60)]),
            interview(2, None, [graded(confidence=99)]),
        ]
        progress = pa.axis_progress(rows, "confidence")
        assert [p["interview_id"] for p in progress["points"]] == [1]

    def test_unavailable_when_the_axis_was_never_graded(self):
        progress = pa.axis_progress([interview(1, 5, [UNGRADED])], "confidence")
        assert progress["available"] is False
        assert progress["reason"]
        assert progress["points"] == []

    def test_empty_history(self):
        progress = pa.axis_progress([], "confidence")
        assert progress["available"] is False
        assert progress["interviews"] == 0

    def test_the_axis_is_always_named_back(self):
        """The caller must be able to label the chart even when there is no data."""
        for rows in ([], [interview(1, 5, [UNGRADED])], [interview(1, 5, [graded()])]):
            assert pa.axis_progress(rows, "professionalism")["axis"] == "professionalism"
