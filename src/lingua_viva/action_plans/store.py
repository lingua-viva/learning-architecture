from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.lingua_viva.action_plans.schema import ActionPlan

_WRITE_LOCK = threading.Lock()


def _state_root() -> Path:
    env = os.environ.get("LV_STATE_HOME", "").strip()
    return Path(env).expanduser() if env else Path.home() / ".lingua-viva"


def plans_path() -> Path:
    path = _state_root() / "actions" / "plans.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compute_action_plan_id() -> str:
    return f"APL-{uuid.uuid4().hex[:20]}"


def _atomic_write(path: Path, lines: list[str]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def _load_all() -> dict[str, ActionPlan]:
    path = plans_path()
    plans: dict[str, ActionPlan] = {}
    if not path.exists():
        return plans
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            plan = ActionPlan.from_dict(json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            continue
        plans[plan.action_plan_id] = plan
    return plans


def upsert_plan(plan: ActionPlan) -> ActionPlan:
    with _WRITE_LOCK:
        plans = _load_all()
        plans[plan.action_plan_id] = plan
        _atomic_write(plans_path(), [json.dumps(p.as_dict(), sort_keys=True) for _id, p in sorted(plans.items())])
        return plan


def read_plan(action_plan_id: str) -> ActionPlan | None:
    return _load_all().get(action_plan_id)


def read_plans(status: str | None = None, limit: int | None = None) -> list[dict]:
    plans = list(_load_all().values())
    if status:
        plans = [p for p in plans if p.approval.status == status]
    plans.sort(key=lambda p: p.created_at, reverse=True)
    if limit is not None:
        plans = plans[:max(0, int(limit))]
    return [p.as_dict() for p in plans]
