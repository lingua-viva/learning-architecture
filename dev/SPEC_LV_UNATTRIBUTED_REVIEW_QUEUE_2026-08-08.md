# SPEC — Unattributed Document Review Queue — 2026-08-08

**Priority: P1 — one specific piece, taken all the way to perfect.**
Second targeted spec under the 2026-08-08 operator ruling (no whole-system passes).
This spec covers exactly one UX piece: *a Drive-ingested document that could not be
attributed to a student can actually be assigned by the teacher — and the list
survives the page.* Nothing else.

## The gap (verified against disk at `137a002`)

Pair 1 G1 shipped attribution honesty: `ingest_class_folder()`
(`src/lingua_viva/class_folder_ingest.py`) attributes conservatively and returns an
`unattributed` list. But the loop stops there:

- The unattributed list exists **only in the ingest HTTP response**. The UI
  (`static/index.html` ~5468) renders each item with a "review" badge and the text
  "Needs manual assignment." — with **no assignment control of any kind**. Navigate
  away and the list is gone; the only recovery is re-running the entire folder ingest.
- There is **no endpoint** to attribute an already-ingested document. The one
  assignment route that exists (`/api/...` at `src/web.py:1863`,
  `assign_student_file`) is the local-filemap lane — it knows nothing about the
  docpipe vault records this ingest created.
- The data needed is already persisted: `docpipe_vault.put_source()` +
  `put_extraction()` ran before attribution was attempted, so `source_id` and the
  extraction exist in the vault. But the `unattributed` response entry does not
  include `source_id`, so even a client that wanted to assign couldn't reference the
  document.

Result: "attribution honesty" currently means the teacher is honestly told about work
she cannot do. The review queue is display-only and ephemeral.

## What to build

### 1. Persist the queue (sanctioned location)

- Append each unattributed item at ingest time to
  `runtime_data_dir("ingest_review") / "unattributed.ndjson"` (the
  `runtime_paths.py` chokepoint — never a source-tree or `__file__`-derived path;
  that class is closed and locked by `test_runtime_write_locations.py`).
- Record: `{queued_at, teacher_id, folder_id, drive_id, source_id, name, reason,
  students_detected, status: "open"}`. **Add `source_id` to the in-memory
  `unattributed` entry in `ingest_class_folder()` too** — one line, it is in scope
  at that point.
- Status transitions are append-only events (`assigned` / `dismissed` lines
  referencing the `drive_id`+`source_id`), matching the repo's append-only ledger
  convention. Current state = last event per document. Re-ingesting the same file
  while an `open` entry exists must not duplicate the queue entry.

### 2. Two routes

- `GET /api/students/ingest/unattributed` — open items, newest first.
- `POST /api/students/ingest/attribute` — body
  `{source_id, drive_id, student_id | dismiss: true, teacher_id?}`.
  - Assign: load the extraction from the vault, run the SAME lens/evidence path the
    automatic branch uses — `docpipe_lens.create_from_extraction(...)` +
    `store.append_evidence(...)` with `attribution_method: "manual_teacher"`,
    `attribution_confidence: 1.0`, `confidence_level: "teacher_confirmed"` (teacher
    dropdown = confirmed evidence, same grade Pair 1 G5 uses). Then append the
    `assigned` event. Reuse the attribution branch of `ingest_class_folder` by
    extracting it into one function — do not copy the evidence-record shape into the
    route (that fork is how the two records drift apart).
  - Validate `student_id` against the current roster; unknown → 422, nothing written.
  - Dismiss: append `dismissed` event only; vault records stay (they are local).

### 3. UI: make the badge a control

In the ingest results panel AND as a small persistent "Needs review (N)" section of
the Students view (so the queue is reachable without re-running ingest):

- Each open item: document name, reason, `students_detected` hints (pre-select the
  dropdown when exactly one hint matches a roster student — suggest, never
  auto-assign; F5's no-auto-select rule applies), a roster dropdown with
  "Choose a student…" placeholder, Assign and Dismiss buttons.
- On assign: item leaves the list, toast confirms, and the student's lens panel
  refresh path is invoked (same surfacing G2 uses — the teacher sees the lens
  actually changed).
- Empty queue: "No documents waiting for review." — never an error state.

### 4. Privacy + ceremony

- Everything local: queue file, vault reads, lens writes. No egress, so no
  `assert_safe_for_external_output` site is added — assert that in review.
- Student names appear in the queue file → it lives under the runtime dir (never the
  repo), `chmod 0o600` like `roster_overrides.ndjson`.
- New routes classified in `contracts/ROUTE_REACHABILITY.yaml`; `static/index.html`
  + `src/web.py` changes → UI contract bump with log line.

## Class-locking tests

1. Hermetic ingest test: unattributed item lands in the queue file **with
   `source_id`**, survives a fresh "process restart" (new store), and is listed by
   the GET route. Locks the class "review queues are persisted, not response-only."
2. Manual attribution produces a lens/evidence record identical in shape to the
   automatic branch (same keys, `teacher_confirmed` grade) — assert via the shared
   function, locking the no-fork rule.
3. Assign to off-roster student → 422 and zero writes (queue unchanged, no evidence).
4. Re-ingest of a queued file does not duplicate the open entry.

## Acceptance

1. Teacher runs class-folder ingest, sees N unattributed items; closes the app;
   reopens; the N items are still there under Students → Needs review.
2. Assigning one updates the student's lens with teacher-confirmed evidence and
   removes it from the queue; dismissing removes it without writes to any lens.
3. Off-roster and duplicate cases behave per the locking tests; suite green;
   contract + route checks green.

## Non-goals

Fuzzy/suggested auto-attribution beyond showing `students_detected` hints, bulk
assign, editing extractions, deleting vault records, any Drive write-back. One queue,
two routes, one panel, done.
