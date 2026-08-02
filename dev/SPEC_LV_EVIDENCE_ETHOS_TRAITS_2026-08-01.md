# SPEC: Evidence Attachment + Ethos Traits on Student Profiles

**Created**: 2026-08-01
**Status**: DRAFT — operator review before build
**Priority**: 2 of 5 — depends on Spec 1 (`SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES_2026-08-01.md`)
**Customer evidence** (ai-lingua-viva Slack):
> Teacher A: "I was wondering if we could build our 'ethos' into the canvas itself, specifically our characteristics and traits that we are developing throughout lessons and projects. It would also be really helpful if, at any point, we could have teacher feedback recorded into these on student profiles to use as evidence in students' reports." / "I think it would be a good idea to incorporate evidence of traits/characteristics too"
> Teacher B: "Please help us with the upload of student documents or evidence."

---

## Problem

Two connected asks, one data model:

1. **Documents as evidence.** Teachers have artifacts (work samples, prior reports, notes) in Drive/local folders. The Sources view can browse them (`GET /api/sources/records`, web.py:2285–2294) but there is no way to attach a source record *to a student* as evidence with provenance.
2. **Ethos traits as evidence.** The school develops named characteristics through lessons and wants teacher feedback recorded against them per student, retrievable when writing reports. The `ethos_profile` column already exists (student_lens.py:778) and `capture()` already returns ethos suggestions — but there's no school-defined trait list, no direct feedback path, and no report surfacing.

Both are the same shape: **an evidence record — a dated, teacher-attributed claim about a student, tied to a category or trait, with provenance.**

## Design

### 1. Evidence record model

New table `evidence_records` in the student lens DB (`StudentLensStore`):

```
evidence_id (UUID PK) | student_id (FK) | teacher_id | created_at
kind: "document" | "teacher_feedback" | "observation_ref"
target_type: "support_category" | "ethos_trait" | "strengths" | "background"
target_id: category_id | trait_id | "academic"|"personal" | null
summary (teacher-visible text)
source_ref (JSON: sources record id + type for documents; observation_id for refs; null for direct feedback)
confidence_level (reuse student_lens.py:85–90 levels)
```

Append-only: no update/delete of evidence rows (soft-delete flag only, matching students table `deleted` pattern). This is the report-defensibility property — evidence that can be silently edited isn't evidence.

### 2. Attach from Sources

- `POST /api/students/{student_id}/evidence` — body: `kind`, `target_type`, `target_id`, `summary`, optional `source_ref`
- For `kind=document`: `source_ref` must be a valid record from `/api/sources/records`; the file itself is NOT copied into the DB — provenance pointer only. Content stays where it lives (local folder / Drive import dir via `import_dir()` in google_drive_integration.py). Local-first promise intact.
- `GET /api/students/{student_id}/evidence?target_type=&target_id=` — grouped listing for lens panels
- Frontend: "Add as evidence" action in the Sources view (pick student + trait/category) and an "Evidence" tab in the student detail view

### 3. School ethos trait list (Tier 2 config)

Extend `school_profile.json` from Spec 1:

```json
{"ethos_traits": [
  {"id": "curiosity", "label": "Curiosity", "description": "..."},
  {"id": "collaboration", "label": "Collaboration", "description": "..."}
]}
```

- Loaded by `read_school_profile()` (Spec 1). Empty list = ethos UI hidden entirely — schools that haven't defined traits see nothing.
- `ethos_profile` on the student stores per-trait rollups: `{trait_id: {evidence_count, last_evidence_at, trajectory_note}}` recomputed when evidence is appended (same recompute-on-append pattern as CEFR/RTI aggregates).
- The existing ethos suggestions from `capture()` map into these trait IDs when labels match; non-matching suggestions surface as "unmapped" for the teacher.

### 4. Teacher feedback → report evidence

- Quick-capture: from the student's ethos panel, teacher types one line + picks trait → evidence record `kind=teacher_feedback`, `confidence_level=teacher_confirmed`
- Voice path (small, additive): observation branch of `/api/voice/act` — when `suggest_support_categories`/ethos matching fires on a trait word, include `ethos_suggestions` in the response for one-tap confirm. No new intent type; no auto-write.
- **Report surfacing**: `ParentReportGenerator.generate_draft()` (parent_report.py:133–194) gains an optional `include_evidence_summaries=True` path — per-trait evidence counts + teacher-confirmed summaries fed into the draft body. **Everything passes the existing gates unchanged**: trauma-safety check (parent_report.py:180–183), `_strip_parent_output()`, and `check_publication_safety()` (governance.py:374–430). Evidence summaries are teacher-authored text and therefore exactly the content class the name-scan gate exists for — the gate runs on the final assembled pack, so no new bypass surface is created.

## What NOT to Change

- `check_publication_safety()` and the parent-report gate order — evidence enters upstream of the gates, never after
- Sources endpoints' read-only nature — attaching evidence never moves/modifies source files
- `attribution_visible_to_parent=False` hard-lock (parent_report.py:220)

## Test Plan

1. Evidence CRUD: create for each kind/target; list grouped; append-only (no update route exists); soft-delete
2. Document evidence requires a resolvable sources record; bogus ref → 400
3. Ethos config: traits render; empty list hides UI; unmapped suggestion surfaced not dropped
4. Rollup recompute on evidence append (evidence_count, last_evidence_at)
5. Report draft with evidence summaries: student full name inserted into a summary → `check_publication_safety` flags it (`review_required=True`) — the critical regression test
6. Privacy log events on evidence create; hermetic via `_isolate` pattern

## Files

| File | Action |
|---|---|
| `src/education/student_lens.py` | MODIFY — evidence_records table, append/list/rollup methods |
| `src/web.py` | MODIFY — evidence endpoints, voice/act ethos_suggestions (additive) |
| `src/education/parent_report.py` | MODIFY — optional evidence summaries in draft |
| `src/lingua_viva/config.py` | MODIFY — ethos_traits in school profile |
| `static/index.html` | MODIFY — Evidence tab, ethos panel, "Add as evidence" in Sources |
| `tests/test_student_evidence.py` | CREATE |
| `contracts/ROUTE_REACHABILITY.yaml` | MODIFY — new endpoints |

## Safety Rules

1. Evidence is append-only; provenance pointers, never copied file contents in the DB
2. All parent-facing output still crosses the full existing gate chain — no shortcut path
3. Trait IDs from config are validated against `[a-z_]+`; labels are display-only
4. No evidence content ever leaves the machine except via the teacher-triggered existing export paths

## Definition of Done

- [ ] A teacher can attach a document from Sources to a student as evidence
- [ ] The school's ethos traits are configurable, and teacher feedback lands against them in one step
- [ ] Evidence appears grouped in the student lens and flows into report drafts behind the safety gates
- [ ] The name-in-evidence-summary regression test passes
- [ ] Full suite green, UI contract bumped, route reachability updated
