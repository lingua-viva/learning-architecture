from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.lingua_viva.closing import CLOSING_CHECKS, format_report, run_closing
from src.lingua_viva.cli import main


def _completed(returncode: int = 0, stdout: str = "ok\n") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_closing_has_exactly_teacher_admin_release_gates():
    assert [check.id for check in CLOSING_CHECKS] == ["gauntlet", "pipeline", "artifacts", "preflight"]


def test_closing_commands_cover_expected_surfaces():
    commands = {check.id: check.command for check in CLOSING_CHECKS}

    assert commands["gauntlet"] == (sys.executable, "-m", "pytest", "tests/gauntlet", "-q")
    assert "tests/test_document_to_lens.py" in commands["pipeline"]
    assert "tests/test_document_import_security.py" in commands["pipeline"]
    assert "tests/test_lesson_plan_artifact.py" in commands["artifacts"]
    assert "tests/test_parent_report.py" in commands["artifacts"]
    assert commands["preflight"] == (sys.executable, "-m", "src.lv_cli", "preflight", "--json")


def test_run_closing_passes_when_all_commands_pass():
    seen: list[tuple[str, ...]] = []

    def runner(command, cwd: Path):
        seen.append(tuple(command))
        assert cwd.name == "learning-architecture"
        return _completed()

    report = run_closing(run_command=runner)

    assert report["verdict"] == "PASS"
    assert [check["status"] for check in report["checks"]] == ["PASS", "PASS", "PASS", "PASS"]
    assert len(seen) == 4


def test_run_closing_fails_on_failed_check():
    def runner(command, cwd: Path):
        if "tests/test_lesson_plan_artifact.py" in command:
            return _completed(returncode=1, stdout="lesson failure\n")
        return _completed()

    report = run_closing(run_command=runner)

    assert report["verdict"] == "FAIL"
    assert {check["id"]: check["status"] for check in report["checks"]}["artifacts"] == "FAIL"
    assert "artifacts: FAIL" in format_report(report)


def test_run_closing_rejects_unknown_only_check():
    report = run_closing(only={"missing"}, run_command=lambda command, cwd: _completed())

    assert report["verdict"] == "FAIL"
    assert report["checks"] == []
    assert report["unknown_checks"] == ["missing"]


def test_closing_cli_uses_runner(monkeypatch, capsys):
    def fake_run_closing(*, only=None):
        assert only == {"preflight"}
        return {
            "surface": "lv_closing",
            "verdict": "PASS",
            "duration_seconds": 0,
            "checks": [{"id": "preflight", "status": "PASS", "duration_seconds": 0}],
            "unknown_checks": [],
        }

    monkeypatch.setattr("src.lingua_viva.closing.run_closing", fake_run_closing)

    assert main(["closing", "--only", "preflight"]) == 0
    assert "preflight: PASS" in capsys.readouterr().out
