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

    uploads = []

    def post_multipart(self, url, token, metadata, content, content_type):
        record = {
            "name": metadata.get("name"),
            "parents": metadata.get("parents"),
            "mime_type": content_type,
            "size": len(content),
            "content": content.decode("utf-8", errors="replace"),
        }
        FakeDriveTransport.uploads.append(record)
        return {"id": f"uploaded-{len(FakeDriveTransport.uploads)}", "name": record["name"]}


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


def test_imported_drive_files_surface_as_extraction_sources(monkeypatch, tmp_path):
    """Regression pin: Drive imports land in the drive-imports dir and MUST be
    visible to /api/extraction/sources (the 2026-07-27 path-mismatch bug)."""
    _configure(monkeypatch, tmp_path)
    response = client.post(
        "/api/google-drive/import",
        json={"file_ids": ["pdf-1"], "purpose": "unassigned"},
    )
    assert response.status_code == 200
    local_path = response.json()["imported"][0]["local_path"]

    sources = client.get("/api/extraction/sources").json()["sources"]
    match = [s for s in sources if s["file_path"] == local_path]
    assert match, "Drive-imported file missing from extraction sources"
    assert match[0]["source_type"] == "google_drive"


def test_upload_route_rejects_empty_payload_even_when_unconfigured():
    response = client.post("/api/google-drive/upload", json={})
    assert response.status_code == 400


def test_upload_route_shares_student_lens(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(tmp_path / "drive_exports"))
    FakeDriveTransport.uploads = []
    created = client.post("/api/students", json={"display_name": "Marco", "grade_level": "G3"})
    assert created.status_code == 200
    student_id = created.json()["student_id"]

    response = client.post("/api/google-drive/upload", json={"student_id": student_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["failed"] == []
    assert len(payload["uploaded"]) == 1
    assert payload["uploaded"][0]["name"].startswith(f"student-lens-{student_id}")
    assert payload["uploaded"][0]["name"].endswith(".md")
    assert payload["uploaded"][0]["folder_id"] == "root-folder"
    assert FakeDriveTransport.uploads[0]["parents"] == ["root-folder"]
    assert FakeDriveTransport.uploads[0]["mime_type"] == "text/markdown"
    assert "# Student Lens - Marco" in FakeDriveTransport.uploads[0]["content"]
    assert "Privacy Boundary" in FakeDriveTransport.uploads[0]["content"]
    # Lens Markdown was materialized in the export dir before sharing.
    exported = list((tmp_path / "drive_exports").glob("student-lens-*.md"))
    assert len(exported) == 1
    assert exported[0].read_text(encoding="utf-8").startswith("# Student Lens - Marco")


def test_upload_route_creates_deliverable_and_audit_receipt(monkeypatch, tmp_path):
    """Sharing to Drive is the highest-risk action in the app (data leaves the
    machine). A successful share must leave a durable DeliverableRecord and
    an exportable AuditReceipt, just like the observation export does."""
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "lv_home"))
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(tmp_path / "drive_exports"))
    FakeDriveTransport.uploads = []
    created = client.post("/api/students", json={"display_name": "Marco", "grade_level": "G3"})
    student_id = created.json()["student_id"]

    response = client.post("/api/google-drive/upload", json={"student_id": student_id})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["uploaded"]) == 1
    assert payload["deliverable"]["type"] == "drive_export"
    assert payload["deliverable"]["status"] == "exported"
    deliverable_id = payload["deliverable"]["deliverable_id"]
    assert deliverable_id in payload["audit_receipt"]["deliverable_ids"]
    # Marco's name must not leak into the receipt payload.
    assert "Marco" not in str(payload["audit_receipt"])

    # The new deliverable must actually surface through the Governance panel's
    # read path, not just be constructed and thrown away.
    listed = client.get("/api/deliverables").json()["deliverables"]
    match = [d for d in listed if d["deliverable_id"] == deliverable_id]
    assert match, "drive_export deliverable missing from /api/deliverables"
    assert match[0]["type"] == "drive_export"

    # And it must be independently exportable via the audit-receipts route.
    exported = client.post(
        "/api/audit-receipts/export",
        json={"scope": "deliverable", "deliverable_id": deliverable_id},
    )
    assert exported.status_code == 200
    assert deliverable_id in exported.json()["receipt"]["deliverable_ids"]


