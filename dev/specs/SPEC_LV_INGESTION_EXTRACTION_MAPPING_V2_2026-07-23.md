# Lingua Viva Ingestion and Extraction Mapping v2

**Date:** 2026-07-23  
**Status:** READY TO BUILD  
**Repo:** `/home/mical/learning-architecture`  
**Depends on:** student lens v2 schema, observation write path, lens UI/API contract, Google Drive connector  
**Build order:** 5 of 5  
**Lens applied:** Gagné Learning Engineering + built-not-mounted root-cause discipline  
**Route:** local only, `MC_AGENT=1` for build/validation commands

## 1. Objective

Map information from local files, Google Drive imports, and teacher-created
local notes into the student lens v2 support profile with provenance,
confidence, teacher review, and a real app path.

This spec owns the "data in" semantics. Slack and Google Drive are transport
surfaces; this spec defines how imported/local file content becomes structured
student-lens data.

This build is not complete when extraction tests pass. It is complete only when
a teacher can use the real served Lingua Viva app to:

- select a local/imported file
- run extraction
- review extracted fields with source references
- confirm or reject ambiguous fields
- write confirmed fields into a student lens
- read the updated lens back in the Students view

## 1.5 Execution Protocol

Build under the same governed agent context used for the prior production
passes:

1. Read `/home/mical/fde/mission-canvas/AGENTS.md`.
2. Read this repo's `CLAUDE.md` and `AGENTS.md`.
3. For any live Mission Canvas shell/pipeline/classification command used
   during implementation or validation, run:

   ```bash
   export MC_AGENT=1
   ```

4. MC shell discipline is build governance only. Do not make Mission Canvas
   runtime the default Lingua Viva runtime.
5. No raw student file content may be sent to an external model. Extraction,
   verification, and review are local-first.

## 2. Teacher Learning Scope

Use Gagné's events as light scaffolding for teacher review, not as a separate
training platform.

First-build learning objectives:

| ID | Objective | Evidence in app |
|---|---|---|
| IO-1 | Identify which imported fields need teacher review | Review queue separates verified, needs confirmation, and unresolved fields |
| IO-2 | Distinguish verified fields from ambiguous fields | Confidence indicators and review tips are visible beside every extracted field |
| IO-3 | Resolve ambiguous extraction results without losing provenance | Confirm/reject controls preserve `source_ref_ids` |
| IO-4 | Maintain source provenance across imported data | Written support-profile entries cite source chunks |

Do not claim numerical review accuracy, speed, teacher competency improvement,
or school-wide consensus until pilot data exists.

Deferred beyond this spec:

- separate teacher competency database
- practice/calibration mode
- peer consensus comparison
- badges or unlock levels
- school-wide import-pattern analytics

## 3. Current State

`src/lingua_viva/extraction_engine.py` extracts a minimal `student_lens` target:

- display name
- campus
- grade level
- home languages
- learning differences
- trauma flag, never auto-verified
- CEFR snapshot fields

It does not fully provide a production path for:

- support category needs
- strengths
- worked/not-worked strategies
- category evidence
- advanced/enrichment indicators
- teacher review of ambiguous support-profile fields
- writing confirmed extracted fields into `StudentLensStore`
- UI reachability through the served app

The root-cause document already identified this failure class: eval-green
extraction code can still be unusable if the teacher cannot trigger it from the
app.

## 4. UI Reachability Contract

Mount this workflow in the existing app. Do not build a backend-only extraction
engine.

Preferred location: **Settings** under the existing file-map/Google Drive
import area, with reviewed results linking back to **Students**.

Required visible controls:

- **Extraction Sources** section listing confirmed local/Drive import files
- **Run Extraction** button for a selected file
- **Review Extraction** panel/modal
- confidence indicators:
  - `imported_verified`
  - `imported_needs_confirmation`
  - `unresolved`
- source-reference links or expandable source snippets
- category definition/guidance text for extracted support fields
- **Confirm** and **Reject** controls for each `needs_confirmation` field
- **Write Confirmed to Lens** button
- result area showing student ID, written fields, review-required fields, and
  unresolved questions

Required UI call sites:

- list extraction candidates from existing file-map/Drive-import state
- call extraction route for a selected file
- call review/write route for confirmed fields
- refresh or link to `GET /api/students/{student_id}/lens` after write

No extraction route may be considered shipped unless it has a call site in
`static/index.html` and is listed in Section 11.

Backend-only extraction route count for this build: **0**.

## 5. Target Schema Fields

Extend `STUDENT_LENS_FIELDS` to include support-profile paths for every
canonical category:

```python
"support_profile.categories.learning_and_cognition.needs",
"support_profile.categories.learning_and_cognition.strengths",
"support_profile.categories.learning_and_cognition.strategies_worked",
"support_profile.categories.learning_and_cognition.strategies_not_worked",
"support_profile.categories.learning_and_cognition.evidence",
"support_profile.categories.learning_and_cognition.open_questions",
...
```

