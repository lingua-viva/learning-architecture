# SPEC: Lingua Viva Native Exit And Integrity Gates

**Date**: 2026-07-30
**Status**: DRAFT - build handoff
**Source matrix**: `dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md`
**Systems**: PRV Privacy / RTE Runtime Execution / CON Connectors
**Primary surfaces**: external LLM provider calls, Rime TTS, Google Drive upload/share-back, governance exports
**Selection rationale**: The unified matrix ranks this as the highest-priority next slice: critical safety, medium effort, low regression risk. It is the required safety layer before any broader external routing or second-user rollout.

---

## Goal

Replace scattered egress checks with a small native exit/integrity gate that every external boundary can call before data leaves the machine.

The app is already local-first and has several route-specific protections:

- `ReasoningEngine.reason(..., local_only=True)` avoids external model calls for student/family data.
- `/api/voice/tts` runs `check_publication_safety()` before Rime.
- `/api/google-drive/upload` writes `DeliverableRecord` + `AuditReceipt`.
- `ObservationCapturePipeline` asserts observations never route externally.

Those are good, but they are not yet a single auditable runtime boundary. This build creates that boundary.

```text
outbound intent -> ExitRequest -> classify/scrub/check -> allow | scrub | block -> audit
```

The point is not to enable more cloud behavior. The point is to make every outbound behavior prove it is safe, locally and mechanically.

## Scope

Build a native module, preferably:

```text
src/lingua_viva/exit_gates.py
```

The module should provide:

- `ExitRequest`
- `ExitDecision`
- `ExitGate`
- `check_exit(request) -> ExitDecision`
- helper wrappers for common surfaces:
  - reasoning provider prompt/query
  - TTS text
  - Drive upload file paths / generated exports
  - governance/publication exports

Do not create a policy engine, external service, database, or UI-heavy dashboard in this slice.

## Required Data Model

Use dataclasses or a similarly simple structure.

Recommended `ExitRequest` fields:

```python
surface: str                  # reasoning | tts | drive_upload | governance_export
destination: str              # openai | groq | mistral | rime | google_drive | local
payload_text: str = ""        # text intended to leave, if any
file_paths: tuple[str, ...] = ()
student_ids: tuple[str, ...] = ()
student_names: tuple[str, ...] = ()
metadata: dict = field(default_factory=dict)
allow_scrubbed: bool = False
```

Recommended `ExitDecision` fields:

```python
allowed: bool
blocked_reason: str = ""
scrubbed_text: str = ""
violations: tuple[dict, ...] = ()
external: bool = True
audit_event: str = ""
```

Stable blocked reasons:

- `student_data_external_blocked`
- `publication_safety_blocked`
- `unsafe_path_blocked`
- `unsupported_destination`
- `empty_payload_blocked`

## Policy

### Rule 1: External LLM Provider Calls

Before any `openai/`, `groq/`, `mistral/`, or Ollama `:cloud` model call:

- Run the gate on the raw user query and system prompt.
- If query/prompt contains student/family data, block the external call.
- If `local_only=True`, always block external calls regardless of scrub result.
- Preserve the existing fail-closed behavior: if no local model is available for student data, return a local refusal instead of falling back to cloud.
- Log an audit event for blocked external reasoning without storing raw text.

This should integrate with `src/lingua_viva/reasoning.py`, preferably in `_call_model()` or immediately before `_call_model()`.

### Rule 2: Rime TTS

Before calling Rime:

- Run the gate on the exact text that would be sent, after `tone_prefix` has been prepended.
- Reuse `check_publication_safety()` and current active student names.
- If blocked, return the existing local-fallback JSON shape so the browser can speak locally.
- Log the blocked event as an exit-gate decision.

This should preserve all current `/api/voice/tts` behavior, including the privacy fallback path.

### Rule 3: Google Drive Upload / Share-Back

Before upload:

- Gate every file path.
- Only allow files under the Lingua Viva home/export/deliverables boundary already accepted by the Drive integration.
- If the route materializes a student lens export, require a generated `DeliverableRecord` and `AuditReceipt` on successful upload, as current behavior does.
- Reject obviously unsafe paths before calling Drive.
- Do not auto-import or auto-upload anything.

This should integrate with `/api/google-drive/upload` and/or `src/lingua_viva/google_drive_integration.py` without weakening existing path checks.

### Rule 4: Governance Observation Export

Before returning/exporting an observation pack intended to leave the local teacher context:

- Run `check_publication_safety()` over the pack.
- Keep current refusal behavior when blocked.
- Add exit-gate audit metadata to the response for allowed exports.

### Rule 5: Audit And Privacy Log

Every decision should be auditable without writing raw student text:

- Allowed external call: existing `external_call_made` remains.
- Blocked external call: add a stable event such as `exit_gate_blocked`.
- Scrubbed/allowed call, if implemented: add `exit_gate_scrubbed`.
- Include only structural detail: surface, destination, reason, hashes/counts, never raw payload text or full file paths where path may contain a student name.

If existing `privacy_log.log_event()` genericizes detail, keep using it safely. Do not rewrite privacy logging broadly.

## Implementation Requirements

1. Centralize the decision logic in `src/lingua_viva/exit_gates.py`.
2. Keep existing route response shapes stable unless currently unsafe.
3. Do not introduce network calls in tests.
4. Do not use broad regex-only PII detection if existing repo primitives can be reused:
   - `src.lingua_viva.privacy.redact_runtime_text`
   - `src.lingua_viva.privacy.assert_safe_for_external_output`
   - `src.lingua_viva.governance.check_publication_safety`
   - active roster/student names where available
5. Prefer fail-closed behavior at external boundaries.
6. Do not block local-only flows just because they contain student data.

## Out Of Scope

- No new auth system; the role gate already exists.
- No consent workflow.
- No Google Picker / narrower Drive scope migration.
- No UI dashboard beyond existing Privacy/Governance surfaces.
- No true provider-token streaming.
- No new cloud providers.
- No production network validation.
- No deletion or migration of existing privacy logs.

## Tests

Add focused tests, preferably:

```text
tests/test_native_exit_integrity_gates.py
```

Minimum coverage:

1. `ExitGate` allows local destinations with student text.
2. `ExitGate` blocks external reasoning when payload contains a known student name.
3. `ExitGate` blocks external reasoning when `local_only=True`.
4. `ExitGate` allows non-student curriculum text to external reasoning.
5. `ReasoningEngine` does not call `urlopen` for blocked student-data external prompts.
6. `ReasoningEngine` logs/returns the existing local-only refusal when no local fallback exists.
7. `/api/voice/tts` still blocks student-name text before Rime key lookup/network call.
8. `/api/voice/tts` still allows safe text and logs external TTS when Rime is configured and mocked.
9. Drive upload rejects unsafe paths before calling upload/network helpers.
10. Drive upload success still returns `deliverable` and `audit_receipt`.
11. Governance observation export still refuses unsafe publication packs.
12. Privacy summary or privacy log records blocked exit-gate decisions without raw text.

Also keep existing suites green:

```bash
pytest -q \
  tests/test_native_exit_integrity_gates.py \
  tests/test_lv_p0_improvement_cycle.py \
  tests/test_voice_tts_privacy_gate.py \
  tests/test_google_drive_app_integration.py \
  tests/test_parent_report_safety_gate.py \
  tests/test_route_reachability.py \
  tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
pytest -q
```

## Acceptance Criteria

- A single native exit-gate module exists and is used by at least reasoning, TTS, and Drive/share-back paths.
- Student/family data cannot reach external LLM providers.
- Student names cannot reach Rime TTS.
- Unsafe Drive paths are rejected before any external upload attempt.
- Allowed Drive share-back still creates durable deliverable and audit receipt records.
- Exit-gate block decisions are logged structurally, without raw text.
- Existing local-first behavior remains unchanged.
- Full suite and preflight pass.
- Working tree remains uncommitted.
