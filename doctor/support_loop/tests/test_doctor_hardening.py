from pathlib import Path
import json
import sys
from types import SimpleNamespace

import pytest


SUPPORT_ROOT = Path(__file__).resolve().parents[1]
DEV_ROOT = SUPPORT_ROOT.parent
sys.path.insert(0, str(DEV_ROOT))

from support_loop import doctor


def test_missing_file_fixture_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "LV_ROOT", tmp_path)
    monkeypatch.setattr(doctor, "REQUIRED_FILES", ["README.md"])
    checks = doctor.check_required_files()
    assert checks[0].status == "fail"


def test_yaml_parse_failure_fixture_is_blocked(tmp_path, monkeypatch):
    (tmp_path / "bad.yaml").write_text("x: [", encoding="utf-8")
    monkeypatch.setattr(doctor, "LV_ROOT", tmp_path)
    monkeypatch.setattr(doctor, "YAML_FILES", ["bad.yaml"])
    checks = doctor.check_yaml_files()
    assert checks[0].status == "fail"


def test_ndjson_schema_failure_fixture_is_blocked(tmp_path, monkeypatch):
    dev = tmp_path / "dev"
    dev.mkdir()
    (dev / "lv_revision_log.ndjson").write_text(json.dumps({"revision_id": "bad"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "LV_ROOT", tmp_path)
    check = doctor.check_revision_log_schema()
    assert check.status == "fail"


def test_readme_overclaim_fixture_is_blocked(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("This is unique globally.", encoding="utf-8")
    monkeypatch.setattr(doctor, "LV_ROOT", tmp_path)
    check = doctor.check_readme_overclaims()
    assert check.status == "fail"


def test_matrix_authority_failure_fixture_is_blocked(tmp_path, monkeypatch):
    matrix = tmp_path / "curriculum"
    matrix.mkdir()
    (matrix / "lingua_viva_matrix.yaml").write_text(
        "authority: authoritative\npromotion_status:\n  current_decision: Promote now.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "LV_ROOT", tmp_path)
    check = doctor.check_matrix_authority()
    assert check.status == "fail"


def test_gauntlet_failure_propagates(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="FAIL", stderr="")

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    check = doctor.check_artifact_gauntlet()
    assert check.status == "fail"


def test_branch_mismatch_blocks(monkeypatch):
    monkeypatch.setattr(doctor, "_git", lambda args: (0, "OTHER-BRANCH"))
    check = doctor.check_branch()
    assert check.status == "fail"


def test_dirty_worktree_is_visible(monkeypatch):
    monkeypatch.setattr(doctor, "_git", lambda args: (0, " M implementations/education/lingua-viva/README.md"))
    check = doctor.check_lingua_viva_worktree()
    assert check.status == "warn"


def test_privacy_risk_path_detection(tmp_path, monkeypatch):
    (tmp_path / "IEP-private-note.txt").write_text("not read by doctor", encoding="utf-8")
    monkeypatch.setattr(doctor, "LV_ROOT", tmp_path)
    check = doctor.check_privacy_paths()
    assert check.status == "private_risk"
