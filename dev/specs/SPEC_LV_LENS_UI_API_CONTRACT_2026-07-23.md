# Lingua Viva Lens UI and API Contract

**Date:** 2026-07-23  
**Status:** READY TO BUILD  
**Repo:** `/home/mical/learning-architecture`  
**Depends on:** `SPEC_LV_STUDENT_LENS_JSON_V2_SCHEMA_2026-07-23.md`, `SPEC_LV_OBSERVATION_IEP_CLASSIFICATION_WRITE_PATH_2026-07-23.md`  
**Build order:** 3 of 5  
**Lens applied:** Gagné Learning Engineering + built-not-mounted root-cause discipline  
**Route:** local only, `MC_AGENT=1` for build/validation commands

## 1. Objective

Expose the student lens v2 support profile in the actual Lingua Viva app so
teachers can use it during intervention sessions without reading raw
observation logs or using terminal-only APIs.

This spec is not complete when API routes exist. It is complete only when the
real served `static/index.html` lets a teacher:

- open **Students**
- select a learner
- see support categories, needs, strengths, worked/not-worked strategies,
  evidence, and open questions
- open **Observe**
- add or accept support-profile entries
- save them through the public capture route
- return to the learner lens and see the profile update

The UI must support the meeting use case: an intervention teacher may not know
the student well and needs a quick, trustworthy profile for a group of three to
four students.

## 1.5 Execution Protocol

Build under the same governed agent context used for the prior Lingua Viva
production passes:

1. Read `/home/mical/fde/mission-canvas/AGENTS.md`.
2. Read this repo's `CLAUDE.md` and `AGENTS.md`.
3. For any live Mission Canvas shell/pipeline/classification command used
   during implementation or validation, run:

   ```bash
   export MC_AGENT=1
   ```

4. MC shell discipline is build governance only. Do not make Mission Canvas
   runtime the default Lingua Viva runtime.
5. No raw student observation text or support-profile content may be sent to an
   external model.

## 2. Gagné Learning Scope

Use Gagné's events as teacher-facing scaffolding, not as an excuse to build a
separate training platform.

First-build event mapping:

| Event | Teacher need | App implementation |
|---|---|---|
| 1 Gain Attention | Notice what matters now | Students lens shows compact top support-profile signals; Observe save feedback names updated categories |
| 2 Inform Objectives | Understand what the workflow is for | Students/Observe copy states that support-profile entries support intervention planning and teacher review |
| 3 Stimulate Recall | Connect new evidence to prior data | Observe view shows current lens beside the capture form; Students view shows recent observations and support profile together |
| 4 Present Content | See structured support data | Support-profile categories render needs, strengths, strategies worked/not worked, evidence, and open questions |
| 5 Provide Guidance | Know how to interpret categories | Category labels/definitions are visible or one click away; Observe suggestions include guidance text |
| 6 Elicit Performance | Teacher applies judgment | Teacher can add/edit/confirm support entries before save |
| 7 Provide Feedback | Know what happened after save | Capture response and UI show saved entries and categories updated |
| 8 Assess Performance | Check local workflow quality | First build tracks counts and warnings, not teacher competency scores |
| 9 Retention/Transfer | Reuse effective strategies | Students/Prepare surfaces worked strategies and advanced/enrichment needs for planning |

Do not claim numerical teacher learning gains, accuracy targets, inter-rater
reliability, or time savings until pilot data exists.

Deferred beyond this spec:

- separate teacher competency database
- weekly calibration drills
- peer consensus comparison
- competency dashboards
- adaptive expert-mode unlocking
- school-wide predictive analytics

## 3. Existing App Architecture Constraint

Build in the app that exists:

- UI file: `static/index.html`
- API file: `src/web.py`
- lens store: `src/education/student_lens.py`
- capture pipeline: `src/education/observation_capture.py`
- tests: `tests/`

Do not create a new `app/` or `api/` directory tree. Do not spec routes like
`/teachers/{teacher_id}/dashboard` unless they are mounted in the existing
single-page app and verified through the served UI. For this build, prefer
enhancing the existing **Students**, **Observe**, and **Prepare** views.

## 4. API Contract

### Existing Route: `GET /api/students/{student_id}/lens`

This remains the primary read route. It must include:

