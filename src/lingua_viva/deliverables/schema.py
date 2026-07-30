from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

DELIVERABLE_TYPES = (
    "parent_report",
    "daily_file",
    "assessment",
    "drive_export",
    "observation_export",
    "help_artifact",
    "portfolio_entry",
    "cohort_lesson_plan",
    "none",
)
STATUSES = ("created", "updated", "sent", "exported", "failed", "not_applicable")
LOCATION_KINDS = ("local_path", "drive_file", "download", "none")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compute_deliverable_id(trace_id: str, action_plan_id: str) -> str:
    digest = hashlib.sha256(f"{trace_id}:{action_plan_id}".encode()).hexdigest()[:20]
    return f"DLV-{digest}"


@dataclass
class DeliverableLocation:
    kind: str = "none"
    uri: str = ""
    path: str = ""
    external_id: str = ""

    def __post_init__(self) -> None:
        if self.kind not in LOCATION_KINDS:
            self.kind = "none"

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DeliverableLocation":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DeliverableRecord:
    deliverable_id: str
    created_at: str = ""
    session_id: str = ""
    trace_id: str = ""
    grounding_id: str = ""
    action_plan_id: str = ""
    action_execution_id: str = ""
    type: str = "none"
    title: str = ""
    status: str = "created"
    location: DeliverableLocation = field(default_factory=DeliverableLocation)
    source_record_ids: list[str] = field(default_factory=list)
    summary: str = ""
    content_hash: str = ""
    error: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = now_iso()
        if self.type not in DELIVERABLE_TYPES:
            self.type = "none"
        if self.status not in STATUSES:
            self.status = "created"

    def as_dict(self) -> dict:
        data = asdict(self)
        data["location"] = self.location.as_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "DeliverableRecord":
        payload = dict(data)
        location_data = payload.pop("location", {}) or {}
        location = location_data if isinstance(location_data, DeliverableLocation) else DeliverableLocation.from_dict(location_data)
        known = {k: v for k, v in payload.items() if k in cls.__dataclass_fields__ and k != "location"}
        return cls(location=location, **known)
