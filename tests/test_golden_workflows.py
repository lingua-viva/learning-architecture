from __future__ import annotations

from src.lingua_viva.golden_workflows.runner import run_workflows


def test_golden_workflows_run_hermetically(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    results = run_workflows(mode="hermetic")
    assert len(results) == 5
    assert all(result.status == "PASS" for result in results)
    assert all("audit_receipt_id" in result.contract_ids for result in results)
