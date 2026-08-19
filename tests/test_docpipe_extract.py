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


def test_xlsx_roster_extracts_cell_text():
    from io import BytesIO

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["First", "Last"])
    sheet.append(["Marco", "Bianchi"])
    sheet.append(["Nora", "Rossi"])
    buffer = BytesIO()
    workbook.save(buffer)
    source, _ = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    xlsx = SourceRecord({
        **source.data,
        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "original_ext": ".xlsx",
    })

    record = _run(extract_document(xlsx, buffer.getvalue()))

    assert "Marco Bianchi" in record.data["normalized_text"]
    assert "Nora Rossi" in record.data["normalized_text"]
    names = [s["display_name"] for s in record.data["structure"]["students_detected"]]
    assert names == ["Marco Bianchi", "Nora Rossi"]


def test_docx_roster_extracts_paragraph_and_table_text():
    from io import BytesIO

    import docx

    document = docx.Document()
    document.add_paragraph("Class List")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "First"
    table.rows[0].cells[1].text = "Last"
    for first, last in [("Marco", "Bianchi"), ("Nora", "Rossi")]:
        cells = table.add_row().cells
        cells[0].text = first
        cells[1].text = last
    buffer = BytesIO()
    document.save(buffer)
    source, _ = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    word = SourceRecord({
        **source.data,
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "original_ext": ".docx",
    })

    record = _run(extract_document(word, buffer.getvalue()))

    assert "Class List" in record.data["normalized_text"]
    names = [s["display_name"] for s in record.data["structure"]["students_detected"]]
    assert names == ["Marco Bianchi", "Nora Rossi"]


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


# --- Support xlsx (FIX_SUPPORT_XLSX_LENS_PARSING 2026-08-18) -------------------


