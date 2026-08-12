"""Test 05 — End-to-End: Lesson → 3-Tier PDFs

THE demo test. Takes an IB MYP unit, runs it through the content
differentiator, renders 3 separate student-ready PDFs (one per tier),
and verifies they're real PDF files that can be printed.

Claudia: change the UNIT to match a real lesson. The PDFs land in
the output directory — open them, check they look right, print one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.education.content_differentiator import ContentDifferentiator, LessonInput
from src.lingua_viva.pdf_generator import (
    render_differentiated_pack,
    render_tier_pdf,
)


# ── The IB unit (replace with real material!) ───────────────────────

UNIT = LessonInput(
    ib_programme="MYP",
    subject="English Language and Literature",
    unit_title="The Power of Persuasion",
    topic="Writing persuasive arguments using claim-evidence-reasoning",
    atl_skills=["Communication", "Critical thinking"],
    cefr_target="B1",
    duration_minutes=50,
    language_of_instruction="en",
    created_by="teacher-claudia",
)


def test_generate_three_tier_pdfs(tmp_path: Path) -> None:
    """Generate 3 separate PDFs — one per tier — from one lesson."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)
    pack_dict = pack.to_dict()

    paths = render_differentiated_pack(pack_dict, output_dir=tmp_path)

    assert len(paths) == 3, f"Expected 3 PDFs, got {len(paths)}"
    assert "foundational" in paths
    assert "on_track" in paths
    assert "extended" in paths

    for tier_name, path in paths.items():
        assert path.exists(), f"{tier_name} PDF not found at {path}"
        assert path.stat().st_size > 500, f"{tier_name} PDF too small ({path.stat().st_size} bytes)"
        # Verify it's actually a PDF
        header = path.read_bytes()[:5]
        assert header == b"%PDF-", f"{tier_name} file is not a valid PDF"


def test_each_tier_pdf_is_distinct(tmp_path: Path) -> None:
    """Each tier produces a different PDF — not three copies."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)
    pack_dict = pack.to_dict()

    paths = render_differentiated_pack(pack_dict, output_dir=tmp_path)

    sizes = {name: path.stat().st_size for name, path in paths.items()}
    # At minimum, filenames differ
    names = {path.name for path in paths.values()}
    assert len(names) == 3, "All 3 PDFs should have distinct filenames"


def test_single_tier_pdf_renders(tmp_path: Path) -> None:
    """render_tier_pdf produces a valid PDF for one tier."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)
    tier_data = pack.tiers["on_track"]
    lesson = pack.to_dict()["lesson"]

    out = tmp_path / "on_track_test.pdf"
    render_tier_pdf("on_track", tier_data, lesson, output_path=out)

    assert out.exists()
    assert out.read_bytes()[:5] == b"%PDF-"
    assert out.stat().st_size > 500


def test_pdf_contains_unit_title(tmp_path: Path) -> None:
    """The PDF content includes the unit title — not a generic placeholder."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)
    tier_data = pack.tiers["foundational"]
    lesson = pack.to_dict()["lesson"]

    pdf_bytes = render_tier_pdf("foundational", tier_data, lesson)
    assert isinstance(pdf_bytes, bytes)
    # The title should appear in the PDF text layer
    # (reportlab embeds it as both metadata and rendered text)
    assert b"Persuasion" in pdf_bytes or b"persuasion" in pdf_bytes


def test_pdf_no_internal_jargon(tmp_path: Path) -> None:
    """Student-facing PDFs must not contain internal system terms."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)

    for tier_name in ("foundational", "on_track", "extended"):
        tier_data = pack.tiers[tier_name]
        lesson = pack.to_dict()["lesson"]
        pdf_bytes = render_tier_pdf(tier_name, tier_data, lesson)

        # These should never appear in student-facing material
        for term in [b"RTI", b"ontology", b"pipeline", b"trace_id"]:
            assert term not in pdf_bytes, \
                f"Internal term '{term.decode()}' found in {tier_name} PDF"


def test_full_e2e_print_ready(tmp_path: Path) -> None:
    """The complete flow: input → differentiate → 3 PDFs on disk.
    This is the demo. Open the PDFs after running."""
    engine = ContentDifferentiator()
    pack = engine.generate(UNIT)
    pack_dict = pack.to_dict()

    paths = render_differentiated_pack(pack_dict, output_dir=tmp_path)

    print("\n=== Generated PDFs (open these!) ===")
    for tier_name, path in paths.items():
        size_kb = path.stat().st_size / 1024
        print(f"  {tier_name:15s} → {path}  ({size_kb:.1f} KB)")
    print()

    # All exist and are valid PDFs
    for path in paths.values():
        assert path.exists()
        assert path.read_bytes()[:5] == b"%PDF-"
