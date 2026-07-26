# Lingua Viva Ingestion and Extraction Mapping v2

**Date:** 2026-07-23  
**Status:** READY TO BUILD  
**Repo:** `/home/mical/learning-architecture`  
**Depends on:** student lens v2 schema, observation write path, lens UI/API contract, Google Drive connector  
**Build order:** 5 of 5  
**Lens applied:** Gagné Learning Engineering (Nine Events of Instruction) + built-not-mounted root-cause discipline  
**Route:** local only, `MC_AGENT=1` for build/validation commands

---

## 0. Gagné Learning Engineering Summary

This spec applies **Robert Gagné's Nine Events of Instruction** as a scaffolding framework for teacher learning within the extraction workflow. Each event is explicitly mapped to prevent Pattern B/C failures (backend built ahead of UI) and ensure teachers develop competency in data extraction and support-profile construction.

**Gagné Event Coverage Table:**

| Event | Teacher Need | Implementation in This Spec |
|---|---|---|
| **1. Gain Attention** | Notice extraction candidates and their value | Extraction Sources section shows available files with visual indicators; Run Extraction button is prominent |
| **2. Inform Objectives** | Understand extraction workflow purpose | Section 2 explicitly states objectives; extraction review UI shows what will happen before action |
| **3. Stimulate Recall** | Connect imported data to existing student knowledge | Review UI displays current student lens alongside extracted fields; source snippets reference prior observations |
| **4. Present Content** | See structured data from files | Extracted fields presented in support-profile category buckets with definitions |
| **5. Provide Guidance** | Know how to interpret and validate extractions | Category definitions, review tips, and confidence indicators guide teacher decisions |
| **6. Elicit Performance** | Practice validation and confirmation | Teacher must confirm/reject each needs_confirmation field; multi-select for multi-category observations |
| **7. Provide Feedback** | Receive immediate validation results | Feedback panel shows written count, confirmed, rejected; next review prompts for improvement |
| **8. Assess Performance** | Verify extraction quality | Test suite validates field correctness; live served-app verification confirms end-to-end flow |
| **9. Retention/Transfer** | Apply extraction skills to new files | Multi-category and contextual strategy handling ensures skills transfer across different import types |

**Learning Domain:** This spec primarily targets **Intellectual Skills** (classifying, applying extraction rules) with secondary emphasis on **Cognitive Strategies** (metacognitive review of extraction decisions).

---

## 1. Objective

Map information from local files, Google Drive imports, and teacher-created
local notes into the student lens v2 support profile with provenance,
confidence, teacher review, and a real app path.

This spec owns the "data in" semantics. Slack and Google Drive are transport
surfaces; this spec defines how imported/local file content becomes structured
student-lens data.

**Critical: This build is NOT complete when extraction tests pass.** It is complete ONLY when:

- A teacher can use the real served Lingua Viva app to select a local/imported file
- Run extraction through the UI
- Review extracted fields with source references and category definitions
- Confirm or reject ambiguous fields
- Write confirmed fields into a student lens
- Read the updated lens back in the Students view

**Pattern B/C Mitigation (ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md §6):**
- Every route has an explicit UI call site (Section 11)
- Backend-only route count is explicitly **0**
- "Live-verified" means verified through actual served app, not direct function calls
- Batch commits must state per-route UI reachability status

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

## 1.6 Pattern B/C Explicit Mitigation

**Per ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md §6, this spec explicitly states:**

1. **UI Reachability:** Every route in Section 11 has a corresponding UI control in `static/index.html`. There are **0 backend-only routes** in this build.
2. **Deferred Work:** None. All routes have UI call sites in this spec.
3. **Verification Type:** All "live-verified" claims in this spec mean "verified by using the actual served app as a teacher would" (not direct function calls).
4. **Route-to-UI Map:** Section 11 explicitly lists every route with its UI control, file, and required verification.

**Pattern B Risk (backend built ahead of UI):** Mitigated by requiring UI call sites before build completion.
**Pattern C Risk (eval-green mistaken for reachable):** Mitigated by requiring served-app verification, not just eval passes.

## 2. Teacher Learning Scope

