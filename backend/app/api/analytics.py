"""
Real analytics, computed from real rows.

Nothing here is estimated or seeded. If a figure cannot be derived from the
database it is not in this file. Module 5 added a real one: Interview.
overall_score, stamped by the voice interviewer when a session completes —
so score and leaderboard figures below are that column, read and ranked, not
invented here. Module 6's eye-contact and expression figures stay out of this
file on purpose — they are measured client-side and so are forgeable, which is
fine for a candidate's own practice feedback and not fine as a number a
recruiter sorts by. See app/schemas/analytics.py for the longer reasoning.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.interview import (
    ACTIVE_STATUSES,
    QUESTION_ANSWERED,
    QUESTION_SKIPPED,
    Interview,
    InterviewQuestion,
    SessionStatus,
)
from app.models.resume import Resume, ResumeStatus
from app.models.ticket import Ticket, TicketStatus
from app.models.user import Role, User
from app.schemas.analytics import (
    CandidatePerformance,
    AdminAnalytics,
    CandidateAnalytics,
    CandidateInterviewSummary,
    CountPoint,
    LeaderboardEntry,
    LiveInterview,
    RecruiterAnalytics,
    RecruiterCandidate,
    TimePoint,
)
from app.services import behavior_analysis, performance_analytics
from app.services.scoring import rating_label

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _counts(db: Session, column, model, **filters) -> dict:
    """GROUP BY helper returning {enum_value: count}."""
    query = db.query(column, func.count()).group_by(column)
    for attr, value in filters.items():
        query = query.filter(getattr(model, attr) == value)
    return {(k.value if hasattr(k, "value") else str(k)): v for k, v in query.all()}


def _technology_counts(resumes: List[Resume]) -> Counter:
    """
    Aggregate technologies across parsed résumés.

    Done in Python rather than SQL because `technologies` is a portable JSON
    column — SQLite has no jsonb operators, and the row counts here are small.
    """
    counter: Counter = Counter()
    for resume in resumes:
        for tech in resume.technologies or []:
            cleaned = str(tech).strip()
            if cleaned:
                counter[cleaned] += 1
    return counter


@router.get(
    "/admin",
    response_model=AdminAnalytics,
    dependencies=[Depends(require_roles(Role.ADMIN))],
)
def admin_analytics(db: Session = Depends(get_db)):
    """Platform-wide counts. Every number is a live COUNT against a table."""
    users_by_role = _counts(db, User.role, User)

    since = datetime.now(timezone.utc) - timedelta(days=13)
    daily = (
        db.query(func.date(Interview.created_at), func.count())
        .filter(Interview.created_at >= since)
        .group_by(func.date(Interview.created_at))
        .all()
    )
    by_day = {str(day): count for day, count in daily}

    today = datetime.now(timezone.utc).date()
    series = []
    for offset in range(13, -1, -1):
        day = str(today - timedelta(days=offset))
        series.append(TimePoint(date=day, count=by_day.get(day, 0)))

    scored = db.query(Interview).filter(Interview.overall_score.isnot(None))
    average_score = scored.with_entities(func.avg(Interview.overall_score)).scalar()

    return AdminAnalytics(
        users_total=db.query(User).count(),
        users_by_role=users_by_role,
        users_blocked=db.query(User).filter(User.is_blocked.is_(True)).count(),
        interviews_total=db.query(Interview).count(),
        interviews_by_status=_counts(db, Interview.status, Interview),
        interviews_by_type=_counts(db, Interview.interview_type, Interview),
        interviews_by_difficulty=_counts(db, Interview.difficulty, Interview),
        questions_total=db.query(InterviewQuestion).count(),
        questions_answered=db.query(InterviewQuestion).filter(QUESTION_ANSWERED).count(),
        questions_skipped=db.query(InterviewQuestion).filter(QUESTION_SKIPPED).count(),
        resumes_total=db.query(Resume).count(),
        resumes_by_status=_counts(db, Resume.status, Resume),
        tickets_open=db.query(Ticket).filter(Ticket.status == TicketStatus.OPEN).count(),
        tickets_total=db.query(Ticket).count(),
        interviews_last_14_days=series,
        average_score=round(average_score, 1) if average_score is not None else None,
        scored_interviews=scored.count(),
    )


@router.get(
    "/candidate",
    response_model=CandidateAnalytics,
    dependencies=[Depends(require_roles(Role.CANDIDATE))],
)
def candidate_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The signed-in candidate's own real activity."""
    mine = db.query(Interview).filter(Interview.user_id == current_user.id)

    question_q = (
        db.query(InterviewQuestion)
        .join(Interview, InterviewQuestion.interview_id == Interview.id)
        .filter(Interview.user_id == current_user.id)
    )

    last = (
        mine.filter(Interview.started_at.isnot(None))
        .order_by(Interview.started_at.desc())
        .first()
    )

    # Module 5. Latest by completion, not by creation — an interview generated
    # but never finished has no score to show.
    scored = mine.filter(Interview.overall_score.isnot(None))
    latest_scored = scored.order_by(Interview.completed_at.desc()).first()
    best_score = scored.with_entities(func.max(Interview.overall_score)).scalar()

    resume = (
        db.query(Resume)
        .filter(Resume.user_id == current_user.id, Resume.status == ResumeStatus.PARSED)
        .order_by(Resume.id.desc())
        .first()
    )

    return CandidateAnalytics(
        interviews_total=mine.count(),
        interviews_by_status=_counts(db, Interview.status, Interview, user_id=current_user.id),
        interviews_by_type=_counts(
            db, Interview.interview_type, Interview, user_id=current_user.id
        ),
        questions_total=question_q.count(),
        questions_answered=question_q.filter(QUESTION_ANSWERED).count(),
        questions_skipped=question_q.filter(QUESTION_SKIPPED).count(),
        last_interview_at=last.started_at if last else None,
        has_resume=resume is not None,
        resume_skills_count=len(resume.skills or []) if resume else 0,
        resume_technologies_count=len(resume.technologies or []) if resume else 0,
        resume_experience_years=resume.total_experience_years if resume else None,
        latest_score=latest_scored.overall_score if latest_scored else None,
        latest_score_rating=(
            rating_label(latest_scored.overall_score) if latest_scored else None
        ),
        best_score=round(best_score, 1) if best_score is not None else None,
    )


