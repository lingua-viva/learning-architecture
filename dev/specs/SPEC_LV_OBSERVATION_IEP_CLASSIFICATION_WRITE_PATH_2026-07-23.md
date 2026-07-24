# Lingua Viva Observation IEP Classification and Write Path

**Date:** 2026-07-23  
**Status:** READY TO BUILD  
**Repo:** `/home/mical/learning-architecture`  
**Depends on:** `SPEC_LV_STUDENT_LENS_JSON_V2_SCHEMA_2026-07-23.md`  
**Build order:** 2 of 5  
**Review basis:** Claudia Canu Fautré lens + Gagné Learning Engineering lens

## 1. Objective

Extend observation capture so teacher notes can be classified into the new
student lens v2 support categories and saved as structured needs, strengths,
evidence, and strategy outcomes.

The write path must keep the existing rule: model suggestions can prepare a
teacher-review form, but the teacher-owned local record is authoritative.

This build is not only a data pipeline. It is also a teacher-learning system:
each classification moment should help teachers become more precise observers,
more consistent support-category users, and better evidence-based intervention
designers.

## 1.5 Execution Protocol

This spec must be built from a governed Mission Canvas shell agent context,
with `MC Shell AGENTS.md = 1` treated as a mandatory build condition:

1. Read `/home/mical/fde/mission-canvas/AGENTS.md` for the Mission Canvas
   shell discipline: locate first, prove first, preserve auditability, and
   keep sensitive education data local.
2. Read this repo's `CLAUDE.md` and `AGENTS.md`; for Lingua Viva, `CLAUDE.md`
   is the local equivalent of MC's repo-orientation manual, while
   `AGENTS.md` defines the stricter production/push meaning.
3. For any live Mission Canvas pipeline/classification command used during
   implementation or validation, run it with:

   ```bash
   export MC_AGENT=1
   ```

4. Do not use MC runtime as the default Lingua Viva runtime. MC shell protocol
   is the build discipline; Lingua Viva remains its own local-first product
   boundary.
5. No external model call may receive raw student observation text.

## 1.6 Teacher Learning Outcomes

After repeated use, the app should help teachers:

- classify observations into the support categories with increasing
  consistency
- distinguish need statements, strength statements, evidence summaries, and
  strategy outcomes
- understand why a category was proposed, without accepting it blindly
- retain context about what worked, what did not work, and under which
  language/environmental conditions
- generate better evidence for formal support planning with less duplicated
  administrative effort

Do not claim numerical learning gains, inter-rater reliability, or time savings
until an actual pilot measures them. The implementation may track the raw data
needed for those future measures.

## 2. Current State

`/api/observe/classify` currently proposes only:

- `template_type`
- CEFR dimension/level/direction
- SEL domain/valence
- urgency flag

`/api/observe/capture` writes:

- raw transcript
- CEFR/SEL/RTI fields
- local-only observation row

It does not classify into the IEP-style categories, record strategy outcomes,
handle multi-category observations, or scaffold teacher learning.

## 3. Observation Model Additions

Add optional fields to `Observation` and the `observations` table:

```python
support_entries: list[dict]
classification_guidance: dict | None
teacher_feedback: dict | None
source_type: str | None
```

Each `support_entries` item:

```json
{
  "support_category": "executive_functioning",
  "need_statement": null,
  "strength_statement": null,
  "strategy_statement": null,
  "strategy_outcome": "worked | did_not_work | unknown",
  "evidence_summary": null,
  "context_tags": {
    "language": "it | en | multilingual | unknown",
    "setting": "intervention | classroom | small_group | one_to_one | unknown"
  },
  "teacher_edited": false,
  "model_suggested": true
}
```

Allowed values:

```python
VALID_STRATEGY_OUTCOMES = ("worked", "did_not_work", "unknown")
VALID_SOURCE_TYPES = ("observation", "slack", "google_drive", "local_file", "report", "teacher_note")
```

`support_category` must be one of `SUPPORT_CATEGORY_IDS` or `None`.

Why list-based: a single observation may legitimately span multiple domains,
for example executive functioning plus communication and language. One saved
observation row can create multiple support-profile entries; every created
entry must cite the same `source_observation_id`.

## 4. Classification Proposal Contract

`/api/observe/classify` must return:

```json
{
  "proposal": {
    "template_type": null,
    "cefr_dimension": null,
    "cefr_level_observed": null,
    "cefr_direction": null,
    "sel_domain": null,
    "sel_valence": null,
    "urgency_flag": null,
    "support_entries": [],
    "classification_guidance": {
      "scaffolding_level": "novice | intermediate | expert",
      "category_definitions": [],
      "examples": [],
      "non_examples": []
    },
    "teacher_feedback": {
      "message": null,
      "review_prompt": null
    }
  },
  "teacher_confirmation_required": true,
  "writes_made": 0
}
```

The prompt must state:

- return strict JSON only
- never rewrite the transcript
- leave uncertain fields null
- do not infer disability, diagnosis, trauma, or protected traits
- `advanced_enrichment` is for challenge/extension needs
- `strategy_outcome` is only `worked` or `did_not_work` if the note explicitly
  says whether the strategy succeeded
- preserve language and setting context when present
- permit multiple support entries only when the transcript explicitly supports
  multiple category-relevant statements
- provide brief category guidance for teacher review, not hidden chain-of-
  thought

