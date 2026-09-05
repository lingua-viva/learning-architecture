"""Operator's 2026-09-05 ruling: app updates never erase the teacher's work.

The v0.2.92 import log uses second-resolution timestamp + filename and opens
with 'w'. Reprocessing the same file in the same second loses the first run.
Its reload also discards the source chunks behind every citation.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import json

import pytest

from src.lingua_viva.data_in_contracts import ExtractedField, ExtractionResult, SourceChunk
from src.lingua_viva.docpipe import lens_extract


def result(level="A2"):
    return ExtractionResult(
        target_schema_id="student_lens",
        fields=[ExtractedField("cefr_snapshot.reading", level, 0.95, ["c1"], "verified")],
        unresolved_questions=[], source_files=["pagella.txt"],
        chunks_used=[SourceChunk("c1", "pagella.txt", f"Lettura: {level}", 0, len(f"Lettura: {level}"))],
    )


def test_same_name_same_second_keeps_both_processing_runs(tmp_path, monkeypatch):
    class FrozenTime:
        @staticmethod
        def now(tz):
            return datetime(2026, 9, 5, 4, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(lens_extract, "datetime", FrozenTime)
    first = lens_extract.save_extraction_log({"s-demo": result()}, "pagella.txt", tmp_path)
    before = first.read_bytes()
    second = lens_extract.save_extraction_log({"s-demo": result("B1")}, "pagella.txt", tmp_path)
    assert first != second, "the next run overwrites the previous teacher work"
    assert first.read_bytes() == before
    assert lens_extract.load_extraction_log(first)["s-demo"].fields[0].value == "A2"
    assert lens_extract.load_extraction_log(second)["s-demo"].fields[0].value == "B1"


def test_reload_preserves_source_chunks_and_empty_results(tmp_path):
    expected = result()
    empty = ExtractionResult("student_lens", [], [], ["pagella.txt"], [])
    path = lens_extract.save_extraction_log({"s-demo": expected, "s-empty": empty}, "pagella.txt", tmp_path)
    loaded = lens_extract.load_extraction_log(path)
    assert asdict(loaded["s-demo"]) == asdict(expected)
    assert asdict(loaded["s-empty"]) == asdict(empty)


def test_old_log_still_loads_without_reprocessing(tmp_path):
    path = tmp_path / "legacy.ndjson"
    path.write_text(json.dumps(dict(student_id="s-demo", field_path="cefr_snapshot.reading",
        value="A1", confidence=0.95, status="verified", supporting_chunk_ids=["old-c1"],
        source_filename="old.txt")) + "\n", encoding="utf-8")
    loaded = lens_extract.load_extraction_log(path)["s-demo"]
    assert loaded.fields[0].value == "A1"
    assert loaded.source_files == ["old.txt"]
    assert loaded.chunks_used == []


def test_original_bytes_remain_after_another_version_of_the_same_file(tmp_path):
    first = lens_extract.preserve_import_source(b"Lettura: A1", "pagella.txt", state_home=tmp_path)
    second = lens_extract.preserve_import_source(b"Lettura: A2", "pagella.txt", state_home=tmp_path)
    assert first.source_id != second.source_id
    for record, content in [(first, b"Lettura: A1"), (second, b"Lettura: A2")]:
        original = tmp_path / "vault" / "sources" / record.source_id / "original.txt"
        assert original.read_bytes() == content
    repeated = lens_extract.preserve_import_source(b"Lettura: A1", "pagella.txt", state_home=tmp_path)
    assert repeated.source_id == first.source_id


def test_failed_write_never_publishes_a_partial_import_log(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(lens_extract.os, "fsync", fail)
    with pytest.raises(OSError, match="disk full"):
        lens_extract.save_extraction_log({"s-demo": result()}, "pagella.txt", tmp_path)
    assert not list((tmp_path / "imports").glob("*.ndjson"))


def test_document_route_preserves_original_before_processing(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.education.student_lens import StudentLensStore
    from src.lingua_viva.docpipe import extract
    from src.web import app

    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    with_store = StudentLensStore()
    with_store.create_lens(student_id="s-demo", display_name="Demo Student")
    with_store.close()
    monkeypatch.setattr(extract, "classify_document_type", lambda *a: "student_report")
    content = b"Demo Student\nLettura: A2"

    async def processing(**kwargs):
        originals = list((tmp_path / "vault" / "sources").glob("*/original.txt"))
        assert len(originals) == 1 and originals[0].read_bytes() == content
        return {"s-demo": result()}
    monkeypatch.setattr(lens_extract, "extract_for_lens_update", processing)
    response = TestClient(app).post("/api/students/import-document", files={"file": ("pagella.txt", content, "text/plain")})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source_record_id"].startswith("SRC-IMPORT-")
    from pathlib import Path
    rows = [json.loads(row) for row in Path(payload["extraction_log_path"]).read_text(encoding="utf-8").splitlines()]
    assert all(row["source_id"] == payload["source_record_id"] for row in rows)


def test_document_route_names_storage_failure_without_processing(monkeypatch):
    from fastapi.testclient import TestClient
    from src.web import app

    def full(*args, **kwargs):
        raise OSError("sensitive internal filesystem path")
    monkeypatch.setattr(lens_extract, "preserve_import_source", full)
    response = TestClient(app).post("/api/students/import-document", files={"file": ("pagella.txt", b"Demo Student\nReading: A2", "text/plain")})
    assert response.status_code == 503
    assert response.json()["error"] == "source_not_saved"
    assert "sensitive internal" not in response.text


def test_retained_sources_and_runs_honour_state_home_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "configuration"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "workspace"))
    source = lens_extract.preserve_import_source(b"Lettura: A2", "pagella.txt")
    log = lens_extract.save_extraction_log({"s-demo": result()}, "pagella.txt", source_id=source.source_id)
    assert log.is_relative_to(tmp_path / "workspace")
    assert (tmp_path / "workspace" / "vault" / "sources" / source.source_id / "original.txt").exists()
    assert not (tmp_path / "configuration").exists()
