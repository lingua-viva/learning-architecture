# PROMPT — Build: Packet Print Surface — 2026-08-08

You are the implementing builder for `~/learning-architecture` (Lingua Viva).

Setup: `cd ~/learning-architecture`, `unset ANTHROPIC_API_KEY` (subscription auth
only), `export MC_AGENT=1`. Start from current `main` — run `git log --oneline -10`
and confirm you see BOTH `c18dd30` (roster-split surface) and `2831ce3`
(unattributed queue). Commits may exist on top of them — fine. If either is
missing, STOP: you are on a stale tree. Then run `git status --short`: if
`src/web.py` or `static/index.html` show modifications you did not make, another
window is still landing its build — wait for a clean status on those files before
touching them.

Read, in order, before writing any code:

1. `dev/SPEC_LV_PACKET_PRINT_2026-08-08.md` — your spec. It wins on scope.
2. `AGENTS.md` — "pushed" has a 7-step definition; you will NOT push.

## What this is

**One UX piece to perfect** (operator ruling 2026-08-08: no whole-system passes).
The backend already renders a complete print-ready HTML document with
`@media print` page-break CSS, and both packet routes already return it as
`packet.print_html` (`src/web.py:5719` preview, `:5819` approve) — but
`grep -c "print_html" static/index.html` → 0 and `window.print` appears nowhere.
The teacher cannot put paper in hands. Also: the only printable doc bakes in the
"Teacher-Only Individual Support" section with student names; the student-safe
variant (`render_shared_packet_markdown`) exists but is only used for Drive
share. You are mounting an existing capability + adding one student-safe render
output. If you find yourself writing PDF tooling or redesigning packet CSS,
stop — you are off the map.

## Map (verified against disk 2026-08-08)

- `src/lingua_viva/lesson_materials.py:746` —
  `render_printable_packet_html(markdown, *, print_ready=False)`; CSS with
  `.page-break { break-before: page; }` at line 800; full-doc wrap at 805.
- `render_printable_packet_markdown` (~line 639) — emits `---` before each
  student handout → `<hr class="page-break">`; per-tier page breaks already work.
  `include_support_section=True` emits "Teacher-Only Individual Support" with
  display names (~676-685).
- `render_shared_packet_markdown` (line 808) — student-safe variant
  (`individual_support=[]`, `include_support_section=False`); used only by
  `share_packet_to_drive` (line 918).
- `src/web.py:5681` preview route, `:5742` approve route — both duplicate the
  markdown/html/print_html render triplet inline.
- `static/index.html` — `previewLessonPacket()` ~2027 (preview panel ~2038-2043),
  `approveLessonPacket()` ~2050 (approved panel ~2060-2062). Preview lives in a
  `max-height:520px;overflow:auto` div — never print the page itself.
- `contracts/UI_CONTRACT.yaml`/`.lock`, `tests/test_ui_contract.py`
  (`EXPECTED_VERSION`) — read the LIVE version at build time (v129 when this
  prompt was written; it may have moved — never assume).
- Surface-lock test style: `tests/test_ask_grounding_surface.py`.

## Build order (each phase its own commit)

1. **Render bundle chokepoint**: `render_packet_bundle(lesson, materials, *,
   status, individual_support)` in `lesson_materials.py` returning
   markdown/html/print_html/**student_print_html** (shared variant,
   `print_ready=True`); both routes call it; `packet` response gains
   `student_print_html`. Locking test `tests/test_packet_print.py`:
   `print_html` contains "Teacher-Only Individual Support" when support present;
   `student_print_html` NEVER contains that heading nor any support student name,
   same inputs; both docs `<!doctype html>` + `page-break`; route responses
   carry both fields.
2. **UI print action**: ONE function `printPacketHtml(printHtml, label)` —
   hidden iframe, `srcdoc`, onload `contentWindow.print()`, cleanup. Two buttons
   in preview panel AND approved panel: "Print teacher packet"
   (`packet.print_html`) and "Print student handouts"
   (`packet.student_print_html`, with a hint that the teacher-only section is
   excluded). Missing field ⇒ button absent/disabled — never fall back to
   printing the app page. No app-wide `@media print`.
3. **Ceremony + surface lock**: UI contract bump (live+1 on the merged tree,
   bump-log line, `EXPECTED_VERSION`, yaml+lock+test one commit). Surface-lock
   test: `printPacketHtml` present, both `packet.print_html` and
   `packet.student_print_html` consumed, both button labels present, exactly one
   print-invocation site.

## Rules that ride with this build

- **Shared repo, concurrent windows.** Another window may be editing
  `static/index.html` / `src/web.py` (pending-evidence build). Hunk-isolate your
  commits — only your own hunks, never `git add .`, never stash without popping.
  If the other window bumped the contract first, recompute yours on top of the
  merged tree — never race it.
- **Everything local.** No egress; printing is a browser-local iframe action.
  No student PII in this PUBLIC repo — fixtures use obviously fake names.
- **No push, no release, no tag.** Committed ≠ shipped; the operator pushes.
- Class fixes at one chokepoint + a locking test; no instance patches.
- Commit style: `type(scope): description` heredoc + `Co-Authored-By:` trailer.

## Verify before claiming done

`pytest -q tests/test_lesson_materials.py tests/test_lesson_packet_routes.py
tests/test_packet_print.py tests/test_ui_contract.py
tests/test_route_reachability.py` green; `python3 scripts/check_ui_contract.py`
and `check_route_reachability.py` OK; then full `pytest -q tests/`. Write
`dev/REPORT_LV_PACKET_PRINT_2026-08-08.md` (commits, acceptance vs spec, what's
still manual — an actual paper print is operator-run) and close with the 5-line
format: WINDOW / SHIPPED / MID-FLIGHT / BLOCKED / REPORT, with SHAs and paths.
