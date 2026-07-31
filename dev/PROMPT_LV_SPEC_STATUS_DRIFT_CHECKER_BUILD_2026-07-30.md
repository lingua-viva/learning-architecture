# Build Prompt - Lingua Viva Spec Status Drift Checker

You are implementing the next AGV artifact-governance slice after Defect Source Triage.

Read first:

```text
dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md
dev/SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md
dev/INDEX.md
scripts/check_route_reachability.py
scripts/check_ui_contract.py
contracts/ROUTE_REACHABILITY.yaml
contracts/UI_CONTRACT.yaml
tests/test_route_reachability.py
tests/test_ui_contract.py
src/lingua_viva/cli.py
```

## Objective

Build a read-only spec status drift checker:

```text
dev specs + dev/INDEX.md + source/test/contracts
  -> structured drift report
  -> missing index rows
  -> stale status claims
  -> missing evidence files/tests
  -> route-contract gaps
```

This does not fix status drift automatically. It classifies and reports it so operators can update docs honestly.

## Hard Rules

1. **Do not commit.**
2. **Do not auto-edit `dev/INDEX.md`, specs, prompts, contracts, source, or tests from the checker.**
3. **Do not add this to preflight in this build.**
4. **No network. No LLM.**
5. **Keep findings conservative to avoid noisy false positives.**
6. **Do not revert unrelated dirty files.**

## Step 0: Baseline

Run:

```bash
git status --short --branch --untracked-files=all
pytest -q tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

The tree may contain unrelated runtime proposal drift or in-flight spec/prompt files. Do not revert unrelated work.

## Step 1: Add Module

Create:

```text
src/lingua_viva/spec_status.py
```

Implement:

- `SpecRecord`
- `SpecStatusFinding`
- `SpecStatusReport`
- `discover_specs(root=None)`
- `parse_index(index_path=None)`
- `check_spec_status(root=None)`
- `report_to_json(report)`
- `report_to_markdown(report)`

Recommended stable finding codes:

- `missing_index_entry`
- `status_drift`
- `missing_claimed_file`
- `missing_claimed_test`
- `missing_spec_prompt_pair`
- `orphan_prompt`
- `route_contract_gap`
- `ui_contract_evidence_gap`
- `malformed_index`

Use stable severities:

- `info`
- `warn`
- `fail`

## Step 2: Discovery And Parsing

Scan:

```text
dev/*SPEC*.md
dev/specs/*SPEC*.md
dev/*PROMPT*.md
dev/INDEX.md
```

Parse from specs:

- title from first `# ...` heading;
- date from metadata line or filename;
- status from `Status:` metadata line;
- references to `src/`, `tests/`, `contracts/`, `scripts/`, `static/`, `dev/reports/`;
- concrete API routes in the form `GET /api/...`, `POST /api/...`, `PUT /api/...`, `DELETE /api/...`.

Parse `dev/INDEX.md` rows enough to map linked spec paths to status/evidence text. Do not try to build a perfect Markdown parser; implement a stable conservative table-row parser.

## Step 3: Findings

Implement the rules in the spec:

- missing index row -> `warn`;
- spec header/index contradiction -> `warn`;
- built/shipped spec claiming missing concrete source/test/evidence file -> `fail`;
- draft "Create/Add/Build `src/foo.py`" planned target -> no missing-file failure;
- top-level spec without prompt pair -> `warn`;
- prompt without spec -> `warn`;
- route exists in `src/web.py` but is absent from `contracts/ROUTE_REACHABILITY.yaml` -> `warn`;
- UI protected file status claims without contract evidence -> `warn`, but do not duplicate hash checks.

Keep historical files lenient: if an old spec says "see INDEX" or is clearly a reference doc, use `info` rather than `warn`.

## Step 4: CLI

Add module CLI:

```bash
python3 -m src.lingua_viva.spec_status --json
python3 -m src.lingua_viva.spec_status --markdown
python3 -m src.lingua_viva.spec_status --strict
```

Behavior:

- default exits `1` only on `fail`;
- `--strict` exits `1` on `warn` or `fail`;
- `--json` prints JSON;
- `--markdown` prints Markdown;
- default can print concise Markdown.

Optional project CLI:

```bash
python3 -m src.lingua_viva.cli spec-status --json
```

Skip project CLI if it creates churn.

## Step 5: Tests

Add:

```text
tests/test_spec_status.py
```

Cover:

- discovers specs from both top-level `dev/` and `dev/specs/`;
- parses index row status/evidence;
- missing index row emits `warn`;
- status contradiction emits `warn`;
- built spec with missing concrete `src/...` file emits `fail`;
- draft planned "Create `src/foo.py`" does not fail;
- missing concrete test claim emits warning/failure based on status;
- missing prompt pair emits `warn`;
- orphan prompt emits `warn`;
- existing route absent from route reachability emits `warn`;
- JSON and Markdown reports contain summary and finding codes;
- CLI exit behavior default vs `--strict`;
- checker does not mutate input files.

Use temporary mini-repos for most tests. Avoid depending on current full `dev/INDEX.md` contents except for one smoke test if useful.

## Step 6: Verification

Run focused:

```bash
pytest -q \
  tests/test_spec_status.py \
  tests/test_route_reachability.py \
  tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

Then run:

```bash
pytest -q
```

Fix real regressions. If the checker reports real current repo drift, do not auto-fix it unless explicitly asked; document the findings in the final report.

## Final Report

Report:

- files changed;
- public functions added;
- CLI behavior;
- finding codes;
- focused test result;
- preflight result;
- full suite result;
- any current repo drift the checker reports.

Do not claim this synchronizes `dev/INDEX.md`. It only detects drift.
