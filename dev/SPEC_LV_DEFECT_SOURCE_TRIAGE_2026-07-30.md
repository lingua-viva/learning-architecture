# SPEC: Lingua Viva Education Defect Source Triage

**Date**: 2026-07-30
**Status**: DRAFT - build handoff
**Source matrix**: `dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md`
**Systems**: EON Education Ontology / EVA Evaluation / AGV Artifact Governance
**Primary artifact**: `src/lingua_viva/defect_triage.py`
**Selection rationale**: Native Exit Gates, Teacher Decision Flywheel, and Cohort Lesson Planning are now landed. The matrix ranks this next because recent builds added many golden, workflow, route, contract, and education-product tests. The next failure mode is agents fixing the wrong layer when a test fails.

---

## Goal

Build a read-only defect triage engine that classifies evaluation failures into the layer that most likely owns the fix:

```text
test / golden workflow / gap signal / route failure
  -> structured evidence
  -> primary defect layer
  -> confidence + reasons
  -> recommended next action
```

The engine must prevent misplaced fixes. For example:

- Do not patch product code when the checker expectation is stale.
- Do not edit ontology nodes when the source document is missing.
- Do not loosen tests when the live connector drifted.
- Do not update contracts without identifying whether a route is intentionally backend-only.

This is a diagnostic tool only. It must not mutate ontology, tests, sources, contracts, route files, or runtime records.

## Defect Layers

Use stable layer IDs:

| Layer ID | Meaning | Typical Evidence |
|---|---|---|
| `curriculum_source` | The authoritative curriculum/source material is missing, stale, unavailable, or insufficient. | Missing citation, empty retrieval, GIR source gap, document ingest/extraction issue, source ledger missing. |
| `checker_logic` | The test/eval/contract/checker expectation is stale, overspecified, or looking at the wrong artifact. | UI contract hash drift after intended route change, brittle string check, test expects old version, golden expected text no longer matches accepted schema. |
| `ontology_taxonomy` | Classification or domain routing is wrong because ontology nodes, signals, candidate proposals, or weights are wrong/incomplete. | `low_classification_confidence`, weak classification, wrong RIU/domain, candidate proposal aging, ontology path mismatch. |
| `live_layer_drift` | The external or environment-dependent live layer changed or is unavailable. | Provider/network/credential error, Slack/Drive/API drift, Ollama embedding endpoint unavailable, rate limit, model-load failure. |
| `product_code` | The application behavior is actually wrong in deterministic local code. | Stack trace points to app module, invariant violated, route returns wrong shape, privacy gate bypass, approval writes in preview. |
| `unknown` | Evidence is insufficient or contradictory. | No failure text, only generic nonzero exit, multiple layers tied with low confidence. |

The classifier may return secondary layers, but it must always choose one `primary_layer`.

## Product Shape

Add:

```text
src/lingua_viva/defect_triage.py
```

Recommended dataclasses:

```python
@dataclass
class DefectEvidence:
    failure_text: str = ""
    test_name: str = ""
    traceback: str = ""
    command: str = ""
    file_path: str = ""
    route: str = ""
    workflow_id: str = ""
    riu_id: str = ""
    domain: str = ""
    gap_signals: list[str] = field(default_factory=list)
    expected: str = ""
    actual: str = ""
    environment: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

@dataclass
class DefectTriageResult:
    defect_id: str
    primary_layer: str
    confidence: float
    secondary_layers: list[str]
    reasons: list[str]
    recommended_owner: str
    recommended_actions: list[str]
    evidence_hash: str
```

Public helpers:

```python
classify_failure(evidence: DefectEvidence | dict | str) -> DefectTriageResult
triage_pytest_output(text: str) -> list[DefectTriageResult]
triage_gap_signal_record(record: dict) -> DefectTriageResult
triage_golden_workflow_result(result: dict) -> DefectTriageResult
result_to_markdown(result: DefectTriageResult) -> str
```

Optional CLI command:

```bash
python3 -m src.lingua_viva.defect_triage --file failure.txt --json
```

If the project CLI is easy to extend, add:

```bash
python3 -m src.lingua_viva.cli triage-defect --file failure.txt --json
```

Do not add preflight gating in this build. This is an operator diagnostic, not a required gate.

## Classification Rules

Use deterministic scoring. No LLM. No network. Suggested signals:

### `curriculum_source`

Score when text contains:

- `source_record_id`, `source ledger`, `citation`, `GIR`, `grounding`, `retrieval`, `document_store`, `document_retrieval`;
- missing or empty source chunks;
- document ingest/extraction failure;
- "Manuale v1 default citation" or equivalent placeholder citation concerns.

Recommended actions:

- inspect source ledger and document store;
- verify curriculum document ingestion;
- avoid changing tests until source availability is confirmed.

### `checker_logic`

Score when text contains:

