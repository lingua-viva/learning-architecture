"""T9 — Students-from-file ingest (SPEC_T9_INGEST_UI_2026-08-04).

The T3 extraction seam is exercised with the T0 fixture extraction (the
frozen contract output shape); one test pins the honest failure while the
real stub still raises NotImplementedError.
"""
from __future__ import annotations

import asyncio
import json
import time
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.web as web
from src.lingua_viva.docpipe import vault
from src.lingua_viva.docpipe.contracts import ExtractionRecord

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "docpipe"
client = TestClient(web.app)


@pytest.fixture()
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "student_lenses.db"))
    monkeypatch.setattr(web, "_INGEST_JOBS", {})
    return tmp_path


def _fixture_extraction(source_id: str) -> dict:
    data = json.loads((FIXTURES / "expected_extraction_lesson_plan_marco_nora.json").read_text(encoding="utf-8"))
    data["source_id"] = source_id
    return data


def _roster_extraction(source_id: str, names: list[str]) -> dict:
    text = "Class List\n" + "\n".join(names) + "\n\n"
    spans = [
        {
            "span_id": "SPN-0001",
            "char_start": 0,
            "char_end": len(text.strip()),
            "text": text.strip(),
        }
    ]
    return {
        "schema_version": "docpipe.extraction.v1",
        "source_id": source_id,
        "source_sha256": "test",
        "extracted_at": "2026-08-06T00:00:00Z",
        "extractor": {"name": "fixture", "version": "1", "model": None},
        "mime": "text/markdown",
        "language": "en",
        "normalized_text": text,
        "spans": spans,
        "structure": {
            "title": "Class List",
            "document_type": "roster",
            "sections": [],
            "students_detected": [
                {
                    "student_id": f"student-{name.lower().replace(' ', '-')}",
                    "display_name": name,
                    "confidence": 0.99,
                    "span_ids": ["SPN-0001"],
                }
                for name in names
            ],
        },
        "warnings": [],
    }


@pytest.fixture()
def fixture_extractor(monkeypatch):
    """Stand-in for T3 with the frozen contract output shape."""
    async def extract(source, content, *, model_client=None):
        data = _fixture_extraction(source.source_id)
        data["source_sha256"] = source.data["sha256"]
        return ExtractionRecord(data)

    from src.lingua_viva.docpipe import extract as docpipe_extract

    monkeypatch.setattr(docpipe_extract, "extract_document", extract)


