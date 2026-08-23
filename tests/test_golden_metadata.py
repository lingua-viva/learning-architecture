"""Golden-suite metadata validation (P1-TEST-001 / P1-TEST-002).

The golden runner (src/lingua_viva/cli.py `_eval`) checks only
query → expected_node. The GOLD-* entries added 2026-08-23 also carry
expected_artifact and expected_grounding — metadata the runner ignores.
Without a check, those fields would be exactly the kind of
looks-like-documentation-but-is-fiction drift the action registry tests
warn about: a golden could cite LV-KL-999 forever and nothing would
notice. These tests make the metadata answerable to the real knowledge
library.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "golden_education_v1.yaml"
KNOWLEDGE_DIR = REPO / "knowledge" / "education"

KNOWN_ARTIFACTS = {"lesson_plan", "parent_report"}


def _golden_queries() -> list[dict]:
    return yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["queries"]


def _knowledge_entries() -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for path in sorted(KNOWLEDGE_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("entries", [])
        for item in items or []:
            if isinstance(item, dict) and item.get("id"):
                entries[item["id"]] = item
    return entries


def test_golden_ids_are_unique():
    ids = [q["id"] for q in _golden_queries()]
    assert len(ids) == len(set(ids))


def test_expected_grounding_ids_exist_and_are_verified():
    """A golden citing a knowledge entry that does not exist (or that no
    one has verified) is asserting grounding the library cannot back."""
    library = _knowledge_entries()
    for q in _golden_queries():
        for kl_id in q.get("expected_grounding") or []:
            assert kl_id in library, (
                f"{q['id']} cites {kl_id}, which is not in knowledge/education/"
            )
            assert library[kl_id].get("verified") is True, (
                f"{q['id']} cites {kl_id}, which is not verified: true"
            )


def test_expected_artifact_values_are_known():
    for q in _golden_queries():
        artifact = q.get("expected_artifact")
        if artifact is not None:
            assert artifact in KNOWN_ARTIFACTS, (
                f"{q['id']} declares unknown artifact {artifact!r}"
            )


def test_gold_lesson_plan_entries_carry_grounding():
    """The GOLD-LP-* entries exist to pin lesson-generation routing AND
    the knowledge a generator should cite — an LP golden without
    grounding is only doing half its job."""
    lp = [q for q in _golden_queries() if q["id"].startswith("GOLD-LP-")]
    assert len(lp) == 10
    for q in lp:
        assert q.get("expected_grounding"), f"{q['id']} has no expected_grounding"


def test_gold_parent_report_entries_present():
    pr = [q for q in _golden_queries() if q["id"].startswith("GOLD-PR-")]
    assert len(pr) == 5
    for q in pr:
        assert q["expected_artifact"] == "parent_report"
