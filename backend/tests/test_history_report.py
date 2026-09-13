"""
Module 10, Slice 2 — the candidate's full-history PDF.

Builds real PDF bytes and reads them back with pypdf, so these assert what a
candidate would actually see rather than what the builder was asked to draw.

The empty case matters most. A candidate with nothing scored is the state every
new account starts in, and a report that crashes there is worse than no report
at all.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import report_pdf  # noqa: E402

import io  # noqa: E402


USER = SimpleNamespace(id=1, name="Ana Reyes", email="ana@example.com")


def interview(id_, days_ago=1):
    return SimpleNamespace(
        id=id_,
        completed_at=(
            None if days_ago is None
            else datetime.now(timezone.utc) - timedelta(days=days_ago)
        ),
    )


def point(id_, score, days_ago, itype="HR", domain="python", rating="Average"):
    return {
        "interview_id": id_,
        "completed_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
        "score": score,
        "rating": rating,
        "interview_type": itype,
        "domain": domain,
        "difficulty": "EASY",
    }


def performance(points, *, weak=True, skills=True, progress=True):
    scores = [p["score"] for p in points]
    return {
        "trend": {
            "points": points,
            "interviews_scored": len(points),
            "average": round(sum(scores) / len(scores), 1) if scores else None,
            "best": max(scores) if scores else None,
            "direction": "improving" if len(points) >= 4 else "insufficient_data",
            "change": 12.0 if len(points) >= 4 else None,
        },
        "weak_areas": {
            "available": bool(weak and points),
            "axis_averages": {
                "communication": 60.0, "confidence": 35.5,
                "technical_relevance": 48.0, "professionalism": 52.0,
            } if weak and points else {},
            "weakest_axis": "confidence" if weak and points else None,
            "weakest_axis_score": 35.5 if weak and points else None,
            "weakest_category": "sql" if weak and points else None,
            "weakest_category_score": 40.0 if weak and points else None,
            "graded_answers": len(points) * 2,
            "provisional": False,
            "practice_recommendations": ["Cut hedging language."] if weak and points else [],
            "learning_resources": ["Pramp"] if weak and points else [],
            "method_note": "Based on answers given so far.",
        },
        "skills": [
            {"category": "sql", "answers_graded": 4, "overall": 40.0,
             "axes": {"communication": 40.0}, "provisional": False},
            {"category": "api", "answers_graded": 1, "overall": 80.0,
             "axes": {"communication": 80.0}, "provisional": True},
        ] if skills and points else [],
        "axis_progress": {
            "available": bool(progress and len(points) > 1),
            "axis": "confidence",
            "points": [], "interviews": len(points),
            "first": 20.0, "latest": 55.0,
            "direction": "improving" if len(points) >= 4 else "insufficient_data",
            "change": 20.0,
        },
    }


def text_of(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class TestZeroInterviews:
    """The state every new account is in."""

    def test_no_interviews_at_all_still_produces_a_pdf(self):
        pdf = report_pdf.build_history_report(USER, [], performance([]))
        assert pdf[:4] == b"%PDF"
        assert len(PdfReader(io.BytesIO(pdf)).pages) >= 1

    def test_it_says_why_it_is_empty_rather_than_printing_dashes(self):
        body = text_of(report_pdf.build_history_report(USER, [], performance([])))
        assert "No scored interviews yet" in body
        assert "saved either way" in body

    def test_interviews_taken_but_none_scored(self):
        """Started three, finished none — the report must not claim a history."""
        interviews = [interview(i, days_ago=None) for i in range(3)]
        body = text_of(report_pdf.build_history_report(USER, interviews, performance([])))
        assert "No scored interviews yet" in body
        assert "Interviews taken" in body

    def test_empty_performance_dict_does_not_crash(self):
        """Defensive: a caller passing nothing useful still gets a document."""
        pdf = report_pdf.build_history_report(USER, [], {})
        assert pdf[:4] == b"%PDF"


class TestOneInterview:
    def test_a_single_scored_interview_produces_a_report(self):
        points = [point(1, 42.0, 5)]
        pdf = report_pdf.build_history_report(USER, [interview(1)], performance(points))
        body = text_of(pdf)
        assert "Interview history" in body
        assert "Ana Reyes" in body
        assert "42" in body

    def test_no_direction_is_claimed_from_one_interview(self):
        points = [point(1, 42.0, 5)]
        body = text_of(
            report_pdf.build_history_report(USER, [interview(1)], performance(points))
        )
        assert "not enough interviews to say" in body
        assert "improving" not in body.lower().split("Where you are weakest")[0]


class TestManyInterviews:
    @pytest.fixture
    def many(self):
        points = [
            point(1, 20.0, 40, rating="Poor"),
            point(2, 35.0, 30, rating="Poor"),
            point(3, 61.0, 20, rating="Average"),
            point(4, 78.0, 10, rating="Good"),
            point(5, 84.0, 2, rating="Good"),
        ]
        interviews = [interview(p["interview_id"]) for p in points]
        return interviews, performance(points)

    def test_every_interview_appears(self, many):
        interviews, perf = many
        body = text_of(report_pdf.build_history_report(USER, interviews, perf))
        for p in perf["trend"]["points"]:
            assert str(p["score"]) in body, p

    def test_it_reports_the_direction_once_there_are_enough(self, many):
        interviews, perf = many
        body = text_of(report_pdf.build_history_report(USER, interviews, perf))
        assert "improving" in body

    def test_the_weakest_axis_and_its_advice_are_present(self, many):
        interviews, perf = many
        body = text_of(report_pdf.build_history_report(USER, interviews, perf))
        assert "Confidence" in body
        assert "35.5" in body
        assert "Cut hedging language" in body

    def test_provisional_categories_are_marked(self, many):
        interviews, perf = many
        body = text_of(report_pdf.build_history_report(USER, interviews, perf))
        assert "provisional" in body


class TestWindowIsUnambiguousInPrint:
    """
    Slice 1's requirement, carried into a document that has no dashed reference
    line and no adjacent copy to reconcile two figures.
    """

    @pytest.fixture
    def body(self):
        points = [point(i, 20.0 + i * 15, 40 - i * 8) for i in range(1, 6)]
        return text_of(
            report_pdf.build_history_report(
                USER, [interview(p["interview_id"]) for p in points], performance(points)
            )
        )

    def test_the_lifetime_figures_name_their_window(self, body):
        assert "averaged across all" in body
        assert "completed interviews" in body

    def test_the_per_interview_table_names_its_window(self, body):
        assert "one row per interview" in body

    def test_it_says_the_two_are_not_a_disagreement(self, body):
        """
        The reconciliation the dashboard does visually has to be done in words
        here, because a saved file is read alone months later.
        """
        assert "difference between the two, not a disagreement" in body

    def test_it_states_that_unfinished_interviews_are_excluded(self, body):
        assert "did not finish" in body or "completed interviews only" in body
