"""Tests for src/lingua_viva/coursework_pack.py (W3, 2026-08-09).

PDFs go to tmp_path / LV_STATE_HOME-redirected dirs only — never
committed. Synthetic data only, per publication-policy.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.lingua_viva import coursework_pack as cwp


@pytest.fixture(autouse=True)
def _state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    yield


def test_build_pack_g3_has_units_and_tiered_activities():
    pack = cwp.build_pack("G3", activities_per_unit=2)
    assert pack["audience"] == "teacher"
    assert pack["cover"]["grade"] == "G3"
    assert pack["units"], "G3 must yield curriculum units"
    for unit in pack["units"]:
        assert len(unit["activities"]) == 2
        for activity in unit["activities"]:
            assert activity["draft"] is True  # honest auto-generated label
            assert activity["answer_key"]
            assert activity["teacher_notes"]
            tiers = activity["tiers"]
            assert set(tiers) == {"foundational", "on_track", "extended"}


def test_differentiation_produces_distinct_tier_content():
    pack = cwp.build_pack("G3", activities_per_unit=1)
    activity = pack["units"][0]["activities"][0]
    tiers = activity["tiers"]
    objectives = {t: tiers[t]["learning_objective"] for t in tiers}
    assert len(set(objectives.values())) == 3, "each tier needs its own objective"
    cefr = {t: tiers[t]["cefr_target"] for t in tiers}
    assert cefr["foundational"] != cefr["extended"]
    prompts = {
        t: json.dumps([task["prompt"] for task in tiers[t]["tasks"]]) for t in tiers
    }
    assert len(set(prompts.values())) == 3, "each tier needs its own tasks"


def test_unknown_grade_raises_keyerror():
    with pytest.raises(KeyError):
        cwp.build_pack("G99")
    with pytest.raises(KeyError):
        cwp.build_pack("G3", unit_id="g3-unit-does-not-exist")


def test_cefr_extraction_from_wording():
    assert cwp._cefr_from_wording("designed to target A2 consolidation") == "A2"
    assert cwp._cefr_from_wording("moving toward B1 readiness") == "B1"
    assert cwp._cefr_from_wording("growth toward A1+ fluency") == "A1+"
    assert cwp._cefr_from_wording("no band here") == "A2"  # honest default


def test_student_view_strips_teacher_only_material():
    pack = cwp.build_pack("G2", activities_per_unit=1)
    student = cwp.student_view(pack)
    assert student["audience"] == "student"
    for unit in student["units"]:
        assert "background_reading" not in unit
        assert "source_citation" not in unit
        for activity in unit["activities"]:
            assert "answer_key" not in activity
            assert "teacher_notes" not in activity
            assert "draft" not in activity
    # Master pack untouched (no mutation).
    assert pack["audience"] == "teacher"
    assert pack["units"][0]["activities"][0]["answer_key"]


def test_generate_class_pack_writes_pdfs_to_state_home(tmp_path, monkeypatch):
    state = tmp_path / "lv-state"
    monkeypatch.setenv("LV_STATE_HOME", str(state))
    result = cwp.generate_class_pack("G3", unit_id="g3-unit-1", activities_per_unit=2)
    assert result["unit_count"] == 1
    audiences = {f["audience"] for f in result["files"]}
    assert audiences == {"teacher", "student"}
    for entry in result["files"]:
        path = Path(entry["path"])
        assert path.is_file()
        assert str(path).startswith(str(state / "artifacts" / "coursework"))
        assert path.read_bytes().startswith(b"%PDF")
    teacher = next(f for f in result["files"] if f["audience"] == "teacher")
    student = next(f for f in result["files"] if f["audience"] == "student")
    # Answer key + notes + reading exist only in the teacher edition.
    assert teacher["bytes"] != student["bytes"]


def test_generate_class_pack_teacher_only(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "s2"))
    result = cwp.generate_class_pack(
        "G1", unit_id="g1-unit-1", include_student_version=False
    )
    assert [f["audience"] for f in result["files"]] == ["teacher"]


def test_background_reading_is_fail_soft_and_cited():
    pack = cwp.build_pack("G4", activities_per_unit=1)
    for unit in pack["units"]:
        reading = unit["background_reading"]
        assert isinstance(reading, list)
        for item in reading:
            assert item["title"]
            assert "citation" in item


def test_no_real_names_in_generated_pack_content():
    """Publication policy: generated coursework must never embed student
    or colleague names — it is class-level material only."""
    pack = cwp.build_pack("G5", activities_per_unit=3)
    blob = json.dumps(pack).lower()
    # Established synthetic fixture names must not leak in either (packs
    # are class-scoped, not student-scoped).
    for name in ("nora rossi", "marco bianchi", "rafael"):
        assert name not in blob


def test_download_artifact_serves_pdf_and_blocks_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.lingua_viva.pdf_generator import artifacts_dir
    import importlib
    import src.lingua_viva.routers.artifacts as artifacts_router
    importlib.reload(artifacts_router)

    out = artifacts_dir("coursework")
    (out / "pack_teacher.pdf").write_bytes(b"%PDF-1.4 fake")
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(b"%PDF-1.4 secret")

    app = FastAPI()
    app.include_router(artifacts_router.router)
    client = TestClient(app)

    ok = client.get("/api/artifacts/download", params={"kind": "coursework", "name": "pack_teacher.pdf"})
    assert ok.status_code == 200
    assert ok.content.startswith(b"%PDF")

    for kind, name in [
        ("coursework", "../../secret.pdf"),
        ("..", "secret.pdf"),
        ("coursework", "/etc/passwd"),
    ]:
        blocked = client.get("/api/artifacts/download", params={"kind": kind, "name": name})
        assert blocked.status_code in (403, 404), (kind, name)

    missing = client.get("/api/artifacts/download", params={"kind": "coursework", "name": "nope.pdf"})
    assert missing.status_code == 404