Use Gagné's events as **light scaffolding for teacher review and learning**, not as a separate training platform. This spec embeds learning moments directly into the extraction workflow.

### 2.1 Learning Objectives (Gagné Event 2: Inform Objectives)

First-build learning objectives for teachers using this extraction flow:

| ID | Objective | Evidence in App | Gagné Event |
|---|---|---|---|
| **IO-1** | Identify which imported fields need teacher review | Review queue separates verified, needs confirmation, and unresolved fields | Events 4, 6 |
| **IO-2** | Distinguish verified fields from ambiguous fields | Confidence indicators (imported_verified vs imported_needs_confirmation) are visible beside every extracted field | Events 4, 5, 8 |
| **IO-3** | Resolve ambiguous extraction results without losing provenance | Confirm/reject controls preserve `source_ref_ids` and context | Events 6, 7 |
| **IO-4** | Maintain source provenance across imported data | Written support-profile entries cite source chunks and original observation IDs | Events 4, 5, 9 |
| **IO-5** | Apply support category definitions correctly | Category labels and definitions are visible during review; review tips reference category criteria | Events 3, 5 |
| **IO-6** | Handle multi-category observations appropriately | UI supports selecting multiple categories from a single observation; each maintains separate source_observation_id | Events 4, 6 |

### 2.2 Learning Domain Classification

**Primary Domain: Intellectual Skills** (Gagné)
- Teachers learn to classify information into support categories
- Apply rules for distinguishing needs, strengths, strategies
- Problem-solve ambiguous extraction cases

**Secondary Domain: Cognitive Strategies** (Gagné)
- Teachers develop metacognitive awareness of their own classification patterns
- Learn to self-monitor extraction decisions
- Develop strategies for validating extraction accuracy

### 2.3 Deferred Learning Features

Not in this build (explicit deferral per ROOT_CAUSE §6.2):

- separate teacher competency database
- practice/calibration mode with synthetic data
- peer consensus comparison across teachers
- competency badges or unlock levels
- school-wide import-pattern analytics
- adaptive scaffolding based on teacher history

These may be added in a future spec named explicitly (not "a follow-up spec").

**Rationale:** First build focuses on **core extraction workflow with embedded learning moments**. Separate training platforms risk Pattern A (wholesale infrastructure ports) and Pattern D (partial-batch wiring) failures.

## 3. Current State

`src/lingua_viva/extraction_engine.py` extracts a minimal `student_lens` target:

- display name
- campus
- grade level
- home languages
- learning differences
- trauma flag, never auto-verified
- CEFR snapshot fields

**Gagné Event Gap Analysis:** Current engine addresses Events 4 (Present Content) partially but lacks:
- Event 1: No attention mechanism for teachers
- Event 2: Objectives not explicitly surfaced
- Event 3: No recall of prior student data during extraction
- Event 5: Guidance is minimal
- Event 6: No practice/confirmation mechanism
- Event 7: No feedback after extraction
- Event 8: No assessment of extraction quality
- Event 9: No retention/transfer support

**This spec closes all nine event gaps.**

It does not fully provide a production path for:

- support category needs
- strengths
- worked/not-worked strategies
- category evidence
- advanced/enrichment indicators
- teacher review of ambiguous support-profile fields
- writing confirmed extracted fields into `StudentLensStore`
- **UI reachability through the served app** (CRITICAL: this was the Pattern C failure in LV-BLT-008)

The root-cause document (§3 Pattern C) explicitly identified this failure class: eval-green extraction code can still be unusable if the teacher cannot trigger it from the app. **This spec addresses this directly.**

## 4. UI Reachability Contract (Gagné Events 1, 2, 4, 6, 7, 9)

**CRITICAL:** This section prevents Pattern B and Pattern C failures.

Mount this workflow in the existing app. **Do not build a backend-only extraction engine.**

### 4.1 UI Placement

**Preferred location:** **Settings** under the existing file-map/Google Drive import area, with reviewed results linking back to **Students**.

This placement ensures:
- **Event 1 (Gain Attention):** Teachers see extraction as part of their existing file import workflow
- **Event 2 (Inform Objectives):** Context is clear - this is for importing student data
- **Event 9 (Retention/Transfer):** Skills learned transfer to existing workflows

