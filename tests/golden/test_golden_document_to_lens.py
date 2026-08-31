"""
Golden evaluation harness for document-to-lens pipeline.

Runs the pipeline against hand-labeled golden sets and reports
precision/recall/accuracy per component.

Usage:
  python3 -m pytest tests/golden/test_golden_document_to_lens.py -v
  python3 -m pytest tests/golden/test_golden_document_to_lens.py -v -k "name"     # name matching only
  python3 -m pytest tests/golden/test_golden_document_to_lens.py -v -k "classify"  # classification only
  python3 -m pytest tests/golden/test_golden_document_to_lens.py -v -k "section"   # section split only
"""

import pytest
import asyncio
from collections import Counter

from tests.golden.document_to_lens_golden import (
    NAME_MATCH_CASES,
    SENTENCE_CLASSIFICATION_CASES,
    MULTI_STUDENT_REPORT,
    SECTION_SPLIT_EXPECTATIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def levenshtein(s1: str, s2: str) -> int:
    """Pure-Python Levenshtein distance (no external dependency)."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,      # deletion
                curr[j] + 1,          # insertion
                prev[j] + (c1 != c2),  # substitution
            ))
        prev = curr
    return prev[-1]


# ---------------------------------------------------------------------------
# TEST 1: Name Matching
# ---------------------------------------------------------------------------

class TestNameMatching:
    """Test name matching against the golden set."""

    def _match(self, doc_name: str, roster_name: str) -> bool:
        """Test if doc_name resolves to roster_name."""
        from src.lingua_viva.docpipe.identity import resolve
        roster = [{"student_id": "test-id", "display_name": roster_name}]
        result = resolve(doc_name, roster)
        return result["status"] in ("exact", "queue")

    def _match_with_levenshtein(self, doc_name: str, roster_name: str, threshold: int = 3) -> bool:
        """Match using Levenshtein distance as fallback."""
        # First try the standard resolver
        if self._match(doc_name, roster_name):
            return True
        # Levenshtein fallback: compare normalized names in both orders
        dn = doc_name.lower().strip()
        rn = roster_name.lower().strip()
        if levenshtein(dn, rn) <= threshold:
            return True
        # Try reversed
        parts = dn.split()
        if len(parts) >= 2:
            reversed_dn = " ".join(parts[1:]) + " " + parts[0]
            if levenshtein(reversed_dn, rn) <= threshold:
                return True
        return False

    @pytest.mark.parametrize(
        "doc_name, roster_name, should_match, difficulty",
        NAME_MATCH_CASES,
        ids=[f"{c[0]}_vs_{c[1]}_{c[3]}" for c in NAME_MATCH_CASES],
    )
    def test_name_match_current_system(self, doc_name, roster_name, should_match, difficulty):
        """Test the current matching system against golden cases."""
        matched = self._match(doc_name, roster_name)
        if should_match:
            if not matched:
                pytest.xfail(f"KNOWN GAP: {doc_name!r} → {roster_name!r} ({difficulty}) — not yet handled")
        else:
            assert not matched, f"FALSE POSITIVE: {doc_name!r} matched {roster_name!r} ({difficulty}) — DANGEROUS"

    @pytest.mark.parametrize(
        "doc_name, roster_name, should_match, difficulty",
        NAME_MATCH_CASES,
        ids=[f"lev_{c[0]}_vs_{c[1]}_{c[3]}" for c in NAME_MATCH_CASES],
    )
    def test_name_match_with_levenshtein(self, doc_name, roster_name, should_match, difficulty):
        """Test matching with Levenshtein distance fallback."""
        matched = self._match_with_levenshtein(doc_name, roster_name)
        if should_match:
            if not matched:
                pytest.xfail(f"KNOWN GAP: {doc_name!r} → {roster_name!r} ({difficulty}) — Levenshtein didn't help")
        else:
            assert not matched, f"FALSE POSITIVE: {doc_name!r} matched {roster_name!r} ({difficulty}) — DANGEROUS"


# ---------------------------------------------------------------------------
# TEST 2: Sentence Classification
# ---------------------------------------------------------------------------

class TestSentenceClassification:
    """Test LLM sentence classification against the golden set.

    These tests call the local LLM (qwen3:8b) so they're slower.
    Skip with: -k "not classify"
    """

    @pytest.fixture(scope="class")
    def engine(self):
        try:
            from src.lingua_viva.reasoning import ReasoningEngine
            return ReasoningEngine()
        except Exception:
            pytest.skip("ReasoningEngine not available")

    @pytest.mark.parametrize(
        "sentence, expected_field, difficulty",
        SENTENCE_CLASSIFICATION_CASES,
        ids=[f"classify_{i}_{c[2]}" for i, c in enumerate(SENTENCE_CLASSIFICATION_CASES)],
    )
    @pytest.mark.asyncio
    async def test_sentence_classification(self, engine, sentence, expected_field, difficulty):
        """Test individual sentence classification."""
        from src.lingua_viva.docpipe.lens_extract import _classify_sentence_to_field, _LENS_FIELD_IDS

        fields = await _classify_sentence_to_field(sentence, engine)

        if expected_field == "none":
            # Should NOT be classified
            if fields:
                actual = fields[0].field_path
                # Extract the field ID from the path
                for fid in _LENS_FIELD_IDS:
                    if fid in actual:
                        pytest.xfail(f"FALSE POSITIVE: boilerplate classified as {fid}")
            # Pass — correctly skipped
            return

        if not fields:
            pytest.xfail(f"MISS: '{sentence[:60]}...' expected {expected_field}, got nothing ({difficulty})")
            return

        actual_path = fields[0].field_path
        # Check if the expected field ID appears in the field_path
        if expected_field not in actual_path:
            pytest.xfail(
                f"MISROUTE: '{sentence[:50]}...' expected {expected_field}, "
                f"got {actual_path} ({difficulty})"
            )


# ---------------------------------------------------------------------------
# TEST 3: Section Splitting
# ---------------------------------------------------------------------------

class TestSectionSplitting:
    """Test per-student section isolation — the cross-contamination guard."""

    def test_section_split_golden(self):
        from src.lingua_viva.docpipe.lens_extract import _split_into_student_sections

        students = [
            {"student_id": "s-chang", "display_name": "Chang Abigail"},
            {"student_id": "s-miro", "display_name": "Corazza Miro"},
            {"student_id": "s-luca", "display_name": "Scala Luca"},
        ]

        sections = _split_into_student_sections(MULTI_STUDENT_REPORT, students)

        for student_id, expectations in SECTION_SPLIT_EXPECTATIONS.items():
            section = sections.get(student_id, "")
            assert section, f"No section found for {student_id}"

            for phrase in expectations["must_contain"]:
                assert phrase in section, (
                    f"MISSING: {student_id} section should contain '{phrase}' but doesn't"
                )

            for phrase in expectations["must_not_contain"]:
                assert phrase not in section, (
                    f"CROSS-CONTAMINATION: {student_id} section contains '{phrase}' "
                    f"which belongs to another student"
                )


# ---------------------------------------------------------------------------
# Accuracy Summary (run as standalone)
# ---------------------------------------------------------------------------

def test_name_matching_accuracy_summary():
    """Print accuracy summary for name matching."""
    from src.lingua_viva.docpipe.identity import resolve

    results = {"correct": 0, "wrong": 0, "missed": 0, "false_positive": 0}
    failures = []

    for doc_name, roster_name, should_match, difficulty in NAME_MATCH_CASES:
        roster = [{"student_id": "test-id", "display_name": roster_name}]
        result = resolve(doc_name, roster)
        matched = result["status"] in ("exact", "queue")

        if should_match and matched:
            results["correct"] += 1
        elif should_match and not matched:
            results["missed"] += 1
            failures.append(f"  MISS: {doc_name!r} → {roster_name!r} ({difficulty})")
        elif not should_match and not matched:
            results["correct"] += 1
        elif not should_match and matched:
            results["false_positive"] += 1
            failures.append(f"  FALSE POS: {doc_name!r} matched {roster_name!r} ({difficulty})")

    total = len(NAME_MATCH_CASES)
    accuracy = results["correct"] / total * 100

    print(f"\n{'='*60}")
    print(f"NAME MATCHING ACCURACY: {results['correct']}/{total} ({accuracy:.0f}%)")
    print(f"  Correct: {results['correct']}")
    print(f"  Missed:  {results['missed']}")
    print(f"  False+:  {results['false_positive']}")
    if failures:
        print(f"\nFailures:")
        for f in failures:
            print(f)
    print(f"{'='*60}\n")

    # FALSE POSITIVES are catastrophic — fail the test
    assert results["false_positive"] == 0, (
        f"{results['false_positive']} false positive(s) — cross-contamination risk"
    )
