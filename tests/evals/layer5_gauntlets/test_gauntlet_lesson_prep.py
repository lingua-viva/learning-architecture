"""Layer 5 Gauntlet: Adaptive Lesson Preparation — ingest docs, build lens, generate, verify.

Property proved: The full teacher workflow produces grounded, style-matched, grade-fenced output.

Only one G3 lesson-plan fixture exists in the corpus
(synthetic_teacher_history/lesson_plan_g3_u1.json). "3 past G3 lesson plans"
is satisfied by adding 2 synthetic G3 units in this teacher's documented
style (same scaffolding vocabulary: visual word banks for foundational,
no-scaffold open-ended prompts for extended) — consistent with how
test_L4_HOLD_003 in test_holdout_prediction.py already had to construct a
holdout lesson plan for the same reason.

Actual grade-fencing (DocumentStore.search() filtering by grade at the
storage layer) is separately covered — and explicitly left skipped as
out-of-scope — by tests/evals/layer2_retrieval/test_grade_fencing.py. Here
the retriever is a test double, so "grade fenced" tests the *consumer*
side of the contract: given a retriever that only returns G3-tagged
chunks, does the generated pack faithfully reflect only what it was
given, with zero G4/G5 leakage.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.education.content_differentiator import ContentDifferentiator, LessonInput
from src.education.teacher_lens_builder import TeacherLensBuilder


def _synthetic_g3_lesson_plan(unit: str, title: str) -> dict:
    return {
        "doc_type": "lesson_plan",
        "grade": "G3",
        "unit": unit,
        "title": title,
        "duration_minutes": 45,
        "ib_programme": "PYP",
        "language_of_instruction": "it",
        "learning_objectives": {
            "foundational": "Students name 5+ items using picture support",
            "on_track": "Students describe the topic in 4+ complete sentences",
            "extended": "Students compare two perspectives using temporal connectors",
        },
        "scaffolding_pattern": {
            "foundational": ["visual word bank", "sentence frames with gaps", "partner reading"],
            "on_track": ["sentence starters available but optional", "self-check rubric"],
            "extended": ["no scaffold", "open-ended prompt", "peer editing required"],
        },
    }


def _g3_lesson_plan_files(tmp_dir: Path, teacher_history_dir: Path) -> list[Path]:
    files = [teacher_history_dir / "lesson_plan_g3_u1.json"]
    for unit, title in (("U2", "La Famiglia — Lezione 2"), ("U3", "La Scuola — Lezione 1")):
        p = tmp_dir / f"lesson_plan_g3_{unit.lower()}.json"
        p.write_text(json.dumps(_synthetic_g3_lesson_plan(unit, title)))
        files.append(p)
    return files


def _g4_lesson_plan_file(tmp_dir: Path) -> Path:
    plan = _synthetic_g3_lesson_plan("U1", "G4 Wrong-Grade Content — Should Never Appear")
    plan["grade"] = "G4"
    plan["scaffolding_pattern"]["foundational"].append("G4-ONLY-MARKER-do-not-leak")
    p = tmp_dir / "lesson_plan_g4_u1.json"
    p.write_text(json.dumps(plan))
    return p


class GradeFencedRetriever:
    """Test double standing in for DocumentStore.search(): only returns
    chunks whose grade matches the query's declared grade — the property
    a real grade-fenced retriever must uphold."""

    def __init__(self, chunks_by_grade: dict[str, list[dict]], grade: str):
        self.chunks_by_grade = chunks_by_grade
        self.grade = grade

    def retrieve(self, query, domain, k=3):
        return self.chunks_by_grade.get(self.grade, [])[:k]


def _lesson() -> LessonInput:
    return LessonInput(
        ib_programme="PYP",
        subject="Language",
        unit_title="La Routine Quotidiana",
        topic="Daily routines vocabulary in Italian",
        atl_skills=["COMM-01"],
        cefr_target="A2",
        duration_minutes=45,
        created_by="teacher_eval",
    )


def test_gauntlet_ingest_past_lesson_plans(teacher_history_dir):
    """Teacher ingests 3 past G3 lesson plans successfully."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        builder = TeacherLensBuilder("teacher-eval", tmp_path / "lens_storage")
        for f in _g3_lesson_plan_files(tmp_path, teacher_history_dir):
            result = builder.ingest(f)
            assert result.classified_type == "lesson_plan"
            assert result.confidence > 0.0


