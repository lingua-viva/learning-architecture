# T4 Lens Engine Spec
**Status:** FROZEN 2026-08-04 for `src/lingua_viva/docpipe/lens.py`.
**Alias:** The prompt text also refers to `dev/SPEC_T4_LENS_2026-08-04.md`; this file is the operator-named lens-engine spec.

## Purpose

Observe is not a blank page. The document pipeline creates a student lens scaffold from ingested documents first, then teacher observations update that scaffold. The vault lens is the document-pipeline source of truth; the existing `StudentLensStore` is populated through an adapter so the current UI can render the same information.

## Frozen Profile Fields

The vault lens uses Christi's 10 fields:

- `learning_and_cognition`
- `communication_and_language`
- `executive_functioning`
- `social_skills`
- `emotional_regulation`
- `physical_sensory_needs`
- `attendance_and_engagement`
- `strategies_trialed`
- `academic_strengths`
- `personal_strengths`

The first seven reuse the existing `support_category` IDs. `strategies_trialed`, `academic_strengths`, and `personal_strengths` bridge to existing strategy/strength store methods.

## `create_from_extraction`

`create_from_extraction(extraction, student_id, student_name, added_by, root=None, student_store=None)` creates or updates a vault lens, then writes through `vault.put_lens`.

Mapping rules:

- Only spans that explicitly belong to the selected student are eligible. Eligibility comes from `structure.students_detected[].span_ids` for that `student_id` or exact display-name mention.
- A category is populated only when a matching span exists. Missing evidence means the field stays empty.
- The engine is deterministic and conservative; it does not call a model.
- Heuristics are only for placing existing source text into Christi's fields:
  - communication/language terms (`quotation`, `explains`, `vocabulary`, `sentence`, `language`, `Italian`) -> `communication_and_language`
  - organization/task-initiation terms (`checklist`, `organize`, `topic sentence`, `before writing`) -> `executive_functioning`
  - strength/extension terms (`strong`, `careful`, `extend`, `can extend`) -> `academic_strengths`
  - strategy terms (`strategy`, `benefits from`, `helped`) -> `strategies_trialed`
- The value is a teacher-readable statement derived from the source span, never a fabricated summary beyond light normalization.
- Evidence is DOCUMENT provenance with `source_ref.type = DOCUMENT`, `source_id`, `path`, `span_id`, confidence, `added_at`, and `added_by`.

Multiple source documents merge into the existing vault lens by appending values and evidence. Existing evidence is never destroyed. Contradictory document statements are retained side by side for UI resolution.

## `merge_observation`

`merge_observation(lens, observation, added_by, root=None, student_store=None)` folds a teacher observation into an existing vault lens, then writes through `vault.put_lens`.

Rules:

- Each `observation.claims[]` item targets one frozen field.
- OBSERVATION evidence uses `source_ref.type = OBSERVATION` plus `obs_id`.
- Merges are additive: previous values and evidence stay in place.
- If an observation contradicts document-derived content, retain both with provenance. Teacher-authored observation evidence outranks model/document-derived suggestions in the UI, but it does not erase them.
- Reversibility is by provenance: every merge adds a `metadata.merge_events[]` record with the observation/source identifier, affected fields, and timestamp. A future revert can remove all evidence and values linked to a specific event or `obs_id`.

## Evidence Invariant

No field may be populated without evidence. The lens engine asserts this before every vault write. Empty values must have empty evidence.

## StudentLensStore Bridge

The vault lens is authoritative. The existing SQLite `StudentLensStore` is updated by adapter functions so current endpoints and UI continue rendering:

- If the student does not exist in `StudentLensStore`, create it with the same `student_id` and `display_name`.
- Frozen support categories map to `add_support_entry(... bucket="evidence", confidence="imported_verified")` for document evidence, or `teacher_confirmed` for observation evidence.
- `strategies_trialed` maps to `strategies_worked`, `strategies_not_worked`, or `open_questions` based on outcome.
- `academic_strengths` and `personal_strengths` map to `add_profile_strength`.
- Source references are passed as `source_ref_ids` where available. Observation provenance is passed as `source_observation_id`.

The bridge is idempotent at the adapter level: it marks synced evidence IDs in `lens.metadata.student_store_sync.synced_evidence_keys` so repeated calls do not fan out duplicate SQLite entries.

## T3 Availability

`dev/SPEC_T3_EXTRACTION_2026-08-04.md` was not present at implementation time. This spec relies on the frozen T0 extraction schema and T0 fixtures.
