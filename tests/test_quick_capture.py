"""Quick capture — Ctrl/Cmd+K (MC-lessons §7).

Desktop has no renderer views to hang a quick-capture command on (see
desktop/ — Electron shell only, no React/view layer), so quick capture lives
in static/index.html as a keyboard-triggered overlay that POSTs free text to
the existing /api/query endpoint. That endpoint already runs the full
governed pipeline (src/pipeline.py Step 0 EntryGate.scan(), unconditional
regardless of eval_mode), so quick capture gets the same privacy blocking as
the Ask flow for free — this test proves that guarantee holds for the exact
phrase gate3_sweep.sh uses to smoke-test the private-query path.

No browser/JS test runner exists in this repo, so the markup/wiring test
below asserts on the served HTML text directly, following the pattern of
other contract/markup-style tests in this suite (e.g. test_sw_surface_parity.py).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.lingua_viva.privacy_log import read_privacy_events
from src.web import app

REPO = Path(__file__).resolve().parent.parent
client = TestClient(app)

PRIVATE_QUERY = "student name: Marco parent report progress report keep local"


def test_quick_capture_markup_and_wiring_present():
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="qc-overlay"' in html
    assert 'id="qc-input"' in html
    assert 'id="qc-form"' in html
    # keyboard shortcut: Ctrl/Cmd+K opens, Escape closes
    assert "metaKey || event.ctrlKey" in html
    assert 'key === "escape"' in html
    # submits through the same governed endpoint as Ask
    assert "/api/query" in html
    assert "submitQuickCapture" in html
    assert "timeout_seconds: 1" in html
    assert "Captured as local trace" in html


def test_quick_capture_blocks_private_student_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy_events.ndjson"))
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))

    response = client.post(
        "/api/query",
        json={"query": PRIVATE_QUERY, "eval_mode": True, "timeout_seconds": 10},
    )

    assert response.status_code == 200
    events = read_privacy_events()
    assert any(e.event_type == "student_data_blocked" for e in events)
