"""SPEC_LV_DRIVE_OOTB_ROSTER_TO_LENSES_2026-08-18 seam tests.

G2: docpipe.drive.fetch_file is real (roster import from a pasted Drive link).
G5: drive_sync.ensure_lens_sync_folder auto-provisions the sync-back folder.
Both must work offline against fakes — no network, no secrets in errors.
"""
from pathlib import Path

import pytest

from src.lingua_viva import drive_sync
from src.lingua_viva import google_drive_integration as gdi
from src.lingua_viva.docpipe import drive as docpipe_drive


def _settings():
    return gdi.DriveSettings(
        enabled=True,
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        root_id="root-folder",
    )


class FetchTransport:
    def __init__(self, meta, content=b"%PDF mocked content"):
        self.meta = meta
        self.content = content
        self.json_urls = []
        self.byte_urls = []

    def post_form(self, url, data):
        return {"access_token": "access-token-secret"}

    def get_json(self, url, token):
        assert token == "access-token-secret"
        self.json_urls.append(url)
        if isinstance(self.meta, Exception):
            raise self.meta
        return self.meta

    def get_bytes(self, url, token):
        assert token == "access-token-secret"
        self.byte_urls.append(url)
        return self.content


def _wire(monkeypatch, transport):
    monkeypatch.setattr(gdi, "ensure_configured", lambda settings=None: _settings())
    monkeypatch.setattr(gdi, "default_transport", lambda: transport)


def test_fetch_file_regular_file_downloads_raw_bytes(monkeypatch):
    transport = FetchTransport(
        {"id": "pdf-1", "name": "roster.pdf", "mimeType": "application/pdf", "size": "123"}
    )
    _wire(monkeypatch, transport)
    result = docpipe_drive.fetch_file("https://drive.google.com/file/d/pdf-1/view")

    assert result.filename == "roster.pdf"
    assert result.mime == "application/pdf"
    assert result.content == b"%PDF mocked content"
    assert result.origin == "drive"
    assert result.drive_file_id == "pdf-1"
    assert "alt=media" in transport.byte_urls[0]
    assert "/export" not in transport.byte_urls[0]


def test_fetch_file_google_doc_exports_plain_text(monkeypatch):
    transport = FetchTransport(
        {"id": "gdoc-1", "name": "Class Roster", "mimeType": "application/vnd.google-apps.document"},
        content=b"Marco Bianchi\nNora Rossi",
    )
    _wire(monkeypatch, transport)
    result = docpipe_drive.fetch_file("https://docs.google.com/document/d/gdoc-1/edit")

    assert result.filename == "Class Roster.txt"
    assert result.mime == "text/plain"
    assert "/export" in transport.byte_urls[0]
    assert "text%2Fplain" in transport.byte_urls[0]


def test_fetch_file_google_sheet_exports_csv(monkeypatch):
    transport = FetchTransport(
        {"id": "sheet-1", "name": "Roster", "mimeType": "application/vnd.google-apps.spreadsheet"},
        content=b"First,Last\nMarco,Bianchi",
    )
    _wire(monkeypatch, transport)
    result = docpipe_drive.fetch_file("sheet-1")

    assert result.filename == "Roster.csv"
    assert result.mime == "text/csv"
    assert "text%2Fcsv" in transport.byte_urls[0]


def test_fetch_file_oversized_by_metadata_is_rejected_before_download(monkeypatch):
    transport = FetchTransport(
        {"id": "big-1", "name": "huge.pdf", "mimeType": "application/pdf",
         "size": str(gdi.MAX_IMPORT_BYTES + 1)}
    )
    _wire(monkeypatch, transport)
    with pytest.raises(gdi.DriveFileTooLarge):
        docpipe_drive.fetch_file("big-1")
    assert transport.byte_urls == []


def test_fetch_file_unparseable_ref_raises_value_error(monkeypatch):
    _wire(monkeypatch, FetchTransport({}))
    with pytest.raises(ValueError):
        docpipe_drive.fetch_file("???")


def test_fetch_file_metadata_failure_is_auth_error_without_secrets(monkeypatch):
    transport = FetchTransport(OSError("network down"))
    _wire(monkeypatch, transport)
    with pytest.raises(gdi.DriveAuthError) as excinfo:
        docpipe_drive.fetch_file("pdf-1")
    text = str(excinfo.value)
    assert "client-secret" not in text and "refresh-token" not in text


def test_fetch_file_unconfigured_raises_config_error(monkeypatch, tmp_path):
    for var in ("LV_GOOGLE_DRIVE_ENABLED", "LV_GOOGLE_CLIENT_ID",
                "LV_GOOGLE_CLIENT_SECRET", "LV_GOOGLE_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))
    with pytest.raises(gdi.DriveConfigError):
        docpipe_drive.fetch_file("pdf-1")


# ---------------------------------------------------------------------------
# G5: ensure_lens_sync_folder
# ---------------------------------------------------------------------------


def _isolate(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))


def test_ensure_lens_sync_folder_reuses_mapped_folder(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    drive_sync.set_sync_folder_map({drive_sync.DEFAULT_SHARED_CATEGORY: "folder-abc"})

    def boom(*a, **k):
        raise AssertionError("create_folder must not be called when a folder is mapped")

    monkeypatch.setattr(gdi, "create_folder", boom)
    assert drive_sync.ensure_lens_sync_folder() == "folder-abc"


def test_ensure_lens_sync_folder_provisions_and_persists(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(gdi, "load_settings", lambda: _settings())
    created = []

    def fake_create(name, parent_id=None, **kwargs):
        created.append(name)
        return "folder-new-1"

    monkeypatch.setattr(gdi, "create_folder", fake_create)
    assert drive_sync.ensure_lens_sync_folder() == "folder-new-1"
    assert created == [drive_sync.LENS_SYNC_FOLDER_NAME]
    # Persisted: the next call reuses the map without creating again.
    assert drive_sync.get_sync_folder_id_for_category(drive_sync.DEFAULT_SHARED_CATEGORY) == "folder-new-1"
    assert drive_sync.ensure_lens_sync_folder() == "folder-new-1"
    assert created == [drive_sync.LENS_SYNC_FOLDER_NAME]


def test_ensure_lens_sync_folder_unconfigured_returns_none(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(gdi, "load_settings", lambda: gdi.DriveSettings(
        enabled=False, client_id=None, client_secret=None, refresh_token=None, root_id=None,
    ))
    assert drive_sync.ensure_lens_sync_folder() is None


def test_ensure_lens_sync_folder_create_failure_is_best_effort(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(gdi, "load_settings", lambda: _settings())

    def boom(*a, **k):
        raise gdi.DriveAuthError("Could not create the Drive folder.")

    monkeypatch.setattr(gdi, "create_folder", boom)
    assert drive_sync.ensure_lens_sync_folder() is None
