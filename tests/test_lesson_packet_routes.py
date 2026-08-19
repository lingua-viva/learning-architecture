from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import Observation, StudentLensStore
from src.web import app


def _payload() -> dict:
    return {
        "teacher_id": "teacher-a",
        "lesson": {
            "ib_programme": "PYP",
            "subject": "language",
            "unit_title": "How we express ourselves",
            "topic": "Describing daily routines in Italian",
            "atl_skills": ["communication"],
            "cefr_target": "A2",
            "duration_minutes": 45,
        },
        "materials": [
            {
                "tier": "foundational",
                "student_ids": ["student-nora"],
                "title": "Routine Match",
                "instructions_for_student": "Match each routine word to a picture.",
                "exercise_body": "1. wake up\n2. eat breakfast\n3. go to school",
                "scaffolding": ["word bank", "sentence starters"],
                "teacher_note": "Use the model first.",
            },
            {
                "tier": "on_track",
                "student_ids": ["student-marco"],
                "title": "Routine Sentences",
                "instructions_for_student": "Write three sentences about a morning routine.",
                "exercise_body": "Use prima, poi, and dopo in your answers.",
                "scaffolding": ["model example"],
                "teacher_note": "Independent practice after one example.",
            },
            {
                "tier": "extended",
                "student_ids": ["student-luca"],
                "title": "Routine Interview",
                "instructions_for_student": "Interview a partner and report the routine.",
                "exercise_body": "Ask two follow-up questions and write a short report.",
                "scaffolding": [],
                "teacher_note": "Invite transfer to a new context.",
            },
        ],
        "individual_support": [
            {
                "student_id": "student-zoe",
                "display_name": "Zoe",
                "reason": "rti_current_tier_3",
            }
        ],
    }


