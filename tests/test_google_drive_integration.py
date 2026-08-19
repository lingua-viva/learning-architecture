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

    def post_multipart(self, url, token, metadata, content, content_type):
        assert token == "access-token-secret"
        if not hasattr(self, "uploads"):
            self.uploads = []
        record = {
            "name": metadata.get("name"),
            "parents": metadata.get("parents"),
            "mime_type": content_type,
            "size": len(content),
        }
        self.uploads.append(record)
        return {"id": f"uploaded-{len(self.uploads)}", "name": record["name"]}


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
    assert status["can_upload"] is True
    assert "client-secret" not in text
    assert "refresh-token" not in text


def test_upload_capability_requires_destination_folder():
    settings = drive.DriveSettings(
        enabled=True,
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        root_id=None,
    )
    assert drive.status(settings)["can_upload"] is False


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


def test_upload_paths_shares_export_dir_file_and_writes_manifest(monkeypatch, tmp_path):
    export = tmp_path / "drive_exports"
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(export))
    export.mkdir(parents=True)
    lens_file = export / "student-lens-abc.json"
    lens_file.write_text('{"student_id": "abc"}', encoding="utf-8")
    transport = FakeDriveTransport()

    result = drive.upload_paths([str(lens_file)], settings=_settings(), transport=transport)

    assert result["failed"] == []
    assert result["uploaded"][0]["drive_id"] == "uploaded-1"
    assert result["uploaded"][0]["folder_id"] == "root-folder"
    assert transport.uploads[0]["parents"] == ["root-folder"]
    assert transport.uploads[0]["mime_type"] == "application/json"
    manifest = json.loads((export / "export_manifest.json").read_text(encoding="utf-8"))
    assert manifest["exports"][0]["name"] == "student-lens-abc.json"
    assert "client-secret" not in json.dumps(manifest)


def test_upload_paths_explicit_folder_overrides_root(monkeypatch, tmp_path):
    export = tmp_path / "drive_exports"
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(export))
    export.mkdir(parents=True)
    deliverable = export / "unit-plan.md"
    deliverable.write_text("# Unit plan", encoding="utf-8")
    transport = FakeDriveTransport()

    result = drive.upload_paths([str(deliverable)], "deliverables-folder", settings=_settings(), transport=transport)

    assert result["uploaded"][0]["folder_id"] == "deliverables-folder"
    assert transport.uploads[0]["parents"] == ["deliverables-folder"]


def test_upload_paths_refuses_files_outside_allowed_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(tmp_path / "drive_exports"))
    outside = tmp_path / "secrets.json"
    outside.write_text("{}", encoding="utf-8")
    transport = FakeDriveTransport()

    result = drive.upload_paths([str(outside)], settings=_settings(), transport=transport)

    assert result["uploaded"] == []
    assert result["failed"][0]["status"] == "outside_shareable_area"
    assert not hasattr(transport, "uploads") or transport.uploads == []


def test_upload_paths_requires_destination(monkeypatch, tmp_path):
    settings = drive.DriveSettings(
        enabled=True,
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        root_id=None,
    )
    with pytest.raises(drive.DriveConfigError):
        drive.upload_paths(["whatever.json"], settings=settings, transport=FakeDriveTransport())


def test_upload_paths_reports_unsupported_and_missing(monkeypatch, tmp_path):
    export = tmp_path / "drive_exports"
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(export))
    export.mkdir(parents=True)
    binary = export / "tool.exe"
    binary.write_bytes(b"MZ")
    transport = FakeDriveTransport()

    result = drive.upload_paths(
        [str(binary), str(export / "missing.json")],
        settings=_settings(),
        transport=transport,
    )

    statuses = {item["status"] for item in result["failed"]}
    assert statuses == {"unsupported_for_upload", "not_found"}
    assert result["uploaded"] == []


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


# --- Connected folders (Drive workspace, SPEC_LV_DRIVE_WORKSPACE_2026-07-27) ---


