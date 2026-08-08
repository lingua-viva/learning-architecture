# PROMPT — Build: Unattributed Document Review Queue — 2026-08-08

You are the implementing builder for `~/learning-architecture` (Lingua Viva).

Setup: `cd ~/learning-architecture`, `unset ANTHROPIC_API_KEY` (subscription auth
only), `export MC_AGENT=1`. Start from current `main` — run `git log --oneline -8`
and confirm you see `42cbfd8` (docs), `137a002` (Voice §1, contract v126),
`cabf828` (write-location class fix). If you don't, STOP and say so — you are on a
stale tree.

Read, in order, before writing any code:

1. `dev/SPEC_LV_UNATTRIBUTED_REVIEW_QUEUE_2026-08-08.md` — your spec. It wins on scope.
2. `dev/SPEC_LV_STUDENT_LENS_FULL_CIRCLE_2026-08-08.md` §G1 (attribution honesty)
   and §G5 (evidence grades — teacher dropdown = `teacher_confirmed`).
3. `AGENTS.md` — "pushed" has a 7-step definition; you will NOT push.

## What this is

**One UX piece to perfect** (operator ruling 2026-08-08: no whole-system passes).
Pair 1's ingest honestly reports unattributed documents — and then strands the
teacher: the list lives only in the ingest HTTP response, the UI renders a "review"
badge with no control (`static/index.html` ~5468), there is no attribution endpoint
(the assignment route at `src/web.py:1863` is the local-filemap lane, a different
system), and the response entries omit `source_id` even though the document is
already in the docpipe vault. You are closing one loop: queue persists → teacher
assigns or dismisses → lens updates → item leaves the queue. If you find yourself
writing fuzzy auto-attribution or bulk tooling, stop — you are off the map.

## Map (verified against disk at `42cbfd8`)

- `src/lingua_viva/class_folder_ingest.py` — `ingest_class_folder()`: vault writes
  (`docpipe_vault.put_source/put_extraction`) happen BEFORE attribution, so
  `source_id` + extraction already persist for unattributed files; the automatic
  attribution branch (`docpipe_lens.create_from_extraction` +
  `store.append_evidence`, ~lines 100–135) is the code you must EXTRACT into one
  shared function and reuse — never copy its record shape into a route.
- `src/web.py:2608` — `POST /api/students/ingest/class-folder` (existing).
- `src/lingua_viva/runtime_paths.py` — `runtime_data_dir("ingest_review")` is your
  ONLY write location (the `Path(__file__)` class is closed and locked by
  `tests/test_runtime_write_locations.py` — do not reopen it).
- `src/lingua_viva/lesson_materials.py` `record_roster_overrides()` — the house
  pattern for append-only NDJSON + `chmod 0o600`; copy the pattern, not the file.
- `static/index.html` ~5468 — current display-only unattributed rendering; Students
  view for the persistent "Needs review (N)" section.
- `contracts/UI_CONTRACT.yaml`/`.lock` (currently **v126**),
  `contracts/ROUTE_REACHABILITY.yaml`, `tests/test_ui_contract.py`
  (`EXPECTED_VERSION = 126`).

## Build order (each phase its own commit)

1. **Persist + `source_id`**: add `source_id` to the in-memory unattributed entry in
   `ingest_class_folder()`; append open items to
   `runtime_data_dir("ingest_review") / "unattributed.ndjson"` (0o600, append-only
   events, last-event-wins state, no duplicate open entries on re-ingest). Locking
   test: item survives a fresh store ("process restart") and carries `source_id`.
2. **Shared attribution function**: extract the automatic branch into one function;
   the automatic path calls it unchanged (existing G1 tests must stay green
   untouched).
3. **Routes**: `GET /api/students/ingest/unattributed` (open items, newest first);
   `POST /api/students/ingest/attribute` (assign via the shared function with
   `attribution_method: "manual_teacher"`, `attribution_confidence: 1.0`,
   `confidence_level: "teacher_confirmed"`, then `assigned` event; or `dismiss`
   event only). Off-roster `student_id` → 422 and ZERO writes — locking test.
4. **UI**: assignment controls in the ingest results panel AND a persistent
   "Needs review (N)" section in Students — roster dropdown with "Choose a
   student…" placeholder, `students_detected` hints may pre-select ONLY on exactly
   one roster match (suggest, never auto-assign — F5 rule), Assign/Dismiss, toast +
   lens-refresh surfacing on assign, "No documents waiting for review." empty state.
5. **Ceremony**: classify both routes in `ROUTE_REACHABILITY.yaml`; UI contract
   bump with log line + `EXPECTED_VERSION` update, committed together.

## Rules that ride with this build

- **Shared repo, concurrent windows.** Another window may be editing
  `static/index.html` / `src/web.py` for the roster-split build. Hunk-isolate your
  commits — only your own hunks, never `git add .`, never stash without popping.
  If the other window bumped the contract first, recompute yours on top of the
  merged tree — never race it.
- **Everything local.** No egress site is added; queue file and names live under
  the runtime dir, never the repo. No student PII in this PUBLIC repo — fixtures
  use obviously fake names.
- **No push, no release, no tag.** Committed ≠ shipped; the operator pushes.
- Class fixes at one chokepoint + a locking test; no instance patches.
- Commit style: `type(scope): description` heredoc + `Co-Authored-By:` trailer.

## Verify before claiming done

`pytest -q tests/test_students_ingest.py tests/test_runtime_write_locations.py
tests/test_ui_contract.py tests/test_route_reachability.py` green (plus your new
test module); `python3 scripts/check_ui_contract.py` and
`check_route_reachability.py` OK; then full `pytest -q tests/`. Write
`dev/REPORT_LV_UNATTRIBUTED_REVIEW_QUEUE_2026-08-08.md` (commits, acceptance vs
spec, what's still manual — live-Drive spot check stays operator-run) and close
with the 5-line format: WINDOW / SHIPPED / MID-FLIGHT / BLOCKED / REPORT, with
SHAs and paths.
