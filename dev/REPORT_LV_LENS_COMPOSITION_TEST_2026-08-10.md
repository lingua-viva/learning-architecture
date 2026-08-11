# REPORT — LV Lens Composition Test (Lane B gate)

**Date:** 2026-08-11 (executed) · **Spec:** 2026-08-10
**Lane:** B of the lens wave · **Authority:** RULINGS R2, R3, R7, R10, R11
**K1 status:** DID NOT FIRE — slot rules produced a clean, usable composition
**K2 status:** DID NOT FIRE — four classes cover all LV actors (R14's model class came from MC evidence, not LV)

**Lane E is UNBLOCKED by this report.**

---

## Task 1 — Real composition run (Claudia person lens + curriculum-designer role lens)

**Real task used:** Parent report for Nora Rossi (fixture: `tests/evals/fixtures/synthetic_teacher_history/parent_update_nora.json` — bilingual SEL + language + next-steps structure, Malaguzzi-toned).

**Slot assignments (§4 rules applied by hand):**

| Slot | Filled by | What it supplied |
|---|---|---|
| Values / weights | Person lens (Claudia) | Children through competence, warm protective tone, "language journey" framing, Italian-first for curriculum, evidence-as-narrative |
| Form / contract | Role lens (curriculum designer) | SEL → Language → Next Steps structure; bilingual pairs (IT first, EN second); l1_l2_ratio ≈ 0.52; specific low-pressure home actions |
| Constraints (vetoes) | UNION of both | Person: no deficit language, no institution names in external docs. Role: no raw scores without context, no identifiable data beyond parent need |

**Collision check:** Zero same-field collisions. Person fills `writing_voice`, `values`, `non_negotiables`. Role fills `report_structure`, `format_requirements`, `quality_checklist`. Each owns its slot — pure union.

**One noted edge case:** If the role were "standardized test analyst" (cold, data-forward), the person lens's Malaguzzi voice (poetic, images-before-abstractions) would create a TONE tension. The slot rules handle it correctly (tone is person-owned → person wins; format is role-owned → role wins), but the resulting artifact — Malaguzzi-voiced test analysis — would be unusual. This is the §4 rule 3 "named tension, third option" scenario: the honest resolution would be a mode switch (narrative section + data appendix), not a blend. Worth noting for the MC plan but not a schema failure.

**Verdict:** Slot rules HELD. Composition was pure union, no resolution needed.

---

## Task 2 — Paddle-fan prototypes (four-class union)

Three prototype lenses authored for one real LV scenario (Nora Rossi parent report):

### 2a. Teacher lens (perspective class)
```yaml
schema_version: "mc.lens.v1"
lens_class: perspective
lens_id: "LENS-PERSP-001_claudia_canu_teacher"
display_name: "Claudia Canu Fautré — Teacher"
version: "0.1"

access_scope:
  students: ["student-nora-rossi", "student-marco-bianchi"]
  grade_levels: ["G3"]
  campuses: ["local"]

writing_voice:
  register: "warm_formal"
  reference_educator: "Loris Malaguzzi"
  voice_lens: "VOICE-EDU-001_malaguzzi_inspired.md"
  languages:
    primary: "it"
    secondary: "en"
    l1_l2_ratio: 0.52

observation_authority:
  can_observe: true
  can_create_lens: true
  can_edit_lens: true
  can_export_lens: true

forbidden_patterns:
  - "deficit language about children"
  - "raw test scores without context"
  - "institution name in external documents"
```

### 2b. School lens (institution class)
```yaml
schema_version: "mc.lens.v1"
lens_class: institution
lens_id: "LENS-INST-001_la_scuola"
display_name: "La Scuola International School"
version: "0.1"

vocabulary:
  assessment_framework: "IB PYP/MYP"
  language_assessment: "CEFR (Pre-A1 to B2) + Prove MT"
  pedagogical_approach: "Reggio Emilia inspired"
  curriculum_model: "UbD (Understanding by Design)"

report_formats:
  parent_update:
    structure: ["social_emotional", "language_progress", "next_steps"]
    bilingual: true
    bilingual_order: "it_first"
  student_work_review:
    structure: ["task", "student_response", "teacher_note"]

curriculum_norms:
  immersion_model: "full Italian immersion K-5"
  rti_model: "3-tier"
  sel_framework: "Responsive Classroom"

forbidden_patterns:
  - "non-IB assessment terminology without mapping"
  - "student ranking or comparison language"
```

### 2c. Jurisdiction lens
```yaml
schema_version: "mc.lens.v1"
lens_class: jurisdiction
lens_id: "LENS-JURIS-001_us_ca_ferpa"
display_name: "US / California / FERPA + COPPA"
version: "0.1"

egress_rules:
  student_pii: { policy: "local_only", rationale: "FERPA 34 CFR §99" }
  student_health: { policy: "local_only", rationale: "FERPA + CA Ed Code §49076" }
  iep_data: { policy: "local_only", rationale: "IDEA Part B + FERPA" }
  parent_contact: { policy: "local_only", rationale: "FERPA directory info opt-out" }
  classroom_observation: { policy: "local_only", rationale: "contains student PII" }
  aggregated_anonymous: { policy: "may_egress", rationale: "de-identified ≠ education record" }

coppa_rules:
  child_age_threshold: 13
  consent_required: "verifiable parental consent for online collection"

california_specific:
  sopipa: true
  ab_1584: true

forbidden_patterns:
  - "student PII in any cloud API call"
  - "student names in external model prompts"
  - "learning difference diagnoses in unencrypted transit"
  - "RTI tier data outside local storage"
```

### 2d. Four-class field-union composition

**Subject (Nora docpipe lens):** `student_id`, `display_name`, `profile` (10 fields), `metadata` (source_ids, observation_ids, merge_events)
**Perspective (teacher):** `lens_id`, `display_name`, `access_scope`, `writing_voice`, `observation_authority`, `forbidden_patterns`
**Institution (school):** `lens_id`, `display_name`, `vocabulary`, `report_formats`, `curriculum_norms`, `forbidden_patterns`
**Jurisdiction:** `lens_id`, `display_name`, `egress_rules`, `coppa_rules`, `california_specific`, `forbidden_patterns`

| Field | Classes present | Collision? | Resolution |
|---|---|---|---|
| `schema_version` | all 4 | **YES** — subject uses `docpipe.lens.v1`, others use `mc.lens.v1` | Design decision needed: per-constituent (nested structure) or convention (top-level owns it) |
| `display_name` | all 4 | **YES** — each says something different | Per-constituent (nested) eliminates this; or subject owns it in composed view |
| `created_at` / `updated_at` | all 4 | **YES** — different timestamps | Composed view uses max(updated_at); or per-constituent |
| `lens_id` / `student_id` | all 4 (different names) | **Designed aggregation** per R3 | `id` field aggregates all constituent IDs |
| `forbidden_patterns` | 3 (perspective + institution + jurisdiction) | **Designed aggregation** per §4 rule 3 | Union as vetoes — 10 patterns, zero contradictions |
| All substantive fields | 1 each | **No collision** | `profile` = subject only; `access_scope` = perspective only; `vocabulary` = institution only; `egress_rules` = jurisdiction only |

**Finding:** All collisions are in **envelope/metadata fields**, not substantive content. The substantive union is perfectly clean. This strongly suggests the composed lens should be a **nested structure** (each class as a keyed sub-object), not a flat union. Nested structure eliminates all three envelope collisions by construction:

```yaml
composed_lens:
  id: ["student-nora-rossi", "LENS-PERSP-001", "LENS-INST-001", "LENS-JURIS-001"]
  subject: { ... }      # Nora's docpipe lens
  perspective: { ... }  # teacher lens
  institution: { ... }  # school lens
  jurisdiction: { ... } # jurisdiction lens
  forbidden_patterns:    # union of all
    - "deficit language about children"
    - "raw test scores without context"
    - "institution name in external documents"
    - "non-IB assessment terminology without mapping"
    - "student ranking or comparison language"
    - "student PII in any cloud API call"
    - "student names in external model prompts"
    - "learning difference diagnoses in unencrypted transit"
    - "RTI tier data outside local storage"
```

**Verdict:** Composition is collision-free on all substantive fields. Three envelope-field collisions all resolve by nesting. `forbidden_patterns` union works exactly as designed.

---

## Task 3 — Audit-surface check (R7: lenses visible and editable)

Walked the LV Observe tab (`src/education/observation_capture.py`, `src/education/student_lens.py`) against the teacher lens prototype.

**What student lenses have today (the parity target):**

| Capability | Student lens | Code |
|---|---|---|
| Create | `create_from_extraction()` + `merge_observation()` | `docpipe/lens.py` |
| View | `get_lens(student_id)` | `student_lens.py:StudentLensStore` |
| Export | `export_lens(student_id)` — full profile + observation log | `student_lens.py` |
| Delete | `delete_lens(student_id)` — soft tombstone | `student_lens.py` |
| Audit trail | `merge_events[]`, evidence chains, `_assert_grounded()` | `docpipe/lens.py` |
| Comment | Teacher observations accumulate on student lens | `observation_capture.py` |

**Gaps for perspective/teacher lens — what does NOT exist:**

1. **No teacher lens storage.** `StudentLensStore` is student-specific (SQLite schema, CRUD methods all keyed on `student_id`). No `PerspectiveLensStore` or generalized `LensStore` exists.
2. **No "my lens" view.** The Observe tab shows student lenses the teacher created. No tab/view exists for a teacher to see their own perspective lens (writing_voice, access_scope, observation_authority).
3. **No teacher lens editing.** Teachers cannot adjust their own perspective parameters (e.g., update writing_voice, add a student to access_scope, change l1_l2_ratio).
4. **No teacher lens audit trail.** Student lenses have `merge_events`; teacher lenses have no equivalent accumulation or history mechanism.
5. **No cross-person lens visibility.** For R10 (cross-person composition), a co-teacher might need to see a colleague's perspective lens to understand their voice/access scope. No mechanism exists.
6. **No dual-role self-model view.** R7 names multi-role self-modeling (parent-lawyer-soccer player). Claudia is both teacher and parent of Nora — these are two perspective-class lenses on the same person. No UI surfaces this or lets the user switch between them.

**MC requirement this produces:** The "users see and modify lenses easily" requirement needs, for perspective-class lenses:
- A generalized `LensStore` (or parallel `PerspectiveLensStore`) with student-lens-parity CRUD
- An "About Me" / "My Lens" tab in the app, parallel to Observe
- Audit trail (`merge_events` equivalent) for perspective lens changes
- Cross-person visibility for collaboration scenarios (R10)
- Role-switching UI for users with multiple perspective lenses

---

## Task 4 — Auto-creation stress (R11: `create_from_extraction()` + `merge_observation()`)

**Method:** Ran the real docpipe machinery against the Nora Rossi fixture set (source document `SRC-WORK-NORA-ROSSI` + observation `OBS-NORA-20260804-01`) live, not just the existing test suite.

**Results:**

| Check | Result |
|---|---|
| `create_from_extraction()` populates correct fields | PASS — `communication_and_language` + `academic_strengths` from document spans |
| Evidence chains intact | PASS — every populated field has `source_ref` with type, source_id, path, span_id |
| `merge_observation()` accumulates without loss | PASS — `strategies_trialed` + `personal_strengths` added; prior fields retained |
| `merge_events` logged correctly | PASS — 2 events: `create_from_extraction` (SRC-WORK-NORA-ROSSI) + `merge_observation` (OBS-NORA-20260804-01) |
| `_assert_grounded()` passes | PASS — no value without evidence, no evidence without span_id/obs_id |
| Dedup by evidence-key hash | PASS — existing test `test_bridge_populates_student_lens_store_without_duplicate_sync` confirms no duplicate sync |
| Existing test suite | PASS — 4/4 tests green in 0.35s |

**Instrument disagreement check (spec requirement — "re-verify live with real data"):**
The fixture lens file (`tests/fixtures/docpipe/lens_nora_rossi.json`) and the live-created lens agree on all populated fields and evidence chain structure. The live run populated `communication_and_language` from SPN-0003 (confidence 0.99) matching the fixture's SPN-0003 (confidence 0.91) — the confidence differs because the fixture was hand-authored (0.91) while the live run derives it from `students_detected[0].confidence` (0.99). This is not a disagreement in mechanism — it's a difference between fixture-authored and code-computed confidence. The code path is correct.

**Verdict:** Auto-creation machinery works as the brief claims. Evidence chains, merge_events, and `_assert_grounded` all behave correctly on real data.

---

## What MC must do differently (≤10 lines)

1. **Compose by nesting, not flattening.** Envelope-field collisions (`schema_version`, `display_name`, `created_at`) vanish if the composed lens is `{subject: {...}, perspective: {...}, institution: {...}, jurisdiction: {...}}` with `id` and `forbidden_patterns` at the top level.
2. **Inherit `_assert_grounded` / evidence-chain pattern from LV wholesale** for all lens classes, not just subject. Every field in every class should carry its provenance.
3. **Build a generalized LensStore** (or per-class stores) with student-lens-parity CRUD — the perspective class has zero storage, zero UI, zero audit trail today.
4. **Add a "My Lens" view** parallel to the Observe tab. R7 demands it; R10 (cross-person composition) depends on it.
5. **Treat `forbidden_patterns` as a first-class composed field** — the union-as-vetoes aggregation is the one proven composition rule. Make it mechanical, not prompt-assembled.
6. **Model class (R14) needs the same treatment** — field ownership, worked example, ID grammar — but that evidence comes from MC, not from this LV test.
