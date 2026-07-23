# Codex Execution Prompt: LV File-Map Verification UI (Confirm + Opt-In Student-Zone Peek)

Copy everything below into a fresh Codex session. Working directory:
`~/learning-architecture` (or wherever your local clone of
`lingua-viva/learning-architecture` lives).

---

```markdown
You're working in the Lingua Viva repo, extending the existing file-map feature
(`src/lingua_viva/filemap.py`, SHIPPED) with a verification/confirmation layer. This
task has a genuine privacy-sensitive component — read the spec's §3 carefully before
writing any code, and re-read it again before you touch anything related to student
zones.

The product bar: a teacher can see exactly which folders the file map found, confirm
which ones are curriculum sources, and — only via an explicit click, never
automatically — look inside a detected student-data folder to see filenames (never
content) and assign specific files to specific students.

The output is not a chat summary. The output is working code, verified live against
a real folder structure (not just synthetic fixtures), and a short report.

## Execution Contract

Work in this order:

1. Read the required files.
2. Read `dev/specs/SPEC_LV_FILEMAP_VERIFICATION_UI_2026-07-22.md` in full. This is
   your spec — do not deviate from its scope, and do NOT build the "automatic
   student-name matching" capability it explicitly excludes (§2b, "Do NOT build").
3. Build §2a (confirm domain entries), verify it live.
4. Build §2b (opt-in zone peek + student assignment), verify it live — this is the
   part with the privacy discipline in §3. Before marking it done, explicitly check:
   does your peek implementation read any file content anywhere? Grep your own diff.
5. Run the full verification checklist.
6. Update `dev/INDEX.md`.
7. Give the final response under 120 words.

Do not build §2b before §2a compiles and is verified — §2a is simpler and lets you
confirm the `FileMap` persistence round-trip works before adding the more sensitive
peek path on top of it.

## Required Reading (in order)

1. `CLAUDE.md` — repo architecture, privacy rules (§ "Privacy first" applies directly
   to this task)
2. `dev/INDEX.md` — current spec status
3. `dev/specs/SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` — read for context on what
   downstream Tier-2 specs expect this spec's output to look like (a confirmed file
   list + target_schema_id). You do not import `data_in_contracts.py` in this spec.
4. `dev/specs/SPEC_LV_FILEMAP_VERIFICATION_UI_2026-07-22.md` — YOUR SPEC, full detail
5. `src/lingua_viva/filemap.py` — the existing scanner you're extending. Read
   `_scan_directory()` (lines 176-252) closely — understand exactly why/how it skips
   descending into student zones (lines 203-211) before you write the opt-in peek
   function that deliberately does what the background scan deliberately doesn't.
6. `src/web.py` — the existing `/api/filemap/*` routes (search for `filemap` in the
   file) — match their existing error-handling and response-shape conventions.
7. `static/index.html` — lines ~1050-1174, the existing Settings file-map panel
   you're extending.

## Why You Specifically

This task requires precise adherence to a stated privacy boundary (never read file
content, reject peek calls against unconfirmed zones, no automatic student-file
matching) while still shipping real, working UI. It's a "follow the rule exactly,
don't improvise around it for convenience" task more than an open design problem —
the spec already made the design decisions; your job is faithful, careful execution
and to flag it clearly if you find yourself tempted to bend one of the §3 rules for
expediency.

## What To Build

Full detail in the spec (§2a/§2b) — do not re-derive it here, read the spec. Summary:

1. `FileMap.confirmations` field (path → "curriculum_source"|"ignore"), round-tripped
   through save/load/to_api. `POST /api/filemap/confirm` route. Settings UI to set it
   per domain entry.
2. `list_files_in_zone(zone_path)` — filenames/sizes/mtimes only, one level, never
   recursive-auto-expand, never reads content. `POST /api/filemap/peek` — must 400 on
   any path not already in `FileMap.student_zones`. `FileMap.student_assignments`
   (or similar) persisting file→student links. Settings UI: student zones listed
   separately, explicit "Show what's inside" button, per-file "Assign to student"
   dropdown (existing roster via `GET /api/students`, plus "new student").

## Hard Rules

- Never read file content in `list_files_in_zone()` or anywhere in this spec's code
  — filenames/sizes/mtimes only. This is checked explicitly in Definition of Done —
  do not skip that self-check.
- `/api/filemap/peek` must reject (400) any `zone_path` not already present in the
  current map's `student_zones` list. Write a test for this specifically.
- Do not build automatic filename-to-student matching/guessing — manual assign only.
- Do not touch `_scan_directory()`'s existing behavior of skipping student zones
  during a background scan.
- Do not commit — leave everything staged for operator.
- No real student data, institution names, or private school documents anywhere,
  including in test fixtures — use synthetic names.

## Verification Before Closing

```bash
python3 -m pytest -q tests/
python3 -m py_compile src/web.py src/lingua_viva/filemap.py
# Live check: scan a real folder tree with a nested "students" or similar subfolder,
# confirm it shows as a detected-but-unlisted zone, peek it, confirm only
# filenames/sizes appear, assign one file to a student, reload Settings, confirm it
# persisted.
# Adversarial check: call POST /api/filemap/peek with a zone_path NOT in
# student_zones — confirm you get a 400, not a file listing.
```

## Deliverables

1. Working code for §2a and §2b.
2. `dev/reports/REPORT_LV_FILEMAP_VERIFICATION_UI_2026-07-22.md` — cover both parts,
   include the adversarial peek-rejection test result explicitly.
3. `dev/INDEX.md` updated.

## Final Response

Under 120 words. Include only:
- status of §2a and §2b (done / partial / blocked, with why)
- confirmation that the content-never-read and zone-membership-reject checks passed
- report path
- test result

Do not restate the whole task.
```
