from src.lingua_viva.privacy import redact_runtime_text
from src.lingua_viva.privacy_log import log_event, privacy_log_path, privacy_summary, read_privacy_events


def _privacy_store(monkeypatch, tmp_path):
    path = tmp_path / "privacy.ndjson"
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(path))
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))
    return path


def test_privacy_event_logged_on_student_block(monkeypatch, tmp_path):
    _privacy_store(monkeypatch, tmp_path)

    redacted = redact_runtime_text("student name: Marco")

    events = read_privacy_events()
    assert "[REDACTED_PRIVATE_CONTEXT]" in redacted
    assert events
    assert events[0].event_type == "student_data_blocked"


def test_privacy_summary_counts(monkeypatch, tmp_path):
    _privacy_store(monkeypatch, tmp_path)
    log_event("query_processed_locally")
    log_event("student_data_blocked")
    log_event("ai_attribution_stripped")

    summary = privacy_summary()

    assert summary["total_queries_local"] == 1
    assert summary["student_blocks"] == 1
    assert summary["ai_attribution_stripped"] == 1
    assert summary["external_calls"] == 0
    assert summary["docx_modifications"] == 0


def test_privacy_log_never_contains_student_names(monkeypatch, tmp_path):
    path = _privacy_store(monkeypatch, tmp_path)

    redact_runtime_text("student name: Marco")

    assert "Marco" not in path.read_text(encoding="utf-8")
    assert "student name:" not in path.read_text(encoding="utf-8")


def test_external_calls_always_zero(monkeypatch, tmp_path):
    _privacy_store(monkeypatch, tmp_path)
    log_event("query_processed_locally")

    assert privacy_summary()["external_calls"] == 0
    assert privacy_log_path().stat().st_mode & 0o777 == 0o600
