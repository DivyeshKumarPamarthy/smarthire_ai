"""
Seed demo accounts and demo interview data.

Render creates an empty database: `create_all` builds the tables but nothing
puts rows in them, so a fresh deployment has no accounts to log in with.

Idempotent. Existing users are matched on email and left alone — their
password is NOT reset, so running this against a database where someone has
changed a password will not undo that. Interviews are only created for a
candidate who has none, so re-running never duplicates the demo history.

    # local
    python -m scripts.seed_demo

    # production — external connection string from the Render dashboard
    DATABASE_URL='postgresql://...' python -m scripts.seed_demo

Run with --dry-run first to see what it would do.
"""

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.interview import (
    Difficulty,
    Interview,
    InterviewQuestion,
    InterviewType,
    QuestionSource,
    SessionStatus,
)
from app.models.user import Role, User
from app.services.scoring import WEIGHTS, rating_label

# The three accounts the README documents.
DEMO_USERS = [
    ("Demo Candidate", "candidate.demo@smarthire.dev", "Candidate@123", Role.CANDIDATE),
    ("Demo Recruiter", "recruiter.demo@smarthire.dev", "Recruiter@123", Role.RECRUITER),
    ("Demo Admin", "admin.demo@smarthire.dev", "Admin@123", Role.ADMIN),
]

# Extra candidates so the recruiter comparison and shortlist insights have
# something real to compare. Deliberately different shapes: one strong and
# improving, one middling and flat, one with barely any history — the last is
# there so the "provisional / too little evidence" path is visible rather than
# theoretical.
EXTRA_CANDIDATES = [
    ("Ana Reyes", "ana.reyes@smarthire.dev", "Demo@1234", "strong"),
    ("Ben Okafor", "ben.okafor@smarthire.dev", "Demo@1234", "middling"),
    ("Chen Wei", "chen.wei@smarthire.dev", "Demo@1234", "thin"),
]

QUESTIONS = [
    ("Tell me about a time you disagreed with a technical decision.", "behavioural"),
    ("How would you design a rate limiter for a public API?", "rate limiting"),
    ("Explain the difference between a process and a thread.", "operating systems"),
    ("How do you decide when to add a database index?", "database optimization"),
    ("Walk me through debugging a slow endpoint.", "performance"),
    ("What happens when you type a URL into a browser?", "networking"),
]

ANSWERS = [
    "I documented the tradeoffs and raised them in a one-to-one rather than in "
    "the group channel, so the discussion stayed about the decision.",
    "I would use a token bucket per client key, held in a shared store so it "
    "survives a restart, and return the retry window in the response headers.",
    "A process owns its own memory; threads share it. That sharing is what "
    "makes threads cheap and also what makes them dangerous.",
    "When a query is read often and filtered on a column that is selective. "
    "Indexes cost write time, so I measure before adding one.",
    "I start with the slowest span rather than guessing — usually it is an "
    "unbatched query inside a loop.",
    "DNS resolves the host, TCP and TLS establish a connection, then the "
    "server responds and the browser builds the render tree.",
]

# Score profiles per candidate shape: (per-interview axis means, roughly).
PROFILES = {
    "demo": [(20, 12, 10, 14), (35, 22, 30, 28), (58, 45, 52, 50),
             (72, 61, 70, 66), (80, 74, 78, 75)],
    "strong": [(78, 74, 80, 76), (82, 79, 85, 80), (88, 84, 90, 86), (91, 88, 92, 89)],
    "middling": [(52, 48, 50, 54), (55, 46, 53, 51), (51, 49, 55, 50), (54, 47, 52, 53)],
    "thin": [(61, 55, 58, 60)],
}


def upsert_user(db: Session, name, email, password, role, dry):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return existing, "exists"
    if dry:
        return None, "would create"
    user = User(
        name=name,
        email=email,
        password=hash_password(password),   # the app's own hashing, not a copy
        role=role,
        is_blocked=False,
    )
    db.add(user)
    db.flush()
    return user, "created"


