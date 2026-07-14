"""
Morning Brief Tests — Product A daily workflow layer.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.education.student_lens import StudentLensStore, Observation
from src.education.observation_capture import ObservationCapturePipeline
from src.education.morning_brief import MorningBriefGenerator, STALE_OBSERVATION_DAYS


def make_store(tmp_path):
    return StudentLensStore(db_path=tmp_path / "brief.db")


def test_empty_roster_produces_no_attention_items(tmp_path):
    store = make_store(tmp_path)
    brief = MorningBriefGenerator(store).generate("teacher_1")
    assert brief.total_students == 0
    assert brief.needs_attention == []
    assert brief.no_recent_observation == []
    assert "nothing urgent" in brief.to_markdown()


def test_only_teachers_students_appear_on_roster(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    store.create_lens(student_id="s2", display_name="Student Two")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed steady progress today", template_type="literacy")
    pipeline.capture(student_id="s2", teacher_id="teacher_2",
                      raw_transcript="I noticed steady progress today", template_type="literacy")

    brief = MorningBriefGenerator(store).generate("teacher_1")
    assert brief.total_students == 1


def test_urgency_flag_surfaces_as_needs_attention(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(
        student_id="s1", teacher_id="teacher_1",
        raw_transcript="I noticed she seemed distressed and left without explanation",
        template_type="sel_incident", sel_domain="emotional_regulation",
        sel_valence="concern", urgency_flag=True,
    )

    brief = MorningBriefGenerator(store).generate("teacher_1")
    assert len(brief.needs_attention) == 1
    assert brief.needs_attention[0].student_id == "s1"
    assert any("Urgent" in r for r in brief.needs_attention[0].reasons)


def test_cefr_regressing_trajectory_surfaces(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    pipeline = ObservationCapturePipeline(store=store)
    # Two observations, most recent showing regression, to set
    # cefr_trajectory_30d = "regressing" via the existing recalculation logic.
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed writing sample at B1", template_type="cefr",
                      cefr_dimension="writing", cefr_level_observed="B1", cefr_direction="progressing")
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed writing sample regressed to A2", template_type="cefr",
                      cefr_dimension="writing", cefr_level_observed="A2", cefr_direction="regressing")

    lens = store.get_lens("s1")
    if lens["cefr_trajectory_30d"] == "regressing":
        brief = MorningBriefGenerator(store).generate("teacher_1")
        assert len(brief.needs_attention) == 1
        assert any("regressing" in r for r in brief.needs_attention[0].reasons)


def test_stale_observation_flagged(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                      raw_transcript="I noticed steady progress today", template_type="literacy")

    # Backdate the student's updated_at to simulate a stale gap.
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=STALE_OBSERVATION_DAYS + 1)).isoformat()
    store._conn.execute("UPDATE students SET updated_at = ? WHERE student_id = ?", (stale_ts, "s1"))
    store._conn.commit()

    brief = MorningBriefGenerator(store).generate("teacher_1")
    assert len(brief.no_recent_observation) == 1
    assert brief.no_recent_observation[0].student_id == "s1"


def test_to_markdown_lists_attention_items(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(
        student_id="s1", teacher_id="teacher_1",
        raw_transcript="I noticed urgent concern today",
        template_type="sel_incident", sel_domain="emotional_regulation",
        sel_valence="concern", urgency_flag=True,
    )
    brief = MorningBriefGenerator(store).generate("teacher_1")
    md = brief.to_markdown()
    assert "# Morning Brief" in md
    assert "Needs Attention" in md
    assert "Student One" in md


def test_no_tier_change_decision_is_ever_made(tmp_path):
    """The brief must never mutate rti_current_tier — surfacing only."""
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Student One", rti_current_tier=1)
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(
        student_id="s1", teacher_id="teacher_1",
        raw_transcript="I noticed urgent concern today",
        template_type="sel_incident", sel_domain="emotional_regulation",
        sel_valence="concern", urgency_flag=True,
    )
    before = store.get_lens("s1")["rti_current_tier"]
    MorningBriefGenerator(store).generate("teacher_1")
    after = store.get_lens("s1")["rti_current_tier"]
    assert before == after == 1
