"""Summaries (U10) reads the support profile and profile strengths through the
lens field contract's OUT filter (2026-09-04).

Before this, a parent note was built from the observation log only: a report
card's strengths and a teacher's Observe note never reached it. Now it reads
`requires("parent_report")`, says what it lacked, and every support-profile
sentence carries the entry id behind it. Fixture data is fictional.
"""

from __future__ import annotations

import pytest

from src.education.parent_report import ParentReportGenerator
from src.education.student_lens import StudentLensStore
from src.lingua_viva.data_in_contracts import ExtractedField, ExtractionResult
from src.lingua_viva.lens_field_contract import MissingEssentialFieldError, requires
from src.lingua_viva.student_lens_writer import write_student_lens


def _field(path, value, status="verified"):
    return ExtractedField(field_path=path, value=value, confidence=0.9,
                          supporting_chunk_ids=["c1"], status=status)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "lenses.db"))
    s = StudentLensStore(db_path=tmp_path / "lenses.db")
    s.create_lens(student_id="s1", display_name="Amina")
    yield s
    s.close()


def test_parent_report_declares_the_support_profile():
    paths = {r.path for r in requires("parent_report")}
    assert {"display_name", "support_profile", "strengths_profile"} <= paths


def test_report_card_strengths_reach_the_parent_note(store):
    write_student_lens(ExtractionResult("student_lens", [
        _field("support_profile.categories.learning_and_cognition.strengths", "retelling stories with key details"),
        _field("support_profile.categories.learning_and_cognition.strategies_worked", "sentence starters for writing"),
        _field("academic_strengths", "reading comprehension"),
    ], [], ["report_card.txt"]), store=store, hint={"student_id": "s1"})
    draft = ParentReportGenerator(store).generate_draft("s1", "teacher_1")
    body = draft.body.lower()
    assert "retelling stories with key details" in body
    assert "sentence starters for writing" in body
    assert "reading comprehension" in body
    assert "support_profile" in draft.fields_used and "strengths_profile" in draft.fields_used
    assert len(draft.source_entry_ids) == 3            # one id per sentence drawn from the lens
    assert draft.fields_enriching_missing == ["grade_level", "home_languages", "assessment_profile"]


def test_an_observe_note_reaches_the_parent_note(store):
    from src.lingua_viva.observe_to_lens import observe_comment_to_lens_sync

    observe_comment_to_lens_sync(
        "Amina helped a classmate today. Listening: A2.",
        student_id="s1", display_name="Amina", teacher_id="teacher_1", store=store,
    )
    # the observation-derived CEFR is read by the trend analyser as before;
    # the profile read happens too, and the draft says what it did not have
    draft = ParentReportGenerator(store).generate_draft("s1", "teacher_1")
    assert "support_profile" in draft.fields_used


def test_needs_and_unconfirmed_and_personal_context_never_reach_a_parent(store):
    write_student_lens(ExtractionResult("student_lens", [
        _field("support_profile.categories.learning_and_cognition.needs", "struggles with decoding"),
        _field("support_profile.categories.personal_context.strengths", "family situation detail"),
        _field("support_profile.categories.social_skills.strengths", "unconfirmed guess", status="needs_confirmation"),
    ], [], ["report_card.txt"]), store=store, hint={"student_id": "s1"})
    draft = ParentReportGenerator(store).generate_draft("s1", "teacher_1")
    body = draft.body.lower()
    assert "decoding" not in body                    # needs bucket is teacher-facing
    assert "family situation" not in body            # personal_context excluded for family audience
    assert "unconfirmed guess" not in body           # needs_confirmation parked in review, never written
    assert draft.source_entry_ids == []


def test_a_lens_without_a_name_refuses_to_render(store):
    store._conn.execute("UPDATE students SET display_name = '' WHERE student_id = 's1'")
    store._conn.commit()
    with pytest.raises(MissingEssentialFieldError):
        ParentReportGenerator(store).generate_draft("s1", "teacher_1")


def test_trauma_safety_still_gates_lens_sentences(store):
    from src.education.content_differentiator import TraumaSafetyError

    store.add_support_entry("s1", "learning_and_cognition", "strengths",
                            "being a refugee student who copes", created_by="teacher_1")
    with pytest.raises(TraumaSafetyError):
        ParentReportGenerator(store).generate_draft("s1", "teacher_1")