class FolderVerifyTransport(FakeDriveTransport):
    """Fake that knows one real shared folder, one file link, one dead link."""

    def get_json(self, url, token):
        assert token == "access-token-secret"
        self.json_urls.append(url)
        if "/files/shared-folder-1" in url:
            return {
                "id": "shared-folder-1",
                "name": "Grade 7 shared",
                "mimeType": "application/vnd.google-apps.folder",
            }
        if "/files/not-a-folder-1" in url:
            return {"id": "not-a-folder-1", "name": "lesson.pdf", "mimeType": "application/pdf"}
        raise OSError("no access")


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("https://drive.google.com/drive/folders/AbC-123_xyz?usp=sharing", "AbC-123_xyz"),
        ("https://drive.google.com/drive/u/0/folders/AbC123xyz", "AbC123xyz"),
        ("https://drive.google.com/open?id=AbC123xyz", "AbC123xyz"),
        ("https://drive.google.com/drive/folders/AbC123xyz/", "AbC123xyz"),
        ("https://drive.google.com/drive/folders/AbC123xyz#heading", "AbC123xyz"),
        ("https://drive.google.com/drive/mobile/folders/AbC123xyz", "AbC123xyz"),
        ("  https://drive.google.com/drive/folders/AbC123xyz?usp=drive_link  ", "AbC123xyz"),
        ("AbC123xyz", "AbC123xyz"),
        ("https://example.com/not-drive", None),
        ("https://docs.google.com/document/d/DocId12345/edit", None),
        ("https://drive.google.com/file/d/FileId12345/view", None),
        ("abc", None),
        ("", None),
    ],
)
def test_parse_folder_link(link, expected):
    assert drive.parse_folder_link(link) == expected


def _folders_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_FOLDERS_PATH", str(tmp_path / "drive_folders.json"))


