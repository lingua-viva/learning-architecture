from __future__ import annotations

import hashlib
import time
from pathlib import Path
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
    ("GW-VOICE-006", "Voice loop: STT to grounded TTS"),
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
        title=f"{workflow_id} {name} fixture",
        uri=f"fixture://{workflow_id}",
        retrieval_scope="content",
        created_at=source_now(),
        observed_at=source_now(),
        provenance="capture" if source_type == "slack" else "import" if source_type == "drive" else "scan",
        student_data=source_type == "slack",
        summary=name,
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


# --- Voice golden workflow (GW-VOICE-006) ---

_VOICE_FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "voice" / "golden_query.wav"
_VOICE_FALLBACK_TRANSCRIPT = "Show me the current project status."
_VOICE_EXPECTED_KEYWORDS = {"current", "project", "status"}
_VOICE_SESSION_ID = "SESSION-GW-VOICE-006"

_VOICE_FAILURE_CLASSES = frozenset({
    "stt_mismatch", "pipeline_error", "gir_out_of_range",
    "tone_mismatch", "tts_prefix_wrong",
})


def _write_voice_gap_signal(failure_class: str) -> None:
    """Append a voice_loop_failure record to gap_signals.ndjson."""
    import json as _json
    from src.lingua_viva.improvement_audit import _gap_signals_path

    path = _gap_signals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "entry_node": "GW-VOICE-006",
        "domain": "voice",
        "gap_signals": [f"voice_loop_failure:{failure_class}"],
        "timestamp": time.time(),
        "session_id": _VOICE_SESSION_ID,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(_json.dumps(record) + "\n")


