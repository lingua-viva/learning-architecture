import json
from types import SimpleNamespace

from src.codex_adapter import (
    CodexEnvelopeStore,
    infer_files_to_read,
    sanitize_source_query,
    summarize_results,
    task_envelope_from_pipeline_result,
)


def fake_pipeline_result(blocks_external=False, gap_signals=None):
    classification = SimpleNamespace(
        riu_id="RIU-029",
        name="Tool-Calling Safety Envelope",
        domain="ai-enablement",
        confidence=0.72,
        default_intent="CREATE",
        signals_matched=["codex", "adapter"],
        blocks_external=blocks_external,
        requires_local=True,
    )
    path_record = SimpleNamespace(
        knowledge_entries_used=["LIB-138", "LIB-160"],
        entry_node="RIU-029",
        path=["RIU-029", "SCAN", "CLASSIFY", "STORE"],
        query_hash="abc123",
    )
    return SimpleNamespace(
        classification=classification,
        path_record=path_record,
        gap_signals=gap_signals or [],
        steps_executed=["SCAN", "CLASSIFY", "RETRIEVE", "STORE"],
        session_id="session-1",
        query_hash="abc123",
        external_called=False,
        duration_ms=42,
    )


def test_sanitize_source_query_redacts_pii():
    safe = sanitize_source_query("Email jane@example.com about server.mjs")
    assert "jane@example.com" not in safe
    assert "[REDACTED_EMAIL]" in safe


def test_sanitize_source_query_blocks_external_without_raw_fallback():
    safe = sanitize_source_query("Generic task", blocks_external=True)
    assert safe == "[SENSITIVE_QUERY_BLOCKED]"


def test_infer_files_to_read():
    files = infer_files_to_read("Patch peers/hub/server.mjs and src/gateway/sanitizer.py.")
    assert "peers/hub/server.mjs" in files
    assert "src/gateway/sanitizer.py" in files


def test_task_envelope_policy_blocks_external_on_entry_gate_signal():
    result = fake_pipeline_result(gap_signals=["entry_gate_blocked:privileged"])
    envelope = task_envelope_from_pipeline_result(
        query="Implement src/foo.py",
        requested_intent="CREATE",
        result=result,
    )
    assert envelope["classification"]["riu"] == "RIU-029"
    assert envelope["policy"]["external_allowed"] is False
    assert envelope["policy"]["models_allowed"] == ["codex"]
    assert envelope["context"]["knowledge_entries"] == ["LIB-138", "LIB-160"]


def test_store_writes_task_and_result(tmp_path):
    store = CodexEnvelopeStore(data_dir=tmp_path)
    envelope = task_envelope_from_pipeline_result(
        query="Implement src/foo.py",
        requested_intent="CREATE",
        result=fake_pipeline_result(),
    )
    store.write_task(envelope)
    assert store.find_task(envelope["task_id"])["objective"] == "Implement src/foo.py"

    record = store.write_result({
        "task_id": envelope["task_id"],
        "status": "completed",
        "patches": [{"file": "src/foo.py"}],
        "commands_run": ["python3 -m pytest"],
        "test_results": {"passed": 1, "failed": 0},
        "decision": "Implemented the change",
    })
    assert record["recorded_at"]
    summary = summarize_results(store.list_results())
    assert envelope["task_id"] in summary
    assert "completed" in summary


def test_write_result_rejects_malformed_envelope(tmp_path):
    import pytest
    store = CodexEnvelopeStore(data_dir=tmp_path)

    # Missing status
    with pytest.raises(ValueError, match="status"):
        store.write_result({"task_id": "TASK-001"})

    # Invalid status value
    with pytest.raises(ValueError, match="status"):
        store.write_result({"task_id": "TASK-001", "status": "maybe"})

    # Missing patches
    with pytest.raises(ValueError, match="patches"):
        store.write_result({"task_id": "TASK-001", "status": "completed"})

    # Missing test_results
    with pytest.raises(ValueError, match="test_results"):
        store.write_result({"task_id": "TASK-001", "status": "completed", "patches": []})

    # Missing decision
    with pytest.raises(ValueError, match="decision"):
        store.write_result({"task_id": "TASK-001", "status": "completed", "patches": [], "test_results": {"passed": 0, "failed": 0}})


def test_write_result_rejects_unknown_task_id(tmp_path):
    """Result for a non-existent task must be rejected."""
    import pytest
    store = CodexEnvelopeStore(data_dir=tmp_path)
    with pytest.raises(ValueError, match="not found"):
        store.write_result({
            "task_id": "TASK-NONEXISTENT",
            "status": "completed",
            "patches": [],
            "test_results": {"passed": 1, "failed": 0},
            "decision": "done",
        })


def test_policy_compliance_blocks_external(tmp_path):
    """If policy forbids external, result reporting external use is rejected."""
    import pytest
    store = CodexEnvelopeStore(data_dir=tmp_path)
    envelope = task_envelope_from_pipeline_result(
        query="test",
        requested_intent="CREATE",
        result=fake_pipeline_result(blocks_external=True),
    )
    store.write_task(envelope)

    # Self-reporting external use → rejected
    with pytest.raises(ValueError, match="POLICY VIOLATION"):
        store.write_result({
            "task_id": envelope["task_id"],
            "status": "completed",
            "patches": [],
            "test_results": {"passed": 1, "failed": 0},
            "decision": "done",
            "external_called": True,
        })

    # Commands containing external indicators → rejected
    with pytest.raises(ValueError, match="POLICY VIOLATION"):
        store.write_result({
            "task_id": envelope["task_id"],
            "status": "completed",
            "patches": [],
            "test_results": {"passed": 1, "failed": 0},
            "decision": "done",
            "commands_run": ["curl https://api.openai.com/v1/chat"],
        })


def test_policy_compliance_allows_local(tmp_path):
    """If policy forbids external but result is local-only, it passes."""
    store = CodexEnvelopeStore(data_dir=tmp_path)
    envelope = task_envelope_from_pipeline_result(
        query="test",
        requested_intent="CREATE",
        result=fake_pipeline_result(blocks_external=True),
    )
    store.write_task(envelope)

    # Local-only result → accepted
    record = store.write_result({
        "task_id": envelope["task_id"],
        "status": "completed",
        "patches": [{"file": "test.py", "diff": "+pass"}],
        "test_results": {"passed": 3, "failed": 0},
        "decision": "Implemented locally with Ollama",
        "commands_run": ["python -m pytest"],
        "external_called": False,
    })
    assert record["recorded_at"]
