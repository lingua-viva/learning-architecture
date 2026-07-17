from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


SEVERITY = {"OK": 0, "WARN": 1, "FIXABLE": 2, "UPDATE_AVAILABLE": 3, "BLOCKED": 4, "PRIVATE_RISK": 5}
CHECK_TO_STATUS = {"pass": "OK", "warn": "WARN", "fixable": "FIXABLE", "fail": "BLOCKED", "private_risk": "PRIVATE_RISK"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class CheckResult:
    id: str
    status: str
    message: str
    detail: str = ""
    safe_fix: str | None = None
    severity: str = "required"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def worst_status(checks: list[CheckResult]) -> str:
    if not checks:
        return "OK"
    statuses = [CHECK_TO_STATUS.get(check.status, check.status) for check in checks]
    return max(statuses, key=lambda status: SEVERITY[status])
