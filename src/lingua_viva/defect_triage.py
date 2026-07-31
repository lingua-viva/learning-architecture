from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

LAYERS = (
    "curriculum_source",
    "checker_logic",
    "ontology_taxonomy",
    "live_layer_drift",
    "product_code",
    "unknown",
)

RECOMMENDED_OWNERS = {
    "curriculum_source": "curriculum/source steward",
    "checker_logic": "test and contract owner",
    "ontology_taxonomy": "ontology/taxonomy owner",
    "live_layer_drift": "integration/environment owner",
    "product_code": "product module owner",
    "unknown": "operator triage",
}

RECOMMENDED_ACTIONS = {
    "curriculum_source": [
        "Inspect the source ledger, citations, document store, and retrieval results.",
        "Verify curriculum/source ingestion before changing product code or tests.",
    ],
    "checker_logic": [
        "Verify whether the product behavior changed intentionally.",
        "Update contract/version/checker expectations only with evidence; do not weaken coverage.",
    ],
    "ontology_taxonomy": [
        "Inspect the ontology node, RIU/domain route, candidate proposals, and learned weights.",
        "Correct taxonomy only after confirming product behavior and source availability.",
    ],
    "live_layer_drift": [
        "Verify credentials, provider availability, model load, and network-dependent environment.",
        "Compare with hermetic behavior before changing deterministic product code.",
    ],
    "product_code": [
        "Reproduce with a focused test and patch the smallest owning module.",
        "Add regression coverage for the violated invariant or route shape.",
    ],
    "unknown": [
        "Capture the full command output, traceback, route/workflow id, and relevant gap signals.",
        "Re-run with structured evidence before choosing an owning layer.",
    ],
}

PATTERNS: dict[str, tuple[str, ...]] = {
    "curriculum_source": (
        "source_record_id",
        "source ledger",
        "citation",
        "missing citation",
        "manuale v1 default citation",
        "gir",
        "grounding",
        "retrieval",
        "empty retrieval",
        "empty source chunks",
        "document_store",
        "document_retrieval",
        "document ingest",
        "document extraction",
        "source chunks",
        "research_gap",
    ),
    "checker_logic": (
        "ui_contract",
        "route_reachability",
        "expected_version",
        "hash mismatch",
        "hash drifted",
        "protected file changed",
        "contract protected",
        "stale expectation",
        "stale route",
        "brittle string",
        "expected old version",
        "golden expected",
        "assertion-only",
    ),
    "ontology_taxonomy": (
        "ontologyengine",
        "classificationresult",
        "riu_id",
        "entry_node",
        "unknown_domain",
        "low_classification_confidence",
        "weak_classification",
        "no_knowledge_at_node",
        "ontology/proposals/cand-",
        "cand-",
        "candidate aging",
        "learned weights",
        "path records",
        "ontology path",
    ),
    "live_layer_drift": (
        "slack",
        "google drive",
        "drive",
        "rime",
        "whisper",
        "ollama",
        "provider",
        "credential",
        "missing_credentials",
        "skipped_missing_credentials",
        "timeout",
        "rate limit",
        "network",
        "unavailable endpoint",
        "connection refused",
        "model-load",
        "model load",
        "embedding endpoint",
        "stt_mismatch",
    ),
    "product_code": (
        "src/web.py",
        "src/education/",
        "src/lingua_viva/",
        "src/pipeline.py",
        "src/context_builder.py",
        "preview wrote",
        "preview writes",
        "privacy gate bypass",
        "route returned 500",
        "500 internal server error",
        "audit receipt incomplete",
        "incomplete audit receipt",
        "approval writes in preview",
        "deliverable",
        "invariant",
        "wrong shape",
        "pipeline_error",
        "tone_mismatch",
        "tts_prefix_wrong",
        "gir_out_of_range",
    ),
}

