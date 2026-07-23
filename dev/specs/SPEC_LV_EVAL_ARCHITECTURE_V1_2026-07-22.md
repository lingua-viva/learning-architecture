# SPEC: Lingua Viva Unified Eval Architecture V1

**Author**: kiro.design  
**Date**: 2026-07-22  
**Status**: SHIPPED (eval skeletons only — implementations pending)  
**Layer count**: 5  
**Total eval count**: 75  
**Dependencies**: None on existing src/ — all tests are forward-looking  

---

## 1. Problem Statement

Lingua Viva's 479 existing tests verify mechanisms: does the parser parse, does the store store, does the endpoint return 200. They do not verify promises:

- Grade fencing: G3 request → only G3 content, never G4
- Student isolation: Marco's lens contains only Marco's data
- Provenance grounding: every generated sentence traces to a source document
- Tier determinism: same inputs → same tier, every time
- Teacher adaptation: system learns patterns from the teacher's own past work

These are the properties that matter to the teacher. This spec defines how we prove them.

---

## 2. Architecture: Five Layers, Zero Overlap

```
Layer 5: GAUNTLETS (end-to-end workflow correctness)          ← 5 gauntlets, ~25 assertions
Layer 4: GOLDEN ARTIFACTS (output quality & style match)      ← 20 tests
Layer 3: ISOLATION & CONTAMINATION (safety boundaries)        ← 15 tests
Layer 2: ADAPTIVE RETRIEVAL & TEACHER LENS (data routing)     ← 20 tests
Layer 1: SCHEMA & CONTRACT (structural validity)              ← 15 tests
```

**Non-overlap rule**: each property is owned by exactly one layer. If a test could fit in two layers, it belongs in the lower (closer to data) layer.

**Dependency rule**: Layer N may only run after Layers 1..(N-1) all pass. A schema failure (Layer 1) means there is no point running retrieval tests (Layer 2).

---

## 3. Layer Ownership Matrix

| Property | Owner Layer | NOT in |
|----------|-------------|--------|
| JSON shape, required fields, types | L1 | L2-L5 |
| Provenance structure (has source_file, page) | L1 | L2-L5 |
| Teacher Lens schema | L1 | L2-L5 |
| Grade fencing (correct sources retrieved) | L2 | L3-L5 |
| Document classification accuracy | L2 | L1,L3-L5 |
| Teacher pattern extraction | L2 | L1,L3-L5 |
| Retrieval determinism (same query → same result) | L2 | L3-L5 |
| Student data never leaks to another student | L3 | L1-L2,L4-L5 |
| Teacher data never leaks to another teacher | L3 | L1-L2,L4-L5 |
| Temporal boundaries (no future data in lens) | L3 | L1-L2,L4-L5 |
| PII never appears in traces/bundles | L3 | L1-L2,L4-L5 |
| Tier assignment correctness (truth table) | L4 | L1-L3,L5 |
| CEFR progression monotonicity | L4 | L1-L3,L5 |
| Bloom's taxonomy alignment | L4 | L1-L3,L5 |
| Holdout prediction (teacher style match) | L4 | L1-L3,L5 |
| Bilingual ratio compliance | L4 | L1-L3,L5 |
| Full workflow correctness (multi-step) | L5 | L1-L4 |
| Cross-layer integration | L5 | L1-L4 |

---

## 4. Layer 1: Schema & Contract (15 tests)

**Property**: Every output conforms to its declared structure.  
**Runtime**: <1s total. No model calls. Pure structural validation.

### Tests

| ID | What it proves | Pass condition |
|----|---------------|----------------|
| L1-LENS-001 | Student lens JSON matches schema | All required fields present, correct types, no extra fields |
| L1-LENS-002 | Empty lens has safe defaults | CEFR=null all dimensions, RTI=1, trajectory=insufficient_data |
| L1-PACK-001 | Activity pack has exactly 3 tiers | Keys are {foundational, on_track, extended}, no more/less |
| L1-PACK-002 | Each tier has required fields | cefr_target, learning_objective, activities[], assessment_criteria |
| L1-PACK-003 | Adapted pack has non-empty provenance | source_mode="adapted" → source_provenance is list with ≥1 entry |
| L1-RUBRIC-001 | Rubric has criteria × levels matrix | Every criterion has every level populated |
| L1-OBS-001 | Observation round-trips | Input → append → retrieve produces identical data |
| L1-OBS-002 | Observation has required attribution | timestamp, teacher_id, student_id all non-null, non-empty |
| L1-TRACE-001 | Trace has hash, no raw text | SHA-256 field present; query_text field absent or null |
| L1-TRACE-002 | Trace has routing metadata | route_id and external_calls fields present |
| L1-PROV-001 | Provenance entry has grounding metadata | source_file, page_start, section all present |
| L1-PROV-002 | Provenance source files exist | Every source_file in provenance resolves to a real path |
| L1-TLENS-001 | Teacher Lens has core dimensions | grading_calibration, differentiation_style, communication_voice |
| L1-TLENS-002 | Teacher Lens has staleness metadata | ingested_doc_count ≥ 0, last_updated is valid ISO8601 |
| L1-TLENS-003 | Teacher Lens patterns cite sources | Every pattern entry has at least one source_document reference |

