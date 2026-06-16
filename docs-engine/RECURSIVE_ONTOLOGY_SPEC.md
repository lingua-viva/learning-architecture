# Recursive Ontology Specification
## Composable Atomic Operations for Mission Canvas

---

## The Principle (AWS Agentic Robotics, AI Council 2026)

If you train a robot to "pick up orange, banana, apple" end-to-end, it can ONLY do that exact sequence. But if you train "pick up orange", "pick up banana", "pick up apple" independently, then ANY combination works: "pick up any two", "leave only the banana", "pick up orange then apple."

**Applied to MC: each ontology node is an independently executable atomic operation.** The pipeline is recursive — output of one node becomes input to classification for the next. The system chains nodes automatically based on what each produces and what each requires.

---

## What Changes

### Before (Monolithic)
```
Query → Classify → ONE node → Reason → ONE output → Store
```
The system handles one node per query. If the answer requires multiple steps, the MODEL has to figure that out in a single REASON pass.

### After (Recursive Composable)
```
Query → Classify → Node A
  → Reason → Output A (produces: scope_document)
  → Detect: Output references Node B (requires: scope_document ✓)
  → Auto-classify → Node B
    → Reason → Output B (produces: stakeholder_map)
    → Detect: Output references Node C
    → Auto-classify → Node C
      → Reason → Output C (produces: decision_record)
      → No further references → STORE all path records
```

The pipeline RE-ENTERS itself. Each node executes independently. The chain emerges from what each node produces and what the next node requires.

---

## Node Schema: Produces / Requires

Every node declares:
- **produces**: What artifacts this node creates when executed successfully
- **requires**: What artifacts must exist (from prior nodes) before this node can execute
- **suggests_next**: What nodes typically follow this one (guidance, not enforcement)

```yaml
- id: MC-WORK-001
  name: Scope Definition
  produces:
    - convergence_brief    # Other nodes can require this
    - assumptions_list
    - non_goals
  requires: []             # No prerequisites — can start from scratch
  suggests_next:
    - MC-WORK-002          # Stakeholder mapping naturally follows scoping
    - MC-WORK-003          # Decision making needs scope to evaluate against

- id: MC-WORK-002
  name: Stakeholder Mapping
  produces:
    - stakeholder_map
    - raci_matrix
  requires:
    - convergence_brief    # Need scope before mapping stakeholders
  suggests_next:
    - MC-WORK-003          # Decisions need to know who decides
    - MC-WORK-008          # Handoff needs to know who receives
```

---

## How Recursion Works in the Pipeline

### Step 1: Normal Classification + Execution
```
User: "Help me define the scope for our new AI project"
  → Classify: MC-WORK-001 (Scope Definition)
  → REASON with traversal context (artifacts, failure modes, success)
  → Output: convergence_brief document
```

### Step 2: Output Analysis (NEW — between SYNTHESIZE and STORE)
```
After SYNTHESIZE, scan output for:
  1. Explicit node references: "You should also do MC-WORK-002"
  2. Artifact references: output mentions "stakeholder_map" → which node produces it?
  3. Unmet dependencies: output says "before proceeding, ensure X" → X maps to a node
  4. Gap signals: model says "I don't have enough information about Y" → Y maps to RESEARCH
```

### Step 3: Recursive Re-entry (NEW)
```
If Step 2 finds actionable references:
  → Queue referenced nodes
  → For each queued node:
    → Check if its `requires` are satisfied (produced by prior nodes in this session)
    → If satisfied: execute immediately (or in parallel if independent)
    → If not satisfied: execute the producing node first
  → Chain outputs: each node's output feeds the next node's context
  → STORE: one path record per node executed, linked by session_id
```

### Step 4: Parallel Execution
```
If multiple queued nodes are independent (no shared requires):
  → Execute in parallel
  → Merge outputs
  → Continue chain
```

---

## The Composability Graph

```
MC-WORK-001 (Scope)
  produces: convergence_brief, assumptions_list, non_goals
  ├── MC-WORK-002 (Stakeholders) requires: convergence_brief
  │   produces: stakeholder_map, raci_matrix
  │   ├── MC-WORK-003 (Decisions) requires: stakeholder_map
  │   │   produces: decision_record, tradeoff_matrix
  │   └── MC-WORK-008 (Handoff) requires: stakeholder_map
  │       produces: handoff_document, context_package
  ├── MC-WORK-005 (Decomposition) requires: convergence_brief
  │   produces: task_breakdown, dependency_graph
  └── MC-WORK-006 (Quality Review) requires: convergence_brief
      produces: review_checklist, gap_analysis

MC-DATA-001 (Quality Assessment)
  produces: quality_report, error_taxonomy
  ├── MC-DATA-004 (Eval Framework) requires: quality_report
  │   produces: golden_dataset, eval_harness, baseline_report
  └── MC-DATA-005 (Pipeline Design) requires: quality_report
      produces: pipeline_spec, data_flow_diagram

MC-GOV-001 (Data Boundary)
  produces: sanitizer_report, firewall_log_entry
  ├── MC-GOV-004 (Agent Governance) requires: sanitizer_report
  │   produces: task_envelope, result_envelope
  └── MC-GOV-005 (Model Routing) requires: sanitizer_report
      produces: model_selection_log

MC-DEPLOY-002 (Onboarding)
  produces: onboarding_plan, time_to_value_metric
  ├── MC-DEPLOY-004 (Churn Prevention) requires: onboarding_plan
  │   produces: health_score, intervention_plan
  │   └── MC-DEPLOY-006 (Expansion) requires: health_score
  │       produces: use_case_map, expansion_plan
  └── MC-DEPLOY-003 (Workshop) requires: onboarding_plan [soft]
      produces: workshop_agenda, hands_on_exercise

MC-DATA-006 (Privacy)
  produces: privacy_impact_assessment, data_map
  └── MC-LEGAL-005 (Compliance Audit) requires: privacy_impact_assessment
      produces: compliance_checklist, gap_report
```

