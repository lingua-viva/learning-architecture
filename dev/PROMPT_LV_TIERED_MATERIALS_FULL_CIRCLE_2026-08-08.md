# PROMPT — Build: Tiered Materials Full Circle — 2026-08-08

You are the implementing builder for `~/learning-architecture` (Lingua Viva). Read, in
order, before writing any code:

1. `dev/SPEC_LV_TIERED_MATERIALS_FULL_CIRCLE_2026-08-08.md` — your spec. It wins on scope.
2. `dev/SPEC_LV_LESSON_MATERIALS_2026-08-01.md` — the existing tier-generation design you
   are extending.
3. `AGENTS.md` — push discipline; "pushed" has a 7-step definition.

This is a **loop-closing build**. `lesson_materials.py` already assigns tiers and
generates `TierMaterial`s; `google_drive_integration.py` already moves files both ways;
the lens store already carries CEFR/RTI per student. You are closing five gaps (G1-G5):
local library, the fourth kept-apart group, today's-lesson selection, readable rendering,
and routed share-back. If you find yourself rewriting the generator or the Drive client,
stop — you are off the map.

## Phase order

Each phase independently commit-able and demo-able:
1. **G2 roster split** — pure logic + tests, no I/O; unblocks everything visible.
   Confirm the individual-support driver field against `ContentDifferentiator` inputs
   before coding; FLAG your chosen rule in the report rather than inventing policy.
2. **G4 readable packet** — rendered HTML view + print CSS over the existing markdown
   model. This is the customer-visible legibility promise; do it early so the operator
   can eyeball it mid-week.
3. **G1 local course library** — pull + manifest + browser; generation reads local only.
4. **G3 today's-lesson selection** — picker + persisted day record.
5. **G5 share-back** — routed upload, naming convention, support-section stripping.

## Rules that ride with this build

- **Phase 0 dependency**: the `_data_dir()` release-seal class fix is Phase 0 of the
  lens-loop prompt (`dev/PROMPT_LV_STUDENT_LENS_FULL_CIRCLE_2026-08-08.md`). If that lane
  has not landed it when you start, land it yourself FIRST (same instructions, one
  commit) and say so in your report — the library (G1) must live in the sanctioned data
  dir, and nothing ships through a broken codesign seal. Do not build it twice: check
  `git log` for it before writing it.
- **Privacy is the harness.** The generation prompt never contains student names, RTI
  tiers, or trauma flags — the existing guarantee extends to every new call path, with
  tests. The INDIVIDUAL SUPPORT section is stripped from the uploaded packet copy —
  prove with a test. `assert_safe_for_external_output` on the upload path. No student
  data or real-name fixtures enter this PUBLIC repo.
- **Customer vocabulary everywhere**: Foundational / On Track / Extended. Rendered
  surfaces show human labels, never field names or markdown syntax. Acceptance standard
  for G4 is the "Olga test": a pilot teacher could use the packet with zero explanation.
- Tests hermetic: `LV_STATE_HOME`/`LV_STUDENT_DB_PATH` set in fixtures (hermeticity leak
  has reproduced five times — don't be the sixth). Drive mocked at the
  `google_drive_integration` seam; manual live-Drive checklist goes to the operator.
- **Shared-seam coordination**: the lens-loop lane (same repo, possibly same week) also
  touches the category→folder-id config (its G3) and `upload_text_to_folder`. One config
  shape, two consumers — if the other lane defined it first, adopt theirs; if you define
  it first, keep it minimal `{key → folder_id}` and note the shape in your report.
  Hunk-isolate all commits; never stash without popping.
- Keep `render_printable_packet_markdown()` as the single content model — the HTML layer
  renders it; it does not fork it. `_validate_printable_packet()` keeps gating.
- Fail visible, never silent: stale library files show freshness; failed uploads queue
  with surfaced reasons; overrides are recorded.

## Report back (≤200 words + paths)

Commit SHAs per phase; acceptance checks 1-7 status (spec §Acceptance); the
individual-support driver rule you chose and why; the folder-map config shape note for
the other lane; screenshots or file paths for a rendered packet (the Olga test);
live-Drive manual checklist; released version + 7-step push verification. Report file:
`dev/REPORT_LV_TIERED_MATERIALS_FULL_CIRCLE_<date>.md` + same-day line in `dev/INDEX.md`
if the repo keeps one.
