"""Regression guards for three defects fixed on 2026-08-27.

Each of these was found by hand and fixed without a test to hold it down.
All three could silently return, and two of them would not show up in CI:

1. Duplicate keys in a dict literal. The ed20299 merge resolved a conflict by
   keeping BOTH sides' entries for "atl_skills" and "learner_profile_attributes"
   inside one dict in _normalize_lesson_plan(). Python keeps the last silently,
   which made the correct implementations dead code and emptied the IB Learner
   Profile section of every lesson plan. Nothing in the language warns.

2. A module-level name defined twice. Same merge, same file — two identical
   copies of the IB_LEARNER_PROFILE_ATTRIBUTES validation allowlist. Harmless
   only while they stay identical.

3. macOS resolves /tmp and /var under a system directory literally named
   "private", so the "**/private*" rule in the private-path classifier matched
   every temp path the app writes while processing an upload. This one is
   invisible on Linux: CI would stay green with the bug fully present, which is
   exactly why it needs pinning here rather than relying on the tests that
   happened to fail on a Mac.
"""

from __future__ import annotations

import ast
import collections
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The modules the ed20299 merge touched, plus the privacy classifier. Kept as an
# explicit list rather than a whole-tree walk: this is a guard against a known
# merge-resolution failure mode, not a general linter.
GUARDED_SOURCES = [
    "src/lingua_viva/lesson_materials.py",
    "src/lingua_viva/filemap.py",
    "src/education/parent_report.py",
    "src/lingua_viva/docpipe/lens_extract.py",
    "src/lingua_viva/docpipe/lens_match.py",
    "doctor/support_loop/privacy.py",
]


def _existing_sources() -> list[Path]:
    return [p for p in (REPO_ROOT / rel for rel in GUARDED_SOURCES) if p.exists()]


# --- 1. duplicate keys in a dict literal -------------------------------------


@pytest.mark.parametrize("source", _existing_sources(), ids=lambda p: p.name)
def test_no_duplicate_keys_in_dict_literals(source: Path):
    """A later duplicate key silently overwrites the earlier one."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [
            k.value for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        ]
        dupes = sorted(k for k, count in collections.Counter(keys).items() if count > 1)
        if dupes:
            offenders.append(f"{source.name}:{node.lineno} -> {dupes}")
    assert not offenders, (
        "Duplicate keys in a dict literal — Python keeps the LAST one and "
        "discards the earlier value without warning:\n  " + "\n  ".join(offenders)
    )


# --- 2. module-level names defined twice --------------------------------------


@pytest.mark.parametrize("source", _existing_sources(), ids=lambda p: p.name)
def test_no_module_level_redefinition(source: Path):
    """Two copies of a constant are one edit away from two different constants."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    dupes = sorted(n for n, count in collections.Counter(names).items() if count > 1)
    assert not dupes, f"{source.name}: redefined at module level: {dupes}"


# --- 3. the macOS system /private prefix is not student data ------------------

# Real macOS temp locations. /tmp and /var are symlinks into /private, so every
# NamedTemporaryFile the app opens while handling an upload lands under one of
# these. None of them is the teacher's data.
MACOS_SYSTEM_TEMP_PATHS = [
    "/private/var/folders/h5/abc123/T/tmpxyz/unit_plan.md",
    "/private/tmp/upload_staging/curriculum.pdf",
    "/private/var/folders/zz/T/lingua_viva_ingest/notes.txt",
]

# Paths that MUST still be refused — the fix strips only the system prefix, so
# a genuinely private file keeps matching on the rest of the path and its name.
STILL_PRIVATE_PATHS = [
    "/Users/teacher/Documents/private/marco.md",
    "/private/var/folders/h5/abc123/T/IEP_marco.pdf",
    "/Users/teacher/Documents/Teaching/IEP_nora.pdf",
]


@pytest.mark.parametrize("path", MACOS_SYSTEM_TEMP_PATHS)
def test_macos_system_private_prefix_is_not_private_data(path: str):
    """The OS's /private is not the teacher's 'private'.

    Without this, add_document() refuses every file the app stages in a temp
    directory on macOS — the platform the signed desktop build ships for.
    """
    from doctor.support_loop.privacy import matches_private_path

    assert not matches_private_path(path), (
        f"{path} was classified as private student data. macOS resolves /tmp "
        "and /var under a SYSTEM directory named 'private'; matching it means "
        "refusing the app's own temp files."
    )


@pytest.mark.parametrize("path", STILL_PRIVATE_PATHS)
def test_genuinely_private_paths_are_still_refused(path: str):
    """The prefix fix must not have opened a hole in the real rule."""
    from doctor.support_loop.privacy import matches_private_path

    assert matches_private_path(path), f"{path} should still be refused"


def test_filemap_does_not_treat_system_private_as_a_student_zone(tmp_path):
    """The same false positive in filemap's marker check.

    A whole-string match on 'private' classified every scanned temp tree as a
    student zone, which excluded it from the map and made confirm_entry report
    'path is not an entry' for a directory just scanned.
    """
    from src.lingua_viva.filemap import _matches_privacy_marker

    assert not _matches_privacy_marker("/private/var/folders/h5/T/Teaching/curriculum")
    # A directory the teacher actually named still matches.
    assert _matches_privacy_marker("/Users/teacher/Teaching/private")
    assert _matches_privacy_marker("/Users/teacher/Teaching/observations")


# --- 4. ATL skills are the teacher's, never the model's ------------------------


def test_atl_skills_come_from_the_teacher_not_the_model():
    """The duplicate-key bug inverted this exact rule.

    _normalize_lesson_plan carries the comment "ATL skills are the teacher's own
    lesson-input selection — ground truth, never the model's." The surviving
    duplicate preferred plan.get("atl_skills") — the model's output — over
    lesson.atl_skills. No test covered it, because the fake engine returns no
    ATL skills, so the inversion was invisible.
    """
    from src.lingua_viva.lesson_materials import _normalize_lesson_plan, LessonInput

    lesson = LessonInput(
        ib_programme="PYP",
        subject="Italian",
        unit_title="How We Express Ourselves",
        topic="weather",
        atl_skills=["communication"],
        cefr_target="A2",
        duration_minutes=45,
        language_of_instruction="en",
    )
    # The model tries to supply its own ATL skills. The teacher's must win.
    plan = {"atl_skills": ["thinking", "research"]}
    normalized = _normalize_lesson_plan(plan, lesson, [], teacher_name="Claudia")

    assert normalized["atl_skills"] == ["communication"], (
        "The model's ATL skills overrode the teacher's lesson input. The "
        "teacher's selection is ground truth for this field."
    )
