"""
Tests for doctor.py's LV_DESKTOP=1 desktop-mode gating.

This behavior (the fix for "System: BLOCKED" showing permanently on every
desktop install — health checks were requiring authoring-repo-only files a
packaged Electron build deliberately never ships, and hard-failing on the
absence of a .git dir) predates SPEC_LV_MULTI_LANE_MERGE_STRATEGY_2026-07-22's
five tracked lanes; it was flagged there as unattributed/untested. Confirmed
by diff inspection to be this session's earlier live desktop-debug fix. This
file is the missing coverage that spec called for.
"""

from __future__ import annotations

import shutil

import doctor.support_loop.doctor as doctor_module

_REAL_LV_ROOT = doctor_module.LV_ROOT  # captured before any test monkeypatches it

# The files a packaged desktop build actually ships (desktop/package.json's
# extraResources filter) — copy the REAL ones so content-correctness checks
# (matrix_authority, claim_register, publication_safety) that this fix does
# NOT touch still pass on their own merits, same as they do in production.
SHIPPING_FILES = [
    "artifacts/inventory.yaml",
    "claims/evidence_register.yaml",
    "governance/publication_safety.yaml",
    "curriculum/lingua_viva_matrix.yaml",
    "doctor/lv_artifact_gauntlet.py",
]


def _make_desktop_tree(tmp_path):
    """A realistic packaged-desktop-style tree: no .git, none of the
    authoring-only files (README, docx, dev/*), but the real content of the
    files that DO ship — not hand-faked minimal stand-ins."""
    for rel in SHIPPING_FILES:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_REAL_LV_ROOT / rel, dest)
    return tmp_path


def test_desktop_mode_skips_authoring_only_required_files(tmp_path, monkeypatch):
    tree = _make_desktop_tree(tmp_path)
    monkeypatch.setattr(doctor_module, "LV_ROOT", tree)
    monkeypatch.setenv("LV_DESKTOP", "1")

    results = doctor_module.check_required_files()
    by_id = {r.id: r for r in results}

    for excluded in doctor_module.DESKTOP_EXCLUDED_FILES:
        check_id = f"required_file:{excluded}"
        assert by_id[check_id].status == "pass", f"{check_id} should pass (skipped) in desktop mode"


def test_authoring_mode_still_fails_on_missing_required_files(tmp_path, monkeypatch):
    """Regression guard: desktop-mode gating must not weaken the authoring-repo
    check when LV_DESKTOP is unset — the same missing files must still fail."""
    tree = _make_desktop_tree(tmp_path)
    monkeypatch.setattr(doctor_module, "LV_ROOT", tree)
    monkeypatch.delenv("LV_DESKTOP", raising=False)

    results = doctor_module.check_required_files()
    by_id = {r.id: r for r in results}

    for excluded in doctor_module.DESKTOP_EXCLUDED_FILES:
        check_id = f"required_file:{excluded}"
        assert by_id[check_id].status == "fail", f"{check_id} should still fail outside desktop mode"


def test_desktop_mode_branch_check_passes_without_git_repo(tmp_path, monkeypatch):
    tree = _make_desktop_tree(tmp_path)
    monkeypatch.setattr(doctor_module, "REPO_ROOT", tree)
    monkeypatch.setenv("LV_DESKTOP", "1")

    result = doctor_module.check_branch()
    assert result.status == "pass"


def test_authoring_mode_branch_check_warns_without_git_repo(tmp_path, monkeypatch):
    tree = _make_desktop_tree(tmp_path)
    monkeypatch.setattr(doctor_module, "REPO_ROOT", tree)
    monkeypatch.delenv("LV_DESKTOP", raising=False)

    result = doctor_module.check_branch()
    assert result.status == "warn"


def test_desktop_mode_docx_check_skips_when_docx_absent(tmp_path, monkeypatch):
    tree = _make_desktop_tree(tmp_path)
    monkeypatch.setattr(doctor_module, "LV_ROOT", tree)
    monkeypatch.setattr(doctor_module, "REPO_ROOT", tree)
    monkeypatch.setenv("LV_DESKTOP", "1")

    result = doctor_module.check_docx_not_modified()
    assert result.status == "pass"


def test_desktop_mode_yaml_files_skips_dev_only_yaml(tmp_path, monkeypatch):
    tree = _make_desktop_tree(tmp_path)
    monkeypatch.setattr(doctor_module, "LV_ROOT", tree)
    monkeypatch.setenv("LV_DESKTOP", "1")

    results = doctor_module.check_yaml_files()
    by_id = {r.id: r for r in results}
    check_id = "yaml:dev/lv_deferred_candidates.yaml"
    assert check_id in by_id
    assert by_id[check_id].status == "pass"


def test_desktop_mode_full_run_doctor_reports_ok_not_blocked(tmp_path, monkeypatch):
    """End-to-end: this is the actual user-visible bug that was fixed —
    a fresh desktop install with no git repo and none of the authoring-only
    files must not report BLOCKED."""
    tree = _make_desktop_tree(tmp_path)
    monkeypatch.setattr(doctor_module, "LV_ROOT", tree)
    monkeypatch.setattr(doctor_module, "REPO_ROOT", tree)
    monkeypatch.setenv("LV_DESKTOP", "1")

    result = doctor_module.run_doctor(write_log=False)
    assert result["status"] != "BLOCKED", (
        f"Desktop install should never report BLOCKED; got {result['status']}. "
        f"Failing checks: {[c for c in result['checks'] if c['status'] == 'fail']}"
    )
