# Build Prompt - Lingua Viva Final Governance, Readiness, and Product-Polish Sweep

You are taking over after the July 30 Lingua Viva build run. The foundation-risk phase is mostly closed. Your job is **not** to build every item in the final sweep. Your job is to read the sweep, verify the current repo state, select exactly one focused next slice, and implement only that slice end to end.

Read first:

```text
dev/SPEC_LV_FINAL_GOVERNANCE_READINESS_PRODUCT_POLISH_SWEEP_2026-07-30.md
dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md
dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30_3.md
dev/INDEX.md
contracts/ROUTE_REACHABILITY.yaml
contracts/UI_CONTRACT.yaml
tests/test_route_reachability.py
tests/test_ui_contract.py
```

Then inspect the current tree:

```bash
git status --short --branch --untracked-files=all
git log -5 --oneline --decorate
```

## Objective

Perform one disciplined final-polish build from the sweep. Pick **one** of these, based on the current repo state and immediate value:

1. **Spec Status Drift Checker review/finish/commit-readiness**
2. **Publication Readiness Repass**
3. **Citation-Gated Policy Retrieval**
4. **Ops Records Review Dashboard**
5. **Daily File Section Ownership Contracts**
6. **Gap-Driven Recommendation Queue**
7. **Teacher Curriculum Proposal Queue**
8. **Drive Metadata-Only Freshness Scanner**
9. **Repeatable Live P0 Experience Sweep**
10. **Stable Producer and Session Tags for Gap Signals**
11. **Learned-Weight Utility Auditor**
12. **Teacher Confirmation Uniformity Auditor**
13. **Admin Copy and Deferred-State Honesty Pass**
14. **Lazy Config Resolution Sweep**

Do **not** build true provider-token streaming from this prompt unless explicitly re-directed. It has higher runtime risk and needs a dedicated spec.

## Hard Rules

1. **Do not commit unless the operator explicitly asks.**
2. **Do not build more than one slice.**
3. **Do not auto-send to parents, Drive, Slack, or public surfaces.**
4. **Do not mutate student lenses, RTI tiers, curriculum, ontology, or runtime records unless the selected slice explicitly requires a local audited proposal/write path.**
5. **Preserve local-first and exit-gate behavior.**
6. **If `src/web.py`, `static/index.html`, or `static/sw.js` changes, run the UI contract bump ceremony.**
7. **If routes are added or removed, update route reachability honestly.**
8. **Keep generated artifacts deterministic. No external LLM/network calls in tests.**
9. **Ignore unrelated dirty files unless they block the selected slice.**

## Step 0: Decide The Slice

Before editing, write a short selection note in your final report explaining:

- which slice you chose;
- why it is the highest-value safe next step;
- which files you expect to touch;
- what you are explicitly not doing.

Prefer:

- **Spec Status Drift Checker** if `src/lingua_viva/spec_status.py` or `tests/test_spec_status.py` exists but needs review/hardening.
- **Publication Readiness Repass** if an external demo, public launch, or Still I Rise package is next.
- **Citation-Gated Policy Retrieval** if SlackBot policy/procedure assistant is next.
- **Ops Records Review Dashboard** if school leadership needs visibility over Slack workflows.

## Slice Instructions

### Option A - Spec Status Drift Checker

Use when AGV status-drift work is already in-flight.

Expected artifacts:

```text
src/lingua_viva/spec_status.py
tests/test_spec_status.py
```

Required behavior:

- read-only checker;
- scans `dev/INDEX.md`, `dev/*SPEC*.md`, `dev/specs/*SPEC*.md`, top-level prompt pairs;
- reports missing index entries, status drift, missing evidence files/tests, spec/prompt pair gaps, and route-contract gaps;
- JSON and Markdown output;
- optional module CLI;
- no preflight integration in this slice.

Focused verification:

