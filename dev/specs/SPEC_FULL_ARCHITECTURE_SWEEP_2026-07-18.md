# SPEC: Lingua Viva — Full Architecture Sweep

**Date**: 2026-07-18
**Status**: READY TO BUILD
**Author**: claude.analysis (MC window, sweep methodology design)
**Purpose**: Systematic audit of the entire LV architecture. Fix what's broken, document what's deferred, produce a report that informs the MC final sweep.
**Output**: `dev/REPORT_ARCHITECTURE_SWEEP_2026-07-18.md` — what improved, what didn't, and lessons for MC.
**Build method**: `export MC_AGENT=1` equivalent (no weight training). Tests must stay green (392 passed). Doctor must stay healthy.

---

## 0. Why This Sweep

LV shipped v1.0.0 on Jul 14. Since then, Phases 4-6 added onboarding, file map, trust UI, and the observe endpoint fix. The codebase has grown from ~300 tests to 392 tests across 55 test files, but no one has done a full cross-cutting audit.

This sweep has two goals:
1. **Get LV to ideal state** — find and fix everything that's broken, stubbed, stale, or insecure.
2. **Generate intel for MC** — every finding, fix pattern, and lesson learned feeds into the MC final sweep spec. LV is the testing ground.

**The sweep is NOT a rebuild.** It's a 10-section audit with targeted fixes. Each section produces a finding (PASS/WARN/FIX/DEFER) and a short note. At the end, the report tallies improvements and non-improvements.

---

## 1. Sweep Sections

### Section 1: Gate Infrastructure (Missing Pieces)

**What to check:**
LV has no MC-equivalent eval harness, no total-health aggregator, no automated Gate 3 script, and no improvement circuit.

**Tasks:**
1. **Create `sir eval golden`** — Wire `tests/golden_education_v1.yaml` into a runnable eval command in the CLI (`src/lingua_viva/cli.py`). Pattern: read golden file, run each query through the pipeline (eval mode), compare classification node + domain to expected. Report pass/fail count. This is the LV equivalent of `mc eval`.

2. **Create `sir health`** — Single command that runs: (a) Doctor (`run_doctor()`), (b) pytest summary (subprocess, capture pass/fail count only), (c) gauntlet (`run_gauntlet()`), (d) golden eval (from step 1). Returns exit 0 if all pass, exit 1 with summary if any fail. This is the LV equivalent of `mc total-health`.

3. **Create `scripts/gate3_sweep.sh`** — Executable bash script that runs the Gate 3 demo sequence programmatically. For each of the 15 iterations:
   - POST `/api/query` with an education query → verify 200 + classification
   - POST `/api/query` with a student name → verify PII blocked
   - GET `/api/why` → verify trace exists with no raw query text
   - GET `/api/privacy` → verify privacy events logged
   - GET `/api/health` → verify doctor passes
   - GET `/api/brief` → verify response shape
   - GET `/api/filemap` → verify response shape
   - POST `/api/profile/clear` with wrong confirmation → verify 400
   - Exit 0 if all pass, exit 1 with details if any fail

**Report fields:**
- `golden_eval`: created / not created, pass rate
- `sir_health`: created / not created
- `gate3_script`: created / not created, 15/15 or fail count

---

### Section 2: Stub Audit (Dead Code That Lies)

**What to check:**
Three critical gates are stubbed out — they return safe defaults but do NO actual checking. This means the pipeline claims governance but delivers none at three critical points.

**Tasks:**
1. **Audit `EntryGate.scan()`** — Currently returns `blocked=False` always. Determine: should it wire into `src/lingua_viva/privacy.py`'s `redact_runtime_text()` to block PII before classification? Or is the sanitizer service sufficient? Document the decision. If wiring: implement. If deferring: add a `# STUB: privacy handled by src/lingua_viva/privacy.py` comment and log finding.

2. **Audit `ExitGate.scan_response()`** — Currently returns `True` always. Determine: does LV need outbound response scanning? MC's exit gate scans for prompt injection in responses. LV is local-first (external research disabled) so this may be correctly stubbed. Document the decision.

3. **Audit `IntegrityGate`** — Currently returns empty warnings. Determine: should it check ontology node existence for classified nodes? Knowledge entry freshness? Document.

4. **Audit `GatewayInterface.needs_external()`** — Returns `False` always. This is intentional (LV is local-first for student privacy). Verify the sanitizer service's fail-closed behavior backs this up. Document.

