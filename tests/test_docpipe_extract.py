"""T3 — grounded extraction (SPEC_T3_EXTRACTION_2026-08-04).

The forced-hallucination test is the point of the workstream: a model claim
whose cited span does not support it must be DROPPED, never demoted.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.lingua_viva.docpipe import jobs, vault
from src.lingua_viva.docpipe.contracts import SourceRecord
from src.lingua_viva.docpipe.extract import extract_document
from src.lingua_viva.docpipe.grounding_docs import verify_extraction
from src.lingua_viva.docpipe.model import ModelResult

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "docpipe"


def _source(fixture_source: str, fixture_content: str) -> tuple[SourceRecord, bytes]:
    data = json.loads((FIXTURES / fixture_source).read_text(encoding="utf-8"))
    content = (FIXTURES / fixture_content).read_bytes()
    return SourceRecord(data), content


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# --- Fixture parity (grounding pass rate must be 100%) -------------------------


def test_lesson_plan_fixture_parity():
    expected = json.loads(
        (FIXTURES / "expected_extraction_lesson_plan_marco_nora.json").read_text(encoding="utf-8")
    )
    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    record = _run(extract_document(source, content))
    data = record.data

    assert data["normalized_text"] == expected["normalized_text"]
    assert data["spans"] == expected["spans"]
    assert data["structure"]["title"] == expected["structure"]["title"]
    assert data["structure"]["document_type"] == expected["structure"]["document_type"]
    assert data["structure"]["sections"] == expected["structure"]["sections"]
    assert data["structure"]["students_detected"] == expected["structure"]["students_detected"]
    assert data["structure"]["curriculum"] == expected["structure"]["curriculum"]
    assert data["language"] == expected["language"]
    assert data["source_sha256"] == source.data["sha256"]

    report = verify_extraction(data)
    assert report.ok and not report.dropped, f"grounding pass rate below 100%: {report}"


def test_student_work_fixture_parity():
    expected = json.loads(
        (FIXTURES / "expected_extraction_student_work_nora_rossi.json").read_text(encoding="utf-8")
    )
    source, content = _source("source_student_work_nora_rossi.json", "student_work_nora_rossi.md")
    record = _run(extract_document(source, content))
    data = record.data

    assert data["normalized_text"] == expected["normalized_text"]
    assert data["spans"] == expected["spans"]
    assert data["structure"]["title"] == expected["structure"]["title"]
    assert data["structure"]["document_type"] == expected["structure"]["document_type"]
    assert data["structure"]["sections"] == expected["structure"]["sections"]
    assert data["structure"]["students_detected"] == expected["structure"]["students_detected"]
    assert data["structure"]["curriculum"] == expected["structure"]["curriculum"]

    report = verify_extraction(data)
    assert report.ok and not report.dropped


def test_extraction_is_schema_valid():
    from src.lingua_viva.docpipe.validate import validate_file

    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    record = _run(extract_document(source, content))
    out = FIXTURES.parent / ".." / ".tmp-extract-check.json"
    out = out.resolve()
    out.write_text(json.dumps(record.data), encoding="utf-8")
    try:
        # validator infers schema by filename shape; write into an extracted/ shape
        pass
    finally:
        out.unlink(missing_ok=True)
    # direct schema check through the vault write path instead:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault.put_source(source, content, root=root)
        vault.put_extraction(record, root=root)  # raises if schema-invalid
        assert (root / "extracted" / f"{source.source_id}.json").exists()


# --- THE hallucination test ----------------------------------------------------


class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    async def complete(self, prompt, *, system_prompt=None, context=None, max_tokens=2000):
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else self.replies_default
        return ModelResult(content=reply, confidence=0.9, model_used="scripted")


def test_hallucinated_student_is_dropped_not_demoted():
    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    model = ScriptedModel([json.dumps({
        "students": [
            {"display_name": "Giulia Ferrari", "span_id": "SPN-0003"},   # span has no such name
            {"display_name": "Luca Verdi", "span_id": "SPN-9999"},       # span does not exist
        ]
    })])
    record = _run(extract_document(source, content, model_client=model))
    names = [s["display_name"] for s in record.data["structure"]["students_detected"]]
    assert "Giulia Ferrari" not in names
    assert "Luca Verdi" not in names
    assert names == ["Marco Bianchi", "Nora Rossi"]  # deterministic finds intact
    dropped = [w for w in record.data["warnings"] if w.startswith("grounding_dropped:model_student:")]
    assert len(dropped) == 2
    # No lowered-confidence survivors: every remaining entry is fully supported.
    assert verify_extraction(record.data).ok


def test_supported_model_student_is_added_with_lower_confidence():
    source, content = _source("source_student_work_nora_rossi.json", "student_work_nora_rossi.md")
    # SPN-0004 really contains no student name; SPN-0003 contains "Nora" (already found).
    # Give the model a claim that IS supported: cite SPN-0001 for Nora Rossi (dupe → ignored),
    # then verify a genuinely-new supported name in a synthetic doc instead.
    # Lowercase in the document → invisible to the capitalized-bigram
    # detector; only the model can claim it, and the claim IS span-supported
    # (verification is case/accent-folded).
    synthetic = (
        "# Class list\n\nRoster: G3 Italian\n\nnew arrival: ada colombo\n\nMarco Bianchi\n\n"
    ).encode("utf-8")
    src = SourceRecord({**json.loads((FIXTURES / "source_student_work_nora_rossi.json").read_text()),
                        "sha256": __import__("hashlib").sha256(synthetic).hexdigest()})
    model = ScriptedModel([json.dumps({
        "students": [{"display_name": "Ada Colombo", "span_id": "SPN-0003"}]
    })])
    record = _run(extract_document(src, synthetic, model_client=model))
    by_name = {s["display_name"]: s for s in record.data["structure"]["students_detected"]}
    assert "Ada Colombo" in by_name
    assert by_name["Ada Colombo"]["confidence"] == 0.7
    assert verify_extraction(record.data).ok


def test_malformed_model_json_retries_then_degrades_honestly():
    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    model = ScriptedModel(["I think the students are Marco and Nora!", "still not json"])
    record = _run(extract_document(source, content, model_client=model))
    assert model.calls == 2
    assert any(w.startswith("model_enrichment_discarded") for w in record.data["warnings"])
    assert [s["display_name"] for s in record.data["structure"]["students_detected"]] == [
        "Marco Bianchi", "Nora Rossi",
    ]


# --- Span integrity + offline + formats ---------------------------------------


def test_spans_slice_back_exactly():
    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    record = _run(extract_document(source, content))
    text = record.data["normalized_text"]
    for span in record.data["spans"]:
        assert span["text"] == text[span["char_start"]:span["char_end"]]


def test_tampered_span_fails_verification():
    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    record = _run(extract_document(source, content))
    record.data["spans"][0]["char_end"] += 3
    report = verify_extraction(record.data)
    assert not report.ok
    assert any("span_integrity" in e for e in report.errors)


def test_offline_no_model_is_fully_deterministic_with_warning():
    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    record = _run(extract_document(source, content, model_client=None))
    assert record.data["extractor"]["model"] is None
    assert any(w.startswith("model_enrichment_unavailable") for w in record.data["warnings"])
    assert len(record.data["structure"]["students_detected"]) == 2


def test_unsupported_format_fails_honestly():
    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    bad = SourceRecord({**source.data, "mime": "image/png", "original_ext": ".png"})
    with pytest.raises(ValueError, match="unsupported format"):
        _run(extract_document(bad, b"\x89PNG..."))


# --- Job runner ----------------------------------------------------------------


def _seed_vault(root: Path) -> str:
    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    vault.put_source(source, content, root=root)
    return source.source_id


def test_job_runs_to_done_and_writes_extraction(tmp_path):
    source_id = _seed_vault(tmp_path)
    job = _run(jobs.run_extraction_job(source_id, root=tmp_path))
    assert job["status"] == "done", job
    assert "2 students detected" in job["progress"]["detail"]
    assert (tmp_path / "extracted" / f"{source_id}.json").exists()
    on_disk = jobs.job_status(job["job_id"], root=tmp_path)
    assert on_disk["status"] == "done"


def test_crashed_job_resumes_to_done_without_partials(tmp_path):
    source_id = _seed_vault(tmp_path)
    # Simulate the app dying mid-job: a job record stuck in "running".
    stuck = jobs._new_job(source_id)
    stuck["status"] = "running"
    jobs._write_job(stuck, tmp_path)
    assert not (tmp_path / "extracted" / f"{source_id}.json").exists()

    resumed = _run(jobs.resume_pending(root=tmp_path))
    assert len(resumed) == 1
    assert resumed[0]["status"] == "done"
    assert (tmp_path / "extracted" / f"{source_id}.json").exists()
    # exactly one extraction file, no temp leftovers
    files = list((tmp_path / "extracted").iterdir())
    assert [f.name for f in files] == [f"{source_id}.json"]


def test_job_failure_is_honest(tmp_path):
    job = _run(jobs.run_extraction_job("SRC-DOES-NOT-EXIST", root=tmp_path))
    assert job["status"] == "failed"
    assert job["error"]
