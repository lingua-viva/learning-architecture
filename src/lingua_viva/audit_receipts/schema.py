from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

SCOPES = ("query", "action_plan", "deliverable", "workflow", "observation_export")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compute_receipt_id(session_id: str, trace_ids: list[str]) -> str:
    digest = hashlib.sha256(f"{session_id}:{'|'.join(sorted(trace_ids))}".encode()).hexdigest()[:20]
    return f"AUD-{digest}"


@dataclass
class AuditReceipt:
    audit_receipt_id: str
    created_at: str = ""
    scope: str = "query"
    session_id: str = ""
    trace_ids: list[str] = field(default_factory=list)
    source_record_ids: list[str] = field(default_factory=list)
    grounding_ids: list[str] = field(default_factory=list)
    action_plan_ids: list[str] = field(default_factory=list)
    deliverable_ids: list[str] = field(default_factory=list)
    missing_join_keys: list[str] = field(default_factory=list)
    entry_gate: dict = field(default_factory=dict)
    routing: dict = field(default_factory=dict)
    egress: dict = field(default_factory=dict)
    approval: dict = field(default_factory=dict)
    hash_chain: dict = field(default_factory=dict)
    export: dict = field(default_factory=lambda: {"format": "json", "path": ""})
    privacy: dict = field(default_factory=lambda: {"student_identifiers_exported": False, "raw_observation_text_exported": False})

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = now_iso()
        if self.scope not in SCOPES:
            self.scope = "query"

    @property
    def is_complete(self) -> bool:
        return not self.missing_join_keys

    def as_dict(self) -> dict:
        data = asdict(self)
        data["is_complete"] = self.is_complete
        return data

    def compute_payload_hash(self) -> str:
        data = self.as_dict()
        data.pop("hash_chain", None)
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
