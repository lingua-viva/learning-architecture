# PROMPT — LV One Envelope Build (2026-08-10)

You are a build window for `~/learning-architecture` (Lingua Viva).
You are implementing `dev/SPEC_LV_ONE_ENVELOPE_2026-08-10.md`. Read it in
full, then `dev/HANDOFF_LV_NEXT_WINDOW_2026-08-10.md` for state and doctrine.

**Precondition**: the Fail-Closed Wave
(`dev/SESSION_REPORT_LV_FAIL_CLOSED_WAVE_2026-08-10.md`) must exist and be
green/pushed. If it is not, STOP — you are the wrong wave.

## Setup

```bash
cd ~/learning-architecture
unset ANTHROPIC_API_KEY; export MC_AGENT=1
git pull --rebase origin main
python3 -m src.lingua_viva.cli preflight --json                # 6/6
python3 -m src.lingua_viva.cli eval teacher-readiness --json   # all green
pytest -q tests/                                               # record baseline counts
```

## Why this wave exists

Lingua Viva has TWO reasoning engines: the native one
(`src/lingua_viva/reasoning.py:42`) and a hand-synchronized duplicate
(`src/pipeline.py:263`, self-described DUPLICATE at :277). Every honesty
invariant built this week (blocked-provider refusal, no-model honesty) had to
be implemented twice, and a harness check (DR, `teacher_readiness.py:449`)
exists purely to police the duplication. Meanwhile the honest-degradation
sentinels (`none`, `none:blocked_provider`, `none:deterministic_only`,
`none:local_only`) are scattered string literals with no registry. This is a
consolidation refactor: **one envelope, one engine, one last-hop parent
filter.** No behavior change on the wire.

## Build items — strictly in order E1 → E2 → E3 (E2 depends on E1's shared ReasonResult)

### E1 — One envelope
- Canonical module (extend `reasoning.py` or new `src/lingua_viva/envelope.py`):
  `MODEL_SENTINELS` tuple, single `ReasonResult` (superset of both current
  variants), `degraded_result(...)` helper asserting sentinel membership,
  centralized provably-local check (existing `resolve_provider_model` +
  `LV_REASON_MODEL` logic) for when to assert `external_calls: 0`.
- Convert every degraded emitter: reasoning.py chokepoints, `web.py`
  `_query_timeout_error()`, `lesson_materials.py` deterministic fallback,
  `coursework_pack.py:305` enrichment degradation.
- `tests/test_response_envelope.py`: sentinel registry lock + source grep
  (no `"none:` literal outside the canonical module) + degraded payloads
  carry `model_used` (+ `external_calls == 0` when local-only).
- Wire shapes DO NOT change. If a shape must change, stop and flag for
  operator ruling — do not improvise.

### E2 — Retire the legacy engine
- `pipeline.py` imports the native `ReasoningEngine` as its `Pipeline`
  default (:619-629); delete the legacy class body (:263-~360) and its
  `_is_external_model` alias; migrate any load-bearing docstring content
  (resolution order, Gap 5a note at :667) to the native engine.
- Update legacy-copy tests in `tests/test_model_failure_honesty.py` to
  assert the same invariants (zero egress, honest sentinel) through the
  now-native pipeline path. Invariants survive; duplicate plumbing dies.
- DR check: remove `expected_fail` (+ ref/until) at `teacher_readiness.py:449`
  — with one predicate in the tree it passes for real and now guards against
  reintroduction.
- Sweep stale `DUPLICATE` / "kept synchronized" comments.

### E3 — Parent emitters through the sharing matrix
- Enumerate all parent-audience emitters (`parent_report` generator via
  `web.py:6158` / `src/education/parent_report.py`, PDF path
  `pdf_generator.py:316`, deliverables `parent_report` kind). Put
  `filter_payload(payload, "parent")` at the LAST hop of each (G5 precedent
  at `web.py:6232-6243`): additive defense-in-depth, shapes unchanged.
- New matrix rules default to DROP for parents.
- Planted-field regression test per converted emitter (including the payload
  handed to the PDF renderer).

## Rules

- One chokepoint per invariant; a test locks every class you fix.
- Shared repo: hunk-level staging; stash-specific-paths → rebase → push →
  pop immediately if rejected.
- This is a refactor wave: **zero wire-shape changes, zero new features.**
  UI contract and golden parses must pass untouched. Findings outside scope
  go in the report as gaps.
- Deterministic paths stay deterministic; no new LLM calls.

## Exit gate (E4)

1. `preflight` 6/6; harness all green — C11 is the ONLY remaining
   expected_fail (with ref+until); DR is a real pass.
2. `pytest -q tests/` — counts >= baseline, no regressions.
3. Live walkthrough on `:8765` (`LV_AUTH_MODE=local_header`, synthetic
   state): (a) ask with no model → deterministic banner envelope with honest
   sentinel; (b) unsupported provider config → refusal envelope, zero
   egress; (c) parent report + PDF with planted non-parent-safe field →
   field provably absent. Liveness = output growth, not pgrep.
4. `grep -rn '"none:' src/` → only the canonical module.
   `grep -rn "class ReasoningEngine" src/` → exactly one.
5. `dev/SESSION_REPORT_LV_ONE_ENVELOPE_2026-08-10.md` with emitter inventory
   table (file:line per converted path).
6. Push, then Rule 0: auto-release fires on `src/**` — done = all 3 assets
   answer 200 and `chore(release): pin desktop-vX.Y.Z` is on origin.
