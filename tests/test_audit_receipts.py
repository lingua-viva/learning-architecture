from __future__ import annotations

from src.lingua_viva.action_plans.schema import ActionPlan, Approval, GroundingSummary, PlannedAction
from src.lingua_viva.action_plans.store import now_iso, upsert_plan
from src.lingua_viva.audit_receipts.builder import build_receipt, sanitize_student_text
from src.lingua_viva.deliverables.schema import DeliverableRecord
from src.lingua_viva.deliverables.store import upsert_deliverable
from src.lingua_viva.sources.ledger import compute_source_record_id, now_iso as source_now, upsert
from src.lingua_viva.sources.schema import SourceRecord


def test_audit_receipt_joins_without_exporting_student_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    observed_at = source_now()
    sid = compute_source_record_id("slack", "channel", "teacher", "student:Marco")
    upsert(SourceRecord(
        source_record_id=sid,
        source_type="slack",
        source_id="channel",
        container="teacher",
        record_id="student:Marco",
        title="Observation",
        uri="slack://channel/message",
        retrieval_scope="metadata",
        created_at=observed_at,
        observed_at=observed_at,
        provenance="capture",
        student_data=True,
    ))
    plan = ActionPlan(
        action_plan_id="APL-1",
        created_at=now_iso(),
        trace_id="TRACE-1",
        grounding_id="GRD-1",
        source_record_ids=[sid],
        grounding_summary=GroundingSummary(tier_used="slack", gir_score=1.0),
        actions=[PlannedAction(action_id="parent_report")],
        approval=Approval(status="approved", approved_by="Teacher Name", approved_at=now_iso()),
    )
    upsert_plan(plan)
    upsert_deliverable(DeliverableRecord(deliverable_id="DLV-1", action_plan_id="APL-1", source_record_ids=[sid], type="parent_report"))
    receipt = build_receipt(scope="workflow", session_id="S1", trace_id="TRACE-1", action_plan_id="APL-1", deliverable_id="DLV-1", source_record_ids=[sid])
    payload = receipt.as_dict()
    assert payload["privacy"]["student_identifiers_exported"] is False
    assert sid not in payload["source_record_ids"]
    assert "Teacher Name" not in str(payload)


def test_sanitize_student_text_redacts_names_and_ids():
    text = sanitize_student_text("student_id Marco-7 met Maria Rossi today")
    assert "Marco-7" not in text
    assert "Maria Rossi" not in text