@router.get(
    "/recruiter",
    response_model=RecruiterAnalytics,
    dependencies=[Depends(require_roles(Role.RECRUITER, Role.ADMIN))],
)
def recruiter_analytics(db: Session = Depends(get_db)):
    """Pool-level counts across all candidates."""
    candidate_ids = [
        row[0] for row in db.query(User.id).filter(User.role == Role.CANDIDATE).all()
    ]

    parsed = (
        db.query(Resume)
        .filter(Resume.user_id.in_(candidate_ids or [0]), Resume.status == ResumeStatus.PARSED)
        .all()
    )
    # one résumé per candidate — the newest parsed one
    newest: dict = {}
    for resume in parsed:
        if resume.user_id not in newest or resume.id > newest[resume.user_id].id:
            newest[resume.user_id] = resume

    interviews = db.query(Interview).filter(Interview.user_id.in_(candidate_ids or [0]))

    tech = _technology_counts(list(newest.values()))

    scored = interviews.filter(Interview.overall_score.isnot(None))
    average_score = scored.with_entities(func.avg(Interview.overall_score)).scalar()

    return RecruiterAnalytics(
        candidates_total=len(candidate_ids),
        candidates_with_resume=len(newest),
        interviews_total=interviews.count(),
        interviews_completed=interviews.filter(
            Interview.status == SessionStatus.COMPLETED
        ).count(),
        # Same definition as GET /analytics/live, so the count and the list it
        # summarises can never disagree — a paused candidate appears in both.
        live_now=interviews.filter(Interview.status.in_(ACTIVE_STATUSES)).count(),
        top_technologies=[
            CountPoint(label=label, count=count) for label, count in tech.most_common(10)
        ],
        average_score=round(average_score, 1) if average_score is not None else None,
        scored_interviews=scored.count(),
    )