def test_gauntlet_teacher_lens_builds(teacher_history_dir):
    """Teacher Lens builds from ingested plans — all dimensions populated."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        builder = TeacherLensBuilder("teacher-eval", tmp_path / "lens_storage")
        for f in _g3_lesson_plan_files(tmp_path, teacher_history_dir):
            builder.ingest(f)

        lens = builder.build_lens()
        assert lens.ingested_doc_count == 3
        for tier in ("foundational", "on_track", "extended"):
            assert lens.differentiation_style[tier]["scaffolding"]
        assert lens.pacing_style


def test_gauntlet_g3_pack_provenance_grade_fenced(teacher_history_dir):
    """Request G3-U1 pack → pack provenance traces ONLY to G3 documents."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        builder = TeacherLensBuilder("teacher-eval", tmp_path / "lens_storage")
        for f in _g3_lesson_plan_files(tmp_path, teacher_history_dir):
            builder.ingest(f)
        lens = builder.build_lens()

        g3_file = teacher_history_dir / "lesson_plan_g3_u1.json"
        g4_file = _g4_lesson_plan_file(tmp_path)
        chunks_by_grade = {
            "G3": [{
                "text": "Morning routine actions practiced with picture cards and TPR.",
                "source_file": str(g3_file), "section": "MORNING ROUTINE",
                "page_start": 1, "page_end": 1,
            }],
            "G4": [{
                "text": "G4-ONLY-MARKER-do-not-leak content about a different unit entirely.",
                "source_file": str(g4_file), "section": "WRONG GRADE",
                "page_start": 1, "page_end": 1,
            }],
        }
        retriever = GradeFencedRetriever(chunks_by_grade, grade="G3")

        pack = ContentDifferentiator().generate_with_teacher_lens(
            _lesson(), lens, retriever=retriever, domain="curriculum"
        )

        assert pack.source_provenance
        for entry in pack.source_provenance:
            assert entry["source_file"] == str(g3_file)


def test_gauntlet_pack_style_matches_teacher(teacher_history_dir):
    """Pack differentiation matches teacher's historical style (scaffolding pattern)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        builder = TeacherLensBuilder("teacher-eval", tmp_path / "lens_storage")
        for f in _g3_lesson_plan_files(tmp_path, teacher_history_dir):
            builder.ingest(f)
        lens = builder.build_lens()

        pack = ContentDifferentiator().generate_with_teacher_lens(_lesson(), lens)

        for tier in ("foundational", "on_track", "extended"):
            assert pack.tiers[tier]["teacher_scaffolding"] == lens.differentiation_style[tier]["scaffolding"]


def test_gauntlet_zero_wrong_grade_content(teacher_history_dir):
    """Zero G4/G5 content appears anywhere in the generated output."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        builder = TeacherLensBuilder("teacher-eval", tmp_path / "lens_storage")
        for f in _g3_lesson_plan_files(tmp_path, teacher_history_dir):
            builder.ingest(f)
        lens = builder.build_lens()

        g3_file = teacher_history_dir / "lesson_plan_g3_u1.json"
        g4_file = _g4_lesson_plan_file(tmp_path)
        chunks_by_grade = {
            "G3": [{
                "text": "Morning routine actions practiced with picture cards and TPR.",
                "source_file": str(g3_file), "section": "MORNING ROUTINE",
                "page_start": 1, "page_end": 1,
            }],
            "G4": [{
                "text": "G4-ONLY-MARKER-do-not-leak content about a different unit entirely.",
                "source_file": str(g4_file), "section": "WRONG GRADE",
                "page_start": 1, "page_end": 1,
            }],
        }
        retriever = GradeFencedRetriever(chunks_by_grade, grade="G3")

        pack = ContentDifferentiator().generate_with_teacher_lens(
            _lesson(), lens, retriever=retriever, domain="curriculum"
        )

        pack_text = json.dumps(pack.to_dict())
        assert "G4-ONLY-MARKER-do-not-leak" not in pack_text
        assert str(g4_file) not in pack_text


def test_gauntlet_source_mode_teacher_adapted(teacher_history_dir):
    """Output source_mode is 'teacher_adapted' when all paths available."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        builder = TeacherLensBuilder("teacher-eval", tmp_path / "lens_storage")
        for f in _g3_lesson_plan_files(tmp_path, teacher_history_dir):
            builder.ingest(f)
        lens = builder.build_lens()

        g3_file = teacher_history_dir / "lesson_plan_g3_u1.json"
        retriever = GradeFencedRetriever(
            {"G3": [{
                "text": "Morning routine actions practiced with picture cards and TPR.",
                "source_file": str(g3_file), "section": "MORNING ROUTINE",
                "page_start": 1, "page_end": 1,
            }]},
            grade="G3",
        )

        pack = ContentDifferentiator().generate_with_teacher_lens(
            _lesson(), lens, retriever=retriever, domain="curriculum"
        )
        assert pack.source_mode == "teacher_adapted"