5. **Check the 3 unimplemented admin endpoints** — `/api/admin/evidence`, `/api/admin/capacity`, `/api/admin/trends` return `{"status": "not_yet_implemented"}`. Decide: implement, remove from router, or add `# Phase 7: admin dashboard` comment. If removing: update any frontend that references them.

**Report fields:**
- `entry_gate`: wired / deferred (with reason)
- `exit_gate`: wired / deferred (with reason)
- `integrity_gate`: wired / deferred (with reason)
- `external_gate`: correctly disabled / needs review
- `admin_stubs`: implemented / removed / documented

---

### Section 3: Privacy Parity Audit

**What to check:**
Three separate privacy layers (sanitizer service, runtime privacy, service worker) each have their own PII regex patterns. If they diverge, one layer catches what another misses.

**Tasks:**
1. **Extract all PII patterns** from:
   - `sanitizer/app.py` — 12 patterns
   - `src/lingua_viva/privacy.py` — 13 patterns (broader set)
   - `static/sw.js` — client-side patterns

2. **Build a comparison table** — pattern name, sanitizer has it, runtime has it, SW has it. Identify gaps.

3. **Fix gaps** — If runtime catches something sanitizer doesn't (or vice versa), add the missing pattern. The SW is defense-in-depth and can lag, but sanitizer and runtime should be at parity.

4. **Verify traces contain no raw queries** — Read `~/.lingua-viva/traces.ndjson` (or test fixture). Confirm every entry has `query_hash` and NO raw query text field.

5. **Verify privacy_events.ndjson permissions** — Should be 0600. Check.

**Report fields:**
- `pattern_parity`: full / gaps found (list gaps)
- `trace_privacy`: clean / raw queries found
- `privacy_log_perms`: correct / fixed

---

### Section 4: Provider Config Deduplication

**What to check:**
`_provider_config_path()` and `_read_provider_config()` exist in BOTH `src/pipeline.py` AND `src/provider_config.py`. If they drift, one reads stale config.

**Tasks:**
1. **Diff the two implementations** — Are they identical? If not, which is canonical?
2. **Consolidate** — One home for provider config reads. The other imports from it. Zero duplication.
3. **Verify no other provider config readers exist** — grep for `providers.json` across the codebase.

**Report fields:**
- `provider_config`: consolidated / already clean / drift found (details)

---

### Section 5: Test Coverage Audit

**What to check:**
392 tests across 55 files, but are the critical paths covered?

**Tasks:**
1. **Verify end-to-end test calls real pipeline** — Read `test_e2e_still_i_rise.py`. Does it mock the model or call Ollama? If mocked: that's OK for CI but note it. If real: verify it handles Ollama-not-running gracefully.

2. **Verify desktop test exists and is meaningful** — Read `test_desktop_phase1.py`. If it's a stub, note it.

3. **Check for untested endpoints** — Compare the endpoint list (38 endpoints) against test file names. Which endpoints have no test?

4. **Run the full suite and verify 392/392** — `python3 -m pytest tests/ -q`. Note any skips or warnings.

5. **Check MANIFEST.yaml test count** — It says 65 tests. Reality is 392. Update if it's a source-of-truth document.

**Report fields:**
- `e2e_test`: real pipeline / mocked / missing
- `desktop_test`: meaningful / stub / missing
- `untested_endpoints`: list
- `test_suite`: X passed, Y skipped, Z failed
- `manifest_stale`: fixed / not applicable

---

### Section 6: Data Integrity

**What to check:**
Runtime data files, learned weights, revision log, archive imports.

**Tasks:**
1. **Revision log schema** — Read `memory/data/revision_log.ndjson` (or equivalent). Verify every entry has all 14 required keys. Report malformed entries.

2. **Learned weights** — Read `ontology/learned_weights.yaml`. Is it empty/default or has it been trained? If default: fine. If trained: verify the training was from operator-origin data only.

3. **Archive imports** — grep for `from archive` or `import archive` across `src/`. Any imports from `archive/mc-engine/` are dead code paths. Remove them.

4. **Runtime data gitignored** — Verify `~/.lingua-viva/` paths are NOT committed to the repo. Check `.gitignore` for `*.ndjson`, `traces.ndjson`, `privacy_events.ndjson`, `tasks.json`.