### 4.2 Required Visible Controls (Gagné Event Coverage)

- **Extraction Sources** section listing confirmed local/Drive import files (Event 4: Present Content)
- **Run Extraction** button for a selected file (Event 1: Gain Attention, Event 6: Elicit Performance)
- **Review Extraction** panel/modal showing:
  - confidence indicators: `imported_verified`, `imported_needs_confirmation`, `unresolved` (Event 4, 5)
  - source-reference links or expandable source snippets (Event 3: Stimulate Recall)
  - category definition/guidance text for extracted support fields (Event 5: Provide Guidance)
  - category label and purpose (Event 5)
  - **Confirm** and **Reject** controls for each `needs_confirmation` field (Event 6: Elicit Performance)
- **Write Confirmed to Lens** button (Event 6: Elicit Performance)
- result area showing:
  - student ID
  - written fields
  - review-required fields
  - unresolved questions
  - feedback message with next review prompt (Event 7: Provide Feedback)

### 4.3 Required UI Call Sites

Every extraction capability must have a UI trigger:

- list extraction candidates from existing file-map/Drive-import state
- call extraction route for a selected file
- call review/write route for confirmed fields
- refresh or link to `GET /api/students/{student_id}/lens` after write (Event 9: Retention/Transfer)

**Rule:** No extraction route may be considered shipped unless it has a call site in `static/index.html` and is listed in Section 11.

**Backend-only extraction route count for this build: 0**

This explicitly prevents Pattern B (backend built ahead of UI that never landed).

## 5. Target Schema Fields (Gagné Event 4: Present Content)

Extend `STUDENT_LENS_FIELDS` to include support-profile paths for every canonical category.

This presents content in a structured, organized way (Gagné Event 4) that teachers can understand and work with.

