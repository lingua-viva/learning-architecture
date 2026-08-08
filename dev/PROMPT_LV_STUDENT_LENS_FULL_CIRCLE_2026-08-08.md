# PROMPT — Build: Student Lens Full Circle — 2026-08-08

You are the implementing builder for `~/learning-architecture` (Lingua Viva). Read, in
order, before writing any code:

1. `dev/SPEC_LV_STUDENT_LENS_FULL_CIRCLE_2026-08-08.md` — your spec. It wins on scope.
2. `dev/SPEC_LENS_PRIMITIVE_2026-08-04.md` — the DOES boundary (what may leave the machine).
3. `dev/SPEC_T4_LENS_ENGINE_2026-08-04.md` — the lens scaffold you will reuse.
4. `AGENTS.md` — push discipline; "pushed" has a 7-step definition.

This is a **loop-closing build**: every major piece exists (`google_drive_integration.py`,
`drive_sync.py`, `student_lens.py`, `docpipe/lens.py`, `privacy.py`). You are wiring five
gaps (G1-G5), not building a system. If you find yourself writing a new Drive client or a
new lens store, stop — you are off the map.

## Phase 0 — release-seal class fix (do this FIRST, own commit)

QA found `sanitizer/app.py` writing `firewall_log.ndjson` INSIDE the signed bundle —
codesign fails. This is the THIRD instance of the `Path(__file__)` / `sys.frozen`
write-location anti-pattern. Per the standing failure-class rule: do not fix the instance.

- Create one `_data_dir()` (or reuse the existing runtime-dir helper if one exists —
  check `LV_STATE_HOME` / `~/.lingua-viva/runtime/` usage in `student_lens.py`) as the
  ONLY sanctioned write location.
- Migrate all three known instances to it; grep the whole repo for writes derived from
  `Path(__file__)`/`sys.frozen`/`sys._MEIPASS` and migrate any others you find.
- Add a test that fails if any module writes inside the app bundle/source tree at
  runtime (the class-locking test — this is the point of the phase).

Your G1-G5 work ships through the release chain; it does not ship if the seal is broken.

## Phase order for G1-G5

Build in this order — each phase independently commit-able and demo-able:
1. **G3 folder map** (category → folder_id, fifth "Personal" category, fail-closed
   routing) — smallest change, everything else exports through it.
2. **G2 observation → lens refresh** — closes the most visible teacher-facing seam.
3. **G5 nine keys + dropdown + inference** — schema + optional mapping.
4. **G1 batch class-folder ingest** — the biggest piece; lands on a working export path.
5. **G4 scheduled sync + sync ledger** — last, because it exercises everything above.

Plus the rename (parent summary → "Student Summaries") — trivial, its own commit.

## Rules that ride with this build

- **Privacy is the harness here.** `assert_safe_for_external_output` on every new egress
  call site, with a test per site. A personal-category item with no reachable personal
  folder is written NOWHERE — prove it with a test. No student data, real_anon files, or
  fixtures containing real names enter this PUBLIC repo.
- **Fail visible, never silent**: attribution guesses are labeled and correctable;
  unreachable folders queue with a surfaced reason; inference mistakes are teacher-fixable.
  Silent wrong is the failure mode that kills a teacher pilot.
- **Append-only stays append-only**: observations and evidence ledgers are never mutated;
  lens profiles are recomputed snapshots.
- Tests must run hermetically: set `LV_STATE_HOME`/`LV_STUDENT_DB_PATH` in fixtures —
  the ontology-hermeticity leak (pytest mutating CAND yamls) has reproduced FIVE times;
  do not become the sixth.
- Drive calls in tests are mocked at the `google_drive_integration` seam; one manual
  live-Drive checklist for the operator goes in your report.
- Hunk-isolate commits; another window may be working the tiered-materials pair in the
  same repo. Coordinate at the one shared seam: if you change `upload_text_to_folder`
  or the folder-map config shape, note it in your report for the other lane.
- UI contract: don't break existing panels; new UI = folder-map settings, UNATTRIBUTED
  review list, sync ledger, nine-keys section, key dropdown.
- If the manifesto definitions doc is not in the repo/config, implement against a
  definitions-file interface + the nine key names, and FLAG it — do not invent
  definitions.

## Report back (≤200 words + paths)

Commit SHAs per phase; acceptance checks 1-7 status (spec §Acceptance); the live-Drive
manual checklist for the operator; any spot where existing code contradicted the spec
(stop-and-flag, don't resolve); the shared-seam notes for the other lane; released
version + 7-step push verification result. Report file:
`dev/REPORT_LV_STUDENT_LENS_FULL_CIRCLE_<date>.md` + same-day line in `dev/INDEX.md`
if the repo keeps one.