def test_connect_folder_verifies_live_and_saves(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    entry = drive.connect_folder(
        "https://drive.google.com/drive/folders/shared-folder-1?usp=sharing",
        name="Grade 7 materials",
        purpose="curriculum_unit_source",
        settings=_settings(),
        transport=FolderVerifyTransport(),
    )

    assert entry["id"] == "shared-folder-1"
    assert entry["name"] == "Grade 7 materials"
    assert entry["purpose"] == "curriculum_unit_source"
    assert entry["last_checked"] is None
    assert entry["share_back"] is False

    saved = drive.list_connected_folders()
    assert [f["id"] for f in saved] == ["shared-folder-1"]
    assert (drive.folders_path().stat().st_mode & 0o777) == 0o600


def test_connect_folder_defaults_name_from_drive_metadata(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    entry = drive.connect_folder(
        "shared-folder-1",
        settings=_settings(),
        transport=FolderVerifyTransport(),
    )
    assert entry["name"] == "Grade 7 shared"
    assert entry["purpose"] == "unassigned"


def test_connect_folder_rejects_file_links(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="file, not a folder"):
        drive.connect_folder(
            "not-a-folder-1", settings=_settings(), transport=FolderVerifyTransport()
        )
    assert drive.list_connected_folders() == []


def test_connect_folder_rejects_unparseable_links(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="folder link"):
        drive.connect_folder(
            "https://example.com/not-drive", settings=_settings(), transport=FolderVerifyTransport()
        )


def test_connect_folder_rejects_invalid_purpose(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="purpose"):
        drive.connect_folder(
            "shared-folder-1",
            purpose="totally_made_up",
            settings=_settings(),
            transport=FolderVerifyTransport(),
        )


def test_connect_folder_unreachable_raises_auth_error(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    with pytest.raises(drive.DriveAuthError):
        drive.connect_folder(
            "dead-folder-1", settings=_settings(), transport=FolderVerifyTransport()
        )
    assert drive.list_connected_folders() == []


def test_reconnecting_same_folder_replaces_entry(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    transport = FolderVerifyTransport()
    drive.connect_folder("shared-folder-1", settings=_settings(), transport=transport)
    drive.connect_folder(
        "shared-folder-1",
        name="Renamed",
        purpose="teacher_artifact_source",
        settings=_settings(),
        transport=transport,
    )

    saved = drive.list_connected_folders()
    assert len(saved) == 1
    assert saved[0]["name"] == "Renamed"
    assert saved[0]["purpose"] == "teacher_artifact_source"


def test_disconnect_and_mark_checked_lifecycle(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    drive.connect_folder("shared-folder-1", settings=_settings(), transport=FolderVerifyTransport())

    drive.mark_folder_checked("shared-folder-1")
    assert drive.list_connected_folders()[0]["last_checked"] is not None

    assert drive.disconnect_folder("shared-folder-1") is True
    assert drive.list_connected_folders() == []
    assert drive.disconnect_folder("shared-folder-1") is False


def test_list_connected_folders_survives_corrupt_registry(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    drive.folders_path().write_text("{not json", encoding="utf-8")
    assert drive.list_connected_folders() == []


def test_list_files_rejects_query_injection_via_folder_id():
    with pytest.raises(ValueError, match="folder ID"):
        drive.list_files(
            "", "x' or 'a'='a", settings=_settings(), transport=FakeDriveTransport()
        )


def test_list_files_escapes_quotes_in_search_text():
    transport = FakeDriveTransport()
    drive.list_files("teacher's notes", settings=_settings(), transport=transport)
    listed_url = transport.json_urls[-1]
    q = parse_qs(urlparse(listed_url).query)["q"][0]
    assert "teacher\\'s notes" in q


class AnyFolderTransport(FakeDriveTransport):
    """Fake that treats every metadata lookup as a valid folder."""

    def get_json(self, url, token):
        assert token == "access-token-secret"
        self.json_urls.append(url)
        folder_id = url.rsplit("/files/", 1)[-1].split("?", 1)[0]
        return {
            "id": folder_id,
            "name": f"Folder {folder_id}",
            "mimeType": "application/vnd.google-apps.folder",
        }


def test_concurrent_connects_do_not_drop_folders(monkeypatch, tmp_path):
    """Registry writes are read-modify-write; the lock must keep them serial.

    Without _FOLDERS_LOCK, two threads that both read the registry before either
    writes it back will last-writer-wins each other and silently drop a folder.
    """
    import threading

    _folders_env(monkeypatch, tmp_path)
    errors = []

    def connect(index):
        try:
            drive.connect_folder(
                f"folder-{index:02d}",
                settings=_settings(),
                transport=AnyFolderTransport(),
            )
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=connect, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    saved = {f["id"] for f in drive.list_connected_folders()}
    assert saved == {f"folder-{i:02d}" for i in range(12)}


def test_mark_folder_checked_unknown_id_writes_nothing(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)
    drive.mark_folder_checked("never-connected")
    assert not drive.folders_path().exists()


def test_upload_paths_rejects_malformed_destination_folder_id(monkeypatch, tmp_path):
    export = tmp_path / "drive_exports"
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(export))
    export.mkdir(parents=True)
    deliverable = export / "unit-plan.md"
    deliverable.write_text("# Unit plan", encoding="utf-8")

    with pytest.raises(ValueError, match="destination folder ID"):
        drive.upload_paths(
            [str(deliverable)], "x' or 'a'='a", settings=_settings(), transport=FakeDriveTransport()
        )


def test_upload_paths_refuses_symlink_escaping_allowed_roots(monkeypatch, tmp_path):
    """A symlink planted inside the export dir must not leak an outside file."""
    export = tmp_path / "drive_exports"
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(export))
    export.mkdir(parents=True)
    outside = tmp_path / "secrets.json"
    outside.write_text('{"secret": true}', encoding="utf-8")
    link = export / "innocent-lens.json"
    link.symlink_to(outside)
    transport = FakeDriveTransport()

    result = drive.upload_paths([str(link)], settings=_settings(), transport=transport)

    assert result["uploaded"] == []
    assert result["failed"][0]["status"] == "outside_shareable_area"
    assert not hasattr(transport, "uploads") or transport.uploads == []


def test_manifests_are_private_and_leave_no_temp_files(monkeypatch, tmp_path):
    """Import/export manifests hold student-linked data: 0600, no temp residue."""
    import_home = tmp_path / "drive_imports"
    export = tmp_path / "drive_exports"
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(import_home))
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(export))
    export.mkdir(parents=True)
    deliverable = export / "unit-plan.md"
    deliverable.write_text("# Unit plan", encoding="utf-8")

    drive.import_files(["text-1"], "unassigned", settings=_settings(), transport=FakeDriveTransport())
    drive.upload_paths([str(deliverable)], settings=_settings(), transport=FakeDriveTransport())

    for manifest in (import_home / "import_manifest.json", export / "export_manifest.json"):
        assert manifest.exists()
        assert (manifest.stat().st_mode & 0o777) == 0o600
    leftovers = [p for p in [*import_home.iterdir(), *export.iterdir()] if p.name.endswith(".tmp")]
    assert leftovers == []


# --- Final hardening (SPEC_LV_DRIVE_FINAL_HARDENING_2026-07-27 H2-H5) -----


class _FakeResponse:
    def __init__(self, chunks, content_length=None):
        self._chunks = list(chunks)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def read(self, n=-1):
        return self._chunks.pop(0) if self._chunks else b""


def test_read_bounded_accepts_normal_body():
    assert drive._read_bounded(_FakeResponse([b"ab", b"cd"], content_length=4), 10) == b"abcd"


def test_read_bounded_rejects_content_length_over_limit():
    with pytest.raises(drive.DriveFileTooLarge):
        drive._read_bounded(_FakeResponse([b"x"], content_length=11), 10)


def test_read_bounded_rejects_oversized_stream_without_header():
    # A lying/absent Content-Length can't bypass the streaming cap.
    with pytest.raises(drive.DriveFileTooLarge):
        drive._read_bounded(_FakeResponse([b"x" * 6, b"x" * 6]), 10)


def test_import_rejects_oversized_file_by_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "imports"))
    monkeypatch.setattr(drive, "MAX_IMPORT_BYTES", 100)

    class BigFileTransport(FakeDriveTransport):
        def get_json(self, url, token):
            return {"id": "big-1", "name": "huge.pdf", "mimeType": "application/pdf", "size": "101"}

        def get_bytes(self, url, token):
            raise AssertionError("oversized file must not be downloaded")

    result = drive.import_files(
        ["big-1"], "unassigned", settings=_settings(), transport=BigFileTransport()
    )
    assert result["imported"] == []
    assert result["failed"][0]["code"] == "file_too_large"
    assert result["failed"][0]["status"] == "file_too_large"
    assert "too large" in result["failed"][0]["message"]


