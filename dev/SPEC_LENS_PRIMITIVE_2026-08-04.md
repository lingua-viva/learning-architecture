# SPEC: Lens Primitive (2026-08-04)

**Status:** DRAFT — combines two same-day tracks into one spec. Concrete instance (Case Study
#1) is already built and tested (`src/lingua_viva/docpipe/`); the generalized primitive framing
below is new. Scope: this repo only. Do not port to Palette/Mission Canvas yet.

## 0. Where this came from

Two things were built independently on 2026-08-04 aimed at the same target:

1. **This design track** — a from-scratch conversation about a general "Lens Primitive": a
   typed, ID-addressable profile structure that shares a student's categorized support need
   (shareable) without ever letting the causal/etiological narrative behind it (why — e.g. a
   specific trauma) leave the local machine. Land: a small patch to
   `src/education/student_lens.py` / `src/lingua_viva/drive_sync.py` (`NARRATION_NOT_SHARED`,
   below) that closes a real leak in the *existing* Observe → Drive export path.
2. **The docpipe track** (`dev/CONTRACTS_V1_2026-08-04.md`, T0-T7 build waves, apparently a
   Kiro-run session, discovered mid-build here) — a frozen `docpipe.lens.v1` schema that already
   implements the same DOES/evidence-invariant principle, more rigorously and mechanically, for
   the *document-upload* intake path. It is live-wired into `src/web.py` (extraction, lens
   creation, Drive sync-queue, `/api/sync/status`) and its lens/vault/sync modules pass their own
   tests in isolation (19/19) even though the wider suite is currently NO-GO for unrelated
   reasons (route-reachability manifest gap, 3 stale TTS-locale tests, one unfinished
   frontend/backend save-validation migration — none of them in `docpipe/lens.py`, `vault.py`, or
   `sync.py`). Those are a separate track's open items and are **not** touched by this spec.

Per operator instruction: combine them, take the best of each, keep going. Do not fix docpipe's
unrelated NO-GO items here — that's out of scope and someone else's file ownership.

## 1. The general primitive

A **Lens** is a typed, evidence-grounded profile for one entity, addressable by a stable ID and
built only by positive construction (DOES), never by filtering raw material with a denylist.

```
lens_id       = "<lens_type>:<entity_id>"       e.g. "student:LV-STU-002"
schema_version = "<lens_type>.lens.v<n>"          e.g. "docpipe.lens.v1"
profile        = { field_id: { value, evidence[] } }   — closed vocabulary per lens_type
metadata       = { source_ids[], observation_ids[], merge_events[] }
```

Rules (mechanically enforced, not advisory — see `_assert_grounded` in `docpipe/lens.py`):

- `profile` has a **fixed, closed set of field IDs** for its `lens_type`. No field outside that
  set can ever be written (`merge_observation` raises on an unknown `field_id`).
- A field is either **empty** (`value` is `None`/`""`/`[]`/`{}` and `evidence == []`) or
  **populated** (`value` is non-empty and `evidence` has ≥1 item). No other state is legal.
- Evidence is a **pointer**, never inlined raw material: `{source_ref, confidence, added_at,
  added_by}`. `source_ref.type` is `DOCUMENT` (needs `span_id`) or `OBSERVATION` (needs
  `obs_id`). The raw document/transcript lives in its own file; the lens never contains it.
- The only way to populate a field is through one of two sanctioned constructors —
  `create_from_extraction()` (document → lens) or `merge_observation()` (dictation/typed note →
  lens). Both classify input into the closed vocabulary, construct a curated `value` +
  evidence pointer, and call `_assert_grounded()` before every write. There is no "edit value
  directly" path. **This is the INPUT → DOES → LENS translator** the operator asked about — it
  already exists, it just wasn't named that.

### Composition — join by reference, never nesting

Different-type lenses combine to answer a question that spans them (e.g. a specific student, in
a specific school, in a specific country's curriculum) by **citing lens IDs together**, the way
`SUPPORT_CATEGORY_IDS` work as taxonomy-style unique IDs today. A composed artifact records which
lens IDs it drew from (`lens_ids: ["student:LV-STU-002", "school:LV-SCH-004", "country:LV-IT"]`),
not a copy of their contents and not one lens embedded inside another. Two lenses of the **same**
type never combine (two students don't merge into one lens) — only cross-type composition is
meaningful, mirroring how MC's ontology nodes stay atomic and combine by citation, not by nesting.

This repo only needs `lens_type = "student"` today (Still I Rise has 7 schools already, more
coming, in different countries — the shape has to survive that growth without a rewrite, but
building `school`/`country`/`organization` lens types now, before a real use case forces the
question, would be exactly the speculative work the operator said not to do yet). When a second
lens_type is actually needed, it gets its own closed vocabulary and its own `schema_version`,
same shape, added under this same spec.

### Envelope framing (for the MC capability-wave agents' benefit)

Mapped onto the manifest/validate/invoke shape used by the MC capability wave
(`ACCOMPLISHMENTS_2026-08-04.md` §7), so this can be read as capability-family kin rather than a
parallel invention:

| Capability-wave concept | Lens Primitive equivalent |
|---|---|
| `manifest()` | `vault/manifest.json` — inventory of every lens instance + its `schema_version` |
| `validate()` | `_assert_grounded()` — run on every write, not opt-in |
| `invoke()` | `create_from_extraction()` / `merge_observation()` — the only writers |
| Insufficiency envelope | An `_assert_grounded()` failure, or a field left legitimately empty with `evidence: []` — "I don't know" is a first-class, representable state, not a crash |

## 2. Concrete instance — LV Student Lens (Case Study #1)

Already built, already tested, already live-wired:

- Schema: `dev/CONTRACTS_V1_2026-08-04.md` §3 (`docpipe.lens.v1`).
- Code: `src/lingua_viva/docpipe/{model,vault,lens,sync,extract,drive}.py`.
- Fields (10, closed): the 7 SEL/RTI categories (`learning_and_cognition`,
  `communication_and_language`, `executive_functioning`, `social_skills`,
  `emotional_regulation`, `physical_sensory_needs`, `attendance_and_engagement`) +
  `strategies_trialed`, `academic_strengths`, `personal_strengths`. No causal/etiological field
  exists anywhere in this schema — there is nowhere to put "why," only "what" and "what helps,"
  which is the DOES boundary the operator specified for the Student Lens from the start.
- Wired in `src/web.py` (document-upload extraction endpoints, `/api/sync/status`) — reachable
  from the real app, not just from tests.
- Drive export (`docpipe/sync.py:render_lens_markdown`) renders only `value` + evidence
  citations, never raw text — confirmed narration-safe by construction, independently of the fix
  below.

## 3. The gap this design track actually closed

Docpipe's lens is one intake path (document upload). **Observe** (mic dictation / typed note) is
a second, older, still-live intake path that writes directly into
`src/education/student_lens.py`'s `StudentLensStore`, bypassing docpipe's constructors entirely.
That path's own export function (`src/lingua_viva/drive_sync.py:format_lens_markdown`) used to
render the **raw observation transcript** (`raw_transcript` / `teacher_edited_transcript`) into
the Drive-shared Markdown — a real leak of exactly the causal/narrative material the DOES
principle exists to keep local, on a path docpipe's grounding invariant never covered.

**Fix landed this session** (uncommitted, tested):
- `src/education/student_lens.py`: `NARRATION_NOT_SHARED` constant; `local_observation_rows()`
  overwrites `raw_transcript`/`teacher_edited_transcript` with it before rows are handed to any
  export path.
- `src/lingua_viva/drive_sync.py`: removed the raw "Recent Observations" narration block from
  `format_lens_markdown()` entirely — the exported doc now only ever carries the same kind of
  material docpipe's `render_lens_markdown()` carries: curated statements + evidence pointers.
- `tests/test_triangulation.py`: two new regression tests — narration never survives into ledger
  rows, and Drive markdown never renders raw observation text.
- 83 tests passing across the affected suite (`test_student_lens.py`, `test_triangulation.py`,
  `test_teacher_decision_flywheel.py`, `test_student_evidence.py`).

This is the DOES pattern applied by construction (overwrite at the export boundary), not by
scanning text for causal language — consistent with the operator's explicit rejection of
keyword/causal-language filtering as unreliable.

## 4. Known debt, revisited — consolidation ruled OUT, not just deferred

§4 originally framed this as scheduling debt: "route Observe's capture endpoint through
`docpipe.lens.merge_observation()`... not attempted here, out of scope before the demo." Having
now read `src/education/observation_capture.py` in full (439 lines), that framing was wrong, not
just premature. This is not a thin wrapper waiting to be swapped for docpipe's constructor — it's
a second, independently mature DOES/classification system:

- Deterministic regex-based `suggest_support_categories()` over 8 categories (7 shared with
  docpipe's `SUPPORT_CATEGORY_FIELDS` + `advanced_enrichment`, which docpipe's v1 deliberately
  excludes), each with its own weighted signal list.
- An **obligatory-routing rule**: write to a category bucket only above
  `CATEGORY_SUGGESTION_THRESHOLD = 0.5`, otherwise route to `open_questions` — i.e. its own
  "Insufficiency is a first-class state" mechanism, arrived at independently of docpipe's
  `_assert_grounded()`.
- A two-tier confidence model (`model_suggested` vs `teacher_confirmed`) plus an ethos-trait
  suggest-then-confirm pattern (`_suggest_ethos_traits` / `confirm_ethos_suggestion`) that has no
  docpipe equivalent at all.
- A structural (not classification-dependent) guarantee that this pipeline never routes
  externally — the same DOES-by-construction shape as docpipe's local-only model lock in
  `docpipe/model.py`, built separately.

Forcing this through `merge_observation()`'s simpler 10-field vocabulary and single-shot
evidence-append would either strip the confidence-tier/suggest-then-confirm behavior teachers
already rely on, or require growing `merge_observation()` until it re-implements
`ObservationCapturePipeline` inside docpipe — a rewrite of live, actively-used surface
(`/api/observe/capture` in `src/web.py`), not a consolidation. **Ruling: do not attempt this
merge.** Instead:

- **`ObservationCapturePipeline` is Case Study #2** of the Lens Primitive pattern (see §2a below)
  — a second, independent proof that the same shape (closed vocabulary, evidence/confidence
  gating, Insufficiency-as-state) emerges without coordination when the DOES principle is applied
  to a different intake modality (dictation/typed note vs. document upload).
- The two write paths into `StudentLensStore` and two export mechanisms stay as they are. Each is
  independently narration-safe (docpipe by construction, Observe via this session's
  `NARRATION_NOT_SHARED` fix at the export boundary). The invariant is enforced twice, not once —
  that remains real debt, but the fix is not "delete one path," it's a future third constructor
  that both existing pipelines write through, designed with both vocabularies in view. Not scoped
  here; flagged for whoever designs `lens_type` #2 (school/organization), since that's when a
  shared constructor's shape would need to be decided anyway.

### 2a. Concrete instance #2 — Observation Capture Pipeline (independent, pre-existing)

`src/education/observation_capture.py`, wired at `src/web.py:3721` (`/api/observe/capture`). Not
built as part of this spec — discovered, read, and recognized as the same pattern:

- Profile fields: the 8 SEL/RTI support categories (7 shared with docpipe + `advanced_enrichment`)
  plus CEFR/ethos-trait dimensions.
- Evidence/grounding equivalent: `model_suggested` (weighted regex match, no teacher confirmation
  yet — the "empty but reasoned" state) vs. `teacher_confirmed` (populated, human-gated) —
  structurally the same empty/populated binary as docpipe's `{value, evidence[]}`, expressed as a
  confidence tier instead of an evidence list.
  Insufficiency equivalent: `open_questions` routing when no category clears
  `CATEGORY_SUGGESTION_THRESHOLD` — the dictation-path version of a legitimately empty field.
- Grounding boundary: narration-safety enforced at the export boundary
  (`local_observation_rows()` / `NARRATION_NOT_SHARED`, §3), not inside this pipeline itself —
  this pipeline's job is classification, not export; export safety is a separate, composable
  concern, same separation docpipe keeps between `lens.py` and `sync.py`.

## 5. Feedback for the MC capability-wave agents

Closing the loop the operator asked for: the envelope contract shape used by the 15 MC
capabilities (`ACCOMPLISHMENTS_2026-08-04.md` §7 — `manifest()` / `validate()` / `invoke()` / an
Insufficiency envelope) traces back to what Lingua Viva needed the day before it was written, and
this repo now has **two** independent implementations of it, not one, which is stronger evidence
than the spec originally had:

1. **docpipe's `lens.v1`** (document-upload path, built same day, apparently by Kiro, without
   coordination with this design track) — the more mechanical, more rigorous version:
   `_assert_grounded()` runs on *every* write, not opt-in, and raises rather than warns on a
   violation. This is `validate()` as a hard gate, not a lint pass.
2. **`ObservationCapturePipeline`** (dictation/typed-note path, pre-existing, older than either of
   the same-day tracks) — arrived at the same shape from a completely different angle: a
   confidence-threshold routing rule instead of an evidence-list check, `open_questions` instead
   of an empty `evidence: []`. Nobody designed these two to match. They match anyway, on the same
   day, in the same repo, without either author reading the other's code first.

The finding worth carrying back into the capability wave's own hardening: **when the same
constraint (never assert positively about something you don't have grounds for) is applied
honestly in two unrelated codebases, they converge on the same shape by necessity, not by shared
spec.** That convergence is itself evidence the shape is right, not an accident of one team's
taste. Concretely for the 15 capabilities: audit whether each one's Insufficiency path is a
first-class, testable output (an explicit "I don't have grounds for this" return value) or a
side-effect of an exception/timeout. docpipe's version raises loudly and gets caught by
`_assert_grounded()`'s own test suite; Observe's version routes to `open_questions` and shows up
in the teacher's UI as a visible, actionable "needs your input" state rather than a silent gap.
Either shape is legitimate — what would be a regression is a capability where insufficiency is
invisible (empty field rendered as if it were a confirmed answer, or a crash with no envelope at
all).
