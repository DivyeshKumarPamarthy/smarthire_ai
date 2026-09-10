"""
Module 9 — notifications, reminders and downloadable reports.

The reminder endpoint is a pull, not a scheduler. This platform has no worker
process, and inventing one to send mail on a timer would be a larger change
than the feature warrants — so reminders are computed when asked for and
de-duplicated so repeated calls cannot spam the feed. If a scheduler is added
later, it calls exactly this function on a timer and nothing else changes.
"""

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.interview import Interview
from app.models.notification import Notification, NotificationKind
from app.models.user import Role, User
from app.schemas.notification import (
    EmailPreference,
    NotificationOut,
    NotificationSummary,
    ReminderRun,
)
from app.services import notifications as notify_service
from app.services import performance_analytics, report_pdf, speech_analysis, scoring

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _owned_interview(db: Session, user: User, interview_id: int) -> Interview:
    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id, Interview.user_id == user.id)
        .first()
    )
    if interview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found."
        )
    return interview


@router.get("", response_model=List[NotificationOut])
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The signed-in user's notifications, newest first."""
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    return query.order_by(Notification.created_at.desc()).limit(limit).all()


@router.get("/summary", response_model=NotificationSummary)
def notification_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Counts for the bell icon, without shipping the whole feed."""
    base = db.query(Notification).filter(Notification.user_id == current_user.id)
    return NotificationSummary(
        total=base.count(),
        unread=base.filter(Notification.read_at.is_(None)).count(),
    )


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found."
        )
    notification.mark_read()
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/read-all", response_model=NotificationSummary)
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unread = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .all()
    )
    for notification in unread:
        notification.mark_read()
    db.commit()

    base = db.query(Notification).filter(Notification.user_id == current_user.id)
    return NotificationSummary(total=base.count(), unread=0)


@router.post(
    "/reminders/run",
    response_model=ReminderRun,
    dependencies=[Depends(require_roles(Role.CANDIDATE))],
)
def run_reminders(
    send_email: bool = Query(
        default=False,
        description="Also email each reminder. Silently skipped when no SMTP host is set.",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Raise a reminder for every interview left unfinished.

    De-duplicated: an interview already reminded about in the last 24 hours is
    counted as skipped rather than notified again, so calling this twice does
    not produce two identical entries in the feed.
    """
    stale = notify_service.stale_interviews(db, current_user)

    created, skipped = [], 0
    for interview in stale:
        if notify_service.already_reminded(db, current_user, interview.id):
            skipped += 1
            continue
        if len(created) >= notify_service.MAX_REMINDERS_PER_RUN:
            # Capped rather than truncated silently: the count of unfinished
            # interviews is still reported in full, so the candidate is told
            # there are more than they were notified about.
            break

        idle = datetime.now(timezone.utc) - interview.started_at
        hours = int(idle.total_seconds() // 3600)
        title, body = notify_service.compose_interview_reminder(interview, hours)
        created.append(
            notify_service.notify(
                db, current_user,
                kind=NotificationKind.INTERVIEW_REMINDER,
                title=title, body=body,
                interview_id=interview.id,
                send_email=send_email,
            )
        )

    return ReminderRun(
        unfinished_interviews=len(stale),
        reminders_created=len(created),
        already_reminded=skipped,
        notifications=created,
    )


@router.post(
    "/performance-summary",
    response_model=NotificationOut,
    dependencies=[Depends(require_roles(Role.CANDIDATE))],
)
def send_performance_summary(
    send_email: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    A roll-up of the candidate's standing, from the Module 8 aggregates.

    Reads the same functions the dashboard does, so the emailed summary and the
    on-screen figures cannot disagree.
    """
    from app.models.interview import InterviewQuestion

    rows = (
        db.query(InterviewQuestion.category, InterviewQuestion.analysis)
        .join(Interview, InterviewQuestion.interview_id == Interview.id)
        .filter(Interview.user_id == current_user.id)
        .all()
    )
    interviews = db.query(Interview).filter(Interview.user_id == current_user.id).all()

    trend = performance_analytics.performance_trend(interviews)
    weak = performance_analytics.weak_areas(rows)
    title, body = notify_service.compose_performance_summary(
        current_user.name, trend, weak
    )

    return notify_service.notify(
        db, current_user,
        kind=NotificationKind.PERFORMANCE_SUMMARY,
        title=title, body=body,
        send_email=send_email,
    )


@router.get("/reports/interview/{interview_id}.pdf")
def download_interview_report(
    interview_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    The interview's report as a PDF.

    Built from the stored analysis rather than recomputed, so a downloaded
    report always matches what the same interview shows on screen.
    """
    interview = _owned_interview(db, current_user, interview_id)

    summary = speech_analysis.summarise(
        [q.analysis for q in interview.questions],
        scoring.time_management_score(interview),
    )

    try:
        pdf = report_pdf.build_interview_report(
            interview, summary, interview.behavior_report
        )
    except Exception:  # noqa: BLE001
        logger.exception("PDF generation failed for interview %s", interview_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The report could not be generated.",
        )

    filename = f"interview-{interview.id}-report.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/preferences", response_model=EmailPreference)
def get_email_preference(current_user: User = Depends(get_current_user)):
    """Whether automated email reaches this user, and whether it can at all."""
    from app.core.config import settings as app_settings

    return EmailPreference(
        email_notifications=current_user.email_notifications,
        # Reported separately so the UI can distinguish "you turned this off"
        # from "this deployment cannot send mail at all" — otherwise a user
        # toggles it on and nothing ever arrives, with no explanation.
        delivery_configured=app_settings.email_enabled,
    )


@router.put("/preferences", response_model=EmailPreference)
def set_email_preference(
    payload: EmailPreference,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Turn automated email on or off for the signed-in user."""
    from app.core.config import settings as app_settings

    current_user.email_notifications = payload.email_notifications
    db.commit()
    db.refresh(current_user)
    return EmailPreference(
        email_notifications=current_user.email_notifications,
        delivery_configured=app_settings.email_enabled,
    )


@router.post(
    "/reminders/stalled-digest",
    response_model=ReminderRun,
    dependencies=[Depends(require_roles(Role.RECRUITER, Role.ADMIN))],
)
def stalled_digest(
    send_email: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Platform-wide interview reminders, as one digest for the caller.

    A digest rather than one notification per candidate: a recruiter watching
    every candidate on the platform would otherwise receive an unreadable wall
    of near-identical entries.

    Raised for the caller only, not fanned out to every recruiter — this is a
    pull, and fanning it out would mean one recruiter pressing a button
    notifies all of them.
    """
    stale = notify_service.stale_interviews_all(db)

    if not stale:
        return ReminderRun(
            unfinished_interviews=0, reminders_created=0,
            already_reminded=0, notifications=[],
        )

    title, body = notify_service.compose_stalled_digest(
        len(stale), notify_service.STALE_INTERVIEW_HOURS
    )
    created = notify_service.notify(
        db, current_user,
        kind=NotificationKind.INTERVIEW_REMINDER,
        title=title, body=body,
        send_email=send_email,
    )
    return ReminderRun(
        unfinished_interviews=len(stale),
        reminders_created=1,
        already_reminded=0,
        notifications=[created],
    )
