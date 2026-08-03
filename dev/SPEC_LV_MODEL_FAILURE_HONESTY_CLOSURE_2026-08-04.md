# SPEC: Model-Failure Honesty Closure (Chip 0.2.31 regression + kiro deep dive)

**Date**: 2026-08-04
**Status**: BUILT — uncommitted (operator commit window); build-time lockfile and wizard 1-token inference probe deferred
**Lens**: protection (primary — FM-4 is a latent student-PII leak), product truth, measurement
**Source evidence**:
- `qa/2026-08-04_chip-regression-0.2.31.md` (Chip / DontWriteDown — 3 bugs, live on a real machine)
- MC-repo `qa/2026-08-04_chip-regression-0.2.31_deep-dive.md` (kiro.design — 5 failure modes; all line-number claims re-verified against LV source 2026-08-04, see §1)
**Depends on**:
- `dev/SPEC_LV_TEACHER_READINESS_HARNESS_2026-08-03.md` (amended same day: harness checks C9–C11 lock these classes after fix)
- `dev/SPEC_LV_GIR_V2_OBSERVATION_LINKAGE_2026-08-03.md` (FM-3's `none:deterministic_only` sentinel feeds GIR/tone badging)

**Priority rationale**: Claudia's 0.2.31 fixes closed the *reported* surfaces; Chip's regression
pass immediately found the same classes alive on adjacent surfaces (voice dead again via a
*different* dep, honest no-model message unreachable, deterministic guide masquerading as an
answer). The failure-class rule says stop fixing instances. This spec closes the five classes at
their chokepoints. FM-4 is the highest-consequence item: a teacher adding any provider outside a
three-entry prefix list would send student PII to that provider with zero warning — a silent
privacy leak, structurally present today.

---

## 1. Verified ground truth (all re-checked against source, 2026-08-04)

| Claim | Verified location |
|---|---|
| Closed prefix list `("openai/", "groq/", "mistral/")` + `:cloud` | `src/pipeline.py:263,266-268` |
| Dead-Ollama fallback returns plausible string `"ollama/qwen2.5:3b"` | `src/pipeline.py:443` |
| `local_only and _is_external_model(...)` never True when Ollama down | `src/pipeline.py:326` |
| Unconditional wrapper+guide concatenation | `src/pipeline.py:881-894` (single point, covers all 4 execute handlers) |
| `requests` absent from pinned deps list | `desktop/electron/bootstrap.ts` `deps` array (~line 302) |
| **Duplication the audit under-states**: full parallel copy of `_is_external_model` + resolution chain | `src/lingua_viva/reasoning.py:66,89,111` — every gate fix below must land in BOTH paths or the paths must be unified |

## 2. Fixes, in ship order (kiro's order, adopted)

### 2.1 P0 — pin `requests>=2.28` (one line, ship immediately)

`bootstrap.ts` deps array. Root cause: `faster-whisper==1.1.1` imports `requests`; it arrived
transitively via `huggingface-hub`, which dropped it for `httpx` in an unpinned upgrade.
Verify: fresh venv → `GET /api/voice/probe` → `stt.available: true`.

### 2.2 P1 — gate the wrapper concatenation (FM-3; one fix point, 4+ handlers)

`src/pipeline.py:881-894`: before concatenating, check `wrapper_result.model_used`. If in
`("none", "none:local_only")` or confidence ≤ 0:

- deliver `execution_result.markdown` ALONE under a prominent "generated without AI model from
  roster data — review carefully" header, with `model_used="none:deterministic_only"` and
  reduced confidence so the GIR/tier badge downgrades (ties into GIR v2 tone coupling);
- never render deterministic output *after* an honest "I can't help" message.

Covers `_execute_differentiation`, `_execute_grouping`, `_execute_rti` (worst case — names
students), `_execute_assessment`. Audit also flags `cohort_planning.py:261`
(`TeacherGuideGenerator` via a different entry point) — verify at build time whether it flows
through the same concatenation; if not, apply the same gate there.

### 2.3 P1 — reachability in the local_only branch (FM-2 consequence)

`src/pipeline.py:326`: the student-data message must fire when the resolved model is
local-*looking* but unreachable: `local_only and (is_external or not reachable)`. The honest
message is "this data can't leave your machine AND no local model is running" —
`local_only_no_model_message()`, not the generic one.

### 2.4 P2 — invert `_is_external_model` to default-deny (FM-4, privacy-critical)

Replace "is this on a known-external prefix list?" with "**is this provably local?**": model
passes the student-data gate only if it resolves to localhost Ollama AND appears in the live
local model list (or an explicit local allowlist). Everything else — `anthropic/*`,
`deepseek/*`, `together/*`, unknown future prefixes, `:online`-style names — is treated as
external and blocked for student data, with a visible warning. **Must land in both
`src/pipeline.py` and `src/lingua_viva/reasoning.py`, or the predicate must be extracted to one
shared module (preferred — kills the duplication class too).** Test all provider paths per the
audit's §4 table, including a fake `anthropic/claude-3.5` in providers.json.

### 2.5 Structural — typed model resolution (FM-2 root)

Replace bare-string returns with `ModelResolution(model, reachable, source="detected"|"fallback")`
(or minimally: never return a plausible model string on connection failure — return a sentinel
downstream code must handle). The `"ollama/qwen2.5:3b"`-on-error pattern exists in both
resolution chains (audit confirmed the second copy near `pipeline.py:1418`); fix both.

### 2.6 Structural — build-time lockfile (FM-1 class closure)

`pip freeze` lockfile generated in CI at build time, embedded in the Electron bundle, installed
with `pip install --require-hashes -r lockfile.txt` on teacher machines. Eliminates the entire
transitive-drift class (`pdfplumber`/`pdfminer.six`, `sqlite-vec`, `uvicorn` chain, `httpcore`
are the other live exposures). Until it ships, 2.1's pin is the stopgap.

### 2.7 P2 — wizard functional probes (FM-5)

`bootstrap.ts` (`verifyPythonDeps`, model check): probe by *doing*, not by *presence* —
actually `import faster_whisper`, actually run a 1-token inference, check Python version before
pip. Wizard claims become "I tested X and it works." (The harness's C2 probe-honesty check then
holds the wizard to that claim on every run.)

## 3. Acceptance criteria

1. Fresh-venv install: voice probe `available: true`; `pip check` clean against the lockfile.
2. Ollama stopped + student-name query → `local_only_no_model_message()`, no deterministic
   content after it (Chip's exact repro, now a test).
3. Ollama stopped + grouping/RTI/differentiation/assessment queries → either the no-model
   message alone or the deterministic doc under the no-AI banner — never both concatenated.
4. `anthropic/claude-3.5` (fake) configured in providers.json + student-data query → blocked
   local, warning surfaced, zero egress (harness negative control C10 asserts this mechanically).
5. Exactly one `_is_external_model` implementation reachable from both pipelines (or verified
   identical + cross-tested if unification is deferred).
6. Full suite + `lv eval golden` + `lv preflight` green; teacher-readiness harness (once built)
   runs C9–C11 clean.

## 4. Non-goals

- No new providers, no external tier (two-model-ladder ruling 2026-08-03 stands — default-deny
  here *narrows* egress, never widens it).
- Wizard UX redesign — only probe honesty, not new screens.

## 5. Files touched (expected)

- EDIT `desktop/electron/bootstrap.ts` (pin, lockfile install path, functional probes),
  `.github/workflows/desktop-release.yml` (lockfile generation + smoke),
  `src/pipeline.py` (§2.2/2.3/2.4/2.5), `src/lingua_viva/reasoning.py` (§2.4/2.5 or unify),
  possibly `src/education/cohort_planning.py` (§2.2)
- NEW shared gate module if unification chosen (e.g. `src/lingua_viva/model_gate.py`) + tests
  (`tests/test_model_failure_honesty.py`)
- EDIT `dev/INDEX.md`
