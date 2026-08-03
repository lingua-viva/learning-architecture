from __future__ import annotations

import os
from pathlib import Path


LV_ROOT = Path(__file__).resolve().parents[2]
DEV_ROOT = LV_ROOT / "dev"


def _state_home() -> Path:
    override = os.environ.get("LV_STATE_HOME") or os.environ.get("LV_CONFIG_HOME")
    return Path(override).expanduser() if override else Path.home() / ".lingua-viva"


STATE_DIR = _state_home() / ".lv_support"
BUNDLE_DIR = STATE_DIR / "bundles"
INCIDENT_LOG = STATE_DIR / "incidents.ndjson"
REPAIR_LOG = STATE_DIR / "repair_log.ndjson"
DOCTOR_LOG = STATE_DIR / "doctor_runs.ndjson"


def find_repo_root(start: Path = LV_ROOT) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


REPO_ROOT = find_repo_root()
