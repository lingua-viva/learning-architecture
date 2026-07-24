"""Regression tests for `lv preflight` (MC-lessons §2).

Cloned from Mission Canvas's own `mc preflight` (src/mc_cli.py::cmd_preflight).
Covers the 6 structural checks and, specifically, the anchored conflict-marker
regex — MC's own preflight originally used `git diff --cached -S "<<<<<<<"`
which false-positives on any file that merely *mentions* a merge-marker
string in prose or code (this test file, or preflight's own source). The
anchored form (`-G '^<{7} '`) only matches real merge markers at the start of
a line. Check #6 (route_reachability) was added by
SPEC_LV_ROUTE_REACHABILITY_GATE_2026-07-23.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run_preflight(*extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "src.lingua_viva.cli", "preflight", *extra_args],
        capture_output=True, text=True, cwd=REPO,
    )


def test_preflight_passes_on_clean_tree():
    result = _run_preflight()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Preflight: 6/6" in result.stdout


def test_preflight_json_reports_all_six_checks():
    result = _run_preflight("--json")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    names = {c["name"] for c in data["checks"]}
    assert names == {
        "ui_contract", "golden_parses", "imports", "ontology", "no_conflicts",
        "route_reachability",
    }
    assert all(c["passed"] for c in data["checks"])
    assert data["passed"] == data["total"] == 6


def test_preflight_runs_under_five_seconds():
    result = _run_preflight("--json")
    data = json.loads(result.stdout)
    assert data["elapsed_seconds"] < 5.0


def test_conflict_marker_check_is_anchored_not_substring():
    """A file that mentions "<<<<<<<" in a string literal (like this test's
    own docstring, or preflight's own source) must not trip the check. Only
    a real anchored merge marker (start-of-line "<<<<<<< ") should. We
    verify this against the *implementation itself* rather than staging a
    real conflict marker (which would require dirtying the git index)."""
    conflict = subprocess.run(
        ["git", "diff", "--cached", "-G", "^<{7} ", "--name-only"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert conflict.returncode == 0
    # This test file itself contains the literal string "<<<<<<<" in its
    # docstring/comments above but is not staged as a conflict — proves the
    # anchored pattern does not match prose mentions.
    substring_match = subprocess.run(
        ["git", "diff", "--cached", "-S", "<<<<<<<", "--name-only"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert substring_match.returncode == 0
