"""Data rights: export before clear (MC-lessons §8).

MC ships export/remove/purge tiers. LV's /api/profile/clear was
all-or-nothing deletion with no export right at all — for data that is
observations about children, the highest-stakes data in either system.
GET /api/profile/export bundles traces (already hash-only, see traces.py),
privacy events, student lens + observation history, and the revision log
into one local-download JSON, so a teacher can keep a copy before clearing.

Smoke test per spec: export -> clear -> export returns empty.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.lingua_viva.reasoning import ReasonResult, ReasoningEngine
from src.web import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _deterministic_reasoning(monkeypatch):
    async def fake_reason(
        self,
        query: str,
        context: dict | None = None,
        model: str | None = None,
        default_model: str | None = None,
        system_prompt: str | None = None,
        local_only: bool = False,
        max_tokens: int = 2000,
    ) -> ReasonResult:
        return ReasonResult(
            content="[Local reasoning for export smoke test]",
            confidence=0.7,
            model_used="none:test",
        )

    monkeypatch.setattr(ReasoningEngine, "reason", fake_reason)


def _post_query(client: TestClient, query: str):
    response = client.post("/api/query", json={"query": query, "eval_mode": True})
    assert response.status_code == 200
    body = response.json()
    assert body.get("type") == "result", body
    return body


def test_export_contains_data_after_activity(client: TestClient):
    client.post("/api/reflect/note", json={"note": "Marco is making progress on liaison sounds."})
    _post_query(client, "student name: Marco parent report progress report keep local")

    export = client.get("/api/profile/export").json()
    assert export["revision_log"], "expected the reflection note to appear in the export"
    assert export["traces"], "expected the query to leave a hashed trace"
    assert export["privacy_events"], "expected the private query to leave a privacy event"
    assert "students" in export and "filemap" in export


def test_export_has_no_raw_query_text(client: TestClient):
    _post_query(client, "student name: Marco parent report progress report keep local")
    export = client.get("/api/profile/export").json()
    dumped = str(export["traces"])
    assert "Marco" not in dumped


def test_export_then_clear_then_export_is_empty(client: TestClient):
    client.post("/api/reflect/note", json={"note": "a private teacher reflection"})
    _post_query(client, "how do I teach the passato prossimo")

    before = client.get("/api/profile/export").json()
    assert before["traces"] or before["revision_log"]

    cleared = client.post("/api/profile/clear", json={"confirm": "clear-all-data"})
    assert cleared.status_code == 200

    after = client.get("/api/profile/export").json()
    assert after["traces"] == []
    assert after["privacy_events"] == []
    assert after["revision_log"] == []
