# Lingua Viva Architecture Sweep — Report

**Date**: 2026-07-18  
**Baseline**: 392 tests, Doctor WARN/healthy, v1.0.0 shipped  
**Final state**: 400 tests, Doctor WARN, artifact gauntlet PASS, Gate 3 script 15/15

## Summary

| Section | Findings | Fixed | Deferred | Status |
|---|---:|---:|---:|---|
| 1. Gate Infrastructure | 3 | 3 | 0 | FIX |
| 2. Stub Audit | 5 | 2 | 3 | FIX/WARN |
| 3. Privacy Parity | 3 | 1 | 1 | FIX |
| 4. Provider Config | 1 | 1 | 0 | FIX |
| 5. Test Coverage | 5 | 2 | 1 | PASS |
| 6. Data Integrity | 5 | 3 | 1 | FIX/WARN |
| 7. Error Handling | 3 | 2 | 0 | FIX |
| 8. Build & Package | 5 | 1 | 3 | WARN |
| 9. Documentation | 4 | 3 | 1 | FIX/WARN |
| 10. Resilience | 4 | 0 | 2 | WARN |
| **Total** | **38** | **18** | **12** | **PASS WITH WARNINGS** |

## Detailed Findings

### 5. Test Coverage

- **PASS** `test_suite`: Baseline run passed at 392 tests; final run passed at 400 tests.
- **PASS** `e2e_test`: `tests/test_e2e_still_i_rise.py` is a real product integration slice across observation capture, student lenses, content differentiation, and teacher guide generation. It does not call Ollama, which is correct for CI.
- **PASS** `desktop_test`: `tests/test_desktop_phase1.py` checks package targets, Electron security flags, backend launch wiring, progress copy, and preload bridge.
- **WARN** `untested_endpoints`: direct tests are still missing for `/api/curriculum/unit/{unit_id}`, `/api/admin/evidence`, `/api/admin/capacity`, `/api/stats`, and `/api/session`.
- **FIX** `manifest_stale`: `MANIFEST.yaml` replaced with current LV counts: 212 ontology nodes, 25 domains, 178 knowledge entries, 559 citations, 400 final tests.

### 6. Data Integrity

- **FIX** `revision_log`: one malformed teacher reflection row in `dev/lv_revision_log.ndjson` was normalized to the full accountability schema. `/api/reflect/note` now writes schema-complete entries.
- **WARN** `learned_weights`: learned weights are non-empty and include legacy MC/LV entries. Test/gate-generated mutations from this sweep were removed. Existing weights were left in place because provenance cannot be proven from this sweep alone.
- **PASS** `archive_imports`: no active `src/` imports from `archive/mc-engine/`.
- **FIX** `runtime_gitignored`: ignored private runtime DB `case-studies/04-still-i-rise/data/still_i_rise.db` caused Doctor PRIVATE_RISK and was removed. Doctor returned to WARN.
- **WARN** `memory/data`: runtime NDJSON files are tracked/dirty in normal test activity patterns; `.gitignore` covers generated copies, but tracked historical files remain.

### 4. Provider Config

- **FIX** `provider_config`: canonical read/path logic is now `src/lingua_viva/config.py`. `src/provider_config.py` is a compatibility wrapper. Legacy `src/pipeline.py` helper names now delegate to the canonical module.
- **PASS** `provider_tests`: provider/config/model tests passed: 45/45.

### 7. Error Handling

- **FIX** `/api/prepare/activity`: invalid `duration_minutes` returned 500; now returns 400 with a clear message.
- **FIX** `/api/query`: missing `query` returned 200 with an error body; now returns 400.
- **PASS** `observe_fix_holds`: unknown observation student returns 404, not 500.
- **PASS** `probe`: 10 invalid POST probes returned 400/404, no 500s.

### 2. Stub Audit

