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
#   v5 (2026-07-20): default ingest scratch storage moved to LV runtime home.
#   v6 (2026-07-20): admin deferred views explain reasons/prerequisites.
#   v7 (2026-07-20): EXP09 fix — healthBadgeClass() + .badge.risk CSS class.
#   v8 (2026-07-20): Claudia-lens hardening — copy/register updates for
#     teacher UI, parent draft route, and quick-capture deterministic feedback.
#   v9 (2026-07-20): sidebar accessibility + token pass.
#   v10 (2026-07-22): file-map confirmation, opt-in zone peek, and assignment UI.
#   v11 (2026-07-22): Slack utility view and Events API integration.
#   v12 (2026-07-22): Slack setup-scope and network-boundary hardening.
#   v13 (2026-07-22): convergence re-lock for combined protected UI work.
#   v14-v18 (2026-07-22): convergence plus local-only Observe/Ask voice workflow.
#   v19 (2026-07-22): 15-pass Observe/Ask Oka voice hardening.
#   v20 (2026-07-23): teacher-lens/RTI endpoints + Phase 5B surface cards.
EXPECTED_VERSION = 21


def _html() -> str:
    return (REPO / "static" / "index.html").read_text(encoding="utf-8")


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


def test_sidebar_nav_contract_counts_and_handlers():
    import re

    html = _html()
    arrays = {}
    for name in ("teacherNav", "adminNav", "utilityNav"):
        match = re.search(rf"const {name} = \[(.*?)\];", html, flags=re.S)
        assert match, f"{name} array missing"
        arrays[name] = re.findall(r'\["([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\]', match.group(1))

    assert len(arrays["teacherNav"]) == 8
    assert len(arrays["adminNav"]) == 4
    assert len(arrays["utilityNav"]) == 7

    view_map = re.search(r"const views = \{(.*?)\n      \};", html, flags=re.S)
    assert view_map, "renderView() view handler map missing"
    handler_ids = set(re.findall(r"^\s*([a-z]+):\s*render[A-Za-z]+,?", view_map.group(1), flags=re.M))
    nav_ids = {item[0] for items in arrays.values() for item in items}
    assert nav_ids <= handler_ids


def test_sidebar_accessibility_markup_and_tokens_present():
    html = _html()
    assert 'id="primary-nav" class="nav" aria-label="Primary"' in html
    assert 'id="utility-nav" class="nav utility" aria-label="Utility"' in html
    assert 'aria-current="page"' in html
    assert ".nav button:focus-visible" in html
    assert "--lv-sidebar-width: 200px;" in html
    assert "grid-template-columns: var(--lv-sidebar-width) minmax(0, 1fr);" in html
    assert "--lv-nav-gap: 4px;" in html
    assert "gap: var(--lv-nav-gap);" in html
    assert "--lv-nav-row-min-height: 38px;" in html
