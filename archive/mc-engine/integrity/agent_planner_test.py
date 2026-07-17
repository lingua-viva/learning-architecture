"""
Agentic Multi-Traversal Planner Test

This tests the recursive composition of the ontology. 
Instead of rigid linear paths, nodes define what they REQUIRE (artifacts) 
and what they PRODUCE (artifacts).

An agent must be able to start at ANY node, discover missing artifacts, 
traverse the ontology to find nodes that produce those artifacts, 
execute them, and return to complete the original task.

This proves that the system can solve complex goals by chaining 
independent atomic units, exactly like a robotic agent chaining 
"Pick up Orange" and "Pick up Apple".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ontology.engine import OntologyEngine

def test_agentic_chaining():
    engine = OntologyEngine()
    nodes = engine.nodes

    # 1. Build an artifact catalog: artifact_name -> list of node_ids that produce it
    artifact_catalog = {}
    for node_id, node in nodes.items():
        produces = getattr(node, "produces", [])
        for art in produces:
            artifact_catalog.setdefault(art, []).append(node_id)

    print(f"Loaded {len(artifact_catalog)} unique artifacts across the ontology.")
    
    # 2. Test recursive resolution for every node
    # We want to see if we can fulfill all requires for a node.
    unresolvable = []
    successful_chains = []
    max_chain_depth = 0

    def resolve_artifacts(target_node_id, needed_artifacts, path, depth=0):
        nonlocal max_chain_depth
        max_chain_depth = max(max_chain_depth, depth)
        
        if depth > 10:
            return False, ["Recursion Limit Exceeded"]

        resolution_path = []
        for art in needed_artifacts:
            producers = artifact_catalog.get(art, [])
            if not producers:
                return False, [f"Missing Artifact Producer: {art}"]
            
            # For simplicity, pick the first producer (an agent might evaluate and pick the best)
            producer_id = producers[0]
            if producer_id in path:
                # We produced this earlier in the chain or there is a cyclic dependency
                continue
            
            producer_node = nodes[producer_id]
            producer_requires = getattr(producer_node, "requires", [])
            
            if producer_requires:
                # Recursive traversal UP to satisfy the producer's dependencies
                success, sub_path = resolve_artifacts(producer_id, producer_requires, path + [producer_id], depth + 1)
                if not success:
                    return False, sub_path
                resolution_path.extend(sub_path)
            
            # After dependencies are met, we execute the producer (move DOWN)
            resolution_path.append(f"Execute {producer_id} to produce [{art}]")

        return True, resolution_path

    print("\n--- Testing Agentic Backward Chaining ---")
    for node_id, node in nodes.items():
        requires = getattr(node, "requires", [])
        if not requires:
            continue
            
        success, chain = resolve_artifacts(node_id, requires, [node_id])
        if success:
            successful_chains.append((node_id, requires, chain))
        else:
            unresolvable.append((node_id, requires, chain))

    print(f"\nResults:")
    print(f"  Nodes with explicit artifact requirements: {len(successful_chains) + len(unresolvable)}")
    print(f"  Successfully resolvable chains: {len(successful_chains)}")
    print(f"  Unresolvable chains (missing producers): {len(unresolvable)}")
    print(f"  Max recursive depth reached: {max_chain_depth}")

    if successful_chains:
        print("\nSample Successful Agentic Traversal Chains:")
        for node_id, reqs, chain in successful_chains[:5]:
            print(f"\n  Target: {node_id} (Requires: {reqs})")
            for step in chain:
                print(f"    -> {step}")
            print(f"    -> Execute {node_id} (Goal Achieved)")

    if unresolvable:
        print("\nUnresolvable Nodes (Ontology Gaps!):")
        for node_id, reqs, err in unresolvable[:10]:
            print(f"  - {node_id} requires {reqs}. Error: {err}")

    if unresolvable:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(test_agentic_chaining())