def make_interview(db, user, axes, days_ago, seq, dry):
    """One completed, scored interview with graded answers behind it."""
    if dry:
        return None

    comm, conf, tech, prof = axes
    overall = round(
        comm * WEIGHTS["communication"] + conf * WEIGHTS["confidence"]
        + tech * WEIGHTS["technical_relevance"] + prof * WEIGHTS["professionalism"], 1
    )
    completed = datetime.now(timezone.utc) - timedelta(days=days_ago)

    interview = Interview(
        user_id=user.id,
        interview_type=[InterviewType.TECHNICAL, InterviewType.HR,
                        InterviewType.BEHAVIORAL][seq % 3],
        domain="backend developer",
        difficulty=[Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD][seq % 3],
        status=SessionStatus.COMPLETED,
        question_count=3,
        source=QuestionSource.AI,
        started_at=completed - timedelta(minutes=14),
        completed_at=completed,
        duration_seconds=840,
        question_seconds=300,
        overall_score=overall,
    )
    db.add(interview)
    db.flush()

    for n in range(3):
        idx = (seq * 3 + n) % len(QUESTIONS)
        text, category = QUESTIONS[idx]
        # Jitter per answer so category averages are not all identical.
        j = lambda v: max(0, min(100, v + random.randint(-6, 6)))  # noqa: E731
        a_comm, a_conf, a_tech, a_prof = j(comm), j(conf), j(tech), j(prof)
        a_overall = round(
            a_comm * WEIGHTS["communication"] + a_conf * WEIGHTS["confidence"]
            + a_tech * WEIGHTS["technical_relevance"]
            + a_prof * WEIGHTS["professionalism"], 1
        )
        words = len(ANSWERS[idx].split())
        db.add(InterviewQuestion(
            interview_id=interview.id,
            question_text=text,
            category=category,
            difficulty=interview.difficulty,
            sequence_no=n + 1,
            answer_text=ANSWERS[idx],
            answer_duration_seconds=42.0,
            asked_at=completed - timedelta(minutes=12 - n * 3),
            answered_at=completed - timedelta(minutes=11 - n * 3),
            analyzed_at=completed,
            # Shape must match what speech_analysis.summarise and
            # performance_analytics read, or the dashboards show nothing.
            analysis={
                "available": True,
                "transcript_word_count": words,
                "fillers": {"total": 1, "by_word": {"um": 1}, "word_count": words,
                            "per_100_words": round(100 / words, 1),
                            "discourse_markers": {}},
                "pace": {"available": True, "words_per_minute": 132,
                         "duration_seconds": 42.0, "verdict": "comfortable",
                         "comfortable_range": [110, 160]},
                "communication": {"available": True, "grammar_issues": [],
                                  "clarity": "Clear and direct.",
                                  "structure": "Problem, action, result.",
                                  "conciseness": "Appropriately brief.",
                                  "improvements": ["Add a concrete metric."]},
                "pronunciation": {"available": True, "intelligibility": "Clear",
                                  "notes": "Easy to follow throughout.",
                                  "unclear_words": []},
                "score": {
                    "available": True,
                    "communication": a_comm, "confidence": a_conf,
                    "technical_relevance": a_tech, "professionalism": a_prof,
                    "overall": a_overall, "rating": rating_label(a_overall),
                    "rationale": "Scored against the disclosed four-axis rubric.",
                },
            },
        ))
    return interview


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    random.seed(7)  # reproducible

    target = str(engine.url).replace(engine.url.password or "", "****") \
        if engine.url.password else str(engine.url)
    print(f"target: {target}")
    if args.dry_run:
        print("DRY RUN — nothing will be written\n")

    db = SessionLocal()
    created_users = 0
    created_interviews = 0
    try:
        for name, email, pw, role in DEMO_USERS:
            user, state = upsert_user(db, name, email, pw, role, args.dry_run)
            print(f"  {role.value:10s} {email:32s} {state}")
            if state == "created":
                created_users += 1

        print()
        candidates = [("demo", "candidate.demo@smarthire.dev")]
        for name, email, pw, shape in EXTRA_CANDIDATES:
            user, state = upsert_user(db, name, email, pw, Role.CANDIDATE, args.dry_run)
            print(f"  CANDIDATE  {email:32s} {state}  ({shape})")
            if state == "created":
                created_users += 1
            candidates.append((shape, email))

        print()
        for shape, email in candidates:
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                print(f"  {email}: skipped (dry run)")
                continue
            have = db.query(Interview).filter(
                Interview.user_id == user.id,
                Interview.status == SessionStatus.COMPLETED,
            ).count()
            if have:
                print(f"  {email:32s} already has {have} completed interview(s) — left alone")
                continue
            profile = PROFILES[shape]
            for seq, axes in enumerate(profile):
                make_interview(db, user, axes, days_ago=(len(profile) - seq) * 6,
                               seq=seq, dry=args.dry_run)
                created_interviews += 1
            print(f"  {email:32s} + {len(profile)} scored interviews ({shape})")

        if args.dry_run:
            db.rollback()
            print("\nDRY RUN — rolled back")
        else:
            db.commit()
            print(f"\ncommitted: {created_users} users, {created_interviews} interviews")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
