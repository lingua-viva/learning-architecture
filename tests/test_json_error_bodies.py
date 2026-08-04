"""A3 — Ingest endpoints must return JSON error bodies, never bare 500 strings.

Every /api/ endpoint returns Content-Type: application/json even on unhandled
exceptions. The frontend parses response.json() — a bare text "Internal Server
Error" causes `Unexpected token 'I'` crashes (Claudia P0-1 finding).
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.web import app
    return TestClient(app, raise_server_exceptions=False)


class TestIngestEndpointsReturnJSON:
    """Both /api/ingest and /api/students/ingest return JSON on any error."""

    def test_ingest_no_file(self, client):
        """POST /api/ingest with no file → JSON 400."""
        resp = client.post("/api/ingest")
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_ingest_wrong_type(self, client):
        """POST /api/ingest with a .txt file → JSON 400 with honest message."""
        resp = client.post(
            "/api/ingest",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_students_ingest_no_file(self, client):
        """POST /api/students/ingest with no body → JSON 400."""
        resp = client.post("/api/students/ingest")
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_students_ingest_empty_file(self, client):
        """POST /api/students/ingest with empty file → JSON 400."""
        resp = client.post(
            "/api/students/ingest",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data


class TestGlobalExceptionHandlerReturnsJSON:
    """The global exception handler guarantees JSON on any unhandled crash."""

    def test_content_type_on_500(self, client):
        """Any 500 response has Content-Type: application/json."""
        # Deliberately trigger a crash via a malformed multipart that passes
        # initial checks but fails deeper — or just verify the handler exists.
        # We POST bad JSON to a JSON-expecting path.
        resp = client.post(
            "/api/students/ingest",
            content=b"not valid json at all",
            headers={"content-type": "application/json"},
        )
        # Should get a 400 (our handler catches json parse) or 500 (global handler)
        # Either way: must be JSON.
        assert "application/json" in resp.headers.get("content-type", "")
        data = resp.json()
        assert "error" in data