Repeat for all eight support categories:

- `learning_and_cognition`
- `communication_and_language`
- `executive_functioning`
- `social_skills`
- `emotional_regulation`
- `physical_sensory_needs`
- `attendance_and_engagement`
- `advanced_enrichment`

Implementation may generate these paths from `SUPPORT_CATEGORY_IDS`, but tests
must assert that every category and bucket is present.

## 6. Extraction Prompt Behavior

The student extraction prompt must tell the local model:

- extract only facts explicitly supported by the source text
- do not diagnose
- do not infer disability, trauma, or protected characteristics
- classify educational observations into the support categories only when
  explicit
- separate needs from strengths
- separate strategies from needs
- only mark a strategy as worked/did-not-worked when the source says outcome
- preserve language and setting context when present
- put challenge/extension/high-readiness evidence under `advanced_enrichment`
- omit uncertain fields

The prompt output must include enough structured metadata for a teacher review
UI:

```json
{
  "field_path": "support_profile.categories.executive_functioning.needs",
  "value": "Needs a visual checklist for multi-step work.",
  "source_ref_ids": ["file.pdf#chunk-0003"],
  "confidence": "imported_verified | imported_needs_confirmation",
  "review_tip": "Check whether the source describes task sequencing or language access.",
  "category_id": "executive_functioning"
}
```

## 7. Verification Rules

Keep the extract-fill-verify invariant:

- A field can only become `verified` if grounded in cited chunks and confirmed
  by verification.
- Ambiguous fields become `needs_confirmation`.
- Unsupported fields are dropped into unresolved questions.
- `trauma_flag` remains never auto-verified.

Add:

- Any category-level need/strategy derived from vague behavior language should
  be `needs_confirmation`, not verified, unless the source directly names the
  need/strategy.
- Strategy outcome requires explicit success/failure language.
- `advanced_enrichment` can verify from direct language such as "advanced",
  "needs challenge", "extension work", "ready for acceleration", or equivalent
  clear source wording.
- Every support-profile field must carry source refs before it can be written.
- Teacher-confirmed ambiguous fields are written with
  `imported_needs_confirmation`, not silently upgraded to `imported_verified`.

## 8. Teacher Guidance and Feedback

For each extraction result, show:

- confidence badge
- category label and definition
- one-sentence review tip
- source reference
- exact source snippet or a bounded excerpt around the cited chunk
- whether the field will write automatically, needs confirmation, or is
  unresolved

Feedback after teacher review:

```json
{
  "feedback": {
    "written_count": 3,
    "review_confirmed": 2,
    "review_rejected": 1,
    "message": "Three fields were written with source references. Two ambiguous fields were confirmed by the teacher.",
    "next_review_prompt": "Check whether strategy outcomes were language-specific or setting-specific."
  }
}
```

Do not include peer-comparison, consensus, or accuracy claims in first build.

## 9. Source References

Every extracted support-profile entry must carry:

```json
{
  "source_ref_ids": ["source-file#chunk-id"],
  "confidence": "imported_verified | imported_needs_confirmation"
}
```

The writer must never create support-profile entries from imported files without
source refs.

Source snippets shown in UI must be bounded and must not leak unrelated student
records from the same file.

## 10. Writer Contract

Implement the real `write_student_lens(result, teacher_id)` contract currently
stubbed in `src/lingua_viva/data_in_contracts.py`, or add a new compatible
writer function if changing that return type would disrupt existing callers.

Behavior:

1. Consume verified fields only for ordinary profile fields.
2. Never auto-write `trauma_flag`.
3. Create a lens only if no assigned student exists and `display_name` is
   verified.
4. If `hint.assigned_student_id` is present, update that existing lens.
5. For support-profile fields:
   - `verified` -> write as `imported_verified`
   - `needs_confirmation` -> do not write until teacher confirms in UI
   - teacher-confirmed `needs_confirmation` -> write as
     `imported_needs_confirmation`
6. Return a result object:

```json
{
  "student_id": "student-123",
  "written_fields": [],
  "review_required": [],
  "unresolved_questions": [],
  "feedback": {
    "written_count": 0,
    "review_confirmed": 0,
    "review_rejected": 0,
    "message": "No fields were written without teacher confirmation."
  }
}
```

## 11. API and Route-to-UI Map

Use these route names unless implementation discovers a strong reason to reuse
an existing route. If changed, update this table before build completion.