---

## Cross-Domain Composition

The real power: nodes from different domains chain naturally.

### Example: "Deploy AI for a healthcare client"
```
MC-WORK-001 → produces: convergence_brief
  ↓ (feeds)
MC-DATA-006 → requires: [any scope doc], produces: privacy_impact_assessment
  ↓ (feeds)
MC-GOV-001 → produces: sanitizer_report (PII patterns for healthcare)
  ↓ (feeds)
MC-DEPLOY-001 → requires: [scope + privacy assessment], produces: poc_scope
  ↓ (feeds)
MC-DEPLOY-002 → requires: poc_scope, produces: onboarding_plan
```

Five nodes, three domains (work, data, deployment), one coherent workflow — assembled automatically from the produces/requires graph.

### Example: "Set up annotation quality for a new data team"
```
MC-DATA-003 → produces: annotation_guidelines, quality_rubric
  ↓ (parallel with)
MC-DATA-001 → produces: quality_report, error_taxonomy
  ↓ (feeds)
MC-DATA-004 → requires: quality_report, produces: golden_dataset, eval_harness
  ↓ (feeds)
MC-DEPLOY-003 → produces: workshop_agenda (training annotators)
```

### Example: "Review this contract and check compliance"
```
MC-LEGAL-004 → produces: clause_analysis, risk_matrix
  ↓ (parallel with)
MC-DATA-006 → produces: privacy_impact_assessment
  ↓ (feeds)
MC-LEGAL-005 → requires: privacy_impact_assessment, produces: compliance_checklist
  ↓ (feeds)
MC-WORK-003 → produces: decision_record (sign or don't sign)
```

---

## What This Means for the Pipeline

### New Pipeline Step: COMPOSE (between SYNTHESIZE and STORE)

```python
# In pipeline.py, after SYNTHESIZE, before STORE:

async def compose(self, synthesis_result, classification, session_context):
    """
    Detect recursive opportunities in the synthesis output.
    If the output references other nodes or unmet requirements,
    queue them for recursive execution.
    """
    next_nodes = []
    
    # 1. Check suggests_next from the current node
    node = self.ontology.nodes.get(classification.riu_id)
    if node and hasattr(node, 'suggests_next'):
        for suggested_id in node.suggests_next:
            suggested = self.ontology.nodes.get(suggested_id)
            if suggested:
                # Check if requires are satisfied by session artifacts
                unmet = [r for r in suggested.requires if r not in session_context.produced_artifacts]
                if not unmet:
                    next_nodes.append(suggested_id)
    
    # 2. Scan output for node references (MC-XXXX patterns)
    import re
    node_refs = re.findall(r'MC-[A-Z]+-\d+', synthesis_result.content)
    for ref in node_refs:
        if ref in self.ontology.nodes and ref not in next_nodes:
            next_nodes.append(ref)
    
    # 3. Return queued nodes (pipeline decides whether to recurse)
    return next_nodes
```

### Session Context (tracks what's been produced)

```python
@dataclass
class SessionContext:
    """Tracks artifacts produced across recursive pipeline calls."""
    session_id: str
    produced_artifacts: set[str] = field(default_factory=set)
    executed_nodes: list[str] = field(default_factory=list)
    depth: int = 0
    max_depth: int = 5  # Prevent infinite recursion
```

### Recursion Guard

```python
if session_context.depth >= session_context.max_depth:
    gap_signals.append(f"recursion_depth_limit:{session_context.depth}")
    # Don't recurse further — store what we have
```

---

## Implementation Priority

1. **Add `produces`, `requires`, `suggests_next` to node schema** (YAML + dataclass)
2. **Add `SessionContext` to pipeline** (tracks produced artifacts across recursive calls)
3. **Add COMPOSE step** (detect next nodes from output)
4. **Wire recursive re-entry** (pipeline calls itself with next node)
5. **Add parallel execution** (independent nodes run simultaneously)
6. **Test with multi-step scenario** (scope → stakeholders → decisions)

---

*Spec by claude.analysis, 2026-06-15. Based on AWS Agentic Robotics presentation (AI Council, May 2026) and operator's recursive pipeline vision.*