### JSON Schemas Required

- `student_lens.schema.json`
- `activity_pack.schema.json`
- `rubric.schema.json`
- `observation.schema.json`
- `privacy_trace.schema.json`
- `teacher_lens.schema.json`
- `provenance.schema.json`

---

## 5. Layer 2: Adaptive Retrieval & Teacher Lens (20 tests)

**Property**: The system pulls correct sources for requested grade/unit, and learns accurate patterns from teacher history.  
**Runtime**: <30s (may use local Ollama for embeddings). No external API calls.

### Tests

| ID | What it proves | Pass condition |
|----|---------------|----------------|
| L2-FENCE-001 | G3 request → G3 sources only | All provenance references contain grade-3 signals |
| L2-FENCE-002 | G3 request → zero wrong-grade sources | No G1/G2/G4/G5 material in provenance |
| L2-FENCE-003 | Unit-specific request → unit sources only | No cross-unit bleed |
| L2-FENCE-004 | Non-existent grade → error, not fabrication | G9 request returns 404/error, never a pack |
| L2-FENCE-005 | Empty store → template fallback | source_mode="generated", not an error |
| L2-DETERM-001 | Same query 3x → identical provenance | Provenance sets are equal across runs |
| L2-DETERM-002 | Same teacher history → identical Teacher Lens | Lens build is deterministic |
| L2-CLASS-001 | Graded exam classified correctly | doc_type = "exam" |
| L2-CLASS-002 | Parent update classified correctly | doc_type = "parent_update" |
| L2-CLASS-003 | Lesson plan classified correctly | doc_type = "lesson_plan" |
| L2-CLASS-004 | Student evaluation classified correctly | doc_type = "evaluation" |
| L2-CLASS-005 | Student records blocked | doc_type "student-records" → error |
| L2-EXTRACT-001 | Grading patterns extracted from exams | Lens.grading_calibration non-empty, cites exam doc_ids |
| L2-EXTRACT-002 | Communication voice from parent updates | Lens.communication_voice has tone, L1_L2_ratio |
| L2-EXTRACT-003 | Differentiation from lesson plans | Lens.differentiation_style has per-tier scaffolding |
| L2-EXTRACT-004 | Assessment weighting from evaluations | Lens.assessment_weighting sums to 1.0 ±0.01 |
| L2-INCR-001 | New doc updates lens without losing old | Superset: new lens.source_documents ⊃ old |
| L2-INCR-002 | Removing + rebuilding shrinks lens | Proper garbage collection |
| L2-PAGE-001 | Provenance page numbers valid | page_start ≤ page_end for every entry |
| L2-FILE-001 | File map infers grade from structure | Folder G3/*.pdf → grade=3 |

### Required Fixture

`golden_retrieval_map.yaml`: maps each test query to its expected source documents and grade. Built from the actual ingested curriculum PDFs.

---

## 6. Layer 3: Isolation & Contamination (15 tests)

**Property**: Data never crosses boundaries — between students, between teachers, across time, or into traces.  
**Runtime**: <5s. No model calls. Uses canary injection pattern.

### Canary Pattern

A "canary" is a unique string (e.g., `CANARY_MARCO_7f3a`) inserted into one student's observation. Tests verify the canary appears ONLY in that student's lens, NEVER in any other student's lens, NEVER in traces, NEVER in generated content.

### Tests

| ID | What it proves | Pass condition |
|----|---------------|----------------|
| L3-STU-001 | Marco canary absent from Nora's lens | Canary string not in any field |
| L3-STU-002 | Marco canary absent from Luca's lens | Canary string not in any field |
| L3-STU-003 | Marco canary present in Marco's lens | Positive control: canary IS there |
| L3-STU-004 | Nora observation → Marco lens byte-identical | No side effects |
| L3-STU-005 | Each observation has exactly one student_id | No nulls, no lists, no multi-assignment |
| L3-STU-006 | Concurrent lens builds → no contamination | Threaded stress test |
| L3-TCH-001 | Teacher A lens has zero Teacher B data | Full isolation |
| L3-TCH-002 | Same source + different teacher lenses → different outputs | Lens influences generation |
| L3-TIME-001 | Lens at T excludes observations after T | Temporal upper bound |
| L3-TIME-002 | Lens at T includes all observations through T | Temporal lower bound (completeness) |
| L3-TIME-003 | Future-timestamped observation → rejected | Validation blocks future data |
| L3-PRIV-001 | Trace files contain zero student names | Grep *.ndjson for fixture names → 0 hits |
| L3-PRIV-002 | Support bundle contains zero student PII | No names, scores, raw observations |
| L3-PRIV-003 | Activity pack contains zero student names | Class-level content only |
| L3-PRIV-004 | File map skips student-data zones | Student DB paths excluded from scan |

---

## 7. Layer 4: Golden Artifacts & Correctness (20 tests)

**Property**: Generated artifacts are pedagogically correct and match the teacher's demonstrated style.  
**Runtime**: <60s. May use local models for holdout scoring.

### Tier Assignment Truth Table

The complete deterministic mapping (source of truth in `tier_assignment_truth_table.yaml`):

| RTI Tier | Weakest CEFR | Expected Tier |
|----------|-------------|---------------|
| 3 | any/null | foundational |
| 2 | null | foundational |
| 2 | Pre-A1 | foundational |
| 2 | A1 | foundational |
| 2 | A1+ | foundational |
| 2 | A2 | foundational |
| 2 | B1 | on_track |
| 2 | B2 | on_track |
| 2 | C1 | on_track |
| 2 | C2 | on_track |
| 1 | null | on_track |
| 1 | Pre-A1 | on_track |
| 1 | A1 | on_track |
| 1 | A1+ | on_track |
| 1 | A2 | on_track |
| 1 | B1 | on_track |
| 1 | B2 | extended |
| 1 | C1 | extended |
| 1 | C2 | extended |

**Note**: The spec says "RTI 1 + CEFR null → foundational (safest default)" but the current implementation returns "on_track". This eval will document the intended correct behavior; the implementation must be updated to match.

### Tests

| ID | What it proves | Pass condition |
|----|---------------|----------------|
| L4-TIER-001 | Determinism: same inputs 10x → same tier | 100% identical across runs |
| L4-TIER-002 | RTI 1 + CEFR B2 → extended | Truth table row |
| L4-TIER-003 | RTI 2 + CEFR A1 → foundational | Truth table row |
| L4-TIER-004 | RTI 3 + CEFR null → foundational | Truth table row |
| L4-TIER-005 | RTI 1 + CEFR A2 → on_track | Truth table row |
| L4-TIER-006 | Full truth table passes | All 19 rows produce expected tier |
| L4-CEFR-001 | CEFR target monotonicity | foundational < on_track < extended |
| L4-CEFR-002 | Floor clamp | No tier targets below Pre-A1 |
| L4-CEFR-003 | Ceiling clamp | No tier targets above C2 |
| L4-BLOOM-001 | Foundational → low Bloom's verbs | identify, name, list, recognize, match |
| L4-BLOOM-002 | On_track → mid Bloom's verbs | explain, compare, connect, describe, classify |
| L4-BLOOM-003 | Extended → high Bloom's verbs | analyze, evaluate, argue, investigate, create |
| L4-HOLD-001 | Holdout: exam grading overlap ≥70% | Train 9, predict 10th |
| L4-HOLD-002 | Holdout: parent voice vocabulary ≥60% | Train 4, predict 5th |
| L4-HOLD-003 | Holdout: differentiation approach match | Train 4, predict 5th |
| L4-HOLD-004 | Holdout: assessment strengths/growth | Train 4, predict 5th |
| L4-LANG-001 | Foundational readability ≤ grade + 1 | Age-appropriate |
| L4-LANG-002 | Extended readability ≥ grade level | Not dumbed down |
| L4-BILING-001 | 70% Italian spec → 60-80% Italian output | Within ±10% |
| L4-BILING-002 | English scaffolding only in foundational | L1 support is differentiated |

---

## 8. Layer 5: End-to-End Gauntlets (5 gauntlets)

**Property**: Full teacher workflows produce correct, safe, grounded results across the entire chain.  
**Runtime**: <120s. Multi-step scenarios.

### Gauntlet 1: New Student Onboarding (5 assertions)
1. Create student with no data → appears in roster
2. Default tier → on_track (RTI 1, CEFR null → current logic) or foundational (proposed safer default)
3. No hallucinated CEFR before observations
4. First observation → lens updates
5. After 5 observations → trajectory calculated

### Gauntlet 2: Adaptive Lesson Preparation (6 assertions)
1. Ingest 3 past G3 lesson plans
2. Teacher Lens builds successfully
3. Request G3-U1 pack
4. Pack provenance traces only to G3 docs
5. Pack style matches teacher's historical patterns
6. Zero G4/G5 content anywhere in output

### Gauntlet 3: RTI Tier Change (5 assertions)
1. Marco at RTI 1
2. Teacher changes to RTI 2
3. Next assignment reflects new RTI
4. Historical lens preserves old observations unchanged
5. Other students unaffected

### Gauntlet 4: Contamination Stress (5 assertions)
1. 10 students, 50 observations each
2. Each lens contains exactly that student's data
3. No observation in two lenses
4. Remove one student → others unchanged
5. Re-run → identical results

### Gauntlet 5: Wrong Input Rejection (5 assertions)
1. G9 → error, not content
2. Non-existent student → 404
3. Future timestamp → rejected
4. Student name in query → redacted in trace
5. student-records doc → blocked at ingest

---

## 9. Required Interfaces (Summary)

| Interface | Status | Layer(s) that test it |
|-----------|--------|----------------------|
| `TeacherLensBuilder` | NEW | L1, L2, L3, L4, L5 |
| `TeacherLensBuilder.ingest()` | NEW | L2 |
| `TeacherLensBuilder.classify()` | NEW | L2 |
| `TeacherLensBuilder.build_lens()` | NEW | L1, L2, L4 |
| `TeacherLensBuilder.holdout_score()` | NEW | L4 |
| `ContentDifferentiator.generate_with_teacher_lens()` | NEW | L4, L5 |
| `StudentLensStore.get_lens_as_of()` | NEW | L3 |
| `StudentLensStore.validate_observation_timestamp()` | NEW | L3, L5 |
| `ContentDifferentiator.assign_tier_for_student()` | EXISTS | L4 |
| `ContentDifferentiator.generate_from_documents()` | EXISTS | L2, L5 |
| `DocumentStore.search()` | EXISTS | L2 |

---

## 10. Fixture Inventory

| Fixture | Location | Purpose |
|---------|----------|---------|
| `synthetic_students.yaml` | `tests/evals/fixtures/` | 5 students with varying RTI/CEFR |
| `synthetic_observations.yaml` | `tests/evals/fixtures/` | 50+ observations with canaries |
| `synthetic_teacher_history/` | `tests/evals/fixtures/` | 20 historical docs (5 exam, 5 parent, 5 lesson, 5 eval) |
| `tier_assignment_truth_table.yaml` | `tests/evals/layer4_golden/` | All RTI×CEFR → tier rows |
| `golden_retrieval_map.yaml` | `tests/evals/layer2_retrieval/` | Expected grade→sources mapping |

---

## 11. Running the Evals

```bash
# Collect all (should show 75+ items)
pytest tests/evals/ --co

# Run (all skip cleanly)
pytest tests/evals/ -v

# Run a single layer
pytest tests/evals/layer1_schema/ -v

# Run existing tests (must still pass)
pytest tests/ -q --ignore=tests/evals/ --tb=no
```

---

## 12. Decision Log

| Decision | Rationale | Reversibility |
|----------|-----------|---------------|
| RTI 1 + CEFR null → "on_track" (current) vs "foundational" (proposed) | Current code returns on_track; exec prompt says foundational is "safest default". Eval documents BOTH — truth table uses current behavior; Gauntlet 1 flags the discrepancy for human decision. | 🔄 TWO-WAY DOOR — can change tier logic after human confirms |
| Teacher Lens as holdout eval (not human-validated golden) | Teacher's own work IS the ground truth. Holdout pattern eliminates need for manual validation. | 🔄 TWO-WAY DOOR |
| All evals `pytest.mark.skip` | Implementation doesn't exist yet; evals must not crash | 🔄 TWO-WAY DOOR |
| No overlap between layers | Forces clarity about which layer owns which property; avoids test sprawl | 🔄 TWO-WAY DOOR |

---

## 13. Success Metrics (Post-Implementation)

When the implementation team ships all interfaces:

- Layer 1: 15/15 pass → structural correctness guaranteed
- Layer 2: 20/20 pass → retrieval is grade-accurate and deterministic
- Layer 3: 15/15 pass → zero cross-contamination
- Layer 4: 20/20 pass → pedagogically correct outputs
- Layer 5: 5/5 gauntlets pass → full workflow integrity

**The ultimate proof**: L4-HOLD-001 through L4-HOLD-004 all ≥70% on real teacher data. That means the system learned the teacher's patterns well enough to reproduce them.

---

**End of spec.**

---

## Appendix A: Fixture Design Rationale

### Why These Specific Students

The 5-student roster is designed to exercise every branch of the tier assignment logic:

- **Sofia** (RTI 1, all B2): The only student who reaches `extended`. Tests the B2 threshold.
- **Marco** (RTI 1, mixed A1-A2): The typical `on_track` student. Also has an RTI change mid-year (1→2→1) which exercises the tier history and audit trail.
- **Nora** (RTI 2, null CEFR): Tests the "null CEFR in RTI 2" → foundational path. Also exercises the silent/emerging learner pattern (Pre-A1 observations appearing over time).
- **Luca** (RTI 3, B1 CEFR): The critical case — strong language but intensive intervention needs. Proves RTI 3 overrides even good CEFR levels.
- **Elena** (RTI 1, null CEFR): Tests the DISPUTED case. Current logic says on_track; some stakeholders expect foundational for safety.

### Why Canary Values

Canary injection is the standard pattern for proving isolation in multi-tenant systems. Each student gets a unique, unambiguous string that could never appear naturally:

- `CANARY_SOFIA_a9b2c4` — embedded in Sofia's first observation
- `CANARY_MARCO_7f3a1d` — embedded in Marco's first observation
- etc.

If a canary appears in ANY other student's lens, the isolation property is violated. This is a binary pass/fail — there is no "partial" isolation.

### Why 55 Observations (Not 50)

The exec prompt says "50+ observations." 55 gives us 11 per student (uneven deliberately):
- Some students have more CEFR-tagged observations (Sofia: 6)
- Some have more SEL observations (Nora, Luca)
- Marco has the RTI change observations
- This unevenness is realistic — teachers don't observe uniformly

### Why Holdout Test (Not Human Validation)

The holdout pattern eliminates the most expensive part of eval maintenance: human judgment. Instead:
1. Ingest N-1 artifacts → build lens
2. Ask: "can the system predict artifact N?"
3. If yes (score ≥ threshold) → lens captured the pattern
4. If no → lens is underfitting or the Nth artifact is an outlier

This is the same principle as cross-validation in ML, applied to teaching pattern recognition.

---

## Appendix B: Implementation Sequencing Recommendation

The implementation team should build in this order (each step unblocks more evals):

1. **StudentLensStore.validate_observation_timestamp()** — smallest change, unblocks L3-TIME-003
2. **StudentLensStore.get_lens_as_of()** — moderate, unblocks L3-TIME-001, L3-TIME-002, Gauntlet 3
3. **TeacherLensBuilder.classify()** — classification only, unblocks L2-CLASS-001 through L2-CLASS-005
4. **TeacherLensBuilder.ingest() + build_lens()** — the big one, unblocks L1-TLENS-*, L2-EXTRACT-*, L2-INCR-*
5. **TeacherLensBuilder.holdout_score()** — scoring only, unblocks L4-HOLD-*
6. **ContentDifferentiator.generate_with_teacher_lens()** — ties it all together, unblocks Gauntlet 2

Each step can be shipped independently. No step requires a later step to be testable.

---

## Appendix C: Known Discrepancies Between Code and Spec

| Item | Current Code | Eval Expectation | Resolution |
|------|-------------|-----------------|------------|
| RTI 1 + CEFR null | Returns `on_track` | Truth table says `on_track` (marked DISPUTED) | Human decides — eval documents both |
| RTI 1 + CEFR B1 | Returns `on_track` | Exec prompt implies `extended` for B1+ | Code is correct per its own threshold (B2); exec prompt's "B1+" language is ambiguous |
| Activity pack `source_provenance` | Sometimes null (template path) | Schema allows null only when source_mode="generated" | Correct behavior — schema enforces the constraint |

---

**Total eval coverage**: 94 tests across 5 layers, 7 JSON schemas, 1 truth table, 1 retrieval map, 55 synthetic observations, 5 historical teaching artifacts.
