from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.education.content_differentiator import LessonInput
from src.lingua_viva.lesson_materials import (
    SYSTEM_PROMPT,
    _SOURCE_EXCERPT_CHARS,
    _source_excerpt,
    TierMaterial,
    assign_roster_split,
    assign_tier_groups,
    import_lesson_file_bytes,
    list_course_library,
    parse_lesson_file_metadata,
    pull_course_library,
    pull_local_file,
    generate_lesson_materials,
    read_todays_lesson_text,
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
        _lens("student-c", "Student C", rti=2, cefr="B1+"),
        _lens("student-d", "Student D", rti=1, cefr=None),
        {
            **_lens("student-b", "Student B", rti=1, cefr="A2"),
            "support_profile": {"needs_individual_support": True},
        },
    ]
    split = assign_roster_split(FakeStore(roster), "teacher-a")
    assert split.tier_groups["on_track"] == ["student-a", "student-c"]
    assert split.tier_groups["foundational"] == ["student-d"]
    assert split.group_members["on_track"][0].__dict__ == {
        "student_id": "student-a",
        "display_name": "Student A",
        "source": "cefr",
    }
    assert split.group_members["on_track"][1].source == "rti"
    assert split.group_members["foundational"][0].source == "default"
    assert split.individual_support[0].student_id == "student-b"
    assert split.individual_support[0].reason == "support_profile_flag"


def test_tier_overrides_applied_and_recorded(tmp_path, monkeypatch):
    """Spec G2: assignments are teacher-overridable per student per day,
    and overrides are recorded (append-only, dated, teacher-attributed)."""
    import json

    from src.lingua_viva.lesson_materials import roster_overrides_path

    monkeypatch.setenv("LV_ROSTER_OVERRIDES_PATH", str(tmp_path / "roster_overrides.ndjson"))
    roster = [
        _lens("student-a", "Student A", rti=1, cefr="A2"),   # would be on_track
        _lens("student-b", "Student B", rti=3, cefr="A1"),   # would be support (RTI 3)
        _lens("student-c", "Student C", rti=1, cefr="B2"),   # would be extended
    ]
    split = assign_roster_split(
        FakeStore(roster),
        "teacher-a",
        overrides={
            "student-a": "extended",            # tier -> tier
            "student-b": "on_track",            # support -> tier (teacher wins)
            "student-c": "individual_support",  # tier -> kept-apart group
            "student-x": "on_track",            # not on roster: ignored, not applied
            "student-a2": "bogus_tier",         # invalid value: dropped
        },
    )
    assert split.tier_groups["extended"] == ["student-a"]
    assert split.tier_groups["on_track"] == ["student-b"]
    assert split.group_members["extended"][0].source == "teacher_override"
    assert split.group_members["on_track"][0].source == "teacher_override"
    assert [s.student_id for s in split.individual_support] == ["student-c"]
    assert split.individual_support[0].reason == "teacher_override"
    assert split.overrides == {
        "student-a": "extended",
        "student-b": "on_track",
        "student-c": "individual_support",
    }
    # Recorded: one dated, teacher-attributed line with exactly the applied set.
    lines = roster_overrides_path().read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["teacher_id"] == "teacher-a"
    assert record["overrides"] == split.overrides
    assert record["recorded_at"].endswith("Z")

    # No overrides -> nothing applied, nothing appended (record stays 1 line).
    clean = assign_roster_split(FakeStore(roster), "teacher-a")
    assert clean.overrides == {}
    assert len(roster_overrides_path().read_text(encoding="utf-8").strip().splitlines()) == 1


def test_roster_split_preview_overrides_do_not_record(tmp_path, monkeypatch):
    from src.lingua_viva.lesson_materials import roster_overrides_path

    monkeypatch.setenv("LV_ROSTER_OVERRIDES_PATH", str(tmp_path / "roster_overrides.ndjson"))
    roster = [_lens("student-a", "Student A", rti=1, cefr="A2")]
    split = assign_roster_split(
        FakeStore(roster),
        "teacher-a",
        overrides={"student-a": "extended"},
        record_overrides=False,
    )

    assert split.overrides == {"student-a": "extended"}
    assert split.group_members["extended"][0].source == "teacher_override"
    assert not roster_overrides_path().exists()


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


def test_placeholder_shaped_model_copy_falls_back_to_deterministic_material():
    placeholder = (
        "TITLE: [Placeholder title]\n"
        "INSTRUCTIONS: Complete [placeholder instruction].\n"
        "EXERCISE:\n"
        "[Local reasoning placeholder - replace this later]\n"
        "SCAFFOLDING NOTES: [placeholder support]"
    )
    result = _generate(engine=FakeEngine(content=placeholder))
    serialized = json.dumps([material.__dict__ for material in result.materials])
    assert "[Placeholder" not in serialized
    assert "[Local reasoning" not in serialized
    assert "Describing daily routines in Italian" in result.materials[0].title


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


