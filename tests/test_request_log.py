"""Request-outcome log + zero-500 audit (MC-lessons §5).

MC could prove zero unhandled 500s across its full firewall history because
it had a longitudinal event log. LV's uvicorn ran with log_level="error" —
no request log at all. `src/lingua_viva/request_log.py` + the `_log_request_outcome`
middleware in src/web.py fix that; `lv health --full` gains a check that
fails on any logged 5xx.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src.lingua_viva.request_log import count_5xx, read_request_events, request_log_path
from src.web import app

client = TestClient(app)


def test_request_event_logged_with_path_template_not_raw_url():
    client.get("/api/curriculum/unit/g3-unit-1")
    events = read_request_events()
    assert events, "expected at least one logged request event"
    matching = [e for e in events if e.path_template == "/api/curriculum/unit/{unit_id}"]
    assert matching, f"expected a path-template entry, got: {[e.path_template for e in events]}"
    assert matching[-1].status == 200
    assert matching[-1].method == "GET"


def test_request_event_has_no_query_content():
    client.get("/api/curriculum/unit/g3-unit-1?x=some-secret-value")
    events = read_request_events()
    for event in events:
        assert "some-secret-value" not in event.path_template


def test_request_log_file_is_0600():
    client.get("/api/health")
    path = request_log_path()
    assert path.is_file()
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_count_5xx_zero_on_clean_traffic():
    client.get("/api/health")
    client.get("/api/session")
    assert count_5xx() == 0


def test_count_5xx_detects_server_errors():
    from src.lingua_viva.request_log import RequestEvent, append_request_event

    append_request_event("GET", "/api/does-not-exist-synthetic", 500)
    events = read_request_events()
    assert count_5xx(events) >= 1


def test_health_full_gains_server_5xx_check(monkeypatch, tmp_path):
    import argparse
    import subprocess as sp

    from src.lingua_viva import cli as lv_cli

    monkeypatch.setattr(sp, "run", lambda *a, **k: sp.CompletedProcess(a, 0, stdout="ok\n", stderr=""))
    monkeypatch.setattr(lv_cli, "run_doctor", lambda write_log=False: {"status": "OK"})
    monkeypatch.setattr(lv_cli, "_eval", lambda args: 0)

    result = lv_cli._full_health(argparse.Namespace(json=True))
    assert result == 0

    from src.lingua_viva.request_log import append_request_event
    append_request_event("GET", "/api/synthetic-failure", 500)
    result = lv_cli._full_health(argparse.Namespace(json=True))
    assert result == 1
