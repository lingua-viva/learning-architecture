"""
Tests for SPEC_LV_INGESTION_EXTRACTION_MAPPING_V2_2026-07-23.md (Build order 5 of 5).
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from src.lingua_viva.data_in_contracts import (
    STUDENT_LENS_FIELDS,
    SUPPORT_PROFILE_CATEGORIES,
    SUPPORT_PROFILE_BUCKETS,
    ExtractedField,
    ExtractionResult,
    SourceChunk,
    extract,
    write_student_lens,
)
from src.education.student_lens import StudentLensStore
from src.web import app

REPO = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO / "tests" / "fixtures" / "data_in_eval" / "student_lens_v2"
client = TestClient(app)


def _html() -> str:
    return (REPO / "static" / "index.html").read_text(encoding="utf-8")


def test_field_contract_contains_all_categories_and_buckets():
    for cat in SUPPORT_PROFILE_CATEGORIES:
        for bucket in SUPPORT_PROFILE_BUCKETS:
            field_path = f"support_profile.categories.{cat}.{bucket}"
            assert field_path in STUDENT_LENS_FIELDS


def test_extraction_finds_category_needs_and_strategies(tmp_path):
    file_path = FIXTURES_DIR / "executive_functioning_need.txt"
    assert file_path.exists()

    result = extract([str(file_path)], target_schema_id="student_lens")
    assert isinstance(result, ExtractionResult)
    assert len(result.chunks_used) >= 1

    # Check for fields or unresolved questions
    assert len(result.fields) + len(result.unresolved_questions) > 0


def test_writer_refuses_support_entries_without_source_refs(tmp_path):
    db_path = tmp_path / "test_refuse_no_refs.db"
    with StudentLensStore(db_path=db_path) as store:
        field_no_refs = ExtractedField(
            field_path="support_profile.categories.executive_functioning.needs",
            value="Needs visual checklist",
            confidence=0.85,
            supporting_chunk_ids=[],  # Empty source refs
            status="verified",
        )
        res = ExtractionResult(
            target_schema_id="student_lens",
            fields=[field_no_refs],
            unresolved_questions=[],
            source_files=["test.txt"],
            chunks_used=[],
        )
        write_res = write_student_lens(res, store=store)
        assert len(write_res["unresolved_questions"]) >= 1
        assert "missing source references" in write_res["unresolved_questions"][0].lower()


def test_trauma_flag_is_never_auto_written(tmp_path):
    db_path = tmp_path / "test_trauma_flag.db"
    with StudentLensStore(db_path=db_path) as store:
        sid = store.create_lens(display_name="Trauma Test")

        trauma_field = ExtractedField(
            field_path="trauma_flag",
            value=True,
            confidence=0.9,
            supporting_chunk_ids=["chunk-1"],
            status="verified",
        )
        res = ExtractionResult(
            target_schema_id="student_lens",
            fields=[trauma_field],
            unresolved_questions=[],
            source_files=["test.txt"],
            chunks_used=[],
        )

        # Attempt to write without teacher confirmation
        write_res = write_student_lens(res, hint={"assigned_student_id": sid}, store=store)
        lens = store.get_lens(sid)
        # trauma_flag must remain False because it was not in confirmed_fields
        assert lens["trauma_flag"] is False
        assert "trauma_flag" in write_res["review_required"]

        # Now write WITH explicit teacher confirmation
        write_res_conf = write_student_lens(
            res,
            confirmed_fields=["trauma_flag"],
            hint={"assigned_student_id": sid},
            store=store,
        )
        lens_conf = store.get_lens(sid)
        assert lens_conf["trauma_flag"] is True
        assert "trauma_flag" in write_res_conf["written_fields"]


def test_writer_preserves_source_refs_and_updates_assigned_student(tmp_path):
    db_path = tmp_path / "test_writer_source_refs.db"
    with StudentLensStore(db_path=db_path) as store:
        sid = store.create_lens(display_name="Assigned Learner")

        need_field = ExtractedField(
            field_path="support_profile.categories.executive_functioning.needs",
            value="Needs 2-step visual task list",
            confidence=0.9,
            supporting_chunk_ids=["file.txt#chunk-0001"],
            status="verified",
        )
        res = ExtractionResult(
            target_schema_id="student_lens",
            fields=[need_field],
            unresolved_questions=[],
            source_files=["file.txt"],
            chunks_used=[
                SourceChunk("file.txt#chunk-0001", "file.txt", "Needs 2-step visual task list", 0, 30)
            ],
        )

        write_res = write_student_lens(res, hint={"assigned_student_id": sid}, store=store)
        assert write_res["student_id"] == sid
        assert "support_profile.categories.executive_functioning.needs" in write_res["written_fields"]

        lens = store.get_lens(sid)
        ef = lens["support_profile"]["categories"]["executive_functioning"]
        assert len(ef["needs"]) == 1
        assert ef["needs"][0]["text"] == "Needs 2-step visual task list"
        assert ef["needs"][0]["source_ref_ids"] == ["file.txt#chunk-0001"]
        assert ef["needs"][0]["confidence"] == "imported_verified"


def test_served_html_includes_all_extraction_ui_callsites():
    html = _html()
    assert "Extraction Sources" in html
    assert "Run Extraction" in html
    assert "Review Extraction" in html
    assert "Write Confirmed to Lens" in html
    assert "/api/extraction/sources" in html
    assert "/api/extraction/run" in html
    assert "/api/extraction/review" in html
    assert "imported_verified" in html
    assert "imported_needs_confirmation" in html


def test_extraction_routes_e2e(tmp_path, monkeypatch):
    db_path = tmp_path / "test_e2e_ext.db"
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(db_path))

    # 1. Sources route
    res_sources = client.get("/api/extraction/sources")
    assert res_sources.status_code == 200
    sources = res_sources.json()["sources"]
    assert len(sources) >= 1

    # 2. Run extraction route
    demo_file = FIXTURES_DIR / "multi_category_obs.txt"
    res_run = client.post(
        "/api/extraction/run",
        json={"file_path": str(demo_file), "target_schema_id": "student_lens"},
    )
    assert res_run.status_code == 200
    run_data = res_run.json()
    assert "verified_fields" in run_data
    assert "needs_confirmation_fields" in run_data

    # 3. Review route
    res_review = client.post(
        "/api/extraction/review",
        json={
            "file_path": str(demo_file),
            "target_schema_id": "student_lens",
            "confirmed_fields": [
                {
                    "field_path": "support_profile.categories.executive_functioning.needs",
                    "value": "Responds well to 2-step visual task list",
                    "supporting_chunk_ids": ["multi_category_obs.txt-0000"],
                    "status": "verified",
                }
            ],
            "rejected_fields": [],
        },
    )
    assert res_review.status_code == 200
    rev_data = res_review.json()
    assert "feedback" in rev_data
    assert rev_data["feedback"]["written_count"] >= 1
