"""
Analytics response shapes.

Every field here is a count, a list, a timestamp, a status, a duration, or —
now that Module 5 exists — a score read straight off Interview.overall_score.
Nothing here reports a figure the platform does not actually compute.

Module 6's figures stay out of the *aggregate* shapes here and out of the
leaderboard. They are measured in the candidate's own browser and are
therefore client-supplied, so ranking people on them would mean ranking on
something forgeable.

They do appear, filtered, on CandidateInterviewSummary — a recruiter
reviewing one session sees attention context beside the score. That is a
deliberate line: context while reading about a person, never a number that
sorts people. What gets filtered out (expression, emotion, the written
summary) and why is in behavior_analysis.recruiter_view.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class CountPoint(BaseModel):
    label: str
    count: int


class TimePoint(BaseModel):
    date: str
    count: int


class AdminAnalytics(BaseModel):
    users_total: int
    users_by_role: Dict[str, int]
    users_blocked: int

    interviews_total: int
    interviews_by_status: Dict[str, int]
    interviews_by_type: Dict[str, int]
    interviews_by_difficulty: Dict[str, int]

    questions_total: int
    # Skipped questions are not attempted, so they are counted separately and
    # never folded into questions_answered.
    questions_answered: int
    questions_skipped: int = 0

    resumes_total: int
    resumes_by_status: Dict[str, int]

    tickets_open: int
    tickets_total: int

    interviews_last_14_days: List[TimePoint]

    # Module 5: mean of Interview.overall_score across every interview that
    # has one. None rather than 0 when nothing has been scored yet — the
    # platform having zero score is a different fact from having no data.
    average_score: Optional[float] = None
    scored_interviews: int = 0


class CandidateAnalytics(BaseModel):
    interviews_total: int
    interviews_by_status: Dict[str, int]
    interviews_by_type: Dict[str, int]

    questions_total: int
    questions_answered: int
    questions_skipped: int = 0

    last_interview_at: Optional[datetime] = None

    has_resume: bool
    resume_skills_count: int = 0
    resume_technologies_count: int = 0
    resume_experience_years: Optional[float] = None

    # Module 5. Both None until at least one interview has been scored — a
    # candidate with no scored interview has no score, not a score of zero.
    latest_score: Optional[float] = None
    latest_score_rating: Optional[str] = None
    best_score: Optional[float] = None
    scoring_available: bool = True


class RecruiterCandidate(BaseModel):
    """One row of the recruiter's candidate list, ordered by activity."""

    user_id: int
    name: str
    email: str
    interviews_total: int
    interviews_completed: int
    has_resume: bool
    top_technologies: List[str] = []
    last_active_at: Optional[datetime] = None
    # Module 5, from the candidate's most recently completed interview — the
    # same basis the leaderboard ranks on. None if that interview was never
    # scored, or if the candidate has no completed interview at all.
    latest_score: Optional[float] = None
    latest_score_rating: Optional[str] = None


class RecruiterAnalytics(BaseModel):
    candidates_total: int
    candidates_with_resume: int
    interviews_total: int
    interviews_completed: int
    live_now: int
    top_technologies: List[CountPoint]
    average_score: Optional[float] = None
    scored_interviews: int = 0
    scoring_available: bool = True


class CandidateInterviewSummary(BaseModel):
    """
    One completed interview as a recruiter sees it: the score, and attention
    context from Module 6.

    `attention` is a filtered view — see
    behavior_analysis.recruiter_view for what is withheld and why. It is a
    plain dict rather than a typed model because it is display-only and its
    shape follows whatever the tracker produced; typing it here would mean two
    places to change every time that evolves.

    None when the candidate had no camera on, or tracking never arrived.
    """

    interview_id: int
    interview_type: str
    domain: str
    difficulty: str
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    question_count: int
    overall_score: Optional[float] = None
    score_rating: Optional[str] = None
    attention: Optional[dict] = None


class LeaderboardEntry(BaseModel):
    """
    One ranked row. Basis: each candidate's most recently completed
    interview — current standing, not a lifetime average or a personal best.

    Only candidates whose most recent completed interview was actually scored
    appear here at all; there is no row with a rank and no score; see
    GET /analytics/leaderboard for why.
    """

    rank: int
    user_id: int
    name: str
    email: str
    score: float
    rating: str
    interview_id: int
    interview_type: str
    domain: str
    difficulty: str
    completed_at: Optional[datetime] = None


class LiveInterview(BaseModel):
    """An interview a candidate is partway through — derived from real status."""

    interview_id: int
    candidate_id: int
    candidate_name: str
    interview_type: str
    domain: str
    difficulty: str
    questions_total: int
    questions_answered: int
    started_at: Optional[datetime] = None
    # True when the candidate has paused. They are still in a live session —
    # this is what tells a watching recruiter why progress has stopped.
    paused: bool = False


# --------------------------------------------------------------- Module 8


