from __future__ import annotations

import hashlib
import re

from src.lingua_viva.audit_receipts.schema import AuditReceipt, compute_receipt_id

_STUDENT_ID_RE = re.compile(r"\b(?:student[_ -]?id|student|child|pupil)[:= ]+[A-Za-z0-9_-]+\b", re.IGNORECASE)
_NAME_HINT_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
LOCAL_EVIDENCE_SCOPES = {"help_artifact", "portfolio_entry", "cohort_lesson_plan"}


def sanitize_student_text(value: str) -> str:
    text = _STUDENT_ID_RE.sub("student_ref:[redacted]", value or "")
    text = _NAME_HINT_RE.sub("[redacted-name]", text)
    return text


def _safe_ids(values: list[str]) -> list[str]:
    return [hashlib.sha256(str(v).encode()).hexdigest()[:16] for v in values if v]


def build_receipt(
    *,
    scope: str = "query",
    session_id: str = "",
    trace_id: str = "",
    action_plan_id: str = "",
    deliverable_id: str = "",
    grounding_id: str = "",
    source_record_ids: list[str] | None = None,
    export_format: str = "json",
    export_path: str = "",
    previous_receipt_sha256: str = "",
) -> AuditReceipt:
    missing: list[str] = []
    trace_ids = [trace_id] if trace_id else []
    source_ids = list(source_record_ids or [])
    grounding_ids = [grounding_id] if grounding_id else []
    action_plan_ids: list[str] = []
    deliverable_ids: list[str] = []
    routing = {"tier_used": "none", "external_called": False, "route_reason": "local_first_policy"}
    approval = {"required": False, "status": "not_required", "approved_by_hash": "", "approved_at": ""}

    if action_plan_id:
        try:
            from src.lingua_viva.action_plans.store import read_plan

            plan = read_plan(action_plan_id)
        except Exception:
            plan = None
        if plan is None:
            missing.append("action_plan_id")
        else:
            action_plan_ids.append(plan.action_plan_id)
            trace_ids = trace_ids or ([plan.trace_id] if plan.trace_id else [])
            if plan.grounding_id and plan.grounding_id not in grounding_ids:
                grounding_ids.append(plan.grounding_id)
            for sid in plan.source_record_ids:
                if sid not in source_ids:
                    source_ids.append(sid)
            routing = {
                "tier_used": plan.grounding_summary.tier_used,
                "external_called": bool(plan.grounding_summary.external_called),
                "route_reason": plan.policy.reason,
            }
            approval = {
                "required": plan.approval.status != "not_required",
                "status": plan.approval.status,
                "approved_by_hash": hashlib.sha256(plan.approval.approved_by.encode()).hexdigest()[:16] if plan.approval.approved_by else "",
                "approved_at": plan.approval.approved_at,
            }

    if deliverable_id or action_plan_id:
        try:
            from src.lingua_viva.deliverables.store import read_deliverable, read_deliverables

            deliverable = read_deliverable(deliverable_id) if deliverable_id else None
            if deliverable is None and action_plan_id:
                rows = read_deliverables(action_plan_id=action_plan_id, limit=1)
                deliverable = rows and __import__(
                    "src.lingua_viva.deliverables.schema", fromlist=["DeliverableRecord"]
                ).DeliverableRecord.from_dict(rows[0])
        except Exception:
            deliverable = None
        if deliverable is None and deliverable_id:
            missing.append("deliverable_id")
        elif deliverable is not None:
            deliverable_ids.append(deliverable.deliverable_id)
            for sid in deliverable.source_record_ids:
                if sid not in source_ids:
                    source_ids.append(sid)

    if source_ids:
        if scope not in LOCAL_EVIDENCE_SCOPES:
            try:
                from src.lingua_viva.sources.ledger import read_records

                existing = {r.get("source_record_id") for r in read_records(limit=1000)}
                if not any(sid in existing for sid in source_ids):
                    missing.append("source_record_ids")
            except Exception:
                missing.append("source_record_ids")
    elif scope != "query":
        missing.append("source_record_ids")

    receipt = AuditReceipt(
        audit_receipt_id=compute_receipt_id(session_id, trace_ids),
        scope=scope,
        session_id=session_id,
        trace_ids=trace_ids,
        source_record_ids=list(source_ids),
        grounding_ids=grounding_ids,
        action_plan_ids=action_plan_ids,
        deliverable_ids=deliverable_ids,
        missing_join_keys=missing,
        entry_gate={"blocked": False, "protect_forced_local": True, "sensitive_signal_hashes": []},
        routing=routing,
        egress={"allowed_hosts": [], "blocked_hosts": [], "sanitized_external_query_hash": ""},
        approval=approval,
        hash_chain={"previous_receipt_sha256": previous_receipt_sha256},
        export={"format": export_format, "path": sanitize_student_text(export_path)},
    )
    receipt.hash_chain["payload_sha256"] = receipt.compute_payload_hash()
    receipt.source_record_ids = _safe_ids(receipt.source_record_ids)
    return receipt
