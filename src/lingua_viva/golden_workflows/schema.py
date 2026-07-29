from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

WORKFLOW_IDS = ("GW-EDU-001", "GW-EDU-002", "GW-EDU-003", "GW-DRIVE-004", "GW-SLACK-005")
WORKFLOW_STATUSES = ("PASS", "FAIL", "SKIPPED_MISSING_CREDENTIALS", "SKIPPED_NOT_BUILT")
STEP_STATUSES = ("PASS", "FAIL", "SKIP")
MODES = ("hermetic", "live")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class WorkflowStep:
    name: str
    status: str = "SKIP"
    ui_path: str = ""
    api_call: str = ""
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class GoldenWorkflowResult:
    workflow_id: str
    name: str
    mode: str = "hermetic"
    status: str = "PASS"
    started_at: str = ""
    duration_ms: int = 0
    steps: list[WorkflowStep] = field(default_factory=list)
    contract_ids: dict = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = now_iso()
        if self.workflow_id not in WORKFLOW_IDS:
            raise ValueError(f"invalid workflow_id: {self.workflow_id}")
        if self.mode not in MODES:
            raise ValueError(f"invalid mode: {self.mode}")
        if self.status not in WORKFLOW_STATUSES:
            raise ValueError(f"invalid status: {self.status}")

    def as_dict(self) -> dict:
        return asdict(self)
