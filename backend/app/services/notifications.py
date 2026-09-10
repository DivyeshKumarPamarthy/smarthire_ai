"""
Module 9 — creating notifications, and optionally emailing them.

Every notification is written to the database first and emailed second. The
in-app feed is what the user is guaranteed to get; email is a delivery channel
that may be unconfigured, slow or broken, and none of those may cost the user
the notification itself.

The compose functions are separate from `notify` so their wording can be tested
without a database or a mail server anywhere in the picture.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.interview import Interview, SessionStatus
from app.models.notification import EmailStatus, Notification, NotificationKind
from app.models.user import User
from app.services import mailer

logger = logging.getLogger(__name__)

# How long an in-progress interview sits untouched before it is worth a nudge.
# Deliberately generous: a candidate who stepped away for lunch should not come
# back to a reminder telling them they abandoned something.
STALE_INTERVIEW_HOURS = 24

# Most reminders one run will raise. A candidate with a long tail of abandoned
# interviews would otherwise get a notification for every one of them at once,
# which buries anything else in the feed and reads as spam rather than help.
# The oldest are reminded about first, and the rest surface on later runs as
# the earlier ones age out of the de-duplication window.
MAX_REMINDERS_PER_RUN = 5


def notify(
    db: Session,
    user: User,
    *,
    kind: NotificationKind,
    title: str,
    body: str,
    interview_id: Optional[int] = None,
    send_email: bool = False,
) -> Notification:
    """
    Record a notification, and email it when asked to.

    Commits the notification before attempting delivery, so a mail server that
    hangs cannot cost the user the record of what happened.
    """
    notification = Notification(
        user_id=user.id,
        kind=kind,
        title=title,
        body=body,
        interview_id=interview_id,
        email_status=EmailStatus.NOT_ATTEMPTED,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    if not send_email:
        return notification

    # The user's own switch, checked here rather than at every call site so a
    # new trigger cannot forget it and mail someone who opted out.
    if not getattr(user, "email_notifications", True):
        notification.email_status = EmailStatus.SKIPPED
        notification.email_error = "This user has automated email switched off."
        db.commit()
        db.refresh(notification)
        return notification

    result = mailer.send_email(user.email, title, body)
    notification.email_status = {
        "sent": EmailStatus.SENT,
        "skipped": EmailStatus.SKIPPED,
        "failed": EmailStatus.FAILED,
    }[result.status]
    notification.email_error = result.error
    db.commit()
    db.refresh(notification)
    return notification


# ----------------------------------------------------------------- composers


def compose_report_ready(interview: Interview) -> tuple[str, str]:
    """Scoring finished and there is something to read."""
    scored = interview.overall_score is not None
    title = f"Your {interview.interview_type.value} interview report is ready"

    if scored:
        body = (
            f"Your {interview.interview_type.value} interview on "
            f"{interview.domain} has been scored.\n\n"
            f"Overall score: {interview.overall_score}\n\n"
            "Open it from your interview history to see the score broken down "
            "by rubric axis, the transcript of each answer, and what to "
            "practise next."
        )
    else:
        # Said plainly rather than dressed up. A candidate whose interview was
        # recorded but not scored needs to know which of the two happened.
        body = (
            f"Your {interview.interview_type.value} interview on "
            f"{interview.domain} is complete.\n\n"
            "It has not been scored — the recordings are saved, but the "
            "analysis did not finish. Your answers are not lost, and the "
            "interview can be scored again later."
        )

    return title, body


def compose_interview_reminder(interview: Interview, hours_idle: int) -> tuple[str, str]:
    """An interview left in progress."""
    title = f"You have an unfinished {interview.interview_type.value} interview"
    body = (
        f"Your {interview.interview_type.value} interview on "
        f"{interview.domain} has been open for about {hours_idle} hours "
        "without being finished.\n\n"
        "You can pick it up where you left off — it resumes at the next "
        "question you have not answered. Nothing you have already recorded is "
        "lost, and finishing it is what produces your score and report."
    )
    return title, body


def compose_session_alert(interview: Interview, reason: str) -> tuple[str, str]:
    """Something happened during a session that the candidate should know."""
    title = f"Session alert — {interview.interview_type.value} interview"
    body = (
        f"During your {interview.interview_type.value} interview on "
        f"{interview.domain}:\n\n{reason}\n\n"
        "Your recordings are saved regardless."
    )
    return title, body


def compose_performance_summary(name: str, trend: dict, weak: dict) -> tuple[str, str]:
    """
    A roll-up of where the candidate stands, from the Module 8 aggregates.

    Written to be readable on its own in an inbox, so it repeats the figures
    rather than linking out to them.
    """
    title = "Your interview performance summary"

    lines = [f"Hello {name},", ""]

    scored = trend.get("interviews_scored", 0)
    if scored == 0:
        lines.append(
            "You have no scored interviews yet. Finish one and this summary "
            "will start tracking how you are doing."
        )
        return title, "\n".join(lines)

    lines.append(
        f"You have completed {scored} scored interview"
        f"{'' if scored == 1 else 's'}."
    )
    lines.append(f"Average score: {trend.get('average')}")
    lines.append(f"Best score: {trend.get('best')}")

    direction = trend.get("direction")
    if direction == "improving":
        lines.append(f"Your scores are improving — up {trend.get('change')} points.")
    elif direction == "declining":
        lines.append(f"Your scores have fallen {abs(trend.get('change', 0))} points.")
    elif direction == "steady":
        lines.append("Your scores are holding steady.")
    else:
        # Never invent a trajectory out of two data points.
        lines.append(
            "There are not yet enough interviews to say which way you are "
            "trending."
        )

    if weak.get("available"):
        lines += [
            "",
            f"Weakest area: {weak['weakest_axis'].replace('_', ' ')} "
            f"({weak['weakest_axis_score']}).",
        ]
        for item in weak.get("practice_recommendations", []):
            lines.append(f"Practice next: {item}")
        lines.append("")
        lines.append(
            "This is based on the answers you have given so far, not a "
            "prediction of future performance."
        )

    return title, "\n".join(lines)


# ------------------------------------------------------------------ reminders


def stale_interviews(db: Session, user: User, hours: int = STALE_INTERVIEW_HOURS) -> List[Interview]:
    """
    In-progress interviews the candidate has left sitting.

    Uses `started_at` rather than `created_at`: an interview generated and
    never opened is not something the candidate abandoned, and nagging them
    about it would be noise.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return (
        db.query(Interview)
        .filter(
            Interview.user_id == user.id,
            Interview.status.in_([SessionStatus.IN_PROGRESS, SessionStatus.PAUSED]),
            Interview.started_at.isnot(None),
            Interview.started_at < cutoff,
        )
        .order_by(Interview.started_at)
        .all()
    )