def test_import_rejects_oversized_content_from_transport(monkeypatch, tmp_path):
    # Transports that don't stream (fixtures) are caught by the post-check.
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "imports"))
    monkeypatch.setattr(drive, "MAX_IMPORT_BYTES", 10)

    class FatContentTransport(FakeDriveTransport):
        def get_json(self, url, token):
            return {"id": "fat-1", "name": "fat.txt", "mimeType": "text/plain"}

        def get_bytes(self, url, token):
            return b"x" * 11

    result = drive.import_files(
        ["fat-1"], "unassigned", settings=_settings(), transport=FatContentTransport()
    )
    assert result["imported"] == []
    assert result["failed"][0]["code"] == "file_too_large"
    assert list((tmp_path / "imports").glob("*.txt")) == []


def test_prune_student_exports_keeps_three_newest(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(tmp_path))
    stamps = ["20260727-090000", "20260727-100000", "20260727-110000", "20260727-120000"]
    for stamp in stamps:
        (tmp_path / f"student-lens-student-marco-{stamp}.json").write_text("{}")
    (tmp_path / "student-lens-student-nora-20260727-080000.json").write_text("{}")
    (tmp_path / "export_manifest.json").write_text("{}")

    removed = drive.prune_student_exports("student-marco")

    assert removed == 1
    kept = sorted(p.name for p in tmp_path.glob("student-lens-student-marco-*.json"))
    assert kept == [f"student-lens-student-marco-{s}.json" for s in stamps[1:]]
    # Other students' snapshots and the manifest are untouched.
    assert (tmp_path / "student-lens-student-nora-20260727-080000.json").exists()
    assert (tmp_path / "export_manifest.json").exists()