def _support_workbook_bytes():
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Classroom Accommodations"
    ws1.append(["Student Name", "Accommodation"])
    ws1.append(["Marco Bianchi", "Extended time on assessments"])
    ws1.append(["Nora Rossi", "Preferential seating"])
    ws2 = wb.create_sheet("External Support")
    ws2.append(["Student Name", "Provider", "Service"])
    ws2.append(["Marco Bianchi", "Dr. Smith", "Speech therapy"])
    ws3 = wb.create_sheet("Educational Evaluation")
    ws3.append(["Student Name", "Date", "Summary"])
    ws3.append(["Nora Rossi", "2026-03-15", "Cognitive assessment complete"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _support_source() -> SourceRecord:
    source, _ = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    return SourceRecord({
        **source.data,
        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "original_ext": ".xlsx",
        "original_filename": "3V ES Student Support .xlsx",
    })


def test_support_xlsx_detects_students_not_sheet_names():
    """Multi-sheet support xlsx: real students detected, sheet names are NOT."""
    record = _run(extract_document(_support_source(), _support_workbook_bytes()))

    names = [s["display_name"] for s in record.data["structure"]["students_detected"]]
    assert "Marco Bianchi" in names
    assert "Nora Rossi" in names
    assert "Classroom Accommodations" not in names
    assert "External Support" not in names
    assert "Educational Evaluation" not in names
    assert record.data["structure"]["document_type"] == "student_support"
    # Spans carry field hints mapping into lens profile fields
    hints = {s.get("field_hint") for s in record.data["spans"] if s.get("field_hint")}
    assert "learning_and_cognition" in hints
    assert "communication_and_language" in hints


def test_support_xlsx_passes_grounding_gate():
    """field_hint is additive — every span is still an exact slice and every
    detected student is supported by cited spans (nothing dropped)."""
    record = _run(extract_document(_support_source(), _support_workbook_bytes()))
    report = verify_extraction(record.data)
    assert report.ok, report.errors
    assert not report.dropped


def test_support_xlsx_spans_feed_lens_fields():
    """The field_hint routes each row into the mapped lens field."""
    from src.lingua_viva.docpipe.lens import _fields_for_span

    record = _run(extract_document(_support_source(), _support_workbook_bytes()))
    marco_spans = [
        s for s in record.data["spans"] if "Marco Bianchi" in str(s.get("text"))
    ]
    assert marco_spans
    for span in marco_spans:
        fields = _fields_for_span(str(span.get("text") or ""), span=span)
        assert fields == [span["field_hint"]]


def test_plain_roster_xlsx_still_uses_generic_path():
    """A single-sheet roster ("Sheet") must not flip to the support path."""
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["First", "Last"])
    ws.append(["Marco", "Bianchi"])
    buf = BytesIO()
    wb.save(buf)
    source, _ = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    xlsx = SourceRecord({
        **source.data,
        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "original_ext": ".xlsx",
    })
    record = _run(extract_document(xlsx, buf.getvalue()))
    assert record.data["structure"]["document_type"] != "student_support"
    assert not any(s.get("field_hint") for s in record.data["spans"])


# --- STEP 1: structure survives extraction (SPEC_LV_UNIFIED_REAL_DATA_FIX §STEP 1)


SYNTHETIC_CORPUS = Path(__file__).parent / "fixtures" / "docpipe" / "synthetic-corpus"


def _xlsx_source(filename: str) -> SourceRecord:
    source, _ = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    return SourceRecord({
        **source.data,
        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "original_ext": ".xlsx",
        "original_filename": filename,
    })


def test_xlsx_rows_become_individual_spans_not_one_sheet_blob():
    """The 3V-shaped fixture yields one span per row (7: header + 6
    students), not 1 span for the whole sheet — the L9 failure."""
    content = (SYNTHETIC_CORPUS / "synthetic_support_3v.xlsx").read_bytes()
    record = _run(extract_document(_xlsx_source("synthetic_support_3v.xlsx"), content))

    spans = record.data["spans"]
    assert len(spans) == 7, f"expected 7 row spans, got {len(spans)}"
    # each of the 6 student rows is its OWN span
    student_spans = [s for s in spans if s["row_index"] >= 2]
    assert len(student_spans) == 6
    assert len({s["span_id"] for s in student_spans}) == 6


def test_xlsx_spans_carry_sheet_row_and_column_identity():
    content = (SYNTHETIC_CORPUS / "synthetic_support_3v.xlsx").read_bytes()
    record = _run(extract_document(_xlsx_source("synthetic_support_3v.xlsx"), content))

    header = record.data["spans"][0]
    assert header["sheet"] == "Sheet1"
    assert header["row_index"] == 1
    assert [c["column"] for c in header["cells"]][:2] == ["A", "B"]
    assert header["cells"][0]["text"] == "Student"
    assert header["cells"][1]["text"] == "class"
    first_student = record.data["spans"][1]
    assert first_student["cells"][0]["column"] == "A"
    assert first_student["cells"][1]["text"] in ("V", "A")


def test_xlsx_multi_sheet_spans_keep_sheet_names():
    content = (SYNTHETIC_CORPUS / "synthetic_class_list.xlsx").read_bytes()
    record = _run(extract_document(_xlsx_source("synthetic_class_list.xlsx"), content))

    sheets = {s["sheet"] for s in record.data["spans"]}
    assert sheets == {"Grade 3", "Grade 6"}
    # row 1 (class names) and row 2 (teachers) survive as their own spans
    grade3 = [s for s in record.data["spans"] if s["sheet"] == "Grade 3"]
    assert grade3[0]["row_index"] == 1
    assert grade3[1]["row_index"] == 2
    # empty columns don't produce cells; column letters are the real ones
    assert all(c["text"] for s in record.data["spans"] for c in s["cells"])


def test_xlsx_row_spans_pass_grounding_gate():
    """Row spans stay byte-exact slices — the grounding gate must hold."""
    content = (SYNTHETIC_CORPUS / "synthetic_class_list.xlsx").read_bytes()
    record = _run(extract_document(_xlsx_source("synthetic_class_list.xlsx"), content))

    report = verify_extraction(record.data, apply_drops=False)
    assert report.ok, report.errors


def test_support_path_untouched_by_row_spans():
    """Multi-sheet SUPPORT workbooks keep the sheet-aware support parse
    (field_hint spans), not the generic row-span path."""
    record = _run(extract_document(_support_source(), _support_workbook_bytes()))
    assert record.data["structure"]["document_type"] == "student_support"
    assert any(s.get("field_hint") for s in record.data["spans"])
    assert not any("row_index" in s for s in record.data["spans"])


def test_xlsx_extractions_survive_the_vault_schema_gate(tmp_path):
    """Class lock: additive span metadata (field_hint from the support path,
    sheet/row_index/cells from STEP 1) must pass the vault's schema
    validation — the 2026-08-18 support fix shipped spans the vault refused
    ('Could not read this document'), which this test would have caught."""
    from src.lingua_viva.docpipe import vault

    # STEP 1 row-span path (generic xlsx)
    content = (SYNTHETIC_CORPUS / "synthetic_class_list.xlsx").read_bytes()
    record = _run(extract_document(_xlsx_source("synthetic_class_list.xlsx"), content))
    assert any("row_index" in s for s in record.data["spans"])
    vault.put_extraction(record, root=tmp_path)

    # support path (field_hint spans)
    record = _run(extract_document(_support_source(), _support_workbook_bytes()))
    assert any(s.get("field_hint") for s in record.data["spans"])
    vault.put_extraction(record, root=tmp_path)


# --- STEP 2: detect from structure, not text shape (SPEC §STEP 2) --------------


def test_structured_zero_student_files_yield_zero_detections():
    """Gate: curriculum + calendar fixtures → 0 detections. Story titles and
    calendar labels stop being students because they are not in a Student
    column — positional evidence, not blocklist additions."""
    for filename in ("synthetic_curriculum.xlsx", "synthetic_calendar.xlsx"):
        content = (SYNTHETIC_CORPUS / filename).read_bytes()
        record = _run(extract_document(_xlsx_source(filename), content))
        assert record.data["structure"]["students_detected"] == [], filename


def test_student_column_detects_abbreviated_names():
    """Gate: 3V fixture → 6. Abbreviated names ('Marco B-R') are students
    because they sit in the Student column — no full-bigram requirement."""
    content = (SYNTHETIC_CORPUS / "synthetic_support_3v.xlsx").read_bytes()
    record = _run(extract_document(_xlsx_source("synthetic_support_3v.xlsx"), content))

    students = record.data["structure"]["students_detected"]
    assert len(students) == 6, [s["display_name"] for s in students]
    assert all(s["evidence"] == "student_column" for s in students)
    names = {s["display_name"] for s in students}
    assert "Marco B-R" in names
    # every detection cites its own row span
    for student in students:
        assert student["span_ids"], student["display_name"]


def test_staff_block_above_header_is_not_students():
    """K-5 shape: staff first names sit ABOVE the Student/Accommodations
    header row — position says they are not students."""
    content = (SYNTHETIC_CORPUS / "synthetic_support_k5.xlsx").read_bytes()
    record = _run(extract_document(_xlsx_source("synthetic_support_k5.xlsx"), content))

    names = {s["display_name"] for s in record.data["structure"]["students_detected"]}
    assert names == {
        "Marco Bianchi", "Nora Rossi", "Sara Conti",
        "Giulia Riva", "Pietro Serra", "Leo Fontana", "Camilla Gatti",
    }


def test_first_last_column_pair_joins_names():
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["First", "Last", "Notes"])
    ws.append(["Marco", "Bianchi", "reading"])
    ws.append(["Nora", "Rossi", ""])
    buf = BytesIO()
    wb.save(buf)
    record = _run(extract_document(_xlsx_source("pair.xlsx"), buf.getvalue()))
    names = [s["display_name"] for s in record.data["structure"]["students_detected"]]
    assert names == ["Marco Bianchi", "Nora Rossi"]