def already_reminded(db: Session, user: User, interview_id: int, within_hours: int = 24) -> bool:
    """
    Has this interview already been the subject of a recent reminder?

    Without this, every call to the reminder endpoint would produce another
    identical notification for the same abandoned interview, and the feed would
    fill with duplicates of one fact.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.interview_id == interview_id,
            Notification.kind == NotificationKind.INTERVIEW_REMINDER,
            Notification.created_at >= cutoff,
        )
        .first()
        is not None
    )


# ------------------------------------------------- recruiter and admin


def compose_interview_completed(candidate_name: str, interview: Interview) -> tuple[str, str]:
    """
    For recruiters: a candidate finished an interview.

    Platform-wide rather than "your candidate" — this schema has no
    recruiter-to-candidate assignment, so claiming ownership in the wording
    would assert a relationship that does not exist.
    """
    scored = interview.overall_score is not None
    title = f"{candidate_name} completed a {interview.interview_type.value} interview"
    body = (
        f"{candidate_name} finished a {interview.interview_type.value} "
        f"interview on {interview.domain} "
        f"({interview.difficulty.value.lower()}).\n\n"
        + (
            f"Overall score: {interview.overall_score}\n\n"
            if scored
            else "It has not been scored — the recordings are saved but the "
                 "analysis did not complete.\n\n"
        )
        + "Open it from the Candidates list to read the full breakdown."
    )
    return title, body


def compose_stalled_digest(count: int, hours: int) -> tuple[str, str]:
    """
    For recruiters: candidates sitting on unfinished interviews.

    A single digest rather than one notification per candidate. A recruiter
    watching the whole platform would otherwise get an unreadable wall of
    near-identical entries, which is the same flooding problem the per-run cap
    solves on the candidate side.
    """
    title = f"{count} candidate interview{'' if count == 1 else 's'} left unfinished"
    body = (
        f"{count} interview{'' if count == 1 else 's'} "
        f"{'has' if count == 1 else 'have'} been open for more than {hours} "
        "hours without being completed.\n\n"
        "Unfinished interviews are not scored and do not appear on the "
        "leaderboard. Open the Sessions list to see which candidates are "
        "affected."
    )
    return title, body


def compose_ticket_raised(reporter_name: str, reason: str) -> tuple[str, str]:
    """For admins: a new report needs triage."""
    title = f"New report raised: {reason}"
    body = (
        f"{reporter_name} raised a report.\n\n"
        f"Reason: {reason}\n\n"
        "Open the Tickets queue to review and resolve it."
    )
    return title, body


def compose_system_alert(subject: str, detail: str) -> tuple[str, str]:
    """
    For admins: something operational needs attention.

    Used for the failures a candidate should never be shown directly — a spent
    AI quota, a mail server refusing connections — which otherwise only ever
    appear in the server log where nobody is watching.
    """
    title = f"System alert: {subject}"
    body = f"{detail}\n\nThis is an operational alert. Candidates are not shown it."
    return title, body


def notify_role(
    db: Session,
    role,
    *,
    kind: NotificationKind,
    title: str,
    body: str,
    interview_id: Optional[int] = None,
    send_email: bool = False,
) -> List[Notification]:
    """
    Raise the same notification for every active user in a role.

    Blocked users are skipped: they cannot act on it, and mailing someone whose
    access has been revoked is exactly the wrong signal to send.
    """
    users = (
        db.query(User)
        .filter(User.role == role, User.is_blocked.is_(False))
        .all()
    )
    return [
        notify(
            db, user,
            kind=kind, title=title, body=body,
            interview_id=interview_id, send_email=send_email,
        )
        for user in users
    ]


def stale_interviews_all(db: Session, hours: int = STALE_INTERVIEW_HOURS) -> List[Interview]:
    """Every candidate's unfinished interviews, for the recruiter/admin view."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return (
        db.query(Interview)
        .filter(
            Interview.status.in_([SessionStatus.IN_PROGRESS, SessionStatus.PAUSED]),
            Interview.started_at.isnot(None),
            Interview.started_at < cutoff,
        )
        .order_by(Interview.started_at)
        .all()
    )