PYTEST_FAILURE_RE = re.compile(
    r"_{2,}\s+(?P<name>test[^\s]+.*?)\s+_{2,}\n(?P<body>.*?)(?=\n_{2,}\s+test|\n=+\s+short test summary info\s+=+|\Z)",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class DefectEvidence:
    failure_text: str = ""
    test_name: str = ""
    traceback: str = ""
    command: str = ""
    file_path: str = ""
    route: str = ""
    workflow_id: str = ""
    riu_id: str = ""
    domain: str = ""
    gap_signals: list[str] = field(default_factory=list)
    expected: str = ""
    actual: str = ""
    environment: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_any(cls, value: "DefectEvidence | dict | str") -> "DefectEvidence":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(failure_text=value)
        if isinstance(value, dict):
            fields = cls.__dataclass_fields__
            payload = {key: val for key, val in value.items() if key in fields}
            if not isinstance(payload.get("gap_signals"), list):
                payload["gap_signals"] = []
            if not isinstance(payload.get("environment"), dict):
                payload["environment"] = {}
            if not isinstance(payload.get("metadata"), dict):
                payload["metadata"] = {}
            return cls(**payload)
        return cls(failure_text=str(value or ""))


@dataclass
class DefectTriageResult:
    defect_id: str
    primary_layer: str
    confidence: float
    secondary_layers: list[str]
    reasons: list[str]
    recommended_owner: str
    recommended_actions: list[str]
    evidence_hash: str

    def as_dict(self) -> dict:
        return asdict(self)


def _evidence_blob(evidence: DefectEvidence) -> str:
    return json.dumps(evidence.as_dict(), ensure_ascii=False, sort_keys=True, default=str)


def _search_blob(evidence: DefectEvidence) -> str:
    parts: list[str] = [
        evidence.failure_text,
        evidence.test_name,
        evidence.traceback,
        evidence.command,
        evidence.file_path,
        evidence.route,
        evidence.workflow_id,
        evidence.riu_id,
        evidence.domain,
        evidence.expected,
        evidence.actual,
        " ".join(str(signal) for signal in evidence.gap_signals),
        json.dumps(evidence.environment, ensure_ascii=False, sort_keys=True, default=str),
        json.dumps(evidence.metadata, ensure_ascii=False, sort_keys=True, default=str),
    ]
    return "\n".join(part for part in parts if str(part).strip()).lower()


def _contains_any(blob: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if pattern in blob]


def _score_evidence(evidence: DefectEvidence) -> tuple[dict[str, float], list[str]]:
    blob = _search_blob(evidence)
    scores = {layer: 0.0 for layer in LAYERS if layer != "unknown"}
    reasons: list[str] = []

    for layer, patterns in PATTERNS.items():
        hits = _contains_any(blob, patterns)
        if hits:
            scores[layer] += min(0.15 * len(hits), 0.75)
            reasons.append(f"{layer}: matched {', '.join(hits[:4])}")

    if evidence.file_path:
        path = evidence.file_path.lower()
        if path.startswith("tests/") or "contracts/" in path or "scripts/check_" in path:
            scores["checker_logic"] += 0.25
            reasons.append("checker_logic: failure is in test/contract/checker path")
        if path.startswith("ontology/"):
            scores["ontology_taxonomy"] += 0.25
            reasons.append("ontology_taxonomy: failure path is ontology-owned")
        if path.startswith("src/"):
            scores["product_code"] += 0.2
            reasons.append("product_code: failure path is product source")

    for signal in evidence.gap_signals:
        signal_l = str(signal).lower()
        if signal_l.startswith(("low_classification_confidence", "weak_classification")):
            scores["ontology_taxonomy"] += 0.45
            reasons.append(f"ontology_taxonomy: gap signal {signal}")
        elif signal_l.startswith("no_knowledge_at_node"):
            if any(word in blob for word in ("source", "retrieval", "citation")):
                scores["curriculum_source"] += 0.45
                reasons.append(f"curriculum_source: source-related gap signal {signal}")
            else:
                scores["ontology_taxonomy"] += 0.35
                reasons.append(f"ontology_taxonomy: knowledge gap at ontology node {signal}")
        elif signal_l.startswith("research_gap"):
            scores["curriculum_source"] += 0.5
            reasons.append(f"curriculum_source: research/source gap signal {signal}")
        elif signal_l == "voice_loop_failure:stt_mismatch":
            scores["live_layer_drift"] += 0.5
            scores["checker_logic"] += 0.15
            reasons.append("live_layer_drift: STT mismatch is voice live-layer drift")
        elif signal_l in {
            "voice_loop_failure:pipeline_error",
            "voice_loop_failure:tone_mismatch",
            "voice_loop_failure:tts_prefix_wrong",
            "voice_loop_failure:gir_out_of_range",
        }:
            scores["product_code"] += 0.5
            reasons.append(f"product_code: deterministic voice workflow signal {signal}")

    if evidence.riu_id or evidence.domain:
        scores["ontology_taxonomy"] += 0.1
    if evidence.route:
        scores["product_code"] += 0.1
    return scores, reasons


def _tie_break(scores: dict[str, float], evidence: DefectEvidence) -> str:
    blob = _search_blob(evidence)
    if max(scores.values(), default=0.0) < 0.2:
        return "unknown"

    contract_only = any(
        marker in blob
        for marker in ("ui_contract", "route_reachability", "expected_version", "hash drifted", "protected file changed")
    )
    local_invariant = any(
        marker in blob
        for marker in ("privacy gate bypass", "preview wrote", "preview writes", "approval writes", "audit receipt incomplete", "voice_loop_failure:pipeline_error", "voice_loop_failure:tone_mismatch", "voice_loop_failure:tts_prefix_wrong")
    )
    provider = any(
        marker in blob
        for marker in ("credential", "skipped_missing_credentials", "timeout", "rate limit", "network", "model-load", "ollama", "whisper", "rime", "slack", "google drive", "stt_mismatch")
    )
    if contract_only and scores["checker_logic"] >= 0.2:
        return "checker_logic"
    if local_invariant and scores["product_code"] >= 0.2:
        return "product_code"
    if provider and scores["live_layer_drift"] >= 0.2:
        return "live_layer_drift"
    if any(marker in blob for marker in ("citation", "source ledger", "retrieval", "document_store", "research_gap")) and scores["curriculum_source"] >= 0.2:
        return "curriculum_source"
    if any(marker in blob for marker in ("low_classification_confidence", "weak_classification", "riu_id", "entry_node", "unknown_domain")) and scores["ontology_taxonomy"] >= 0.2:
        return "ontology_taxonomy"

    order = ("product_code", "checker_logic", "live_layer_drift", "ontology_taxonomy", "curriculum_source")
    return max(order, key=lambda layer: (scores.get(layer, 0.0), -order.index(layer)))


def classify_failure(evidence: DefectEvidence | dict | str) -> DefectTriageResult:
    ev = DefectEvidence.from_any(evidence)
    blob = _evidence_blob(ev)
    evidence_hash = sha256(blob.encode("utf-8")).hexdigest()[:20]
    scores, reasons = _score_evidence(ev)
    primary = _tie_break(scores, ev)
    if primary == "unknown":
        confidence = 0.1 if blob.strip("{} ") else 0.0
        reasons = reasons or ["No strong layer-specific evidence was present."]
    else:
        top = scores.get(primary, 0.0)
        runner_up = max((score for layer, score in scores.items() if layer != primary), default=0.0)
        confidence = min(0.95, max(0.35, 0.45 + top - (runner_up * 0.35)))
    secondary = [
        layer for layer, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if layer != primary and score >= 0.2
    ][:3]
    return DefectTriageResult(
        defect_id=f"DEF-{evidence_hash[:12]}",
        primary_layer=primary,
        confidence=round(confidence, 2),
        secondary_layers=secondary,
        reasons=reasons[:8],
        recommended_owner=RECOMMENDED_OWNERS[primary],
        recommended_actions=RECOMMENDED_ACTIONS[primary],
        evidence_hash=evidence_hash,
    )


def triage_pytest_output(text: str) -> list[DefectTriageResult]:
    text = text or ""
    matches = list(PYTEST_FAILURE_RE.finditer(text))
    results: list[DefectTriageResult] = []
    for match in matches:
        name = " ".join(match.group("name").split())
        body = match.group("body").strip()
        file_match = re.search(r"([A-Za-z0-9_./-]+\.py):\d+:", body)
        results.append(
            classify_failure(
                DefectEvidence(
                    failure_text=body,
                    test_name=name,
                    traceback=body,
                    file_path=file_match.group(1) if file_match else "",
                )
            )
        )
    if results:
        return results
    if text.strip():
        return [classify_failure(DefectEvidence(failure_text=text))]
    return [classify_failure(DefectEvidence())]


def triage_gap_signal_record(record: dict) -> DefectTriageResult:
    signals = record.get("gap_signals") if isinstance(record.get("gap_signals"), list) else []
    return classify_failure(
        DefectEvidence(
            failure_text=json.dumps(record, sort_keys=True, default=str),
            workflow_id=str(record.get("workflow_id") or record.get("entry_node") or ""),
            domain=str(record.get("domain") or ""),
            gap_signals=[str(signal) for signal in signals],
            metadata={"session_id": record.get("session_id"), "entry_node": record.get("entry_node")},
        )
    )


def triage_golden_workflow_result(result: dict) -> DefectTriageResult:
    steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    failed_steps = [step for step in steps if isinstance(step, dict) and step.get("status") == "FAIL"]
    if not failed_steps and result.get("status") in ("SKIPPED_MISSING_CREDENTIALS", "SKIPPED_NOT_BUILT"):
        failed_steps = [{"name": result.get("status"), "evidence": {"notes": result.get("notes", "")}}]
    text = json.dumps({"result": result, "failed_steps": failed_steps}, sort_keys=True, default=str)
    step_names = " ".join(str(step.get("name") or "") for step in failed_steps).lower()
    gap_signals: list[str] = []
    for step in failed_steps:
        evidence = step.get("evidence") if isinstance(step.get("evidence"), dict) else {}
        failure_class = evidence.get("failure_class") or evidence.get("voice_failure_class")
        if failure_class:
            gap_signals.append(f"voice_loop_failure:{failure_class}")
    extra = ""
    if any(name in step_names for name in ("source_record", "retrieval", "citation")):
        extra = " source_record retrieval citation"
    elif "audit_receipt" in step_names:
        extra = " audit receipt incomplete audit receipt incomplete"
    elif "grounding_result" in step_names:
        extra = " grounding_result invariant"
    return classify_failure(
        DefectEvidence(
            failure_text=text + extra,
            workflow_id=str(result.get("workflow_id") or ""),
            gap_signals=gap_signals,
            metadata={"status": result.get("status"), "mode": result.get("mode")},
        )
    )


def result_to_markdown(result: DefectTriageResult) -> str:
    lines = [
        f"# Defect Triage: {result.defect_id}",
        "",
        f"- Primary layer: `{result.primary_layer}`",
        f"- Confidence: `{result.confidence:.2f}`",
        f"- Recommended owner: {result.recommended_owner}",
        "",
        "## Reasons",
    ]
    lines.extend(f"- {reason}" for reason in result.reasons)
    lines.append("")
    lines.append("## Next Actions")
    lines.extend(f"- {action}" for action in result.recommended_actions)
    if result.secondary_layers:
        lines.append("")
        lines.append(f"Secondary layers: {', '.join(result.secondary_layers)}")
    return "\n".join(lines)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify Lingua Viva defect evidence.")
    parser.add_argument("--file", type=Path, help="Read failure evidence from a text file.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    parser.add_argument("text", nargs="*", help="Failure text when --file is not supplied.")
    args = parser.parse_args(argv)
    if args.file:
        text = args.file.read_text(encoding="utf-8", errors="replace")
    else:
        text = " ".join(args.text)
    result = classify_failure(text)
    if args.json:
        print(json.dumps(result.as_dict(), sort_keys=True))
    else:
        print(result_to_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
