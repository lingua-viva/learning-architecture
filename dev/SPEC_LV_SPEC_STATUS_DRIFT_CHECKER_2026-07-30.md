# SPEC: Lingua Viva Spec Status Drift Checker

**Date**: 2026-07-30
**Status**: DRAFT - build handoff
**Source matrix**: `dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md`
**Systems**: AGV Artifact Governance / HTH Health / SRF Surfaces
**Primary artifact**: `src/lingua_viva/spec_status.py`
**Selection rationale**: Native Exit Gates, Teacher Decision Flywheel, Cohort Lesson Planning, and Defect Source Triage are now queued/built in rapid succession. The matrix ranks this next because `dev/INDEX.md` and individual spec status headers have repeatedly lagged behind code, tests, route contracts, and reports.

---

## Goal

Build a read-only spec status drift checker:

```text
spec corpus + dev/INDEX.md + source tree + tests
  -> structured status report
  -> missing index rows
  -> stale status claims
  -> missing evidence files/tests
  -> actionable warnings
```

The checker must keep documentation honest without becoming another source of churn. It reports drift; it does not rewrite specs, commit files, or mark work shipped automatically.

## Problem Being Solved

This repo uses `dev/INDEX.md` as the single source of truth for spec status, but fast parallel build windows create predictable drift:

- new top-level `dev/SPEC_*.md` files are not always indexed;
- status headers inside specs can disagree with `dev/INDEX.md`;
- specs or prompts claim routes/tests/files that no longer exist;
- backend routes are added without route reachability classification;
- UI/web route changes require `UI_CONTRACT` ceremony;
- reports say "built" but evidence files are missing or tests are absent.

Existing gates cover some of this:

- `scripts/check_route_reachability.py`
- `scripts/check_ui_contract.py`
- `tests/test_route_reachability.py`
- `tests/test_ui_contract.py`

This build should not duplicate those gates. It should add the missing documentation/status layer.

## Product Shape

Add:

```text
src/lingua_viva/spec_status.py
```

Recommended dataclasses:

```python
@dataclass
class SpecRecord:
    path: str
    title: str
    date: str
    header_status: str
    indexed: bool
    index_status: str
    claimed_files: list[str]
    claimed_tests: list[str]
    claimed_routes: list[str]
    evidence_refs: list[str]

@dataclass
class SpecStatusFinding:
    severity: str              # info | warn | fail
    code: str
    spec_path: str
    message: str
    evidence: dict

@dataclass
class SpecStatusReport:
    generated_at: str
    spec_count: int
    indexed_count: int
    findings: list[SpecStatusFinding]
    summary: dict
```

Public helpers:

```python
discover_specs(root: Path | None = None) -> list[SpecRecord]
parse_index(index_path: Path | None = None) -> dict
check_spec_status(root: Path | None = None) -> SpecStatusReport
report_to_markdown(report: SpecStatusReport) -> str
report_to_json(report: SpecStatusReport) -> dict
```

Optional CLI:

```bash
python3 -m src.lingua_viva.spec_status --json
python3 -m src.lingua_viva.spec_status --markdown
```

Optional project CLI:

```bash
python3 -m src.lingua_viva.cli spec-status --json
```

Do not add this to preflight in the first build. It should be an operator diagnostic until the warning vocabulary stabilizes.

## Scope

Scan:

```text
dev/*SPEC*.md
dev/specs/*SPEC*.md
dev/*PROMPT*.md
dev/INDEX.md
```

The primary status check is over specs. Prompt files are supporting artifacts and should be used only to verify spec/prompt pairing.

## Detection Rules

### Missing Index Entry

Warn when a spec file exists under `dev/` or `dev/specs/` but no matching link/path/title appears in `dev/INDEX.md`.

Matching should tolerate:

- `dev/SPEC_NAME.md` linked as `SPEC_NAME.md`;
- `dev/specs/SPEC_NAME.md` linked as `specs/SPEC_NAME.md`;
- display text without the date suffix.

### Header / Index Status Drift

Warn when:

