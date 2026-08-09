# SPEC — Packet Print Surface (One Piece to Perfect) — 2026-08-08

Status: DRAFT — ready to build
Scope ruling: one UX piece taken all the way to done (operator ruling 2026-08-08,
no whole-system passes). This piece: **a teacher can put paper in hands** — the
printable packet becomes actually printable from the app.

## The verified gap (all checked against disk 2026-08-08)

The backend already produces a complete, self-contained, print-ready HTML
document — and the UI never lets the teacher print it.

- `src/lingua_viva/lesson_materials.py:746` `render_printable_packet_html(markdown,
  *, print_ready=False)` — full renderer with embedded CSS including
  `@media print { .page-break { break-before: page; } body { margin: 18mm; } }`
  (line 800). `print_ready=True` wraps in a full `<!doctype html>` document
  (line 805).
- The markdown renderer emits `---` before every student handout
  (`render_printable_packet_markdown`, ~line 695) → `<hr class="page-break">` →
  each tier handout starts on a fresh page. Page breaks are DONE.
- Both packet routes ALREADY return it: `src/web.py:5719` (preview) and
  `src/web.py:5819` (approve) compute
  `print_html = render_printable_packet_html(markdown, print_ready=True)` and
  return it as `packet.print_html`.
- **`grep -c "print_html" static/index.html` → 0.** The UI ignores the field.
- **`grep -c "window.print" static/index.html` → 0.** No print action anywhere.
- The preview renders inside `style="max-height:520px;overflow:auto;"`
  (index.html ~2040) — printing the app page would print a clipped scroll box
  plus the whole app chrome.
- The teacher-only INDIVIDUAL SUPPORT section is baked into the one packet:
  `render_printable_packet_markdown(include_support_section=True)` emits
  "### Teacher-Only Individual Support" with student display names
  (lesson_materials.py ~676-685). The student-safe variant exists —
  `render_shared_packet_markdown` (line 808, `individual_support=[]`,
  `include_support_section=False`) — but it is only used for the Drive share
  (line 918). If the teacher prints today, the only printable thing carries the
  teacher-only names section.

Net effect: the "Printable Lesson Packet" fails the paper test. The teacher's
path to paper is copy/paste into a school doc. This spec closes it.

## What to build

### Phase 1 — one render bundle at the chokepoint (backend)

Both routes currently duplicate the render triplet (markdown / html /
print_html) and neither produces a student-safe print doc. Extract ONE shared
helper in `src/lingua_viva/lesson_materials.py`:

```python
def render_packet_bundle(lesson, materials, *, status, individual_support) -> dict
```

returning `{"markdown", "html", "print_html", "student_print_html"}` where
`student_print_html` = `render_printable_packet_html(render_shared_packet_markdown(
lesson, materials, status=status), print_ready=True)`. Both routes
(`/api/lesson-materials/packet/preview` ~5681, `/packet/approve` ~5742) call it;
`packet` response dict gains `student_print_html`. No route grows its own render
logic — class fix at one chokepoint.

Locking test (new module `tests/test_packet_print.py`):
- `render_packet_bundle` output: `print_html` contains
  "Teacher-Only Individual Support" when individual support is present;
  `student_print_html` NEVER contains that heading and NEVER contains any
  individual-support student display name — for the same inputs.
- Both docs start with `<!doctype html>` and contain `page-break`.
- Route-level: preview response `packet` carries both `print_html` and
  `student_print_html` (existing test style in `tests/test_lesson_packet_routes.py`).

### Phase 2 — print action in the UI (one chokepoint function)

One JS function in `static/index.html`:

```js
function printPacketHtml(printHtml, label) { ... }
```

Mechanism: create a hidden `<iframe>`, set `srcdoc` to the print-ready doc, on
load call `contentWindow.print()`, remove the iframe after. Do NOT add an
app-wide `@media print` stylesheet — the print doc is self-contained by design;
printing must never depend on app CSS.

Buttons, in BOTH the preview panel (~2038-2043) and the approved panel (~2060-2062):
- **"Print teacher packet"** → `printPacketHtml(data.packet.print_html, ...)` —
  the full packet including the teacher-only section.
- **"Print student handouts"** → `printPacketHtml(data.packet.student_print_html, ...)`
  — the student-safe variant. Button copy or a one-line hint must say the
  teacher-only individual support section is not in this version.

Both buttons disabled/absent when the field is missing (older cached draft) —
fail closed, no printing the clipped preview div as a fallback.

### Phase 3 — ceremony + surface lock

- UI contract bump (live version + 1 against the merged tree; bump-log line;
  `EXPECTED_VERSION` in `tests/test_ui_contract.py`; yaml+lock+test in one commit).
- Surface-lock test (in `tests/test_packet_print.py`, house grep style à la
  `tests/test_ask_grounding_surface.py`): `static/index.html` contains
  `printPacketHtml`, consumes `packet.print_html` AND `packet.student_print_html`,
  contains both button labels, and does NOT contain `window.print()` outside the
  iframe chokepoint (i.e., exactly one print invocation site).

## Acceptance

1. Teacher previews a packet → two print buttons appear → "Print teacher packet"
   opens the OS print dialog with the full document, each tier handout on its own
   page.
2. "Print student handouts" prints a document with NO "Teacher-Only Individual
   Support" heading and no individual-support names.
3. Same two buttons after approve.
4. Empty individual support ⇒ both variants print fine (no empty-section litter —
   already guaranteed by `include_support_section` logic; test it anyway).
5. All existing packet tests untouched and green.

## Non-goals (off the map)

- PDF generation, pagination tuning, print CSS redesign — the embedded CSS is done.
- Printing anything else in the app (reports, lenses). One piece.
- Changing packet content, tiers, or the Drive share path.
- App-wide print stylesheet.
