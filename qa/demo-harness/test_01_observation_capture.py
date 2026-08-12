"""Test 01 — Observation Capture Pipeline

Scenario: A teacher at an IB international school records observations
about three students during an English MYP3 lesson on persuasive writing.
The observations update each student's lens with evidence-backed claims.

Claudia: run this with `pytest qa/demo-harness/test_01_observation_capture.py -v`
Then change the observation text to match real classroom notes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure LV imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("LV_STUDENT_DB_PATH", "/tmp/lv-demo-harness-students.db")


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


# ── The three students ──────────────────────────────────────────────

STUDENTS = [
    {
        "student_id": "demo-amina",
        "display_name": "Amina",
        "grade_level": "MYP3",
        "campus": "nairobi",
        "home_languages": ["sw", "en"],
    },
    {
        "student_id": "demo-david",
        "display_name": "David",
        "grade_level": "MYP3",
        "campus": "nairobi",
        "home_languages": ["en"],
    },
    {
        "student_id": "demo-grace",
        "display_name": "Grace",
        "grade_level": "MYP3",
        "campus": "nairobi",
        "home_languages": ["fr", "en"],
    },
]

# ── Observation text (replace with real notes!) ─────────────────────

OBSERVATIONS = [
    {
        "student_id": "demo-amina",
        "text": "Amina used strong topic sentences in her persuasive paragraph today. "
                "She structured her argument clearly but needed support with connective "
                "phrases between her second and third points. Sentence starter card helped.",
    },
    {
        "student_id": "demo-david",
        "text": "David read his persuasive piece aloud confidently. His vocabulary is "
                "expanding — used 'compelling' and 'furthermore' correctly. Still working "
                "on paragraph organization; tends to put his strongest point last.",
    },
    {
        "student_id": "demo-grace",
        "text": "Grace translated her argument from French to English and the structure "
                "held well. She self-corrected two verb tenses. She encouraged David to "
                "reorganize his paragraph before presenting.",
    },
]


def test_create_students(student_store) -> None:
    """Create three student lenses — verify they exist."""
    for s in STUDENTS:
        student_store.create_lens(**s)

    for s in STUDENTS:
        lens = student_store.get_lens(s["student_id"])
        assert lens["display_name"] == s["display_name"]
        assert lens["grade_level"] == s["grade_level"]


def test_record_observations(student_store) -> None:
    """Record observations and verify lens updates."""
    from src.education.student_lens import Observation

    # Create students first
    for s in STUDENTS:
        student_store.create_lens(**s)

    # Record each observation
    for obs in OBSERVATIONS:
        observation = Observation(
            student_id=obs["student_id"],
            teacher_id="teacher-claudia",
            template_type="general",
            raw_transcript=obs["text"],
        )
        student_store.append_observation(observation)

    # Verify observations landed (export_lens includes observation history)
    for obs in OBSERVATIONS:
        lens = student_store.export_lens(obs["student_id"])
        assert len(lens["observations"]) >= 1
        latest = lens["observations"][-1]
        assert latest["raw_transcript"] == obs["text"]
        assert latest["teacher_id"] == "teacher-claudia"


def test_observation_privacy(student_store) -> None:
    """Student data stays local — no external calls made."""
    for s in STUDENTS:
        student_store.create_lens(**s)

    from src.education.student_lens import Observation
    obs = Observation(
        student_id="demo-amina",
        teacher_id="teacher-claudia",
        template_type="general",
        raw_transcript=OBSERVATIONS[0]["text"],
    )
    student_store.append_observation(obs)

    # The observation is in the local DB, not sent anywhere
    lens = student_store.export_lens("demo-amina")
    assert lens["observations"][-1]["origin"] == "local"
    assert lens["observations"][-1]["sync_status"] == "pending"
