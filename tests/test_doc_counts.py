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

from pathlib import Path

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
    nodes, _domains = _live_counts()
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
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