- a spec header says `Status: DRAFT` but `dev/INDEX.md` says `SHIPPED`, `BUILT`, or `BUILT + HARDENED`;
- a spec header says `SHIPPED`/`BUILT` but `dev/INDEX.md` says draft/approved only;
- a top-level new spec has no status header.

Do not fail automatically for old historical specs whose header says "see INDEX". Emit `info`.

### Missing Claimed Files

Parse code-ish file references from spec/prompt text:

- `src/...`
- `tests/...`
- `contracts/...`
- `scripts/...`
- `static/...`
- `dev/reports/...`

Warn when a referenced required file does not exist.

Do not warn for:

- examples inside fenced code blocks that are clearly payload examples;
- future target files in a DRAFT spec if the text says "Create", "Add", "Build", or "Recommended";
- routes or file names shown only as illustrative examples.

Keep this conservative. False positives will make the checker useless.

### Missing Claimed Tests

Warn when a spec/prompt claims a concrete test file such as:

```text
tests/test_teacher_decision_flywheel.py
```

and that file does not exist, unless the local context says it is a planned file in a DRAFT spec.

### Spec / Prompt Pairing

Info or warn when:

- a top-level `dev/SPEC_LV_FOO_YYYY-MM-DD.md` has no corresponding `dev/PROMPT_LV_FOO*_BUILD_YYYY-MM-DD.md`;
- a prompt exists with no corresponding spec;
- date suffixes disagree.

This should be `warn` for current top-level July 30 build handoffs and `info` for old historical files.

### Route Contract Evidence

When a spec/prompt mentions a concrete route like:

```text
POST /api/cohort-plans/preview
```

and the route exists in `src/web.py`, warn if the route is absent from `contracts/ROUTE_REACHABILITY.yaml`.

If the route does not exist yet and the spec is DRAFT, do not warn.

### UI Contract Evidence

When a spec/prompt mentions `src/web.py`, `static/index.html`, or `static/sw.js` changes and also claims built/shipped status, warn if:

- `contracts/UI_CONTRACT.yaml` does not contain a recent bump-log entry mentioning the spec keyword;
- `tests/test_ui_contract.py` expected version does not match the contract version.

Do not reimplement hash checks. Call or rely on `scripts/check_ui_contract.py` only in tests.

## Severity Semantics

Use:

- `info`: historical drift, optional pair mismatch, "see INDEX" status delegation.
- `warn`: current spec status/evidence drift that should be fixed before handoff.
- `fail`: malformed `dev/INDEX.md`, unreadable spec corpus, impossible duplicate status rows, or current built/shipped spec claiming missing required files/tests.

The initial CLI should exit:

- `0` if no `fail`;
- `1` if any `fail`;
- optional `--strict` exits `1` on `warn`.

## Tests

Add:

```text
tests/test_spec_status.py
```

Minimum coverage:

1. Discovers specs in both `dev/` and `dev/specs/`.
2. Parses `dev/INDEX.md` rows into path/status/evidence fields.
3. Missing index row emits `warn`.
4. Header/index status contradiction emits `warn`.
5. Built/shipped spec claiming missing concrete `src/...` file emits `fail`.
6. Draft spec that says "Create `src/foo.py`" does not fail missing file.
7. Missing concrete test file claim emits `warn` or `fail` based on status.
8. Top-level spec without prompt pair emits `warn`.
9. Prompt without spec emits `warn`.
10. Existing route missing from `ROUTE_REACHABILITY.yaml` emits `warn`.
11. Report JSON/Markdown output includes summary and finding codes.
12. CLI returns `0` for warn-only by default and `1` with `--strict`.
13. Checker does not write to `dev/INDEX.md`, spec files, contracts, or tests.

Focused verification:

```bash
pytest -q \
  tests/test_spec_status.py \
  tests/test_route_reachability.py \
  tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
pytest -q
```

## Acceptance Criteria

- The checker runs deterministically and read-only.
- It discovers current top-level and historical specs.
- It reports missing index entries, status drift, missing claimed evidence, pair mismatches, and route-contract gaps.
- It keeps false positives low by treating DRAFT "create/build/add" references as planned work.
- It has JSON and Markdown report output.
- Focused tests, preflight, and full suite pass.
- Working tree remains uncommitted unless the operator explicitly asks for a commit.
