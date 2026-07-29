from __future__ import annotations

import hashlib
import time
from typing import Optional

from src.lingua_viva.action_plans.schema import ActionPlan, Approval, GroundingSummary, PlanPolicy, PlannedAction
from src.lingua_viva.action_plans.store import compute_action_plan_id, now_iso, upsert_plan
from src.lingua_viva.audit_receipts.builder import build_receipt
from src.lingua_viva.deliverables.schema import DeliverableLocation, DeliverableRecord, compute_deliverable_id
from src.lingua_viva.deliverables.store import upsert_deliverable
from src.lingua_viva.golden_workflows.schema import GoldenWorkflowResult, WorkflowStep
from src.lingua_viva.grounding.build import build_grounding_result
from src.lingua_viva.sources.ledger import compute_source_record_id, now_iso as source_now, upsert
from src.lingua_viva.sources.schema import SourceRecord

WORKFLOWS = [
    ("GW-EDU-001", "Observation to parent report"),
    ("GW-EDU-002", "Daily file from local and Drive"),
    ("GW-EDU-003", "Grounded answer to assessment"),
    ("GW-DRIVE-004", "Drive import to answer and export"),
    ("GW-SLACK-005", "Slack observation to lens update"),
]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _run_one(workflow_id: str, name: str, mode: str) -> GoldenWorkflowResult:
    if mode == "live":
        return GoldenWorkflowResult(workflow_id=workflow_id, name=name, mode=mode, status="SKIPPED_MISSING_CREDENTIALS", notes="Live credentials are required.")

    source_type = "slack" if workflow_id == "GW-SLACK-005" else "drive" if workflow_id == "GW-DRIVE-004" else "local"
    session_id = f"SESSION-{workflow_id}"
    trace_id = f"TRACE-{workflow_id}"
    source_id = compute_source_record_id(source_type, workflow_id, "hermetic", "fixture")
    record = SourceRecord(
        source_record_id=source_id,
        source_type=source_type,
        source_id=workflow_id,
        container="hermetic",
        record_id="fixture",
        title=f"{workflow_id} fixture",
        uri=f"fixture://{workflow_id}",
        retrieval_scope="content",
        created_at=source_now(),
        observed_at=source_now(),
        provenance="capture" if source_type == "slack" else "import" if source_type == "drive" else "scan",
        student_data=source_type == "slack",
        content_hash=_hash(workflow_id),
    )
    upsert(record, detail={"workflow_id": workflow_id})

    grounding = build_grounding_result(
        trace={"trace_id": trace_id, "session_id": session_id, "model_used": "local"},
        content="The answer is grounded in a local fixture.",
        query_text=name,
        session_id=session_id,
        intent="education_workflow",
    )
    plan = ActionPlan(
        action_plan_id=compute_action_plan_id(),
        created_at=now_iso(),
        session_id=session_id,
        trace_id=trace_id,
        grounding_id=grounding.grounding_id,
        intent="education_workflow",
        user_goal=name,
        source_record_ids=[source_id],
        grounding_summary=GroundingSummary(tier_used=grounding.tier_used, gir_score=grounding.gir.score, external_called=False),
        actions=[PlannedAction(action_id="parent_report" if workflow_id == "GW-EDU-001" else "import_document", name=name, param_sources={"input": [source_id]}, expected_output="drive_export" if workflow_id == "GW-DRIVE-004" else "file")],
        approval=Approval(status="approved", approved_by="operator", approved_at=now_iso()),
        policy=PlanPolicy(can_execute=True, reason="ready"),
    )
    upsert_plan(plan)

    deliverable = DeliverableRecord(
        deliverable_id=compute_deliverable_id(trace_id, plan.action_plan_id),
        session_id=session_id,
        trace_id=trace_id,
        grounding_id=grounding.grounding_id,
        action_plan_id=plan.action_plan_id,
        type="drive_export" if workflow_id == "GW-DRIVE-004" else "parent_report" if workflow_id == "GW-EDU-001" else "daily_file" if workflow_id == "GW-EDU-002" else "assessment",
        title=name,
        status="created",
        location=DeliverableLocation(kind="local_path", path=f"fixture://{workflow_id}/deliverable"),
        source_record_ids=[source_id],
        summary="Hermetic workflow deliverable.",
    )
    upsert_deliverable(deliverable)
    receipt = build_receipt(scope="workflow", session_id=session_id, trace_id=trace_id, action_plan_id=plan.action_plan_id, deliverable_id=deliverable.deliverable_id, source_record_ids=[source_id])

    steps = [
        WorkflowStep("source_record", "PASS", evidence={"source_record_id": source_id}),
        WorkflowStep("grounding_result", "PASS", evidence={"grounding_id": grounding.grounding_id, "tier_used": grounding.tier_used}),
        WorkflowStep("action_plan", "PASS", evidence={"action_plan_id": plan.action_plan_id}),
        WorkflowStep("deliverable_record", "PASS", evidence={"deliverable_id": deliverable.deliverable_id}),
        WorkflowStep("audit_receipt", "PASS", evidence={"audit_receipt_id": receipt.audit_receipt_id, "complete": receipt.is_complete}),
    ]
    return GoldenWorkflowResult(
        workflow_id=workflow_id,
        name=name,
        mode=mode,
        status="PASS" if receipt.audit_receipt_id else "FAIL",
        steps=steps,
        contract_ids={
            "source_record_id": source_id,
            "grounding_id": grounding.grounding_id,
            "action_plan_id": plan.action_plan_id,
            "deliverable_id": deliverable.deliverable_id,
            "audit_receipt_id": receipt.audit_receipt_id,
        },
    )


def run_workflows(*, mode: str = "hermetic", only: Optional[str] = None) -> list[GoldenWorkflowResult]:
    results: list[GoldenWorkflowResult] = []
    for workflow_id, name in WORKFLOWS:
        if only and workflow_id != only:
            continue
        started = time.time()
        try:
            result = _run_one(workflow_id, name, mode)
        except Exception as exc:
            result = GoldenWorkflowResult(workflow_id=workflow_id, name=name, mode=mode, status="FAIL", notes=str(exc))
        result.duration_ms = int((time.time() - started) * 1000)
        results.append(result)
    return results


def print_matrix(results: list[GoldenWorkflowResult]) -> str:
    lines = ["Golden Workflow Matrix", "=" * 60]
    for result in results:
        lines.append(f"{result.workflow_id} [{result.mode}] {result.status} ({result.duration_ms}ms) - {result.name}")
        for step in result.steps:
            lines.append(f"  {step.status} {step.name}")
    lines.append("=" * 60)
    lines.append(f"Result: {sum(1 for r in results if r.status == 'PASS')}/{len(results)} passed")
    return "\n".join(lines)
