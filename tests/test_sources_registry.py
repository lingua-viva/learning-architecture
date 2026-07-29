"""Unified source registry and answer provenance — Slice 1.

Spec: dev/SPEC_UNIFIED_SOURCES_WORKBENCH_2026-07-28.md §Lingua Viva.

Two things are load-bearing here:

1. **Per-source degradation.** The registry exists to tell a teacher what
   Lingua Viva can currently see. If Drive is down, the local-folder count
   must still be right, and the Drive row must say "could not read" rather
   than "0" — a zero is a claim, an error is a fact.

2. **Provenance is measured, not asserted.** `route`, `external_calls` and
   `external_called` were hardcoded to local/0 in the query response, in
   new_trace() at write time, AND in read_traces() at read time. The Why view
   could therefore only ever report "local", true or not. That is receipt
   decay (AGENTS.md lagging indicator #4) and it is now derived from the
   model that actually answered.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.lingua_viva.traces import ReasoningTrace, new_trace

client = TestClient(web.app)


# --- registry --------------------------------------------------------------


def test_registry_lists_every_source_with_a_real_status():
    payload = client.get("/api/sources/status").json()
    ids = {source["id"] for source in payload["sources"]}
    assert ids == {"local", "drive", "slack"}
    for source in payload["sources"]:
        assert source["status"] in {"connected", "not_configured", "unavailable"}
        assert source["label"]
        assert source["detail"]


def test_registry_counts_connected_sources():
    payload = client.get("/api/sources/status").json()
    expected = sum(1 for s in payload["sources"] if s["status"] == "connected")
    assert payload["connected_count"] == expected
    assert payload["total_count"] == len(payload["sources"])


def test_one_broken_source_does_not_blank_the_others(monkeypatch):
    """A Drive outage must not take the local-folder count with it."""
    import src.lingua_viva.google_drive_integration as drive

    def boom():
        raise RuntimeError("drive is unreachable")

    monkeypatch.setattr(drive, "status", boom)

    payload = client.get("/api/sources/status").json()
    rows = {source["id"]: source for source in payload["sources"]}

    assert rows["drive"]["status"] == "unavailable"
    # An unreadable source reports None, never 0 — a zero would be a claim.
    assert rows["drive"]["count"] is None
    assert rows["local"]["status"] in {"connected", "not_configured"}
    assert rows["slack"]["status"] in {"connected", "not_configured"}


def test_registry_reports_excluded_student_zones():
    payload = client.get("/api/sources/status").json()
    assert "student_zones_excluded" in payload
    assert payload["student_zone_note"]
    local = next(s for s in payload["sources"] if s["id"] == "local")
    assert "student_zones_excluded" in local


# --- provenance receipts ---------------------------------------------------


def test_new_trace_records_the_route_it_is_given():
    trace = new_trace("q", model_used="openai/gpt-4o", external_calls=1, route="external")
    assert trace.external_calls == 1
    assert trace.route == "external"


def test_new_trace_infers_route_from_the_call_count():
    assert new_trace("q", external_calls=1).route == "external"
    assert new_trace("q", external_calls=0).route == "local"


def test_read_traces_does_not_rewrite_history(tmp_path, monkeypatch):
    """The regression that made the Why view unable to report anything but
    'local': read_traces() overwrote both fields on every read."""
    import json

    from dataclasses import asdict

    from src.lingua_viva.traces import read_traces

    path = tmp_path / "traces.ndjson"
    monkeypatch.setenv("LV_TRACE_PATH", str(path))
    recorded = new_trace("q", model_used="openai/gpt-4o", external_calls=1, route="external")
    path.write_text(json.dumps(asdict(recorded)) + "\n", encoding="utf-8")

    loaded = read_traces(limit=10)
    assert loaded[0].route == "external"
    assert loaded[0].external_calls == 1


def test_read_traces_tolerates_older_records_without_the_fields(tmp_path, monkeypatch):
    import json

    from src.lingua_viva.traces import read_traces

    path = tmp_path / "traces.ndjson"
    monkeypatch.setenv("LV_TRACE_PATH", str(path))
    legacy = {
        "trace_id": "t1",
        "timestamp": "2026-07-28T00:00:00+00:00",
        "query_hash": "abc",
        "classification_domain": "education",
        "model_used": "qwen2.5:3b",
        "duration_ms": 10,
        "token_count": 0,
    }
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    loaded = read_traces(limit=10)
    assert loaded[0].route == "local"
    assert loaded[0].external_calls == 0


def test_query_response_reports_the_route_it_actually_used(monkeypatch):
    """Non-student query answered by a cloud model must not claim 'local'."""
    import src.lingua_viva.reasoning as native

    monkeypatch.setattr(
        native.ReasoningEngine, "_is_external_model", staticmethod(lambda model: True)
    )
    response = client.post(
        "/api/query",
        json={"query": "What are good warm up activities?", "eval_mode": True},
    ).json()

    if response.get("type") == "result":
        assert response["route"] == "external"
        assert response["pipeline"]["external_called"] is True
        assert response["external_calls"] == 1


def test_query_response_carries_sources_for_provenance():
    response = client.post(
        "/api/query", json={"query": "What are good warm up activities?", "eval_mode": True}
    ).json()
    if response.get("type") == "result":
        assert isinstance(response.get("sources"), list)


# --- the UI actually calls all of this -------------------------------------


def test_sources_view_renders_the_registry():
    body = client.get("/").text
    assert "renderSourceRegistry()" in body, "registry never called from renderSources"
    assert 'id="sources-registry"' in body
    assert 'api("/api/sources/status")' in body
    assert "excluded from AI processing" in body, "student-zone badge missing"


def test_ask_no_longer_defaults_the_route_badge_to_local():
    """`message.meta.route || "local"` rendered a guarantee whenever the field
    was absent. An unrecorded route must read as unrecorded."""
    body = client.get("/").text
    assert 'escapeHtml(message.meta.route || "local")' not in body
    assert "route not recorded" in body
    assert "answered by a cloud model" in body