5. **Memory/data directory** — Check what's in `memory/data/`. Anything that's runtime state (not seed data) should be gitignored.

**Report fields:**
- `revision_log`: valid / N malformed entries
- `learned_weights`: clean / stale / trained
- `archive_imports`: clean / N dead imports removed
- `runtime_gitignored`: clean / gaps

---

### Section 7: Error Handling Probe

**What to check:**
Hit every POST endpoint with missing/invalid data. Every one should return a helpful error (400/404), never a 500.

**Tasks:**
1. **Probe each POST endpoint** with: empty body, missing required fields, invalid types, non-existent IDs.

Endpoints to probe:
```bash
# Should return 400 (missing body)
curl -X POST localhost:8787/api/query -H "Content-Type: application/json" -d '{}'

# Should return 400 (missing student_id)  
curl -X POST localhost:8787/api/observe/capture -H "Content-Type: application/json" -d '{"text": "test"}'

# Should return 400 (invalid student_id)
curl -X POST localhost:8787/api/observe/capture -H "Content-Type: application/json" -d '{"student_id": "nonexistent", "text": "test"}'

# Should return 400 (missing path)
curl -X POST localhost:8787/api/filemap/scan -H "Content-Type: application/json" -d '{}'

# Should return 400 (bad path)
curl -X POST localhost:8787/api/filemap/scan -H "Content-Type: application/json" -d '{"root_path": "/nonexistent"}'

# Should return 400 (wrong confirm)
curl -X POST localhost:8787/api/profile/clear -H "Content-Type: application/json" -d '{"confirm": "wrong"}'

# Should return 400 (missing fields)
curl -X POST localhost:8787/api/provider/connect -H "Content-Type: application/json" -d '{}'

# Should return 400 (missing query)
curl -X POST localhost:8787/api/reflect/note -H "Content-Type: application/json" -d '{}'
```

2. **Fix any 500s** — Convert to 400 with helpful error message.

3. **Verify the observe endpoint fix holds** — The most recent commit fixed a 500→404 for unknown students. Verify it returns 404 (not 500, not 200).

**Report fields:**
- `endpoints_probed`: N
- `500s_found`: N (list which endpoints)
- `500s_fixed`: N
- `observe_fix_holds`: yes / no

---

### Section 8: Build & Package Verification

**What to check:**
Binary builds, install scripts, Docker, desktop packaging.

**Tasks:**
1. **PyInstaller spec** — Does `mc.spec` (or equivalent) build a working `sir` binary? Run `pyinstaller mc.spec --clean --noconfirm` if feasible. If not feasible (takes too long), verify the spec file references correct paths.

2. **install.sh** — Read it. Verify URLs point to the right GitHub release (`lingua-viva/learning-architecture`). Verify port (7896 for installed, 8787 for dev). Verify no hardcoded paths that break on other machines.

3. **Desktop build** — Run `npm run build --prefix desktop`. Does it complete? Are there TypeScript errors?

4. **Docker** — Read `docker-compose.yml` and `sanitizer/Dockerfile`. Do they reference correct ports and paths?

5. **PWA cache versioning** — `CACHE_NAME = "lv-pwa-v1"` in `sw.js`. If the app has been updated since v1.0.0, the cache name should be bumped so users get the new version. Check if any post-v1.0.0 changes affect cached assets.

**Report fields:**
- `pyinstaller_spec`: valid / errors
- `install_script`: correct URLs / broken URLs
- `desktop_build`: passes / fails
- `docker`: valid / stale
- `pwa_cache`: current / needs bump

---

### Section 9: Documentation & Stale Count Audit

**What to check:**
MANIFEST.yaml, README, CLAUDE.md, any document that claims specific counts or features.

**Tasks:**
1. **MANIFEST.yaml** — Compare stated counts (tests, nodes, knowledge entries, domains) against reality. Fix discrepancies.

2. **README** — Check for inflated or stale claims. The gauntlet already checks for "unique globally" — run the gauntlet's forbidden pattern list.

3. **CLAUDE.md** — If it exists, verify it reflects the current architecture (not stale MC references).

