# REPORT — Roster Split Review & Override Surface — 2026-08-08

## Window

Roster split review / override surface for Prepare.

## Commits

- `339688a` — `feat(roster-split): expose placement reasons at split chokepoint`
- `feffaad` — `feat(roster-split): add pure split preview endpoint`
- `c18dd30` — `feat(roster-split): mount prepare review surface`
- `2a8bc5f` — `chore(roster-split): lock prepare review contracts`
- `d839294` — `test(roster-split): update stale prepare call-site locks`

## Acceptance

- Prepare now calls `POST /api/lesson-materials/roster-split` and renders Foundational / On Track / Extended columns plus a visually separate Individual Support section.
- Each rendered student row carries a placement reason: RTI, CEFR, default, teacher override, or individual-support reason.
- Teachers can set a four-way placement override per student, reset it per student, and see an instant re-preview without recording preview-only override choices.
- `tier_overrides` now flows through Generate, Packet Preview, and Packet Approve lesson-materials POST bodies.
- Generate renders the returned applied overrides after materials are generated.
- Empty roster state says plainly that generation can continue with empty groups.
- Route reachability classifies the new preview and generate UI call sites, and legacy Prepare endpoints are now backend-only.
- UI contract bumped to v127 against a clean tree at the committed roster-split state.

## Verification

Run from clean detached worktree `/tmp/lv-roster-verify2-iMZtya` at `d839294`:

- `pytest -q tests/test_lesson_materials.py tests/test_lesson_packet_routes.py tests/test_ui_contract.py tests/test_route_reachability.py` — `37 passed`
- `python3 scripts/check_ui_contract.py` — OK, contract v127
- `python3 scripts/check_route_reachability.py` — OK, 155 routes classified
- `pytest -q tests/` — `2045 passed, 13 skipped`

## Manual / Context

- Confirmed `98d1c95`, `42cbfd8`, `137a002`, and `e7580cc` in local git history before implementation.
- No push performed.
- The main worktree still contains unrelated concurrent unattributed-review edits in `src/web.py`, `static/index.html`, contract files, and ingest-review files. Roster-split commits were hunk-isolated; verification used a clean worktree to avoid those unrelated dirty files.
