from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.education.content_differentiator import LessonInput
from src.lingua_viva.lesson_materials import (
    SYSTEM_PROMPT,
    TierMaterial,
    assign_roster_split,
    assign_tier_groups,
    list_course_library,
    pull_course_library,
    generate_lesson_materials,
    render_printable_packet_html,
    render_printable_packet_markdown,
    select_todays_lesson,
    share_packet_to_drive,
    write_printable_packet,
)
from src.lingua_viva.reasoning import ReasonResult

GOOD_CONTENT = (
    "TITLE: My Daily Routine Practice\n"
    "INSTRUCTIONS: Read the words, then do the activity.\n"
    "EXERCISE:\n"
    "1. Match each picture to the correct word.\n"
    "2. Complete the sentence: Every morning I ___.\n"
    "3. Say one sentence about your morning.\n"
    "SCAFFOLDING NOTES: word bank, sentence starters"
)


class FakeEngine:
    """Mock ReasoningEngine — records every prompt it was asked to reason over."""

    def __init__(self, content: str = GOOD_CONTENT, model_used: str = "mock"):
        self.content = content
        self.model_used = model_used
        self.calls: list[dict] = []

    async def reason(self, query, context=None, model=None, default_model=None, system_prompt=None, local_only=False, max_tokens=2000):
        self.calls.append({"query": query, "system_prompt": system_prompt})
        return ReasonResult(content=self.content, confidence=0.8, model_used=self.model_used)


class FakeStore:
    def __init__(self, roster: list[dict]):
        self.roster = roster
        self.closed = False

    def list_lenses_for_teacher(self, teacher_id: str) -> list[dict]:
        return self.roster

    def close(self) -> None:
        self.closed = True


def _lens(student_id: str, name: str, rti: int = 1, cefr: str = "A2") -> dict:
    return {
        "student_id": student_id,
        "display_name": name,
        "rti_current_tier": rti,
        "cefr_snapshot": {"speaking": cefr},
    }


def _lesson(**overrides) -> LessonInput:
    data = {
        "ib_programme": "PYP",
        "subject": "language",
        "unit_title": "How we express ourselves",
        "topic": "Describing daily routines in Italian",
        "atl_skills": ["communication"],
        "cefr_target": "A2",
        "duration_minutes": 45,
    }
    data.update(overrides)
    return LessonInput(**data)


def _roster() -> list[dict]:
    return [
        _lens("student-marco", "Marco", rti=1, cefr="A2"),   # on_track
        _lens("student-nora", "Nora", rti=3, cefr="A1"),     # foundational
        _lens("student-luca", "Luca", rti=1, cefr="B2"),     # extended
    ]


def _generate(engine=None, roster=None, **kwargs):
    engine = engine if engine is not None else FakeEngine()
    store = FakeStore(_roster() if roster is None else roster)
    kwargs.setdefault("push_to_drive", False)
    return asyncio.run(
        generate_lesson_materials(_lesson(), store=store, engine=engine, **kwargs)
    )


def test_generate_returns_three_tiers():
    result = _generate()
    assert [m.tier for m in result.materials] == ["foundational", "on_track", "extended"]
    for material in result.materials:
        assert material.title == "My Daily Routine Practice"
        assert material.instructions_for_student == "Read the words, then do the activity."
        assert "Match each picture" in material.exercise_body
        assert material.scaffolding == ["word bank", "sentence starters"]
    assert result.sync_status == "not_requested"
    assert result.lesson_summary == "Describing daily routines in Italian (A2 target, 45min)"
    # Roster mapped to the expected tiers (ids in metadata only)
    by_tier = {m.tier: m.student_ids for m in result.materials}
    assert by_tier == {
        "foundational": [],
        "on_track": ["student-marco"],
        "extended": ["student-luca"],
    }
    assert [student.student_id for student in result.individual_support] == ["student-nora"]
    assert result.individual_support[0].reason == "rti_current_tier_3"


def test_assign_roster_split_keeps_explicit_support_apart():
    roster = [
        _lens("student-a", "Student A", rti=1, cefr="A2"),
        {
            **_lens("student-b", "Student B", rti=1, cefr="A2"),
            "support_profile": {"needs_individual_support": True},
        },
    ]
    split = assign_roster_split(FakeStore(roster), "teacher-a")
    assert split.tier_groups["on_track"] == ["student-a"]
    assert split.individual_support[0].student_id == "student-b"
    assert split.individual_support[0].reason == "support_profile_flag"


def test_no_student_names_in_llm_prompts_or_content():
    engine = FakeEngine()
    result = _generate(engine=engine)
    assert len(engine.calls) == 3
    for call in engine.calls:
        joined = f"{call['query']}\n{call['system_prompt']}"
        for name in ("Marco", "Nora", "Luca", "student-marco", "student-nora", "student-luca"):
            assert name not in joined
        assert call["system_prompt"] == SYSTEM_PROMPT
    for material in result.materials:
        for name in ("Marco", "Nora", "Luca"):
            assert name not in material.title
            assert name not in material.instructions_for_student
            assert name not in material.exercise_body


def test_name_leak_in_generated_content_is_rejected():
    leaky = GOOD_CONTENT.replace("Say one sentence", "Marco, say one sentence")
    with pytest.raises(ValueError, match="student_name_in_generated_content"):
        _generate(engine=FakeEngine(content=leaky))


def test_safety_check_rejects_unsafe():
    unsafe = GOOD_CONTENT.replace(
        "EXERCISE:", "EXERCISE:\nThis worksheet was generated by AI for RTI tier 3 students."
    )
    with pytest.raises(ValueError, match="unsafe_student_facing_copy"):
        _generate(engine=FakeEngine(content=unsafe))


