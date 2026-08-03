# T7 — E2E Integration + Grounding Audit (Wave 4 — THE RELEASE GATE)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Prereqs: T0–T6 + T9 committed (T8 is independent; include its PII gate check if
landed). Read first: `dev/CONTRACTS_V1_2026-08-04.md`, all T-track specs,
`dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: `tests/e2e_docpipe/`, a runner script in `scripts/`. Nothing else.

## Phase 1 — Spec prompt

Define the end-to-end acceptance test for the LV document loop. Output
`dev/SPEC_T7_E2E_2026-08-04.md`, no code.

The loop under test:
```
Drive file → local vault → extraction → lens created by the app
→ teacher dictates observation → parsed → edited → saved
→ lens updated locally → propagated back to Drive
```

Specify:
- Fixture Drive folder contents (synthetic students only) and a local-only
  variant of the loop for when Drive credentials are absent (the loop must be
  provable without network — Drive hops marked SKIPPED, not passed).
- The exact assertions at each hop (source hash in manifest; extraction
  schema-valid with spans; lens fields all evidence-backed; observation merge
  additive; sync queue drained; Drive doc readable).
- **The grounding audit**: a full pass over the resulting vault asserting NO
  field anywhere is populated without valid `evidence[]` whose span/obs
  references resolve. Use the docpipe validator + `grounding.verify`.
- Failure-mode tests, each must degrade safely and never corrupt the vault:
  Drive unavailable mid-import; local model timeout during extraction; app
  killed during lens write; sync queue interrupted mid-drain.
- Regression floor: full existing suite + `lv eval teacher-readiness` ≥ 16/19.

## Phase 2 — Implementation prompt

Implement the spec as a runnable suite. Deliver a single command
(`scripts/run_docpipe_e2e.sh` or `lv eval docpipe`) that runs the full loop
against a real Drive folder (or the local-only variant), printing a pass/fail
report per hop plus the grounding audit result as a hard gate.

**If the grounding audit finds ANY ungrounded field, the suite exits nonzero.
That is the release gate** — nothing ships to teachers while it fails.

Commit ONLY owned files by explicit path, message
`docpipe: e2e loop + grounding audit release gate (T7)`. Report: per-hop results,
grounding audit verdict, and any hop that only passed in local-only mode.
