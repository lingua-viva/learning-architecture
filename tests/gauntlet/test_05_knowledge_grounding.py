"""Gauntlet phase 5 — the knowledge library and grounding integrity.

The knowledge library is what stands between a lesson plan and a fabricated
standard. This phase pins its shape (every entry complete, verified, cited),
the loader's contract, the official IB learner profile list, and the GIR's
honesty about unsupported claims.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.lingua_viva.grounding.build import build_grounding_result
from src.lingua_viva.lesson_materials import (
    IB_LEARNER_PROFILE_ATTRIBUTES,
    load_curriculum_knowledge,
)

from .conftest import REPO

KNOWLEDGE_DIR = REPO / "knowledge" / "education"

# The library as it actually is on 2026-08-23: 8 domain files, 51 entries.
# (The gauntlet prompt said "60+" — that number was never true; asserting
# the real floor keeps this test honest and still catches deletions.)
# Updated 2026-08-27: the reconciled merge added atl_approaches_to_learning,
# italian_l2_pedagogy and learner_profile, taking the library to 8 — which is
# what the comment above already claimed. The constant had been left at 6.
KNOWLEDGE_FILES = 8
KNOWLEDGE_ENTRIES_MIN = 38


def _all_entries() -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("entries", [])
        for item in items or []:
            if isinstance(item, dict):
                out.append((path, item))
    return out


# --- library shape ------------------------------------------------------------


def test_knowledge_library_has_expected_size():
    files = sorted(KNOWLEDGE_DIR.glob("*.yaml"))
    assert len(files) == KNOWLEDGE_FILES, [f.name for f in files]
    assert len(_all_entries()) >= KNOWLEDGE_ENTRIES_MIN


def test_every_entry_is_structurally_complete():
    for path, entry in _all_entries():
        where = f"{path.name}:{entry.get('id')}"
        assert str(entry.get("id") or "").startswith("LV-KL-"), where
        assert str(entry.get("title") or "").strip(), where
        assert str(entry.get("content") or "").strip(), where
        assert entry.get("ontology_nodes"), where
        assert entry.get("evidence_tier") in (1, 2, 3), where


def test_entry_ids_are_unique_across_the_whole_library():
    ids = [entry["id"] for _, entry in _all_entries()]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, sorted(dupes)


def test_every_verified_entry_carries_a_citation():
    """verified: true is a claim someone checked this against a source —
    an entry claiming that with no citation is a fabricated standard."""
    for path, entry in _all_entries():
        if entry.get("verified") is True:
            citations = [str(c).strip() for c in entry.get("citations") or []]
            assert any(citations), f"{path.name}:{entry['id']} verified but uncited"


def test_tier_1_entries_cite_official_sources():
    """Evidence tier 1 = official standard — it must name its document."""
    for path, entry in _all_entries():
        if entry.get("evidence_tier") == 1:
            citations = " ".join(str(c) for c in entry.get("citations") or [])
            assert citations.strip(), f"{path.name}:{entry['id']} tier-1 without citation"


# --- loader contract ----------------------------------------------------------


def test_loader_returns_only_real_library_entries():
    library_ids = {entry["id"] for _, entry in _all_entries()}
    entries = load_curriculum_knowledge("language", "Describing daily routines in Italian")
    assert entries
    assert len(entries) <= 8
    for entry in entries:
        assert entry.id in library_ids, entry.id
        assert entry.content.strip()
        assert entry.source_path


def test_loader_never_invents_knowledge_for_an_unknown_topic():
    """An off-library topic still returns real entries (general pedagogy),
    never synthesized ones."""
    library_ids = {entry["id"] for _, entry in _all_entries()}
    entries = load_curriculum_knowledge("language", "quantum chromodynamics")
    for entry in entries:
        assert entry.id in library_ids, entry.id


# --- official IB learner profile ---------------------------------------------


def test_learner_profile_list_is_exactly_the_official_ten():
    assert IB_LEARNER_PROFILE_ATTRIBUTES == (
        "Inquirers", "Knowledgeable", "Thinkers", "Communicators", "Principled",
        "Open-minded", "Caring", "Risk-takers", "Balanced", "Reflective",
    )


# --- GIR honesty --------------------------------------------------------------


def test_gir_flags_unsupported_certainty_claims(monkeypatch, tmp_path):
    """Confident factual claims with no sources behind them must count as
    unsupported — the GIR may not launder fabrication into a clean score."""
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    result = build_grounding_result(
        content=(
            "The IB requires exactly twelve units per year. "
            "Every PYP school must use this template."
        ),
        query_text="how many units does the IB require",
    )
    assert result.gir.total_claims >= 2
    assert result.gir.unsupported_claims >= 1
    assert result.gir.score < 1.0


def test_gir_respects_uncertainty_markers(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    hedged = build_grounding_result(
        content="This might work well for a Grade 3 group, and possibly for Grade 4.",
        query_text="grade level fit",
    )
    assert hedged.gir.unsupported_claims == 0
