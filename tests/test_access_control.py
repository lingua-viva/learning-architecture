"""
Cross-Teacher Access Control Tests — permission gating for shared students.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.education.student_lens import StudentLensStore
from src.education.observation_capture import ObservationCapturePipeline
from src.education.access_control import TeacherLensAccess, UnauthorizedLensAccessError


def make_store(tmp_path):
    return StudentLensStore(db_path=tmp_path / "access.db")


def test_unauthorized_teacher_blocked_from_get_lens(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed reading sample at A2", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")

    access = TeacherLensAccess(store)
    with pytest.raises(UnauthorizedLensAccessError):
        access.get_lens("teacher_2", "s1")


def test_authorized_teacher_can_read_lens(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed reading sample at A2", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")

    access = TeacherLensAccess(store)
    lens = access.get_lens("teacher_1", "s1")
    assert lens["student_id"] == "s1"


def test_list_shared_students_identifies_co_teachers_and_excludes_self(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="Math observation", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")
    pipeline.capture(student_id="s1", teacher_id="teacher_2",
                      raw_transcript="English observation", template_type="cefr",
                      cefr_dimension="writing", cefr_level_observed="A2", cefr_direction="progressing")

    access = TeacherLensAccess(store)
    shared = access.list_shared_students("teacher_1")
    assert len(shared) == 1
    assert shared[0].student_id == "s1"
    assert shared[0].co_teachers == ["teacher_2"]
    assert "teacher_1" not in shared[0].co_teachers


def test_student_with_single_observer_has_empty_co_teachers(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="Math observation", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")

    access = TeacherLensAccess(store)
    shared = access.list_shared_students("teacher_1")
    assert shared[0].co_teachers == []


def test_get_colleague_observations_excludes_own_observations(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="Math observation", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")
    pipeline.capture(student_id="s1", teacher_id="teacher_2",
                      raw_transcript="English observation", template_type="cefr",
                      cefr_dimension="writing", cefr_level_observed="A2", cefr_direction="progressing")

    access = TeacherLensAccess(store)
    colleague_obs = access.get_colleague_observations("teacher_1", "s1")
    assert len(colleague_obs) == 1
    assert all(o["teacher_id"] != "teacher_1" for o in colleague_obs)
    assert colleague_obs[0]["teacher_id"] == "teacher_2"


def test_get_colleague_observations_raises_for_unauthorized_teacher(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="Math observation", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")

    access = TeacherLensAccess(store)
    with pytest.raises(UnauthorizedLensAccessError):
        access.get_colleague_observations("teacher_3", "s1")
