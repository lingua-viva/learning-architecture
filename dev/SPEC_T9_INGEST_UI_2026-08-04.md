# SPEC T9 — Students Ingest UI: file → extraction → lens scaffolds (2026-08-04)

**Status: implemented same-day (2026-08-04, T9 lane on the second machine).**

Sources: `dev/PROMPT_PAIR_T9_INGEST_UI_2026-08-04.md`, `dev/CONTRACTS_V1_2026-08-04.md`
(frozen), `dev/SPEC_T2_VAULT_2026-08-04.md`, `dev/SPEC_T4_LENS_ENGINE_2026-08-04.md`,
`dev/LV_BUILD_BRIEF_2026-08-04.md` §3 + §11, runbook.

**Dependency reality at build time:** T2 (vault) and T4 (lens engine) are landed and
verified locally. T1 (`drive.list_folder`/`fetch_file`) and T3
(`extract.extract_document`) are still the frozen T0 stubs on origin — their
signatures are contract-frozen, so T9 builds against the seam: every call site uses
the exact contract call, degrades honestly while the stub raises, and lights up with
zero T9 changes when T1/T3 land. Per the runbook, local-file ingest alone is the
accepted day-one fallback, and Drive must never block this lane.

## 1. Backend (src/web.py — the T9-owned ingest surface)

Three routes under one surface:

- **`POST /api/students/ingest`** — multipart upload (`file`) or JSON
  `{"drive_ref": "..."}`.
  1. Read bytes (cap 15 MB — 413 above), build a `docpipe.source.v1` SourceRecord
     (SRC-uuid, origin local|drive, sha256, mime from filename, owner =
     teacher identity when provisioned else "teacher:local"), `vault.put_source`.
  2. Register job (JOB-uuid) and run the chain as an asyncio background task:
     `extract.extract_document(source, content)` → `vault.put_extraction` →
     student identification → lens creation. UI never blocks.
  3. Drive path: `drive.fetch_file(drive_ref)` at the top of the same chain —
     honest job failure ("Drive ingest is not available yet…") while T1 is a stub.
  Response: `{"job_id", "source_id", "status": "queued"}` immediately.
- **`GET /api/students/ingest/{job_id}`** — job status:
  `{"status": queued|extracting|identifying|done|failed, "source_name",
  "students_created": [{student_id, display_name, fields_populated}],
  "needs_confirmation": [{display_name, confidence, reason}],
  "students_found": n, "error": honest reason or null, "warnings": []}`.
  Unknown job (post-restart): 404 with the honest note that re-import is safe
  because duplicate imports merge, never fork (T4 evidence dedupe).
- **`POST /api/students/ingest/confirm`** — `{"job_id", "display_name"}`:
  creates the lens for ONE surfaced low-confidence student after the teacher
  confirms. Required by the never-auto-create rule; part of the ingest surface.

**Student identification rules** (from `extraction.structure.students_detected`):
- confidence ≥ 0.7 AND a display_name → lens created automatically via
  `lens.create_from_extraction(..., student_store=StudentLensStore())` — the
  bridge makes the student appear in the existing roster immediately.
- confidence < 0.7 → surfaced in `needs_confirmation`; NEVER auto-created.
- No students detected → `done` with `students_found: 0` and honest copy;
  never seed demo students (empty-on-install rule).
- Duplicate re-import: `create_from_extraction` loads the existing lens and
  dedupes evidence by key — merge, never fork (T4 rule, verified by test).
- `student_id` for new students: reuse extraction's detected `student_id` if
  present, else derived stable id.

**Job state** is in-memory (module dict). Durable artifacts (source, extraction,
lenses) live in the vault, so a crash mid-job loses only the progress view —
the status route's 404 copy tells the teacher re-import is safe. T3's future
job-runner events can replace this without changing the routes.

## 2. Frontend (Students region of static/index.html — T9-owned)

Panel at the top of renderStudents (above Add Student):
- **"Import students from a file"**: file input + Import button. Zero manual
  field entry. Muted note that Drive folder import arrives with the Drive
  connector (no dead button while T1 is a stub).
- On submit: POST the file, then poll the job status every 2s while the view
  is mounted (poll handle cleared on re-render; polling only runs on the
  Students view). Status line: "Reading document… / Identifying students… /
  n student(s) added from <file> / failed: <honest reason>".
- Done: roster refreshes (`ensureStudents` + re-render) — created students
  appear with a "from <original_filename>" provenance line (evidence[] minimal
  surface). `needs_confirmation` entries render with a "This looks like
  <name> (low confidence) — Add student" button → confirm endpoint.
- Failure: plain message with the source-document name; the teacher's file is
  never silently dropped.
- Fresh install: Students tab renders the import affordance and an empty
  roster — no demo content.

## 3. Not in scope (brief §11)

Other tabs' ingestion (Daily/Plan/Prepare/Assess/Parents) — copies this pattern
later. Drive folder browsing UI (T1). Sync badges (T6). Full provenance UI.

## 4. Tests (tests/test_students_ingest.py)

The T3 seam is exercised with the T0 fixture extractions (the frozen contract
output shape) monkeypatched over `extract_document`; one test pins the honest
failure while the real stub raises NotImplementedError.
1. Full chain: upload fixture lesson-plan → job done → students created →
   vault validates via docpipe validator → lens evidence non-empty →
   StudentLensStore has the student (bridge worked).
2. Low-confidence student → needs_confirmation, no lens; confirm endpoint
   creates it.
3. Extraction stub (current reality) → job failed with honest reason; source
   persisted; no lens writes.
4. Re-import same fixture → no duplicate evidence (merge, never fork).
5. No students detected → done, students_found 0, honest copy.
6. Oversized upload → 413. Unknown job id → 404 with re-import-safe copy.
7. Frontend string asserts: import affordance present, no demo seeding,
   provenance line, polling wired.

UI contract: index.html + web.py protected → single bump at commit.
Route reachability: 3 new routes classified in ROUTE_REACHABILITY.yaml.

---
**Status 2026-08-04:** spec complete; implementation in the same session.
Commit: `students: file/drive ingest → extraction → lens scaffolds, one tab e2e (T9)`.
