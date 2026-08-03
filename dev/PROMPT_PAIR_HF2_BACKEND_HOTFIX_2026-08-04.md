# HF2 — Backend Hotfixes: F4 (false no-model refusal) + F6 (bundle write path)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

No spec phase — but F4 requires debugging before fixing. Read first:
`dev/QA_DEEP_DIVE_CHIP_0.2.32_2026-08-04.md`
(sections F4, F6, FM-E) and `dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: `src/lingua_viva/reasoning.py`, `src/pipeline.py` (breaker/engine
delegation only), `doctor/support_loop/paths.py`, plus tests. Nothing else.

## Fix 1 — F6: bundle-relative write path (30 min, do first)

`doctor/support_loop/paths.py:6-8` — `LV_ROOT = Path(__file__).resolve().parents[2]`
resolves inside the signed app bundle, breaking codesign and failing under macOS
App Translocation. Fix: derive the writable root from `LV_STATE_HOME` env var /
`~/.lingua-viva/.lv_support/`, consistent with `src/lingua_viva/config.py`. Add a
test asserting the support path is under the user state home, never under the
package tree.

## Fix 2 — F4: false "no AI model" refusal with Ollama running (P1)

Chip reproduced 100%: generic/weakly-classified queries (CORE-RESEARCH, confidence
0.3) return the no-model message in ~25ms while Ollama is up and healthy.
**Reproduce and pin the mechanism before changing code** — the deep dive's FM-E
analysis says the breaker alone may not explain it. Candidate mechanisms to test:
1. `_ollama_breaker_open_until` is a CLASS variable on `ReasoningEngine` — one
   tripped instance poisons every later instance for 30s even after Ollama
   recovers (per-request engines inherit the open breaker).
2. `_call_model` returning `None` on a transient `URLError`/`ConnectionError` and
   falling through to `no_model_message()` without distinguishing "not installed"
   from "momentarily unreachable".
3. `config.detect_model()` failing transiently during model load.

Reproduce with a script: trip the breaker (Ollama briefly down or blocked), restore
Ollama, immediately run a generic query through `run_teacher_query` — confirm the
false refusal, then verify your fix kills it.

Required fixes once pinned:
- Breaker state must not outlive reality: either make it instance-level, clear it
  in `__init__`, or (better, argue your choice) probe `/api/tags` fresh before
  honoring an open breaker.
- The fallback message must be honest about WHAT failed: "Tried to reach
  ollama/<model> but the connection was refused" — never "install a model" when
  one is installed. Route new wording through `src/lingua_viva/messages.py` (the
  single source for no-model messages — do not add a second message site; the GIR
  harness recognizes this class).
- The duplicate `class ReasoningEngine` at `src/pipeline.py:252` is the
  maintainability hazard that caused split-brain fixes before. If unification is
  safe tonight, have pipeline.py delegate to `src/lingua_viva/reasoning.py`; if
  not, apply the breaker fix to BOTH copies and leave a `# DUPLICATE:` marker plus
  a note in your report.

## Done criteria

- Repro script demonstrates the false refusal on HEAD and its absence after fix.
- Add a regression test locking the class (breaker staleness → honest recovery).
- Existing tests green (`python3 -m pytest tests/ -q` on touched areas; full suite
  runs in CI); `lv eval teacher-readiness` ≥ 16/19 — C9/C10 must stay green.
- Commit ONLY owned files by explicit path, message
  `fix: F4 stale-breaker false no-model refusal, F6 bundle write path (HF2)`.
- Report: pinned root cause, chosen fix, test names.
