from __future__ import annotations

from pathlib import Path

from src.lingua_viva.defect_triage import (
    DefectEvidence,
    classify_failure,
    result_to_markdown,
    triage_gap_signal_record,
    triage_golden_workflow_result,
    triage_pytest_output,
)


def test_ui_contract_version_mismatch_is_checker_logic():
    result = classify_failure(
        "UI_CONTRACT FAIL: protected file changed without version bump. EXPECTED_VERSION is stale; hash drifted."
    )
    assert result.primary_layer == "checker_logic"
    assert result.confidence >= 0.5


def test_route_reachability_stale_expectation_is_checker_logic():
    result = classify_failure(
        DefectEvidence(
            failure_text="ROUTE_REACHABILITY stale route expectation for GET /api/cohort-plans; backend-only route not classified.",
            file_path="contracts/ROUTE_REACHABILITY.yaml",
        )
    )
    assert result.primary_layer == "checker_logic"


def test_low_classification_confidence_and_riu_mismatch_is_ontology_taxonomy():
    result = classify_failure(
        {
            "failure_text": "OntologyEngine produced ClassificationResult with low_classification_confidence and wrong riu_id",
            "riu_id": "RIU-WRONG",
            "domain": "education",
        }
    )
    assert result.primary_layer == "ontology_taxonomy"


def test_missing_citation_and_empty_retrieval_is_curriculum_source():
    result = classify_failure(
        "GIR failed because retrieval returned empty source chunks and missing citation from document_store."
    )
    assert result.primary_layer == "curriculum_source"


def test_provider_timeout_or_missing_credentials_is_live_layer_drift():
    result = classify_failure(
        "Google Drive provider timeout: SKIPPED_MISSING_CREDENTIALS and unavailable endpoint."
    )
    assert result.primary_layer == "live_layer_drift"


def test_preview_write_or_incomplete_audit_receipt_is_product_code():
    result = classify_failure(
        "Invariant failed: preview wrote deliverable and audit receipt incomplete after approval route returned wrong shape."
    )
    assert result.primary_layer == "product_code"


def test_common_underscore_failure_phrases_do_not_fall_to_unknown():
    receipt = classify_failure("audit_receipt incomplete for cohort_lesson_plan approval")
    voice = classify_failure("voice_loop_failure:tts_prefix_wrong")
    contract = classify_failure("tests/test_ui_contract.py AssertionError expected 84 == 85")

    assert receipt.primary_layer == "product_code"
    assert voice.primary_layer == "product_code"
    assert contract.primary_layer == "checker_logic"


def test_live_connector_word_does_not_override_local_route_invariant():
    result = classify_failure("Google Drive route returned 500 from src/web.py invariant wrong shape")

    assert result.primary_layer == "product_code"
    assert "live_layer_drift" in result.secondary_layers


def test_voice_loop_failure_classes_are_deterministic():
    stt = triage_gap_signal_record(
        {
            "entry_node": "GW-VOICE-006",
            "domain": "voice",
            "gap_signals": ["voice_loop_failure:stt_mismatch"],
        }
    )
    pipeline = triage_gap_signal_record(
        {
            "entry_node": "GW-VOICE-006",
            "domain": "voice",
            "gap_signals": ["voice_loop_failure:pipeline_error"],
        }
    )
    model_load = classify_failure("Whisper model-load failure while running voice loop.")
    assert stt.primary_layer == "live_layer_drift"
    assert pipeline.primary_layer == "product_code"
    assert model_load.primary_layer == "live_layer_drift"


def test_gap_signal_record_uses_entry_node_domain_and_signals():
    result = triage_gap_signal_record(
        {
            "entry_node": "node-x",
            "domain": "curriculum",
            "session_id": "S1",
            "gap_signals": ["no_knowledge_at_node:source_retrieval", "research_gap:missing_module"],
        }
    )
    assert result.primary_layer == "curriculum_source"
    assert "curriculum_source" in " ".join(result.reasons)


def test_golden_workflow_result_inspects_failed_steps():
    receipt_result = triage_golden_workflow_result(
        {
            "workflow_id": "GW-EDU-001",
            "status": "FAIL",
            "steps": [{"name": "audit_receipt", "status": "FAIL", "evidence": {"complete": False}}],
        }
    )
    source_result = triage_golden_workflow_result(
        {
            "workflow_id": "GW-EDU-003",
            "status": "FAIL",
            "steps": [{"name": "source_record", "status": "FAIL", "evidence": {"citation": ""}}],
        }
    )
    assert receipt_result.primary_layer == "product_code"
    assert source_result.primary_layer == "curriculum_source"


def test_pytest_output_with_multiple_failures_returns_multiple_results():
    text = """
________________________ test_ui_contract_check_passes ________________________
tests/test_ui_contract.py:197: AssertionError
E AssertionError: [ui-contract] FAIL: protected file changed without version bump: src/web.py
________________________ test_drive_live_timeout ________________________
tests/test_google_drive_app_integration.py:44: TimeoutError
E Google Drive credential timeout from provider
=========================== short test summary info ============================
FAILED tests/test_ui_contract.py::test_ui_contract_check_passes
FAILED tests/test_google_drive_app_integration.py::test_drive_live_timeout
"""
    results = triage_pytest_output(text)
    assert len(results) == 2
    assert results[0].primary_layer == "checker_logic"
    assert results[1].primary_layer == "live_layer_drift"


def test_unknown_or_empty_evidence_returns_low_confidence_unknown():
    result = classify_failure("")
    assert result.primary_layer == "unknown"
    assert result.confidence <= 0.1
    assert "Capture the full command output" in result.recommended_actions[0]


def test_markdown_contains_layer_confidence_reasons_and_next_actions():
    result = classify_failure("ROUTE_REACHABILITY hash mismatch")
    markdown = result_to_markdown(result)
    assert "Primary layer" in markdown
    assert "Confidence" in markdown
    assert "## Reasons" in markdown
    assert "## Next Actions" in markdown


def test_classifier_does_not_mutate_known_runtime_files(tmp_path, monkeypatch):
    gap = tmp_path / "gap_signals.ndjson"
    contract = tmp_path / "UI_CONTRACT.yaml"
    proposal_dir = tmp_path / "ontology" / "proposals"
    proposal = proposal_dir / "CAND-TEST.yaml"
    source = tmp_path / "sources.ndjson"
    proposal_dir.mkdir(parents=True)
    for path, content in (
        (gap, '{"gap_signals":["research_gap:x"]}\n'),
        (contract, "version: 1\n"),
        (proposal, "candidate_id: CAND-TEST\nhit_count: 1\n"),
        (source, '{"source_record_id":"SRC-1"}\n'),
    ):
        path.write_text(content, encoding="utf-8")
    before = {path: path.read_text(encoding="utf-8") for path in (gap, contract, proposal, source)}

    monkeypatch.setenv("LV_GAP_SIGNALS_PATH", str(gap))
    classify_failure("UI_CONTRACT route reachability low_classification_confidence missing citation provider timeout")
    triage_gap_signal_record({"entry_node": "n", "domain": "d", "gap_signals": ["research_gap:x"]})
    triage_golden_workflow_result({"workflow_id": "GW-EDU-001", "status": "FAIL", "steps": []})

    after = {path: path.read_text(encoding="utf-8") for path in (gap, contract, proposal, source)}
    assert after == before
