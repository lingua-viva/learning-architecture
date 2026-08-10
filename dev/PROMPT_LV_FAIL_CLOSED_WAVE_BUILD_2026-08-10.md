# PROMPT — LV Fail-Closed Wave Build (2026-08-10)

You are a build window for `~/learning-architecture` (Lingua Viva), a
local-first teacher tool. You are implementing
`dev/SPEC_LV_FAIL_CLOSED_WAVE_2026-08-10.md`. Read it in full first, then
`dev/HANDOFF_LV_NEXT_WINDOW_2026-08-10.md` for state and doctrine.

## Setup

```bash
cd ~/learning-architecture
unset ANTHROPIC_API_KEY; export MC_AGENT=1
git pull --rebase origin main   # remote alias: lingua-viva
python3 -m src.lingua_viva.cli preflight --json                # expect 6/6
python3 -m src.lingua_viva.cli eval teacher-readiness --json   # expect 19/19
```

If baselines are not green, STOP and report — do not build on a red base.

## Why this wave exists (context you must hold)

The safeguarding classifier once returned GREEN for "His dad hits him at
home". It was found by accident. The class fix is live in
`src/lingua_viva/safeguarding.py` (round-up at :225, personal-context
secondary at :237), but nothing proves it against phrases nobody has tried
yet, and nothing stops the next regression. Separately: two P0 harness
checks (C11 at `teacher_readiness.py:356`, DR at :449) are *permanent*
`expected_fail` — a live regression mask; and the built-but-not-called
defect class has regenerated after every build wave because the audit for it
is manual. This wave turns all three into standing, self-verifying machinery.

## Build items (independent — build in this order anyway: F1, F2, F3)

### F1 — Adversarial safeguarding corpus (P0)
- `tests/fixtures/safeguarding_corpus.yaml`: `must_flag` (≥25, each with
  `phrase`, `minimum_tier`, `source`, `added`) + `must_stay_green` (≥10).
  Seed families are enumerated in the spec — cover paraphrases that do NOT
  contain the literal indicator strings from `RED_INDICATORS` (:94) /
  `AMBER_INDICATORS` (:158). Include the original incident phrase verbatim
  at `minimum_tier: RED`.
- `tests/test_safeguarding_corpus.py`: every must_flag classifies at >= its
  minimum tier (`_TIER_RANK`, :74); every must_stay_green stays GREEN;
  provenance fields mandatory. Failure messages must print phrase/expected/
  got/rationale.
- Harness check **C12** (P0, chain `preflight`, no expected_fail) in
  `teacher_readiness.py` using the same corpus loader — one implementation,
  two callers.
- If the classifier needs strengthening to pass: round-up only (never lower
  a tier), deterministic, glass-box rationale. Balance against
  `must_stay_green` — do not buy recall with a flood of false RED.
- Prove the instrument: locally weaken the classifier, show corpus test +
  C12 go red, capture output for the report, revert.

### F2 — expected_fail expiry mechanism (P0)
- `ReadinessCheck` (:38) gains `expected_fail_until` + `expected_fail_ref`;
  `_add_check` (:174) raises ValueError on bare `expected_fail=True`;
  lapsed `until` ⇒ recorded as REAL failure with
  `{"expected_fail_lapsed": ...}` evidence (CLI gate at `cli.py:127` then
  catches it unchanged).
- Update carriers: C11 → ref STT probe-parity + until 2026-09-10;
  DR → ref `dev/SPEC_LV_ONE_ENVELOPE_2026-08-10.md` + until 2026-08-24.
- Markdown table (:555) shows the new columns.
- Lock with the four tests listed in the spec.

### F3 — Standing wiring instrument (P1)
- `src/lingua_viva/wiring_audit.py`: AST import/call graph over
  `src/lingua_viva/**`, `src/education/**`, `src/web.py`, `src/pipeline.py`.
  Roots: `web.py` + `cli.py`. `tests/` are NOT roots. CRITICAL: catch
  in-function `from src.lingua_viva.X import Y` imports at all AST depths —
  that pattern is everywhere (`web.py:4419`, `lesson_materials.py:1113`) and
  missing it makes every module a false orphan.
- Allowlist `governance/wiring_allowlist.yaml` — entries require `ref` or
  `until` (F2 doctrine); lapsed = orphan. `archive/**` excluded.
- Wire in: `cli eval wiring --json` (exit 1 on non-allowlisted orphan) +
  harness check **WA** (P1, chain `preflight`).
- Self-test: planted orphan detected; in-function-import module NOT flagged.
- If the current tree has real orphans you cannot wire in scope: allowlist
  with refs and list them in the report. Do not silently expand scope.

## Rules

- Fix classes at chokepoints, never just surfaces; every fix gets a test
  that locks the class.
- Shared repo: other windows may commit under you. Hunk-level staging only;
  on push rejection `git stash push <specific paths>` → `pull --rebase` →
  push → `stash pop` immediately.
- Deterministic-first: no LLM calls in any of these instruments.
- Scope discipline: the spec is the boundary. New findings go in the report
  as gaps, not as bonus builds.
- Operator-blocked items (Slack/Drive values, Perplexity key, PAT secret)
  stay blocked — fail closed where absent.

## Exit gate (F4) — all required before "done"

1. `preflight` 6/6; `eval teacher-readiness --json` **21/21** (C12 + WA), 0 stubbed.
2. `pytest -q tests/` — no regressions vs 2225 passed / 13 skipped.
3. Live walkthrough (`uvicorn src.web:app --port 8765`, `LV_AUTH_MODE=local_header`,
   synthetic state): a must_flag phrase through the real observation route →
   restricted ledger only, NOT the student lens stream; a must_stay_green
   phrase flows normally. Verify liveness by output growth, not pgrep.
4. Weakening demonstration recorded and reverted.
5. `dev/SESSION_REPORT_LV_FAIL_CLOSED_WAVE_2026-08-10.md` written: built
   items, corpus counts, orphan/allowlist verdicts, evidence blocks,
   remaining gaps, commits.
6. Commit convention: `feat(engine): ...` / `fix(meta): ...` etc. Push, then
   apply **Rule 0**: this touches `src/**` so auto-release fires — done means
   all 3 release assets answer HTTP 200 and `chore(release): pin desktop-vX.Y.Z`
   is on origin. Watch the run; the pin-site job enforces this in CI, but you
   verify independently.