- **FIX** `entry_gate`: `EntryGate.scan()` now uses `src.lingua_viva.privacy` to detect/redact private runtime data, force PROTECT intent, and block external routing.
- **DEFER** `exit_gate`: documented as a local-only stub. External research is disabled, so inbound external response scanning is not currently load-bearing.
- **DEFER** `integrity_gate`: documented as deferred to the native LV pipeline replacement.
- **PASS** `external_gate`: `GatewayInterface.needs_external()` intentionally returns false; LV teacher workflows remain local-only.
- **DEFER** `admin_stubs`: `/api/admin/evidence`, `/api/admin/capacity`, and `/api/admin/trends` now include Phase 7 comments explaining missing data prerequisites.

### 3. Privacy Parity

- **FIX** `pattern_parity`: runtime privacy now actually applies its declared PII regex set, not only Doctor redaction plus student-context patterns. Added international phone parity with sanitizer.
- **WARN** `service_worker`: `static/sw.js` remains defense-in-depth and intentionally lags the server-side pattern set.
- **PASS** `trace_privacy`: `~/.lingua-viva/traces.ndjson` stores hashes, not raw queries. Local check found no `CEFR targets` / `La Famiglia` raw text.
- **PASS** `privacy_log_perms`: `~/.lingua-viva/privacy_events.ndjson` mode is `0600`.

### 10. Resilience

- **PASS** `reasoning_timeout`: native `src/lingua_viva/reasoning.py` uses `LV_REASON_TIMEOUT_SECONDS` with bounded `urlopen`; web `/api/query` wraps calls in `asyncio.wait_for`.
- **PASS** `brief_independence`: `/api/brief` is pure local aggregation: schedule, student lens store, revision log, Doctor summary, file map summary. No model calls.
- **PASS** `ws_timeout`: WebSocket query messages route through `/api/query`, which applies the same timeout.
- **DEFER** `circuit_breaker`: no explicit Ollama circuit breaker exists. Current behavior is bounded timeout plus graceful fallback; a short-lived breaker would improve repeated-down-Ollama UX.

### 8. Build & Package

- **WARN** `pyinstaller_spec`: `mc.spec` is syntactically plausible but stale in naming (`sir`, Still I Rise, MC comments) and points at `src/mc_cli.py`. Not rebuilt during this sweep.
- **WARN** `install_script`: URLs point to `lingua-viva/learning-architecture`, but installer branding, binary name, install home, and port remain Still I Rise / `sir` / `~/.still-i-rise` / `7896`. Needs a dedicated installer rename pass.
- **PASS** `desktop_build`: `npm run build --prefix desktop` passed.
- **WARN** `docker`: `docker-compose.yml` still says Mission Canvas and uses `MC_SANITIZER_*` env names. Sanitizer image itself builds from the local app.
- **FIX** `pwa_cache`: `static/sw.js` cache bumped from `lv-pwa-v1` to `lv-pwa-v6`.

### 9. Documentation

- **FIX** `manifest`: replaced stale MC manifest with current LV runtime/test/count data.
- **FIX** `readme`: replaced active MC-powered runtime framing with Lingua Viva local teacher runtime framing while preserving gauntlet-safe maturity language.
- **PASS** `claude_md`: current enough; it reflects LV runtime boundary and archive boundary.
- **FIX/WARN** `specs_status`: Phase 4, Phase 5, Phase 6, complete app build, and backend migration specs marked SHIPPED. Accountable curriculum, local support loop proposal, and Phase B support-bundle specs retain non-shipped/proposed status where appropriate.

### 1. Gate Infrastructure

- **FIX** `golden_eval`: added `python3 -m src.lingua_viva.cli eval golden tests/golden_education_v1.yaml`; result 36/36.
- **FIX** `sir_health`: added LV equivalent `python3 -m src.lingua_viva.cli health --full --json`; result Doctor WARN, pytest PASS, gauntlet PASS, golden PASS.
- **FIX** `gate3_script`: added executable `scripts/gate3_sweep.sh`; result 15/15. The script uses `eval_mode: true` to avoid learned-weight/proposal mutations.