```python
"support_profile.categories.learning_and_cognition.needs",
"support_profile.categories.learning_and_cognition.strengths",
"support_profile.categories.learning_and_cognition.strategies_worked",
"support_profile.categories.learning_and_cognition.strategies_not_worked",
"support_profile.categories.learning_and_cognition.evidence",
"support_profile.categories.learning_and_cognition.open_questions",
... (repeat for all categories)
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

Implementation may generate these paths from `SUPPORT_CATEGORY_IDS`, but tests must assert that every category and bucket is present.

## 6. Extraction Prompt Behavior (Gagné Events 4, 5)

The student extraction prompt must tell the local model to support teacher learning:

### 6.1 Content Presentation Rules (Event 4)

- extract only facts explicitly supported by the source text
- do not diagnose
- do not infer disability, trauma, or protected characteristics
- classify educational observations into the support categories only when explicit
- separate needs from strengths
- separate strategies from needs
- only mark a strategy as worked/did-not-worked when the source says outcome explicitly
- preserve language and setting context when present
- put challenge/extension/high-readiness evidence under `advanced_enrichment`
- omit uncertain fields

### 6.2 Guidance for Learning (Event 5: Provide Learning Guidance)

The prompt must include teacher-facing guidance:

- For each extracted field, include a `review_tip` that helps teachers validate the extraction
- Review tips should reference category definitions and criteria
- Provide `category_definitions` that are visible in the review UI
- Include examples of what belongs in each category vs. what does not

**Scaffolding Levels (Event 5):**

```json
{
  "scaffolding_level": "novice | intermediate | expert",
  "category_definitions": [...],
  "examples": [...],
  "non_examples": [...]
}
```

Default to `intermediate` for first build. Novice level shows full definitions and examples; expert shows minimal guidance.

### 6.3 Output Structure

The prompt output must include enough structured metadata for a teacher review UI:

```json
{
  "field_path": "support_profile.categories.executive_functioning.needs",
  "value": "Needs a visual checklist for multi-step work.",
  "source_ref_ids": ["file.pdf#chunk-0003"],
  "confidence": "imported_verified | imported_needs_confirmation",
  "review_tip": "Check whether the source describes task sequencing or language access.",
  "category_id": "executive_functioning",
  "category_definition": "Planning, sequencing, organization, attention, working memory...",
  "scaffolding_level": "intermediate"
}
```

## 7. Verification Rules (Gagné Events 5, 8)

Keep the extract-fill-verify invariant. This section supports **Event 5 (Guidance)** by providing clear rules and **Event 8 (Assess Performance)** by ensuring quality verification.

### 7.1 Field Verification (Event 8)

- A field can only become `verified` if grounded in cited chunks and confirmed by verification
- Ambiguous fields become `needs_confirmation`
- Unsupported fields are dropped into unresolved questions
- `trauma_flag` remains never auto-verified

### 7.2 Category-Level Rules (Event 8)

- Any category-level need/strategy derived from vague behavior language should be `needs_confirmation`, not verified, unless the source directly names the need/strategy
- Strategy outcome requires explicit success/failure language
- `advanced_enrichment` can verify from direct language such as "advanced", "needs challenge", "extension work", "ready for acceleration", or equivalent clear source wording
- Every support-profile field must carry source refs before it can be written
- Teacher-confirmed ambiguous fields are written with `imported_needs_confirmation`, not silently upgraded to `imported_verified`

### 7.3 Assessment Alignment (Event 8)

Tests must verify that:
- Extraction produces correct category classifications (measures stated objectives)
- Verification rules catch ambiguous cases (allows demonstration of mastery)
- Assessment is aligned with real-world extraction tasks (authentic assessment)

## 8. Teacher Guidance and Feedback (Gagné Events 5, 7)

For each extraction result, show teacher-facing learning supports:

### 8.1 Guidance Display (Event 5)

- confidence badge
- category label and definition
- one-sentence review tip
- source reference
- exact source snippet or a bounded excerpt around the cited chunk
- whether the field will write automatically, needs confirmation, or is unresolved

### 8.2 Feedback After Review (Event 7: Provide Feedback)

Feedback must be **descriptive/analytic** (most valuable per Gagné):

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

**Feedback Types Used:**
- **Descriptive/Analytic:** "Three fields were written..." - provides specific information about what happened and next steps
- **Next Review Prompt:** Directs teacher to specific improvement areas (remedial feedback)

**Avoid:** Confirmatory-only or evaluative-only feedback that doesn't guide improvement.

### 8.3 Feedback Quality Standards (Event 7)

Do not include in first build:
- peer-comparison
- consensus claims
- accuracy percentages
- teacher competency scoring

These require pilot data and would overclaim without evidence.

## 9. Source References (Gagné Event 3: Stimulate Recall)

Every extracted support-profile entry must carry provenance to help teachers connect new data to existing knowledge:

```json
{
  "source_ref_ids": ["source-file#chunk-id"],
  "confidence": "imported_verified | imported_needs_confirmation",
  "source_observation_id": "obs-123"
}
```

**Event 3 Application:**
- Source snippets help teachers recall what they've already documented
- Source observation IDs link to existing records, stimulating recall of prior knowledge
- Context tags (language, setting) provide additional memory cues

The writer must never create support-profile entries from imported files without source refs.

Source snippets shown in UI must be bounded and must not leak unrelated student records from the same file.

## 10. Writer Contract (Gagné Events 6, 7, 8)

Implement the real `write_student_lens(result, teacher_id)` contract currently stubbed in `src/lingua_viva/data_in_contracts.py`, or add a new compatible writer function if changing that return type would disrupt existing callers.

### 10.1 Write Behavior (Event 6: Elicit Performance)

1. Consume verified fields only for ordinary profile fields
2. Never auto-write `trauma_flag`
3. Create a lens only if no assigned student exists and `display_name` is verified
4. If `hint.assigned_student_id` is present, update that existing lens
5. For support-profile fields:
   - `verified` -> write as `imported_verified`
   - `needs_confirmation` -> do not write until teacher confirms in UI
   - teacher-confirmed `needs_confirmation` -> write as `imported_needs_confirmation`

### 10.2 Feedback Return (Event 7)

Return a result object:

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
    "message": "No fields were written without teacher confirmation.",
    "next_review_prompt": "Review ambiguous fields and check source references."
  }
}
```

### 10.3 Assessment Verification (Event 8)

Writer tests must verify:
- Correct fields are written based on confidence levels
- Source refs are preserved
- Provenance is maintained
- Teacher confirmations are respected

