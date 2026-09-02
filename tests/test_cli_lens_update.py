from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.education.student_lens import StudentLensStore
from src.lingua_viva import cli


@pytest.fixture()
def lv_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "lv-home"
    monkeypatch.setenv("LV_CONFIG_HOME", str(home))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(home / "runtime" / "student_lenses.db"))
    monkeypatch.setattr(
        cli,
        "ReasoningEngine",
        lambda: (_ for _ in ()).throw(RuntimeError("no model in CLI tests")),
    )
    return home


def _seed_student(student_id: str = "s-abigail", name: str = "Abigail Chang") -> None:
    with StudentLensStore() as store:
        store.create_lens(student_id=student_id, display_name=name, grade_level="G3")


def _report(path: Path, name: str = "Abigail Chang") -> Path:
    path.write_text(
        f"{name}\n"
        "Progress report\n"
        "Reading: A2. Writing: A1. Speaking: A1+. "
        "Beginning progress is visible in number sense. "
        "Strong number sense and mathematical problem-solving.",
        encoding="utf-8",
    )
    return path


def test_lens_update_preview_only_writes_nothing(
    lv_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    _seed_student()
    report = _report(tmp_path / "Abigail_Chang_report.txt")

    code = cli.main(["lens-update", str(report), "--preview-only"])

    assert code == 0
    out = capsys.readouterr().out
    assert "lens-update: Abigail_Chang_report.txt" in out
    assert "Fields:" in out
    with StudentLensStore() as store:
        lens = store.get_lens("s-abigail")
    assert lens["support_profile"]["categories"]["learning_and_cognition"]["evidence"] == []


def test_lens_update_nonexistent_file_exits_1(
    lv_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    code = cli.main(["lens-update", str(tmp_path / "missing.pdf")])

    assert code == 1
    assert "does not exist or is not a file" in capsys.readouterr().out


def test_lens_update_class_list_exits_0(
    lv_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    _seed_student()
    roster = tmp_path / "class_roster.csv"
    roster.write_text(
        "student,name,class\n"
        "1,Abigail Chang,G3\n"
        "2,Marco Bianchi,G3\n"
        "3,Nora Rossi,G3\n"
        "4,Luca Scala,G3\n",
        encoding="utf-8",
    )

    code = cli.main(["lens-update", str(roster)])

    assert code == 0
    assert "use roster import instead" in capsys.readouterr().out


def test_lens_update_single_file_e2e(
    lv_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _seed_student()
    report = _report(tmp_path / "Abigail_Chang_report.txt")
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")

    code = cli.main(["lens-update", str(report)])

    assert code == 0
    out = capsys.readouterr().out
    assert "Updated 1 student lens(es)" in out
    with StudentLensStore() as store:
        lens = store.get_lens("s-abigail")
    evidence = lens["support_profile"]["categories"]["learning_and_cognition"]["evidence"]
    assert evidence


def test_lens_update_json_output(
    lv_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    _seed_student()
    report = _report(tmp_path / "Abigail_Chang_report.txt")

    code = cli.main(["lens-update", str(report), "--preview-only", "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["file"] == "Abigail_Chang_report.txt"
    assert payload[0]["document_type"] == "student_report"
    assert payload[0]["students"][0]["student_id"] == "s-abigail"
    assert payload[0]["students"][0]["fields"]


def test_lens_update_student_filter(
    lv_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    _seed_student("s-abigail", "Abigail Chang")
    _seed_student("s-marco", "Marco Bianchi")
    report = _report(tmp_path / "generic_report.txt", name="Class summary")

    code = cli.main([
        "lens-update",
        str(report),
        "--preview-only",
        "--student",
        "s-marco",
        "--json",
    ])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["students"][0]["student_id"] == "s-marco"
    assert payload[0]["students"][0]["display_name"] == "Marco Bianchi"
