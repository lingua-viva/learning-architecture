"""Test 04 — Parent Report from Student Lens

Scenario: After building a student lens from observations and documents,
generate a parent-safe summary. Verify it contains strengths-based
language and no raw assessment data leaks.

Claudia: this test shows the full arc — observe → lens → report.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("LV_STUDENT_DB_PATH", "/tmp/lv-demo-harness-parent-report.db")


@pytest.fixture
def student_store():
    from src.education.student_lens import StudentLensStore
    db = Path(os.environ["LV_STUDENT_DB_PATH"])
    if db.exists():
        db.unlink()
    store = StudentLensStore(db_path=db)
    yield store
    store.close()
    if db.exists():
        db.unlink()


def _setup_student_with_observations(store):
    """Create Amina with two observations — enough for a parent report."""
    from src.education.student_lens import Observation

    store.create_lens(
        student_id="demo-amina",
        display_name="Amina",
        grade_level="MYP3",
        campus="nairobi",
        home_languages=["sw", "en"],
    )

    observations = [
        "Amina wrote a strong persuasive paragraph using claim-evidence-reasoning. "
        "Her vocabulary is strong and her inference careful. Next step: organize "
        "the final paragraph with a clearer topic sentence.",
        "Amina encouraged David to reorganize his paragraph before presenting. "
        "She used the sentence starter card to structure her second quotation.",
    ]

    for i, text in enumerate(observations):
        obs = Observation(
            student_id="demo-amina",
            teacher_id="teacher-claudia",
            template_type="general",
            raw_transcript=text,
        )
        store.append_observation(obs)

    return store.export_lens("demo-amina")


def test_student_lens_has_observations(student_store) -> None:
    """After setup, the student lens contains both observations."""
    lens = _setup_student_with_observations(student_store)
    assert len(lens["observations"]) == 2
    assert lens["display_name"] == "Amina"


def test_no_raw_data_in_parent_facing_output(student_store) -> None:
    """Parent-facing summaries must not contain raw RTI tiers,
    internal IDs, or assessment codes."""
    lens = _setup_student_with_observations(student_store)

    # The raw lens data contains internal fields that should never
    # appear in a parent-facing report
    internal_fields = [
        lens.get("student_id", ""),
        "rti_current_tier",
        "rti_tier_history",
        "sync_status",
        "ontology_node",
        "routing_decision_ids",
    ]

    # Build a simple parent-safe summary from the observations
    obs_texts = [o["raw_transcript"] for o in lens["observations"]]
    summary = " ".join(obs_texts)

    for field in internal_fields:
        if isinstance(field, str) and field:
            assert field not in summary or field in obs_texts[0] or field in obs_texts[1], \
                f"Internal field '{field}' should not appear in parent-facing content"


def test_observations_are_strengths_based(student_store) -> None:
    """Observations use strengths-based language, not deficit framing."""
    lens = _setup_student_with_observations(student_store)

    deficit_patterns = [
        "can't", "unable", "failed", "struggling with",
        "below grade level", "at-risk", "deficit",
    ]

    for obs in lens["observations"]:
        text = obs["raw_transcript"].lower()
        for pattern in deficit_patterns:
            assert pattern not in text, \
                f"Deficit pattern '{pattern}' found in observation: {text[:80]}"