## 11. API and Route-to-UI Map (Pattern B/C Prevention)

**CRITICAL: This section prevents Pattern B (backend-only routes) and Pattern D (partial-batch wiring) failures.**

Use these route names unless implementation discovers a strong reason to reuse an existing route. **If changed, update this table before build completion.**

| Route | Purpose | UI control/function | File | Required verification | Gagné Events |
|---|---|---|---|---|---|
| `GET /api/extraction/sources` | List confirmed local/Drive files available for extraction | Extraction Sources section | `static/index.html` | Served HTML contains route string and result list renders | Events 1, 2, 4 |
| `POST /api/extraction/run` | Run extract-fill-verify for one selected file | **Run Extraction** button | `static/index.html` | Served HTML contains route string; route returns review items | Events 4, 5, 6 |
| `POST /api/extraction/review` | Submit teacher confirmations/rejections and write confirmed fields | **Write Confirmed to Lens** button | `static/index.html` | Served HTML contains route string; live write updates lens | Events 6, 7, 8 |
| `GET /api/students/{student_id}/lens` | Read updated lens after write | Students link/refresh | `static/index.html` | Live readback shows written support-profile entries | Events 9 |

**Backend-only route count: 0**

**Pattern B/C Rule:** If implementation adds another route, it must be added here with a UI control before the build can be reported PASS. This prevents:
- Pattern B: Backend built ahead of UI that never lands
- Pattern C: Eval-green code that's not reachable through UI
- Pattern D: Partial-batch wiring (some routes mounted, others not)

## 12. File Sources (Gagné Event 3: Stimulate Recall)

Inputs can come from:

- local file-map assigned files
- Google Drive imported local cache files
- teacher-created local notes

**Event 3 Connection:** Teachers recognize these sources from their existing workflows, stimulating recall of prior import experiences.

Slack observations are already written through observation capture and should not be re-imported through the file extraction path unless exported as local files later.

Google Drive imported files and local files must use the same extraction path after they are local.

## 13. Fixture Expansion (Gagné Event 6: Elicit Performance)

Add synthetic fixtures under:

```text
tests/fixtures/data_in_eval/student_lens_v2/
```

**Practice opportunities for teachers (Event 6):**

Fixtures must provide realistic practice scenarios:

- clear executive functioning need
- communication/language need
- emotional regulation observation
- worked strategy
- strategy tried but did not work
- advanced/enrichment student
- ambiguous note that must not verify
- sensitive trauma-adjacent note that must not auto-write trauma
- **multi-category extraction** (Event 6: complex practice)
- source snippet with language/setting context (Event 3: recall stimulus)

Fixtures must not contain real student data.

## 14. Tests (Gagné Events 6, 8)

### 14.1 Extraction/Writer Correctness Tests (Event 8: Assess Performance)

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

### 14.2 UI/Reachability Tests (Pattern B/C Prevention)

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

**Pattern C Prevention:** These tests ensure "live-verified" means actual UI reachability, not just eval passes.

### 14.3 Gagné Event Verification Tests

Add tests that verify each Gagné event is supported:

- Event 1: Extraction Sources section is visible and prominent
- Event 2: Objectives are stated before extraction begins
- Event 3: Source references link to existing observations
- Event 4: Extracted fields are structured and organized
- Event 5: Guidance (definitions, tips) is visible during review
- Event 6: Teacher can confirm/reject fields (practice)
- Event 7: Feedback is descriptive and actionable
- Event 8: Verification rules catch ambiguous cases
- Event 9: Multi-category support ensures transfer

### 14.4 UI Contract Protection

Update protected UI contract if `static/index.html` or `src/web.py` changes:

- bump `contracts/UI_CONTRACT.yaml`
- re-lock `contracts/UI_CONTRACT.lock`
- update `tests/test_ui_contract.py` expected version

This prevents Pattern D (partial-batch wiring) failures.

## 15. Live Served-App Verification (Pattern C Prevention)

**CRITICAL: This section prevents Pattern C failures (eval-green mistaken for reachable).**

Before reporting PASS, verify through the actual served app, not only direct function calls or evals.

