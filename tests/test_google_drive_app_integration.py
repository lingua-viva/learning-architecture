import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.lingua_viva import google_drive_integration as drive
from src.web import app


client = TestClient(app)


class FakeDriveTransport:
    def post_form(self, url, data):
        return {"access_token": "access-token-secret"}

    def get_json(self, url, token):
        if "/files?" in url:
            return {
                "files": [{
                    "id": "pdf-1",
                    "name": "lesson.pdf",
                    "mimeType": "application/pdf",
                    "modifiedTime": "2026-07-23T12:00:00Z",
                    "size": "10",
                }]
            }
        return {"id": "pdf-1", "name": "lesson.pdf", "mimeType": "application/pdf"}

    def get_bytes(self, url, token):
        return b"%PDF mocked"


def _configure(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_ENABLED", "1")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("LV_GOOGLE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("LV_GOOGLE_DRIVE_ROOT_ID", "root-folder")
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))
    monkeypatch.setattr(drive, "UrlLibDriveTransport", FakeDriveTransport)


def test_status_route_is_secret_free(monkeypatch):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_ENABLED", "1")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("LV_GOOGLE_REFRESH_TOKEN", "refresh-token")

    response = client.get("/api/google-drive/status")
    assert response.status_code == 200
    body = response.text
    assert response.json()["configured"] is True
    assert "client-secret" not in body
    assert "refresh-token" not in body


def test_list_route_requires_configuration():
    response = client.post("/api/google-drive/list", json={"query": "lesson"})
    assert response.status_code == 503


def test_list_route_returns_mocked_drive_metadata(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    response = client.post("/api/google-drive/list", json={"query": "lesson"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["files"][0]["id"] == "pdf-1"
    assert payload["files"][0]["supported_for_extraction"] is True
    assert "access-token-secret" not in response.text


def test_import_route_writes_local_file_and_assignment(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    created = client.post("/api/students", json={"display_name": "Marco", "grade_level": "G3"})
    assert created.status_code == 200
    student_id = created.json()["student_id"]

    response = client.post(
        "/api/google-drive/import",
        json={
            "file_ids": ["pdf-1"],
            "purpose": "student_lens_source",
            "assigned_student_id": student_id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    local_path = Path(payload["imported"][0]["local_path"])
    assert local_path.exists()
    assert str(local_path).startswith(str(tmp_path / "drive_imports"))
    mapped = client.get("/api/filemap").json()
    assert mapped["student_assignments"][0]["assigned_student_id"] == student_id
    assert mapped["student_assignments"][0]["assigned_purpose"] == "student_lens_source"


def test_import_rejects_unknown_student_before_download(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    response = client.post(
        "/api/google-drive/import",
        json={
            "file_ids": ["pdf-1"],
            "purpose": "student_lens_source",
            "assigned_student_id": "missing",
        },
    )
    assert response.status_code == 400


def test_import_payload_errors_return_400_even_when_unconfigured():
    empty = client.post("/api/google-drive/import", json={"file_ids": []})
    invalid_purpose = client.post(
        "/api/google-drive/import",
        json={"file_ids": ["pdf-1"], "purpose": "bad-purpose"},
    )

    assert empty.status_code == 400
    assert invalid_purpose.status_code == 400


def test_no_google_drive_upload_route_exists():
    response = client.post("/api/google-drive/upload", json={})
    assert response.status_code == 404


def test_settings_ui_mounts_google_drive_controls():
    html = Path("static/index.html").read_text(encoding="utf-8")
    for text in (
        "Google Drive",
        "/api/google-drive/status",
        "/api/google-drive/list",
        "/api/google-drive/import",
        "List Drive Files",
        "Import Selected",
        "student_lens_source",
        "curriculum_unit_source",
    ):
        assert text in html

    served = client.get("/")
    assert served.status_code == 200
    assert "Google Drive" in served.text
    assert "/api/google-drive/import" in served.text