def test_adult_name_columns_are_never_student_columns():
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Teacher Name", "Room"])
    ws.append(["Ilaria Moretti", "12"])
    buf = BytesIO()
    wb.save(buf)
    record = _run(extract_document(_xlsx_source("teachers.xlsx"), buf.getvalue()))
    assert record.data["structure"]["students_detected"] == []


def test_unstructured_documents_keep_the_bigram_fallback():
    """Markdown lesson plans have no columns — the bigram path survives as
    the fallback, tagged as its own (lower-confidence) evidence class."""
    source, content = _source("source_lesson_plan_marco_nora.json", "lesson_plan_marco_nora.md")
    record = _run(extract_document(source, content))
    students = record.data["structure"]["students_detected"]
    assert students, "bigram fallback must still detect in unstructured docs"
    assert all(s["evidence"] == "bigram_fallback" for s in students)


def test_repeated_header_rows_are_structure_not_students():
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Student", "class"])
    ws.append(["Marco B-R", "V"])
    ws.append(["Student", "class"])  # page-break header repeat
    ws.append(["Nora R-S", "A"])
    buf = BytesIO()
    wb.save(buf)
    record = _run(extract_document(_xlsx_source("repeat.xlsx"), buf.getvalue()))
    names = [s["display_name"] for s in record.data["structure"]["students_detected"]]
    assert names == ["Marco B-R", "Nora R-S"]


def test_prose_mentioning_students_is_not_a_name_column():
    """Exact-label rule: a header IS a student-name label, never prose that
    contains one — mottos ('...per studenti...'), plan columns ('Student
    Support Plan'), and descriptions ('Gli studenti sono...') are not name
    columns. This is what produced the curriculum/3V false positives."""
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Niente senza gioia · per studenti curiosi", "Unità"])
    ws.append(["Le Stagioni", "Uno"])
    ws2 = wb.create_sheet("Plan")
    ws2.append(["Student", "Student Support Plan", "Gli studenti sono qui descritti"])
    ws2.append(["Marco B-R", "Piano Alfa", "Nota Lunga"])
    buf = BytesIO()
    wb.save(buf)
    record = _run(extract_document(_xlsx_source("prose.xlsx"), buf.getvalue()))
    names = [s["display_name"] for s in record.data["structure"]["students_detected"]]
    # only the exact "Student" column detects; plan/prose columns never do
    assert names == ["Marco B-R"]


def test_nome_cognome_pair_and_lone_nome_column():
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Nome", "Cognome"])
    ws.append(["Marco", "Bianchi"])
    ws2 = wb.create_sheet("Lone")
    ws2.append(["Nome", "Classe"])
    ws2.append(["Nora Rossi", "3V"])
    buf = BytesIO()
    wb.save(buf)
    record = _run(extract_document(_xlsx_source("nome.xlsx"), buf.getvalue()))
    names = {s["display_name"] for s in record.data["structure"]["students_detected"]}
    assert names == {"Marco Bianchi", "Nora Rossi"}
