"""UI bundle contract regression test (MC-lessons §3).

Pins the current contract version. When a deliberate UI change requires a
version bump (`python3 scripts/check_ui_contract.py --bump`), update
EXPECTED_VERSION here in the same commit and add a bump-log line to
contracts/UI_CONTRACT.yaml explaining why — MC's own ceremony discipline:
the comments are the changelog.
"""

import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

# Bump log:
#   v1 (2026-07-19): initial lock, MC-lessons pass baseline.
#   v2 (2026-07-19): src/web.py request-outcome logging middleware (§5).
#   v3 (2026-07-19): static/index.html Ctrl/Cmd+K quick-capture overlay (§7).
#   v4 (2026-07-19): GET /api/profile/export + Export My Data button (§8).
EXPECTED_VERSION = 4


def test_version_bumped_exactly_one_from_live():
    contract = yaml.safe_load((REPO / "contracts" / "UI_CONTRACT.yaml").read_text(encoding="utf-8"))
    assert contract["version"] == EXPECTED_VERSION, (
        "contracts/UI_CONTRACT.yaml version drifted from the pinned test value — "
        "if this was a deliberate UI change, update EXPECTED_VERSION here and add "
        "a bump-log line to the contract file."
    )


def test_ui_contract_check_passes():
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_ui_contract.py")],
        capture_output=True, text=True, cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ui_contract_lock_matches_live_files():
    import hashlib
    import json

    contract = yaml.safe_load((REPO / "contracts" / "UI_CONTRACT.yaml").read_text(encoding="utf-8"))
    lock = json.loads((REPO / "contracts" / "UI_CONTRACT.lock").read_text(encoding="utf-8"))
    assert lock["version"] == contract["version"]
    for rel in contract["files"]:
        actual = hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
        assert lock["hashes"][rel] == actual, f"{rel} hash drifted from lock without a version bump"
