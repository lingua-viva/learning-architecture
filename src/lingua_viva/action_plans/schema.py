from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.lingua_viva.sources.schema import ORIGIN_VALUES

APPROVAL_STATUSES = frozenset({"not_required", "pending", "approved", "rejected", "expired"})


@dataclass
class GroundingSummary:
    tier_used: str = "none"
    gir_score: float = 1.0
    external_called: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlannedAction:
    action_id: str
    name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    param_sources: dict[str, list[str]] = field(default_factory=dict)
    risk_level: str = "none"
    side_effects: list[str] = field(default_factory=list)
    allows_external: bool = False
    requires_approval: bool = True
    expected_output: str = "none"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlannedAction":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Approval:
    status: str = "pending"
    approved_by: str = ""
    approved_at: str = ""
    rejected_reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in APPROVAL_STATUSES:
            self.status = "pending"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlanPolicy:
    egress_hosts: list[str] = field(default_factory=list)
    protect_forced_local: bool = True
    sanitized_external_query: str = ""
    can_execute: bool = False
    reason: str = "awaiting_approval"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionPlan:
    action_plan_id: str
    created_at: str
    session_id: str = ""
    trace_id: str = ""
    grounding_id: str = ""
    intent: str = ""
    user_goal: str = ""
    created_by: str = "operator"
    source_record_ids: list[str] = field(default_factory=list)
    grounding_summary: GroundingSummary = field(default_factory=GroundingSummary)
    actions: list[PlannedAction] = field(default_factory=list)
    approval: Approval = field(default_factory=Approval)
    policy: PlanPolicy = field(default_factory=PlanPolicy)
    execution_result: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.created_by not in ORIGIN_VALUES:
            self.created_by = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_plan_id": self.action_plan_id,
            "created_at": self.created_at,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "grounding_id": self.grounding_id,
            "intent": self.intent,
            "user_goal": self.user_goal,
            "created_by": self.created_by,
            "source_record_ids": list(self.source_record_ids),
            "grounding_summary": self.grounding_summary.as_dict(),
            "actions": [a.as_dict() for a in self.actions],
            "approval": self.approval.as_dict(),
            "policy": self.policy.as_dict(),
            "execution_result": self.execution_result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionPlan":
        payload = dict(data)
        grounding_summary = GroundingSummary(**{k: v for k, v in (payload.pop("grounding_summary", {}) or {}).items() if k in GroundingSummary.__dataclass_fields__})
        actions = [PlannedAction.from_dict(a) for a in payload.pop("actions", []) or []]
        approval = Approval(**{k: v for k, v in (payload.pop("approval", {}) or {}).items() if k in Approval.__dataclass_fields__})
        policy = PlanPolicy(**{k: v for k, v in (payload.pop("policy", {}) or {}).items() if k in PlanPolicy.__dataclass_fields__})
        known = {k: v for k, v in payload.items() if k in cls.__dataclass_fields__}
        return cls(grounding_summary=grounding_summary, actions=actions, approval=approval, policy=policy, **known)