class SkillStat(BaseModel):
    """One question category, averaged across every graded answer in it."""

    category: str
    answers_graded: int
    overall: Optional[float] = None
    axes: Dict[str, float] = {}
    # True when too few answers stand behind this row to treat it as settled.
    # Reported rather than filtered: hiding a candidate's only data point in a
    # category is its own kind of misrepresentation.
    provisional: bool = False


class TrendPoint(BaseModel):
    """One scored interview, as a point on the candidate's timeline."""

    interview_id: int
    completed_at: datetime
    score: float
    rating: str
    interview_type: str
    domain: str
    difficulty: str


class PerformanceTrend(BaseModel):
    points: List[TrendPoint] = []
    interviews_scored: int = 0
    average: Optional[float] = None
    best: Optional[float] = None
    # improving | declining | steady | insufficient_data
    direction: str = "insufficient_data"
    # Score-point difference between the earlier and later half of the
    # history. None until there are enough interviews to compare halves.
    change: Optional[float] = None


class WeakAreas(BaseModel):
    """
    The lowest-scoring axis and category in the candidate's record.

    Named for what the data supports: this is where they have actually scored
    worst so far, not a forecast of how they will do next time.
    """

    available: bool
    reason: Optional[str] = None
    axis_averages: Dict[str, float] = {}
    weakest_axis: Optional[str] = None
    weakest_axis_score: Optional[float] = None
    weakest_category: Optional[str] = None
    weakest_category_score: Optional[float] = None
    graded_answers: int = 0
    practice_recommendations: List[str] = []
    learning_resources: List[str] = []
    provisional: bool = False
    method_note: Optional[str] = None


class AxisPoint(BaseModel):
    """One interview's average on a single rubric axis."""

    interview_id: int
    completed_at: datetime
    score: float


class AxisProgress(BaseModel):
    """
    Module 10: movement on the axis a candidate was told to work on.

    Distinct from PerformanceTrend on purpose. That tracks the overall score;
    this tracks the one axis the advice named, because a candidate can lift
    their overall score while the thing they were asked to fix stays flat.
    """

    available: bool
    axis: str
    reason: Optional[str] = None
    points: List[AxisPoint] = []
    interviews: int = 0
    first: Optional[float] = None
    latest: Optional[float] = None
    # improving | declining | steady | insufficient_data — the same four
    # values, the same four-interview floor, as PerformanceTrend.
    direction: str = "insufficient_data"
    change: Optional[float] = None


class CandidatePerformance(BaseModel):
    """Module 8: skills, trend and weak areas for one candidate."""

    skills: List[SkillStat] = []
    trend: PerformanceTrend
    weak_areas: WeakAreas
    # Module 10, added additively — every key above is unchanged.
    axis_progress: Optional[AxisProgress] = None


# ---------------------------------------------------------- Module 10


class RecruiterCandidatePerformance(BaseModel):
    """
    One candidate's performance, filtered for a recruiter.

    Deliberately not CandidatePerformance: this shape cannot carry
    practice_recommendations or learning_resources, so the visibility decision
    is enforced by the type and not only by the filter that builds it.
    """

    user_id: int
    name: str
    skills: List[SkillStat] = []
    trend: PerformanceTrend
    weak_areas: Dict = {}
    axis_progress: Optional[AxisProgress] = None


class ComparisonCell(BaseModel):
    """One candidate's standing on one axis, with its evidence attached."""

    axis: str
    score: Optional[float] = None
    # Both mandatory, per the binding Gate 1/Gate 2 decision: side by side,
    # thin evidence must stay visibly thin or a candidate with one graded
    # answer reads as equivalent to one with twelve.
    answers_graded: int = 0
    provisional: bool = True


class ComparisonEntry(BaseModel):
    user_id: int
    name: str
    interviews_scored: int = 0
    cells: List[ComparisonCell] = []


class CandidateComparison(BaseModel):
    """
    Two to four candidates on the same axes.

    `candidates` is in the order the caller supplied. There is no rank, no
    position and no ordering hint — the interface must not perform ranking on a
    recruiter's behalf. Ranking exists once, in the leaderboard, labelled.
    """

    candidates: List[ComparisonEntry] = []
    axes: List[str] = []
    note: str


class Insight(BaseModel):
    kind: str
    candidate_id: int
    candidate_name: str
    headline: str
    # Always populated. An insight whose reason cannot be shown is not emitted.
    evidence: str
    provisional: bool = False


class ShortlistInsights(BaseModel):
    insights: List[Insight] = []
    pool_average: Optional[float] = None
    scored_candidates: int = 0
    note: str


class AIOperationStat(BaseModel):
    operation: str
    calls: int
    failures: int
    quota_failures: int
    failure_rate: float
    avg_ms: float


class AIMonitoring(BaseModel):
    """
    Provider-call history. In-memory, so the window begins at the last restart
    — labelled as such and never presented as uptime.
    """

    window_start: datetime
    total_calls: int = 0
    total_failures: int = 0
    failure_rate: float = 0.0
    quota_failures: int = 0
    avg_latency_ms: float = 0.0
    operations: List[AIOperationStat] = []
    note: str