| Route | Purpose | UI control/function | File | Required verification |
|---|---|---|---|---|
| `GET /api/extraction/sources` | List confirmed local/Drive files available for extraction | Extraction Sources section | `static/index.html` | Served HTML contains route string and result list renders |
| `POST /api/extraction/run` | Run extract-fill-verify for one selected file | **Run Extraction** button | `static/index.html` | Served HTML contains route string; route returns review items |
| `POST /api/extraction/review` | Submit teacher confirmations/rejections and write confirmed fields | **Write Confirmed to Lens** button | `static/index.html` | Served HTML contains route string; live write updates lens |
| `GET /api/students/{student_id}/lens` | Read updated lens after write | Students link/refresh | `static/index.html` | Live readback shows written support-profile entries |

Backend-only route count: **0**.

If implementation adds another route, it must be added here with a UI control
before the build can be reported PASS.

## 12. File Sources

Inputs can come from:

- local file-map assigned files
- Google Drive imported local cache files
- teacher-created local notes

Slack observations are already written through observation capture and should
not be re-imported through the file extraction path unless exported as local
files later.

Google Drive imported files and local files must use the same extraction path
after they are local.

## 13. Fixture Expansion

Add synthetic fixtures under:

```text
tests/fixtures/data_in_eval/student_lens_v2/
```

Fixtures:

- clear executive functioning need
- communication/language need
- emotional regulation observation
- worked strategy
- strategy tried but did not work
- advanced/enrichment student
- ambiguous note that must not verify
- sensitive trauma-adjacent note that must not auto-write trauma
- multi-category extraction
- source snippet with language/setting context

Fixtures must not contain real student data.

## 14. Tests

Add tests for extraction/writer correctness:

- field contract contains all categories and buckets
- extraction finds clear category needs
- extraction separates worked/not-worked strategies
- ambiguous notes produce no verified category fields
- advanced/enrichment maps correctly
- writer updates existing assigned student
- writer creates a new lens only when identity is grounded
- writer preserves source refs
- writer refuses imported support-profile entries without source refs
- `trauma_flag` is never auto-written
- Google Drive imported files and local files use the same extraction path

Add UI/reachability tests:

- served/static HTML includes `Extraction Sources`
- served/static HTML includes `Run Extraction`
- served/static HTML includes `Review Extraction`
- served/static HTML includes `Write Confirmed to Lens`
- served/static HTML includes `/api/extraction/sources`
- served/static HTML includes `/api/extraction/run`
- served/static HTML includes `/api/extraction/review`
- review UI includes confidence badges and source refs
- every extraction route has a UI call-site test

Update protected UI contract if `static/index.html` or `src/web.py` changes:

- bump `contracts/UI_CONTRACT.yaml`
- re-lock `contracts/UI_CONTRACT.lock`
- update `tests/test_ui_contract.py` expected version

## 15. Live Served-App Verification

Before reporting PASS, verify through the actual served app, not only direct
function calls or evals.

Minimum:

1. Start isolated local app:

   ```bash
   export MC_AGENT=1
   LV_HOME=/tmp/lv-extraction-live \
   LV_STUDENT_DB_PATH=/tmp/lv-extraction-live/student_lenses.db \
   uv run uvicorn src.web:app --host 127.0.0.1 --port 8799
   ```

2. Fetch `/` and confirm served HTML contains:
   - `Extraction Sources`
   - `/api/extraction/sources`
   - `/api/extraction/run`
   - `/api/extraction/review`

3. Create or use a local test student.
4. Create a synthetic local file with one clear support need, one worked
   strategy, and one ambiguous field.
5. Make the file available through the UI-backed extraction source path.
6. Call or click **Run Extraction** and confirm:
   - verified fields are separated from `needs_confirmation`
   - source refs are present
   - guidance/review tips are present
7. Confirm/reject review items through the public review route or browser UI.
8. Read `GET /api/students/{id}/lens` and confirm:
   - confirmed fields were written
   - ambiguous rejected fields were not written
   - every imported support-profile entry has source refs
   - `trauma_flag` was not auto-written

If browser automation is available, click the full Settings/Extraction workflow.
If not available, state that limitation and include the served HTML + public
HTTP route verification above.

## 16. Acceptance Criteria

- A selected imported/local file can populate verified student lens v2 fields.
- Teachers can reach extraction from the real app UI.
- Teachers can review ambiguous extraction results in the real app UI.
- Every extraction route has a UI call site.
- Needs and strategies land in the right category buckets.
- Teacher review items are surfaced for ambiguous/sensitive fields.
- Review feedback is visible after confirmation/rejection.
- Source refs are preserved for every imported support-profile entry.
- `trauma_flag` is never auto-written.
- Existing extraction evals continue to pass.
- UI contract passes after any protected file changes.
- Full test suite passes without live network dependencies.
- Build report distinguishes:
  - direct extraction/eval verification
  - served-app UI reachability verification

## 17. Explicit Non-Goals

- No live Google API calls in tests.
- No Slack re-import path.
- No external LLM calls with raw student content.
- No peer comparison or teacher competency scoring.
- No school-wide pattern analytics in this build.
- No writing unsupported or unresolved fields into student lenses.
