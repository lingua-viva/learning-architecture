# BUILD PROMPT: Teacher Readiness Harness (`lv eval teacher-readiness`) — Track 2

**Spec**: `dev/SPEC_LV_TEACHER_READINESS_HARNESS_2026-08-03.md` (authoritative — read it in full first)
**Date**: 2026-08-03 (amended 2026-08-04: checks C9–C11)
**Role**: builder agent, Lingua Viva repo (`~/learning-architecture`)

## Context you don't have

Teachers went live 2026-08-03 on desktop-v0.2.31. That release fixed defects found by a *manual*
persona QA pass (`qa/2026-08-03_teacher-readiness-claudia.md`); a regression pass then found the
same failure classes alive on adjacent surfaces (`qa/`-dated 2026-08-04 Chip report + kiro deep
dive). Your job is to make that QA mechanical: one command, real routes, honest report. You are
Track 2 of three parallel tracks; Track 1 (`SPEC_LV_MODEL_FAILURE_HONESTY_CLOSURE_2026-08-04.md`)
fixes the product, Track 3 (`SPEC_LV_GIR_V2_OBSERVATION_LINKAGE_2026-08-03.md`) fixes the metric.

## Read first (in order)

1. The spec (all sections — §2.3's check table and §2.6's dual-path baseline are the core)
2. `qa/2026-08-03_teacher-readiness-claudia.md` — the failure classes you are mechanizing
3. `src/lingua_viva/golden_workflows/runner.py` + `tests/test_golden_workflows.py` — reuse this substrate
4. `src/lingua_viva/cli.py:486-491` — where the `eval` subparser lives
5. `dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` §6 — required checklist if you add any route (you shouldn't need to)

## Ground rules (non-negotiable)

- **NEVER commit or push in this repo.** The operator owns the single commit window
  (standing rule). Build, test, leave the tree dirty, report exactly what you changed.
- **Synthetic data only**: Marco Bianchi / Nora Rossi class. No real student data, no
  institution names, ever — including in fixtures, logs, and reports.
- **Only touch your owned surface**: new files (`src/lingua_viva/teacher_readiness.py`,
  `tests/test_teacher_readiness.py`, `tests/fixtures/teacher_readiness_corpus.yaml`), the
  `cli.py` eval subparser, the sanitizer firewall logger (trace_id field only), `dev/INDEX.md`
  (your row only). Other sessions may be editing `src/pipeline.py`, `src/lingua_viva/reasoning.py`,
  `grounding/` — do NOT touch those files for any reason.
- **Honest counting**: a check that could not run is FAIL, never skip. Stubs are labeled stubs
  and count against readiness. Do not inflate.
- No new models, no external egress beyond localhost Ollama (two-model-ladder ruling 2026-08-03).
- Report, never gate: nothing downstream may block on harness exit codes in this build.

## Build order (spec §3)

**Phase 1**: runner + 4 persona chains through real web routes + checks C1/C2/C3/C7/C8/C11 +
`dev/reports/TEACHER_READINESS.md` (+`.json`) — overwritten every run, never appended.
**Phase 2**: frozen negative-control corpus + content-free `trace_id` in
`sanitizer/data/firewall_log.ndjson` lines + scoped zero-egress assertion + test-scoped socket
guard (guard lives in the harness, not the product).
**Phase 3**: invention probe (thinned observations, seeded "cite observation IDs definitively",
every cited identifier must exist in the ledger) + C5/C6/C9/C10.

Deliberate-defect verification is part of the build: in a throwaway branch/worktree, reintroduce
each 0.2.30 defect class (bracket placeholder, lying probe, double-save) and prove its check
flips to FAIL. Record the proof in your report.

## Expected-FAIL baselines (do not "fix" these — they are evidence)

- §2.6 dual-path verify: baseline **FAIL** until Track 1 unifies `_is_external_model`
  (`src/pipeline.py:263-268` vs `src/lingua_viva/reasoning.py:66` — both exist today, confirmed).
- C9/C10/C11: expected FAIL until Track 1's fixes land. A FAIL here proves your check detects
  the live defect. Green-washing these is the one way to fail this task completely.

## Coordination contract with Track 1

The sentinel string `none:deterministic_only` (Track 1 emits it from the wrapper gate;
your C9 asserts on it). Do not invent a different sentinel.

## Definition of done

1. `lv eval teacher-readiness` runs all 4 chains against the real app, <10 min, only-localhost
   egress, and writes both report files.
2. All spec §4 acceptance criteria checked and individually reported PASS/FAIL/NOT-BUILT.
3. `python3 -m pytest tests/ -q` zero failures; `lv preflight` green; `lv eval golden` green;
   `python3 -m src.lingua_viva.spec_status` shows no NEW fail-severity findings from your files.
4. `dev/INDEX.md` row updated to BUILT — uncommitted (operator commit window), same edit as your
   status claim.
5. A build report in your final message: files changed, checks implemented vs deferred,
   deliberate-defect proof results, current harness readiness % with the expected-FAIL items
   listed as such.