def test_no_model_available_uses_deterministic_materials():
    engine = FakeEngine(content="[Local reasoning for lingua-viva - no model available]", model_used="none")
    result = _generate(engine=engine)
    assert len(result.materials) == 3
    assert result.materials[0].title.endswith("Foundational Practice")
    assert "Local reasoning" not in result.materials[0].exercise_body


# --- STEP 10 (SPEC_LV_UNIFIED_REAL_DATA_FIX 2026-08-19, C2/C3): generation honesty


class FailingEngine:
    def __init__(self, content: str = "", model_used: str = "ollama/qwen3:8b", error: str = ""):
        self.content = content
        self.model_used = model_used
        self.error = error

    async def reason(self, query, context=None, model=None, default_model=None, system_prompt=None, local_only=False, max_tokens=2000):
        return ReasonResult(
            content=self.content,
            confidence=0.0 if self.error else 0.8,
            model_used=self.model_used,
            error=self.error,
        )


@pytest.mark.parametrize(
    "engine",
    [
        FailingEngine(error="empty_model_response"),                      # STEP 8 failure signal
        FailingEngine(error="timeout"),
        FailingEngine(model_used="none:local_only", error="local_only_no_model"),
        FailingEngine(model_used="none"),                                 # no model, error=""
        FailingEngine(content="", model_used="mock"),                     # THE C3 shape: empty content, no error
        FakeEngine(content="EXERCISE:\n1. Read the text.\n2. Answer."),   # drifted format: no INSTRUCTIONS section
    ],
    ids=["empty_response", "timeout", "privacy_refusal", "none_model", "empty_no_error", "blank_instructions"],
)
def test_template_fallback_is_loud_and_never_blank(engine):
    """Class lock (spec §4 STEP 10): no template-fallback output without its
    status signal, and no tier — least of all foundational — ever renders
    blank instructions / blank exercise / empty scaffolding. The C3 audit
    finding was the foundational tier degrading to NOTHING, silently."""
    result = _generate(engine=engine)
    assert len(result.materials) == 3
    for material in result.materials:
        assert material.generation_status == "template_fallback"
        assert material.instructions_for_student.strip()
        assert material.exercise_body.strip()
        assert material.scaffolding
    # The signal must survive serialization to the API response.
    from src.lingua_viva.lesson_materials import materials_as_dicts

    for item in materials_as_dicts(result):
        assert item["generation_status"] == "template_fallback"


def test_genuinely_generated_materials_report_generated_status():
    result = _generate()  # FakeEngine returns GOOD_CONTENT
    for material in result.materials:
        assert material.generation_status == "generated"


def test_material_from_dict_round_trips_generation_status():
    from src.lingua_viva.lesson_materials import material_from_dict

    material = material_from_dict({"tier": "foundational", "generation_status": "template_fallback"})
    assert material.generation_status == "template_fallback"
    # Old dicts without the field default to "generated" (pre-v164 payloads).
    assert material_from_dict({"tier": "on_track"}).generation_status == "generated"


def test_every_fallback_path_sets_the_status_signal_class_lock():
    """Source-level lock: inside _generate_tier_material, every switch to
    _deterministic_material_fields must be paired with a template_fallback
    status assignment — a new silent fallback path fails this test."""
    import inspect

    from src.lingua_viva import lesson_materials

    source = inspect.getsource(lesson_materials._generate_tier_material)
    fallback_calls = source.count("_deterministic_material_fields(")
    status_marks = source.count('generation_status = "template_fallback"')
    assert fallback_calls >= 2
    assert fallback_calls == status_marks


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


def test_printable_packet_allows_ordinary_teaching_brackets():
    """Square brackets are normal in worksheets ("[word bank]", "[your
    answer]") and must NOT fail validation — the old blanket bracket ban
    rejected every real packet (FIX_PREPARE_CLASS_MATERIALS Issue 7)."""
    materials = [
        TierMaterial(
            tier=tier,
            student_ids=[f"student-{tier}"],
            title=f"Activity {tier}",
            instructions_for_student="Fill each gap using the [word bank] below.",
            exercise_body="1. I ___ [wake up] at seven.\n2. [your answer]",
            scaffolding=["word bank"],
            teacher_note="Brackets are fine.",
        )
        for tier in ("foundational", "on_track", "extended")
    ]
    markdown = render_printable_packet_markdown(_lesson(), materials)
    assert "[word bank]" in markdown


