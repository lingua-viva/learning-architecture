"""Layer 4: Holdout Prediction — teacher lens can predict/reproduce held-out artifacts.

Property proved: The system learns teacher patterns well enough to score ≥ threshold on holdout test.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.education.teacher_lens_builder import TeacherLensBuilder


def test_L4_HOLD_001_exam_criteria_overlap_70(teacher_history_dir):
    """L4-HOLD-001: Train on N-1 exams, predict Nth → criteria overlap ≥ 70%.

    Setup: Ingest graded_exam_g3_u1.json as training. Hold out graded_exam_g3_u2.json.
    Pass: holdout_score(graded_exam_g3_u2.json, "exam").criteria_overlap >= 0.70
    Calls: TeacherLensBuilder.ingest(exam_1) → holdout_score(exam_2)
    """
    with tempfile.TemporaryDirectory() as tmp:
        builder = TeacherLensBuilder("teacher-eval", Path(tmp))
        builder.ingest(teacher_history_dir / "graded_exam_g3_u1.json")

        result = builder.holdout_score(teacher_history_dir / "graded_exam_g3_u2.json", "exam")
        assert result.criteria_overlap >= 0.70


def test_L4_HOLD_002_parent_voice_vocabulary_60(teacher_history_dir):
    """L4-HOLD-002: Train on N-1 parent updates, predict Nth → vocabulary overlap ≥ 60%.

    Setup: Ingest parent_update_marco.json. Hold out parent_update_nora.json.
    Pass: holdout_score(parent_update_nora.json, "parent_update").vocabulary_overlap >= 0.60
    """
    with tempfile.TemporaryDirectory() as tmp:
        builder = TeacherLensBuilder("teacher-eval", Path(tmp))
        builder.ingest(teacher_history_dir / "parent_update_marco.json")

        result = builder.holdout_score(teacher_history_dir / "parent_update_nora.json", "parent_update")
        assert result.vocabulary_overlap >= 0.60


def test_L4_HOLD_003_differentiation_approach_match(teacher_history_dir):
    """L4-HOLD-003: Train on N-1 lesson plans, predict Nth → structural_match.

    Setup: Ingest lesson_plan_g3_u1.json. Hold out a second lesson plan.
    Pass: holdout_score(lesson_plan_holdout, "lesson_plan").structural_match >= 0.50

    No second lesson-plan fixture exists in the corpus, so this constructs
    a holdout that mirrors this teacher's documented style (same scaffolding
    vocabulary — visual word banks for foundational, no-scaffold open-ended
    prompts for extended) but a different unit/topic, which is exactly the
    property under test: does the same *style* generalize to new content?
    """
    with tempfile.TemporaryDirectory() as tmp:
        builder = TeacherLensBuilder("teacher-eval", Path(tmp))
        builder.ingest(teacher_history_dir / "lesson_plan_g3_u1.json")

        holdout = {
            "doc_type": "lesson_plan",
            "grade": "G3",
            "unit": "U2",
            "title": "La Famiglia — Lezione 2: I Membri della Famiglia",
            "duration_minutes": 45,
            "ib_programme": "PYP",
            "language_of_instruction": "it",
            "italian_percentage_target": 0.75,
            "learning_objectives": {
                "foundational": "Students name 5+ family members using picture support",
                "on_track": "Students describe their own family in 4+ complete sentences",
                "extended": "Students compare family structures using temporal connectors",
            },
            "scaffolding_pattern": {
                "foundational": ["visual word bank", "sentence frames with gaps", "partner reading"],
                "on_track": ["sentence starters available but optional", "self-check rubric"],
                "extended": ["no scaffold", "open-ended prompt", "peer editing required"],
            },
        }
        holdout_path = Path(tmp) / "holdout_lesson_plan.json"
        holdout_path.write_text(json.dumps(holdout))

        result = builder.holdout_score(holdout_path, "lesson_plan")
        assert result.structural_match >= 0.50


def test_L4_HOLD_004_assessment_strengths_match(teacher_history_dir):
    """L4-HOLD-004: Train on N-1 evaluations, predict Nth → strengths/growth identified.

    Setup: Ingest student_evaluation_q1.json. Hold out a Q2 evaluation.
    Pass: holdout_score(evaluation_q2, "evaluation").overall_score >= 0.50

    No second evaluation fixture exists, so this constructs a Q2 evaluation
    for the same student using this teacher's documented dimension set
    (speaking/writing/reading) — testing whether the assessment structure
    this teacher always uses generalizes to a new quarter.
    """
    with tempfile.TemporaryDirectory() as tmp:
        builder = TeacherLensBuilder("teacher-eval", Path(tmp))
        builder.ingest(teacher_history_dir / "student_evaluation_q1.json")

        holdout = {
            "doc_type": "evaluation",
            "student_id": "student-marco",
            "grade": "G3",
            "quarter": "Q2",
            "date": "2026-02-15",
            "assessment_dimensions": {
                "speaking": {"weight": 0.40, "level": "A2", "descriptor": "Produces longer phrases."},
                "writing": {"weight": 0.30, "level": "A1", "descriptor": "Writes short sentences."},
                "reading": {"weight": 0.30, "level": "A2", "descriptor": "Reads short texts independently."},
            },
            "strengths": ["Growing confidence in speaking"],
            "growth_areas": ["Written production still developing"],
            "rti_status": {"current_tier": 1, "recommended_change": "none"},
        }
        holdout_path = Path(tmp) / "holdout_evaluation_q2.json"
        holdout_path.write_text(json.dumps(holdout))

        result = builder.holdout_score(holdout_path, "evaluation")
        assert result.overall_score >= 0.50
