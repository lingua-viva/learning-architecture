from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import StudentLensStore
from src.lingua_viva.docpipe.lens_extract import resolve_import_log_path
from src.web import app


def _field_log(student_id: str) -> str:
    return json.dumps(
        {
            "student_id": student_id,
            "field_path": "grade_level",
            "value": "G5",
            "confidence": 0.99,
            "status": "verified",
            "supporting_chunk_ids": ["crafted#chunk-0000"],
        }
    ) + "\n"


def test_resolve_import_log_path_confines_to_imports_dir(tmp_path):
    allowed = tmp_path / "imports" / "ok.ndjson"
    allowed.parent.mkdir()
    allowed.write_text("", encoding="utf-8")
    outside = tmp_path / "outside.ndjson"
    outside.write_text("", encoding="utf-8")

    assert resolve_import_log_path(allowed, state_home=tmp_path) == allowed.resolve()
    try:
        resolve_import_log_path(outside, state_home=tmp_path)
    except ValueError as exc:
        assert "imports directory" in str(exc)
    else:
        raise AssertionError("outside import log was accepted")


def test_apply_extractions_rejects_client_supplied_path_outside_imports(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "lv-home"))
    db_path = tmp_path / "student_lenses.db"
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db_path))

    with StudentLensStore(db_path=db_path) as store:
        sid = store.create_lens(display_name="Security Probe", grade_level="G3")

    outside = tmp_path / "crafted.ndjson"
    outside.write_text(_field_log(sid), encoding="utf-8")

    response = TestClient(app).post(
        "/api/students/apply-extractions",
        json={"extraction_log_path": str(outside), "confirmed_students": [sid]},
    )

    assert response.status_code == 400
    with StudentLensStore(db_path=db_path) as store:
        assert store.get_lens(sid)["grade_level"] == "G3"
