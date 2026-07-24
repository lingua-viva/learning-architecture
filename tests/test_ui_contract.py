"""UI bundle contract regression test (MC-lessons §3).

Pins the current contract version. When a deliberate UI change requires a
version bump (`python3 scripts/check_ui_contract.py --bump`), update
EXPECTED_VERSION here in the same commit and add a bump-log line to
contracts/UI_CONTRACT.yaml explaining why — MC's own ceremony discipline:
the comments are the changelog.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

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
#   v21 (2026-07-23): Linux download button.
#   v22 (2026-07-23): Observe support-profile classification write path.
#   v23 (2026-07-23): Google Drive explicit-import Settings mount.
#   v26 (2026-07-23): Restored unobserved_students return statement in web.py.
#   v27 (2026-07-23): support-profile summary JavaScript parse fix.
#   v28 (2026-07-23): Ingestion and extraction mapping v2 UI implementation.
#   v29 (2026-07-23): LV-BLT-001 provider connect form + LV-BLT-003 teaching
#     artifact ingest UI in Settings.
#   v30 (2026-07-23): LV-BLT-007 System stats mounted in Health; direct RTI
#     tier control mounted in Students; removed duplicate, never-mounted
#     GET /api/students/unobserved (brief.py's own _unobserved() is what
#     Home's reminder actually calls); removed duplicate GET
#     /api/teacher/today (Home retains /api/brief); session_info() docstring.
EXPECTED_VERSION = 30


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


def test_static_inline_javascript_syntax_is_valid():
    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available for static JS syntax check")
    html = _html()
    start = html.index("<script>") + len("<script>")
    end = html.index("</script>", start)
    script = html[start:end]
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as handle:
        handle.write(script)
        handle.flush()
        result = subprocess.run([node, "--check", handle.name], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


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
    handler_entries = re.findall(r"^\s*([a-z]+):\s*render[A-Za-z]+,?", view_map.group(1), flags=re.M)
    nav_entries = [item[0] for items in arrays.values() for item in items]
    handler_ids = set(handler_entries)
    nav_ids = set(nav_entries)

    assert len(handler_entries) == len(handler_ids), "renderView() contains duplicate handler ids"
    assert len(nav_entries) == len(nav_ids), "sidebar contains duplicate nav ids"
    assert nav_ids == handler_ids, (
        "every live view handler must have exactly one sidebar mount, and every "
        "sidebar item must have a handler; do not ship dead renderers or dead nav"
    )


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