def test_lesson_packet_approval_writes_deliverable_and_receipt(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv_home"))
    monkeypatch.setenv("LV_LESSON_PACKET_DIR", str(tmp_path / "packets"))

    with TestClient(app) as client:
        response = client.post("/api/lesson-materials/packet/approve", json=_payload())

    assert response.status_code == 200
    body = response.json()
    packet_path = Path(body["packet"]["file_path"])
    assert packet_path.exists()
    assert packet_path.suffix == ".pdf"
    assert packet_path.read_bytes().startswith(b"%PDF")
    assert Path(body["packet"]["markdown_path"]).suffix == ".md"
    assert Path(body["packet"]["markdown_path"]).exists()
    tier_paths = body["packet"]["pdf_paths"]["student_tiers"]
    assert set(tier_paths) == {"foundational", "on_track", "extended"}
    for tier_path in tier_paths.values():
        assert Path(tier_path).read_bytes().startswith(b"%PDF")
    assert body["deliverable"]["type"] == "lesson_material_packet"
    assert body["deliverable"]["deliverable_id"] in body["audit_receipt"]["deliverable_ids"]
    assert body["audit_receipt"]["is_complete"] is True
    assert body["sync_status"] == "not_requested"
    assert body["packet"]["format"] == "html+markdown"
    assert "<h1>Printable Lesson Packet" in body["packet"]["html"]
    assert "# Student Handout -" in body["packet"]["markdown"]
    assert "Teacher-Only Individual Support" in body["packet"]["markdown"]
    assert "student-nora" not in body["packet"]["markdown"]

    with TestClient(app) as client:
        repeated = client.post("/api/lesson-materials/packet/approve", json=_payload())
    assert repeated.status_code == 200
    assert repeated.json()["packet"]["file_path"] == body["packet"]["file_path"]
    assert repeated.json()["packet"]["pdf_paths"] == body["packet"]["pdf_paths"]


def test_lesson_packet_shareback_uploads_stripped_markdown_and_html(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv_home"))
    monkeypatch.setenv("LV_LESSON_PACKET_DIR", str(tmp_path / "packets"))
    monkeypatch.setenv("LV_LESSON_UPLOAD_QUEUE_PATH", str(tmp_path / "queue.json"))
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

    payload = {
        **_payload(),
        "push_to_drive": True,
        "folder_map": {
            "lesson_materials": {
                "g3-a": {"G3": {"language": {"folder_id": "folder-output"}}}
            }
        },
        "class_id": "g3-a",
        "grade": "G3",
        "subject": "language",
    }

    with TestClient(app) as client:
        response = client.post("/api/lesson-materials/packet/approve", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["sync_status"] == "pushed_to_drive"
    assert len(uploads) == 2
    assert {item["mime_type"] for item in uploads} == {"text/markdown", "text/html"}
    for item in uploads:
        assert item["folder_id"] == "folder-output"
        assert "Teacher-Only Individual Support" not in item["content"]
        assert "Zoe" not in item["content"]


def test_roster_split_preview_returns_reasons_without_recording_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_ROSTER_OVERRIDES_PATH", str(tmp_path / "roster_overrides.ndjson"))
    teacher_id = "teacher-a"
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        student_a = store.create_lens(display_name="Student A", rti_current_tier=1)
        student_b = store.create_lens(display_name="Student B", rti_current_tier=2)
        student_c = store.create_lens(display_name="Student C", rti_current_tier=3)
        store.append_observation(
            Observation(
                student_id=student_a,
                teacher_id=teacher_id,
                template_type="cefr",
                raw_transcript="Student A read the sentence.",
                cefr_dimension="reading",
                cefr_level_observed="A2",
            )
        )
        for sid in (student_b, student_c):
            store.append_observation(
                Observation(
                    student_id=sid,
                    teacher_id=teacher_id,
                    template_type="general",
                    raw_transcript="Roster membership note.",
                )
            )

    with TestClient(app) as client:
        response = client.post(
            "/api/lesson-materials/roster-split",
            json={
                "teacher_id": teacher_id,
                "tier_overrides": {student_b: "extended"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["groups"]["on_track"][0]["student_id"] == student_a
    assert body["groups"]["on_track"][0]["source"] == "cefr"
    assert body["groups"]["extended"][0]["student_id"] == student_b
    assert body["groups"]["extended"][0]["source"] == "teacher_override"
    assert body["individual_support"][0]["student_id"] == student_c
    assert body["individual_support"][0]["reason"] == "rti_current_tier_3"
    assert body["overrides"] == {student_b: "extended"}
    assert body["roster_names"][student_a] == "Student A"
    assert not (tmp_path / "roster_overrides.ndjson").exists()


def test_library_import_file_uploads_selects_and_detects_metadata(monkeypatch, tmp_path):
    import base64

    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv_home"))
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    content = (
        "Class: MYP2 English\nUnit: Migration stories\nTask: Poetry analysis\n\n"
        "Learning goal: analyse imagery.\n\nWarm-up: read the poem aloud."
    ).encode("utf-8")

    with TestClient(app) as client:
        response = client.post(
            "/api/lesson-materials/library/import-file",
            json={
                "name": "Poetry Lesson.md",
                "content_base64": base64.b64encode(content).decode("ascii"),
                "grade": "MYP2",
                "subject": "english",
            },
        )

    assert response.status_code == 200
    body = response.json()
    entry = body["imported"]["entry"]
    assert entry["status"] == "pulled"
    assert body["selection"]["local_path"] == entry["local_path"]
    assert body["metadata"]["grade"] == "MYP2"
    assert body["metadata"]["unit"] == "Migration stories"
    assert body["metadata"]["topic"] == "Poetry analysis"
    assert "read the poem aloud" in body["metadata"]["excerpt"].lower()


def test_library_import_file_accepts_local_path(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv_home"))
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    source = tmp_path / "Routine Lesson.txt"
    source.write_text("Warm-up: describe your morning routine.", encoding="utf-8")

    with TestClient(app) as client:
        response = client.post(
            "/api/lesson-materials/library/import-file",
            json={"file_path": str(source), "grade": "G3", "subject": "language"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["imported"]["entry"]["name"] == "Routine Lesson.txt"
    assert body["selection"]["grade"] == "G3"


def test_library_import_file_requires_grade_and_file(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    with TestClient(app) as client:
        no_grade = client.post(
            "/api/lesson-materials/library/import-file",
            json={"name": "a.md", "content_base64": "YQ=="},
        )
        no_file = client.post(
            "/api/lesson-materials/library/import-file",
            json={"grade": "G3"},
        )
    assert no_grade.status_code == 400
    assert no_grade.json()["error"] == "grade_required"
    assert no_file.status_code == 400
    assert no_file.json()["error"] == "file_required"


def test_generate_rejects_lesson_file_outside_course_library(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    outside = tmp_path / "outside.md"
    outside.write_text("not in the library", encoding="utf-8")

    payload = {"lesson": _payload()["lesson"], "lesson_file_path": str(outside)}
    with TestClient(app) as client:
        response = client.post("/api/lesson-materials/generate", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_lesson_file"
    assert "outside_course_library" in body["detail"]


def test_generate_threads_selected_lesson_file_content(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv_home"))
    monkeypatch.setenv("LV_COURSE_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))

    from src.lingua_viva.reasoning import ReasonResult

    prompts = []

    class FakeEngine:
        async def reason(self, query, context=None, model=None, default_model=None,
                         system_prompt=None, local_only=False, max_tokens=2000):
            prompts.append(query)
            return ReasonResult(
                content=(
                    "TITLE: Routine Practice\n"
                    "INSTRUCTIONS: Read then answer.\n"
                    "EXERCISE:\n1. Read the model.\n2. Write two sentences.\n"
                    "SCAFFOLDING NOTES: word bank"
                ),
                confidence=0.8,
                model_used="mock",
            )

    monkeypatch.setattr("src.lingua_viva.reasoning.ReasoningEngine", FakeEngine)

    source = tmp_path / "Routine Lesson.txt"
    source.write_text("Il mio quartiere: describe your neighbourhood.", encoding="utf-8")

    with TestClient(app) as client:
        imported = client.post(
            "/api/lesson-materials/library/import-file",
            json={"file_path": str(source), "grade": "G3", "subject": "language"},
        )
        assert imported.status_code == 200
        local_path = imported.json()["imported"]["entry"]["local_path"]

        response = client.post(
            "/api/lesson-materials/generate",
            json={
                "lesson": _payload()["lesson"],
                "lesson_file_path": local_path,
                "push_to_drive": False,
            },
        )

    assert response.status_code == 200
    assert len(prompts) == 3
    for prompt in prompts:
        assert "Il mio quartiere" in prompt