## 4.5 Learning Guidance Layer

The classification proposal must support fading teacher scaffolds:

- `novice`: show category definitions, examples, and non-examples
- `intermediate`: show category definition and one rationale sentence
- `expert`: show proposed structured fields only

Default to `intermediate`. Do not block the first implementation on adaptive
scaffolding logic; a static `intermediate` response is acceptable if the shape
is present and tested.

Examples/non-examples must be general and synthetic. They must not quote or
reveal other students' observations.

## 5. Capture Contract

`/api/observe/capture` accepts the new fields after teacher review.

On save:

1. Append the observation row exactly as today.
2. For each teacher-confirmed item in `support_entries`, append structured
   entries into `support_profile`.
3. If `need_statement` is present, add to that category's `needs`.
4. If `strength_statement` is present, add to that category's `strengths`.
5. If `strategy_statement` is present:
   - `worked` -> `strategies_worked`
   - `did_not_work` -> `strategies_not_worked`
   - `unknown` or null -> evidence only, not a worked/not-worked strategy
6. Always add `evidence_summary` if present.
7. Every created entry cites `source_observation_id`.
8. If the teacher edited a model-suggested statement, store the support-profile
   entry as `teacher_confirmed`, not `model_suggested`, while preserving
   `source_observation_id`.

The append-only observation row remains the source of truth.

## 5.5 Teacher Feedback System

The capture response should include immediate feedback that reinforces teacher
learning without overclaiming accuracy:

```json
{
  "feedback": {
    "saved_entries": 2,
    "categories_updated": ["executive_functioning"],
    "message": "Saved under Executive Functioning. This category is used for planning, sequencing, organization, and task-initiation evidence.",
    "next_review_prompt": "Check whether the strategy outcome was language-specific or setting-specific."
  }
}
```

Do not implement school-wide peer comparison in the first build unless there
is real multi-teacher pilot data. The code may record teacher-confirmed vs
model-suggested/edited provenance so future calibration can be measured.

## 5.6 Practice and Calibration Mode

Add the data seams needed for a future practice mode, but do not require a full
training module in this build.

Minimum:

- classification proposals include definitions/examples for teacher review
- capture records whether the teacher accepted, edited, or rejected model
  suggestions
- tests verify that teacher edits are recorded as teacher-confirmed

Deferred:

- weekly calibration drills
- peer consensus comparison
- competency dashboard
- adaptive expert-mode unlocking

These are product-learning features for a later UI/API spec unless the
operator explicitly pulls them into this build.

## 6. Slack Behavior

Slack remains a fast input surface.

Initial build:

- Slack observations continue to save as `template_type="literacy"` unless
  explicitly changed later.
- Slack raw text is stored locally.
- Slack does not auto-classify categories unless/until the same classification
  proposal path is wired behind an explicit teacher review UI.
- Slack acknowledgements remain fixed and must not echo the raw observation or
  inferred category back into Slack.

Optional later build:

- Slack acknowledgement can say "Observation saved; review suggested tags in
  Lingua Viva" without echoing content.

## 7. Privacy and Safety Rules

- No student observation text routes to an external model.
- Local model classification may propose category fields.
- Clinical/diagnostic language is not created by the app.
- The app can classify evidence into support categories; it must not diagnose.
- Trauma-sensitive fields remain confirmation-only.
- Invalid classification output degrades to null fields, never a crash.
- Strategy outcomes are contextual, not universal. If a strategy works in
  Italian small-group work but not English whole-class work, that context must
  remain attached in the saved evidence.
- Category guidance and feedback must never expose another student's data.

## 8. Tests

Add tests for:

- classifier parser accepts all new fields
- invalid category becomes null
- invalid strategy outcome becomes null
- classifier parser accepts multiple support entries
- capture with one `need_statement` writes one support-profile need
- capture with multiple confirmed support entries writes multiple category
  entries sharing the same `source_observation_id`
- capture with worked strategy writes `strategies_worked`
- capture with did-not-work strategy writes `strategies_not_worked`
- unknown strategy outcome does not write worked/not-worked buckets
- language/setting context is preserved in evidence/entry metadata
- teacher-edited model suggestions save as `teacher_confirmed`
- classification guidance returns definitions/examples without writing data
- capture feedback reports categories updated without overclaiming accuracy
- observation export includes the structured fields
- degraded model returns empty proposal and `writes_made == 0`
- Slack behavior remains unchanged and existing Slack tests pass
- isolated pytest invocation works under `tests/conftest.py`

## 9. Acceptance Criteria

- A teacher can capture a note into a selected category.
- Lens export shows the note under the correct category.
- Strategy worked/not-worked evidence is separated from needs.
- One observation can update multiple confirmed support categories.
- Language/setting context is preserved when present.
- The teacher receives immediate, bounded learning feedback after capture.
- The proposal path provides category guidance but makes zero writes.
- Existing CEFR/RTI/SEL behavior remains intact.
- Full test suite passes.
- Build report notes that the work was executed under the MC-shell discipline
  in Section 1.5, including `MC_AGENT=1` for any live MC
  pipeline/classification command used.

## 10. Explicit Non-Goals

- No autonomous diagnosis.
- No external LLM calls with raw student observation text.
- No school-wide peer comparison without real pilot data.
- No claims of teacher competency improvement until measured.
- No Slack auto-classification without a teacher review surface.
