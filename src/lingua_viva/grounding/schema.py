from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

TIERS = ("local", "drive", "slack", "knowledge", "external")
TIER_STATUSES = frozenset({"hit", "miss", "blocked", "skipped"})


@dataclass
class Classification:
    node_id: str = ""
    domain: str = ""
    confidence: float = 0.0
    blocks_external: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Routing:
    route_policy_version: str = "lv.local_first.v1"
    capability_tier: str = ""
    selected_provider: str = ""
    external_called: bool = False
    route_reason: str = "local_first_policy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TierAttempt:
    tier: str
    status: str
    reason: str = ""
    source_record_ids: list[str] = field(default_factory=list)
    count: int = 0

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ValueError(f"invalid tier: {self.tier}")
        if self.status not in TIER_STATUSES:
            self.status = "miss"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceUsed:
    source_record_id: str = ""
    source_type: str = ""
    title: str = ""
    retrieval_scope: str = "snippet"
    sensitivity_hint: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GIR:
    score: float = 1.0
    total_claims: int = 0
    unsupported_claims: int = 0
    uncertainty_claims: int = 0
    method: str = "claim_support_v2_linkage"
    fabricated_identifiers: list[str] = field(default_factory=list)
    v1_score: float | None = None
    v1_delta: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroundingResult:
    grounding_id: str
    trace_id: str
    session_id: str
    query_hash: str
    intent: str = ""
    classification: Classification = field(default_factory=Classification)
    routing: Routing = field(default_factory=Routing)
    tier_attempts: list[TierAttempt] = field(default_factory=list)
    tier_used: str = "none"
    sources_used: list[SourceUsed] = field(default_factory=list)
    gir: GIR = field(default_factory=GIR)
    protect: dict[str, Any] = field(default_factory=lambda: {"forced_local": True, "reason": "student_data_local_only"})

    def as_dict(self) -> dict[str, Any]:
        return {
            "grounding_id": self.grounding_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "query_hash": self.query_hash,
            "intent": self.intent,
            "classification": self.classification.as_dict(),
            "routing": self.routing.as_dict(),
            "tier_attempts": [t.as_dict() for t in self.tier_attempts],
            "tier_used": self.tier_used,
            "sources_used": [s.as_dict() for s in self.sources_used],
            "external_citations": [],
            "gir": self.gir.as_dict(),
            "protect": dict(self.protect),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroundingResult":
        payload = dict(data)
        classification = Classification(**{k: v for k, v in (payload.pop("classification", {}) or {}).items() if k in Classification.__dataclass_fields__})
        routing = Routing(**{k: v for k, v in (payload.pop("routing", {}) or {}).items() if k in Routing.__dataclass_fields__})
        attempts = [TierAttempt(**{k: v for k, v in item.items() if k in TierAttempt.__dataclass_fields__}) for item in payload.pop("tier_attempts", []) or []]
        sources = [SourceUsed(**{k: v for k, v in item.items() if k in SourceUsed.__dataclass_fields__}) for item in payload.pop("sources_used", []) or []]
        gir = GIR(**{k: v for k, v in (payload.pop("gir", {}) or {}).items() if k in GIR.__dataclass_fields__})
        known = {k: v for k, v in payload.items() if k in cls.__dataclass_fields__}
        return cls(classification=classification, routing=routing, tier_attempts=attempts, sources_used=sources, gir=gir, **known)
