# PROMPT — Build: Roster Split Review & Override Surface — 2026-08-08

You are the implementing builder for `~/learning-architecture` (Lingua Viva).

Setup: `cd ~/learning-architecture`, `unset ANTHROPIC_API_KEY` (subscription auth
only), `export MC_AGENT=1`. Start from current `main` — run `git log --oneline -8`
and confirm you see `42cbfd8` (docs), `137a002` (Voice §1, contract v126),
`e7580cc` (override wiring). If you don't, STOP and say so — you are on a stale tree.

Read, in order, before writing any code:

1. `dev/SPEC_LV_ROSTER_SPLIT_REVIEW_2026-08-08.md` — your spec. It wins on scope.
2. `dev/SPEC_LV_TIERED_MATERIALS_FULL_CIRCLE_2026-08-08.md` §G2 — the split rule and
   the "kept apart, never a fourth tier" INDIVIDUAL SUPPORT constraint you inherit.
3. `AGENTS.md` — "pushed" has a 7-step definition; you will NOT push.

## What this is

**One UX piece to perfect** (operator ruling 2026-08-08: no whole-system passes).
The backend is DONE — `assign_roster_split(..., overrides=...)`,
`RosterSplit.overrides`, `record_roster_overrides()` NDJSON, and `tier_overrides`
accepted by all three lesson-materials routes all shipped in `b721a0c` + `e7580cc`,
locked by `test_tier_overrides_applied_and_recorded`. What does not exist is the
surface: `grep -c "tier_overrides" static/index.html` → 0, and the words
"Foundational / On Track / Extended" appear nowhere a teacher can see. You are
mounting an existing capability, not building one. If you find yourself changing the
split rule in `lesson_materials.py`, stop — you are off the map.

## Map (verified against disk at `42cbfd8`)

- `src/lingua_viva/lesson_materials.py` — `assign_roster_split()`,
  `record_roster_overrides()`, `roster_overrides_path()`, `RosterSplit`
  (`tier_groups`, `roster_names`, `individual_support`, `overrides`).
- `src/web.py` — `_tier_overrides_from_payload()` helper just above the generate
  route (~5455); routes: `/api/lesson-materials/generate` (~5462),
  `.../packet/preview` (~5577), `.../packet/approve` (~5668). Generate already
  returns `"tier_overrides": split.overrides`.
- `static/index.html` — Prepare view; `lessonPayload()` builds the POST bodies;
  packet preview/approve handlers around line 1960–1995.
- `contracts/UI_CONTRACT.yaml`/`.lock` (currently **v126**),
  `contracts/ROUTE_REACHABILITY.yaml`, `scripts/check_ui_contract.py`,
  `scripts/check_route_reachability.py`, `tests/test_ui_contract.py`
  (`EXPECTED_VERSION = 126`).

## Build order (each phase its own commit)

1. **Placement reasons at the chokepoint**: extend `assign_roster_split` so each
   group member carries why it landed there (`rti` / `cefr` / `default` /
   `teacher_override`). One function, no route logic. Extend the existing split
   tests.
2. **Preview endpoint**: `POST /api/lesson-materials/roster-split` per the spec —
   store-only, no LLM, no Drive, and **previewed overrides are never recorded**
   (`record=False` path or pure variant; `record_roster_overrides` fires only where
   the override takes effect). Locking test: preview with `tier_overrides` leaves
   the override NDJSON absent/unchanged.
3. **Prepare panel**: three tier columns + visually separate INDIVIDUAL SUPPORT
   section, per-student placement reason, four-way placement select, override badge
   + per-student reset, instant re-preview on change, `state.tierOverrides` passed
   in ALL THREE lesson-materials POST bodies, applied overrides rendered after
   generate. Empty roster → plain statement, generation unchanged.
4. **Ceremony + surface lock**: classify the new route in
   `ROUTE_REACHABILITY.yaml`; bump UI contract (see rules); surface lock test in
   the `tests/test_ask_grounding_surface.py` style — individual-support markup
   distinct from tier columns, and no lesson-materials POST body in the file drops
   `tier_overrides`.

## Rules that ride with this build

- **Shared repo, concurrent windows.** Another window may be editing
  `static/index.html` / `src/web.py` for the unattributed-review build. Hunk-isolate
  your commits — commit ONLY your own hunks, never `git add .`, never stash without
  immediately popping. This week's contract drift came from exactly this.
- **Contract ceremony**: bump AFTER your final static/web edit, against the merged
  tree; add a bump-log line to `UI_CONTRACT.yaml`; update `EXPECTED_VERSION` in
  `tests/test_ui_contract.py`; commit yaml+lock+test TOGETHER with the change. If
  the other window landed a bump first, recompute yours on top — never race it.
- **No push, no release, no tag.** Committed ≠ shipped; the operator pushes.
- Class fixes at one chokepoint + a locking test; no instance patches.
- No student PII in this PUBLIC repo — fixture names stay obviously fake.
- Commit style: `type(scope): description` heredoc +
  `Co-Authored-By:` trailer, as in `git log`.

## Verify before claiming done

`pytest -q tests/test_lesson_materials.py tests/test_lesson_packet_routes.py
tests/test_ui_contract.py tests/test_route_reachability.py` green;
`python3 scripts/check_ui_contract.py` and `check_route_reachability.py` OK; then
full `pytest -q tests/`. Write
`dev/REPORT_LV_ROSTER_SPLIT_REVIEW_2026-08-08.md` (commits, acceptance vs spec,
what's still manual) and close with the 5-line format:
WINDOW / SHIPPED / MID-FLIGHT / BLOCKED / REPORT, with SHAs and paths.
