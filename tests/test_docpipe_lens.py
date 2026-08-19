from __future__ import annotations

import json
from pathlib import Path

from src.education.student_lens import StudentLensStore
from src.lingua_viva.docpipe import lens, vault
from src.lingua_viva.docpipe.contracts import ExtractionRecord, ObservationRecord


FIXTURES = Path(__file__).parent / "fixtures" / "docpipe"


def _load(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _observation(obs_id: str, claims: list[dict]) -> ObservationRecord:
    return ObservationRecord(
        {
            "schema_version": "docpipe.observation.v1",
            "obs_id": obs_id,
            "student_id": "student-nora-rossi",
            "created_at": "2026-08-04T09:00:00Z",
            "created_by": "teacher:olga",
            "raw_transcript": "Synthetic teacher observation for Nora Rossi.",
            "teacher_edited_text": "Synthetic teacher observation for Nora Rossi.",
            "claims": claims,
        }
    )


def _assert_no_ungrounded_fields(record) -> None:
    for field in record.data["profile"].values():
        value = field["value"]
        evidence = field["evidence"]
        if value in (None, "", [], {}):
            assert evidence == []
        else:
            assert evidence


def test_create_from_extraction_builds_grounded_scaffold(tmp_path: Path) -> None:
    extraction = ExtractionRecord(_load("expected_extraction_lesson_plan_marco_nora.json"))

    record = lens.create_from_extraction(
        extraction,
        student_id="student-nora-rossi",
        student_name="Nora Rossi",
        added_by="teacher:federica",
        root=tmp_path,
    )

    profile = record.data["profile"]
    assert profile["communication_and_language"]["evidence"][0]["span_id"] == "SPN-0006"
    assert profile["academic_strengths"]["evidence"][0]["source_ref"]["type"] == "DOCUMENT"
    assert profile["learning_and_cognition"]["value"] is None
    assert vault.get_lens("student-nora-rossi", root=tmp_path).data == record.data
    _assert_no_ungrounded_fields(record)


def test_merge_three_observations_accumulates_evidence_without_loss(tmp_path: Path) -> None:
    extraction = ExtractionRecord(_load("expected_extraction_student_work_nora_rossi.json"))
    record = lens.create_from_extraction(
        extraction,
        student_id="student-nora-rossi",
        student_name="Nora Rossi",
        added_by="teacher:federica",
        root=tmp_path,
    )
    initial_comm_evidence = len(record.data["profile"]["communication_and_language"]["evidence"])

    observations = [
        _observation(
            "OBS-NORA-T4-001",
            [
                {
                    "field_id": "communication_and_language",
                    "value": "Explained the quotation clearly to a peer.",
                    "confidence": 0.9,
                }
            ],
        ),
        _observation(
            "OBS-NORA-T4-002",
            [
                {
                    "field_id": "strategies_trialed",
                    "value": {
                        "strategy": "Sentence starter card",
                        "outcome": "worked",
                        "evidence": "Helped organize the second quotation.",
                    },
                    "confidence": 0.88,
                }
            ],
        ),
        _observation(
            "OBS-NORA-T4-003",
            [
                {
                    "field_id": "personal_strengths",
                    "value": "Waited for Marco to finish before adding her idea.",
                    "confidence": 0.92,
                }
            ],
        ),
    ]
    for observation in observations:
        record = lens.merge_observation(
            record,
            observation,
            added_by="teacher:olga",
            root=tmp_path,
        )

    assert len(record.data["profile"]["communication_and_language"]["evidence"]) == initial_comm_evidence + 1
    assert record.data["profile"]["strategies_trialed"]["evidence"][0]["source_ref"]["type"] == "OBSERVATION"
    assert record.data["profile"]["personal_strengths"]["evidence"][0]["obs_id"] == "OBS-NORA-T4-003"
    assert set(record.data["metadata"]["observation_ids"]) == {
        "OBS-NORA-T4-001",
        "OBS-NORA-T4-002",
        "OBS-NORA-T4-003",
    }
    assert len(record.data["metadata"]["merge_events"]) == 4
    _assert_no_ungrounded_fields(record)


def test_document_and_observation_contradictions_are_retained(tmp_path: Path) -> None:
    extraction = ExtractionRecord(_load("expected_extraction_student_work_nora_rossi.json"))
    record = lens.create_from_extraction(
        extraction,
        student_id="student-nora-rossi",
        student_name="Nora Rossi",
        added_by="teacher:federica",
        root=tmp_path,
    )

    record = lens.merge_observation(
        record,
        _observation(
            "OBS-NORA-T4-CONFLICT",
            [
                {
                    "field_id": "communication_and_language",
                    "value": "Needed support explaining the quotation orally today.",
                    "confidence": 0.95,
                }
            ],
        ),
        added_by="teacher:olga",
        root=tmp_path,
    )

    field = record.data["profile"]["communication_and_language"]
    assert isinstance(field["value"], list)
    assert len(field["evidence"]) == 2
    assert {item["source_ref"]["type"] for item in field["evidence"]} == {
        "DOCUMENT",
        "OBSERVATION",
    }


def test_bridge_populates_student_lens_store_without_duplicate_sync(tmp_path: Path) -> None:
    store = StudentLensStore(db_path=tmp_path / "student_lenses.db")
    try:
        extraction = ExtractionRecord(_load("expected_extraction_student_work_nora_rossi.json"))
        record = lens.create_from_extraction(
            extraction,
            student_id="student-nora-rossi",
            student_name="Nora Rossi",
            added_by="teacher:federica",
            root=tmp_path / "vault",
            student_store=store,
        )
        record = lens.merge_observation(
            record,
            _load_observation_fixture(),
            added_by="teacher:olga",
            root=tmp_path / "vault",
            student_store=store,
        )
        synced_once = set(record.data["metadata"]["student_store_sync"]["synced_evidence_keys"])
        record = lens.sync_to_student_lens_store(
            record,
            store,
            root=tmp_path / "vault",
        )
        assert set(record.data["metadata"]["student_store_sync"]["synced_evidence_keys"]) == synced_once

        ui_lens = store.get_lens("student-nora-rossi")
        assert ui_lens["display_name"] == "Nora Rossi"
        comm_evidence = ui_lens["support_profile"]["categories"]["communication_and_language"]["evidence"]
        assert comm_evidence
        strengths = ui_lens["strengths_profile"]["personal_strengths"]
        assert len(strengths) == 1
        assert strengths[0]["source_observation_id"] == "OBS-NORA-20260804-01"
    finally:
        store.close()


def _load_observation_fixture() -> ObservationRecord:
    return ObservationRecord(_load("observation_nora_rossi.json"))


def test_ingest_registers_student_on_teacher_roster(tmp_path: Path) -> None:
    """Prepare-fix P3b: importing a document about a student puts that
    student on the ingesting teacher's roster, so Prepare's group split
    sees the class without requiring a first observation."""
    store = StudentLensStore(db_path=tmp_path / "student_lenses.db")
    try:
        extraction = ExtractionRecord(_load("expected_extraction_student_work_nora_rossi.json"))
        lens.create_from_extraction(
            extraction,
            student_id="student-nora-rossi",
            student_name="Nora Rossi",
            added_by="teacher:federica",
            root=tmp_path / "vault",
            student_store=store,
        )
        # A second student exists but was never ingested by this teacher.
        store.create_lens(student_id="student-other", display_name="Other")

        roster = store.list_lenses_for_teacher("teacher:federica")
        assert [item["student_id"] for item in roster] == ["student-nora-rossi"]
        row = store._conn.execute(
            "SELECT source FROM teacher_roster WHERE teacher_id = ? AND student_id = ?",
            ("teacher:federica", "student-nora-rossi"),
        ).fetchone()
        assert row["source"] == "ingest"
    finally:
        store.close()
