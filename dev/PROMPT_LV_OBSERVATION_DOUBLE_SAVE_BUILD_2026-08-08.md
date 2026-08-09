# PROMPT — Build: Observation Double-Save Idempotency — 2026-08-08

You are the implementing builder for `~/learning-architecture` (Lingua Viva).

Setup: `cd ~/learning-architecture`, `unset ANTHROPIC_API_KEY` (subscription auth
only), `export MC_AGENT=1`. Start from current `main` — run `git log --oneline -10`
and confirm you see `fd370a4` (packet-print contract v130) and `26836f5` (pending
evidence review, contract v131). Commits may exist on top — fine. If either is
missing, STOP: stale tree. If `git status --short` shows modifications to
`src/web.py`/`static/index.html` you did not make, another window is mid-landing —
wait for those files to be clean before touching them.

Read, in order, before writing any code:

1. `dev/SPEC_LV_OBSERVATION_DOUBLE_SAVE_2026-08-08.md` — your spec. It wins on scope.
2. `AGENTS.md` — "pushed" has a 7-step definition; you will NOT push.

## What this is

**One UX piece to perfect** (operator ruling 2026-08-08: no whole-system passes).
Teacher-readiness C7 FAILED (P2, 08-03 run): two identical
`POST /api/observe/capture` calls create two observation records —
`append_observation` (`src/education/student_lens.py:1260`) has zero dedupe,
while the two sibling writers already suppress double-submits
(`add_profile_strength` ~2198-2207, `_append_ethos_evidence_item` ~2326-2336).
A double-tap on Save silently duplicates an observation, which then feeds
rollups, RTI recalculation, and reports twice. You are adding the missing
idempotency at the one chokepoint + surfacing "Already saved." to the teacher.
If you find yourself building fuzzy matching, historical dedup, or chasing other
harness failures, stop — off the map.

## Map (verified against disk 2026-08-08)

- `src/education/student_lens.py:1260` — `append_observation`, the ONLY place
  the fix lives. House idempotency patterns to mirror: `add_profile_strength`
  ~2198 (identical text+source → return unchanged), `_append_ethos_evidence_item`
  ~2326 (identical summary+source → return existing).
- `src/web.py` — `/api/observe/capture` route (pass `duplicate: true` through).
- `static/index.html` — observation save handler in the Observe view (~2076+,
  `saveObservation`/equivalent — find the actual handler; the mic/save flow was
  built in the Observe panel).
- Harness: `src/lingua_viva/teacher_readiness.py:347-355` `_run_double_artifact`
  — C7 predicate is `len(after - before) == 1` for two identical captures.
  Runner: `python3 -m src.lingua_viva.cli eval teacher-readiness` (report-only,
  ~6 min; writes `dev/reports/TEACHER_READINESS.md`).
- `contracts/UI_CONTRACT.yaml`/`.lock`, `tests/test_ui_contract.py`
  (`EXPECTED_VERSION`) — read the LIVE version (v131 at spec time; may have
  moved — never assume).

## Build order (each phase its own commit — do not collapse phases)

1. **Chokepoint idempotency**: in `append_observation`, identical
   (`student_id`, `teacher_id`, `template_type`, `raw_transcript`) within a
   300 s double-submit window → return the EXISTING observation dict +
   `"duplicate": True`; no new row, no re-enrichment, no RTI recalc, no rollup
   side effects. Outside the window or any field differs → normal insert.
   Time must be test-controllable. Locking tests in
   `tests/test_observation_double_save.py`: one-row + same id + duplicate flag;
   different text/teacher/template → two rows; window expiry → two rows;
   suppressed path leaves enrichment/RTI state identical to single-save.
2. **Route + UI honesty**: `/api/observe/capture` passes `duplicate: true`
   through; save handler shows "Already saved." instead of a second success and
   does NOT re-trigger lens-refresh surfacing. Nothing else changes.
3. **Ceremony + surface lock + harness evidence**: contract bump (live+1 on the
   merged tree, bump-log line, `EXPECTED_VERSION`, yaml+lock+test one commit);
   surface lock — "Already saved." present, handler checks `duplicate`. Run the
   teacher-readiness harness and put the fresh C7 PASS row in your report;
   report (but do NOT chase) the other harness reds.

## Rules that ride with this build

- **Shared repo, concurrent windows.** Another window is on the Student Summary
  finish-line piece (also touches `src/web.py`/`static/index.html`).
  Hunk-isolate; only your own hunks; never `git add .`; never stash without
  popping. Whoever lands the contract bump second recomputes on the merged
  tree — never race it.
- **Everything local.** No student PII in this PUBLIC repo — fixtures use
  obviously fake names.
- **No push, no release, no tag.** Committed ≠ shipped; the operator pushes.
- Class fixes at one chokepoint + a locking test; no instance patches — the
  dedupe lives in `append_observation`, never in the route or UI.
- Commit style: `type(scope): description` heredoc + `Co-Authored-By:` trailer.

## Verify before claiming done

`pytest -q tests/test_observation_double_save.py tests/test_ui_contract.py
tests/test_route_reachability.py` green plus the existing observation/lens test
modules you touched nothing in; `python3 scripts/check_ui_contract.py` and
`check_route_reachability.py` OK; harness C7 PASS evidence captured; then full
`pytest -q tests/`. Write
`dev/REPORT_LV_OBSERVATION_DOUBLE_SAVE_2026-08-08.md` (commits, acceptance vs
spec, fresh harness table excerpt) and close with the 5-line format:
WINDOW / SHIPPED / MID-FLIGHT / BLOCKED / REPORT, with SHAs and paths.
