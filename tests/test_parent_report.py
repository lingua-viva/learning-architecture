"""
Parent Progress Report Tests — teacher daily workflow, parent-facing artifact.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.education.student_lens import StudentLensStore
from src.education.observation_capture import ObservationCapturePipeline
from src.education.content_differentiator import TraumaSafetyError
from src.education.parent_report import ParentReportGenerator, VALID_TEMPLATES


def make_store(tmp_path):
    return StudentLensStore(db_path=tmp_path / "parent.db")


def test_invalid_template_type_rejected(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    gen = ParentReportGenerator(store)
    with pytest.raises(ValueError):
        gen.generate_draft("s1", "teacher_1", template_type="not_a_real_template")


def test_draft_mentions_progress_when_cefr_improved(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed reading sample at A2", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed reading sample at B1", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="B1", cefr_direction="progressing")

    gen = ParentReportGenerator(store)
    draft = gen.generate_draft("s1", "teacher_1")
    assert "Amina" in draft.subject_line
    assert "progress" in draft.body.lower()
    assert draft.home_activities


def test_draft_never_contains_rti_or_concern_clinical_language(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina", rti_current_tier=2)
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(
        student_id="s1", teacher_id="teacher_1",
        raw_transcript="I noticed a peer conflict incident today",
        template_type="sel_incident", sel_domain="peer_relationships", sel_valence="concern",
    )
    gen = ParentReportGenerator(store)
    draft = gen.generate_draft("s1", "teacher_1")
    lowered = draft.body.lower()
    for banned in ("tier", "rti", "concern", "intervention", "flagged", "escalat"):
        assert banned not in lowered


def test_approve_locks_attribution_false(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina", home_languages=["ar", "en"])
    gen = ParentReportGenerator(store)
    draft = gen.generate_draft("s1", "teacher_1")
    artifact = gen.approve(draft, teacher_display_name="Ms. Fatima")
    assert artifact.attribution_visible_to_parent is False
    assert artifact.from_label == "Ms. Fatima (Class Teacher)"
    assert artifact.language == "ar"


def test_approve_has_no_parameter_to_set_attribution_true(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    gen = ParentReportGenerator(store)
    draft = gen.generate_draft("s1", "teacher_1")
    import inspect
    sig = inspect.signature(gen.approve)
    assert "attribution_visible_to_parent" not in sig.parameters


def test_teacher_edited_body_used_in_artifact(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    gen = ParentReportGenerator(store)
    draft = gen.generate_draft("s1", "teacher_1")
    artifact = gen.approve(draft, teacher_display_name="Ms. Fatima",
                            teacher_edited_body="Amina had a wonderful week overall.")
    assert artifact.body == "Amina had a wonderful week overall."


def test_teacher_edit_reintroducing_unsafe_label_still_blocked(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    gen = ParentReportGenerator(store)
    draft = gen.generate_draft("s1", "teacher_1")
    with pytest.raises(TraumaSafetyError):
        gen.approve(draft, teacher_display_name="Ms. Fatima",
                    teacher_edited_body="Amina is a refugee student who is doing well.")


def test_parent_artifact_has_no_ai_or_internal_fields(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    gen = ParentReportGenerator(store)
    draft = gen.generate_draft("s1", "teacher_1")
    artifact = gen.approve(draft, teacher_display_name="Ms. Fatima")
    field_names = artifact.__dataclass_fields__.keys()
    for forbidden in ("ai_draft", "generating_observation_ids", "student_id", "teacher_id"):
        assert forbidden not in field_names


def test_no_home_languages_defaults_to_en(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    gen = ParentReportGenerator(store)
    draft = gen.generate_draft("s1", "teacher_1")
    artifact = gen.approve(draft, teacher_display_name="Ms. Fatima")
    assert artifact.language == "en"


def test_to_printable_text_is_plain_string(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    gen = ParentReportGenerator(store)
    draft = gen.generate_draft("s1", "teacher_1")
    artifact = gen.approve(draft, teacher_display_name="Ms. Fatima")
    text = artifact.to_printable_text()
    assert "Amina" in text
    assert "Ms. Fatima" in text
    assert "AI" not in text
