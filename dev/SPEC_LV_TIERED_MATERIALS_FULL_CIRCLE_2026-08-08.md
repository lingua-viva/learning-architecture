# SPEC — Tiered Materials Full Circle (Drive → Local Library → Tiers → Drive) — 2026-08-08

**Priority: P0 — must work this week.** Operator ruling 2026-08-08 + commitments from the
2026-08-06 Still I Rise sync (Olga needs teacher-simple; operator on the current output:
"it's very computer right now, but I'll make it more legible").

## Goal statement

Coursework lives in Drive by grade and subject. The teacher's mapped desktop pulls it down
into a **local course library** — a personal repo of lesson material referenced many times,
not re-downloaded per use. For a class of ~15, the roster is split **by lens** into the
three instructional tracks — **Foundational / On Track / Extended** — plus a fourth
**NEEDS INDIVIDUAL SUPPORT** group that is deliberately kept apart from the tiers. The
teacher picks **today's lesson plan** from the local library, the app agentically generates
the three tiers of work for that day, the teacher reviews a **readable, printable** packet
(not markdown code), approves, and the packet is **shared back to Drive** under the right
class/grade/subject folder.

## What already exists (build on it, do not rebuild)

| Piece | Where | State |
|---|---|---|
| Tier assignment | `src/lingua_viva/lesson_materials.py` `assign_tier_groups()` via `ContentDifferentiator` | WORKS, 3 tiers, no separate support group |
| Generation | `generate_lesson_materials(lesson, student_ids, teacher_id, push_to_drive)` → `TierMaterial` per tier | WORKS |
| Packet render | `render_printable_packet_markdown()` + `_validate_printable_packet()` | WORKS but output reads as raw Markdown — the legibility complaint |
| Privacy in generation | LLM prompt carries tier/CEFR/subject/topic only, never names/RTI/trauma flags; roster-name scan on output | WORKS — do not weaken |
| Drive download/upload | `google_drive_integration.py` (`list_folder_files`, `download_file_text`, `upload_text_to_folder`, `import_files`) | WORKS |
| Roster w/ tier inputs | `StudentLensStore.list_lenses_for_teacher()` (grade_level, CEFR, rti_current_tier, support_profile) | WORKS |

## The five gaps this spec closes

### G1 — Local course library (the personal repo)
- New: a persistent local library at the sanctioned data dir (`_data_dir()`-based —
  see Phase 0 of the lens-loop prompt; coordinate, don't duplicate), organized
  `library/<grade>/<subject>/<files>`, mirroring mapped Drive coursework folders.
- `pull_course_library(folder_id, grade, subject)`: download/refresh from Drive with a
  manifest (source file id, modified time, local path, sha) so re-pulls only fetch
  changed files. Bounded by existing H2 download caps.
- The library is **read-many**: generation reads local files only — no Drive round-trip
  at lesson time. Offline generation from an already-pulled library must work.
- Library browser in the UI: by grade/subject, showing freshness (local vs Drive
  modified time).

### G2 — Roster split: 3 tiers + NEEDS INDIVIDUAL SUPPORT, kept apart
- Extend `assign_tier_groups()`: before tiering, peel off students whose lens marks them
  as needing individual support (driver: `rti_current_tier == 3` and/or an explicit
  support-profile flag — builder confirms the exact field against `ContentDifferentiator`
  inputs and FLAGS the chosen rule in the report). They form the **INDIVIDUAL SUPPORT
  group** and are excluded from Foundational/On Track/Extended.
- Tier names in every surface are **Foundational / On Track / Extended** (the customer's
  vocabulary from the sync) — not tier1/2/3.
- The support group gets NO auto-generated tier work this week (that's the point of
  keeping them apart — their work is teacher-individual). The packet lists them by name
  in a teacher-only section so nobody silently falls out of the lesson.
- Assignments are teacher-overridable per student per day; overrides recorded.

### G3 — "Today's lesson" selection
- Teacher picks one file from the local library (browser from G1) as today's lesson plan
  for a class/grade/subject; recent picks surfaced first. The selected file's text feeds
  `generate_lesson_materials` as the `lesson` source. Persist the pick as part of the
  day's record (date, file, class) so the share-back (G5) and any re-generation are
  reproducible.

### G4 — Teacher-readable packet (the legibility fix)
- Keep `render_printable_packet_markdown()` as the canonical content model. Add a
  **rendered layer**: packet displayed in-app as formatted rich text (rendered HTML from
  the markdown — headings, real tables, checkboxes), and exported as (a) print-ready
  HTML with print CSS (page break per student handout, readable serif body, no visible
  `#`/`**`/`---`) and (b) the markdown for Docs-paste compatibility.
- Test the reading experience like a teacher: the acceptance standard is "Olga could
  hand this to a pilot teacher with zero explanation." No code fences, no raw markdown
  syntax, no JSON, no field names as labels (`instructions_for_student` → "Instructions").
- Approval flow stays: DRAFT → teacher review (rendered view) → APPROVED → eligible for
  share-back. `_validate_printable_packet()` keeps blocking placeholders.

### G5 — Share-back to Drive by class/grade/subject
- On approval, upload the packet (rendered HTML + markdown) to a mapped output folder
  per class/grade/subject (folder map shape shared with the lens-loop build's G3 —
  coordinate on the config schema, one shape, two consumers).
- Filename convention: `<date>_<grade>_<subject>_<lesson-title>_tiered_packet.*`.
- Egress gate: `assert_safe_for_external_output` before upload. Student names appear in
  the packet's distribution lists (tier rosters) — that is teacher-approved,
  organization-internal sharing per the sync; the INDIVIDUAL SUPPORT teacher-only
  section, however, is **stripped from the shared upload** (support status is sensitive)
  and kept in the local/teacher copy only.

## Non-goals (this week)
- Perplexity/live-web lesson enrichment (long-term vision, out). Rubric generator.
  Generating individualized work for the support group. Slack. Voice.

## Acceptance (operator's machine, real Drive, a real class of ~15)
1. Pull a grade/subject coursework folder → local library populated with manifest;
   second pull fetches only changed files; generation works offline from the library.
2. Roster of 15 splits into Foundational/On Track/Extended + INDIVIDUAL SUPPORT; the
   support group appears in no tier; override works and is recorded.
3. Pick today's lesson file → three tiers generated for that day/class.
4. Rendered packet contains zero raw markdown artifacts; print preview paginates per
   handout; the "Olga test" passes on visual inspection.
5. Approve → packet lands in the correct class/grade/subject Drive folder under the
   naming convention; support-group section absent from the uploaded copy (test).
6. Generation prompt still never contains student names/RTI/trauma flags (existing test
   extended to the new path).
7. Full regression suite green; shipped through auto-release; 7-step push verification.
