"""
Module 9 — email, notification wording and reminder rules.

No SMTP server and no database here: the mailer is exercised against a fake
transport, and the compose functions are pure. What is being pinned down is
mostly *wording and honesty*, because that is where this module can do damage —
telling a candidate an email was sent when none was, or reporting a trajectory
from two data points.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services import mailer, notifications as notify  # noqa: E402


def interview(itype="HR", domain="python", score=None, difficulty="EASY"):
    return SimpleNamespace(
        id=1,
        interview_type=SimpleNamespace(value=itype),
        domain=domain,
        difficulty=SimpleNamespace(value=difficulty),
        overall_score=score,
    )


class TestMailer:
    def test_unconfigured_host_skips_rather_than_failing(self, monkeypatch):
        """
        A demo machine with no mail server must not look like a broken one, and
        must never raise into the caller.
        """
        monkeypatch.setattr(settings, "SMTP_HOST", "")
        result = mailer.send_email("a@b.com", "Subject", "Body")
        assert result.sent is False
        assert result.skipped is True
        assert result.status == "skipped"

    def test_a_server_failure_is_reported_as_failed_not_skipped(self, monkeypatch):
        """
        "No server configured" and "the server rejected us" are different
        facts; collapsing them would hide a real fault behind an expected one.
        """
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")

        def boom(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(mailer.smtplib, "SMTP", boom)
        result = mailer.send_email("a@b.com", "Subject", "Body")
        assert result.status == "failed"
        assert result.skipped is False
        assert "connection refused" in result.error

    def test_send_never_raises_whatever_smtplib_does(self, monkeypatch):
        """Email must never break the thing it is reporting on."""
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")

        def boom(*args, **kwargs):
            raise RuntimeError("something unexpected")

        monkeypatch.setattr(mailer.smtplib, "SMTP", boom)
        assert mailer.send_email("a@b.com", "S", "B").sent is False

    def test_message_carries_both_plain_and_html_parts(self):
        message = mailer.build_message("a@b.com", "Subj", "plain", "<p>rich</p>")
        assert message["To"] == "a@b.com"
        assert message["Subject"] == "Subj"
        assert message.is_multipart()

    def test_missing_recipient_is_an_error_not_a_send(self, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
        result = mailer.send_email("", "Subject", "Body")
        assert result.sent is False
        assert result.error


class TestComposedWording:
    def test_scored_report_states_the_score(self):
        title, body = notify.compose_report_ready(interview(score=72.5))
        assert "report is ready" in title
        assert "72.5" in body

    def test_unscored_report_says_so_rather_than_implying_a_score(self):
        """
        The case a candidate most needs telling about. Silence here would leave
        them waiting for a report that is never coming.
        """
        _title, body = notify.compose_report_ready(interview(score=None))
        assert "not been scored" in body
        assert "saved" in body

    def test_reminder_says_progress_is_not_lost(self):
        _title, body = notify.compose_interview_reminder(interview(), 30)
        assert "30 hours" in body
        assert "lost" in body

    def test_summary_with_no_scores_does_not_invent_figures(self):
        trend = {"interviews_scored": 0}
        _title, body = notify.compose_performance_summary("Ana", trend, {"available": False})
        assert "no scored interviews" in body
        assert "Average" not in body

    def test_summary_reports_an_improving_trend(self):
        trend = {
            "interviews_scored": 6, "average": 61.0, "best": 80.0,
            "direction": "improving", "change": 12.0,
        }
        weak = {
            "available": True, "weakest_axis": "technical_relevance",
            "weakest_axis_score": 44.0, "practice_recommendations": ["Do the thing"],
        }
        _title, body = notify.compose_performance_summary("Ana", trend, weak)
        assert "improving" in body
        assert "technical relevance" in body
        assert "Do the thing" in body

    def test_summary_refuses_to_call_a_trend_without_enough_data(self):
        trend = {
            "interviews_scored": 2, "average": 50.0, "best": 60.0,
            "direction": "insufficient_data", "change": None,
        }
        _title, body = notify.compose_performance_summary("Ana", trend, {"available": False})
        assert "not yet enough interviews" in body

    def test_summary_states_it_is_not_a_prediction(self):
        trend = {
            "interviews_scored": 5, "average": 50.0, "best": 60.0,
            "direction": "steady", "change": 1.0,
        }
        weak = {
            "available": True, "weakest_axis": "confidence",
            "weakest_axis_score": 40.0, "practice_recommendations": [],
        }
        _title, body = notify.compose_performance_summary("Ana", trend, weak)
        assert "not a prediction" in body


class TestReminderPolicy:
    def test_a_run_is_capped_so_the_feed_cannot_be_flooded(self):
        """
        A candidate with a long tail of abandoned interviews would otherwise
        get one notification per interview in a single run, burying everything
        else in the feed.
        """
        assert notify.MAX_REMINDERS_PER_RUN <= 10

    def test_the_stale_window_is_generous_enough_to_not_nag(self):
        """Someone who stepped away for an hour has not abandoned anything."""
        assert notify.STALE_INTERVIEW_HOURS >= 12


class TestRoleAwareWording:
    """
    Recruiter- and admin-facing copy.

    The recruiter case has a specific trap: this schema has no
    recruiter-to-candidate assignment, so wording that implies ownership
    ("your candidate") would assert a relationship the data cannot support.
    """

    def test_completion_alert_names_the_candidate_without_claiming_ownership(self):
        title, body = notify.compose_interview_completed("Ana Reyes", interview(score=71.0))
        assert "Ana Reyes" in title
        assert "71.0" in body
        assert "your candidate" not in body.lower()

    def test_completion_alert_says_when_an_interview_went_unscored(self):
        _title, body = notify.compose_interview_completed("Ana Reyes", interview(score=None))
        assert "not been scored" in body

    def test_stalled_digest_is_one_message_about_many_interviews(self):
        """
        A recruiter watches every candidate, so one notification per stalled
        interview would be unreadable. The digest carries the count instead.
        """
        title, body = notify.compose_stalled_digest(23, 24)
        assert "23" in title
        assert "24 hours" in body

    def test_stalled_digest_reads_correctly_for_a_single_interview(self):
        title, _body = notify.compose_stalled_digest(1, 24)
        assert "1 candidate interview left unfinished" in title

    def test_ticket_alert_points_at_the_queue(self):
        title, body = notify.compose_ticket_raised("Sam", "abusive language")
        assert "abusive language" in title
        assert "Sam" in body

    def test_system_alert_is_marked_as_not_candidate_facing(self):
        """Operational detail must not leak to the people being assessed."""
        _title, body = notify.compose_system_alert("Gemini quota", "All keys exhausted.")
        assert "Candidates are not shown it" in body


class TestEmailPreferencePolicy:
    def test_the_preference_defaults_to_on(self):
        """
        Everything sent is transactional — about the user's own interviews or
        their own work queue — so on is the right default. The switch exists so
        it is still a choice.
        """
        from app.models.user import User

        assert User.__table__.c.email_notifications.default.arg is True

    def test_the_preference_is_not_nullable(self):
        """A null preference would be neither on nor off at the check site."""
        from app.models.user import User

        assert User.__table__.c.email_notifications.nullable is False
