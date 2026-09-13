"""
Module 9 — the downloadable report.

Builds a PDF of one interview from data already stored: the Module 5/7 rubric
score and per-answer analysis, plus the Module 6 behaviour report where one
exists.

Two things this deliberately does not do. It does not recompute anything — a
downloaded report and the same report on screen must never disagree, so both
read the same stored analysis. And it does not quietly omit a section that
failed: an answer that was never transcribed says so in the PDF, because a
report that silently skips it reads as though the answer was never given.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.scoring import WEIGHTS

logger = logging.getLogger(__name__)

INK = colors.HexColor("#1a1d1a")
MUTED = colors.HexColor("#5c635c")
ACCENT = colors.HexColor("#1f4e4a")
RULE = colors.HexColor("#dde1db")

AXIS_LABEL = {
    "communication": "Communication",
    "confidence": "Confidence",
    "technical_relevance": "Technical relevance",
    "professionalism": "Professionalism",
}


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "t", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=20, leading=24, textColor=INK, alignment=TA_LEFT, spaceAfter=2,
        ),
        "sub": ParagraphStyle(
            "s", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, leading=13, textColor=MUTED, spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11, leading=14, textColor=ACCENT, spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "b", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, leading=13.5, textColor=INK, spaceAfter=6,
        ),
        "quote": ParagraphStyle(
            "q", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=9.5, leading=13.5, textColor=INK,
            leftIndent=8, spaceAfter=6,
        ),
        "note": ParagraphStyle(
            "n", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.5, leading=12, textColor=MUTED, spaceAfter=6,
        ),
    }


def _kv_table(rows, widths=(52 * mm, 108 * mm)):
    table = Table(rows, colWidths=list(widths), hAlign="LEFT")
    table.setStyle(
        TableStyle([
            ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
            ("FONT", (1, 0), (1, -1), "Helvetica", 9),
            ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
            ("TEXTCOLOR", (1, 0), (1, -1), INK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ])
    )
    return table


def build_interview_report(interview, summary: dict, behavior: Optional[dict] = None) -> bytes:
    """
    Render one interview to PDF bytes.

    `summary` is the Module 5/7 summary block exactly as the analysis endpoint
    returns it, so the PDF and the screen cannot drift apart.
    """
    st = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Interview report #{interview.id}",
        author="SmartHire AI",
    )

    flow = []
    flow.append(Paragraph("Interview report", st["title"]))
    flow.append(Paragraph(
        f"{interview.interview_type.value} &middot; {interview.domain} &middot; "
        f"{interview.difficulty.value.lower()}", st["sub"],
    ))
    flow.append(HRFlowable(width="100%", thickness=1, color=INK, spaceAfter=10))

    completed = (
        interview.completed_at.strftime("%d %b %Y, %H:%M")
        if interview.completed_at else "not completed"
    )
    flow.append(_kv_table([
        ["Interview", f"#{interview.id}"],
        ["Status", interview.status.value.replace("_", " ").lower()],
        ["Completed", completed],
        ["Questions", str(interview.question_count)],
    ]))

    # ---------------- score ----------------
    score = (summary or {}).get("score") or {}
    flow.append(Paragraph("Overall score", st["h2"]))

    if score.get("available"):
        flow.append(_kv_table([
            ["Score", f"{score['overall']} / 100"],
            ["Rating", str(score.get("rating", "—"))],
            ["Answers scored", str(score.get("graded_answers", 0))],
        ]))

        axes = ((summary.get("feedback") or {}).get("axis_averages")) or {}
        if axes:
            rows = [["Axis", "Weight", "Average"]]
            for axis, weight in WEIGHTS.items():
                if axis in axes:
                    rows.append([
                        AXIS_LABEL.get(axis, axis),
                        f"{int(weight * 100)}%",
                        str(axes[axis]),
                    ])
            table = Table(rows, colWidths=[70 * mm, 30 * mm, 30 * mm], hAlign="LEFT")
            table.setStyle(TableStyle([
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
                ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            flow.append(Spacer(1, 8))
            flow.append(table)
    else:
        flow.append(Paragraph(
            score.get("reason")
            or "This interview has not been scored. The recordings are saved.",
            st["body"],
        ))

    # ---------------- what to practise ----------------
    feedback = (summary or {}).get("feedback") or {}
    if feedback.get("available"):
        flow.append(Paragraph("What to practise", st["h2"]))
        if feedback.get("weakest_axis"):
            flow.append(Paragraph(
                f"Weakest axis: <b>{AXIS_LABEL.get(feedback['weakest_axis'], feedback['weakest_axis'])}</b>",
                st["body"],
            ))
        for item in feedback.get("practice_recommendations", []):
            flow.append(Paragraph(f"&bull; {item}", st["body"]))
        resources = feedback.get("learning_resources") or []
        if resources:
            flow.append(Paragraph(
                "Where to practise: " + ", ".join(resources), st["note"],
            ))

    # ---------------- behaviour ----------------
    if behavior and behavior.get("available"):
        flow.append(Paragraph("Behaviour and engagement", st["h2"]))
        rows = []
        if behavior.get("eye_contact_percent") is not None:
            rows.append(["Eye contact", f"{round(behavior['eye_contact_percent'])}%"])
        if behavior.get("engagement"):
            rows.append(["Engagement", str(behavior["engagement"])])
        if behavior.get("tracked_seconds"):
            rows.append(["Tracked", f"{round(behavior['tracked_seconds'])}s"])
        if rows:
            flow.append(_kv_table(rows))
        flow.append(Paragraph(
            "Measured in the browser during the interview. This is context "
            "only — it does not contribute to the score above.",
            st["note"],
        ))

    # ---------------- per answer ----------------
    flow.append(PageBreak())
    flow.append(Paragraph("Answers", st["h2"]))

    for question in interview.questions:
        block = [
            Paragraph(
                f"<b>Q{question.sequence_no}</b> &middot; {question.category}", st["body"]
            ),
            Paragraph(question.question_text, st["quote"]),
        ]

        analysis = question.analysis or {}
        if question.skipped_at is not None:
            block.append(Paragraph("Skipped — recorded as not attempted.", st["note"]))
        elif question.answered_at is None:
            block.append(Paragraph("Not answered.", st["note"]))
        elif question.answer_text:
            block.append(Paragraph(f"&ldquo;{question.answer_text}&rdquo;", st["quote"]))
        else:
            # The distinction that matters: recorded but not transcribed is not
            # the same as never answered, and the report must not blur them.
            block.append(Paragraph(
                analysis.get("reason")
                or "Recorded, but no transcript is available for this answer.",
                st["note"],
            ))

        answer_score = analysis.get("score") or {}
        if answer_score.get("available"):
            parts = [
                f"{AXIS_LABEL.get(a, a)} {answer_score[a]}"
                for a in WEIGHTS if a in answer_score
            ]
            block.append(Paragraph(
                f"<b>{answer_score['overall']}</b> &middot; {answer_score.get('rating', '')} "
                f"&mdash; {' · '.join(parts)}",
                st["note"],
            ))

        block.append(Spacer(1, 6))
        block.append(HRFlowable(width="100%", thickness=0.4, color=RULE, spaceAfter=8))
        # Keep a question and its answer on one page where it fits — a question
        # split from its own transcript is hard to read back.
        flow.append(KeepTogether(block))

    flow.append(Paragraph(
        "Scores are an AI assessment against a fixed, disclosed rubric "
        "(Communication 30%, Confidence 25%, Technical relevance 30%, "
        "Professionalism 15%). They are not a certified evaluation. "
        f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')}.",
        st["note"],
    ))

    doc.build(flow)
    return buffer.getvalue()


def build_history_report(user, interviews, performance: dict) -> bytes:
    """
    A candidate's whole scored history as one PDF.

    Reuses _styles(), _kv_table() and the colour constants above so a candidate
    holding this and a per-interview report recognises them as the same
    document family.

    ON THE TWO WINDOWS, which Slice 1 had to reconcile on screen with a dashed
    reference line and adjacent copy — neither of which a printed page has:

      Every figure here now comes from completed interviews only, so the two
      numbers a reader sees are no longer drawn from different populations.
      What remains is the ordinary distinction between an average across a
      history and the individual results inside it, and print handles that
      perfectly well as long as each figure says which it is. So both are
      shown, and every heading names its window explicitly: "averaged across
      all N completed interviews" against "one row per interview".

      Had the populations still differed, the agreed fallback was to drop the
      lifetime average entirely rather than print a number that invites the
      wrong reading. That is not needed, and this note records why so nobody
      reinstates the ambiguity later.
    """
    st = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Interview history — {user.name}",
        author="SmartHire AI",
    )

    trend = (performance or {}).get("trend") or {}
    weak = (performance or {}).get("weak_areas") or {}
    skills = (performance or {}).get("skills") or []
    progress = (performance or {}).get("axis_progress") or {}
    points = trend.get("points") or []

    flow = []
    flow.append(Paragraph("Interview history", st["title"]))
    flow.append(Paragraph(user.name, st["sub"]))
    flow.append(HRFlowable(width="100%", thickness=1, color=INK, spaceAfter=10))

    completed = [iv for iv in interviews if iv.completed_at is not None]
    flow.append(_kv_table([
        ["Interviews taken", str(len(interviews))],
        ["Completed", str(len(completed))],
        ["Scored", str(trend.get("interviews_scored", 0))],
        ["Generated", datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")],
    ]))

    # Nothing scored: say so and stop, rather than printing a page of dashes.
    if not points:
        flow.append(Paragraph("No scored interviews yet", st["h2"]))
        flow.append(Paragraph(
            "None of your interviews has been both completed and scored, so "
            "there is no history to report yet. Recordings and answers are "
            "saved either way — finishing an interview is what produces a "
            "score.",
            st["body"],
        ))
        doc.build(flow)
        return buffer.getvalue()

    # ---------- lifetime figures, labelled as such ----------
    flow.append(Paragraph(
        f"Overall — averaged across all {len(points)} completed interviews",
        st["h2"],
    ))
    summary_rows = [
        ["Average score", str(trend.get("average"))],
        ["Best score", str(trend.get("best"))],
    ]
    direction = trend.get("direction")
    if direction and direction != "insufficient_data":
        change = trend.get("change")
        summary_rows.append([
            "Direction",
            f"{direction}" + (f" ({change:+})" if change is not None else ""),
        ])
    else:
        summary_rows.append([
            "Direction",
            "not enough interviews to say — four are needed to compare",
        ])
    flow.append(_kv_table(summary_rows))

    if weak.get("available") and weak.get("axis_averages"):
        rows = [["Axis", "Average across all completed interviews"]]
        for axis in WEIGHTS:
            if axis in weak["axis_averages"]:
                rows.append([AXIS_LABEL.get(axis, axis), str(weak["axis_averages"][axis])])
        table = Table(rows, colWidths=[60 * mm, 90 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
            ("TEXTCOLOR", (0, 1), (-1, -1), INK),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
            ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        flow.append(Spacer(1, 8))
        flow.append(table)
        flow.append(Paragraph(
            f"Based on {weak.get('graded_answers', 0)} graded answers from "
            "completed interviews. Answers from interviews you did not finish "
            "are not counted.",
            st["note"],
        ))

    # ---------- per-interview figures, labelled as such ----------
    flow.append(Paragraph("Each interview — one row per interview", st["h2"]))
    flow.append(Paragraph(
        "These are the individual results the averages above are taken from. "
        "A single interview will often sit well above or below your average; "
        "that is the difference between the two, not a disagreement.",
        st["note"],
    ))

    rows = [["Completed", "Type", "Domain", "Score", "Rating"]]
    for point in points:
        completed_at = point.get("completed_at")
        rows.append([
            completed_at.strftime("%d %b %Y") if hasattr(completed_at, "strftime")
            else str(completed_at)[:10],
            str(point.get("interview_type", "")),
            str(point.get("domain", ""))[:26],
            str(point.get("score")),
            str(point.get("rating", "")),
        ])
    table = Table(rows, colWidths=[28 * mm, 26 * mm, 52 * mm, 20 * mm, 32 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    flow.append(Spacer(1, 6))
    flow.append(table)

    # ---------- what to work on ----------
    if weak.get("available"):
        flow.append(Paragraph("Where you are weakest", st["h2"]))
        axis = weak.get("weakest_axis")
        flow.append(Paragraph(
            f"<b>{AXIS_LABEL.get(axis, axis)}</b> — {weak.get('weakest_axis_score')} "
            f"averaged across all completed interviews.",
            st["body"],
        ))
        if weak.get("weakest_category"):
            flow.append(Paragraph(
                f"Weakest question category: <b>{weak['weakest_category']}</b> "
                f"({weak['weakest_category_score']}).",
                st["body"],
            ))
        else:
            flow.append(Paragraph(
                "No single question category yet has the three graded answers "
                "needed to name one as your weakest.",
                st["note"],
            ))

        if progress.get("available") and progress.get("interviews", 0) > 1:
            flow.append(Paragraph(
                f"On this axis you have gone from {progress['first']} to "
                f"{progress['latest']} across {progress['interviews']} "
                "completed interviews"
                + (
                    f" — {progress['direction']}."
                    if progress.get("direction") != "insufficient_data"
                    else ", which is too few to call a direction."
                ),
                st["body"],
            ))

        for item in weak.get("practice_recommendations", []):
            flow.append(Paragraph(f"&bull; {item}", st["body"]))
        resources = weak.get("learning_resources") or []
        if resources:
            flow.append(Paragraph("Where to practise: " + ", ".join(resources), st["note"]))

    # ---------- by category ----------
    if skills:
        flow.append(Paragraph("By question category — weakest first", st["h2"]))
        rows = [["Category", "Average", "Graded answers"]]
        for skill in skills:
            rows.append([
                str(skill["category"]),
                str(skill["overall"]),
                f"{skill['answers_graded']}" + (" (provisional)" if skill["provisional"] else ""),
            ])
        table = Table(rows, colWidths=[70 * mm, 30 * mm, 50 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
            ("TEXTCOLOR", (0, 1), (-1, -1), INK),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
            ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        flow.append(Spacer(1, 6))
        flow.append(table)
        if any(s["provisional"] for s in skills):
            flow.append(Paragraph(
                "A category marked provisional has fewer than three graded "
                "answers behind it — shown because it is your real data, but "
                "too thin to read against the others.",
                st["note"],
            ))

    flow.append(Paragraph(
        "Scores are an AI assessment against a fixed, disclosed rubric "
        "(Communication 30%, Confidence 25%, Technical relevance 30%, "
        "Professionalism 15%), not a certified evaluation. Every figure in "
        "this report comes from completed interviews only.",
        st["note"],
    ))

    doc.build(flow)
    return buffer.getvalue()
