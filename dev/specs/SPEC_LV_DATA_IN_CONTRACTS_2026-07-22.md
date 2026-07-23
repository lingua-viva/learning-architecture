# SPEC: Data-In Contracts — File Map → Extract → Verify → Artifact (LV-DATA-IN-0)

**Date**: 2026-07-22
**Status**: APPROVED — contracts frozen, ready for Tier 2 implementation
**Author**: Claude (this session), grounded in operator's existing backend design
**Trigger**: Operator has been building the backend pieces (filemap.py, student_lens.py)
ahead of the UI; this is the first live app walkthrough, so it's time to freeze how the
pieces connect before parallelizing the build across multiple agent windows.
**Scope**: Interface/contract definitions only. No pipeline logic. Implemented in
`src/lingua_viva/data_in_contracts.py`.
**Risk level**: LOW — pure additive module, nothing existing imports it yet.
**Blocks**: Spec 5 (Extract+Fill+Verify Engine), Spec 6 (Student Lens writer),
Spec 7 (Curriculum Unit writer). Does NOT block Specs 1-4 (UI wiring, file-map
verification UI, voice, readable-lens renderer) — those have no dependency on this spec.

---

## 1. The Problem

The operator has been building "data in" backend pieces (file mapping, student lens
storage) without a working UI to build *against* — this is the first session actually
walking the live app. Before splitting the remaining work across parallel agent windows
(Codex/Claude/Kiro), the shared interfaces between pipeline stages need to be frozen once,
centrally, so independent windows don't each invent incompatible shapes and require a
rebuild to reconcile them.

## 2. What Already Exists (do not rebuild)

| Piece | File | Status |
|---|---|---|
| Structural file scanner (domain inference, student-zone exclusion, sensitivity) | `src/lingua_viva/filemap.py` | SHIPPED (`SPEC_PHASE5_FILE_MAP`) — never reads file content, path/domain/size only |
| File-map API | `src/web.py` `/api/filemap/*` | SHIPPED, live-tested this session (scanned real Downloads folder, 79 dirs, correct domain hits) |
| File-map Settings UI | `static/index.html:1050-1174` | SHIPPED — exists, just needs a per-purpose confirmation step (Spec 2) |
| Student lens storage (SQLite, append-only observations, RTI rules A-E, CEFR trajectory) | `src/education/student_lens.py` | SHIPPED — `create_lens`, `append_observation`, `get_lens`, `export_lens`, RTI escalation |
| Curriculum matrix reader | `src/lingua_viva/curriculum.py` | SHIPPED, but `_all_units()` **fabricates** unit titles from a hardcoded `_starter_themes()` dict when the matrix has no explicit `units` list — this is placeholder data, not real curriculum content |
| Assessment/rubric generator | `src/education/assessment_generator.py`, `content_differentiator.py` | SHIPPED, consumes a `LessonInput`/unit dict — already works, just needs real unit data instead of fixture themes |

**Conclusion**: the missing piece is not storage, not UI framing, not the assessment
generator — it's the pipeline that turns files on a teacher's disk into verified values
in the schemas these stores already expect.

## 3. The Pipeline Contract

```
[File Map]  →  [Verify/Select — Spec 2]  →  [Extract+Fill+Verify — Spec 5]  →  [Writer: Spec 6 | Spec 7]
  (done)          per-purpose confirm            ONE reusable engine              per target schema
```

`extract()` and `ExtractionResult` (full contract in `data_in_contracts.py`):

- Takes an already-confirmed file list (Spec 2's job, not the engine's) + a
  `target_schema_id`.
- Returns every candidate field with a `status`: `verified` (grounded in a cited
  chunk, safe to auto-write), `needs_confirmation` (plausible but ambiguous — e.g.
  which grade a document belongs to — surfaced to the teacher, never auto-written),
  or `unsupported` (verification pass found no grounding — dropped, logged as an
  `unresolved_question` instead of silently discarded).
- **Extraction and verification are one engine, not two specs.** The extraction
  prompt targets the schema directly; the verification pass checks the same output
  against its cited source chunks. Splitting these into separate specs risks exactly
  the "doesn't fit together" failure the operator flagged.