4. **dev/specs/** — Check each spec's status. Mark completed ones as SHIPPED. Mark deferred ones as DEFERRED with reason.

**Report fields:**
- `manifest`: current / N fixes
- `readme`: clean / N stale claims
- `claude_md`: current / stale
- `specs_status`: N shipped, N deferred, N stale

---

### Section 10: Reasoning Timeout & Resilience

**What to check:**
The LV feedback notes mention `LV_REASON_TIMEOUT_SECONDS`. Does the reasoning engine have a bounded timeout? What happens when Ollama stalls?

**Tasks:**
1. **Check `src/lingua_viva/reasoning.py`** — Is there a timeout on Ollama calls? On BYOK provider calls? If not: add one (default 120s, configurable via `LV_REASON_TIMEOUT_SECONDS`).

2. **Check the brief endpoint** — If the pipeline hangs, does `/api/brief` also hang? The brief should be pure file reads (no model calls). Verify.

3. **Check WebSocket handler** — Does the WS query handler have a timeout? If Ollama stalls, does the WS connection hang indefinitely?

4. **Circuit breaker** — If Ollama is down, does the next query immediately fail with a helpful error, or does it wait 30s to timeout? MC has a circuit breaker pattern. Check if LV has one.

**Report fields:**
- `reasoning_timeout`: exists (Xs) / added (Xs) / missing
- `brief_independence`: no model calls / model calls found
- `ws_timeout`: exists / missing
- `circuit_breaker`: exists / missing / not needed (local-only)

---

## 2. Build Order

Run sections in this order (dependencies flow downward):

1. **Section 5** (Test Coverage) — Run tests first to establish baseline. Everything else assumes tests are green.
2. **Section 6** (Data Integrity) — Clean data before testing behavior.
3. **Section 4** (Provider Config) — Consolidate before probing endpoints.
4. **Section 7** (Error Handling) — Probe endpoints (server must be running).
5. **Section 2** (Stub Audit) — Decide on gates (may change pipeline behavior).
6. **Section 3** (Privacy Parity) — Audit after any gate changes.
7. **Section 10** (Resilience) — Timeouts and circuit breakers.
8. **Section 8** (Build & Package) — Verify builds after code changes.
9. **Section 9** (Documentation) — Update docs to reflect current state.
10. **Section 1** (Gate Infrastructure) — Build eval/health/gate3 script LAST (they test everything above).

---

## 3. Report Template

After the sweep, produce `dev/REPORT_ARCHITECTURE_SWEEP_2026-07-18.md` with this structure:

```markdown
# Lingua Viva Architecture Sweep — Report

**Date**: 2026-07-18
**Baseline**: 392 tests, doctor healthy, v1.0.0 shipped
**Final state**: [test count] tests, [doctor status], [gate3 status]

## Summary

| Section | Findings | Fixed | Deferred | Status |
|---|---|---|---|---|
| 1. Gate Infrastructure | | | | |
| 2. Stub Audit | | | | |
| 3. Privacy Parity | | | | |
| 4. Provider Config | | | | |
| 5. Test Coverage | | | | |
| 6. Data Integrity | | | | |
| 7. Error Handling | | | | |
| 8. Build & Package | | | | |
| 9. Documentation | | | | |
| 10. Resilience | | | | |
| **Total** | | | | |

## Detailed Findings

[Per-section details with PASS/WARN/FIX/DEFER per task]

## Lessons for Mission Canvas

[What patterns worked, what was harder than expected, what MC should 
prioritize in its own sweep. This section is the ENTIRE POINT of running 
the LV sweep first.]

### Pattern transfers (what MC should steal)
- ...

### Anti-patterns (what MC should avoid)
- ...

### Methodology notes (what to do differently in the MC sweep)
- ...
```

---

## 4. Rules

- `export MC_AGENT=1` (or LV equivalent) — no weight training during sweep
- Tests must stay green throughout. If a fix breaks a test, fix the test or revert the fix.
- Doctor must stay healthy. If a finding conflicts with doctor, resolve before proceeding.
- Don't rebuild. This is an audit with targeted fixes, not a rewrite.
- Every finding gets a disposition: PASS (already correct), FIX (fixed in this sweep), DEFER (documented with reason), WARN (noted, no action needed).
- The report is the deliverable. If you fixed 20 things but didn't write the report, the sweep didn't happen.

---

*This spec is designed to run on LV first, produce a report, and then inform the MC final sweep. The 10 sections cover the same cross-cutting concerns that MC's Gate 3 will test. What we learn here — which checks caught real bugs, which were noise, which fixes were trivial vs hard — directly shapes the MC sweep methodology.*