@router.get(
    "/recruiter/candidates",
    response_model=List[RecruiterCandidate],
    dependencies=[Depends(require_roles(Role.RECRUITER, Role.ADMIN))],
)
def recruiter_candidates(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    The real candidate list.

    Ordered by activity (most interviews first) — this is a directory, not a
    ranking. For a ranking, see GET /analytics/leaderboard.
    """
    candidates = (
        db.query(User)
        .filter(User.role == Role.CANDIDATE)
        .order_by(User.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    out: List[RecruiterCandidate] = []
    for user in candidates:
        mine = db.query(Interview).filter(Interview.user_id == user.id)
        last = mine.order_by(Interview.created_at.desc()).first()

        resume = (
            db.query(Resume)
            .filter(Resume.user_id == user.id, Resume.status == ResumeStatus.PARSED)
            .order_by(Resume.id.desc())
            .first()
        )

        latest_scored = (
            mine.filter(Interview.overall_score.isnot(None))
            .order_by(Interview.completed_at.desc())
            .first()
        )

        out.append(
            RecruiterCandidate(
                user_id=user.id,
                name=user.name,
                email=user.email,
                interviews_total=mine.count(),
                interviews_completed=mine.filter(
                    Interview.status == SessionStatus.COMPLETED
                ).count(),
                has_resume=resume is not None,
                top_technologies=[str(t) for t in (resume.technologies or [])[:6]] if resume else [],
                last_active_at=last.created_at if last else None,
                latest_score=latest_scored.overall_score if latest_scored else None,
                latest_score_rating=(
                    rating_label(latest_scored.overall_score) if latest_scored else None
                ),
            )
        )

    out.sort(key=lambda c: c.interviews_total, reverse=True)
    return out


@router.get(
    "/recruiter/candidates/{user_id}/interviews",
    response_model=List[CandidateInterviewSummary],
    dependencies=[Depends(require_roles(Role.RECRUITER, Role.ADMIN))],
)
def recruiter_candidate_interviews(
    user_id: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
):
    """
    One candidate's completed interviews: the Module 5 score, and the part of
    the Module 6 attention data that is defensible in front of a recruiter.

    Context, not ranking. The leaderboard still ranks on the interview score
    alone — the attention figures below are submitted by the candidate's own
    browser and are therefore forgeable, which is tolerable as background when
    someone reviews a session and would not be tolerable as something people
    are sorted by.

    What is omitted matters as much as what is here: expression, emotion and
    the written summary are filtered out by behavior_analysis.recruiter_view,
    because those rest on inference that does not measure reliably enough to
    inform a decision about a person. See that function for the reasoning.

    Transcripts and recordings are still not exposed — this adds attention
    context, not access to the candidate's face or words.
    """
    candidate = (
        db.query(User).filter(User.id == user_id, User.role == Role.CANDIDATE).first()
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such candidate."
        )

    interviews = (
        db.query(Interview)
        .filter(
            Interview.user_id == user_id,
            Interview.status == SessionStatus.COMPLETED,
        )
        .order_by(Interview.completed_at.desc())
        .limit(limit)
        .all()
    )

    return [
        CandidateInterviewSummary(
            interview_id=row.id,
            interview_type=row.interview_type.value,
            domain=row.domain,
            difficulty=row.difficulty.value,
            completed_at=row.completed_at,
            duration_seconds=row.duration_seconds,
            question_count=row.question_count,
            overall_score=row.overall_score,
            score_rating=(
                rating_label(row.overall_score) if row.overall_score is not None else None
            ),
            attention=behavior_analysis.recruiter_view(row.behavior_report),
        )
        for row in interviews
    ]


@router.get(
    "/leaderboard",
    response_model=List[LeaderboardEntry],
    dependencies=[Depends(require_roles(Role.RECRUITER, Role.ADMIN))],
)
def leaderboard(db: Session = Depends(get_db), limit: int = Query(default=100, ge=1, le=500)):
    """
    Module 5: candidates ranked by their most recently completed interview.

    "Most recent", not best-ever or averaged: this is meant to read as current
    standing, so one strong recent interview outranks a stronger one from
    months ago, and a bad day only costs a candidate their rank until they
    complete another interview.

    A candidate appears here only if their most recent completed interview was
    actually scored. That excludes candidates with no completed interview, and
    interviews completed before scoring existed — both are "no data", not
    "scored zero", and a ranked row with no score behind it would say
    otherwise.
    """
    candidates = db.query(User).filter(User.role == Role.CANDIDATE).all()

    entries: List[LeaderboardEntry] = []
    for user in candidates:
        latest_completed = (
            db.query(Interview)
            .filter(Interview.user_id == user.id, Interview.status == SessionStatus.COMPLETED)
            .order_by(Interview.completed_at.desc())
            .first()
        )
        if latest_completed is None or latest_completed.overall_score is None:
            continue

        entries.append(
            LeaderboardEntry(
                rank=0,  # assigned below, after sorting
                user_id=user.id,
                name=user.name,
                email=user.email,
                score=latest_completed.overall_score,
                rating=rating_label(latest_completed.overall_score),
                interview_id=latest_completed.id,
                interview_type=latest_completed.interview_type.value,
                domain=latest_completed.domain,
                difficulty=latest_completed.difficulty.value,
                completed_at=latest_completed.completed_at,
            )
        )

    entries.sort(key=lambda e: e.score, reverse=True)
    for position, entry in enumerate(entries[:limit], start=1):
        entry.rank = position

    return entries[:limit]


@router.get(
    "/live",
    response_model=List[LiveInterview],
    dependencies=[Depends(require_roles(Role.RECRUITER, Role.ADMIN))],
)
def live_interviews(db: Session = Depends(get_db)):
    """
    Interviews a candidate is currently partway through.

    Includes PAUSED as well as IN_PROGRESS: a paused candidate is still in a
    live session, and dropping them from this list would make someone who
    stepped away for a minute silently disappear from the monitor. The `paused`
    flag on each row is what distinguishes the two.

    Progress is counted from real answered questions, not simulated.
    """
    rows = (
        db.query(Interview, User)
        .join(User, Interview.user_id == User.id)
        .filter(Interview.status.in_(ACTIVE_STATUSES))
        .order_by(Interview.started_at.desc().nullslast())
        .all()
    )

    out: List[LiveInterview] = []
    for interview, user in rows:
        total = (
            db.query(InterviewQuestion)
            .filter(InterviewQuestion.interview_id == interview.id)
            .count()
        )
        answered = (
            db.query(InterviewQuestion)
            .filter(InterviewQuestion.interview_id == interview.id, QUESTION_ANSWERED)
            .count()
        )
        out.append(
            LiveInterview(
                interview_id=interview.id,
                candidate_id=user.id,
                candidate_name=user.name,
                interview_type=interview.interview_type.value,
                domain=interview.domain,
                difficulty=interview.difficulty.value,
                questions_total=total,
                questions_answered=answered,
                started_at=interview.started_at,
                paused=interview.status == SessionStatus.PAUSED,
            )
        )
    return out


@router.get(
    "/candidate/performance",
    response_model=CandidatePerformance,
    dependencies=[Depends(require_roles(Role.CANDIDATE))],
)
def candidate_performance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Module 8: skill-wise breakdown, performance trend and weak areas.

    Split out from /candidate rather than bolted onto it. That endpoint backs
    the dashboard header and is fetched on every visit; this one walks every
    answer the candidate has ever given, and making the header wait on that
    scan would be paying for the detail on the pages that never show it.

    Reads only the transcript-based Module 5 scores. Module 6's camera figures
    are deliberately absent: they are measured in the candidate's own browser
    and are therefore forgeable, and the platform's standing rule is that they
    never feed a number that ranks or grades anyone.
    """
    rows = (
        db.query(InterviewQuestion.category, InterviewQuestion.analysis)
        .join(Interview, InterviewQuestion.interview_id == Interview.id)
        .filter(Interview.user_id == current_user.id)
        .all()
    )
    interviews = db.query(Interview).filter(Interview.user_id == current_user.id).all()

    return CandidatePerformance(
        skills=performance_analytics.skill_breakdown(rows),
        trend=performance_analytics.performance_trend(interviews),
        weak_areas=performance_analytics.weak_areas(rows),
    )
