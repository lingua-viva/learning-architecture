"""
Trend Analysis Tests — after-class daily workflow layer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.education.student_lens import StudentLensStore
from src.education.observation_capture import ObservationCapturePipeline
from src.education.trend_analysis import TrendAnalyzer


def make_store(tmp_path):
    return StudentLensStore(db_path=tmp_path / "trend.db")


def test_no_observations_yields_zero_count(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    trend = TrendAnalyzer(store).analyze_student("s1")
    assert trend.observation_count == 0
    assert trend.date_range == (None, None)
    assert "No observations" in trend.to_markdown()


def test_cefr_dimension_improvement_detected(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed reading sample at A2", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed reading sample at B1", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="B1", cefr_direction="progressing")

    trend = TrendAnalyzer(store).analyze_student("s1")
    reading = next(d for d in trend.cefr_dimensions if d.dimension == "reading")
    assert reading.first_level == "A2"
    assert reading.latest_level == "B1"
    assert reading.direction == "improved"


def test_cefr_dimension_decline_detected(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed writing sample at B1", template_type="cefr",
                      cefr_dimension="writing", cefr_level_observed="B1", cefr_direction="progressing")
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed writing sample regressed to A2", template_type="cefr",
                      cefr_dimension="writing", cefr_level_observed="A2", cefr_direction="regressing")

    trend = TrendAnalyzer(store).analyze_student("s1")
    writing = next(d for d in trend.cefr_dimensions if d.dimension == "writing")
    assert writing.direction == "declined"


def test_sel_counts_and_dominant_domain(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    pipeline = ObservationCapturePipeline(store=store)
    for _ in range(2):
        pipeline.capture(student_id="s1", teacher_id="teacher_1",
                          raw_transcript="I noticed a peer conflict incident", template_type="sel_incident",
                          sel_domain="peer_relationships", sel_valence="concern")
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed a great moment of kindness", template_type="sel_positive",
                      sel_domain="peer_relationships", sel_valence="positive")

    trend = TrendAnalyzer(store).analyze_student("s1")
    assert trend.sel_concern_count == 2
    assert trend.sel_positive_count == 1
    assert trend.dominant_sel_domain == "peer_relationships"


def test_rti_tier_change_counted(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One", rti_current_tier=1)
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed a tier change decision by the team",
                      template_type="rti_flag", rti_tier=2)

    trend = TrendAnalyzer(store).analyze_student("s1")
    assert trend.rti_tier_changes == 1
    assert trend.rti_tier_current == 2


def test_student_trend_markdown_contains_key_sections(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed reading sample at A2", template_type="cefr",
                      cefr_dimension="reading", cefr_level_observed="A2", cefr_direction="progressing")

    md = TrendAnalyzer(store).analyze_student("s1").to_markdown()
    assert "# Trend Summary" in md
    assert "RTI tier" in md
    assert "CEFR progress" in md


def test_class_summary_aggregates_across_roster(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="A", rti_current_tier=1)
    store.create_lens(student_id="s2", display_name="B", rti_current_tier=2)
    store.create_lens(student_id="s3", display_name="C", rti_current_tier=1)
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed steady reading progress", template_type="literacy")
    pipeline.capture(student_id="s2", teacher_id="teacher_1",
                      raw_transcript="I noticed steady reading progress", template_type="literacy")
    # s3 not observed by teacher_1 -> excluded from this teacher's roster

    summary = TrendAnalyzer(store).analyze_class("teacher_1")
    assert summary.student_count == 2
    assert summary.tier_distribution[1] == 1
    assert summary.tier_distribution[2] == 1
    assert summary.avg_observations_per_student == 1.0


def test_class_summary_counts_flagged_students(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="A")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(
        student_id="s1", teacher_id="teacher_1",
        raw_transcript="I noticed urgent concern", template_type="sel_incident",
        sel_domain="emotional_regulation", sel_valence="concern", urgency_flag=True,
    )
    summary = TrendAnalyzer(store).analyze_class("teacher_1")
    assert summary.students_flagged == 1


def test_class_summary_markdown(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="A")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed steady progress", template_type="literacy")
    md = TrendAnalyzer(store).analyze_class("teacher_1").to_markdown()
    assert "# Class Summary" in md
    assert "RTI tier distribution" in md
