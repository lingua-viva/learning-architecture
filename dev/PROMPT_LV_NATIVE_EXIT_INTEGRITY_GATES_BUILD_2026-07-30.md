# Build Prompt - Lingua Viva Native Exit And Integrity Gates

You are implementing the next highest-priority Lingua Viva safety slice.

The unified matrix at `dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md` ranks this first:

```text
SPEC_LV_NATIVE_EXIT_INTEGRITY_GATES_2026-07-30.md
```

This is a heavy implementation window. The goal is to consolidate Lingua Viva's scattered external-boundary checks into one native exit/integrity gate used by the real outbound paths.

Read first:

```text
dev/LV_SYSTEM_IMPROVEMENT_MATRIX_2026-07-30.md
dev/SPEC_LV_NATIVE_EXIT_INTEGRITY_GATES_2026-07-30.md
dev/HANDOFF_LINGUA_VIVA_2026-07-30.md
src/lingua_viva/reasoning.py
src/lingua_viva/privacy.py
src/lingua_viva/governance.py
src/lingua_viva/privacy_log.py
src/lingua_viva/google_drive_integration.py
src/web.py
tests/test_lv_p0_improvement_cycle.py
tests/test_voice_tts_privacy_gate.py
tests/test_google_drive_app_integration.py
tests/test_parent_report_safety_gate.py
tests/test_server_side_auth_role_gate.py
```

## Hard Rules

1. **Do not commit.** Leave the working tree uncommitted.
2. **Do not add a new auth system.** The server-side role gate already exists.
3. **Do not add new cloud providers or live network-dependent tests.**
4. **Do not weaken current local-first behavior.**
5. **Do not let student/family data reach external LLMs, Rime, or Drive by accident.**
6. **Do not log raw student text, raw prompts, full unsafe paths, API keys, or auth headers.**
7. **Do not remove existing one-off gates until their replacement is proven by tests.** It is acceptable for the central gate to call existing primitives.
8. **Do not turn this into a broad UI/dashboard build.** This is a runtime safety boundary.

## Step 0: Baseline And Orientation

Run:

```bash
git status --short --branch --untracked-files=all
pytest -q tests/test_lv_p0_improvement_cycle.py tests/test_voice_tts_privacy_gate.py tests/test_google_drive_app_integration.py tests/test_parent_report_safety_gate.py tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

The repo may have uncommitted work from earlier July 30 builds. Do not revert unrelated files.

## Step 1: Add The Native Gate Module

Create:

```text
src/lingua_viva/exit_gates.py
```

Implement:

- `ExitRequest`
- `ExitDecision`
- `ExitGate`
- `check_exit(request)`

Keep it deterministic and stdlib-first. Use existing repo privacy primitives where possible:

- `src.lingua_viva.privacy.redact_runtime_text`
- `src.lingua_viva.privacy.assert_safe_for_external_output`
- `src.lingua_viva.governance.check_publication_safety`
- roster/student names supplied by callers

Recommended blocked reasons:

```text
student_data_external_blocked
publication_safety_blocked
unsafe_path_blocked
unsupported_destination
empty_payload_blocked
```

Destinations considered external:

```text
openai
groq
mistral
ollama:cloud
rime
google_drive
```

Local destinations must remain allowed.

## Step 2: Wire Reasoning Provider Calls

Integrate the gate into `src/lingua_viva/reasoning.py`.

Before any external model request is constructed or sent:

- Build an `ExitRequest(surface="reasoning", destination=..., payload_text=query + system prompt metadata or separate checked fields)`.
- If `local_only=True`, block external destinations before `_call_model()`.
- If payload contains student/family data, block external destinations before `_call_model()`.
- Preserve the existing local-only refusal message when no local fallback exists.
- Keep `external_call_made` for actual allowed external calls.
- Add a blocked event such as `exit_gate_blocked` when the gate blocks.

Do not let the test suite pass by checking only helper functions; include a regression where `request.urlopen` would fail the test if called.

## Step 3: Wire Rime TTS

Integrate the gate into `/api/voice/tts` in `src/web.py`.

Requirements:

- Run the gate on the exact text that would be sent to Rime, including `tone_prefix`.
- Preserve current behavior when blocked: return the local fallback shape and do not read/use the Rime key or call the network.
- Preserve current behavior when safe text is allowed and Rime is configured.
- Continue logging `voice_kept_local_student_data` and `voice_sent_to_external_tts` if existing tests expect them.
- Add exit-gate structural logging without raw text.

## Step 4: Wire Drive Upload / Share-Back

Integrate the gate into `/api/google-drive/upload` and/or `src/lingua_viva/google_drive_integration.py`.

Requirements:

- Gate explicit `file_paths` before upload helpers run.
- Gate generated student-lens export paths before upload helpers run.
- Reject unsafe paths before Drive calls.
- Preserve existing allowed path behavior.
- Preserve successful `DeliverableRecord` and `AuditReceipt` output.
- Preserve pruning behavior for successful student exports.

If existing Drive integration already has path checks, do not replace them blindly. Use the central gate as the preflight and keep lower-level checks as defense in depth.

## Step 5: Wire Governance Observation Export

Ensure `/api/governance/observation-export` goes through the central gate or a central helper before returning an export intended for external use.

Requirements:

- Existing publication-safety refusal still works.
- Allowed exports include enough structural metadata to show the exit gate passed, without changing the sensitive pack format unnecessarily.
- Tests should prove unsafe content is refused.

## Step 6: Tests

Add:

```text
tests/test_native_exit_integrity_gates.py
```

Cover at least:

- local destination allows student text
- external reasoning blocks known student names
- external reasoning blocks `local_only=True`
- external reasoning allows safe curriculum text
- `ReasoningEngine` does not call `urlopen` when gate blocks
- `ReasoningEngine` preserves local-only refusal when no local fallback exists
- TTS blocks student-name text before Rime/network
- TTS safe text can reach mocked Rime and logs allowed external TTS
- Drive upload rejects unsafe file paths before upload/network
- Drive upload success still returns deliverable + audit receipt
- governance observation export refuses unsafe publication pack
- privacy log has structural `exit_gate_blocked` event and does not contain raw student text

Also update existing tests if they encode older one-off behavior that is still conceptually correct but now has extra metadata.

## Step 7: Contracts

If `src/web.py` changes, run:

```bash
python3 scripts/check_ui_contract.py --bump
```

Then add a one-line bump log to `contracts/UI_CONTRACT.yaml` and sync `EXPECTED_VERSION` in `tests/test_ui_contract.py`.

If new or changed routes appear, update:

```text
contracts/ROUTE_REACHABILITY.yaml
```

No route changes are expected for this slice.

## Step 8: Verification

Run focused:

```bash
pytest -q \
  tests/test_native_exit_integrity_gates.py \
  tests/test_lv_p0_improvement_cycle.py \
  tests/test_voice_tts_privacy_gate.py \
  tests/test_google_drive_app_integration.py \
  tests/test_parent_report_safety_gate.py \
  tests/test_server_side_auth_role_gate.py \
  tests/test_route_reachability.py \
  tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

Then run:

```bash
pytest -q
```

Fix real regressions. If a failure is inherited, capture exact evidence before continuing.

## Final Report

Report:

- files changed
- where the central gate lives
- which outbound surfaces now call it
- blocked reasons implemented
- how raw text/path logging is avoided
- focused test result
- preflight result
- full suite result
- any intentionally deferred surfaces

Do not claim production FERPA/COPPA certification. Claim only that the native runtime exit gate is implemented and covered by tests.
