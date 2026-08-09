# SPEC — Student Summary Finish Line (One Piece to Perfect) — 2026-08-08

Status: DRAFT — ready to build
Scope ruling: one UX piece taken all the way to done (operator ruling 2026-08-08).
This piece: **the family-facing Student Summary draft actually leaves the app
honestly** — the draft loop gets its missing exit, and the demo-student fallback
class is closed.

## The verified gap (all checked against disk 2026-08-08)

The Student Summaries panel drafts well and then strands the teacher — and the
route can silently substitute a demo student.

1. **Demo-student fallback (the serious one).**
   `POST /api/parents/recommendation` (`src/web.py:6136`):
   - `:6141` — `student_id = str(payload.get("student_id") or "student-nora")`
   - `:6152` — if `store.export_lens(student_id)` raises for ANY reason
     (unknown id included), it silently retries with `"student-nora"`.
   A teacher hitting this route with a bad/missing id receives a family-facing
   draft **built from demo-student data, labeled as their student**. The UI's
   F5 guard (index.html ~3875) protects only the current panel — the route
   itself is fail-open. This is a class bug: fabricating output rather than
   refusing.
2. **The draft dead-ends.** Panel text promises "Drafts appear here for editing
   before sending" (index.html:3866) and the review label says "Review before
   sending" — but after the draft renders (`:3898` — warnings + subject +
   `<textarea>` + label) there is **no affordance at all**: no copy, no print,
   no save. `grep parent-copy\|parent-print\|parent-send static/index.html` → 0.
   The teacher's actual exit is manual select-all in a textarea.
3. **C6 traceability is wired but unlocked.** `source_observation_ids` is now
   returned (`web.py:~6170`, comment cites teacher-readiness C6) — but the
   2026-08-03 harness run recorded `source_observation_ids: []` (FAIL P1) and
   no test locks the field. Whether the fix is complete is unproven.

## What to build

### Phase 1 — fail-closed student identity (backend class fix)

In the route: missing/blank `student_id` → 400; `export_lens` failure → 404
`{"error": "unknown_student"}`. Delete BOTH `"student-nora"` fallbacks
(web.py:6141 and 6152 — `grep -c student-nora src/web.py` must go to 0). Zero
generation, zero writes on the failure paths.

Locking tests (new module `tests/test_parent_summary_finish.py`):
- missing student_id → 400, unknown student → 404, and neither response
  contains a draft body.
- `"student-nora"` absent from `src/web.py` (string-level class lock, same
  style as the write-location lock).

### Phase 2 — C6 traceability lock

Test: a student with observations gets a draft whose `source_observation_ids`
is non-empty and every id belongs to that student's lens (mirror the harness C6
predicate). If the current wiring already passes, this is a pure lock — do not
redesign the id selection. If it fails, fix at the route's id-collection point
only.

### Phase 3 — the exit: copy + print

After the draft renders, two controls:
- **"Copy final text"** — copies the CURRENT edited textarea content (subject
  line + body) to the clipboard, toast on success. The teacher's edits win —
  never copy the original draft over their edits.
- **"Print"** — builds a minimal self-contained HTML doc from the edited
  textarea content (escaped) + subject line, and hands it to the EXISTING
  `printPacketHtml(...)` chokepoint from the packet-print build. Do not add a
  second print-invocation site — `tests/test_packet_print.py` locks exactly one.

The safety-warning block behavior is unchanged: warnings stay visible above the
draft; copy/print are not blocked (flag-never-block, same reasoning as Gap 1 —
the teacher owns the final message). "Review before sending. No AI attribution
in final message." stays visible next to the controls.

### Phase 4 — ceremony + surface lock

- UI contract bump (live version + 1 on the merged tree — v131 when this spec
  was written, re-read it; bump-log line; `EXPECTED_VERSION`; yaml+lock+test one
  commit).
- Surface-lock test: index.html contains "Copy final text" and the print
  control wired through `printPacketHtml`; `window.print` still appears at
  exactly one site; the F5 empty-student guard string stays present.

## Acceptance

1. Unknown or missing student can NEVER produce a draft — 400/404, no demo
   substitution, `student-nora` gone from web.py.
2. Draft → teacher edits in place → Copy puts the edited text on the clipboard;
   Print opens the OS dialog with the edited text, via the shared iframe
   chokepoint.
3. `source_observation_ids` non-empty and student-owned for students with
   observations (harness C6 predicate green at this surface).
4. Safety warnings render exactly as before; existing parent-report tests
   untouched and green.

## Non-goals (off the map)

- Sending email/anything from the app — copy/print IS the exit by design.
- Redesigning draft content, tone, `_strip_parent_output`, or the safety gate.
- Draft persistence/history. One piece.
- The harness's other reds (C8 materials 422, ZE evidence) — separate pieces.
