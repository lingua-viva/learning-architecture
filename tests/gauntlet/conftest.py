"""Shared fixtures for the end-to-end gauntlet.

Prompt: dev/PROMPT_LV_END_TO_END_GAUNTLET_2026-08-23.md

Design decisions (deliberate, please keep):

- **No LLM calls anywhere.** Extraction runs with model_client=None; lesson
  plan tests use stub engines; parent reports are template-based already.
- **No session-scoped env mutation.** A session fixture that monkeypatches
  env vars leaks into every other test collected in a full-suite run.
  Instead, everything that takes an explicit path (StudentLensStore(db_path),
  extract root=...) gets one, and the few call sites that only read env
  (LV_PRIVACY_LOG_PATH, LV_STATE_HOME) are patched function-scoped inside
  the tests that need them.
- **Extraction runs once per session** (`corpus_extractions`): the five
  corpus workbooks are pure input → ExtractionRecord, so sharing the result
  is safe and keeps the gauntlet fast.
- **The lens store is seeded once per session** (`gauntlet_env`) from the
  class-list detections — the same names every phase asserts against.
  Tests that mutate state use their own students or their own store.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from src.education.student_lens import Observation, StudentLensStore
from src.lingua_viva.docpipe.contracts import SourceRecord
from src.lingua_viva.docpipe.extract import extract_document

REPO = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = REPO / "tests" / "fixtures" / "docpipe" / "synthetic-corpus"
REAL_ANON_DIR = REPO / "tests" / "fixtures" / "docpipe" / "real_anon"
REFERENCES_DIR = REPO / "references"
_BASE_SOURCE = REPO / "tests" / "fixtures" / "docpipe" / "source_lesson_plan_marco_nora.json"

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MIME = "application/pdf"

LABELS: dict = json.loads((CORPUS_DIR / "labels.json").read_text(encoding="utf-8"))
LABELS_BY_FILE: dict[str, dict] = {f["file"]: f for f in LABELS["files"]}

# The 19 labeled students of the synthetic class list. This list doubles as
# the privacy containment roster in phase 6: none of these names may appear
# in any artifact that leaves the app.
EXPECTED_STUDENTS: list[str] = LABELS_BY_FILE["synthetic_class_list.xlsx"]["expected_students"]

CORPUS_FILES = [
    "synthetic_class_list.xlsx",
    "synthetic_support_3v.xlsx",
    "synthetic_support_k5.xlsx",
    "synthetic_curriculum.xlsx",
    "synthetic_calendar.xlsx",
]

TEACHER_ID = "t-gauntlet"


def run(coro):
    """Run a coroutine on a fresh event loop (extract_document is async)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def source_for(path: Path, mime: str = XLSX_MIME) -> SourceRecord:
    """Build a SourceRecord for a fixture file, mirroring what the import
    route constructs (same pattern as tests/test_docpipe_extract.py)."""
    base = json.loads(_BASE_SOURCE.read_text(encoding="utf-8"))
    content = path.read_bytes()
    base.update(
        {
            "mime": mime,
            "original_ext": path.suffix,
            "original_filename": path.name,
            "path": str(path),
            "byte_size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "source_id": f"src-gauntlet-{path.stem}",
        }
    )
    return SourceRecord(base)


def detected_students(record) -> list[dict]:
    return record.data["structure"].get("students_detected", [])


def detected_names(record) -> list[str]:
    return [s["display_name"] for s in detected_students(record)]


@pytest.fixture(scope="session")
def corpus_extractions() -> dict[str, object]:
    """ExtractionRecord for each of the five corpus workbooks.

    Pure computation (no env, no store, no model) — safe to share.
    """
    out: dict[str, object] = {}
    for name in CORPUS_FILES:
        path = CORPUS_DIR / name
        out[name] = run(extract_document(source_for(path), path.read_bytes()))
    return out


@pytest.fixture(scope="session")
def gauntlet_env(tmp_path_factory, corpus_extractions):
    """Isolated student store seeded from the class-list detections.

    - one lens per detected student (the 19 labeled names)
    - Marco Bianchi seeded with 2 progressing CEFR observations (A1 → A2 in
      speaking, so TrendAnalyzer computes direction "improved") plus one
      sel_positive — the recipe parent-report strengths need
    """
    base_dir = tmp_path_factory.mktemp("gauntlet")
    store = StudentLensStore(db_path=base_dir / "student_lenses.db")

    class_list = corpus_extractions["synthetic_class_list.xlsx"]
    student_ids: dict[str, str] = {}
    for name in detected_names(class_list):
        student_ids[name] = store.create_lens(display_name=name, grade_level="G3")

    marco_id = student_ids["Marco Bianchi"]
    seeds = [
        Observation(
            student_id=marco_id,
            teacher_id=TEACHER_ID,
            template_type="cefr",
            raw_transcript="Used short rehearsed phrases to describe the morning routine.",
            cefr_dimension="speaking",
            cefr_level_observed="A1",
            cefr_direction="progressing",
        ),
        Observation(
            student_id=marco_id,
            teacher_id=TEACHER_ID,
            template_type="cefr",
            raw_transcript="Sustained a two-minute exchange about the weekend in Italian.",
            cefr_dimension="speaking",
            cefr_level_observed="A2",
            cefr_direction="progressing",
        ),
        Observation(
            student_id=marco_id,
            teacher_id=TEACHER_ID,
            template_type="sel_positive",
            raw_transcript="Invited a newer classmate into the small-group game unprompted.",
            sel_domain="relationship_skills",
            sel_valence="positive",
        ),
    ]
    for obs in seeds:
        result = store.append_observation(obs, duplicate_window_seconds=300)
        assert not result.get("duplicate"), "seed observation deduplicated unexpectedly"

    env = {
        "base_dir": base_dir,
        "store": store,
        "student_ids": student_ids,
        "marco_id": marco_id,
        "teacher_id": TEACHER_ID,
        "expected_students": EXPECTED_STUDENTS,
        "labels": LABELS_BY_FILE,
        "corpus_dir": CORPUS_DIR,
        "real_anon_dir": REAL_ANON_DIR,
        "extractions": corpus_extractions,
    }
    yield env
    store.close()