def test_upload_route_refuses_files_outside_lv_home(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(tmp_path / "drive_exports"))
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    response = client.post("/api/google-drive/upload", json={"file_paths": [str(outside)]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["uploaded"] == []
    assert payload["failed"][0]["status"] == "outside_shareable_area"


def test_upload_route_requires_destination_folder(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.delenv("LV_GOOGLE_DRIVE_ROOT_ID")
    monkeypatch.setenv("LV_GOOGLE_DRIVE_EXPORT_DIR", str(tmp_path / "drive_exports"))
    created = client.post("/api/students", json={"display_name": "Marco", "grade_level": "G3"})
    student_id = created.json()["student_id"]

    response = client.post("/api/google-drive/upload", json={"student_id": student_id})
    assert response.status_code == 503


class FolderVerifyTransport(FakeDriveTransport):
    """Knows one shared folder, one plain file, and fails everything else."""

    def get_json(self, url, token):
        if "/files/shared-folder-1" in url:
            return {
                "id": "shared-folder-1",
                "name": "Grade 7 shared",
                "mimeType": "application/vnd.google-apps.folder",
            }
        if "/files/not-a-folder-1" in url:
            return {"id": "not-a-folder-1", "name": "lesson.pdf", "mimeType": "application/pdf"}
        if "/files?" in url or "/files/pdf-1" in url:
            return super().get_json(url, token)
        raise OSError("no access")


def _configure_folders(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("LV_GOOGLE_DRIVE_FOLDERS_PATH", str(tmp_path / "drive_folders.json"))
    monkeypatch.setattr(drive, "UrlLibDriveTransport", FolderVerifyTransport)


def test_folders_route_connect_list_disconnect_lifecycle(monkeypatch, tmp_path):
    _configure_folders(monkeypatch, tmp_path)

    connected = client.post(
        "/api/google-drive/folders",
        json={
            "link": "https://drive.google.com/drive/folders/shared-folder-1?usp=sharing",
            "name": "Grade 7 materials",
            "purpose": "curriculum_unit_source",
        },
    )
    assert connected.status_code == 200
    entry = connected.json()["connected"]
    assert entry["id"] == "shared-folder-1"
    assert entry["purpose"] == "curriculum_unit_source"

    listed = client.get("/api/google-drive/folders")
    assert listed.status_code == 200
    assert [f["id"] for f in listed.json()["folders"]] == ["shared-folder-1"]

    removed = client.delete("/api/google-drive/folders/shared-folder-1")
    assert removed.status_code == 200
    assert removed.json()["disconnected"] == "shared-folder-1"
    assert client.get("/api/google-drive/folders").json()["folders"] == []
    assert client.delete("/api/google-drive/folders/shared-folder-1").status_code == 404


def test_sync_folder_map_route_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))

    saved = client.post(
        "/api/google-drive/sync-folder-map",
        json={
            "folder_map": {
                "student_summaries": "folder-summary",
                "personal": "folder-personal",
            }
        },
    )
    assert saved.status_code == 200
    assert saved.json()["folder_map"]["student_summaries"] == "folder-summary"
    assert saved.json()["folder_map"]["personal"] == "folder-personal"

    loaded = client.get("/api/google-drive/sync-folder-map")
    assert loaded.status_code == 200
    assert loaded.json()["folder_map"] == saved.json()["folder_map"]
    categories = {item["id"]: item for item in loaded.json()["categories"]}
    assert categories["personal"]["label"] == "Personal"
    assert categories["personal"]["configured"] is True


def test_folders_route_rejects_bad_links_and_file_links(monkeypatch, tmp_path):
    _configure_folders(monkeypatch, tmp_path)

    bad_link = client.post(
        "/api/google-drive/folders", json={"link": "https://example.com/not-drive"}
    )
    assert bad_link.status_code == 400

    file_link = client.post("/api/google-drive/folders", json={"link": "not-a-folder-1"})
    assert file_link.status_code == 400
    assert client.get("/api/google-drive/folders").json()["folders"] == []


def test_folders_route_requires_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_GOOGLE_DRIVE_FOLDERS_PATH", str(tmp_path / "drive_folders.json"))
    response = client.post("/api/google-drive/folders", json={"link": "shared-folder-1"})
    assert response.status_code == 503


def test_list_route_marks_connected_folder_checked(monkeypatch, tmp_path):
    _configure_folders(monkeypatch, tmp_path)
    client.post("/api/google-drive/folders", json={"link": "shared-folder-1"})
    assert client.get("/api/google-drive/folders").json()["folders"][0]["last_checked"] is None

    listed = client.post(
        "/api/google-drive/list", json={"query": "", "folder_id": "shared-folder-1"}
    )
    assert listed.status_code == 200
    assert client.get("/api/google-drive/folders").json()["folders"][0]["last_checked"]


def test_drive_workspace_ui_mounts_controls():
    html = Path("static/index.html").read_text(encoding="utf-8")
    for text in (
        "Google Drive",
        "/api/google-drive/status",
        "/api/google-drive/list",
        "/api/google-drive/import",
        'api("/api/google-drive/folders")',
        'api("/api/google-drive/folders", {',
        'api("/api/google-drive/sync-folder-map")',
        "api(`/api/google-drive/folders/${",
        "Drive Folder Routing",
        "renderDrive",
        "drive-connect-link",
        "drive-folder-select",
        "Show files",
        "Bring selected files in",
        "Nothing is added to the student lens until you approve it",
        "student_lens_source",
        "curriculum_unit_source",
    ):
        assert text in html, f"missing UI mount: {text}"

    served = client.get("/")
    assert served.status_code == 200
    assert "Google Drive" in served.text
    assert "/api/google-drive/import" in served.text


def test_list_route_rejects_injected_folder_id(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    response = client.post(
        "/api/google-drive/list", json={"query": "", "folder_id": "x' or 'a'='a"}
    )
    assert response.status_code == 400


def test_drive_operations_emit_privacy_events(monkeypatch, tmp_path):
    from src.lingua_viva.privacy_log import read_privacy_events

    _configure_folders(monkeypatch, tmp_path)

    client.post("/api/google-drive/folders", json={"link": "shared-folder-1"})
    client.post("/api/google-drive/import", json={"file_ids": ["pdf-1"], "purpose": "unassigned"})
    client.delete("/api/google-drive/folders/shared-folder-1")

    events = [e.event_type for e in read_privacy_events(limit=20)]
    assert "drive_folder_connected" in events
    assert "drive_files_imported" in events
    assert "drive_folder_disconnected" in events


def test_import_route_rejects_empty_and_non_string_file_ids(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    for bad in ([], [123], ["ok", ""], "not-a-list", None):
        response = client.post("/api/google-drive/import", json={"file_ids": bad, "purpose": "unassigned"})
        assert response.status_code == 400, bad
        assert "file_ids" in response.json()["error"]


# --- In-app Google sign-in routes (SPEC_LV_DRIVE_SELF_SERVICE_AUTH §A) ----


def test_auth_start_route_503_without_client_config(monkeypatch, tmp_path):
    # Isolate lv_home() — a machine with a real connected OAuth client has
    # ~/.lingua-viva/config/oauth_client.json (hermeticity gap, 2026-08-01).
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "lv-home"))
    response = client.post("/api/google-drive/auth/start")
    assert response.status_code == 503
    assert "client configuration" in response.json()["error"]


def test_auth_start_route_returns_auth_url(monkeypatch):
    from src.lingua_viva import google_drive_oauth as oauth

    monkeypatch.setenv("LV_GOOGLE_OAUTH_CLIENT_ID", "app-cid")
    monkeypatch.setenv("LV_GOOGLE_OAUTH_CLIENT_SECRET", "app-csecret")
    opened = []
    monkeypatch.setattr(oauth.webbrowser, "open", opened.append)
    try:
        response = client.post("/api/google-drive/auth/start")
        assert response.status_code == 200
        body = response.json()
        assert body["flow_pending"] is True
        assert body["auth_url"].startswith(oauth.AUTH_URL)
        assert opened == [body["auth_url"]]  # backend-side browser open
        assert "app-csecret" not in response.text
    finally:
        oauth.cancel_active_flow()


def test_auth_disconnect_route_deletes_and_logs(monkeypatch, tmp_path):
    from src.lingua_viva import google_drive_oauth as oauth

    log_path = tmp_path / "privacy_events.ndjson"
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(log_path))
    oauth._save_stored_auth({"version": 1, "refresh_token": "rt"})
    monkeypatch.setattr(drive, "UrlLibDriveTransport", FakeDriveTransport)

    response = client.post("/api/google-drive/auth/disconnect")
    assert response.status_code == 200
    assert response.json() == {"disconnected": True}
    assert oauth.load_stored_auth() is None
    events = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert any(e["event_type"] == "drive_account_disconnected" for e in events)


def test_auth_disconnect_route_when_not_signed_in():
    response = client.post("/api/google-drive/auth/disconnect")
    assert response.status_code == 200
    assert response.json() == {"disconnected": False}