- Artifact writers (Spec 6, Spec 7) consume `result.verified_only()` **only**. Nothing
  downstream ever writes a `needs_confirmation` or `unsupported` field automatically.

## 4. Target Schema 1 — Student Lens

Not a new schema — restates `StudentLensStore.create_lens()`'s existing argument set
as an extraction target (`STUDENT_LENS_FIELDS` in the contracts module), so Spec 5 and
Spec 6 agree on field names without importing each other.

**Hard rule**: `trauma_flag` must always resolve to `needs_confirmation`, never
`verified`, regardless of how clearly a source document states it. This is the one
field in the schema where a wrong auto-write has real safety consequences — a teacher
must always be the one to confirm it, mirroring the existing `avoid_pairing_with`
pattern (`student_lens.py` line ~279: teacher-set, not observation-derived).

## 5. Target Schema 2 — Curriculum Unit (NEW)

Does not exist as a store yet — Spec 7 builds it. Deliberately **separate from**
`curriculum/lingua_viva_matrix.yaml`, which Doctor governs as `non_authoritative` and
explicitly forbids promoting (`doctor/support_loop/doctor.py::check_matrix_authority`).
Teacher-ingested units must never write into that file — they get their own per-teacher
store (SQLite, same pattern as `student_lenses.db`), carrying a `source_status` field
(`teacher_ingested_unverified` / `teacher_ingested_confirmed`) so it's always legible
where a unit's content actually came from.

Field shape mirrors `curriculum.py`'s existing unit dict (`unit_id`, `grade`, `title`,
`focus`, `cefr_target`, `materials`) so Plan/Prepare/Assess consume real ingested units
through the **same code path** they already use for the fixture ones — only the data
source changes, not the consuming code.

**Rubric does not need its own target schema.** `assess_rubric()` (`src/web.py:719`)
already consumes the same unit dict shape via `LessonInput` — once Curriculum Unit
ingestion is real, Assess improves automatically. Do not build a third schema for it.

## 6. What Is Explicitly Deferred (not in scope for this spec or Tier 2)

- The ambiguity-resolution chat ("is this 3rd or 4th grade?") — `needs_confirmation`
  fields are surfaced as a flat review list for now, not a conversational
  clarification loop. That requires the semantic engine work already deferred to the
  next session (2 weeks out, per operator).
- Rubric as an independent ingestion target (see §5).
- Any change to `curriculum/lingua_viva_matrix.yaml`'s authority status.

## 7. Build Order

1. This spec + `src/lingua_viva/data_in_contracts.py` — DONE, this session.
2. Update `dev/INDEX.md` — DONE, this session.
3. Tier 2 windows (Spec 5, 6, 7) import from `data_in_contracts.py` and implement
   against the `raise NotImplementedError(...)` stubs. Do not redefine
   `ExtractionResult`/`ExtractedField`/`SourceChunk` locally in any Tier 2 spec.

## 8. Definition of Done

- [x] `data_in_contracts.py` exists, imports cleanly, no existing code broken (additive only)
- [x] Both target schemas documented with field lists
- [x] `trauma_flag` hard-rule stated explicitly
- [x] Curriculum Unit's separation from the non-authoritative matrix stated explicitly
- [x] Rubric explicitly folded into Curriculum Unit, not a third schema
- [x] `dev/INDEX.md` updated

## 9. Provenance

- Grounded in live inspection this session: `filemap.py` (both MC's and LV's ported
  version), `student_lens.py`, `curriculum.py`, `assess_rubric()`, Doctor's
  `check_matrix_authority`, and the live `/api/filemap/scan` test against
  `~/Downloads` (79 directories, correct domain hits, zero false student-zone matches).
- Operator's own capability decomposition ("map files, extract data, fill in JSON
  structure, verify against hallucination, create artifact") — this spec merges
  "extract/fill/verify" into one engine per §3, keeps "map files" and "create artifact"
  separate per the operator's original split.