```bash
pytest -q tests/test_spec_status.py tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

### Option B - Publication Readiness Repass

Use before public/external launch.

Expected artifact:

```text
dev/reports/REPORT_LV_PUBLICATION_READINESS_REPASS_2026-07-30.md
```

Read:

```text
publication-policy.md
dev/specs/LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md
dev/SPEC_LV_FINAL_GOVERNANCE_READINESS_PRODUCT_POLISH_SWEEP_2026-07-30.md
README.md
docs/
static/
```

Audit:

- public copy overclaims;
- parent/student examples and anonymization;
- AI attribution accuracy;
- consent assumptions;
- local-only claims vs connectors;
- evidence for product claims;
- public vs internal/admin boundaries.

Make small copy fixes only if they are clearly wrong and low-risk. Otherwise report findings.

Verification:

```bash
python3 -m src.lingua_viva.cli preflight
pytest -q tests/test_ui_contract.py tests/test_route_reachability.py
```

### Option C - Citation-Gated Policy Retrieval

Expected artifacts:

```text
src/education/policy_retrieval.py
tests/test_policy_retrieval.py
```

Build:

- local retrieval over approved policy docs only;
- every answer must include source document, section, version/effective date;
- no answer if no exact citation;
- escalation/refusal for safeguarding, HR, medical, or legal advice without exact policy source;
- deterministic templates, no network/LLM.

Optional backend route only if needed:

```text
POST /api/policy/search
```

If adding route, update route reachability as backend-only unless UI is built.

### Option D - Ops Records Review Dashboard

Expected artifacts may include:

```text
static/index.html
src/web.py
tests/test_sir_ops_request_center.py
tests/test_sir_schedule_acks.py
tests/test_route_reachability.py
tests/test_ui_contract.py
```

Build a read-only admin/coordinator surface for existing ops records:

- filter by campus/date/type/status;
- show owner, requester, reopened/needs-review flags;
- no new Slack behavior;
- no destructive actions;
- keep sensitive HR/safeguarding details out of broad UI.

This is UI work, so perform UI contract ceremony.

### Option E - Daily File Section Ownership Contracts

Expected artifacts:

```text
src/education/daily_file.py
tests/test_daily_file.py
```

Build:

- explicit section schema;
- section ownership tags;
- validator for ops/student/curriculum/private/reminder boundaries;
- tests for student PII/private notes in wrong sections;
- no UI unless existing daily view already has a validation surface.

### Option F - Gap-Driven Recommendation Queue

Expected artifacts:

```text
src/education/recommendations.py
tests/test_recommendations.py
```

Build:

- read-only recommendations from student lens/gap clusters;
- priority score and reasons;
- suggested actions: observe again, help artifact, cohort plan inclusion, RTI review;
- teacher approve/defer/dismiss state only if locally stored and audited;
- no auto tier change, no parent communication, no hidden lens mutation.

### Option G - Teacher Curriculum Proposal Queue

Expected artifacts:

```text
src/education/curriculum_proposals.py
tests/test_curriculum_proposals.py
```

Build:

- proposal records for curriculum edits;
- statuses: draft/submitted/approved/rejected/needs_changes;
- owner approval gate;
- no automatic curriculum mutation;
- list/review helpers or route if needed.

### Option H - Drive Metadata-Only Freshness Scanner

Build metadata awareness only. No content download.

Expected artifacts depend on existing Drive modules:

```text
src/lingua_viva/google_drive_integration.py
src/lingua_viva/sources.py
tests/test_google_drive_app_integration.py
```

Build:

- file id/name/modified time/size/mime type;
- compare against last seen metadata;
- "new/changed source available" summary;
- explicit import remains required.

### Option I - Repeatable Live P0 Experience Sweep

Expected artifacts:

```text
src/lingua_viva/p0_sweep.py
tests/test_p0_sweep.py
```

Build:

- deterministic local runner over core teacher journeys;
- no credentials by default;
- output JSON/Markdown report;
- do not require Playwright unless already present and stable.

### Option J - Stable Producer and Session Tags for Gap Signals

Expected artifacts:

```text
src/lingua_viva/gap_audit.py
src/lingua_viva/improvement_audit.py
tests/test_gap_audit.py
tests/test_improvement_audit.py
```

Build:

- backward-compatible `origin`, `producer`, `session_id` fields;
- readers tolerate legacy records;
- audit separates real user vs harness/golden/eval signals.

### Option K - Learned-Weight Utility Auditor

Build a read-only auditor. Do not delete or mutate weights.

Expected artifacts:

```text
src/lingua_viva/gap_audit.py
tests/test_gap_audit.py
```

### Option L - Teacher Confirmation Uniformity Auditor

Expected artifacts:

```text
src/lingua_viva/action_audit.py
tests/test_action_audit.py
```

Audit action surfaces for:

```text
system proposes -> teacher reviews -> teacher approves -> durable record
```

Report routes/actions that violate the pattern.

### Option M - Admin Copy and Deferred-State Honesty Pass

Review UI/admin copy and backend-only route reasons.

Expected artifacts vary. Make only small, evidence-backed copy/contract changes.

### Option N - Lazy Config Resolution Sweep

Expected artifacts:

```text
src/lingua_viva/config.py
tests/test_config.py
```

Build:

- scan remaining import-time `os.environ` reads;
- convert high-impact stale env constants to lazy getters;
- add tests for env mutation isolation.

## Verification Requirements

Always run:

```bash
python3 -m src.lingua_viva.cli preflight
```

Run the selected slice's focused tests.

If shared modules, route contracts, UI contracts, or privacy/audit surfaces are touched, run a broader focused set around those modules.

Run full suite when:

- `src/web.py` changes;
- shared stores/audit/deliverables/gates change;
- UI contract changes;
- route reachability changes;
- the selected slice touches multiple systems.

Full suite:

```bash
pytest -q
```

## Final Report

Report:

- selected slice and rationale;
- files changed;
- behavior added;
- behavior explicitly not added;
- whether UI contract or route reachability changed;
- focused test result;
- preflight result;
- full suite result, or why it was not run;
- any remaining backlog items from the sweep that should come next.

Do not claim the full final sweep is complete unless every listed item was explicitly reviewed and either built, descoped, or reported. The expected outcome is one clean focused build.

