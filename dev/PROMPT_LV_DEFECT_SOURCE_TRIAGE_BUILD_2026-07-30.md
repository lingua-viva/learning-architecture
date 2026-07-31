# Build Prompt - Lingua Viva Education Defect Source Triage

You are implementing the next matrix-ranked Lingua Viva improvement after Cohort Lesson Planning.

Read first:

```text
dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md
dev/SPEC_LV_DEFECT_SOURCE_TRIAGE_2026-07-30.md
src/lingua_viva/gap_audit.py
src/lingua_viva/improvement_audit.py
src/lingua_viva/golden_workflows/runner.py
src/lingua_viva/golden_workflows/schema.py
src/lingua_viva/cli.py
src/pipeline.py
src/context_builder.py
contracts/UI_CONTRACT.yaml
contracts/ROUTE_REACHABILITY.yaml
tests/test_gap_audit.py
tests/test_improvement_audit.py
tests/test_golden_workflows.py
tests/test_route_reachability.py
tests/test_ui_contract.py
```

## Objective

Build a read-only defect triage engine:

```text
failure evidence -> owning defect layer -> reasons -> next action
```

The purpose is to stop agents from fixing the wrong layer. A failing test may mean the curriculum source is missing, a checker is stale, the ontology route is wrong, a live connector drifted, or product code is broken. The tool must classify that before anyone patches code.

## Hard Rules

1. **Do not commit.**
2. **No external LLMs or network calls.**
3. **Do not mutate runtime state.**
4. **Do not edit ontology proposals, gap signals, contracts, source ledger, or test expectations from the classifier.**
5. **Do not add this to preflight.**
6. **Use deterministic rules only.**
7. **Keep confidence conservative.**

## Step 0: Baseline

Run:

```bash
git status --short --branch --untracked-files=all
pytest -q tests/test_gap_audit.py tests/test_improvement_audit.py tests/test_golden_workflows.py tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

The working tree may contain unrelated ontology proposal drift from runtime/evaluation state. Do not revert unrelated changes.

## Step 1: Add Defect Triage Module

Create:

```text
src/lingua_viva/defect_triage.py
```

Implement:

- `DefectEvidence`
- `DefectTriageResult`
- `classify_failure(evidence)`
- `triage_pytest_output(text)`
- `triage_gap_signal_record(record)`
- `triage_golden_workflow_result(result)`
- `result_to_markdown(result)`

Stable layers:

- `curriculum_source`
- `checker_logic`
- `ontology_taxonomy`
- `live_layer_drift`
- `product_code`
- `unknown`

Each result must include:

- stable `defect_id`;
- `primary_layer`;
- `confidence` in `[0.0, 1.0]`;
- `secondary_layers`;
- `reasons`;
- `recommended_owner`;
- `recommended_actions`;
- `evidence_hash`.

## Step 2: Deterministic Classifier

Use scoring rules from the spec.

Important mappings:

- UI contract hash/version mismatch -> `checker_logic`
- route reachability stale/deferred mismatch -> `checker_logic`
- low classification confidence / wrong RIU / `OntologyEngine` path failure -> `ontology_taxonomy`
- missing citation / empty retrieval / source ledger absence -> `curriculum_source`
- Slack/Drive/Rime/Ollama/Whisper/provider credentials, timeout, unavailable endpoint -> `live_layer_drift`
- preview writes, privacy bypass, incomplete audit receipt, route 500 from local code -> `product_code`
- no useful evidence -> `unknown`

Tie-breakers:

1. Contract-only drift beats product code.
2. Provider/credential/model-load drift beats product code unless a local invariant failed.
3. Privacy/approval/write invariant beats everything except explicit checker-only drift.
4. Classification/RIU/domain evidence beats generic product code.
5. Source/citation evidence beats generic product code.

## Step 3: Pytest Output Parsing

`triage_pytest_output(text)` should:

- split common pytest failure sections;
- produce one result per failed test when possible;
- include test name in the evidence;
- return one `unknown` result for non-empty unparseable output.

Do not try to implement a perfect parser. Implement enough for common pytest output and keep fallback behavior stable.

## Step 4: Gap Signal And Golden Workflow Triage

`triage_gap_signal_record(record)` should use:

- `entry_node`
- `domain`
- `gap_signals`
- `session_id`

Examples:

- `low_classification_confidence:*` -> `ontology_taxonomy`
- `weak_classification:*` -> `ontology_taxonomy`
- `no_knowledge_at_node:*` -> `ontology_taxonomy` or `curriculum_source` if source/retrieval words are present
- `voice_loop_failure:stt_mismatch` -> `live_layer_drift` with possible checker secondary
- `voice_loop_failure:pipeline_error` -> `product_code`
- `voice_loop_failure:tone_mismatch` -> `product_code`
- `research_gap:*` -> `curriculum_source`

`triage_golden_workflow_result(result)` should inspect failed steps:

- `source_record` / retrieval / citation step -> `curriculum_source`
- `grounding_result` out of range -> `product_code` or `checker_logic` if assertion-only
- `audit_receipt` incomplete -> `product_code`
- STT/model-load/live credential issue -> `live_layer_drift`

## Step 5: Optional CLI

If low-risk, add:

```bash
python3 -m src.lingua_viva.defect_triage --file failure.txt --json
```

Optional project CLI:

```bash
python3 -m src.lingua_viva.cli triage-defect --file failure.txt --json
```

Skip CLI wiring if it creates churn. The module and tests are the core deliverable.

## Step 6: Tests

Add:

```text
tests/test_defect_triage.py
```

Cover:

- UI contract mismatch -> `checker_logic`;
- route reachability stale expectation -> `checker_logic`;
- low classification confidence / RIU mismatch -> `ontology_taxonomy`;
- missing citation / empty retrieval -> `curriculum_source`;
- provider timeout / missing credentials -> `live_layer_drift`;
- preview writes deliverable or incomplete audit receipt -> `product_code`;
- voice loop failure classes triage deterministically;
- gap signal records classify from `entry_node`, `domain`, and `gap_signals`;
- pytest output with multiple failures returns multiple results;
- empty evidence -> `unknown`;
- markdown output includes layer, confidence, reasons, next actions;
- no mutation of known runtime files.

Use temp files and monkeypatch env vars for mutation tests.

## Step 7: Verification

Run focused:

```bash
pytest -q \
  tests/test_defect_triage.py \
  tests/test_gap_audit.py \
  tests/test_improvement_audit.py \
  tests/test_golden_workflows.py \
  tests/test_route_reachability.py \
  tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

Then run:

```bash
pytest -q
```

Fix real regressions. If a failure is inherited or environment-only, document exact evidence.

## Final Report

Report:

- files changed;
- public functions added;
- layer IDs;
- whether CLI was added or intentionally skipped;
- examples of classification mappings;
- focused test result;
- preflight result;
- full suite result;
- any remaining ambiguity.

Do not claim the tool fixes defects. It only classifies likely ownership and recommends next actions.
