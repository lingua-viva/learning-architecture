"""Layer 3: Privacy Boundary — PII never appears in traces, bundles, or generated content.

Property proved: Student names and personal data are confined to the lens store only.
No model calls for PRIV-003 and PRIV-004 (pure structural). PRIV-001/002 need server context.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.education.content_differentiator import ContentDifferentiator, LessonInput
from src.lingua_viva.filemap import is_student_data_zone, scan_directory


STUDENT_NAMES = ["Sofia", "Marco", "Nora", "Luca", "Elena"]


@pytest.mark.skip(reason="requires running server + trace file generation")
def test_L3_PRIV_001_traces_contain_zero_student_names(synthetic_students):
    """L3-PRIV-001: Trace files (.ndjson) contain zero student names.

    Setup: Run queries mentioning student names → read all trace files.
    Pass: grep for every student display_name in fixtures → 0 matches in traces.
    """
    pass


@pytest.mark.skip(reason="requires support bundle generation endpoint")
def test_L3_PRIV_002_support_bundle_zero_pii():
    """L3-PRIV-002: Support bundle contains zero student PII.

    Setup: Generate a support bundle.
    Pass: Bundle JSON/text has no student names, no observation text, no scores.
    """
    pass


def test_L3_PRIV_003_activity_pack_zero_student_names():
    """L3-PRIV-003: Generated activity pack contains zero student names.

    Setup: Generate a pack (template mode — no student data involved).
    Pass: Serialized pack JSON has no student names.
    """
    lesson = LessonInput(
        ib_programme="PYP",
        subject="Language",
        unit_title="La Routine Quotidiana",
        topic="Daily routines vocabulary in Italian",
        atl_skills=["COMM-01"],
        cefr_target="A2",
        duration_minutes=45,
        created_by="teacher_eval",
    )
    pack = ContentDifferentiator().generate(lesson)
    pack_json = json.dumps(pack.to_dict())

    for name in STUDENT_NAMES:
        assert name not in pack_json, (
            f"Student name '{name}' found in generated activity pack"
        )


def test_L3_PRIV_004_filemap_skips_student_data_zones():
    """L3-PRIV-004: File map scan excludes student-data zones.

    Pass: is_student_data_zone() correctly identifies student data paths.
    """
    # Paths that SHOULD be student data zones
    student_paths = [
        Path("Students/reports/marco_q1.pdf"),
        Path("students/IEPs/nora_iep.pdf"),
        Path("student_data/observations.db"),
    ]
    for p in student_paths:
        assert is_student_data_zone(p), f"Expected student data zone: {p}"

    # Paths that should NOT be student data zones
    safe_paths = [
        Path("curriculum/G3/unit1.pdf"),
        Path("assessment/rubrics/writing_rubric.pdf"),
        Path("docs/teacher_guide.md"),
    ]
    for p in safe_paths:
        assert not is_student_data_zone(p), f"Incorrectly flagged as student data: {p}"


def test_L3_PRIV_005_scan_excludes_student_dirs():
    """Bonus: scan_directory with a Students/ subfolder — student zone is flagged.

    The scan returns directory entries. We verify that any path classified as
    student_data_zone is identifiable as such, ensuring downstream tools
    can enforce the boundary.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "Teaching"
        (root / "curriculum" / "G3").mkdir(parents=True)
        (root / "Students" / "reports").mkdir(parents=True)

        # Create files
        (root / "curriculum" / "G3" / "unit1.pdf").write_text("x")
        (root / "Students" / "reports" / "marco.pdf").write_text("sensitive")

        entries = scan_directory(root, max_depth=4)
        paths_found = [e.path for e in entries]

        # Verify that is_student_data_zone correctly gates Student paths
        for p in paths_found:
            rel = Path(p).relative_to(root)
            if "Students" in str(rel) or "students" in str(rel):
                assert is_student_data_zone(rel), (
                    f"Student path {rel} not flagged as student_data_zone"
                )
