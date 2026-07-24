import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from src.lingua_viva import google_drive_integration as drive
from src.lingua_viva.filemap import get_confirmed_extraction_inputs, load_map


class FakeDriveTransport:
    def __init__(self, *, fail_download_ids=None):
        self.fail_download_ids = set(fail_download_ids or [])
        self.posted = []
        self.json_urls = []
        self.byte_urls = []

    def post_form(self, url, data):
        self.posted.append((url, data))
        return {"access_token": "access-token-secret"}

    def get_json(self, url, token):
        assert token == "access-token-secret"
        self.json_urls.append(url)
        if "/files?" in url:
            return {
                "files": [
                    {
                        "id": "pdf-1",
                        "name": "lesson.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-07-23T12:00:00Z",
                        "size": "123",
                    },
                    {
                        "id": "img-1",
                        "name": "photo.png",
                        "mimeType": "image/png",
                    },
                ],
                "nextPageToken": None,
            }
        file_id = url.split("/files/", 1)[1].split("?", 1)[0].split("/export", 1)[0]
        file_id = file_id.replace("%2F", "/")
        if file_id == "bad-mime":
            return {"id": file_id, "name": "photo.png", "mimeType": "image/png"}
        if file_id == "gdoc-1":
            return {"id": file_id, "name": "Planning.gdoc", "mimeType": "application/vnd.google-apps.document"}
        return {"id": file_id, "name": "../Student Report.pdf", "mimeType": "application/pdf"}

    def get_bytes(self, url, token):
        self.byte_urls.append(url)
        if any(item in url for item in self.fail_download_ids):
            raise OSError("network down")
        return b"%PDF mocked content"


def _settings():
    return drive.DriveSettings(
        enabled=True,
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        root_id="root-folder",
    )


def test_status_is_secret_free():
    status = drive.status(_settings())
    text = json.dumps(status)
    assert status["configured"] is True
    assert status["can_upload"] is False
    assert "client-secret" not in text
    assert "refresh-token" not in text


def test_missing_config_returns_unconfigured(monkeypatch):
    monkeypatch.delenv("LV_GOOGLE_DRIVE_ENABLED", raising=False)
    status = drive.status()
    assert status["configured"] is False
    assert status["can_list"] is False


def test_whitespace_credentials_do_not_count_as_configured(monkeypatch):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_ENABLED", "1")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_ID", "   ")
    monkeypatch.setenv("LV_GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("LV_GOOGLE_REFRESH_TOKEN", "refresh")

    status = drive.status()
    assert status["configured"] is False
    assert status["client_id_set"] is False


def test_list_builds_query_and_returns_secret_free_metadata():
    transport = FakeDriveTransport()
    result = drive.list_files("lesson", "folder-1", settings=_settings(), transport=transport)

    assert result["files"][0]["supported_for_import"] is True
    assert result["files"][0]["supported_for_extraction"] is True
    assert result["files"][1]["supported_for_import"] is False
    serialized = json.dumps(result)
    assert "access-token-secret" not in serialized
    assert "refresh-token" not in serialized
    parsed = urlparse(transport.json_urls[0])
    query = parse_qs(parsed.query)["q"][0]
    assert "'folder-1' in parents" in query
    assert "name contains 'lesson'" in query


def test_import_writes_to_local_cache_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))
    result = drive.import_files(
        ["pdf-1"],
        "curriculum_unit_source",
        settings=_settings(),
        transport=FakeDriveTransport(),
    )

    imported = result["imported"][0]
    local_path = Path(imported["local_path"])
    assert local_path.exists()
    assert local_path.parent == tmp_path / "drive_imports"
    assert ".." not in local_path.name
    manifest = json.loads((tmp_path / "drive_imports" / "import_manifest.json").read_text())
    manifest_text = json.dumps(manifest)
    assert "%PDF mocked content" not in manifest_text
    assert "client-secret" not in manifest_text
    assert manifest["imports"][0]["purpose"] == "curriculum_unit_source"


def test_drive_ids_are_fully_url_encoded(monkeypatch, tmp_path):
    transport = FakeDriveTransport()
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))

    drive.import_files(["folder/file-1"], "unassigned", settings=_settings(), transport=transport)

    assert any("/files/folder%2Ffile-1?" in url for url in transport.json_urls)
    assert any("/files/folder%2Ffile-1?" in url for url in transport.byte_urls)


def test_google_docs_export_gets_txt_suffix(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))
    result = drive.import_files(
        ["gdoc-1"],
        "teacher_artifact_source",
        settings=_settings(),
        transport=FakeDriveTransport(),
    )

    assert result["imported"][0]["local_path"].endswith(".txt")
    assert result["imported"][0]["supported_for_extraction"] is True


def test_unsupported_mime_type_is_reported(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))
    result = drive.import_files(
        ["bad-mime"],
        "unassigned",
        settings=_settings(),
        transport=FakeDriveTransport(),
    )

    assert result["imported"] == []
    assert result["failed"][0]["status"] == "unsupported_for_import"


def test_partial_download_failure_does_not_crash_batch(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))
    result = drive.import_files(
        ["pdf-1", "fail-1"],
        "unassigned",
        settings=_settings(),
        transport=FakeDriveTransport(fail_download_ids={"fail-1"}),
    )

    assert len(result["imported"]) == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["status"] == "download_failed"


def test_student_assignment_must_exist_before_download(monkeypatch, tmp_path):
    transport = FakeDriveTransport()
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))

    with pytest.raises(ValueError):
        drive.import_files(
            ["pdf-1"],
            "student_lens_source",
            "missing-student",
            settings=_settings(),
            transport=transport,
            student_exists=lambda _student_id: False,
        )

    assert transport.byte_urls == []


def test_student_assignment_records_filemap_bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "drive_imports"))
    result = drive.import_files(
        ["pdf-1"],
        "student_lens_source",
        "student-123",
        settings=_settings(),
        transport=FakeDriveTransport(),
        student_exists=lambda _student_id: True,
    )

    mapped = load_map()
    assert mapped.student_assignments[0]["assigned_student_id"] == "student-123"
    assert mapped.student_assignments[0]["source"] == "google_drive_import"
    inputs = get_confirmed_extraction_inputs(mapped)
    assert inputs[0]["file_path"] == result["imported"][0]["local_path"]
    assert inputs[0]["target_schema_id"] == "student_lens"
