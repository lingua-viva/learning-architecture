# SPEC: File-Map Verification UI — Confirm Purpose, Opt-In Student-Zone Peek (LV-DATA-IN-2)

**Date**: 2026-07-22
**Status**: APPROVED — ready to build
**Author**: Claude (this session)
**Trigger**: Live walkthrough surfaced that File Map (Settings) shows aggregate counts
only — no way for a teacher to confirm which folders are for what, and no way to
opt specific student-data folders into the pipeline (they're excluded by design today).
**Scope**: `src/lingua_viva/filemap.py`, `src/web.py` (filemap routes), `static/index.html`
(Settings view)
**Risk level**: MEDIUM — this spec deliberately opens a privacy-sensitive door (opt-in
listing of filenames inside detected student-data zones). Read §3 before writing any code.
**Depends on**: Nothing structurally, but its OUTPUT is the input `SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md`'s `extract()` expects (a confirmed file list + target_schema_id) —
read that spec's §3 for the shape you're producing, even though you don't import
`data_in_contracts.py` directly in this spec.
**Sibling specs**: `SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md`, `SPEC_LV_UI_WIRING_FIXES_2026-07-22.md`

---

## 1. The Problem

`filemap.py` (SHIPPED, `SPEC_PHASE5_FILE_MAP`) already scans directories, infers a
domain (curriculum/assessment/cefr/resources/reference/planning) per folder, and
detects "student zones" — folders matching student-data keywords
(`is_student_data_zone()`, `STUDENT_DATA_KEYWORDS`) or privacy markers
(`PRIVACY_PATH_MARKERS`). Critically: **when the scanner hits a student zone, it does
NOT descend into it.** `_scan_directory()` filters student zones out of `dirs[:]`
before walking further (`filemap.py` lines 203-211) and only records the zone's path
in `student_zones` — never its contents. This is intentional, correct, privacy-first
behavior for a *background* scan.

But it means the file map today can tell a teacher "I found 3 folders that look like
they contain student data, and I stayed out of them" — and nothing more. There is no
path from "I found a student-data folder" to "here's what's inside it, tell me which
files are actually useful for building lenses." The teacher's own messy files (grade
books, observation notes, whatever format they happen to be in) never become visible
to the pipeline at all right now.

Separately, non-student domain folders (curriculum/reference/etc.) ARE listed with
paths — but nothing lets a teacher confirm "yes, use this folder for curriculum
ingestion" versus just seeing a count in a settings summary.

## 2. What To Build

### 2a. Confirm domain-tagged entries for a purpose

1. Extend `FileMap` (`filemap.py`) with a `confirmations: dict[str, str]` field —
   maps an entry path to a purpose (`"curriculum_source"` | `"ignore"`). Update
   `save_map`/`load_map`/`to_api` to round-trip it (owner-only file permissions,
   same as today — do not weaken that).
2. New route `POST /api/filemap/confirm` in `src/web.py`: payload
   `{"path": "...", "purpose": "curriculum_source" | "ignore"}`. Validates the path
   exists in the current map's entries, records the confirmation, saves, returns the
   updated map summary.
3. In Settings (`static/index.html`, the file-map panel), list domain-tagged entries
   (not just a count) with a "Use for curriculum" / "Ignore" action per entry. Show
   current confirmation state.

### 2b. Opt-in peek into a detected student zone

This is the part that needs care — read this twice before implementing.

1. New function in `filemap.py`: `list_files_in_zone(zone_path: str) -> list[dict]`.
   Given a path already present in `FileMap.student_zones`, list the **filenames,
   sizes, and mtimes only** of files directly under it (one level — do not
   recursively auto-expand into sub-folders; if there are sub-folders, list them as
   entries too, requiring their own explicit peek). **Never open or read file
   content.** This is the same "structural awareness without content access"
   guarantee `filemap.py`'s own module docstring already commits to — do not break
   it here.
2. New route `POST /api/filemap/peek` in `src/web.py`: payload `{"zone_path": "..."}`.
   Must verify `zone_path` is actually a member of the current `FileMap.student_zones`
   list before doing anything — reject any other path with 400. This prevents the
   route from becoming a general filesystem browser.
3. Frontend: in Settings, list detected student zones separately from domain entries,
   each with a "Show what's inside" button (explicit teacher click required — never
   auto-expand). On click, call `/api/filemap/peek`, show the returned filenames in a
   simple list (no content preview, filenames/sizes only, matching the backend
   guarantee).
