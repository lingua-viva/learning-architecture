# BUILD PROMPT: Model-Failure Honesty Closure — Track 1

**Spec**: `dev/SPEC_LV_MODEL_FAILURE_HONESTY_CLOSURE_2026-08-04.md` (authoritative — read it in full first)
**Date**: 2026-08-04
**Role**: builder agent, Lingua Viva repo (`~/learning-architecture`)

## Context you don't have

Live teacher machines hit these on 0.2.31: voice dead via an unpinned transitive dep, the
privacy-differentiated no-model message unreachable when Ollama is down, and deterministic
teacher guides rendered after an honest "I can't help" message. A deep-dive audit generalized
them to 5 failure classes; every line-number claim was re-verified against source 2026-08-04
(spec §1 table). The highest-consequence item is FM-4: `_is_external_model` is a closed
3-prefix list, so any provider a teacher adds outside it (`anthropic/…`, `deepseek/…`) would
receive student PII silently. You are Track 1 of three parallel tracks; Track 2 (readiness
harness) will assert your fixes via checks C9–C11, Track 3 (GIR v2) consumes your sentinel.

## Read first (in order)

1. The spec — §1 (verified ground truth), §2 (fixes in ship order), §3 (acceptance)
2. `src/pipeline.py:263-268, 326, 435-445, 875-894` and `src/lingua_viva/reasoning.py:58-111` —
   the TWO parallel copies of the gate/resolution machinery; unification is the preferred fix
3. `desktop/electron/bootstrap.ts` `deps` array (~line 300) — note the existing P0-1 comment
   pattern for documenting transitive-dep pins; follow it for `requests`
4. `src/education/pipeline_execute.py:240-255` + `src/education/cohort_planning.py:261` — the
   execute handlers and the alternate `TeacherGuideGenerator` entry point
5. `.github/workflows/desktop-release.yml` — where the lockfile generation and smoke test land

## Ground rules (non-negotiable)

- **NEVER commit or push in this repo.** Operator owns the commit window. Build, test, leave
  dirty, report. (Desktop release / tag cutting is NOT yours either.)
- **Only touch your owned surface**: `src/pipeline.py`, `src/lingua_viva/reasoning.py`, new
  `src/lingua_viva/model_gate.py` (if unifying — preferred), `desktop/electron/bootstrap.ts`,
  `.github/workflows/desktop-release.yml`, `src/education/cohort_planning.py` (only if §2.2
  requires), your test files, `dev/INDEX.md` (your row only). Track 3 owns `grounding/` and
  `voice_tone.py`; Track 2 owns the harness files and `cli.py` — do NOT edit those.
- **Adjacent-hunk hazard**: your §2.2 edit is `pipeline.py:875-894`; Track 3's coupling point
  is `pipeline.py:950`. Keep your diff strictly inside your hunks; never stage whole-file
  batches on shared files.
- **Default-deny only narrows egress.** Nothing in this build may add a provider, widen the
  allowlist, or route student data anywhere new (two-model-ladder ruling 2026-08-03).
- Synthetic data only in tests (Marco Bianchi / Nora Rossi).

## Build order (spec §2 — ship order matters)

1. **§2.1** pin `requests>=2.28` in `bootstrap.ts` deps (document like the existing P0-1
   comment). Smallest possible diff; this is the immediate-ship item.
2. **§2.2** wrapper-concatenation gate at `pipeline.py:875-894`: on
   `wrapper_result.model_used in ("none", "none:local_only")` or confidence ≤ 0, deliver
   `execution_result.markdown` ALONE under a prominent "generated without AI model from roster
   data — review carefully" header, `model_used="none:deterministic_only"`, reduced confidence.
   **The sentinel string `none:deterministic_only` is a cross-track contract — exact spelling.**
   Verify whether `cohort_planning.py:261` flows through this same point; if not, gate it too.
3. **§2.3** reachability in the `local_only` branch (`pipeline.py:326`): local-looking but
   unreachable model ⇒ `local_only_no_model_message()`.
4. **§2.4** invert `_is_external_model` to default-deny "provably local" (localhost Ollama AND
   present in the live local model list / explicit local allowlist). Extract to ONE shared
   module used by both `pipeline.py` and `reasoning.py` (preferred), or land identically in
   both with a cross-test proving parity. Test the audit's §4 provider table, including fake
   `anthropic/claude-3.5` in providers.json.
5. **§2.5** typed/sentinel model resolution: kill the `"ollama/qwen2.5:3b"`-on-error plausible
   fallback in BOTH chains (`pipeline.py:443` + the ReasoningEngine copy).
6. **§2.6** build-time `pip freeze` lockfile in CI, embedded in the bundle, installed with
   `--require-hashes`; keep §2.1's pin as the stopgap regardless.
7. **§2.7** wizard functional probes in `bootstrap.ts`: actual `import faster_whisper`, actual
   1-token inference, Python version check before pip. Claims become "tested and works."

If time-boxed, items 1–5 are the required core; 6–7 may be reported DEFERRED with rationale —
but never silently.

## Definition of done (spec §3, restated as checks)

1. Fresh venv: voice probe `stt.available: true`; `pip check` clean.
2. Ollama stopped + student-name query ⇒ `local_only_no_model_message()`, nothing appended.
3. Ollama stopped + each of grouping/RTI/differentiation/assessment ⇒ no-model message alone
   OR deterministic doc under the no-AI banner — never concatenated. (Each handler gets a test.)
4. Fake `anthropic/claude-3.5` + student-data query ⇒ blocked local, warning surfaced, zero
   egress.
5. Exactly one `_is_external_model` implementation reachable from both pipelines (or proven
   identical with a parity test if unification was deferred — say which, and why).
6. `python3 -m pytest tests/ -q` zero failures; `lv preflight` green; `lv eval golden` green;
   `python3 -m src.lingua_viva.spec_status` shows no NEW fail-severity findings.
7. `dev/INDEX.md` row updated (BUILT — uncommitted, operator commit window), listing any
   DEFERRED items explicitly.
8. Build report: files changed per fix number, sentinel contract confirmation, provider-table
   test results, unification decision, deferred items.
