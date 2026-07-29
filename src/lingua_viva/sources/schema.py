from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SOURCE_TYPES = frozenset({"local", "drive", "slack"})
RETRIEVAL_SCOPES = frozenset({"metadata", "snippet", "content", "excluded"})
PROVENANCE_VALUES = frozenset({"scan", "import", "sync", "fetch", "capture"})
SENSITIVITY_HINTS = frozenset({"unknown", "low", "medium", "high", "protect"})
EGRESS_POLICIES = frozenset({"read_only", "approval_required", "write_enabled", "blocked"})
ORIGIN_VALUES = frozenset({"operator", "agent", "eval", "public", "unknown"})
OBSERVATION_EVENTS = frozenset({"seen", "changed", "excluded", "imported", "deleted", "error"})


@dataclass
class Policy:
    egress_policy: str = "read_only"
    model_context_allowed: bool = True
    external_allowed: bool = False
    reason: str = "local_first"

    def __post_init__(self) -> None:
        if self.egress_policy not in EGRESS_POLICIES:
            self.egress_policy = "read_only"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceRecord:
    source_record_id: str
    source_type: str
    source_id: str
    container: str
    record_id: str
    title: str
    uri: str
    retrieval_scope: str
    created_at: str
    observed_at: str
    provenance: str
    student_data: bool = False
    sensitivity_hint: str = "unknown"
    policy: Policy = field(default_factory=Policy)
    summary: str = ""
    content_hash: str = ""
    origin: str = "operator"

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"invalid source_type: {self.source_type}")
        if self.retrieval_scope not in RETRIEVAL_SCOPES:
            self.retrieval_scope = "metadata"
        if self.provenance not in PROVENANCE_VALUES:
            self.provenance = "scan"
        if self.sensitivity_hint not in SENSITIVITY_HINTS:
            self.sensitivity_hint = "unknown"
        if self.origin not in ORIGIN_VALUES:
            self.origin = "unknown"
        if self.student_data:
            self.sensitivity_hint = "protect"
            self.policy.model_context_allowed = False
            self.policy.external_allowed = False
            self.policy.egress_policy = "blocked"
            self.policy.reason = "student_data_local_only"
        if self.sensitivity_hint == "protect" or self.retrieval_scope == "excluded":
            self.policy.model_context_allowed = False
            self.policy.external_allowed = False

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["policy"] = self.policy.as_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceRecord":
        payload = dict(data)
        policy_data = payload.pop("policy", None) or {}
        policy = Policy(**{k: v for k, v in policy_data.items() if k in Policy.__dataclass_fields__})
        known = {k: v for k, v in payload.items() if k in cls.__dataclass_fields__ and k != "policy"}
        return cls(policy=policy, **known)


@dataclass
class SourceObservation:
    observation_id: str
    source_record_id: str
    source_type: str
    event: str
    observed_at: str
    content_hash: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event not in OBSERVATION_EVENTS:
            self.event = "seen"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceObservation":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
