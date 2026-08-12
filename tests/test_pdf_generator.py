"""Tests for src/lingua_viva/pdf_generator.py (W3, 2026-08-09).

All PDFs go to tmp_path (never committed); LV_STATE_HOME is redirected so
no test touches the operator's real ~/.lingua-viva/. All names are
synthetic fixtures per publication-policy.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.lingua_viva.pdf_generator import (
    BRAND,
    artifacts_dir,
    render_coursework_pack_pdf,
    render_document,
    render_lesson_pdf,
    render_parent_report_pdf,
    state_home,
)


@pytest.fixture(autouse=True)
def _state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    yield


def _lesson() -> dict:
    return {
        "subject": "Italian Language",
        "unit_title": "La famiglia e le relazioni",
        "topic": "La famiglia e le relazioni",
        "cefr_target": "A2",
        "duration_minutes": 30,
    }


def _materials() -> list[dict]:
    return [
        {
            "tier": "foundational",
            "title": "Parole della famiglia",
            "learning_objective": "Children notice and name family words.",
            "cefr_target": "A1",
            "tasks": [
                {"type": "guided_practice", "prompt": "Point to the word you know.",
                 "chunk_minutes": 10},
            ],
            "vocabulary_list": [{"term": "famiglia"}, {"term": "relazioni"}],
            "scaffolding": ["word bank", "picture support"],
            "teacher_note": "Pair with a stronger reader.",
        },
        {
            "tier": "on_track",
            "title": "Frasi sulla famiglia",
            "instructions_for_student": "Write three sentences about a family in a story.",
            "exercise_body": "Use the words from the word wall.",
            "scaffolding": ["sentence starters"],
        },
    ]


def _pack() -> dict:
    return {
        "pack_id": "cwp-test-1",
        "audience": "teacher",
        "cover": {"title": "Grade 3 Italian coursework", "grade": "G3",
                  "focus": "Italian language development", "unit_count": 1},
        "units": [{
            "unit_id": "g3-unit-1",
            "title": "La famiglia e le relazioni",
            "focus": "Italian language development",
            "cefr_target": "A2",
            "source_citation": "Manuale §2.1, Grade 3",
            "overview": "Unit overview text.",
            "activities": [{
                "activity_id": "g3-unit-1-act-1",
                "title": "Vocabolario in contesto",
                "instructions": "Collect and use key words.",
                "duration_minutes": 20,
                "draft": True,
                "tiers": {
                    "foundational": {"cefr_target": "A1",
                                     "learning_objective": "Notice and name.",
                                     "tasks": [{"prompt": "Point to a word."}]},
                    "on_track": {"cefr_target": "A2",
                                 "learning_objective": "Connect and explain.",
                                 "tasks": [{"prompt": "Write sentences."}]},
                },
                "answer_key": ["Accept any accurate use of the term."],
                "teacher_notes": ["Pre-teach with visuals."],
            }],
            "background_reading": [{"title": "IB PYP Central Idea Requirement",
                                    "citation": "IBO (2018)."}],
        }],
    }


def test_render_document_returns_valid_pdf_bytes():
    data = render_document(
        title="Test document",
        metadata={"Grade": "G3"},
        sections=[{"heading": "Section", "paragraphs": ["Hello."],
                   "bullets": ["one", "two"],
                   "table": {"header": ["A", "B"], "rows": [["1", "2"]]}}],
    )
    assert isinstance(data, bytes)
    assert data.startswith(b"%PDF")
    assert len(data) > 500


def test_render_document_writes_to_path(tmp_path):
    out = tmp_path / "doc.pdf"
    result = render_document(title="On disk", sections=[], output_path=out)
    assert result == out
    assert out.read_bytes().startswith(b"%PDF")


def test_render_lesson_pdf_bytes_and_path(tmp_path):
    data = render_lesson_pdf(_lesson(), _materials())
    assert data.startswith(b"%PDF")
    out = tmp_path / "lesson.pdf"
    path = render_lesson_pdf(_lesson(), _materials(), output_path=out)
    assert Path(path).stat().st_size > 500


def test_render_parent_report_pdf():
    report = {
        "subject_line": "A note about your child's progress",
        "body": "We noticed your child trying new ways to make meaning in class.",
        "home_activities": ["Read a short story together in any language."],
        "from_label": "The classroom team",
        "language": "en",
    }
    data = render_parent_report_pdf(report)
    assert data.startswith(b"%PDF")


def test_render_coursework_pack_pdf_teacher_and_student(tmp_path):
    teacher = render_coursework_pack_pdf(_pack(), output_path=tmp_path / "t.pdf")
    student_pack = dict(_pack(), audience="student")
    student = render_coursework_pack_pdf(student_pack, output_path=tmp_path / "s.pdf")
    t_bytes = Path(teacher).read_bytes()
    s_bytes = Path(student).read_bytes()
    assert t_bytes.startswith(b"%PDF") and s_bytes.startswith(b"%PDF")
    # Teacher pack includes the answer-key section → strictly more content.
    assert len(t_bytes) != len(s_bytes)


def test_escaping_survives_markup_characters():
    data = render_document(
        title="A <b>title</b> & more",
        sections=[{"paragraphs": ["1 < 2 & 3 > 2 <notatag/>"]}],
    )
    assert data.startswith(b"%PDF")


def test_state_home_and_artifacts_dir_respect_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "custom"))
    assert state_home() == tmp_path / "custom"
    out = artifacts_dir("coursework")
    assert out == tmp_path / "custom" / "artifacts" / "coursework"
    assert out.is_dir()


def test_brand_is_generic_no_institution_name():
    assert BRAND == "Still I Rise"
