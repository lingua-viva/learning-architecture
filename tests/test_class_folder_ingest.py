from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import StudentLensStore
from src.lingua_viva import google_drive_integration as drive
from src.lingua_viva.class_folder_ingest import FOLDER_MIME, ingest_class_folder
from src.web import app


def _patch_drive(monkeypatch, tmp_path, folder_map, contents):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_ENABLED", "1")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("LV_GOOGLE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))

    def list_folder_files(folder_id):
        return folder_map.get(folder_id, [])

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


def test_class_folder_ingest_recurses_and_records_attribution(monkeypatch, tmp_path):
    folder_map = {
        "root-folder": [
            {"id": "sub-folder", "name": "Student work", "mime_type": FOLDER_MIME},
            {"id": "marco-file", "name": "Marco Bianchi reading note.txt", "mime_type": "text/plain"},
        ],
        "sub-folder": [
            {"id": "nora-file", "name": "reflection.txt", "mime_type": "text/plain"},
        ],
    }
    contents = {
        "marco-file": "Marco Bianchi explains vocabulary with a relevant quotation.",
        "nora-file": "Nora Rossi explains the quotation clearly and uses a checklist.",
    }
    _patch_drive(monkeypatch, tmp_path, folder_map, contents)

    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        nora = store.create_lens(display_name="Nora Rossi")
        marco = store.create_lens(display_name="Marco Bianchi")

        result = ingest_class_folder("root-folder", "teacher:olga", store=store)

        assert result["failed"] == []
        assert result["unattributed"] == []
        assert {item["student_id"] for item in result["students_created_or_updated"]} == {
            nora,
            marco,
        }
        methods = {
            item["student_id"]: item["attribution_method"]
            for item in result["students_created_or_updated"]
        }
        assert methods[marco] == "filename_roster_exact"
        assert methods[nora] == "document_header_roster_exact"

        evidence = store.list_evidence(marco, target_type="background")
        assert evidence[0]["kind"] == "document"
        assert evidence[0]["source_ref"]["attribution_method"] == "filename_roster_exact"
        lens = store.get_lens(nora)
        assert lens["support_profile"]["categories"]["communication_and_language"]["evidence"]


def test_class_folder_ingest_surfaces_unattributed_documents(monkeypatch, tmp_path):
    folder_map = {
        "root-folder": [
            {"id": "unknown-file", "name": "exit-ticket.txt", "mime_type": "text/plain"},
        ],
    }
    contents = {"unknown-file": "Anonymous exit ticket with no student name."}
    _patch_drive(monkeypatch, tmp_path, folder_map, contents)

    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        store.create_lens(display_name="Nora Rossi")
        result = ingest_class_folder("root-folder", "teacher:olga", store=store)

        assert result["students_created_or_updated"] == []
        assert result["unattributed"][0]["drive_id"] == "unknown-file"
        assert result["unattributed"][0]["reason"].startswith("No exact")


def test_class_folder_ingest_route_uses_student_store(monkeypatch, tmp_path):
    _patch_drive(
        monkeypatch,
        tmp_path,
        {
            "root-folder": [
                {"id": "nora-file", "name": "Nora Rossi plan.txt", "mime_type": "text/plain"},
            ],
        },
        {"nora-file": "Nora Rossi explains the quotation clearly."},
    )
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "route_students.db"))
    with StudentLensStore(db_path=tmp_path / "route_students.db") as store:
        store.create_lens(display_name="Nora Rossi")

    client = TestClient(app)
    response = client.post(
        "/api/students/ingest/class-folder",
        json={"folder_id": "root-folder", "teacher_id": "teacher:olga"},
    )

    assert response.status_code == 200
    assert response.json()["students_created_or_updated"][0]["display_name"] == "Nora Rossi"
