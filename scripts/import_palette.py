"""
Import Palette Taxonomy and Knowledge Library into Mission Canvas

Reads the existing Palette v1.3 taxonomy (131 RIUs) and v1.4 knowledge library
(203 entries) and converts them to Mission Canvas ontology/knowledge format.

Usage:
    python scripts/import_palette.py

This preserves ALL existing institutional memory. The 131 RIUs become domain
nodes in the ontology. The 203 knowledge entries become the knowledge library.
The 6 core intent nodes (PROTECT, RESEARCH, DECIDE, CREATE, DIAGNOSE, REFLECT)
remain as the routing layer above the imported RIUs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

PALETTE_ROOT = Path(__file__).parent.parent.parent / "palette"
MC_ROOT = Path(__file__).parent.parent

# Agent type → intent mapping
AGENT_TO_INTENT = {
    "Researcher": "RESEARCH",
    "Builder": "CREATE",
    "Architect": "DECIDE",
    "Debugger": "DIAGNOSE",
    "Narrator": "CREATE",
    "Validator": "REFLECT",
    "Monitor": "REFLECT",
    "Orchestrator": "DECIDE",
    "Human:Delivery": "DECIDE",
}

# Journey stage → parent core node (rough mapping)
STAGE_TO_PARENT = {
    "foundation": "CORE-DECIDE",
    "retrieval": "CORE-RESEARCH",
    "orchestration": "CORE-DECIDE",
    "implementation": "CORE-CREATE",
    "deployment": "CORE-CREATE",
}


def load_taxonomy() -> list[dict]:
    """Load the Palette taxonomy YAML."""
    tax_dir = PALETTE_ROOT / "taxonomy" / "releases"
    # Find latest version
    versions = sorted(tax_dir.glob("v*"), reverse=True)
    if not versions:
        print(f"ERROR: No taxonomy versions found in {tax_dir}")
        return []

    tax_file = None
    for v in versions:
        candidates = list(v.glob("*.yaml"))
        if candidates:
            tax_file = candidates[0]
            break

    if not tax_file:
        print("ERROR: No taxonomy YAML found")
        return []

    print(f"Loading taxonomy: {tax_file}")
    with open(tax_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data.get("rius", [])


def load_knowledge_library() -> list[dict]:
    """Load the Palette knowledge library YAML."""
    kl_dir = PALETTE_ROOT / "knowledge-library"
    versions = sorted(kl_dir.glob("v*"), reverse=True)
    if not versions:
        print(f"ERROR: No KL versions found in {kl_dir}")
        return []

    kl_file = None
    for v in versions:
        # Look for the main library file, not individual RIU entries
        candidates = list(v.glob("palette_knowledge_library*.yaml"))
        if not candidates:
            candidates = list(v.glob("*library*.yaml"))
        if candidates:
            kl_file = candidates[0]
            break

    if not kl_file:
        print("ERROR: No KL YAML found")
        return []

    print(f"Loading knowledge library: {kl_file}")
    with open(kl_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data.get("library_questions", [])


def convert_riu_to_node(riu: dict) -> dict:
    """Convert a Palette RIU to a Mission Canvas ontology node."""
    riu_id = riu.get("riu_id", "")
    coords = riu.get("coordinates", {})
    category = coords.get("category", "*")
    agents = riu.get("agent_types", [])
    stage = riu.get("journey_stage", "foundation")

    # Determine domain from coordinates
    if category == "legal" or category == "legal-services":
        domain = "legal"
    elif category in ("*", "ai-ml", "enterprise"):
        domain = "ai-enablement"
    else:
        domain = category.replace("-", "_") if category != "*" else "ai-enablement"

    # Determine default intent from agent types
    default_intent = "RESEARCH"
    for agent in agents:
        if agent in AGENT_TO_INTENT:
            default_intent = AGENT_TO_INTENT[agent]
            break

    # Determine parent from stage
    parent = STAGE_TO_PARENT.get(stage, "CORE-RESEARCH")

    # Determine if blocks_external from reversibility
    reversibility = riu.get("reversibility", "two_way")
    blocks_external = reversibility == "one_way"

    # Signals from trigger_signals
    signals = riu.get("trigger_signals", [])

    # Dependencies become escalates_to
    deps = riu.get("dependencies", [])

    return {
        "id": riu_id,
        "name": riu.get("name", ""),
        "description": riu.get("problem_pattern", ""),
        "domain": domain,
        "parent": parent,
        "signals": signals,
        "blocks_external": blocks_external,
        "requires_local": blocks_external,
        "escalates_to": deps,
        "resolves_to": [],
        "evidence_tier": 2,
        "path_weight": 1.0,
        "default_intent": default_intent,
        "default_lens": None,
        # Preserve original fields as metadata
        "_journey_stage": stage,
        "_workstreams": riu.get("workstreams", []),
        "_reversibility": reversibility,
        "_tags": riu.get("tags", []),
        "_artifacts": riu.get("artifacts", []),
        "_success_conditions": riu.get("success_conditions", {}),
        "_failure_modes": riu.get("failure_modes", {}),
        "_execution_intent": riu.get("execution_intent", ""),
    }


def convert_kl_entry(entry: dict) -> dict:
    """Convert a Palette KL entry to Mission Canvas knowledge entry."""
    sources = entry.get("sources", [])
    citations = []
    for s in sources:
        if isinstance(s, dict):
            title = s.get("title", "")
            url = s.get("url", "")
            citations.append(f"{title} ({url})" if url else title)
        elif isinstance(s, str):
            citations.append(s)

    # Map difficulty to evidence tier
    difficulty = entry.get("difficulty", "medium")
    tier_map = {"critical": 1, "high": 1, "medium": 2, "low": 3}
    tier = tier_map.get(difficulty, 2)

    return {
        "id": entry.get("id", ""),
        "title": entry.get("question", ""),
        "content": entry.get("answer", ""),
        "ontology_nodes": entry.get("related_rius", []),
        "evidence_tier": tier,
        "citations": citations,
        "tags": entry.get("tags", []),
        "verified": True,
        "_problem_type": entry.get("problem_type", ""),
        "_difficulty": difficulty,
        "_industries": entry.get("industries", []),
    }


def group_nodes_by_domain(nodes: list[dict]) -> dict[str, list[dict]]:
    """Group converted nodes by domain."""
    groups: dict[str, list[dict]] = {}
    for node in nodes:
        domain = node.get("domain", "ai-enablement")
        groups.setdefault(domain, []).append(node)
    return groups


def write_domain_file(domain: str, nodes: list[dict], output_dir: Path) -> None:
    """Write a domain YAML file in Mission Canvas format."""
    # Strip metadata fields (prefixed with _) from nodes for the YAML output
    clean_nodes = []
    for node in nodes:
        clean = {k: v for k, v in node.items() if not k.startswith("_")}
        clean_nodes.append(clean)

    data = {
        "domain": domain,
        "version": "1.0",
        "description": f"Imported from Palette taxonomy v1.3. {len(clean_nodes)} nodes.",
        "imported_from": "palette/taxonomy/releases/v1.3/",
        "nodes": clean_nodes,
    }

    output_file = output_dir / f"{domain.replace(' ', '_')}.yaml"
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)
    print(f"  Wrote {output_file.name}: {len(clean_nodes)} nodes")


def write_knowledge_file(domain: str, entries: list[dict], output_dir: Path) -> None:
    """Write a knowledge YAML file in Mission Canvas format."""
    clean_entries = []
    for entry in entries:
        clean = {k: v for k, v in entry.items() if not k.startswith("_")}
        clean_entries.append(clean)

    data = {
        "domain": domain,
        "version": "1.0",
        "description": f"Imported from Palette knowledge library v1.4. {len(clean_entries)} entries.",
        "entries": clean_entries,
    }

    output_file = output_dir / f"{domain.replace(' ', '_')}_imported.yaml"
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)
    print(f"  Wrote {output_file.name}: {len(clean_entries)} entries")


def main():
    print("=" * 60)
    print("Mission Canvas ← Palette Import")
    print("=" * 60)

    # Import taxonomy
    print("\n--- Taxonomy ---")
    rius = load_taxonomy()
    if not rius:
        print("No RIUs found. Skipping taxonomy import.")
    else:
        print(f"Loaded {len(rius)} RIUs")
        nodes = [convert_riu_to_node(r) for r in rius]
        groups = group_nodes_by_domain(nodes)
        output_dir = MC_ROOT / "ontology" / "domains"
        print(f"\nWriting domain files to {output_dir}/:")
        for domain, domain_nodes in sorted(groups.items()):
            write_domain_file(domain, domain_nodes, output_dir)

    # Import knowledge library
    print("\n--- Knowledge Library ---")
    entries = load_knowledge_library()
    if not entries:
        print("No entries found. Skipping KL import.")
    else:
        print(f"Loaded {len(entries)} entries")
        converted = [convert_kl_entry(e) for e in entries]

        # Group by related domain (first RIU's domain)
        kl_output_dir = MC_ROOT / "knowledge"
        # Write all as a single imported file
        write_knowledge_file("palette", converted, kl_output_dir)

        total_citations = sum(len(e["citations"]) for e in converted)
        print(f"  Total citations: {total_citations}")

    # Summary
    print("\n" + "=" * 60)
    print("Import complete.")
    if rius:
        print(f"  Taxonomy: {len(rius)} RIUs → {len(groups)} domain files")
    if entries:
        print(f"  Knowledge: {len(entries)} entries imported")
    print("\nRun tests: python3 -m pytest tests/ -v")
    print("Run health: python3 -c 'from src.integrity.health_check import HealthCheck; ...")
    print("=" * 60)


if __name__ == "__main__":
    main()
