"""Single source of truth for counts (MC-lessons §6).

MC's own sweep found 5 stale doc entries (node counts drifted from live
data). LV was worse: CLAUDE.md claimed "137-node classification system"
while the live loader had 212. Of the 111 fork-era ai-enablement nodes, 101
were unreferenced by any live domain and archived to
archive/mc-engine/ontology/domains/; 10 were kept live (ontology/domains/
ai-enablement-core.yaml) because other domains' escalates_to/resolves_to
edges form a transitive closure requiring them — archiving the full 111
broke graph integrity (test_ontology.py::test_no_broken_edges). Net: 111
live nodes, 25 domains. Preflight check #4 (§2) already pins
MANIFEST.yaml's ontology.nodes to the live loader count; this test pins
the same live count against the two other places it's quoted in prose
(README.md, CLAUDE.md), so a doc going stale again fails the suite instead
of accumulating silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from ontology.engine import OntologyEngine

REPO = Path(__file__).resolve().parent.parent


def _live_counts() -> tuple[int, int]:
    engine = OntologyEngine()
    return engine.node_count, engine.domain_count


def test_manifest_ontology_counts_match_live_loader():
    nodes, domains = _live_counts()
    manifest = yaml.safe_load((REPO / "MANIFEST.yaml").read_text(encoding="utf-8"))
    assert manifest["ontology"]["nodes"] == nodes
    assert manifest["ontology"]["domains"] == domains


def test_readme_ontology_count_matches_live_loader():
    nodes, domains = _live_counts()
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert f"{nodes} nodes across {domains} domains" in text
    assert f"{nodes}-node classification system across {domains} domains" in text


def test_claude_md_ontology_count_matches_live_loader():
    """Pin the count in CLAUDE.md *if* CLAUDE.md still quotes it.

    The PC-0 reconcile merge (ed20299) replaced the 93-line developer-facing
    CLAUDE.md with a 202-line guide written for Claudia, who is not a
    developer. That guide quotes no node count, and it should not — forcing
    "111-node classification system" into a teacher's manual to satisfy a
    test would be the test dictating the documentation.

    The guard's purpose is undamaged: README.md still carries the prose and
    test_readme_ontology_count_matches_live_loader still pins it, and
    test_manifest_ontology_counts_match_live_loader pins MANIFEST.yaml
    against the live loader. So the count cannot drift silently.

    This stays as a conditional rather than a deletion so that if developer
    prose ever returns to CLAUDE.md, its number is checked from that moment.

    Open and deliberately not settled here: where the developer guidance the
    merge displaced should live (AGENTS.md quotes no count either). That is a
    documentation-ownership call for a human, not something to infer.
    """
    nodes, _domains = _live_counts()
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    # Sentinel must be the count-bearing phrase, not the bare words: the
    # teacher guide says "Don't touch the governance or classification
    # system", which is an instruction to Claudia, not a claim about a number.
    if not re.search(r"\d+-node classification system", text):
        pytest.skip(
            "CLAUDE.md is the teacher-facing guide and quotes no ontology "
            "count; README.md and MANIFEST.yaml carry the pinned count."
        )
    assert f"{nodes}-node classification system" in text


def test_ai_enablement_bulk_is_archived_but_referenced_subset_stays_live():
    # The original 111-node import no longer exists as one file.
    assert not (REPO / "ontology" / "domains" / "ai-enablement.yaml").exists()
    # Full 111-node history preserved in the archive.
    assert (REPO / "archive" / "mc-engine" / "ontology" / "domains" / "ai-enablement.yaml").is_file()
    # 10-node transitive-closure subset stays live (cross-domain escalation deps).
    core = REPO / "ontology" / "domains" / "ai-enablement-core.yaml"
    assert core.is_file()
    live_ids = {n["id"] for n in yaml.safe_load(core.read_text(encoding="utf-8"))["nodes"]}
    assert live_ids == {
        "RIU-001", "RIU-002", "RIU-004", "RIU-006",
        "RIU-012", "RIU-020", "RIU-029", "RIU-061", "RIU-200", "RIU-534",
    }