```json
{
  "student_id": "student-123",
  "display_name": "Maria Garcia",
  "grade_level": "MYP5",
  "rti_current_tier": 2,
  "cefr_snapshot": {
    "listening": "B1",
    "speaking": "A2",
    "reading": "B1",
    "writing": "A2"
  },
  "support_profile": {
    "schema_version": 2,
    "categories": {
      "executive_functioning": {
        "needs": [],
        "strengths": [],
        "strategies_worked": [],
        "strategies_not_worked": [],
        "evidence": [],
        "open_questions": []
      }
    }
  },
  "support_profile_warnings": [],
  "observations": []
}
```

Read-time normalization must tolerate malformed legacy support-profile JSON and
return warnings instead of crashing the UI.

### Existing Route: `POST /api/observe/classify`

Used by Observe's **Suggest fields** control. It must return:

- CEFR/SEL proposal fields
- `support_entries`
- `classification_guidance`
- `teacher_feedback`
- `teacher_confirmation_required: true`
- `writes_made: 0`

This route must never write lens data.

### Existing Route: `POST /api/observe/capture`

Used by Observe's **Save Observation** control. It must accept teacher-reviewed
`support_entries` and return bounded feedback:

```json
{
  "observation": {"observation_id": "obs-123"},
  "feedback": {
    "saved_entries": 2,
    "categories_updated": ["executive_functioning"],
    "message": "Saved under Executive Functioning...",
    "next_review_prompt": "Check whether the strategy outcome was language-specific or setting-specific."
  },
  "local_only": true
}
```

### Optional Route: `GET /api/categories`

Add only if the UI genuinely calls it. If implemented, it must return static,
secret-free category metadata:

```json
{
  "categories": [
    {
      "id": "executive_functioning",
      "label": "Executive Functioning",
      "definition": "Planning, sequencing, organization, attention, working memory, transition, and task-initiation evidence.",
      "examples": ["Student starts the task after a two-step checklist is provided."],
      "non_examples": ["Do not record a diagnosis unless it appears in a verified source."]
    }
  ]
}
```

If this route is not implemented, equivalent category definitions must be
available inside `static/index.html` and tested there.

### Optional Route: `GET /api/students/support-summary`

Add only if the UI genuinely calls it from an existing dashboard/planning
surface. It must return aggregate counts only and no raw observation text.

There are no other new routes in this first build. If implementation adds one,
the route must be added to Section 6 with an exact UI call site.

## 5. UI Contract

### Students View

Enhance existing `renderStudents()` and `loadLens()` in `static/index.html`.

Required UI:

- roster remains visible
- selected lens panel shows:
  - student name
  - CEFR trajectory
  - support tier
  - recent observations
  - support profile summary
- support profile summary renders all non-empty categories
- each category shows at least:
  - category label
  - total item count
  - latest need/strength/evidence
  - visible split between worked and did-not-work strategies when present
- `advanced_enrichment` is visually separate from intervention/support needs
- support-profile warnings are visible when returned by API

Gagné coverage:

- Event 1: compact support signals
- Event 3: recent observations adjacent to profile
- Event 4: structured support buckets
- Event 5: category labels/definitions

### Observe View

Enhance existing `renderObserve()`.

Required UI:

- current selected lens remains visible beside the form
- **Suggest fields** calls `/api/observe/classify`
- support-profile review section includes:
  - category selector
  - need field
  - strength field
  - strategy field
  - strategy outcome selector: worked / did_not_work / unknown
  - evidence summary field
  - language selector
  - setting selector
  - teacher-confirmed checkbox
  - add/remove support-entry controls
- **Save Observation** calls `/api/observe/capture` with `support_entries`
- saved feedback appears in the UI
- the lens panel refreshes after save

Gagné coverage:

- Event 3: current lens context
- Event 5: guidance text from proposal/category metadata
- Event 6: teacher edits/confirmations
- Event 7: save feedback

### Prepare / Differentiated Groups

Enhance the existing differentiated groups surface only if the data is already
available from existing endpoints. Do not create a new unmounted intervention
route for this build.

Minimum:

- compact student group cards may show support tier and relevant support hints
- worked strategies may appear as planning hints when present
- advanced/enrichment needs do not increase intervention tier

Gagné coverage:

- Event 9: transfer of worked strategies into planning

## 6. Route-to-UI Reachability Map

Every route in this build must be mapped here before implementation is called
complete.