### 15.1 Minimum Verification (Event 8: Assess Performance in Real Context)

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
4. Create a synthetic local file with:
   - one clear support need
   - one worked strategy
   - one ambiguous field
   - multi-category observation (Event 6: complex practice)
5. Make the file available through the UI-backed extraction source path.
6. Call or click **Run Extraction** and confirm:
   - verified fields are separated from `needs_confirmation` (Event 4)
   - source refs are present (Event 3)
   - guidance/review tips are present (Event 5)
7. Confirm/reject review items through the public review route or browser UI (Event 6).
8. Read `GET /api/students/{id}/lens` and confirm:
   - confirmed fields were written (Event 6, 7)
   - ambiguous rejected fields were not written
   - every imported support-profile entry has source refs (Event 3)
   - `trauma_flag` was not auto-written

### 15.2 Pattern C Explicit Check

**"Live-verified" claim in this build means:** "Verified by using the actual served app as a teacher would, not by direct function/API calls."

If browser automation is available, click the full Settings/Extraction workflow. If not available, state that limitation and include the served HTML + public HTTP route verification above.

## 16. Acceptance Criteria

### 16.1 Functional Criteria

- A selected imported/local file can populate verified student lens v2 fields
- Teachers can reach extraction from the real app UI
- Teachers can review ambiguous extraction results in the real app UI
- Every extraction route has a UI call site
- Needs and strategies land in the right category buckets
- Teacher review items are surfaced for ambiguous/sensitive fields
- Review feedback is visible after confirmation/rejection
- Source refs are preserved for every imported support-profile entry
- `trauma_flag` is never auto-written

### 16.2 Learning Criteria (Gagné Events)

- Teachers can see category definitions and examples during review (Event 5)
- Teachers receive descriptive feedback after extraction (Event 7)
- Multi-category support ensures skill transfer (Event 9)
- Source references stimulate recall of prior knowledge (Event 3)

### 16.3 Quality Criteria

- Existing extraction evals continue to pass
- UI contract passes after any protected file changes
- Full test suite passes without live network dependencies
- Build report distinguishes:
  - direct extraction/eval verification
  - served-app UI reachability verification

### 16.4 Pattern B/C Prevention Criteria

- All routes have UI call sites listed in Section 11
- Backend-only route count is explicitly 0
- Live verification is through served app, not direct calls
- Any new route added must have UI call site before PASS

## 17. Explicit Non-Goals

- No live Google API calls in tests
- No Slack re-import path
- No external LLM calls with raw student content
- No peer comparison or teacher competency scoring
- No school-wide pattern analytics in this build
- No writing unsupported or unresolved fields into student lenses
- No separate teacher-learning platform (learning is embedded in workflow)

## 18. Coordination with Other Specs

This spec coordinates with:

1. **SPEC_LV_STUDENT_LENS_JSON_V2_SCHEMA_2026-07-23.md** (Build order 1): Uses the support-profile schema defined there
2. **SPEC_LV_OBSERVATION_IEP_CLASSIFICATION_WRITE_PATH_2026-07-23.md** (Build order 2): Shares the support category structure and provenance model
3. **SPEC_LV_LENS_UI_API_CONTRACT_2026-07-23.md** (Build order 3): Provides the UI surface this spec mounts into

**Gagné Coordination:**
- LENS_UI_API_CONTRACT covers Gagné Events for the Students/Observe views
- OBSERVATION_IEP_CLASSIFICATION covers Gagné Events for observation capture
- This spec (INGESTION_EXTRACTION_MAPPING) covers Gagné Events for file-based extraction

All three specs together ensure **complete Gagné event coverage** across all data entry paths into the support profile.

## 19. References

- Gagné, R. M., Briggs, L. J., & Wager, W. W. (1992). Principles of instructional design (4th ed.).
- ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md (Patterns A-D analysis)
- SPEC_LV_STUDENT_LENS_JSON_V2_SCHEMA_2026-07-23.md
- SPEC_LV_OBSERVATION_IEP_CLASSIFICATION_WRITE_PATH_2026-07-23.md
- SPEC_LV_LENS_UI_API_CONTRACT_2026-07-23.md