def test_prune_student_exports_missing_dir_is_noop(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(tmp_path / "never-created"))
    assert drive.prune_student_exports("student-marco") == 0


def test_list_files_rejects_overlong_query():
    with pytest.raises(ValueError, match="too long"):
        drive.list_files("x" * 2000, settings=_settings(), transport=FakeDriveTransport())


def test_atomic_write_temp_file_is_0600_from_birth(monkeypatch, tmp_path):
    import os as os_module

    modes = {}
    real_replace = os_module.replace

    def spy(src, dst):
        modes["tmp"] = os_module.stat(src).st_mode & 0o777
        real_replace(src, dst)

    monkeypatch.setattr(drive.os, "replace", spy)
    target = tmp_path / "private.json"
    drive._atomic_write_private_json(target, {"a": 1})
    assert modes["tmp"] == 0o600
    assert (target.stat().st_mode & 0o777) == 0o600


class _HTTPFailTransport:
    def post_form(self, url, data):
        from io import BytesIO
        from urllib import error as urlerror

        raise urlerror.HTTPError(url, 400, "Bad Request", None, BytesIO(b'{"error":"server_error"}'))


def test_auth_error_chain_never_contains_secrets():
    with pytest.raises(drive.DriveAuthError) as excinfo:
        drive._access_token(_settings(), _HTTPFailTransport())
    chain_text = "".join(
        repr(part) for part in (excinfo.value, excinfo.value.__cause__, excinfo.value.args)
    )
    assert "refresh-token" not in chain_text
    assert "client-secret" not in chain_text


def test_access_token_rejects_non_dict_payload():
    class ListTransport:
        def post_form(self, url, data):
            return ["not", "a", "dict"]

    with pytest.raises(drive.DriveAuthError):
        drive._access_token(_settings(), ListTransport())


def test_list_files_handles_malformed_responses():
    class NonDictListTransport(FakeDriveTransport):
        def get_json(self, url, token):
            return ["garbage"]

    with pytest.raises(drive.DriveAuthError):
        drive.list_files(settings=_settings(), transport=NonDictListTransport())

    class JunkFieldsTransport(FakeDriveTransport):
        def get_json(self, url, token):
            return {"files": "junk", "nextPageToken": 123}

    result = drive.list_files(settings=_settings(), transport=JunkFieldsTransport())
    assert result == {"files": [], "next_page_token": None}


def test_import_handles_non_dict_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "imports"))

    class GarbageMetaTransport(FakeDriveTransport):
        def get_json(self, url, token):
            return "garbage"

    result = drive.import_files(
        ["x-1"], "unassigned", settings=_settings(), transport=GarbageMetaTransport()
    )
    assert result["imported"] == []
    assert result["failed"][0]["status"] == "download_failed"


def test_import_revoked_mid_import_fails_cleanly(monkeypatch, tmp_path):
    # Concurrent disconnect: token revoked between listing and download.
    monkeypatch.setenv("LV_GOOGLE_DRIVE_IMPORT_DIR", str(tmp_path / "imports"))

    class RevokedMidwayTransport(FakeDriveTransport):
        def get_json(self, url, token):
            return {"id": "pdf-1", "name": "lesson.pdf", "mimeType": "application/pdf", "size": "10"}

        def get_bytes(self, url, token):
            from io import BytesIO
            from urllib import error as urlerror

            raise urlerror.HTTPError(url, 401, "Unauthorized", None, BytesIO(b"{}"))

    result = drive.import_files(
        ["pdf-1"], "unassigned", settings=_settings(), transport=RevokedMidwayTransport()
    )
    assert result["imported"] == []
    assert result["failed"][0]["status"] == "download_failed"
    assert result["failed"][0]["message"] == "This file could not be imported safely."