| Route | UI control/function | File | Required verification |
|---|---|---|---|
| `GET /api/students/{student_id}/lens` | `loadLens()` in Students and Observe lens panel | `static/index.html` | Served HTML contains `loadLens`; live route returns `support_profile`; UI refreshes after save |
| `POST /api/observe/classify` | `Suggest fields` button, `suggestObservation()` | `static/index.html` | Served HTML contains route string; route returns `writes_made: 0` |
| `POST /api/observe/capture` | `Save Observation` button, `saveObservation()` | `static/index.html` | Served HTML contains route string; live save updates support profile |
| `GET /api/categories` | Category guidance lookup, if implemented | `static/index.html` | If route exists, served HTML must call it |
| `GET /api/students/support-summary` | Dashboard/planning summary, if implemented | `static/index.html` | If route exists, served HTML must call it |

Backend-only route count for this spec: **0**.

If a route exists but is not in the table, the build is not done.

## 7. Privacy and Safety

- Raw student observations stay local.
- No external model receives raw observation text or support-profile content.
- Classification proposals are drafts; teacher confirmation is required before
  support-profile writes.
- The UI must not call clinical/diagnostic labels generated by the model.
- `advanced_enrichment` is additive; it must not imply intervention/RTI flags.
- Summary endpoints must not expose raw observation text.
- Support-profile warnings must be shown without exposing private internals.

## 8. Tests

Add or update tests for:

- `GET /api/students/{id}/lens` includes support profile and warnings
- malformed support profile does not crash API/UI rendering
- Students HTML includes `Support profile`
- Students HTML includes `renderSupportProfileSummary`
- Students HTML includes all canonical category IDs or labels
- Observe HTML includes support-profile review controls
- Observe HTML includes `/api/observe/classify`
- Observe HTML includes `/api/observe/capture`
- Observe save payload includes `support_entries`
- classify route returns `writes_made == 0`
- capture route writes support entries and returns feedback
- advanced enrichment remains separate from support-tier/RTI calculations
- optional routes, if implemented, have UI call-site tests

Update protected UI contract if `static/index.html` or `src/web.py` changes:

- bump `contracts/UI_CONTRACT.yaml`
- re-lock `contracts/UI_CONTRACT.lock`
- update `tests/test_ui_contract.py` expected version

## 9. Live Served-App Verification

Before reporting PASS, verify through the real served app, not only direct
function tests.

Minimum:

1. Start isolated local app:

   ```bash
   export MC_AGENT=1
   LV_HOME=/tmp/lv-lens-ui-live \
   LV_STUDENT_DB_PATH=/tmp/lv-lens-ui-live/student_lenses.db \
   uv run uvicorn src.web:app --host 127.0.0.1 --port 8799
   ```

2. Fetch `/` and confirm served HTML contains:
   - `Support profile`
   - `renderSupportProfileSummary`
   - `/api/observe/classify`
   - `/api/observe/capture`
   - `support_entries`

3. Create a local test student through `POST /api/students`.
4. Save one observation through `POST /api/observe/capture` with two confirmed
   support entries across different categories.
5. Read `GET /api/students/{id}/lens` and confirm:
   - both categories updated
   - worked/not-worked strategies are in the correct buckets
   - language/setting context is preserved
   - `advanced_enrichment`, if used, does not alter RTI tier
6. Confirm the served app can still load `/` without JS parse errors.

If browser automation is available, click the Students/Observe workflow. If it
is not available, state that limitation and include the served HTML + public
HTTP route verification above.

## 10. Acceptance Criteria

- A teacher can reach support-profile information from the real Students view.
- A teacher can create support-profile entries from the real Observe view.
- Every required route has an actual UI call site.
- The support-profile UI shows needs, strengths, strategies worked,
  strategies not worked, evidence, and open questions when present.
- Advanced/enrichment needs are visible but separate from intervention flags.
- Observation capture writes reviewed support entries and refreshes the lens.
- Capture feedback is visible after save.
- Existing CEFR/RTI/SEL behavior remains intact.
- UI contract passes after any protected file changes.
- Full test suite passes.
- Build report distinguishes:
  - direct route/function verification
  - served-app UI reachability verification

## 11. Explicit Non-Goals

- No separate teacher-learning platform in this build.
- No new unmounted `/teachers/{teacher_id}/dashboard` route.
- No peer comparison or consensus scoring.
- No claims of teacher competency improvement.
- No external LLM calls with raw student data.
- No school-wide analytics unless mounted in the real app and separately
  approved.