def test_printable_packet_still_rejects_placeholder_output():
    """Placeholder-shaped model output must still be rejected — the
    targeted regex, not the bracket ban, carries this safety property."""
    materials = [
        TierMaterial(
            tier=tier,
            student_ids=[f"student-{tier}"],
            title=f"Activity {tier}",
            instructions_for_student="[no model available]",
            exercise_body="[Local reasoning stub]",
            scaffolding=[],
            teacher_note="",
        )
        for tier in ("foundational", "on_track", "extended")
    ]
    with pytest.raises(ValueError, match="unsafe_or_placeholder_printable_packet"):
        render_printable_packet_markdown(_lesson(), materials)


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


def test_pull_local_file_and_upload_bytes_share_the_library(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    source = tmp_path / "Poetry Lesson.md"
    source.write_text(
        "Class: MYP2 English\nUnit: Migration stories\nTask: Poetry analysis\n\n"
        "Learning goal: analyse imagery.\n\nWarm-up: read the poem aloud.",
        encoding="utf-8",
    )

    imported = pull_local_file(str(source), "MYP2", "english")
    entry = imported["entry"]
    assert entry["status"] == "pulled"
    assert Path(entry["local_path"]).read_text(encoding="utf-8").startswith("Class: MYP2")

    again = pull_local_file(str(source), "MYP2", "english")
    assert again["entry"]["status"] == "unchanged"
    assert again["entry"]["local_path"] == entry["local_path"]

    uploaded = import_lesson_file_bytes(
        "Uploaded Lesson.txt", b"Warm-up: greetings\nMain activity: dialogue", "MYP2", "english"
    )
    assert uploaded["entry"]["status"] == "pulled"
    duplicate = import_lesson_file_bytes(
        "Uploaded Lesson.txt", b"Warm-up: greetings\nMain activity: dialogue", "MYP2", "english"
    )
    assert duplicate["entry"]["status"] == "unchanged"

    listed = list_course_library("MYP2", "english")
    assert {item["name"] for item in listed["files"]} == {"Poetry Lesson.md", "Uploaded Lesson.txt"}


def test_pull_local_file_rejects_unsupported_extension(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    source = tmp_path / "lesson.exe"
    source.write_bytes(b"nope")
    with pytest.raises(ValueError, match="unsupported lesson file type"):
        pull_local_file(str(source), "G3", "language")


def test_parse_lesson_file_metadata_detects_curriculum(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    source = tmp_path / "Poetry Lesson.md"
    source.write_text(
        "Class: MYP2 English\nUnit: Migration stories\nTask: Poetry analysis\n\n"
        "Learning goal: analyse imagery.\n\nWarm-up: read the poem aloud.",
        encoding="utf-8",
    )
    imported = pull_local_file(str(source), "MYP2", "english")
    meta = parse_lesson_file_metadata(imported["entry"]["local_path"])
    assert meta["grade"] == "MYP2"
    assert meta["subject"] == "English"
    assert meta["unit"] == "Migration stories"
    assert meta["topic"] == "Poetry analysis"
    assert meta["document_type"] == "lesson_plan"
    assert "read the poem aloud" in meta["excerpt"].lower()


def test_read_todays_lesson_text_handles_xlsx(monkeypatch, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Vocabulary", "Meaning"])
    sheet.append(["andare", "to go"])
    source = tmp_path / "vocab.xlsx"
    workbook.save(source)

    imported = pull_local_file(str(source), "G3", "language")
    text = read_todays_lesson_text(imported["entry"]["local_path"])
    assert "andare" in text


def test_generate_threads_source_text_into_every_tier_prompt():
    engine = FakeEngine()
    _generate(
        engine=engine,
        source_text="Il mio quartiere: describe your neighbourhood using c'è / ci sono.",
    )
    assert len(engine.calls) == 3
    for call in engine.calls:
        assert "LESSON CONTENT START" in call["query"]
        assert "c'è / ci sono" in call["query"]


def test_generate_without_source_text_omits_content_block():
    engine = FakeEngine()
    _generate(engine=engine)
    assert len(engine.calls) == 3
    for call in engine.calls:
        assert "LESSON CONTENT" not in call["query"]


def test_source_excerpt_bounds_long_content():
    excerpt = _source_excerpt("word " * 1000)
    assert len(excerpt) <= _SOURCE_EXCERPT_CHARS + 2
    assert excerpt.endswith("…")
    assert _source_excerpt("  short text  ") == "short text"
    assert _source_excerpt("   ") is None
    assert _source_excerpt(None) is None
