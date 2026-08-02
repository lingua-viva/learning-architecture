# SPEC: Routing Memory — Closing the Loop on Voice + Classification Decisions

**Created**: 2026-08-01
**Status**: DRAFT — operator review before build
**Priority**: 5 of 5 — depends on Spec 1 (categories) + Spec 4 (detection log); wire-in target: `lv audit` / `lv distill`
**Design inputs**:
- `~/Downloads/palette_obligatory_routing_loop_2026-05-26 (1).md` — gap #3: "The EXTRACT step produces gap signals… nothing reads and acts on them." The loop is only a loop if something consumes the signal.
- `~/Downloads/palette_evolutionary_orchestrator_speech (2).md` — the constraint set this spec inherits wholesale (see §Inherited Constraints)

---

## Problem

LV now makes routing decisions on every utterance: intent (observation/generate/question, `classify_intent`), student (Spec 4), category (Spec 1's `suggest_support_categories`). All are deterministic signal lists with hand-set thresholds — correct for launch (**"the smallest system that can be trusted in production"**). But the corrective signal already flowing back is being dropped on the floor:

- Teacher edits `template_type` after a voice save → the intent classifier was wrong, nobody records it
- Teacher confirms/rejects a `model_suggested` category → ground-truth label, discarded after the flip
- Teacher re-assigns a fuzzy-matched student → detection error, invisible
- Clarification asked and answered → the resolution is exactly a labeled training row, gone

At Mission Canvas this same defect class ("detection dies before analyze()") took three sessions to close. LV can have the collection infrastructure from the start — **without** any live adaptation.

## Inherited Constraints (from the evolutionary-orchestrator risk analysis — non-negotiable)

1. **Passive below threshold.** At LV's scale (dozens of utterances/day), no weight or threshold auto-adjusts, ever, in this spec. The layer collects and reports. Activation criteria for a future v2: ≥50 corrected outcomes per decision type — and even then, adjustment lands as a *proposed diff to the signal lists* for operator review, never a runtime mutation. (Speech: "Below threshold, the layer is passive — collecting signal, not adjusting weights.")
2. **Fitness = teacher correction, not "no error."** A saved observation isn't success; an *uncorrected* observation after a teacher saw it is. (Speech risk #2: proxy mismatch — "non-blocked output is not the same as right output.")
3. **Deterministic rules are the floor.** Signal lists in `voice_intent.py` / `observation_capture.py` encode human judgment; the memory layer proposes, humans dispose. (Risk #4: keyword rule erosion.)
4. **Safety gates never enter the loop.** `check_publication_safety`, the never-guess clarification rule, the TTS privacy gate, exit-gate rules — none of these emit fitness signal and none can be de-weighted by it. They are pre/post-routing checks, structurally outside the memory. (The `detectOneWayDoor()` principle.)
5. **Append-only, versioned, replayable.** `routing_memory_v1.ndjson`, schema field in every row, no row ever rewritten; any future weight is a deterministic function of the full history. (Risk: poisoning + debuggability — "read-only at inference time.")

## Design

### 1. Decision records (extends Spec 4's log)

One NDJSON row per routing decision to `LV_ROUTING_MEMORY_PATH` (default `memory/data/routing_memory_v1.ndjson`):

```
{ts, schema: "lv_route_mem_v1", decision_id (UUID), trace_id,
 decision: "intent" | "student_detect" | "category_suggest",
 outcome: <enum per type>, confidence, signals_matched: [signal-list keys only],
 subject_ref: {observation_id | student_id},   # ids only
 corrected: null}
```

**Never stored**: transcripts, student/teacher names, any free text. Signal keys (e.g., `"obs_verb:helped"`) are references into the shipped signal lists — auditable without content.

### 2. Correction capture (the missing half)

Correction events append (never mutate) a paired row `{decision_id, corrected: {...}}`:

- `template_type` edited post-save → intent correction (observation → the edited value)
- Category suggestion confirmed → positive; dismissed/recategorized → negative with the teacher's category
- Student re-assigned on an observation → detection correction
- Clarification answered → resolution row (which candidate won)

Hook points are all existing write paths (observe edit/confirm endpoints, Spec 1 confirm-tap, Spec 4 clarification flow) — each gains one fire-and-forget append call. Correction capture must be invisible to the teacher: zero new UI, zero latency.

### 3. Consumption: `lv audit` integration (closing gap #3)

This is the part the routing-loop doc says everyone skips. Extend `build_audit_report()` / `distill_gap_signals()` (`improvement_audit.py:145–192`) with a routing section:

- **Per decision type**: volume, correction rate, confidence distribution of corrected vs uncorrected decisions
- **Per signal key**: precision proxy — how often decisions matching this signal get corrected ("`gen_verb:make` fired on 12 utterances, 7 corrected to question" → that signal is a candidate for removal)
- **Diversity/collapse watch** (speech risk #3 adapted): if >90% of voice traffic lands on one intent, or a category never fires across 50+ observations with category-relevant corrections, flag it — the signal list has a blind spot, which is a *coverage* gap, not a weight problem
- Output: ranked, human-readable proposals in the existing audit-report format, each citing decision counts + the exact signal-list line it questions. Distilled clusters ride the existing `reconcile_with_candidates` promotion/discard flow

### 4. What v1 explicitly does NOT do

No runtime reads of the memory. No threshold changes. No A/B routing. No per-teacher adaptation. The inference path's only new work is appending log rows. If this spec's diff touches a threshold constant or a signal list, reject the diff.

## Test Plan

1. Every decision type emits exactly one row with valid schema; key-set assertion proves no content fields
2. Correction paths: each of the four hooks appends a paired row referencing the right `decision_id`
3. Append-only: corrections never rewrite decision rows (file line count strictly grows; earlier lines byte-stable)
4. Audit report: synthetic memory file → correct correction rates, per-signal precision, collapse flag at >90% single-intent
5. Log-write failure (read-only path) → voice/act and observe endpoints unaffected (fire-and-forget proof)
6. Unknown schema rows in the file → skipped with count, never crash `lv audit`
7. Hermetic: `LV_ROUTING_MEMORY_PATH` → tmp_path everywhere

## Files

| File | Action |
|---|---|
| `src/lingua_viva/routing_memory.py` | CREATE — record/correction appenders, reader, schema validation |
| `src/web.py` | MODIFY — emit at decision points; correction hooks in edit/confirm endpoints |
| `src/lingua_viva/improvement_audit.py` | MODIFY — routing section in audit/distill |
| `src/lingua_viva/cli.py` | MODIFY — surface routing section in `lv audit` output |
| `tests/test_routing_memory.py` | CREATE |

## Definition of Done

- [ ] Every intent/detection/category decision leaves a content-free, versioned, append-only trace
- [ ] All four teacher-correction paths captured invisibly
- [ ] `lv audit` reports correction rates, per-signal precision, and collapse flags with concrete signal-list proposals
- [ ] Zero runtime behavior change on any routing path (thresholds and signal lists untouched — verifiable by diff)
- [ ] Full suite green

---

*The one-sentence version: LV's routers stay dumb and trustworthy; the system starts remembering when teachers disagree with them; and `lv audit` turns that memory into proposals a human approves. Evolution with the operator as the selection pressure.*
