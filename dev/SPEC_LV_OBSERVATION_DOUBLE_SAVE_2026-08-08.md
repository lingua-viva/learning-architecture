# SPEC — Observation Double-Save Idempotency (One Piece to Perfect) — 2026-08-08

Status: DRAFT — ready to build
Scope ruling: one UX piece taken all the way to done (operator ruling 2026-08-08).
This piece: **saving the same observation twice creates one record, and the
teacher is told so** — closing teacher-readiness C7.

## The verified gap (all checked against disk 2026-08-08)

- Teacher-readiness harness C7 ("Repeated save produces one record") FAILED P2
  on the 2026-08-03 run: `created_count: 2` — two identical
  `POST /api/observe/capture` calls created two observation records
  (`src/lingua_viva/teacher_readiness.py:347-355`, `_capture` at `:215` posts
  `student_id`/`teacher_id`/`raw_transcript`/`template_type`).
- The chokepoint has NO dedupe: `append_observation`
  (`src/education/student_lens.py:1260`) — zero duplicate/idempotency handling
  (verified by grep).
- This is an inconsistency in the house pattern, not just a bug: the OTHER two
  writers already suppress double-submits —
  `add_profile_strength` (~2198-2207: identical text + source → return
  unchanged, no profile_version bump) and `_append_ethos_evidence_item`
  (~2326-2336: identical summary + source → return existing). Observations are
  the one governed write path without it.
- Teacher impact: a double-tap on Save (touch devices, slow disk) silently
  duplicates the observation; the duplicate then feeds lens rollups, RTI
  recalculation, reports, and evidence counts twice.

## What to build

### Phase 1 — idempotency at the chokepoint (store)

In `append_observation` (student_lens.py:1260): before inserting, look for an
existing observation with identical (`student_id`, `teacher_id`,
`template_type`, `raw_transcript`) whose `created_at` is within a short
double-submit window (default 300 s; injectable/parameterizable for tests —
follow however `_now_iso` is testable in this store, or accept a `now`
parameter). On a hit: return the EXISTING observation dict with
`"duplicate": True` added — no new row, no re-enrichment, no RTI
recalculation, no rollup side effects.

Outside the window, or any field differing → normal insert (a teacher may
legitimately record the same words another day).

Locking tests (new module `tests/test_observation_double_save.py`):
- Identical capture twice → one row, second return carries `duplicate: True`,
  same `observation_id`, and enrichment/RTI state matches the single-save state.
- Different transcript, different teacher, or different template_type → two rows.
- Same capture after the window elapses → two rows (time-controlled).
- Harness parity: the C7 predicate (`before`/`after` id-set delta == 1) passes
  against the route.

### Phase 2 — route + UI honesty

- `/api/observe/capture` response passes `duplicate: true` through unchanged.
- UI (`static/index.html` observation save handler): on `duplicate: true`, show
  an "Already saved." toast/status instead of a second success message, and do
  NOT re-trigger the lens-refresh surfacing a second time. No other behavior
  change.

### Phase 3 — ceremony + surface lock + harness evidence

- If `src/web.py`/`static/index.html` changed: UI contract bump (live version
  + 1 on the merged tree — v131 when this spec was written, re-read it;
  bump-log line; `EXPECTED_VERSION`; yaml+lock+test one commit).
- Surface-lock test: "Already saved." present in index.html; the save handler
  checks `duplicate`.
- Run the teacher-readiness harness
  (`python3 -m src.lingua_viva.cli eval teacher-readiness` — report-only,
  ~6 min) and put the fresh C7 row (PASS) in your report. Other harness reds
  (C8 materials 422, ZE, C9/C10) are OUT of scope — report them, don't chase
  them.

## Acceptance

1. Double-tap save = one observation record, teacher sees "Already saved."
2. Legitimate repeats (different day/text/teacher/template) are never
   suppressed.
3. No duplicate enrichment/RTI/rollup side effects on the suppressed path.
4. Harness C7 green on a fresh run; all existing observation/lens tests
   untouched and green.

## Non-goals (off the map)

- Fuzzy/near-duplicate detection — exact match within a window only.
- Dedup of historical existing data — forward-only.
- Touching the other harness failures. One piece.
