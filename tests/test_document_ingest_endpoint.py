"""
Document Ingest Endpoint Tests — Gap 2, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md.

Exercises POST /api/ingest, the browser-facing replacement for
`mc ingest <path.pdf> --type=...` — the one real CLI dependency a teacher
would otherwise have hit. Thin-wraps src/mc_cli.py's ingest_document(), so
this file focuses on the route-level contract (PDF-only, 50MB cap,
temp-file lifecycle, no client-supplied filesystem paths, friendly errors)
rather than re-testing parse/redact/store behavior already covered by
tests/test_document_intelligence.py.

Uses the real local Ollama embedding endpoint for the success-path test
(no mock) — consistent with test_document_intelligence.py's convention for
local-only calls.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import src.mc_cli as mc_cli
import src.web as web

client = TestClient(web.app)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_myp_guide.pdf"


def test_ingest_endpoint_accepts_pdf_and_stores_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(mc_cli, "DOCUMENT_STORE_PATH", tmp_path / "documents.db")

    with open(FIXTURE, "rb") as f:
        response = client.post(
            "/api/ingest",
            files={"file": ("sample_myp_guide.pdf", f, "application/pdf")},
            data={"doc_type": "curriculum"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["filename"] == "sample_myp_guide.pdf"
    assert body["chunks_added"] > 0
    assert (tmp_path / "documents.db").exists()


def test_ingest_endpoint_never_leaves_a_temp_file_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(mc_cli, "DOCUMENT_STORE_PATH", tmp_path / "documents.db")

    with open(FIXTURE, "rb") as f:
        client.post(
            "/api/ingest",
            files={"file": ("sample_myp_guide.pdf", f, "application/pdf")},
            data={"doc_type": "curriculum"},
        )

    ingest_tmp_dir = web._ingest_temp_dir()
    assert list(ingest_tmp_dir.iterdir()) == []


def test_ingest_endpoint_rejects_non_pdf():
    response = client.post(
        "/api/ingest",
        files={"file": ("notes.txt", b"plain text content", "text/plain")},
        data={"doc_type": "curriculum"},
    )
    assert response.status_code == 400
    assert "Only PDF files are supported" in response.json()["error"]


def test_ingest_endpoint_rejects_student_records_type():
    with open(FIXTURE, "rb") as f:
        response = client.post(
            "/api/ingest",
            files={"file": ("sample_myp_guide.pdf", f, "application/pdf")},
            data={"doc_type": "student-records"},
        )
    assert response.status_code == 400
    assert "not supported by this ingestion path" in response.json()["error"]


def test_ingest_endpoint_rejects_no_file():
    response = client.post("/api/ingest", data={"doc_type": "curriculum"})
    assert response.status_code == 400
    assert "No file was uploaded" in response.json()["error"]


def test_ingest_endpoint_rejects_oversized_file(monkeypatch):
    # Patch the cap down instead of constructing a real 50MB+ fixture.
    monkeypatch.setattr(web, "MAX_INGEST_BYTES", 10)
    with open(FIXTURE, "rb") as f:
        response = client.post(
            "/api/ingest",
            files={"file": ("sample_myp_guide.pdf", f, "application/pdf")},
            data={"doc_type": "curriculum"},
        )
    assert response.status_code == 413
    assert "too large" in response.json()["error"]


def test_ingest_endpoint_gives_friendly_error_on_corrupt_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(mc_cli, "DOCUMENT_STORE_PATH", tmp_path / "documents.db")

    response = client.post(
        "/api/ingest",
        files={"file": ("fake.pdf", b"this is not a real pdf file", "application/pdf")},
        data={"doc_type": "curriculum"},
    )
    assert response.status_code == 400
    assert "couldn't be read" in response.json()["error"]


def test_ingest_endpoint_never_trusts_a_client_supplied_path(tmp_path, monkeypatch):
    """The uploaded filename must never be used as a real filesystem path —
    only its suffix is inspected, and the bytes are written to a
    server-chosen tempfile.mkstemp() path."""
    monkeypatch.setattr(mc_cli, "DOCUMENT_STORE_PATH", tmp_path / "documents.db")

    traversal_name = "../../../../tmp/should-not-exist-here.pdf"
    with open(FIXTURE, "rb") as f:
        response = client.post(
            "/api/ingest",
            files={"file": (traversal_name, f, "application/pdf")},
            data={"doc_type": "curriculum"},
        )
    assert response.status_code == 200
    # The response echoes the client-given display name, but nothing was
    # ever written to that path — only to a mkstemp() path inside
    # _ingest_temp_dir(), already proven empty by the temp-file-lifecycle
    # test above.
    assert not Path("/tmp/should-not-exist-here.pdf").exists()
