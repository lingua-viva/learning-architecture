"""Parent report HTML template (SPEC_LV_IMPROVEMENT_CHECKLIST_2026-08-22 P1-DOC-001).

The print layout lives in render_parent_report_html (documented by
templates/parent_report.html), not in Python string concatenation. Locks:
- structured sections (strengths / growth areas / next steps) are derived
  from the same sentences that form the body, so the existing trauma-safety
  and publication-safety gates cover them;
- empty sections render an honest note, never invented content;
- the name-stripped draft surface renders a fill-in line, not a name;
- all values are HTML-escaped.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.education.observation_capture import ObservationCapturePipeline
from src.education.parent_report import ParentReportGenerator, render_parent_report_html
from src.education.student_lens import StudentLensStore
from src.web import app

REPO = Path(__file__).resolve().parents[1]


def make_store(tmp_path):
    return StudentLensStore(db_path=tmp_path / "parent.db")


def _capture_progress(store, student_id):
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id=student_id, teacher_id="teacher_1",
                     raw_transcript="reading sample at A2", template_type="cefr",
                     cefr_dimension="reading", cefr_level_observed="A2",
                     cefr_direction="progressing")
    pipeline.capture(student_id=student_id, teacher_id="teacher_1",
                     raw_transcript="reading sample at B1", template_type="cefr",
                     cefr_dimension="reading", cefr_level_observed="B1",
                     cefr_direction="progressing")


def test_draft_structured_sections_when_progressed(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina", grade_level="3")
    _capture_progress(store, "s1")
    draft = ParentReportGenerator(store).generate_draft("s1", "teacher_1")
    assert draft.strengths, "progressed CEFR dimension must produce a strength"
    assert draft.growth_areas == []
    assert draft.student_name == "Amina"
    assert draft.grade_level == "3"
    assert draft.reporting_period  # month-year of writing
    assert draft.intro.startswith("We noticed Amina")


def test_draft_growth_area_when_watching(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    pipeline = ObservationCapturePipeline(store=store)
    pipeline.capture(student_id="s1", teacher_id="teacher_1",
                     raw_transcript="writing sample at A1", template_type="cefr",
                     cefr_dimension="writing", cefr_level_observed="A1",
                     cefr_direction="maintaining")
    draft = ParentReportGenerator(store).generate_draft("s1", "teacher_1")
    assert draft.growth_areas
    assert "watching" in draft.growth_areas[0]


def test_every_section_sentence_is_in_body(tmp_path):
    """Gate-coverage invariant: trauma/publication safety run on the body —
    a section sentence that is not in the body would dodge those gates."""
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    _capture_progress(store, "s1")
    store.append_evidence({
        "student_id": "s1", "teacher_id": "teacher_1",
        "target_type": "support_category", "target_id": "communication_and_language",
        "summary": "Chose to retell the story in Italian without prompting",
        "kind": "teacher_feedback", "confidence_level": "teacher_confirmed",
    })
    draft = ParentReportGenerator(store).generate_draft(
        "s1", "teacher_1", include_evidence_summaries=True
    )
    for sentence in draft.strengths + draft.growth_areas:
        assert sentence in draft.body


def test_personal_context_never_reaches_strengths(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    _capture_progress(store, "s1")
    store.append_evidence({
        "student_id": "s1", "teacher_id": "teacher_1",
        "target_type": "support_category", "target_id": "personal_context",
        "summary": "Safeguarding note — home situation may affect readiness.",
        "kind": "teacher_feedback", "confidence_level": "teacher_confirmed",
    })
    draft = ParentReportGenerator(store).generate_draft(
        "s1", "teacher_1", include_evidence_summaries=True
    )
    joined = " ".join(draft.strengths).lower()
    assert "safeguarding" not in joined
    assert "home situation" not in joined


def test_approved_artifact_print_html_has_all_sections(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina", grade_level="3")
    _capture_progress(store, "s1")
    gen = ParentReportGenerator(store)
    artifact = gen.approve(gen.generate_draft("s1", "teacher_1"),
                           teacher_display_name="Ms. Fatima")
    html = artifact.to_print_html()
    assert "Amina" in html
    assert "<strong>Grade</strong><br>3" in html
    assert "Reporting period" in html
    assert "<h2>Strengths</h2>" in html
    assert "<h2>Growth areas</h2>" in html
    assert "Next steps" in html
    assert "Ms. Fatima (Class Teacher)" in html
    assert "Teacher signature / date" in html
    assert "AI" not in html


def test_blank_student_name_renders_fill_line():
    html = render_parent_report_html({
        "subject_line": "A note from class",
        "student_name": "",
        "strengths": [], "growth_areas": [], "home_activities": [],
    })
    assert 'class="fill-line"' in html


def test_empty_sections_render_honest_notes_not_invented_content(tmp_path):
    store = make_store(tmp_path)
    store.create_lens(student_id="s1", display_name="Amina")
    gen = ParentReportGenerator(store)
    artifact = gen.approve(gen.generate_draft("s1", "teacher_1"),
                           teacher_display_name="Ms. Fatima")
    html = artifact.to_print_html()
    assert "still collecting classroom observations" in html
    assert "None noted for this period." in html


def test_render_escapes_html_in_values():
    html = render_parent_report_html({
        "subject_line": "<script>alert(1)</script>",
        "student_name": "Amina <b>",
        "strengths": ["<img src=x>"],
        "growth_areas": [], "home_activities": [],
    })
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html


def test_template_file_documents_renderer_fields():
    template = (REPO / "templates" / "parent_report.html").read_text(encoding="utf-8")
    for placeholder in ("{{ subject_line }}", "{{ student_name }}", "{{ grade_level }}",
                        "{{ reporting_period }}", "{{ strengths }}", "{{ growth_areas }}",
                        "{{ home_activities }}", "{{ from_label }}"):
        assert placeholder in template
    assert "render_parent_report_html" in template
    assert "Teacher signature / date" in template


def test_recommendation_endpoint_print_html_is_name_stripped(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)
    with StudentLensStore(db_path=tmp_path / "students.db") as store:
        student_id = store.create_lens(display_name="Mira Patel", grade_level="4")
        _capture_progress(store, student_id)

    with TestClient(app) as client:
        response = client.post(
            "/api/parents/recommendation",
            json={"student_id": student_id, "teacher_id": "teacher-a"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["strengths"]
    assert body["grade_level"] == "4"
    html = body["print_html"]
    assert "Mira" not in html  # draft surface is name-stripped by design
    assert 'class="fill-line"' in html
    assert "<h2>Strengths</h2>" in html
    assert "Teacher signature / date" in html
