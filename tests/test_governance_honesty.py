from __future__ import annotations

from src.lingua_viva import governance
from src.lingua_viva.privacy_log import log_event
from src.lingua_viva.traces import append_trace, new_trace


def test_governance_honesty_passes_when_ledgers_match(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_EXPORT_SIGNING_KEY_PATH", str(tmp_path / "signing_key"))

    log_event("query_processed_locally")
    log_event("external_call_made")
    append_trace(new_trace("public curriculum query", external_calls=1, route="external"))

    result = governance.check_governance_honesty()

    assert result["status"] == "PASS"
    assert result["activity"] == "RECORDED"
    assert result["privacy_log_non_empty"] is True
    assert result["signed_pack_verifies"] is True


def test_governance_honesty_catches_external_trace_under_report(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_EXPORT_SIGNING_KEY_PATH", str(tmp_path / "signing_key"))

    log_event("query_processed_locally")
    append_trace(new_trace("public curriculum query", external_calls=1, route="external"))

    result = governance.check_governance_honesty()

    assert result["status"] == "FAIL"
    assert any(item["id"] == "external_trace_under_reported" for item in result["findings"])


def test_governance_honesty_fresh_install_reports_no_activity(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_EXPORT_SIGNING_KEY_PATH", str(tmp_path / "signing_key"))

    result = governance.check_governance_honesty()

    assert result["status"] == "PASS"
    assert result["activity"] == "NO_ACTIVITY"
    assert result["privacy_log_exists"] is False