def _upload(name: str = "lesson_plan_marco_nora.md") -> dict:
    content = (FIXTURES / name).read_bytes()
    response = client.post(
        "/api/students/ingest",
        files={"file": (name, content, "text/markdown")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _upload_bytes(name: str, content: bytes, mime: str) -> dict:
    response = client.post(
        "/api/students/ingest",
        files={"file": (name, content, mime)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _wait_for_job(job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/students/ingest/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("ingest job did not finish in time")


def test_full_chain_creates_grounded_lenses(isolated_state, fixture_extractor):
    started = _upload()
    job = _wait_for_job(started["job_id"])
    assert job["status"] == "done", job
    assert job["students_found"] == 2
    names = sorted(s["display_name"] for s in job["students_created"])
    assert names == ["Marco Bianchi", "Nora Rossi"]

    # Vault artifacts validate against the frozen schemas.
    from src.lingua_viva.docpipe.validate import validate_file

    root = vault.vault_root()
    assert not validate_file(root / "manifest.json")
    for created in job["students_created"]:
        lens_path = root / "lenses" / created["student_id"] / "lens.json"
        assert not validate_file(lens_path)
        lens = json.loads(lens_path.read_text(encoding="utf-8"))
        populated = [f for f in lens["profile"].values() if f["evidence"]]
        assert populated, "created lens has no grounded fields"
        for field in lens["profile"].values():
            if field["value"] in (None, "", [], {}):
                assert field["evidence"] == []
            else:
                assert field["evidence"], "populated field without evidence"

    # Bridge: the students appear in the existing roster store.
    def roster(store):
        return sorted(str(l.get("display_name")) for l in store.list_lenses())

    names_in_store = web._with_student_store(roster)
    assert "Marco Bianchi" in names_in_store and "Nora Rossi" in names_in_store

    # Operator ruling §8.1: every locally saved lens is queued for Drive
    # write-back (the T6 queue holds until push_file can drain).
    from src.lingua_viva.docpipe import sync as docpipe_sync

    for created in job["students_created"]:
        assert docpipe_sync.sync_status(created["student_id"])["status"] in ("pending", "failed")


def test_reimport_merges_never_forks(isolated_state, fixture_extractor):
    first = _wait_for_job(_upload()["job_id"])
    assert first["status"] == "done"
    root = vault.vault_root()
    marco_id = next(s["student_id"] for s in first["students_created"] if s["display_name"] == "Marco Bianchi")
    before = json.loads((root / "lenses" / marco_id / "lens.json").read_text(encoding="utf-8"))
    evidence_before = sum(len(f["evidence"]) for f in before["profile"].values())

    second = _wait_for_job(_upload()["job_id"])
    assert second["status"] == "done"
    after = json.loads((root / "lenses" / marco_id / "lens.json").read_text(encoding="utf-8"))
    evidence_after = sum(len(f["evidence"]) for f in after["profile"].values())
    # Different source_id per import → new evidence keys are allowed, but the
    # student must NOT fork into a second lens.
    lens_dirs = [p.name for p in (root / "lenses").iterdir() if p.is_dir()]
    assert lens_dirs.count(marco_id) == 1
    assert len([d for d in lens_dirs if "marco" in d.lower()]) == 1
    assert evidence_after >= evidence_before


def test_low_confidence_student_needs_confirmation(isolated_state, monkeypatch):
    async def extract(source, content, *, model_client=None):
        data = _fixture_extraction(source.source_id)
        data["source_sha256"] = source.data["sha256"]
        for student in data["structure"]["students_detected"]:
            student["confidence"] = 0.4
        return ExtractionRecord(data)

    from src.lingua_viva.docpipe import extract as docpipe_extract

    monkeypatch.setattr(docpipe_extract, "extract_document", extract)
    job = _wait_for_job(_upload()["job_id"])
    assert job["status"] == "done"
    assert job["students_created"] == []
    assert len(job["needs_confirmation"]) == 2

    # Teacher confirms one — only then is the lens created.
    response = client.post("/api/students/ingest/confirm", json={
        "job_id": job["job_id"], "display_name": "Nora Rossi",
    })
    assert response.status_code == 200, response.text
    created = response.json()["student"]
    assert created["display_name"] == "Nora Rossi"
    lens_path = vault.vault_root() / "lenses" / created["student_id"] / "lens.json"
    assert lens_path.exists()
    refreshed = client.get(f"/api/students/ingest/{job['job_id']}").json()
    assert all(item["display_name"] != "Nora Rossi" for item in refreshed["needs_confirmation"])


def test_bulk_roster_requires_confirmation_before_creating_students(isolated_state, monkeypatch):
    names = ["Marco Bianchi", "Nora Rossi", "Luca Verdi", "Sara Conti", "Maya Singh"]

    async def extract(source, content, *, model_client=None):
        data = _roster_extraction(source.source_id, names)
        data["source_sha256"] = source.data["sha256"]
        return ExtractionRecord(data)

    from src.lingua_viva.docpipe import extract as docpipe_extract

    monkeypatch.setattr(docpipe_extract, "extract_document", extract)
    job = _wait_for_job(_upload()["job_id"])

    assert job["status"] == "done"
    assert job["students_found"] == 5
    assert job["students_created"] == []
    assert [item["display_name"] for item in job["needs_confirmation"]] == names

    def roster(store):
        return list(store.list_lenses())

    assert web._with_student_store(roster) == []


def test_bulk_confirm_subset_creates_only_selected_students(isolated_state, monkeypatch):
    names = ["Marco Bianchi", "Nora Rossi", "Luca Verdi", "Sara Conti", "Maya Singh"]

    async def extract(source, content, *, model_client=None):
        data = _roster_extraction(source.source_id, names)
        data["source_sha256"] = source.data["sha256"]
        return ExtractionRecord(data)

    from src.lingua_viva.docpipe import extract as docpipe_extract

    monkeypatch.setattr(docpipe_extract, "extract_document", extract)
    job = _wait_for_job(_upload()["job_id"])
    response = client.post("/api/students/ingest/confirm", json={
        "job_id": job["job_id"],
        "display_names": ["Marco Bianchi", "Luca Verdi", "Maya Singh"],
    })
    assert response.status_code == 200, response.text
    created = response.json()["students"]
    assert [student["display_name"] for student in created] == [
        "Marco Bianchi", "Luca Verdi", "Maya Singh",
    ]

    refreshed = client.get(f"/api/students/ingest/{job['job_id']}").json()
    assert [item["display_name"] for item in refreshed["needs_confirmation"]] == [
        "Nora Rossi", "Sara Conti",
    ]
    assert sorted(s["display_name"] for s in refreshed["students_created"]) == [
        "Luca Verdi", "Marco Bianchi", "Maya Singh",
    ]


def test_bulk_undo_archives_only_students_from_that_import(isolated_state, monkeypatch):
    existing = client.post("/api/students", json={"display_name": "Existing Student", "grade_level": "G3"})
    assert existing.status_code == 200, existing.text
    names = ["Marco Bianchi", "Nora Rossi"]

    async def extract(source, content, *, model_client=None):
        data = _fixture_extraction(source.source_id)
        data["source_sha256"] = source.data["sha256"]
        data["structure"]["students_detected"] = [
            {
                "student_id": f"student-{name.lower().replace(' ', '-')}",
                "display_name": name,
                "confidence": 0.99,
                "span_ids": ["SPN-0001"],
            }
            for name in names
        ]
        return ExtractionRecord(data)

    from src.lingua_viva.docpipe import extract as docpipe_extract

    monkeypatch.setattr(docpipe_extract, "extract_document", extract)
    job = _wait_for_job(_upload()["job_id"])
    assert sorted(s["display_name"] for s in job["students_created"]) == names

    response = client.delete(f"/api/students/ingest/{job['job_id']}")
    assert response.status_code == 200, response.text
    assert sorted(s["display_name"] for s in response.json()["students_archived"]) == names

    roster = client.get("/api/students").json()["students"]
    assert [student["display_name"] for student in roster] == ["Existing Student"]


def test_bulk_undo_does_not_touch_students_from_another_import(isolated_state, monkeypatch):
    batches = [
        ["Marco Bianchi", "Nora Rossi"],
        ["Luca Verdi", "Sara Conti"],
    ]

    async def extract(source, content, *, model_client=None):
        names = batches.pop(0)
        data = _fixture_extraction(source.source_id)
        data["source_sha256"] = source.data["sha256"]
        data["structure"]["students_detected"] = [
            {
                "student_id": f"student-{name.lower().replace(' ', '-')}",
                "display_name": name,
                "confidence": 0.99,
                "span_ids": ["SPN-0001"],
            }
            for name in names
        ]
        return ExtractionRecord(data)

    from src.lingua_viva.docpipe import extract as docpipe_extract

    monkeypatch.setattr(docpipe_extract, "extract_document", extract)
    first = _wait_for_job(_upload()["job_id"])
    second = _wait_for_job(_upload()["job_id"])
    assert sorted(s["display_name"] for s in first["students_created"]) == [
        "Marco Bianchi", "Nora Rossi",
    ]
    assert sorted(s["display_name"] for s in second["students_created"]) == [
        "Luca Verdi", "Sara Conti",
    ]

    response = client.delete(f"/api/students/ingest/{first['job_id']}")
    assert response.status_code == 200, response.text

    roster = sorted(student["display_name"] for student in client.get("/api/students").json()["students"])
    assert roster == ["Luca Verdi", "Sara Conti"]


def test_ingest_job_status_survives_memory_reset(isolated_state, fixture_extractor):
    job = _wait_for_job(_upload()["job_id"])
    web._INGEST_JOBS = {}

    response = client.get(f"/api/students/ingest/{job['job_id']}")

    assert response.status_code == 200, response.text
    assert response.json()["job_id"] == job["job_id"]


def test_real_extraction_end_to_end_no_mock(isolated_state, monkeypatch):
    """T3 landed: the REAL extractor (deterministic core, no model) drives the
    chain — upload the fixture document, get real grounded lenses. This test
    replaced the honest-stub-failure test the moment T3 shipped."""
    # Force the deterministic path: no model client in the ingest job.
    import src.lingua_viva.docpipe.model as docpipe_model

    monkeypatch.setattr(
        docpipe_model, "LocalModelClient",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no model in test")),
    )
    job = _wait_for_job(_upload()["job_id"])
    assert job["status"] == "done", job
    names = sorted(s["display_name"] for s in job["students_created"])
    assert names == ["Marco Bianchi", "Nora Rossi"]
    root = vault.vault_root()
    extraction = json.loads(
        (root / "extracted" / f"{job['source_id']}.json").read_text(encoding="utf-8")
    )
    assert extraction["structure"]["document_type"] == "lesson_plan"
    for created in job["students_created"]:
        lens = json.loads(
            (root / "lenses" / created["student_id"] / "lens.json").read_text(encoding="utf-8")
        )
        assert any(f["evidence"] for f in lens["profile"].values())


def test_real_xlsx_roster_upload_needs_confirmation_before_creation(isolated_state, monkeypatch):
    """Acceptance: real Excel class list uploads through /api/students/ingest.

    Five detected students is roster-shaped, so Item 3 requires review first:
    names found, zero profiles created until the teacher confirms.
    """
    from openpyxl import Workbook

    import src.lingua_viva.docpipe.model as docpipe_model

    monkeypatch.setattr(
        docpipe_model, "LocalModelClient",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no model in test")),
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["First", "Last"])
    names = [
        ("Marco", "Bianchi"),
        ("Nora", "Rossi"),
        ("Luca", "Verdi"),
        ("Sara", "Conti"),
        ("Maya", "Singh"),
    ]
    for first, last in names:
        sheet.append([first, last])
    buffer = BytesIO()
    workbook.save(buffer)

    started = _upload_bytes(
        "class-list.xlsx",
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    job = _wait_for_job(started["job_id"])

    assert job["status"] == "done", job
    assert job["students_found"] == 5
    assert job["students_created"] == []
    assert [item["display_name"] for item in job["needs_confirmation"]] == [
        "Marco Bianchi",
        "Nora Rossi",
        "Luca Verdi",
        "Sara Conti",
        "Maya Singh",
    ]


def test_real_docx_roster_upload_needs_confirmation_before_creation(isolated_state, monkeypatch):
    """Acceptance: real Word table uploads through /api/students/ingest."""
    import docx
    import src.lingua_viva.docpipe.model as docpipe_model

    monkeypatch.setattr(
        docpipe_model, "LocalModelClient",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no model in test")),
    )
    document = docx.Document()
    document.add_paragraph("Class List")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "First"
    table.rows[0].cells[1].text = "Last"
    for first, last in [
        ("Marco", "Bianchi"),
        ("Nora", "Rossi"),
        ("Luca", "Verdi"),
        ("Sara", "Conti"),
        ("Maya", "Singh"),
    ]:
        cells = table.add_row().cells
        cells[0].text = first
        cells[1].text = last
    buffer = BytesIO()
    document.save(buffer)

    started = _upload_bytes(
        "class-list.docx",
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    job = _wait_for_job(started["job_id"])

    assert job["status"] == "done", job
    assert job["students_found"] == 5
    assert job["students_created"] == []
    assert len(job["needs_confirmation"]) == 5


def test_real_unsupported_upload_fails_honestly(isolated_state, monkeypatch):
    import src.lingua_viva.docpipe.model as docpipe_model

    monkeypatch.setattr(
        docpipe_model, "LocalModelClient",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no model in test")),
    )
    started = _upload_bytes(
        "slides.pptx",
        b"not really a presentation, but the extension is unsupported",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    job = _wait_for_job(started["job_id"])

    assert job["status"] == "failed"
    assert "unsupported format" in job["error"]
    assert "xlsx" in job["error"] and "docx" in job["error"]


def test_no_students_found_is_honest(isolated_state, monkeypatch):
    async def extract(source, content, *, model_client=None):
        data = _fixture_extraction(source.source_id)
        data["source_sha256"] = source.data["sha256"]
        data["structure"]["students_detected"] = []
        return ExtractionRecord(data)

    from src.lingua_viva.docpipe import extract as docpipe_extract

    monkeypatch.setattr(docpipe_extract, "extract_document", extract)
    job = _wait_for_job(_upload()["job_id"])
    assert job["status"] == "done"
    assert job["students_found"] == 0
    assert job["students_created"] == []


def test_oversized_upload_is_rejected(isolated_state, monkeypatch):
    monkeypatch.setattr(web, "INGEST_MAX_BYTES", 10)
    response = client.post(
        "/api/students/ingest",
        files={"file": ("big.md", b"x" * 11, "text/markdown")},
    )
    assert response.status_code == 413


def test_unknown_job_says_reimport_is_safe(isolated_state):
    response = client.get("/api/students/ingest/JOB-nope")
    assert response.status_code == 404
    assert "safe" in response.json()["error"]


def test_drive_ref_degrades_honestly_while_t1_is_a_stub(isolated_state):
    response = client.post("/api/students/ingest", json={"drive_ref": "folder-123"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert "not available" in body["error"]


def test_no_demo_roster_seeding_remains():
    source = (REPO / "src" / "web.py").read_text(encoding="utf-8")
    assert "_seed_demo_roster" not in source
    assert 'student_id="student-luca"' not in source


HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")


def test_import_affordance_present_no_manual_entry():
    assert "Import students from a file" in HTML
    assert 'id="ingest-file"' in HTML
    assert '"/api/students/ingest"' in HTML
    assert "Nothing was invented" in HTML
    assert ".xlsx,.docx,.csv,.txt,.md,.markdown,.pdf" in HTML


def test_low_confidence_confirm_button_wired():
    assert "data-ingest-confirm" in HTML
    assert '"/api/students/ingest/confirm"' in HTML


def test_bulk_roster_confirm_and_undo_controls_wired():
    assert "data-ingest-confirm-check" in HTML
    assert "data-ingest-confirm-selected" in HTML
    assert "display_names: names" in HTML
    assert "Undo this import" in HTML
    assert "/api/students/ingest/${state.ingestJob.job_id}" in HTML
    assert '{method: "DELETE"}' in HTML
