# Lingua Viva Doctor Full Sweep — Prompt (2026-08-04)

**For:** whichever Claude Code session runs this (Kiro or otherwise). This is the LV analog of
Mission Canvas's `mc improve` loop — Doctor here is narrower in scope than `mc improve` (it's a
publication-safety/authoring-repo health check, not a self-improving pipeline), so this prompt
wires Doctor together with every other diagnostic/eval/build-gap tool this repo actually has into
one disciplined sweep. Nothing here is guessed — every command below was verified to exist and
run before this prompt was written.

## Ground rules (read before starting)

- **One finding at a time.** Fix root cause, add/extend a test that locks the fix, re-run the
  specific check, then move to the next finding. This mirrors
  `dev/REPORT_DOCTOR_SWEEP_2026-07-20.md` — the last time Doctor findings were worked this way.
  Do not batch-silence multiple findings with one broad change.
- **Never blindly "build the missing file."** `spec-status` will surface `missing_claimed_file`
  findings where an old spec claims a file that was never built. Some of these are real gaps.
  Others are **stale MC-transfer specs** (e.g. anything claiming `src/mc_cli.py`,
  `src/api_server.py`, `src/gates/`, `src/missions/`) that were deliberately never ported — LV's
  own Doctor has a dedicated check (`check_active_surface_mc_bloat`) specifically to keep
  Mission-Canvas platform machinery OUT of LV's active surfaces. Building one of those files
  would itself trip that check. For every `missing_claimed_file` finding: first decide superseded
  (mark the spec's status accordingly, don't build) vs. still-intended-and-real-gap (build it,
  minimal, matching LV's existing architecture) vs. genuinely ambiguous (flag for operator
  ruling, do not guess).
- **Privacy first, no exceptions.** Never read `.docx` contents, never touch curriculum content,
  never promote the curriculum matrix, never touch student data. Doctor's own `blocked_actions`
  list is authoritative: docx edits, curriculum matrix promotion, curriculum content rewrites,
  destructive git commands, student-data upload, external support transmission.
- **Don't commit or push without the operator's explicit go-ahead.** Build, fix, verify, and
  write a report — leave the working tree ready for review, same discipline as every prior
  session.
- If a finding requires a genuine product decision (not a bug, not clearly root-cause-able),
  write it up the same way `dev/ADD_STUDENT_FORM_DECISION_2026-08-04.md` did: options +
  recommendation, don't just pick one silently.

## Phase 0 — Baseline (capture everything before touching anything)

Run all of these and save raw output before any fix, so the before/after delta is honest:

```bash
python3 -m src.lingua_viva.cli health --full --json          # doctor + pytest + gauntlet + golden eval + server 5xx, one shot
python3 -m src.lingua_viva.cli doctor --json                 # 16 publication/authoring-repo checks
python3 -m src.lingua_viva.cli preflight --json               # ui_contract, golden_parses, imports, ontology, route_reachability, no_conflicts
pytest tests/ -q                                               # full suite — last known baseline: 1975 passed / 13 skipped / 0 failed
python3 doctor/lv_artifact_gauntlet.py                        # publication artifact gauntlet directly
python3 -m src.lingua_viva.cli eval golden --json             # education golden classification suite
python3 -m src.lingua_viva.cli eval teacher-readiness --json  # persona route harness — last known result was 68.4% and STALE, needs a real re-run
python3 -m src.lingua_viva.cli audit --json                   # lagging-indicator audit over gap signals
python3 -m src.lingua_viva.cli distill --json                 # ranked gap clusters / candidates / revision log
python3 -m src.lingua_viva.cli candidates --all               # ontology candidate nodes proposed from classification gaps
python3 -m src.lingua_viva.cli spec-status --markdown --strict # spec/status drift across dev/ — 94 specs, ~159 findings last run (19 fail, 140 warn)
python3 -m src.lingua_viva.cli golden-workflows --hermetic --json  # integration-loop golden workflows
python3 scripts/check_app_reality.py
python3 scripts/check_route_reachability.py
python3 scripts/check_ui_contract.py
python3 scripts/run_lv_voice_gir_hardening.py
```

Save every raw output under `dev/reports/artifacts/doctor-sweep-2026-08-04/` before fixing
anything.

## Phase 1 — Fix every FAIL / hard error (not warnings yet)

Priority order: `pytest` failures → `doctor` FAIL checks → `preflight` FAIL checks → gauntlet FAIL
→ golden eval failures → `golden-workflows` failures. For each:
1. Read the actual failure, trace to the real file (don't guess from the message alone).
2. Fix the root cause, not the symptom — if the same defect class could hit another code path,
   fix the class, not just the one reported instance.
3. Add or extend a test that locks the fix so it can't silently regress.
4. Re-run only that specific check to confirm green before moving to the next finding.

## Phase 2 — Triage `spec-status` findings (this is the "build missing pieces" phase)

For every `fail`-level `missing_claimed_file` finding (there were 19 at last run):
- Read the spec. Is it superseded by later work (check git log / current architecture / whether
  the described feature shipped under a different file name)? → Update the spec's Status header
  to reflect reality (e.g. `superseded_by: <later spec or commit>`), no code change.
- Is it a real, still-wanted gap with no later spec covering it? → Build the minimal version that
  satisfies the spec's actual intent, matching LV's existing module boundaries
  (`src/lingua_viva/` for runtime, `src/education/` for teacher-facing product code — see
  `CLAUDE.md` "Runtime boundary"). Write tests. Do not import or recreate MC platform machinery.
- Is it genuinely unclear which of the above applies? → Do not guess. Write it into a decision doc
  (options + recommendation) for operator ruling, same pattern as prior decision docs in `dev/`.

For every `warn`-level `missing_index_entry` / `status_drift` (there were ~140):
- These are cheap doc hygiene: add the spec to `dev/INDEX.md`, add a `Status:` header. Batch these
  — they're mechanical, not judgment calls, as long as you're not changing what a spec claims.

## Phase 3 — Work through `audit`, `distill`, `candidates`, and the GIR hardening script

- `audit`/`distill`: these surface lagging-indicator drift and ranked gap clusters from real
  classification signals. For each real signal (not noise), decide fix vs. deliberately-deferred
  — if deferred, it needs a one-line reason, not silence.
- `candidates`: ontology nodes proposed from genuine classification gaps. Promote what's
  clearly correct and low-risk; leave ambiguous ones for operator review — never promote a
  candidate that would touch curriculum content without sign-off.
- `run_lv_voice_gir_hardening.py`: review the GIR delta output (v1 vs v2 shadow score). Any drop
  in grounding integrity is a real regression — root-cause it, don't just note it.

## Phase 4 — Re-run everything from Phase 0, full clean pass

Same command list as Phase 0. Every FAIL must now be gone or explicitly documented as an
operator-decision item (not silently left). `pytest tests/ -q` must be at least as green as the
1975/13/0 baseline — if any count regressed, that's a new Phase 1 finding, not something to note
and move past.

## Phase 5 — Report

Write `dev/REPORT_DOCTOR_FULL_SWEEP_2026-08-04.md` following the same structure as
`dev/REPORT_DOCTOR_SWEEP_2026-07-20.md`:
1. Findings handled — one entry per fix: starting state, root cause, change, test coverage.
2. Findings reviewed and deliberately deferred — with reason.
3. Findings that needed an operator decision — pointer to the decision doc, not resolved here.
4. Full before/after of every Phase 0 command.
5. Final verification block (health --full, preflight, full pytest, spec-status counts).

Leave the working tree uncommitted for review — do not push.
