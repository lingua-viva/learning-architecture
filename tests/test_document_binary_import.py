"""U3 corpus: the document the matcher reads is also the document extracted.

Found in the overnight audit, 2026-09-05, base v0.2.92: the HTTP route parses
PDF/DOCX for matching, then passes their raw binary bytes to a UTF-8 decoder
for lens extraction. A successful match therefore hides empty/garbled fields.
"""
from io import BytesIO

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_binary_report_uses_parsed_text_but_retains_original_bytes(tmp_path, monkeypatch, extension):
    lines = ["Student Report", "Demo Student", "Reading: A2", "Writing: A1", "Listening: A2", "Speaking: A1+"]
    stream = BytesIO()
    if extension == "pdf":
        from reportlab.pdfgen.canvas import Canvas
        doc = Canvas(stream)
        for index, line in enumerate(lines):
            doc.drawString(72, 740 - index * 24, line)
        doc.save()
    else:
        from docx import Document
        doc = Document()
        for line in lines:
            doc.add_paragraph(line)
        doc.save(stream)
    content = stream.getvalue()
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    from src.education.student_lens import StudentLensStore
    store = StudentLensStore()
    store.create_lens(student_id="s-demo", display_name="Demo Student")
    store.close()
    from src.lingua_viva import reasoning
    def offline():
        raise RuntimeError("No model in this deterministic corpus case")
    monkeypatch.setattr(reasoning, "ReasoningEngine", offline)
    from src.web import app
    response = TestClient(app).post("/api/students/import-document", files={"file": (f"report.{extension}", content)})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["matched_students"][0]["student_id"] == "s-demo", payload
    fields = {row["field_path"]: row["value"] for row in payload["extractions_preview"]["s-demo"]["fields"]}
    assert fields.get("cefr_snapshot.reading") == "A2", fields
    assert fields.get("cefr_snapshot.speaking") == "A1+", fields
    original = tmp_path / "vault" / "sources" / payload["source_record_id"] / f"original.{extension}"
    assert original.read_bytes() == content


@pytest.mark.parametrize("extension,content", [
    ("png", b"\x89PNG\r\nDemo Student Reading: A2"),
    ("docx", b"broken-zip Demo Student Reading: A2"),
])
def test_unsupported_or_damaged_binary_is_not_reinterpreted_as_student_text(extension, content):
    from src.web import app
    response = TestClient(app).post("/api/students/import-document", files={"file": (f"report.{extension}", content)})
    assert response.status_code == 422
    assert response.json()["error"] in {"ocr_not_available", "text_extraction_failed"}
    assert "extractions_preview" not in response.json()


def test_scan_without_text_layer_is_a_named_refusal():
    from reportlab.pdfgen.canvas import Canvas
    from src.web import app
    stream = BytesIO()
    doc = Canvas(stream)
    doc.rect(72, 500, 100, 100)  # an image-like page, no text layer
    doc.showPage()
    doc.save()
    response = TestClient(app).post("/api/students/import-document", files={"file": ("scan.pdf", stream.getvalue())})
    assert response.status_code == 422
    assert response.json()["error"] == "text_extraction_failed"
    assert "scan" in response.json()["message"].lower()