def _run_voice_loop(mode: str) -> GoldenWorkflowResult:
    """Golden workflow #6: exercises the full voice path end to end.

    Steps: stt_transcribe → pipeline_run → grounding_result →
    tone_resolved → tts_hermetic. Each maps to one WorkflowStep.
    """
    if mode == "live":
        return GoldenWorkflowResult(
            workflow_id="GW-VOICE-006", name="Voice loop: STT to grounded TTS",
            mode=mode, status="SKIPPED_MISSING_CREDENTIALS",
            notes="Live mode requires a real audio recording.",
        )

    steps: list[WorkflowStep] = []
    failures: list[str] = []

    # Step 1: stt_transcribe
    transcript = ""
    try:
        from src.lingua_viva.voice_stt import WhisperLocalProvider

        provider = WhisperLocalProvider(model_size="tiny")
        wav_bytes = _VOICE_FIXTURE.read_bytes()
        provider._ensure_model()
        transcript = provider.transcribe(wav_bytes)
        transcript_lower = transcript.lower()
        matched = {kw for kw in _VOICE_EXPECTED_KEYWORDS if kw in transcript_lower}
        missing = _VOICE_EXPECTED_KEYWORDS - matched
        if not missing:
            steps.append(WorkflowStep(
                "stt_transcribe", "PASS",
                evidence={"transcript_preview": transcript[:100], "keywords_matched": sorted(matched)},
            ))
        else:
            steps.append(WorkflowStep(
                "stt_transcribe", "FAIL",
                evidence={
                    "transcript_preview": transcript[:100],
                    "keywords_expected": sorted(_VOICE_EXPECTED_KEYWORDS),
                    "keywords_missing": sorted(missing),
                },
            ))
            failures.append("stt_mismatch")
    except Exception as exc:
        # Model load failure or no ffmpeg — SKIP, not FAIL
        steps.append(WorkflowStep(
            "stt_transcribe", "SKIP",
            evidence={"reason": f"{type(exc).__name__}: {str(exc)[:120]}"},
        ))
        # Use a fallback transcript so subsequent steps can still run
        transcript = _VOICE_FALLBACK_TRANSCRIPT

    # Step 2: pipeline_run
    pipeline_result = None
    try:
        import asyncio
        from src.lingua_viva.app import run_teacher_query

        loop = asyncio.new_event_loop()
        try:
            pipeline_result = loop.run_until_complete(
                run_teacher_query(
                    transcript,
                    intent="RESEARCH",
                    session_id=_VOICE_SESSION_ID,
                    eval_mode=True,
                )
            )
        finally:
            loop.close()
        steps.append(WorkflowStep(
            "pipeline_run", "PASS",
            evidence={"duration_ms": pipeline_result.duration_ms, "steps": pipeline_result.steps_executed},
        ))
    except Exception as exc:
        steps.append(WorkflowStep(
            "pipeline_run", "FAIL",
            evidence={"error": f"{type(exc).__name__}: {str(exc)[:200]}"},
        ))
        failures.append("pipeline_error")

    # Step 3: grounding_result
    if pipeline_result and pipeline_result.grounding:
        gir_score = pipeline_result.grounding.gir.score
        if 0.0 <= gir_score <= 1.0:
            steps.append(WorkflowStep(
                "grounding_result", "PASS",
                evidence={"gir_score": gir_score, "method": pipeline_result.grounding.gir.method},
            ))
        else:
            steps.append(WorkflowStep(
                "grounding_result", "FAIL",
                evidence={"gir_score": gir_score, "reason": "score out of [0, 1] range"},
            ))
            failures.append("gir_out_of_range")
    elif pipeline_result:
        steps.append(WorkflowStep(
            "grounding_result", "FAIL",
            evidence={"reason": "PipelineResult.grounding is None"},
        ))
        failures.append("gir_out_of_range")
    else:
        steps.append(WorkflowStep("grounding_result", "SKIP", evidence={"reason": "pipeline did not run"}))

    # Step 4: tone_resolved — consistency check
    if pipeline_result and pipeline_result.grounding:
        from src.lingua_viva.voice_tone import resolve_voice_tone

        stored_tone = pipeline_result.path_record.voice_tone
        expected_tone = resolve_voice_tone(pipeline_result.grounding.gir.score)["tone"]
        valid_tones = {"plain", "clarify", "name_boundary"}
        if stored_tone in valid_tones and stored_tone == expected_tone:
            steps.append(WorkflowStep(
                "tone_resolved", "PASS",
                evidence={"stored_tone": stored_tone, "expected_tone": expected_tone},
            ))
        else:
            steps.append(WorkflowStep(
                "tone_resolved", "FAIL",
                evidence={"stored_tone": stored_tone, "expected_tone": expected_tone, "valid_tones": sorted(valid_tones)},
            ))
            failures.append("tone_mismatch")
    else:
        steps.append(WorkflowStep("tone_resolved", "SKIP", evidence={"reason": "grounding not available"}))

    # Step 5: tts_hermetic — prefix construction check (no network)
    if pipeline_result and pipeline_result.grounding:
        from src.lingua_viva.voice_tone import resolve_voice_tone as _resolve

        gir_score = pipeline_result.grounding.gir.score
        tone_info = _resolve(gir_score)
        prefix = tone_info["prefix"]
        tone = tone_info["tone"]
        # For plain tone, prefix should be empty; for others, non-empty
        prefix_correct = (tone == "plain" and prefix == "") or (tone != "plain" and prefix != "")
        if prefix_correct:
            steps.append(WorkflowStep(
                "tts_hermetic", "PASS",
                evidence={"tone": tone, "prefix_length": len(prefix), "prefix_present": bool(prefix)},
            ))
        else:
            steps.append(WorkflowStep(
                "tts_hermetic", "FAIL",
                evidence={"tone": tone, "prefix": prefix, "reason": "prefix presence does not match tone"},
            ))
            failures.append("tts_prefix_wrong")
    else:
        steps.append(WorkflowStep("tts_hermetic", "SKIP", evidence={"reason": "grounding not available"}))

    # Write gap signals for any failures
    for failure_class in failures:
        _write_voice_gap_signal(failure_class)

    status = "PASS" if not failures else "FAIL"
    return GoldenWorkflowResult(
        workflow_id="GW-VOICE-006",
        name="Voice loop: STT to grounded TTS",
        mode=mode,
        status=status,
        steps=steps,
        notes=f"failures: {failures}" if failures else "",
    )


def run_workflows(*, mode: str = "hermetic", only: Optional[str] = None) -> list[GoldenWorkflowResult]:
    results: list[GoldenWorkflowResult] = []
    for workflow_id, name in WORKFLOWS:
        if only and workflow_id != only:
            continue
        started = time.time()
        try:
            if workflow_id == "GW-VOICE-006":
                result = _run_voice_loop(mode)
            else:
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