def test_cefr_tier_mapping():
    engine = FakeEngine()
    _generate(engine=engine)
    prompts = {call["query"].split("-tier worksheet")[0].strip().split()[-1]: call["query"] for call in engine.calls}
    # A2 lesson target: foundational one step down, extended one step up
    assert "CEFR target for this tier: A1+" in prompts["foundational"]
    assert "CEFR target for this tier: A2" in prompts["on_track"]
    assert "CEFR target for this tier: A2+" in prompts["extended"]


def test_empty_roster_still_returns_materials():
    result = _generate(roster=[])
    assert len(result.materials) == 3
    for material in result.materials:
        assert material.student_ids == []
        assert material.teacher_note.startswith("No students currently at this tier.")
        assert material.exercise_body


def test_no_model_available_raises_generation_failed():
    engine = FakeEngine(content="[Local reasoning for lingua-viva - no model available]", model_used="none")
    with pytest.raises(ValueError, match="generation_failed"):
        _generate(engine=engine)


def test_unknown_student_id_raises_permission_error():
    store = FakeStore(_roster())
    with pytest.raises(PermissionError, match="unauthorized_student_ids:student-zed"):
        assign_tier_groups(store, "teacher-a", ["student-zed"])


def test_drive_not_configured_sync_status(monkeypatch):
    import src.lingua_viva.drive_sync as drive_sync

    monkeypatch.setattr(drive_sync, "get_sync_folder_id", lambda: None)
    result = _generate(push_to_drive=True)
    assert result.sync_status == "drive_not_configured"


def test_printable_packet_renders_three_clean_handouts():
    materials = [
        TierMaterial(
            tier="foundational",
            student_ids=["student-nora"],
            title="Routine Match",
            instructions_for_student="Match each routine word to a picture.",
            exercise_body="1. wake up\n2. eat breakfast\n3. go to school",
            scaffolding=["word bank", "sentence starters"],
            teacher_note="Use the model first.",
        ),
        TierMaterial(
            tier="on_track",
            student_ids=["student-marco"],
            title="Routine Sentences",
            instructions_for_student="Write three sentences about a morning routine.",
            exercise_body="Use prima, poi, and dopo in your answers.",
            scaffolding=["model example"],
            teacher_note="Independent practice after one example.",
        ),
        TierMaterial(
            tier="extended",
            student_ids=["student-luca"],
            title="Routine Interview",
            instructions_for_student="Interview a partner and report the routine.",
            exercise_body="Ask two follow-up questions and write a short report.",
            scaffolding=[],
            teacher_note="Invite transfer to a new context.",
        ),
    ]

    markdown = render_printable_packet_markdown(_lesson(), materials)

    assert markdown.count("# Student Handout -") == 3
    assert "## Teacher Cover Page" in markdown
    assert "### Activity" in markdown
    assert "### Exit Ticket" in markdown
    assert "RTI" not in markdown
    assert "student-nora" not in markdown
    assert "generated by AI" not in markdown


def test_printable_packet_rendered_html_hides_markdown_syntax():
    result = _generate()
    markdown = render_printable_packet_markdown(_lesson(), result.materials)
    rendered = render_printable_packet_html(markdown)

    assert "<h1>Printable Lesson Packet" in rendered
    assert "# Student Handout" not in rendered
    assert "**" not in rendered
    assert "<ul>" in rendered


def test_write_printable_packet_creates_private_markdown(tmp_path):
    result = _generate()
    path = write_printable_packet(
        _lesson(),
        result.materials,
        directory=tmp_path,
        individual_support=result.individual_support,
    )

    assert path.suffix == ".md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Printable Lesson Packet -")
    assert "Status: APPROVED" in text
    assert "Teacher-Only Individual Support" in text


def test_course_library_pull_and_today_selection(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    files = [{"id": "drive-1", "name": "Routine Lesson.txt"}]

    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.list_folder_files",
        lambda folder_id: files,
    )
    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.download_file_text",
        lambda file_id: "Lesson plan text for today.",
    )

    pulled = pull_course_library("folder-123", "G3", "language")
    assert len(pulled["pulled"]) == 1
    listed = list_course_library("G3", "language")
    local_path = listed["files"][0]["local_path"]
    assert Path(local_path).read_text(encoding="utf-8") == "Lesson plan text for today."

    second = pull_course_library("folder-123", "G3", "language")
    assert len(second["skipped"]) == 1

    selection = select_todays_lesson(
        teacher_id="teacher-a",
        class_id="g3-a",
        grade="G3",
        subject="language",
        local_path=local_path,
    )
    assert selection.class_id == "g3-a"
    assert selection.local_path == local_path


def test_share_packet_upload_strips_individual_support(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_LESSON_UPLOAD_QUEUE_PATH", str(tmp_path / "queue.json"))
    result = _generate()
    uploads = []

    def fake_upload_text_to_folder(folder_id, filename, content, mime_type="text/markdown"):
        uploads.append({
            "folder_id": folder_id,
            "filename": filename,
            "content": content,
            "mime_type": mime_type,
        })
        return {"id": filename}

    monkeypatch.setattr(
        "src.lingua_viva.google_drive_integration.upload_text_to_folder",
        fake_upload_text_to_folder,
    )

    share = share_packet_to_drive(
        _lesson(),
        result.materials,
        folder_map={
            "lesson_materials": {
                "g3-a": {"G3": {"language": {"folder_id": "folder-output"}}}
            }
        },
        class_id="g3-a",
        grade="G3",
        subject="language",
    )
    assert share["status"] == "pushed_to_drive"
    assert {item["mime_type"] for item in uploads} == {"text/markdown", "text/html"}
    for item in uploads:
        assert "Teacher-Only Individual Support" not in item["content"]
        assert "Nora" not in item["content"]
