from __future__ import annotations

from src.lingua_viva.sources.ledger import compute_source_record_id, now_iso, read_observations, read_records, upsert
from src.lingua_viva.sources.schema import SourceRecord


def _record(source_type: str, student_data: bool = False) -> SourceRecord:
    observed_at = now_iso()
    source_id = compute_source_record_id(source_type, "source", "container", "record")
    return SourceRecord(
        source_record_id=source_id,
        source_type=source_type,
        source_id="source",
        container="container",
        record_id="record",
        title=f"{source_type} record",
        uri=f"{source_type}://record",
        retrieval_scope="metadata",
        created_at=observed_at,
        observed_at=observed_at,
        provenance="capture" if source_type == "slack" else "scan",
        student_data=student_data,
        content_hash="h1",
    )


def test_source_record_id_is_stable():
    assert compute_source_record_id("local", "a", "b", "c") == compute_source_record_id("local", "a", "b", "c")
    assert compute_source_record_id("local", "a", "b", "c") != compute_source_record_id("drive", "a", "b", "c")


def test_upsert_dedups_current_records(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    record = _record("local")
    upsert(record)
    upsert(record)
    records = read_records("local")
    assert len(records) == 1
    assert records[0]["source_record_id"] == record.source_record_id
    assert len(read_observations(record.source_record_id)) == 1


def test_all_source_types_and_student_data_policy(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    for source_type in ("local", "drive", "slack"):
        upsert(_record(source_type, student_data=source_type == "slack"))
    records = {r["source_type"]: r for r in read_records(limit=10)}
    assert set(records) == {"local", "drive", "slack"}
    assert records["slack"]["student_data"] is True
    assert records["slack"]["policy"]["model_context_allowed"] is False
    assert records["slack"]["policy"]["external_allowed"] is False
