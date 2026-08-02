# Build Prompt — Multi-Teacher Triangulation via Shared Drive Workspace

You are implementing `dev/SPEC_LV_MULTI_TEACHER_TRIANGULATION_2026-08-01.md`.
**Preconditions**: Spec 1 built (Category Profile panel). Spec 2 (evidence) optional — if
absent, ship observation-only ledgers and leave evidence hooks commented with a TODO.
**Check the spec's Open Question has an operator ruling** (teacher display names). If unruled,
stop and report.

Read first:

```text
dev/SPEC_LV_MULTI_TEACHER_TRIANGULATION_2026-08-01.md
src/lingua_viva/drive_sync.py            (full — sync_lens_to_drive, _record_pending_sync, config keys)
src/lingua_viva/google_drive_integration.py  (upload_text_to_folder + whatever list/download helpers exist — inventory them before designing pull)
src/education/student_lens.py            (Observation.to_row, append_observation, confidence levels 85-90, schema)
tests/                                   (grep for existing drive_sync test doubles/mocks — REUSE that pattern)
src/lingua_viva/privacy_log.py
static/index.html                        (student detail view from Spec 1)
```

## Objective

Teachers on separate machines triangulate on shared students through the school's own Drive
folder: per-teacher NDJSON observation ledgers pushed alongside the existing Markdown lens,
pulled + merged append-only by UUID with provenance, rendered with author badges and
deterministic convergence/divergence signals.

## Hard Rules

1. **IDs, never names, in Drive filenames.** `{student_id}.{teacher_id}.ledger.ndjson`.
2. **Append-only union merge.** Known UUID → skip. No overwrites, no conflict resolution
   code — if you find yourself writing merge-conflict logic, re-read the spec.
3. **Provenance immutable.** Imported rows keep original `teacher_id`; `origin="imported"`;
   local rows are never modified by a pull.
4. **No new egress.** The only network destination is the already-configured sync folder via
   the existing Drive integration functions. If a helper you need (list folder files, download
   file content) doesn't exist in `google_drive_integration.py`, add it there following the
   existing auth/error patterns — do not import googleapiclient anywhere else.
5. **Fire-and-forget failures** like the existing push path — a failed pull never blocks or
   corrupts; partial imports are safe because merge is idempotent.
6. **Convergence signals are deterministic** — counting and date comparison only, no LLM.
7. Hermetic tests, no commits, UI contract ceremony as usual.

## Build Order

### Step 1 — Schema
`origin TEXT DEFAULT 'local'` on observations (and evidence_records if Spec 2 present) +
guarded migration. `StudentLensStore.import_observation_rows(rows) -> {imported, skipped}`:
validates each row against Observation fields, skips known UUIDs, tags `origin="imported"`,
recomputes aggregates once at the end (not per row). `remove_imported(student_id, teacher_id)`.

### Step 2 — Ledger export
In `sync_lens_to_drive()`: after the Markdown upload, serialize this teacher's observations
(+ evidence) for the student to NDJSON, upload as the ID-named ledger file (reuse
`upload_text_to_folder`, mime `application/x-ndjson`). Full-state overwrite each sync.
Ledger header row: `{"schema": "lv_ledger_v1", "teacher_id": ..., "student_id": ...,
"exported_at": ...}` — version the schema from day one.

### Step 3 — Pull + merge
`pull_shared_ledgers(student_id=None)` in drive_sync.py: list `*.ledger.ndjson` in the folder,
skip own teacher_id, download, validate header schema (unknown schema version → skip file,
log warning), feed rows to `import_observation_rows`. Endpoint
`POST /api/drive/pull-shared` returning `{files_seen, imported, skipped, errors}`.
Privacy events: `ledger_pulled`, `observations_imported` (counts + ids only).
Also wire into the existing sync cadence if one exists — find where `sync_lens_to_drive` is
scheduled/triggered (grep web.py for it) and mirror.

### Step 4 — Triangulation rendering
Extend the lens payload (the endpoint behind the student detail view) with per-entry
`author: {teacher_id, display}` and per-category `convergence`:
- `corroborated`: 2+ distinct teacher_ids with entries in the category
- `divergent`: opposing `cefr_direction` values (progressing vs regressing) from different
  teachers within 30 days — include both observation ids
- `single_source`: exactly one contributing teacher
Frontend: author badges (per the operator's display ruling), corroborated/divergent chips,
"Pull colleague updates" button, colleagues strip, "Remove this colleague's data" (confirm
dialog) → remove_imported.

### Step 5 — Tests (`tests/test_triangulation.py`)
Cover the spec's 8-point test plan. Critical ones:
- Double-import idempotence (counts identical)
- Self-ledger import → all skipped
- Divergence window: 29 days apart → flagged; 31 days → not
- remove_imported surgical (other colleagues' + local rows untouched)
- Unknown ledger schema version skipped cleanly
Use the existing drive test-double pattern found in Step 0 reading — do not invent a second
mocking approach.

### Step 6 — Verify
```bash
python3 -m pytest tests/test_triangulation.py tests/test_ui_contract.py -q
python3 -m src.lingua_viva.cli preflight
python3 -m pytest -q tests/
```
Manual (two-machine simulation): two LV_STUDENT_DB_PATH homes, same fake folder, push from A,
pull from B, verify attributed entries + convergence chips.

## Definition of Done

- [ ] Ledger push/pull round-trip works between two isolated DB homes
- [ ] Merge append-only, idempotent, provenance-true, reversible per colleague
- [ ] Convergence/divergence chips render; nothing auto-resolves
- [ ] Filenames ID-only; privacy events complete; no new egress surface
- [ ] Route reachability + UI contract updated, full suite green
