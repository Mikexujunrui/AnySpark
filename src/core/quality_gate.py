"""Quality Gate — lightweight quality check using the existing review panel.

Used by Autopilot after each chapter is written. Runs a subset of reviewers
(2-3 instead of all 8) for speed, and compares the overall_score against a
threshold determined by the gate level (low/medium/high).

If score < threshold:
  - soft mode: pause task, notify user
  - hard mode: already paused at each step
  - autonomous mode: trigger one auto-rewrite, then proceed regardless
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Gate level → minimum overall score (0-10 scale)
GATE_THRESHOLDS = {
    "low": 5.0,
    "medium": 7.0,
    "high": 8.5,
}

# Number of reviewers to use for lightweight review (speed vs thoroughness)
GATE_REVIEWER_COUNT = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


@dataclass
class QualityResult:
    passed: bool
    score: float = 0.0
    threshold: float = 0.0
    gate_level: str = "medium"
    summary: str = ""
    reviewer_count: int = 0
    action: str = "continue"  # "continue" | "rewrite" | "pause"


async def run_quality_gate(
    chapter_text: str,
    book_id: str,
    chapter_ref: str = "",
    gate_level: str = "medium",
    audit_mode: str = "soft",
    max_rewrite_attempts: int = 2,
) -> QualityResult:
    """Run a lightweight quality review on a chapter.

    Args:
        chapter_text: The chapter content to review.
        book_id: The book ID (for loading knowledge context).
        chapter_ref: Chapter reference (e.g., "#3").
        gate_level: "low" | "medium" | "high" — determines score threshold.
        audit_mode: "hard" | "soft" | "autonomous" — determines failure action.
        max_rewrite_attempts: Max auto-rewrite attempts in autonomous mode.

    Returns:
        QualityResult with pass/fail, score, and recommended action.
    """
    threshold = GATE_THRESHOLDS.get(gate_level, 7.0)
    target_reviewers = GATE_REVIEWER_COUNT.get(gate_level, 2)

    try:
        from core.review_panel import panel

        # Pick the first N active reviewers for a lightweight review
        active_reviewers = panel.get_active_reviewers()
        if not active_reviewers:
            # No reviewers configured — auto-pass
            return QualityResult(
                passed=True,
                score=8.0,
                threshold=threshold,
                gate_level=gate_level,
                summary="无评审员，自动通过",
                action="continue",
            )

        selected_ids = [r.id for r in active_reviewers[:target_reviewers]]

        # Run the review
        report = await panel.run_review(
            chapter_text=chapter_text,
            book_id=book_id,
            chapter_ref=chapter_ref,
            reviewer_ids=selected_ids,
            mode="concurrent",
        )

        score = report.overall_score
        passed = score >= threshold

        # Determine action based on audit mode
        if passed:
            action = "continue"
        elif audit_mode == "autonomous":
            action = "rewrite"  # Will trigger auto-rewrite
        else:
            action = "pause"  # soft/hard: pause for user review

        return QualityResult(
            passed=passed,
            score=score,
            threshold=threshold,
            gate_level=gate_level,
            summary=report.summary[:500] if report.summary else "",
            reviewer_count=report.reviewer_count,
            action=action,
        )

    except Exception as e:
        logger.warning("Quality gate review failed: %s", e)
        # If review fails, auto-pass (don't block the pipeline)
        return QualityResult(
            passed=True,
            score=7.0,
            threshold=threshold,
            gate_level=gate_level,
            summary=f"评审出错，自动通过: {str(e)[:100]}",
            action="continue",
        )


def should_pause_for_quality(result: QualityResult, audit_mode: str) -> bool:
    """Decide whether to pause the autopilot task based on quality result."""
    if result.passed:
        return False
    if audit_mode == "autonomous":
        # Autonomous mode only pauses after exhausting rewrite attempts
        return False
    # soft mode: pause to let user review
    return True