4. For each file shown after a peek, add an "Assign to student" dropdown populated
   from the current roster (`GET /api/students`) plus a "new student" option. Record
   this as `{"file_path": ..., "assigned_student_id": ... | null, "assigned_purpose":
   "student_lens_source"}` — persist alongside `confirmations` (extend the same dict
   or add a parallel `student_assignments: list[dict]` field to `FileMap`, your
   choice, but it must round-trip through `save_map`/`load_map`/`to_api` like
   everything else).

**Do NOT build**: automatic student-name matching between filenames and roster
entries (e.g., guessing "marco_notes.docx" belongs to student "Marco"). That's
extraction-engine territory (Spec 5, not this spec) and risks a wrong guess feeling
authoritative. The teacher assigns manually here — full stop, no lift beyond one
dropdown click per file.

## 3. Privacy Discipline — Read Before Building

- `list_files_in_zone()` and `/api/filemap/peek` must NEVER read file content —
  filenames, sizes, mtimes only. This mirrors the existing guarantee in
  `filemap.py`'s module docstring ("It never opens or reads user files") — that
  guarantee must hold for zone-peek too, it just extends to *listing* zone contents,
  not reading them.
- The peek route must reject any path not already present in the confirmed
  `student_zones` list from a prior scan. A teacher opts a *zone* in during scanning
  (implicitly, by the zone being detected) and then opts *individual files within it*
  in explicitly, one at a time, via the assign-to-student action. There is no "peek
  anywhere on disk" capability here.
- None of this spec writes any file content anywhere — no extraction happens in this
  spec. The output of this spec is a confirmed, teacher-approved list of
  `(file_path, target_schema_id, hint)` tuples ready for Spec 5's `extract()` — that
  handoff shape should be retrievable via `to_api()` or a small new
  `get_confirmed_extraction_inputs()` helper, whichever fits the existing module
  better.

## 4. What Does NOT Change

- `_scan_directory()`'s behavior of not descending into student zones during a
  background scan — unchanged. The opt-in peek is a separate, explicit, one-zone-
  at-a-time action, never automatic.
- Domain inference logic (`infer_education_domain`, `infer_sensitivity`) — unchanged.
- Existing `/api/filemap/scan`, `/api/filemap/exclude`, `/api/filemap/clear` routes —
  unchanged, this spec only adds `/confirm` and `/peek`.

## 5. Build Order

1. `FileMap.confirmations` field + round-trip through save/load/to_api (20 min)
2. `POST /api/filemap/confirm` route (20 min)
3. `list_files_in_zone()` + zone-membership validation (30 min)
4. `POST /api/filemap/peek` route, with the reject-if-not-a-known-zone check (20 min)
5. Student-assignment persistence (`student_assignments` field + round-trip) (20 min)
6. Settings UI: domain-entry confirm actions (30 min)
7. Settings UI: student-zone list + peek button + per-file assign dropdown (45 min)
8. Live-verify: scan a real folder with a nested "students" subfolder, confirm the
   zone is detected-but-unlisted before peek, peek it, see filenames only, assign one
   to a student (30 min)

**Total**: ~3.5 hours

## 6. Definition of Done

- [ ] Domain-tagged entries can be confirmed as `curriculum_source` or `ignore` from
      the UI, persisted, visible on reload
- [ ] Student zones list separately from domain entries in the UI
- [ ] Peek is opt-in (explicit button), never automatic
- [ ] Peek route rejects any path not in the current `student_zones` list (test this —
      try calling it with an arbitrary path, confirm 400)
- [ ] Peek returns filenames/sizes/mtimes only — grep your own diff for any
      `.read()`/`open(..., 'r')` call on a peeked file and confirm there is none
- [ ] A peeked file can be assigned to a student (existing roster or flagged new),
      persisted, visible on reload
- [ ] `python3 -m pytest -q tests/` passes
- [ ] Live-verified against a real folder structure with a nested student-data
      subfolder, not just synthetic fixtures

## 7. Provenance

- `filemap.py` inspected and live-tested this session (`/api/filemap/scan` against
  real `~/Downloads`, 79 directories, correct domain hits, zero false student-zone
  hits on that particular folder — this spec's zone-peek path was NOT exercised in
  that test since Downloads had no detected student zones).
- Operator's stated goal: "we have information about the students... we need to take
  that messy data and create the lenses... just 'create lenses for all my students'
  and it's done" — this spec is the confirmed-input step that makes that possible
  without silently reading files a teacher never approved.
