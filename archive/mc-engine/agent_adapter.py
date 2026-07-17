"""
Codex execution adapter envelopes.

This is the smallest useful governed loop:
  MC pipeline result -> task envelope -> Codex executes -> result envelope -> NDJSON audit log.

The adapter does not launch Codex. It defines the wire contract and durable memory
surface so a Codex session can be governed and audited by Mission Canvas.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.gateway.sanitizer import Sanitizer


DEFAULT_DATA_BOUNDARY = "no-phi, no-child-data, no-pricing"
DEFAULT_MODELS_ALLOWED = ["codex"]


def _default_data_dir() -> Path:
    return Path(__file__).parent.parent / "memory" / "data"


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _task_id() -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return f"TASK-{stamp}-{uuid.uuid4().hex[:8]}"


def _append_ndjson(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def sanitize_source_query(query: str, blocks_external: bool = False) -> str:
    """Return a task-safe source query. Never falls back to raw text if blocked."""
    result = Sanitizer().analyze(query, {"blocks_external": blocks_external})
    if result.blocked or not result.sanitized:
        return "[SENSITIVE_QUERY_BLOCKED]"
    return result.sanitized


def infer_files_to_read(text: str) -> list[str]:
    """Extract obvious repo-relative file references from a task description."""
    candidates = re.findall(r"(?:[\w.-]+/)+[\w.-]+(?:\.[\w.-]+)?", text)
    seen: set[str] = set()
    files: list[str] = []
    for c in candidates:
        cleaned = c.strip(".,:;)\"' ")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            files.append(cleaned)
    return files[:12]


def task_envelope_from_pipeline_result(
    *,
    query: str,
    requested_intent: str,
    result: Any,
    objective: Optional[str] = None,
    constraints: Optional[list[str]] = None,
) -> dict[str, Any]:
    classification = result.classification
    path_record = result.path_record
    gap_signals = list(getattr(result, "gap_signals", []) or [])
    external_allowed = not classification.blocks_external and not any(
        g.startswith("entry_gate_blocked") or g == "research_blocked_by_entry_gate"
        for g in gap_signals
    )

    safe_query = sanitize_source_query(query, blocks_external=classification.blocks_external)
    objective_text = objective or safe_query

    return {
        "task_id": _task_id(),
        "created_at": _iso_now(),
        "source_query": safe_query,
        "classification": {
            "riu": classification.riu_id,
            "name": classification.name,
            "domain": classification.domain,
            "intent": requested_intent.upper(),
            "confidence": classification.confidence,
            "default_intent": classification.default_intent,
            "signals_matched": list(classification.signals_matched),
        },
        "policy": {
            "external_allowed": external_allowed,
            "models_allowed": DEFAULT_MODELS_ALLOWED,
            "data_boundary": DEFAULT_DATA_BOUNDARY,
            "one_way_door": False,
            "requires_local": bool(classification.requires_local),
            "blocks_external": bool(classification.blocks_external),
        },
        "objective": objective_text,
        "constraints": constraints or [
            "Do not send PHI, child data, credentials, pricing, or client-identifying data to external models.",
            "Use repo-local context and existing project patterns before inventing new abstractions.",
            "Return a result envelope with patches, commands, tests, decision, and reflection.",
        ],
        "context": {
            "files_to_read": infer_files_to_read(query),
            "knowledge_entries": list(path_record.knowledge_entries_used),
            "prior_paths": [path_record.query_hash],
            "steps_executed": list(result.steps_executed),
            "gap_signals": gap_signals,
        },
        "mc_path": {
            "session_id": result.session_id,
            "query_hash": result.query_hash,
            "entry_node": path_record.entry_node,
            "path": list(path_record.path),
            "external_called": bool(result.external_called),
            "duration_ms": result.duration_ms,
        },
    }


@dataclass
class AgentEnvelopeStore:
    data_dir: Path = field(default_factory=_default_data_dir)

    @property
    def tasks_file(self) -> Path:
        return self.data_dir / "agent_tasks.ndjson"

    @property
    def executions_file(self) -> Path:
        return self.data_dir / "agent_executions.ndjson"

    def write_task(self, envelope: dict[str, Any]) -> dict[str, Any]:
        _append_ndjson(self.tasks_file, envelope)
        return envelope

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(reversed(_read_ndjson(self.tasks_file)))[:limit]

    def find_task(self, task_id: str) -> Optional[dict[str, Any]]:
        for task in reversed(_read_ndjson(self.tasks_file)):
            if task.get("task_id") == task_id:
                return task
        return None

    def write_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Validate and store a result envelope. Enforces schema + policy compliance."""
        # Schema validation
        if not result.get("task_id"):
            raise ValueError("result envelope requires task_id")
        if not result.get("status") or result["status"] not in ("completed", "blocked", "partial", "failed"):
            raise ValueError("result envelope requires status: completed|blocked|partial|failed")
        if "patches" not in result or not isinstance(result["patches"], list):
            raise ValueError("result envelope requires patches (list)")
        if "test_results" not in result or not isinstance(result["test_results"], dict):
            raise ValueError("result envelope requires test_results (dict with passed/failed)")
        if "decision" not in result or not isinstance(result["decision"], str):
            raise ValueError("result envelope requires decision (string)")

        # Normalize optional fields
        result.setdefault("commands_run", [])
        result.setdefault("models_used", [])
        result.setdefault("reflection", "")
        result.setdefault("external_called", False)

        # Task ID match: verify the task exists
        task = self.find_task(result["task_id"])
        if task is None:
            raise ValueError(f"task_id '{result['task_id']}' not found in task store")

        # Policy compliance check
        policy = task.get("policy", {})
        if not policy.get("external_allowed", True):
            # Policy says no external — check if agent self-reports external use
            if result.get("external_called"):
                raise ValueError(
                    f"POLICY VIOLATION: task {result['task_id']} forbids external calls, "
                    f"but result reports external_called=true"
                )
            # Check commands_run for external model indicators
            external_indicators = ["curl", "wget", "httpx", "requests.post", "openai", "anthropic", "perplexity"]
            for cmd in result.get("commands_run", []):
                cmd_lower = str(cmd).lower()
                if any(ind in cmd_lower for ind in external_indicators):
                    raise ValueError(
                        f"POLICY VIOLATION: task {result['task_id']} forbids external calls, "
                        f"but commands_run contains '{cmd}'"
                    )

        record = {
            "recorded_at": _iso_now(),
            **result,
        }
        _append_ndjson(self.executions_file, record)
        return record

    def list_results(self, limit: int = 20, query: str = "") -> list[dict[str, Any]]:
        records = list(reversed(_read_ndjson(self.executions_file)))
        if query:
            q = query.lower()
            records = [r for r in records if q in json.dumps(r, sort_keys=True).lower()]
        return records[:limit]


def summarize_results(records: list[dict[str, Any]], limit: int = 5) -> str:
    if not records:
        return "No Codex execution records found."
    lines = [f"Codex execution records: {len(records)} shown"]
    for r in records[:limit]:
        patches = r.get("patches") or []
        commands = r.get("commands_run") or []
        tests = r.get("test_results") or {}
        status = r.get("status", "unknown")
        task_id = r.get("task_id", "unknown")
        decision = r.get("decision", "")
        lines.append(
            f"- {task_id}: {status}; patches={len(patches)}; commands={len(commands)}; "
            f"tests={tests.get('passed', 0)} passed/{tests.get('failed', 0)} failed; {decision[:120]}"
        )
    return "\n".join(lines)


def load_result_file(path: str) -> dict[str, Any]:
    if path == "-":
        import sys
        return json.loads(sys.stdin.read())
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# Backwards-compat alias
CodexEnvelopeStore = AgentEnvelopeStore
