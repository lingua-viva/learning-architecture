"""
Weekly Recommendation Engine Tests — end-of-week teacher planning artifact.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.education.student_lens import StudentLensStore
from src.education.observation_capture import ObservationCapturePipeline
from src.education.weekly_recommendation import WeeklyRecommendationGenerator, UNOBSERVED_WEEK_DAYS


def make_store(tmp_path):
    return StudentLensStore(db_path=tmp_path / "weekly.db")


def backdate(store, student_id, days_ago):
    from datetime import datetime, timedelta, timezone
    past = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    store._conn.execute("UPDATE students SET updated_at = ? WHERE student_id = ?", (past, student_id))
    store._conn.commit()


def test_empty_roster_produces_no_recommendations(tmp_path):
    store = make_store(tmp_path)
    rec = WeeklyRecommendationGenerator(store).generate("teacher_1")
    assert rec.priority_students == []
    assert rec.unobserved_this_week == []
    assert rec.class_summary.student_count == 0


def test_roster_scoped_to_teacher(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    store.create_lens(student_id="s2", display_name="Omar")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="note", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")
    pipeline.capture(student_id="s2", teacher_id="teacher_2",
                      raw_transcript="note", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")

    rec = WeeklyRecommendationGenerator(store).generate("teacher_1")
    assert rec.class_summary.student_count == 1


def test_active_escalation_surfaces_as_priority(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="urgent safety concern noted",
                      template_type="sel_incident", sel_domain="safety", sel_valence="concern",
                      urgency_flag=True)

    rec = WeeklyRecommendationGenerator(store).generate("teacher_1")
    assert len(rec.priority_students) == 1
    assert rec.priority_students[0].student_id == "s1"
    assert rec.priority_students[0].reasons


def test_cefr_regression_surfaces_as_priority(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    store._conn.execute("UPDATE students SET cefr_trajectory_30d = 'regressing' WHERE student_id = 's1'")
    store._conn.commit()
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="note", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="regressing")

    rec = WeeklyRecommendationGenerator(store).generate("teacher_1")
    assert any("regressing" in r for item in rec.priority_students for r in item.reasons)


def test_unobserved_student_surfaced_and_scoped_by_threshold(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="note", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")
    backdate(store, "s1", UNOBSERVED_WEEK_DAYS + 1)

    rec = WeeklyRecommendationGenerator(store).generate("teacher_1")
    assert len(rec.unobserved_this_week) == 1
    assert rec.unobserved_this_week[0].student_id == "s1"


def test_recently_observed_student_not_in_unobserved_list(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="note", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")

    rec = WeeklyRecommendationGenerator(store).generate("teacher_1")
    assert rec.unobserved_this_week == []


def test_curriculum_note_documents_missing_unit_data(tmp_path):
    store = make_store(tmp_path)
    rec = WeeklyRecommendationGenerator(store).generate("teacher_1")
    assert "curriculum calendar" in rec.curriculum_note
    assert "known gap" in rec.curriculum_note


def test_to_markdown_contains_key_sections(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="urgent safety concern noted",
                      template_type="sel_incident", sel_domain="safety", sel_valence="concern",
                      urgency_flag=True)

    md = WeeklyRecommendationGenerator(store).generate("teacher_1").to_markdown()
    assert "# Weekly Recommendation" in md
    assert "# Class Summary" in md
    assert "Priority for Next Week" in md
    assert "curriculum calendar" in md


def test_quiet_week_message_when_no_flags(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="note", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")

    md = WeeklyRecommendationGenerator(store).generate("teacher_1").to_markdown()
    assert "quiet week" in md