## Validation

- `python3 -m pytest tests/ -q`: 400 passed.
- `python3 -m pytest doctor/support_loop/tests/ -q`: 15 passed.
- `python3 -m doctor.support_loop doctor`: WARN.
- `python3 doctor/lv_artifact_gauntlet.py`: PASS.
- `python3 -m src.lingua_viva.cli eval golden tests/golden_education_v1.yaml --json`: 36/36.
- `python3 -m src.lingua_viva.cli health --full --json`: PASS summary.
- `scripts/gate3_sweep.sh`: 15/15.
- `npm run build --prefix desktop`: PASS.
- `rg "Mission Canvas|Still I Rise|MC_|mc\\." static/ src/lingua_viva/ tests/`: 0 hits.
- `git status --short -- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx`: empty.

## Lessons for Mission Canvas

### Pattern Transfers

- **Make every gate executable.** LV became more trustworthy when Gate 3 moved from an ad hoc prompt loop to `scripts/gate3_sweep.sh`. MC should require named scripts for every release gate, not just documented curl snippets.
- **Use non-mutating eval mode for sweeps.** The first Gate 3 script run mutated learned weights and candidate proposals. MC’s sweep scripts must set explicit no-training/no-memory flags and verify ontology/memory status afterward.
- **Centralize config before probing behavior.** Provider drift was easier to fix before endpoint probes. MC should consolidate duplicate config readers before running health/error sweeps, or failures may point at stale readers.
- **Treat Doctor PRIVATE_RISK as a release stop.** A single ignored local DB made Doctor stop. MC should keep this behavior: path-level private-risk detection is cheap and catches real contamination.
- **Write regression tests for every sweep fix.** LV added focused tests for error handling, privacy parity, gate stubs, and CLI infrastructure. MC should not accept “manual probe passed” as the final state.
- **Expose trust data as first-class APIs.** `/api/why`, `/api/privacy`, `/api/profile`, and trace logs made final hardening much easier to automate. MC should build equivalent introspection endpoints before its final sweep.

### Anti-Patterns

- **Do not leave “safe default” stubs unnamed.** EntryGate returning `blocked=False` looked harmless until the sweep asked whether governance was real. MC stubs must either enforce something or be labeled with scope and owner.
- **Do not let tests train the product.** Golden/e2e/test paths that write learned weights make audits noisy and can hide real drift. MC needs a hard separation between evaluation and learning.
- **Do not keep fork-era install assets indefinitely.** LV’s active app is Lingua Viva, but installer/PyInstaller/Docker still carry SIR/MC names. MC should audit packaging names as a first-class architecture surface.
- **Do not duplicate provider/config/security readers.** Drift risk grows silently. MC should have one canonical module for provider config, secret loading, and model routing.
- **Do not rely on client-side privacy parity.** The service worker can help, but server/runtime parity is the real bar. MC should classify browser redaction as defense-in-depth only.

### Methodology Notes

- **Run sections in dependency order.** Baseline tests → data cleanup → config consolidation → endpoint probes was the correct order. Doing endpoint probes first would have mixed true 500s with config drift and runtime contamination.
- **Record dispositions while auditing.** PASS/FIX/DEFER/WARN forced useful decisions: entry gate fixed, exit/integrity/admin deferred, installer warned, cache fixed.
- **Probe invalid inputs with a live server.** Unit tests missed the `/api/prepare/activity` bad-duration 500. MC should include live invalid-payload probes for every POST endpoint.
- **Check dirty state before and after gates.** The LV sweep caught candidate/weight mutations only because status was reviewed after script runs. MC should automate pre/post dirty-file allowlists.
- **Keep report as the artifact.** The report turned scattered fixes into reusable evidence. MC’s final sweep spec should require the same summary table, detailed findings, and lessons section before any “ship” claim.
