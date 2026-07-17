from __future__ import annotations

from pathlib import Path


LV_ROOT = Path(__file__).resolve().parents[2]
DEV_ROOT = LV_ROOT / "dev"
STATE_DIR = LV_ROOT / ".lv_support"
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

