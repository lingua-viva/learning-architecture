"""Routes for the sources ledger + knowledge library (routers/sources.py).

Auth default is off (LV_AUTH_MODE unset → permissive local context), so all
routes must work unauthenticated. Synthetic fixture data only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.lingua_viva import library
from src.lingua_viva.sources.ledger import compute_source_record_id, now_iso, upsert
from src.lingua_viva.sources.schema import SourceRecord
from src.web import app

client = TestClient(app)


@pytest.fixture()
def lv_state(monkeypatch, tmp_path):
    state = tmp_path / "lv-state"
    monkeypatch.setenv("LV_STATE_HOME", str(state))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_SANITIZER_DATA_DIR", str(tmp_path / "sanitizer-data"))
    return state


def _record(record_id: str = "doc-1", title: str = "G3 curriculum map") -> SourceRecord:
    now = now_iso()
    return SourceRecord(
        source_record_id=compute_source_record_id("local", "local", "curriculum", record_id),
        source_type="local",
        source_id="local",
        container="curriculum",
        record_id=record_id,
        title=title,
        uri=f"/synthetic/{record_id}.md",
        retrieval_scope="metadata",
        created_at=now,
        observed_at=now,
        provenance="scan",
    )


def test_get_sources_records_and_observations(lv_state):
    record, _changed = upsert(_record())

    resp = client.get("/api/sources/records")
    assert resp.status_code == 200
    body = resp.json()
    assert body["initialized"] is True
    assert body["counts"] == {"local": 1}
    assert any(r["source_record_id"] == record.source_record_id for r in body["records"])

    obs = client.get("/api/sources/observations", params={"source_record_id": record.source_record_id})
    assert obs.status_code == 200
    events = obs.json()["observations"]
    assert events and events[0]["source_record_id"] == record.source_record_id


def test_get_sources_records_filters(lv_state):
    upsert(_record("doc-a", title="Assessment ladder"))
    upsert(_record("doc-b", title="Reggio provocation bank"))

    resp = client.get("/api/sources/records", params={"q": "reggio", "limit": 5})
    assert resp.status_code == 200
    records = resp.json()["records"]
    assert len(records) == 1
    assert records[0]["title"] == "Reggio provocation bank"


def test_post_sources_record_and_observation(lv_state):
    resp = client.post("/api/sources/records", json={
        "source_type": "local",
        "container": "reference",
        "record_id": "safeguarding-ref",
        "title": "Safeguarding reference pack",
        "uri": "/synthetic/safeguarding.pdf",
        "provenance": "import",
    })
    assert resp.status_code == 200
    stored = resp.json()["record"]
    assert stored["source_record_id"].startswith("SRC-")
    assert resp.json()["changed"] is True

    obs = client.post("/api/sources/observations", json={
        "source_record_id": stored["source_record_id"],
        "event": "seen",
    })
    assert obs.status_code == 200
    assert obs.json()["observation"]["event"] == "seen"

    missing = client.post("/api/sources/records", json={})
    assert missing.status_code == 422


def test_library_status_and_search_routes(lv_state, tmp_path):
    doc = tmp_path / "unit.md"
    doc.write_text(
        "# Unit planner\n\nCentral idea and lines of inquiry for the unit of "
        "inquiry, mapped to the programme of inquiry.\n",
        encoding="utf-8",
    )
    added = client.post("/api/library/add", json={"path": str(doc)})
    assert added.status_code == 200
    doc_id = added.json()["doc"]["doc_id"]

    status = client.get("/api/library/status")
    assert status.status_code == 200
    assert status.json()["doc_count"] == 1

    found = client.get("/api/library/search", params={"q": "central idea"})
    assert found.status_code == 200
    results = found.json()["results"]
    assert results and results[0]["doc_id"] == doc_id

    by_category = client.get("/api/library/search", params={"category": "curriculum"})
    assert by_category.status_code == 200
    assert any(r["doc_id"] == doc_id for r in by_category.json()["results"])

    empty = client.get("/api/library/search", params={"q": "zzz-no-such-tokens"})
    assert empty.status_code == 200
    assert empty.json()["results"] == []


def test_library_add_route_error_paths(lv_state, tmp_path):
    assert client.post("/api/library/add", json={}).status_code == 422
    assert client.post(
        "/api/library/add", json={"path": str(tmp_path / "missing.md")}
    ).status_code == 404


def test_research_route_fail_closed_by_default(lv_state, monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("LV_ALLOW_RESEARCH", raising=False)
    resp = client.post("/api/library/research", json={"query": "anything", "dry_run": True})
    assert resp.status_code == 403
    assert resp.json()["enabled"] is False


def test_research_route_dry_run_when_enabled(lv_state, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LV_ALLOW_RESEARCH", "1")
    resp = client.post(
        "/api/library/research",
        json={"query": "IB PYP assessment rubric examples", "dry_run": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["doc"]["source"] == "perplexity"
    assert library.status()["by_source"] == {"perplexity": 1}
