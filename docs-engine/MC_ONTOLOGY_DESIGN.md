# Mission Canvas Ontology — Native Design
## Not imported. Built for MC's pipeline and three-customer reality.

---

## Why Build, Not Import

The current MC ontology is Palette's taxonomy with the metadata stripped out. This creates two problems:

1. **Wrong granularity**: 111 of 137 nodes are AI-enablement-specific (Palette's domain). But MC serves attorneys, hardware distributors, refugee educators, and general professionals. The ontology should cover what MC's USERS need, not what Palette's BUILDER needed.

2. **Missing depth**: The Palette taxonomy has ~2,965 traversable nodes per RIU (artifacts, failure modes, success conditions, dependencies). MC imported 0% of this. Importing it creates a maintenance burden — every Palette update means an MC reimport. Better to build MC's own ontology from first principles, using Palette as a reference spec.

The Palette taxonomy is the SPEC. The MC ontology is the PRODUCT.

---

## Design Principles

1. **Two-axis classification**: Intent (what do you want to do) and Domain (what is this about) are separate axes, scored independently, combined at routing time. Never competing, and never represented as parent/child of each other.

2. **Layered depth**: Every node has a classification layer (fast, used by CLASSIFY) and a traversal layer (rich, used by CONTEXT/REASON). Stored separately.

3. **Customer-extensible**: The core ontology ships with MC. Customer ontologies extend it. `mc instance create` merges core + customer nodes. No fork needed.

4. **Name-is-signal**: Auto-indexing proved that names and descriptions are the primary signal source. Explicit signals are overrides, not the foundation.

5. **Grow from use**: Path records feed learned weights. Successful classifications boost their signals. The ontology improves with every query.

---

## Architecture: Two Indexes, One Node

```
┌──────────────────────────────────────────────┐
│               OntologyNode                    │
│                                               │
│  Classification Layer (fast, always loaded):  │
│    id, name, description, domain, parent      │
│    signals, blocks_external, requires_local   │
│    default_intent, evidence_tier              │
│                                               │
│  Traversal Layer (rich, lazy or preloaded):   │
│    artifacts, failure_modes, success_criteria │
│    dependencies, coordinates, journey_stage   │
│    agent_types, reversibility, workstream     │
│                                               │
└──────────────────────────────────────────────┘

Query → ClassificationIndex (signal matching, ~1ms)
      → TraversalIndex (metadata lookup, ~0.1ms after load)
      → Pipeline (CONTEXT step enriches prompt with traversal data)
```

---

## Layer 1: Intents (6 nodes — renamed, not domain nodes)

These are NOT domain nodes. They are the "what do you want to do" axis. Scored in a separate pass.

| ID | Name | Pipeline Behavior |
|----|------|-------------------|
| INTENT-PROTECT | Protect | Local-only. No external calls. PII/PHI lock. |
| INTENT-RESEARCH | Research | External research allowed. Perplexity/web. |
| INTENT-DECIDE | Decide | Reversibility analysis. One-way door detection. |
| INTENT-CREATE | Create | Artifact generation. Templates applied. |
| INTENT-DIAGNOSE | Diagnose | Root cause analysis. Failure mode matching. |
| INTENT-REFLECT | Reflect | Self-audit. Pattern extraction. Path review. |

**Signals**: Same as current CORE- nodes. These fire first, set the intent, then domain classification runs.

**Key change**: Renamed from `CORE-*` to `INTENT-*` to make the separation explicit. CORE implied they were the default. INTENT makes clear they're one axis.

**Compatibility requirement**: During migration, the pipeline still expects `ClassificationResult.riu_id` and the path store still writes `entry_node`. The first implementation should keep a compatibility field:

```python
ClassificationResult(
    intent_id="INTENT-PROTECT",
    node_id="MC-GOV-001",
    riu_id="MC-GOV-001",  # temporary compatibility alias
)
```

Remove the alias only after `pipeline.py`, `context_builder.py`, memory, health checks, and CLI output all use `node_id` explicitly.

---

## Layer 2: Core Domains (Ships with MC — every installation)

These cover what any MC user might ask about, regardless of industry. Designed from the three-customer reality + general professional use.

### Node Admission Standard

A node ships only if it passes all five tests below. If it fails later, it is merged, renamed, or moved to a customer extension.

1. **Routing use**: The node catches a query class that would otherwise route incorrectly or too generically.
2. **Context use**: The node adds artifacts, failure modes, success criteria, dependencies, or governance constraints that materially improve the REASON step.
3. **Memory use**: Path records for the node teach MC something reusable about future work.
4. **Governance use**: The node either changes boundary behavior or makes a boundary/audit decision easier to inspect.
5. **Customer use**: At least one of the real deployment contexts benefits from the node: Komodo/Mavens, Tropical IT, Still I Rise, or MC's own dogfooding.

No node exists only because it is conceptually tidy. Every node must earn its place in runtime behavior.


### Domain: governance (MC's own operations)
*"Questions about how MC itself works, its boundaries, its decisions."*

| ID | Name | Description | Traversal Data |
|----|------|-------------|----------------|
| MC-GOV-001 | Data Boundary Enforcement | PII/PHI detection and sanitization | artifacts: [sanitizer_report, firewall_log_entry], failure_modes: {silent: [pattern miss], loud: [false positive blocks work]}, success: {execution: all PII redacted, outcome: zero leaks in audit, safety: no false positives on legitimate data} |
| MC-GOV-002 | Classification Routing | How queries get classified to nodes | artifacts: [classification_result, confidence_score], failure_modes: {silent: [wrong RIU selected], loud: [no match found]}, dependencies: [] |
| MC-GOV-003 | Decision Audit Trail | Append-only decision logging | artifacts: [path_record, decision_log_entry], reversibility: one_way (append-only, cannot delete) |
| MC-GOV-004 | Agent Execution Governance | Task envelopes, policy compliance, result validation | artifacts: [task_envelope, result_envelope], failure_modes: {silent: [agent bypasses policy], loud: [policy violation detected]} |
| MC-GOV-005 | Model Routing | Which model handles which query | artifacts: [model_selection_log], dependencies: [MC-GOV-001] |

### Domain: work (Professional work patterns — any industry)
*"How work gets done. Planning, executing, reviewing, communicating."*

| ID | Name | Description | Traversal Data |
|----|------|-------------|----------------|
| MC-WORK-001 | Scope Definition | What are we building, why, for whom | artifacts: [convergence_brief, assumptions_list, non_goals], failure_modes: {silent: [scope creep], loud: [stakeholder disagreement], clustered: [unclear ownership]}, success: {execution: brief accepted, outcome: fewer re-litigations}, reversibility: two_way |
| MC-WORK-002 | Stakeholder Mapping | Who decides, who reviews, who executes | artifacts: [stakeholder_map, raci_matrix], failure_modes: {silent: [hidden decision maker], loud: [approval bottleneck]}, dependencies: [MC-WORK-001] |
| MC-WORK-003 | Decision Making | Evaluate options, assess reversibility, commit | artifacts: [decision_record, tradeoff_matrix], failure_modes: {silent: [undocumented assumption], loud: [irreversible mistake]}, reversibility: varies |
| MC-WORK-004 | Status Communication | Update stakeholders on progress/risks/decisions | artifacts: [status_update, risk_register], failure_modes: {silent: [information hiding], loud: [surprise escalation]} |
| MC-WORK-005 | Task Decomposition | Break complex work into bounded steps | artifacts: [task_breakdown, dependency_graph], failure_modes: {silent: [hidden dependency], clustered: [parallel work collision]} |
| MC-WORK-006 | Quality Review | Evaluate output against acceptance criteria | artifacts: [review_checklist, gap_analysis], failure_modes: {silent: [rubber stamp], loud: [scope dispute]}, dependencies: [MC-WORK-001] |
| MC-WORK-007 | Knowledge Capture | Extract and store what was learned | artifacts: [lessons_learned, pattern_library_entry], failure_modes: {silent: [knowledge lost to context window]}, success: {outcome: future queries benefit} |
| MC-WORK-008 | Handoff | Transfer responsibility with full context | artifacts: [handoff_document, context_package], failure_modes: {silent: [context loss], loud: [responsibility gap]}, dependencies: [MC-WORK-004] |

### Domain: data (Data quality, structure, evaluation — any domain)
*"Working with data. Quality, structure, annotation, evaluation."*

| ID | Name | Description | Traversal Data |
|----|------|-------------|----------------|
| MC-DATA-001 | Data Quality Assessment | Measure accuracy, completeness, consistency | artifacts: [quality_report, error_taxonomy], failure_modes: {silent: [unmeasured drift], loud: [data corruption discovered late]} |
| MC-DATA-002 | Taxonomy / Ontology Design | Classify problems into structured categories | artifacts: [taxonomy_yaml, signal_index], failure_modes: {silent: [classification gap], loud: [conflicting categories]}, success: {execution: all queries classifiable, outcome: routing accuracy >50%} |
| MC-DATA-003 | Annotation Workflow | Label data with quality controls | artifacts: [annotation_guidelines, quality_rubric, inter_rater_report], failure_modes: {silent: [labeler drift], loud: [disagreement], clustered: [ambiguous guidelines]} |
| MC-DATA-004 | Evaluation Framework | Measure AI system quality systematically | artifacts: [golden_dataset, eval_harness, baseline_report], failure_modes: {silent: [wrong metric], loud: [eval doesn't match production]}, dependencies: [MC-DATA-001] |
| MC-DATA-005 | Data Pipeline Design | Move data from source to destination with governance | artifacts: [pipeline_spec, data_flow_diagram], failure_modes: {silent: [schema drift], loud: [pipeline failure]}, dependencies: [MC-DATA-001] |
| MC-DATA-006 | Privacy / Compliance | PII detection, data minimization, regulatory requirements | artifacts: [privacy_impact_assessment, data_map], failure_modes: {silent: [PII leak undetected], loud: [regulatory violation]}, reversibility: one_way (once leaked, cannot unleak) |

### Domain: deployment (Getting systems to production and keeping them running)
*"Deploy, monitor, iterate, scale."*

| ID | Name | Description | Traversal Data |
|----|------|-------------|----------------|
| MC-DEPLOY-001 | POC Execution | Prove value with minimal scope | artifacts: [poc_scope, success_criteria, measurement_plan], failure_modes: {silent: [success theater], loud: [POC scope creep]}, success: {execution: POC delivered, outcome: decision made, safety: no production impact} |
| MC-DEPLOY-002 | Customer Onboarding | Get a customer team to first value | artifacts: [onboarding_plan, time_to_value_metric], failure_modes: {silent: [user abandonment], loud: [integration failure], clustered: [champion leaves]} |
| MC-DEPLOY-003 | Workshop Delivery | Run interactive sessions that change behavior | artifacts: [workshop_agenda, hands_on_exercise, feedback_survey], failure_modes: {silent: [no behavior change], loud: [attendees confused]}, success: {outcome: behavior change at 30 days} |
| MC-DEPLOY-004 | Churn Prevention | Detect and address disengagement before renewal | artifacts: [health_score, intervention_plan], failure_modes: {silent: [silent churn], loud: [angry escalation]}, dependencies: [MC-DEPLOY-002] |
| MC-DEPLOY-005 | System Monitoring | Observe production behavior, detect anomalies | artifacts: [dashboard, alert_rules, incident_log], failure_modes: {silent: [alert fatigue], loud: [missed incident]} |
| MC-DEPLOY-006 | Use Case Expansion | Identify the next governed workflow after first value | artifacts: [use_case_map, expansion_plan, adoption_path], failure_modes: {silent: [tool stays single-use], loud: [new workflow lacks boundary review]}, dependencies: [MC-DEPLOY-002, MC-DEPLOY-004] |
| MC-DEPLOY-007 | Documentation | Produce accurate, maintainable docs | artifacts: [user_guide, api_reference, runbook], failure_modes: {silent: [docs drift from reality], loud: [missing critical doc]} |

### Domain: legal (Legal-specific — from Palette RIU-700s)
*"Privilege, compliance, deadlines, risk."*

| ID | Name | Description | Traversal Data |
|----|------|-------------|----------------|
| MC-LEGAL-001 | Privilege Assessment | Determine if content is attorney-client privileged | artifacts: [privilege_log], failure_modes: {silent: [privilege waived unknowingly]}, reversibility: one_way, blocks_external: true, requires_local: true |
| MC-LEGAL-002 | Legal Research | Find precedent, statute, regulation | artifacts: [research_memo, citation_list], blocks_external: false |
| MC-LEGAL-003 | Obligation / Deadline Tracking | Monitor legal, regulatory, consent, filing, and response deadlines | artifacts: [obligation_register, deadline_calendar, alert_config], failure_modes: {silent: [missed obligation], loud: [late escalation]}, reversibility: one_way |
| MC-LEGAL-004 | Contract Review | Analyze contract terms, flag risks | artifacts: [clause_analysis, risk_matrix], blocks_external: true, requires_local: true |
| MC-LEGAL-005 | Compliance Audit | Verify regulatory compliance | artifacts: [compliance_checklist, gap_report], dependencies: [MC-DATA-006] |

---

## Core Node Utility Contract

This is the usefulness audit for the shipped ontology. Each node has a concrete reason to exist in MC runtime; otherwise it should not ship.

| Node | Runtime Use | Why It Benefits MC |
|------|-------------|--------------------|
| INTENT-PROTECT | Forces local-only routing and boundary-first reasoning | Prevents leaks and makes sensitive work safe by default |
| INTENT-RESEARCH | Allows governed external research after sanitization | Keeps research useful without bypassing the firewall |
| INTENT-DECIDE | Activates reversibility/tradeoff framing | Improves high-stakes choices and one-way-door handling |
| INTENT-CREATE | Guides artifact generation | Makes MC produce usable deliverables, not just advice |
| INTENT-DIAGNOSE | Activates failure-mode/root-cause framing | Turns vague problems into actionable repair paths |
| INTENT-REFLECT | Keeps self-audit and path review local | Lets MC learn from itself without externalizing sensitive history |
| MC-GOV-001 | Classifies sanitizer, PHI/PII, firewall, and data-boundary work | Core to the trust story and every client boundary |
| MC-GOV-002 | Classifies routing/classification failures | Converts wrong-routing incidents into ontology improvement work |
| MC-GOV-003 | Classifies path records, audit logs, decision memory | Makes MC's compounding memory inspectable and defensible |
| MC-GOV-004 | Classifies Codex/agent task envelopes and result validation | Governs the agents that modify MC itself |
| MC-GOV-005 | Classifies model choice and direct routing questions | Keeps @mention/direct model routing inside governance |
| MC-WORK-001 | Classifies scoping and project-definition requests | Prevents unbounded work and creates reusable briefs |
| MC-WORK-002 | Classifies stakeholder/ownership questions | Reduces approval and accountability failures |
| MC-WORK-003 | Classifies domain-specific decision work after INTENT-DECIDE fires | Adds artifacts and failure modes beyond the intent label |
| MC-WORK-004 | Classifies updates, risks, and progress communication | Improves client/team operating rhythm |
| MC-WORK-005 | Classifies decomposition/planning of complex tasks | Helps MC turn large work into bounded agent-safe steps |
| MC-WORK-006 | Classifies review, acceptance, and gap-analysis work | Raises output quality before client delivery |
| MC-WORK-007 | Classifies lesson extraction and reusable pattern capture | Directly supports compounding memory |
| MC-WORK-008 | Classifies handoff and continuity work | Prevents context loss across agents, sessions, and teams |
| MC-DATA-001 | Classifies data quality and drift questions | Useful across health, logistics, education, and AI evals |
| MC-DATA-002 | Classifies taxonomy/ontology/schema design | Dogfoods MC's own ontology and customer classification maps |
| MC-DATA-003 | Classifies annotation/labeling workflows | Supports Encord-like use cases and educational/health data review |
| MC-DATA-004 | Classifies eval, golden dataset, and measurement work | Prevents hand-wavy claims and tracks system quality |
| MC-DATA-005 | Classifies data movement and integration pipelines | Supports Tropical IT operations and MC deployment plumbing |
| MC-DATA-006 | Classifies privacy/compliance/data-minimization work | Cross-client safety boundary for PHI, child data, pricing, and secrets |
| MC-DEPLOY-001 | Classifies POC planning and success criteria | Keeps trials measurable and reversible |
| MC-DEPLOY-002 | Classifies onboarding and first-value work | Makes customer rollout explicit instead of ad hoc |
| MC-DEPLOY-003 | Classifies workshop/training delivery | Supports enablement-heavy deployments and behavior change |
| MC-DEPLOY-004 | Classifies engagement/churn-risk work | Helps MC detect stalled adoption before renewal risk |
| MC-DEPLOY-005 | Classifies monitoring, incidents, and production health | Keeps deployed MC instances observable |
| MC-DEPLOY-006 | Classifies next-workflow expansion after first value | Expands usefulness without treating it as generic sales |
| MC-DEPLOY-007 | Classifies docs/runbooks/user guidance | Keeps deployable systems operable by humans |
| MC-LEGAL-001 | Classifies privilege-sensitive content | High-stakes legal boundary, always local |
| MC-LEGAL-002 | Classifies public law/regulation research | Enables useful legal research while preserving boundary distinctions |
| MC-LEGAL-003 | Classifies obligation/deadline tracking | Broadly useful for legal, compliance, consent, and regulatory operations |
| MC-LEGAL-004 | Classifies contract review and clause-risk work | Common professional workflow with confidentiality risk |
| MC-LEGAL-005 | Classifies compliance audits and gap checks | Connects legal/compliance work to privacy and evidence artifacts |

### Node Retirement Rule

A node is removed, merged, or moved to a customer extension if any of these are true after golden testing and path-record review:

1. It receives fewer than 1% of routed non-test queries across two active deployment cycles.
2. Its top matched queries are better handled by another node with no loss of context quality.
3. Its traversal data does not change the prompt, policy, output artifact, or audit trail.
4. It creates repeated low-confidence or wrong-route gap signals.
5. It exists only for sales narrative and not for runtime behavior.

### Customer Example Node Utility

The example customer nodes are not decorative. They represent the first node candidates that should survive customer-specific golden testing.

| Node | Runtime Use | Why It Benefits MC |
|------|-------------|--------------------|
| TI-001 | Classifies quote/pricing/duty requests | Gives Tropical IT a governed quote workflow without leaking pricing rules |
| TI-002 | Classifies customs/import/export status work | Adds country-specific logistics failure modes and document checks |
| TI-003 | Classifies inventory and reorder questions | Supports field operations and offline/last-known inventory surfaces |
| TI-004 | Classifies order status across quote, customs, inventory, delivery | Provides the central Tropical IT customer-service workflow |
| TI-005 | Classifies supplier/OEM pricing and lead-time work | Helps compare vendors while preserving proprietary terms |
| SIR-001 | Classifies student progress and assessment data | Keeps child data local and guides teacher-facing reports |
| SIR-002 | Classifies curriculum localization/adaptation | Supports refugee/IB context without generic lesson-plan drift |
| SIR-003 | Classifies teacher-support and activity planning | Gives teachers practical artifacts for next-class use |
| SIR-004 | Classifies offline queue/sync/session issues | Directly supports PWA offline-first deployment in low-connectivity contexts |
| SIR-005 | Classifies safeguarding, consent, child-protection boundaries | Makes child safety a first-class governance path |
| KH-001 | Classifies medical-information response workflows | Keeps regulated medical affairs responses auditable and local when needed |
| KH-002 | Classifies publication/manuscript tracking | Supports consultant workflows around scientific publication operations |
| KH-003 | Classifies consultant AI workflow adoption | Connects Komodo/Mavens rollout to onboarding and adoption metrics |
| KH-004 | Classifies PHI boundary verification | Provides a provable HIPAA-grade boundary test path |

Customer nodes also follow the retirement rule. If real customer queries do not hit them, they should not remain in that instance.

---

## Layer 3: Customer Extensions (Not shipped — configured per deployment)

Each customer adds their own domain nodes. These EXTEND the core, they don't replace it.

### Example: Tropical IT extension (`ontology/customers/tropical-it.yaml`)

```yaml
domain: logistics
customer: tropical-it
nodes:
  - id: TI-001
    name: Multi-Country Quote Generation
    description: Generate pricing across 9 countries with duties and FX
    signals: [quote, pricing, landed cost, duty, customs]
    artifacts: [quote_document, duty_calculation, fx_snapshot]
    failure_modes:
      silent: [stale FX rate used]
      loud: [duty classification wrong]
    success_conditions:
      execution: Quote generated in <10 seconds
      outcome: Customer accepts quote
    dependencies: []
    coordinates: {industry: hardware, category: distribution}
    
  - id: TI-002
    name: Customs Clearance Tracking
    description: Monitor shipment through import/export stages per country
    signals: [customs, clearance, import, export, HS code, duty]
    artifacts: [clearance_status, import_document_checklist]
    failure_modes:
      silent: [document missing at border]
      loud: [shipment held by customs]
      clustered: [new country regulation not reflected]
    dependencies: [TI-001]
    coordinates: {industry: hardware, category: logistics}
    
  - id: TI-003
    name: Inventory by Country
    description: Stock levels across 9 countries, reorder alerts
    signals: [inventory, stock, reorder, warehouse, availability]
    artifacts: [inventory_snapshot, reorder_recommendation]
    failure_modes:
      silent: [inventory drift between systems]
    
  - id: TI-004
    name: Order Lifecycle
    description: Track order from quote through delivery across borders
    signals: [order, shipment, delivery, tracking, status]
    artifacts: [order_timeline, shipment_tracker]
    dependencies: [TI-001, TI-002, TI-003]
    
  - id: TI-005
    name: Supplier / OEM Management
    description: Track OEM pricing, lead times, availability
    signals: [supplier, OEM, vendor, lead time, availability]
    artifacts: [supplier_scorecard, pricing_comparison]
```

### Example: Still I Rise extension (`ontology/customers/still-i-rise.yaml`)

```yaml
domain: education
customer: still-i-rise
nodes:
  - id: SIR-001
    name: Student Progress Assessment
    description: Track learning outcomes per student across subjects
    signals: [assessment, progress, student, mastery, grade, score]
    artifacts: [progress_report, mastery_map]
    failure_modes:
      silent: [assessment bias undetected]
      loud: [student misplaced in level]
    blocks_external: true  # Student data never leaves
    requires_local: true
    coordinates: {industry: education, category: assessment}
    
  - id: SIR-002
    name: Curriculum Adaptation
    description: Modify IB curriculum for local context and language
    signals: [curriculum, adaptation, IB, local, language, translation]
    artifacts: [adapted_module, language_bridge_plan]
    failure_modes:
      silent: [cultural mismatch in content]
      loud: [IB compliance violation]
    dependencies: []
    
  - id: SIR-003
    name: Teacher Support
    description: Provide teaching resources, lesson plans, coaching
    signals: [teacher, lesson, plan, coaching, resource, activity]
    artifacts: [lesson_plan, activity_guide, coaching_notes]
    success_conditions:
      execution: Teacher has resources for next week
      outcome: Student engagement improves
    
  - id: SIR-004
    name: Offline Learning Session
    description: Queue-based session when connectivity is intermittent
    signals: [offline, queue, sync, session, connectivity]
    artifacts: [queued_session_log, sync_report]
    failure_modes:
      silent: [sync conflict on reconnect]
    
  - id: SIR-005
    name: Child Safeguarding
    description: Ensure no child PII leaves the system, comply with COPPA/GDPR-K
    signals: [safeguarding, child protection, COPPA, minor, parental consent]
    artifacts: [safeguarding_audit, consent_log]
    blocks_external: true
    requires_local: true
    reversibility: one_way  # Consent records are permanent
    dependencies: [MC-DATA-006, MC-GOV-001]
```

### Example: Komodo/Mavens extension (`ontology/customers/komodo.yaml`)

```yaml
domain: life-sciences
customer: komodo-mavens
nodes:
  - id: KH-001
    name: Medical Information Response
    description: Generate compliant responses to HCP medical inquiries
    signals: [medical information, HCP, inquiry, compliant response, off-label]
    artifacts: [response_document, compliance_review_trail]
    failure_modes:
      silent: [off-label information included without disclaimer]
      loud: [response contradicts product label]
    blocks_external: true  # PHI in the question
    requires_local: true
    reversibility: one_way  # Response is a regulatory record
    coordinates: {industry: pharma, category: medical-affairs}
    
  - id: KH-002
    name: Publication Planning
    description: Track manuscripts through submission and review
    signals: [publication, manuscript, submission, journal, peer review]
    artifacts: [publication_tracker, submission_checklist]
    
  - id: KH-003
    name: Consultant AI Workflow
    description: Build and deploy AI-assisted workflows for consultants
    signals: [workflow, consultant, enablement, adoption, AI tool]
    artifacts: [workflow_spec, adoption_metrics, training_module]
    failure_modes:
      silent: [consultant bypasses workflow]
      loud: [workflow produces wrong output]
    success_conditions:
      execution: Workflow deployed to consultant team
      outcome: Adoption >80% at 30 days
    dependencies: [MC-DEPLOY-002]
    
  - id: KH-004
    name: PHI Boundary Verification
    description: Verify no patient data reaches external models
    signals: [PHI, HIPAA, patient data, boundary, verification]
    artifacts: [boundary_test_report, firewall_audit]
    blocks_external: true
    requires_local: true
    dependencies: [MC-GOV-001, MC-DATA-006]
```

---

## Node Count Summary

| Layer | Nodes | Ships With |
|-------|-------|------------|
| **Intents** | 6 | Every MC install |
| **Core: governance** | 5 | Every MC install |
| **Core: work** | 8 | Every MC install |
| **Core: data** | 6 | Every MC install |
| **Core: deployment** | 7 | Every MC install |
| **Core: legal** | 5 | Every MC install |
| **Core domain total** | 31 | Every MC install |
| **Shipped total** | 37 | Every MC install |
| **Tropical IT extension** | 5+ | TI deployment only |
| **Still I Rise extension** | 5+ | SIR deployment only |
| **Komodo extension** | 4+ | KH deployment only |

**Shipped ontology = 37 nodes** (6 intents + 31 core domain nodes, vs current 137). Smaller, more focused, richer per node.

Each customer extension adds 4-10 nodes specific to its domain. Total per deployment: ~41-47 nodes with full traversal data (artifacts, failure modes, success conditions, dependencies, coordinates, reversibility, journey stage).

---

## OntologyNode Schema (MC-native)

```python
@dataclass
class OntologyNode:
    """MC-native ontology node with classification + traversal layers."""
    
    # ── Classification Layer (always loaded, used by classify()) ──
    id: str
    name: str
    description: str
    domain: str                        # governance | work | data | deployment | legal | customer
    parent: Optional[str] = None       # Domain hierarchy only. Never INTENT-*.
    signals: list[str] = field(default_factory=list)
    blocks_external: bool = False
    requires_local: bool = False
    default_intent: Optional[str] = None       # If absent, intent pass controls routing
    allowed_intents: list[str] = field(default_factory=list)  # Empty = all intents allowed
    evidence_tier: int = 2
    
    # Domain nodes do not inherit a universal default. Most should leave
    # default_intent empty and let the intent pass decide. Set it only when
    # the domain itself implies a safe default, e.g. Privilege Assessment -> PROTECT.

    # ── Traversal Layer (loaded at startup, used by CONTEXT/REASON) ──
    artifacts: list[str] = field(default_factory=list)
    failure_modes: dict[str, list[str]] = field(default_factory=dict)  # {silent: [], loud: [], clustered: []}
    success_conditions: dict[str, str] = field(default_factory=dict)   # {execution: "", outcome: "", safety: ""}
    dependencies: list[str] = field(default_factory=list)
    coordinates: dict[str, str] = field(default_factory=dict)          # {industry: "", category: "", use_case: ""}
    reversibility: str = "two_way"     # one_way | two_way | mixed
    journey_stage: str = "foundation"  # foundation | retrieval | orchestration | implementation | deployment
    agent_types: list[str] = field(default_factory=list)
    workstream: str = ""
    
    # ── Graph edges ──
    escalates_to: list[str] = field(default_factory=list)
    resolves_to: list[str] = field(default_factory=list)
    co_occurs_with: list[str] = field(default_factory=list)

    # ── Migration / compatibility ──
    legacy_riu_id: Optional[str] = None  # Old RIU mapping, only while migrating
```

---

## How Classification Changes

```python
def classify(self, query, intent=None):
    """Two-pass classification. Intent first, then domain."""
    
    # Pass 1: INTENT (what do you want to do?)
    intent_result = self._classify_intent(query, explicit_intent=intent)
    # Returns: INTENT-PROTECT, INTENT-RESEARCH, etc.
    
    # Pass 2: DOMAIN (what is this about?)
    domain_result = self._classify_domain(query, intent=intent_result)
    # Returns: MC-WORK-001, TI-002, KH-003, etc.
    
    # Combine
    return ClassificationResult(
        intent=intent_result,           # INTENT-PROTECT
        node=domain_result,             # MC-WORK-001
        riu_id=domain_result.id,        # compatibility until old pipeline fields are renamed
        # ... confidence, signals, etc.
    )
```

No more CORE-hijacking. Intent and domain are always separate.

### Intent/Domain Combination Rules

After the two passes, routing combines the results with explicit rules:

| Case | Behavior |
|------|----------|
| User explicitly selects PROTECT or REFLECT | Local-only, regardless of domain |
| Entry gate blocks | Force `INTENT-PROTECT`, local-only |
| Domain node has `blocks_external: true` | Local-only, regardless of intent |
| Domain node has `allowed_intents` and selected intent is absent | Add gap signal and fall back to node default intent |
| Selected intent is RESEARCH and domain allows external | Sanitize first, then external research |

This makes governance a product of both axes without letting either axis hijack the other.

---

## How Context Changes

```python
def build_context(self, classification, knowledge_entries, traversal_index):
    """Build the REASON step prompt with traversal data."""
    
    node = traversal_index.get(classification.node.id)
    
    sections = [
        f"## Classification: {node.name} ({node.id})",
        f"Intent: {classification.intent}",
        f"Domain: {node.domain}",
        f"Confidence: {classification.confidence:.0%}",
    ]
    
    if node.artifacts:
        sections.append(f"\n## Expected Artifacts")
        for a in node.artifacts:
            sections.append(f"  - {a}")
    
    if node.failure_modes:
        sections.append(f"\n## Known Failure Modes")
        for category, modes in node.failure_modes.items():
            sections.append(f"  {category}: {'; '.join(modes)}")
    
    if node.success_conditions:
        sections.append(f"\n## Success Criteria")
        for dim, criterion in node.success_conditions.items():
            sections.append(f"  {dim}: {criterion}")
    
    if node.dependencies:
        sections.append(f"\n## Prerequisites")
        for dep_id in node.dependencies:
            dep = traversal_index.get(dep_id)
            sections.append(f"  - {dep.name} ({dep_id})")
    
    if node.reversibility == "one_way":
        sections.append(f"\n⚠ ONE-WAY DOOR: This decision cannot easily be undone.")
    
    # ... knowledge entries, prior paths, research results ...
    
    return "\n".join(sections)
```

---

## How Customer Extension Works

```bash
# Deploy for Tropical IT
mc instance create \
  --customer tropical-it \
  --ontology ontology/customers/tropical-it.yaml \
  --boundary "no-pricing, no-client-data" \
  --block-signals "proprietary, internal only" \
  --models claude \
  --surfaces browser,pwa
```

The engine loads:
1. `ontology/core/intents.yaml` (6 nodes)
2. `ontology/core/governance.yaml` (5 nodes)
3. `ontology/core/work.yaml` (8 nodes)
4. `ontology/core/data.yaml` (6 nodes)
5. `ontology/core/deployment.yaml` (7 nodes)
6. `ontology/core/legal.yaml` (5 nodes)
7. `ontology/customers/tropical-it.yaml` (5+ nodes)

Total: ~42 nodes, each with full traversal data. Signal index builds automatically from names + descriptions + explicit signals.

### Customer Extension Merge Rules

Customer YAMLs are overlays, not forks:

1. Customer node IDs must be globally unique and prefixed (`TI-*`, `SIR-*`, `KH-*`).
2. Customer nodes may depend on core nodes, but core nodes may not depend on customer nodes.
3. Customer nodes may override deployment config such as `block_signals`, but may not weaken core governance rules.
4. If a customer node sets `blocks_external: true`, it must also set `requires_local: true`.
5. The merge fails closed on duplicate IDs, broken dependencies, malformed traversal fields, or invalid governance combinations.
6. Golden datasets are per instance: core golden cases always run, then customer golden cases run.

---

## Migration Path from Current State

| Step | What | Risk |
|------|------|------|
| 1 | Extend `OntologyNode` to accept traversal fields while preserving current fields | Low — unknown fields currently get filtered |
| 2 | Write 6 intent nodes + 31 core domain nodes as new YAML files in `ontology/core/` | None — new files, don't touch existing |
| 3 | Write loader that can load `ontology/core/` + optional `ontology/customers/*.yaml` | None — new path, old loader remains |
| 4 | Write TraversalIndex class and add context sections for artifacts, failures, success, deps | Low — additive |
| 5 | Update validator for generated signal coverage and new governance fields | Low — health check semantics change |
| 6 | Split classify() into intent pass + domain pass behind a feature flag | Medium — changes classification behavior |
| 7 | Run golden dataset against new ontology, compare to current baseline and specific dogfood cases | Measurement, not change |
| 8 | If new ontology ≥ baseline and passes governance goldens, switch default loader. If not, iterate signals. | Reversible |
| 9 | Remove old `ontology/domains/ai-enablement.yaml` only after two clean sessions on new loader | Deferred |
| 10 | Write customer extension YAMLs (Tropical IT, Still I Rise, Komodo) | Per deployment |

**TWO-WAY DOOR throughout.** Old ontology stays until new one is proven.

### Minimum Golden Dataset Before Switching

The new ontology is not allowed to become default until these pass:

| Category | Minimum Cases | Examples |
|----------|---------------|----------|
| Intent separation | 30 | Same domain with PROTECT/RESEARCH/DECIDE/CREATE variants |
| Governance | 20 | PHI, child data, privilege, credentials, pricing, public research |
| Dogfood | 15 | Codex adapter, sanitizer, PWA, ontology migration, task envelopes |
| Client extensions | 15 per client | Tropical IT order/quote/customs, SIR offline/child data, KH PHI/medical info |
| Regression | Existing golden set | Must not fall below current baseline |

Pass criteria: no governance false-negatives, classification accuracy at or above current baseline, and every low-confidence case emits a useful gap signal.

---

## What This Changes for the Interview Story

Current: "137 nodes imported from a larger taxonomy."

After: "37 shipped nodes designed for the product: 6 intents and 31 core domain nodes, each with artifacts, failure modes, success criteria, and dependencies. Customer nodes extend the core — Tropical IT adds logistics nodes, Still I Rise adds education/offline nodes. Same pipeline, different map. About 41-47 nodes per deployment, each one rich enough to guide the model through known failure patterns and toward defined success."

That's a better story. Smaller, deeper, customer-shaped.

---

*Design by claude.analysis, 2026-06-15. Reference spec: Palette taxonomy v1.3 (131 RIUs, 2,965 traversable nodes). This design is for MC's runtime ontology — the product, not the toolkit.*
