# REPORT — Packet Print Surface — 2026-08-08

## Window

Packet print surface: make the printable lesson packet actually printable from Prepare, with teacher and student-safe print variants.

## Commits

- `6ce1e37` — `feat(packet-print): add student-safe print bundle`
- `d491a4a` — `feat(packet-print): add teacher and student print buttons`
- `fd370a4` — `chore(packet-print): bump UI contract to v130`

## Acceptance

- Added `render_packet_bundle(...)` as the packet rendering chokepoint for Markdown, app HTML, teacher `print_html`, and student-safe `student_print_html`.
- Preview and approve packet routes now return both `packet.print_html` and `packet.student_print_html`.
- Teacher print HTML keeps the Teacher-Only Individual Support section when support students are present.
- Student print HTML is built from the shared packet renderer and excludes the teacher-only support section and support student names.
- Prepare packet preview and approved packet panels now show `Print teacher packet` and `Print student handouts` buttons when the corresponding print document exists.
- Printing uses one hidden-iframe chokepoint, `printPacketHtml(printHtml, label)`, and never falls back to printing the clipped app page.
- UI contract bumped to v130 and surface lock added in `tests/test_packet_print.py`.

## Verification

Run from clean detached worktree `/tmp/lv-packet-print-verify-3eAPMj` at `fd370a4`:

- `pytest -q tests/test_lesson_materials.py tests/test_lesson_packet_routes.py tests/test_packet_print.py tests/test_ui_contract.py tests/test_route_reachability.py` — `42 passed`
- `python3 scripts/check_ui_contract.py` — OK, contract v130
- `python3 scripts/check_route_reachability.py` — OK, 157 routes classified
- `pytest -q tests/` — `2057 passed, 13 skipped`

## Manual / Context

- No push performed.
- Actual OS/browser paper-print confirmation remains operator-run.
- During final verification, another window began pending-evidence edits in `src/web.py`, `static/index.html`, contract files, and related tests. Packet-print verification was run in a clean worktree at the committed packet-print state to avoid mixing those unrelated in-flight changes.
