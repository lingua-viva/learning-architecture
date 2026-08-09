from __future__ import annotations

from fastapi.testclient import TestClient

from src.education.student_lens import StudentLensStore
from src.lingua_viva import google_drive_integration as drive
from src.lingua_viva.class_folder_ingest import ingest_class_folder
from src.lingua_viva.ingest_review import list_open_items, review_queue_path
from src.web import app


def _patch_drive(monkeypatch, tmp_path, contents):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_ENABLED", "1")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("LV_GOOGLE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))

    def list_folder_files(folder_id):
        return [
            {"id": file_id, "name": f"{file_id}.txt", "mime_type": "text/plain"}
            for file_id in contents
        ]

    def import_files(file_ids, purpose, **_kwargs):
        imported = []
        for file_id in file_ids:
            local = tmp_path / "drive_imports" / f"{file_id}.txt"
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(contents[file_id], encoding="utf-8")
            imported.append({
                "drive_id": file_id,
                "name": f"{file_id}.txt",
                "local_path": str(local),
                "purpose": purpose,
                "assigned_student_id": None,
                "supported_for_extraction": True,
                "status": "imported",
            })
        return {"imported": imported, "failed": []}

    monkeypatch.setattr(drive, "list_folder_files", list_folder_files)
    monkeypatch.setattr(drive, "import_files", import_files)


def test_unattributed_ingest_persists_source_id_and_get_route(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    _patch_drive(monkeypatch, tmp_path, {"unknown-file": "Anonymous exit ticket."})
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        store.create_lens(display_name="Nora Rossi")
        result = ingest_class_folder("root-folder", "teacher:olga", store=store)

    assert result["unattributed"][0]["source_id"].startswith("SRC-")
    assert review_queue_path().is_file()
    assert review_queue_path().stat().st_mode & 0o077 == 0
    assert list_open_items()[0]["source_id"] == result["unattributed"][0]["source_id"]

    client = TestClient(app)
    response = client.get("/api/students/ingest/unattributed")
    assert response.status_code == 200
    assert response.json()["items"][0]["drive_id"] == "unknown-file"


def test_manual_attribution_uses_shared_shape_and_teacher_confirmed(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    _patch_drive(monkeypatch, tmp_path, {"unknown-file": "Anonymous exit ticket with quotation evidence."})
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        student_id = store.create_lens(display_name="Nora Rossi")
        result = ingest_class_folder("root-folder", "teacher:olga", store=store)
    item = result["unattributed"][0]

    client = TestClient(app)
    response = client.post(
        "/api/students/ingest/attribute",
        json={
            "source_id": item["source_id"],
            "drive_id": item["drive_id"],
            "student_id": student_id,
            "teacher_id": "teacher:olga",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assignment"]["attribution_method"] == "manual_teacher"
    assert body["assignment"]["confidence_level"] == "teacher_confirmed"
    assert client.get("/api/students/ingest/unattributed").json()["items"] == []

    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        evidence = store.list_evidence(student_id, target_type="background")
    assert evidence[0]["confidence_level"] == "teacher_confirmed"
    assert evidence[0]["source_ref"]["attribution_method"] == "manual_teacher"
    assert evidence[0]["source_ref"]["attribution_confidence"] == 1.0


def test_off_roster_assignment_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    _patch_drive(monkeypatch, tmp_path, {"unknown-file": "Anonymous exit ticket."})
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        store.create_lens(display_name="Nora Rossi")
        result = ingest_class_folder("root-folder", "teacher:olga", store=store)
    item = result["unattributed"][0]
    before = review_queue_path().read_text(encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/students/ingest/attribute",
        json={
            "source_id": item["source_id"],
            "drive_id": item["drive_id"],
            "student_id": "student-not-roster",
            "teacher_id": "teacher:olga",
        },
    )

    assert response.status_code == 422
    assert review_queue_path().read_text(encoding="utf-8") == before
    assert client.get("/api/students/ingest/unattributed").json()["items"][0]["status"] == "open"


def test_reingest_does_not_duplicate_open_queue_item(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    _patch_drive(monkeypatch, tmp_path, {"unknown-file": "Anonymous exit ticket."})
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        store.create_lens(display_name="Nora Rossi")
        ingest_class_folder("root-folder", "teacher:olga", store=store)
        ingest_class_folder("root-folder", "teacher:olga", store=store)

    assert len(list_open_items()) == 1


def test_dismiss_removes_item_without_lens_write(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    _patch_drive(monkeypatch, tmp_path, {"unknown-file": "Anonymous exit ticket."})
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        student_id = store.create_lens(display_name="Nora Rossi")
        result = ingest_class_folder("root-folder", "teacher:olga", store=store)
    item = result["unattributed"][0]

    client = TestClient(app)
    response = client.post(
        "/api/students/ingest/attribute",
        json={
            "source_id": item["source_id"],
            "drive_id": item["drive_id"],
            "dismiss": True,
            "teacher_id": "teacher:olga",
        },
    )
    assert response.status_code == 200
    assert client.get("/api/students/ingest/unattributed").json()["items"] == []
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        assert store.list_evidence(student_id, target_type="background") == []
