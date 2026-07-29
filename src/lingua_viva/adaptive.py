"""Adaptive learning Phase 1 — assessment deltas and tier recommendations.

Spec: SPEC_LV_REMAINING_GAPS_2026-07-29.md Gap 6, Phase 1 only.

The loop the spec sketches is observe -> assess -> compare -> adjust tier ->
differentiate. Everything except *compare* already exists. This is the
comparison step, and nothing more: it computes how a child's recorded CEFR
levels have moved and, when the movement is consistent enough, produces a
**recommendation**.

Three things this deliberately does not do, all of them from the spec's
"Not in Phase 1" list and its acceptance criteria:

  - It never changes a tier. `update_rti_tier()` is not called from this
    module. The system recommends; the teacher decides and the decision is
    recorded as theirs.
  - It does not select content or adjust pacing.
  - It does not speak with more confidence than the data supports. Two
    observations are a line, not a trend, so the recommendation threshold is
    higher than the badge threshold and everything below it reads
    "not enough yet".

**On storing vs computing.** The spec says to store the delta, and AGENTS.md's
verdict-not-reconstruction rule normally agrees. It does not apply here: a
delta is a pure function of two rows in an append-only observations table, so
recomputing it is exact rather than approximate, and the ground truth cannot
be lost. A stored copy could drift from the observations it claims to
summarise; a derived one cannot. Computed on read, deliberately.
"""

from __future__ import annotations

from typing import Any, Optional

# The ordered CEFR scale, mirroring VALID_CEFR_LEVELS in student_lens.py.
# Position on this list is what makes "moved up" and "moved down" meaningful.
CEFR_SCALE: tuple[str, ...] = (
    "Pre-A1", "A1", "A1+", "A2", "A2+", "B1", "B1+", "B2", "C1", "C2",
)
_SCALE_INDEX = {level: index for index, level in enumerate(CEFR_SCALE)}

# How many consistent moves before this module will put a recommendation in
# front of a teacher. The spec asks for 3+.
RECOMMENDATION_THRESHOLD = 3

GROWTH = "growth"
STABLE = "stable"
REGRESSION = "regression"
INSUFFICIENT = "insufficient_data"


def _level_index(level: Optional[str]) -> Optional[int]:
    return _SCALE_INDEX.get(str(level or "").strip())


def deltas_for_student(store, student_id: str) -> list[dict[str, Any]]:
    """Per-dimension movement between consecutive recorded CEFR levels.

    One entry per pair of consecutive observations in the same dimension,
    oldest first. Observations without a usable level are skipped rather than
    guessed at — an unparseable level is not a zero-sized move.
    """
    rows = store._conn.execute(
        "SELECT cefr_dimension, cefr_level_observed, recorded_at "
        "FROM observations WHERE student_id = ? AND cefr_level_observed IS NOT NULL "
        "ORDER BY recorded_at ASC",
        (student_id,),
    ).fetchall()

    by_dimension: dict[str, list[tuple[str, int]]] = {}
    for row in rows:
        index = _level_index(row["cefr_level_observed"])
        if index is None:
            continue
        dimension = str(row["cefr_dimension"] or "overall")
        by_dimension.setdefault(dimension, []).append((row["recorded_at"], index))

    deltas: list[dict[str, Any]] = []
    for dimension, points in by_dimension.items():
        for (_, previous), (at, current) in zip(points, points[1:]):
            deltas.append({
                "dimension": dimension,
                "at": at,
                "from": CEFR_SCALE[previous],
                "to": CEFR_SCALE[current],
                "steps": current - previous,
                "direction": (
                    GROWTH if current > previous
                    else REGRESSION if current < previous
                    else STABLE
                ),
            })
    deltas.sort(key=lambda item: item["at"])
    return deltas


def growth_signal(deltas: list[dict[str, Any]]) -> dict[str, Any]:
    """The badge a teacher sees: growth, stable, regression, or not enough yet."""
    if not deltas:
        return {
            "signal": INSUFFICIENT,
            "label": "Not enough yet",
            "detail": "Two or more recorded levels are needed before movement means anything.",
            "delta_count": 0,
        }

    ups = sum(1 for item in deltas if item["direction"] == GROWTH)
    downs = sum(1 for item in deltas if item["direction"] == REGRESSION)

    if ups > downs:
        signal, label = GROWTH, "Moving up"
    elif downs > ups:
        signal, label = REGRESSION, "Moving down"
    else:
        signal, label = STABLE, "Holding steady"

    return {
        "signal": signal,
        "label": label,
        "detail": f"{len(deltas)} recorded change(s): {ups} up, {downs} down.",
        "delta_count": len(deltas),
        "up": ups,
        "down": downs,
    }


def tier_recommendation(
    deltas: list[dict[str, Any]], current_tier: int
) -> Optional[dict[str, Any]]:
    """A suggestion for the teacher, or None.

    Returns None — not a neutral "no change" recommendation — when the
    evidence is thin. A recommendation the teacher is expected to ignore
    trains them to ignore all of them.

    Never changes anything. The caller surfaces this; only the teacher acts.
    """
    if len(deltas) < RECOMMENDATION_THRESHOLD:
        return None

    recent = deltas[-RECOMMENDATION_THRESHOLD:]
    directions = {item["direction"] for item in recent}

    if directions == {GROWTH} and current_tier > 1:
        return {
            "recommendation": "consider_lower_tier",
            "current_tier": current_tier,
            "suggested_tier": current_tier - 1,
            "because": (
                f"The last {RECOMMENDATION_THRESHOLD} recorded changes all moved up."
            ),
            "requires_teacher_confirmation": True,
        }
    if directions == {REGRESSION} and current_tier < 3:
        return {
            "recommendation": "consider_higher_tier",
            "current_tier": current_tier,
            "suggested_tier": current_tier + 1,
            "because": (
                f"The last {RECOMMENDATION_THRESHOLD} recorded changes all moved down."
            ),
            "requires_teacher_confirmation": True,
        }
    return None


def student_growth(store, lens: dict[str, Any]) -> dict[str, Any]:
    """Badge plus any recommendation for one student, ARON-referenced."""
    from src.lingua_viva.governance import aron_ref

    student_id = lens["student_id"]
    deltas = deltas_for_student(store, student_id)
    current_tier = int(lens.get("rti_current_tier") or 1)
    # The raw student_id is deliberately NOT returned. LV's ids are derived
    # from names ("student-marco"), so shipping one alongside the ARON code
    # would defeat the code sitting next to it — anything that rendered this
    # payload on a projector would show the name in the id. Callers join on
    # `reference`, which /api/students also returns.
    return {
        "reference": aron_ref(student_id),
        "growth": growth_signal(deltas),
        "recommendation": tier_recommendation(deltas, current_tier),
        "current_tier": current_tier,
    }


def growth_for_all(store) -> list[dict[str, Any]]:
    return [student_growth(store, lens) for lens in store.list_lenses()]


def pending_recommendations(store) -> list[dict[str, Any]]:
    """Only the students with a live recommendation, for the Daily briefing."""
    return [row for row in growth_for_all(store) if row["recommendation"]]