def test_connect_folder_handles_non_dict_metadata(monkeypatch, tmp_path):
    _folders_env(monkeypatch, tmp_path)

    class GarbageMetaTransport(FakeDriveTransport):
        def get_json(self, url, token):
            return "garbage"

    with pytest.raises(drive.DriveAuthError):
        drive.connect_folder(
            "https://drive.google.com/drive/folders/shared-folder-1",
            settings=_settings(),
            transport=GarbageMetaTransport(),
        )

# ---------------------------------------------------------------------------
# SPEC_LV_DRIVE_OOTB 2026-08-18: parse_file_link (G2) + create_folder (G5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("https://drive.google.com/file/d/FileId12345/view?usp=sharing", "FileId12345"),
        ("https://docs.google.com/document/d/DocId12345/edit", "DocId12345"),
        ("https://docs.google.com/spreadsheets/d/SheetId123/edit#gid=0", "SheetId123"),
        ("https://drive.google.com/open?id=AbC123xyz", "AbC123xyz"),
        ("  https://drive.google.com/file/d/FileId12345/view  ", "FileId12345"),
        ("AbC-123_xyz", "AbC-123_xyz"),
        ("https://example.com/not-drive", None),
        ("???", None),
        ("abc", None),
        ("", None),
    ],
)
def test_parse_file_link(link, expected):
    assert drive.parse_file_link(link) == expected


class FolderCreateTransport(FakeDriveTransport):
    def __init__(self, existing=None):
        super().__init__()
        self.existing = existing or []
        self.created = []

    def get_json(self, url, token):
        assert token == "access-token-secret"
        self.json_urls.append(url)
        assert "/files?" in url
        return {"files": self.existing}

    def post_json(self, url, token, payload):
        assert token == "access-token-secret"
        self.created.append(payload)
        return {"id": "new-folder-1"}


def test_create_folder_reuses_existing_folder_by_name():
    transport = FolderCreateTransport(existing=[{"id": "existing-1", "name": "Lenses"}])
    folder_id = drive.create_folder("Lenses", settings=_settings(), transport=transport)
    assert folder_id == "existing-1"
    assert transport.created == []
    query = parse_qs(urlparse(transport.json_urls[0]).query)["q"][0]
    assert "name = 'Lenses'" in query
    assert "trashed = false" in query


def test_create_folder_creates_when_absent():
    transport = FolderCreateTransport()
    folder_id = drive.create_folder(
        "Lingua Viva – Student Lenses", settings=_settings(), transport=transport
    )
    assert folder_id == "new-folder-1"
    assert transport.created == [{
        "name": "Lingua Viva – Student Lenses",
        "mimeType": "application/vnd.google-apps.folder",
    }]


def test_create_folder_with_parent_scopes_search_and_metadata():
    transport = FolderCreateTransport()
    drive.create_folder("Lenses", "parent-123", settings=_settings(), transport=transport)
    query = parse_qs(urlparse(transport.json_urls[0]).query)["q"][0]
    assert "'parent-123' in parents" in query
    assert transport.created[0]["parents"] == ["parent-123"]


def test_create_folder_escapes_quotes_in_name():
    transport = FolderCreateTransport()
    drive.create_folder("Nora's 'class'", settings=_settings(), transport=transport)
    query = parse_qs(urlparse(transport.json_urls[0]).query)["q"][0]
    assert "name = 'Nora\\'s \\'class\\''" in query


def test_create_folder_rejects_blank_name_and_bad_parent():
    transport = FolderCreateTransport()
    with pytest.raises(ValueError):
        drive.create_folder("   ", settings=_settings(), transport=transport)
    with pytest.raises(ValueError):
        drive.create_folder("Lenses", "bad id!", settings=_settings(), transport=transport)


def test_create_folder_post_failure_raises_auth_error_without_secrets():
    class FailingPost(FolderCreateTransport):
        def post_json(self, url, token, payload):
            raise OSError("network down")

    with pytest.raises(drive.DriveAuthError) as excinfo:
        drive.create_folder("Lenses", settings=_settings(), transport=FailingPost())
    assert "client-secret" not in str(excinfo.value)
    assert "refresh-token" not in str(excinfo.value)
