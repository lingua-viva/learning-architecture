# Lingua Viva Student Lens JSON v2 Schema

**Date:** 2026-07-23  
**Status:** READY TO BUILD  
**Repo:** `/home/mical/learning-architecture`  
**Depends on:** existing `src/education/student_lens.py`, `src/lingua_viva/data_in_contracts.py`  
**Build order:** 1 of 5

## 1. Objective

Upgrade the student lens from the current CEFR/RTI/SEL snapshot into a school
support profile that can hold IEP-style evidence for differentiation and
intervention groups.

The schema must preserve the current local-first, append-only observation
contract. Existing local databases must keep working.

## 2. Current state

`StudentLensStore` currently stores:

- student identity/display metadata
- home languages
- learning differences
- trauma flag
- avoid-pairing social constraint
- RTI tier and tier history
- CEFR snapshot and 30-day trajectory
- SEL summary
- append-only observations

It does not yet store:

- school support categories
- needs by category
- strengths by category
- strategies that worked
- strategies that did not work
- explicit source/provenance references
- advanced/enrichment needs

## 3. Canonical categories

The v2 support profile must use exactly these canonical category IDs:

```python
SUPPORT_CATEGORY_IDS = (
    "learning_and_cognition",
    "communication_and_language",
    "executive_functioning",
    "social_skills",
    "emotional_regulation",
    "physical_sensory_needs",
    "attendance_and_engagement",
    "advanced_enrichment",
)
```

Display labels:

- Learning and Cognition
- Communication and Language
- Executive Functioning
- Social Skills
- Emotional Regulation
- Physical/Sensory Needs
- Attendance and Engagement
- Advanced Students / Enrichment

`advanced_enrichment` is additive. It is not a disability/support deficit
bucket; it captures extension, challenge, acceleration, and high-readiness
needs.

## 4. Lens JSON shape

Add one top-level JSON field to the exported lens:

```json
{
  "support_profile": {
    "schema_version": 2,
    "categories": {
      "learning_and_cognition": {
        "needs": [],
        "strengths": [],
        "strategies_worked": [],
        "strategies_not_worked": [],
        "evidence": [],
        "open_questions": []
      }
    },
    "last_reviewed_at": null,
    "last_reviewed_by": null
  }
}
```

Every category object has the same structure.

### Entry shape

`needs`, `strengths`, `strategies_worked`, `strategies_not_worked`, and
`open_questions` contain objects:

```json
{
  "id": "uuid",
  "text": "short teacher-readable statement",
  "created_at": "ISO-8601 UTC timestamp",
  "created_by": "teacher_id",
  "source_observation_id": "uuid or null",
  "source_ref_ids": [],
  "confidence": "teacher_confirmed | model_suggested | imported_verified | imported_needs_confirmation",
  "active": true
}
```

`evidence` contains objects:

```json
{
  "id": "uuid",
  "summary": "teacher-readable evidence summary",
  "evidence_type": "observation | slack | google_drive | local_file | report | teacher_note",
  "source_observation_id": "uuid or null",
  "source_ref_ids": [],
  "created_at": "ISO-8601 UTC timestamp",
  "created_by": "teacher_id"
}
```

## 5. Storage

Add a nullable/default JSON column to `students`:

```sql
support_profile TEXT NOT NULL DEFAULT '{}'
```

Migration must be additive and idempotent:

- new databases create the column
- existing databases get the column through `ALTER TABLE`
- empty `{}` is normalized to the full v2 default on read
- no existing field is removed or renamed

## 6. Validation rules

- Unknown category IDs are rejected.
- Entry text must be non-empty and capped at 2000 characters.
- Evidence summaries must be non-empty and capped at 2000 characters.
- `confidence` must be one of the declared values.
- `evidence_type` must be one of the declared values.
- `advanced_enrichment` entries must not be interpreted as intervention risk.
- Reads never crash if old DB rows contain `{}` or malformed JSON; they return
  the safe default profile plus a validation warning.

## 7. Public store methods

Add methods to `StudentLensStore`:

```python
def support_profile_default() -> dict: ...
def get_support_profile(student_id: str) -> dict: ...
def replace_support_profile(student_id: str, profile: dict, reviewed_by: str | None = None) -> dict: ...
def add_support_entry(
    student_id: str,
    category_id: str,
    bucket: str,
    text: str,
    created_by: str,
    source_observation_id: str | None = None,
    source_ref_ids: list[str] | None = None,
    confidence: str = "teacher_confirmed",
) -> dict: ...
```

Allowed buckets for `add_support_entry`:

- `needs`
- `strengths`
- `strategies_worked`
- `strategies_not_worked`
- `open_questions`

Evidence can be added through a separate helper:

```python
def add_support_evidence(...): ...
```

## 8. Backward compatibility

Existing callers of:

- `create_lens`
- `get_lens`
- `export_lens`
- `list_lenses`
- `get_lens_as_of`

must continue to work. `get_lens` and `export_lens` should include
`support_profile`, but tests that only assert existing fields should not break.

## 9. Tests

Add or update tests for:

- new lens default contains all 8 categories
- existing DB without `support_profile` migrates cleanly
- malformed support JSON degrades to default
- adding a need increments `profile_version`
- adding worked/not-worked strategies lands in the correct bucket
- unknown category is rejected
- `advanced_enrichment` is present and independent from RTI tier
- schema conformance test includes `support_profile`

## 10. Acceptance criteria

- Full test suite passes.
- Existing local `student_lenses.db` files open without manual migration.
- Exported student lens JSON has `support_profile.schema_version == 2`.
- Every category has identical buckets.
- No student data leaves local SQLite.