- `UI_CONTRACT`, `ROUTE_REACHABILITY`, `EXPECTED_VERSION`, `hash mismatch`;
- stale route reachability expectation;
- brittle exact text expectation;
- "expected old version" / "contract protected file changed";
- failure in tests that only assert the test harness/contract metadata.

Recommended actions:

- verify whether product behavior changed intentionally;
- update contract/version only if intended;
- update checker expectation with evidence, not by weakening coverage.

### `ontology_taxonomy`

Score when text contains:

- `OntologyEngine`, `ClassificationResult`, `riu_id`, `entry_node`, `domain`;
- `low_classification_confidence`, `weak_classification`, `unknown_domain`, `no_knowledge_at_node`;
- `ontology/proposals/CAND-`, candidate aging, learned weights, path records.

Recommended actions:

- inspect ontology node/domain and candidate proposals;
- add or correct ontology taxonomy only if the product behavior is otherwise correct.

### `live_layer_drift`

Score when text contains:

- `Slack`, `Google Drive`, `Rime`, `Whisper`, `Ollama`, provider/API names;
- credential, timeout, rate limit, network, model-load, unavailable endpoint;
- skip reason such as `SKIPPED_MISSING_CREDENTIALS`.

Recommended actions:

- verify credentials/environment;
- isolate hermetic behavior before changing product code;
- document live-only drift if hermetic tests pass.

### `product_code`

Score when text contains:

- stack traces into `src/web.py`, `src/education/*`, `src/lingua_viva/*`, `src/pipeline.py`;
- invariant language such as "preview wrote deliverable", "privacy gate bypassed", "route returned 500", "audit receipt incomplete";
- assertion comparing API behavior to a stable accepted contract.

Recommended actions:

- reproduce with focused test;
- patch the smallest owning module;
- add regression coverage.

### `unknown`

Return when no layer reaches the confidence threshold or when tied high scores cannot be resolved.

Recommended actions:

- ask for full command output;
- capture traceback, route, workflow id, and relevant gap signals.

## Tie-Breaking

Use deterministic tie-breaking:

1. If the evidence says a route/contract version drifted and the failure is only contract metadata, prefer `checker_logic`.
2. If an external provider/credential/model-load string is present, prefer `live_layer_drift` unless a local deterministic invariant also failed.
3. If a privacy/approval/write invariant failed, prefer `product_code`.
4. If classification confidence or RIU/domain is central, prefer `ontology_taxonomy`.
5. If citation/source availability is central, prefer `curriculum_source`.
6. Otherwise `unknown`.

Confidence should be in `[0.0, 1.0]`. Keep it conservative; `0.55` with clear reasons is better than fake certainty.

## Integration Points

This build should be standalone and read-only, but it should understand existing artifacts:

- `memory/data/gap_signals.ndjson`
- `src/lingua_viva/improvement_audit.py`
- `src/lingua_viva/gap_audit.py`
- `src/lingua_viva/golden_workflows/runner.py`
- `contracts/UI_CONTRACT.yaml`
- `contracts/ROUTE_REACHABILITY.yaml`
- ontology candidate files under `ontology/proposals/`

Do not modify these artifacts except for tests if needed.

## Tests

Add:

```text
tests/test_defect_triage.py
```

Minimum coverage:

1. UI contract version mismatch classifies as `checker_logic`.
2. Route reachability stale expectation classifies as `checker_logic`.
3. Low classification confidence / wrong RIU evidence classifies as `ontology_taxonomy`.
4. Missing citation / empty retrieval evidence classifies as `curriculum_source`.
5. Provider timeout / missing credentials classifies as `live_layer_drift`.
6. Preview writing deliverables or incomplete audit receipt classifies as `product_code`.
7. Voice loop `stt_mismatch` or model-load failure produces deterministic triage.
8. Gap signal records classify using `entry_node`, `domain`, and `gap_signals`.
9. Pytest output with multiple failures returns one result per failed test.
10. Unknown or empty evidence returns `unknown` with low confidence and an action asking for more evidence.
11. `result_to_markdown()` contains primary layer, confidence, reasons, and next actions.
12. No mutation: classifier does not write to gap-signal, ontology proposal, contract, or source files.

Focused verification:

```bash
pytest -q \
  tests/test_defect_triage.py \
  tests/test_gap_audit.py \
  tests/test_improvement_audit.py \
  tests/test_golden_workflows.py \
  tests/test_route_reachability.py \
  tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
pytest -q
```

## Acceptance Criteria

- Build produces deterministic triage results without network or LLM calls.
- Every result has stable `primary_layer`, `confidence`, `reasons`, and `recommended_actions`.
- Known failure examples map to the expected defect layer.
- Multi-failure pytest output is split into multiple results.
- Gap-signal and golden-workflow records can be triaged directly.
- No runtime state is mutated by classification.
- Focused tests, preflight, and full suite pass.
- Working tree remains uncommitted unless the operator explicitly asks for a commit.
