# SPEC: Live Observation Capture — Mic → Text → Field-Fill → Lens (LV-OBSERVE-LIVE-0)

**Date**: 2026-07-22
**Status**: DRAFT — proposed, not built
**Author**: Claude (this session)
**Trigger**: Operator wants the existing mic button in Observe to do more than dictate
into a blank textbox — speech should get mapped to the right student-lens fields
automatically, and the teacher should be able to see the student's current lens while
they're speaking. Explicitly scoped small: "keep it simple and working at all for now."
**Scope**: One new backend classification step + reusing the existing lens-rendering
code in the Observe view. No new storage, no new schema, no change to the append-only
write path.
**Risk level**: LOW — the existing `append_observation()` write path is untouched; the
only new thing is an LLM call that *pre-fills form fields a teacher already reviews and
edits before hitting Save*, exactly as they do today.
**Blocks**: Nothing. **Blocked by**: nothing — everything this spec needs already ships.

---

## 1. The Problem

Today, `Observe` (`static/index.html:756-807`) already has a mic button. It calls the
browser's native `SpeechRecognition` API (`startSpeech()`, lines 778-794) to dictate text
into a textarea — that part already works and needs no changes. But everything after
that is manual: the teacher must know, and correctly pick, which CEFR skill and level the
sentence they just said maps to, from two dropdowns (`obs-dim`, `obs-level`, lines
767-768), before `saveObservation()` (lines 796-807) POSTs the fixed shape
`{student_id, transcript, cefr_dimension, cefr_level_observed}` to
`/api/observe/capture`.

That's real friction for what should be a fast, in-the-moment capture: a teacher
watching a student struggle with past tense mid-lesson has to stop, mentally categorize
what they just said into the app's taxonomy, then click the right dropdowns. The ask is
to remove that categorization step — say what you saw, let the app figure out where it
goes — and to show the student's current lens alongside the capture form so the teacher
has context while they're observing, not just after the fact via the roster view.

## 2. What Already Exists (do not rebuild)

| Piece | File | Status |
|---|---|---|
| Mic → text dictation (on-device, browser-native, no server round-trip) | `static/index.html:778-794` (`startSpeech()`) | SHIPPED — reuse as-is, zero changes |
| Manual Observe capture form (student picker, transcript box, CEFR dropdowns, Save) | `static/index.html:756-807` | SHIPPED — this spec pre-fills it, does not replace it |
| `POST /api/observe/capture` → `ObservationCapturePipeline.capture()` | `src/web.py:680-714`, `src/education/observation_capture.py:66-150` | SHIPPED — unchanged. Tag fields (`cefr_dimension`, `cefr_level_observed`, etc.) are taken as **explicit request values, never inferred**, "per the build rule against guessing CEFR/RTI classifications" (`observation_capture.py:84-90`) |
| `Observation` dataclass + valid enums (`VALID_TEMPLATE_TYPES`, `VALID_CEFR_DIMENSIONS`, `VALID_CEFR_LEVELS`, `VALID_SEL_VALENCE`) | `src/education/student_lens.py:56-103` | SHIPPED |
| `append_observation()` — append-only write, recalculates snapshot + RTI rules | `src/education/student_lens.py:303-365` | SHIPPED, untouched by this spec |
| Lens read + rendering (`cefr_snapshot`, `rti_current_tier`, `sel_summary`, last-3 observations, `avoid_pairing_with`) | `GET /api/students/{id}/lens` (`src/web.py:791-805`) + `loadLens()` (`static/index.html:809-837`) | SHIPPED, currently only reachable from the roster view — this spec reuses it inside Observe |
| LLM calling convention (Ollama-first, OpenAI-compatible, graceful no-model degrade) | `src/lingua_viva/reasoning.py` `ReasoningEngine.reason()` | SHIPPED — reuse as-is |
| The one existing "unstructured text → verified/needs_confirmation fields" engine | `src/lingua_viva/extraction_engine.py` | SHIPPED, but scoped to whole-lens fields (`STUDENT_LENS_FIELDS`) extracted from **files**, not per-observation tags from a **single spoken utterance** — different input shape, same design pattern worth reusing |

**Conclusion**: the missing piece is a small classification step between "teacher
finished talking" and "teacher hits Save" — nothing upstream (mic, dictation) or
downstream (write path, RTI rules, lens recompute) needs to change.

## 3. The Pipeline (v1, deliberately minimal)

```
[Mic → text]  →  [LLM field-fill — NEW]  →  [Teacher reviews/edits pre-filled form]  →  [Save — unchanged]
  (done)             this spec                  same form, same button                same POST, same pipeline
```

1. Teacher picks a student (existing dropdown), taps mic, speaks. `startSpeech()`
   fills the transcript textarea — **unchanged**.
2. **New**: on transcript-ready (mic stop, or a new "Suggest" button if auto-fire on
   every pause proves too eager — implementer's call), the frontend calls a new
   endpoint, `POST /api/observe/classify`, with `{student_id, raw_transcript}`.
3. The backend calls `ReasoningEngine().reason()` once (same call shape as
   `extraction_engine.py`'s `_propose_fields()`), with a system prompt that gives the
   model the transcript, the valid enums from `student_lens.py`
   (`VALID_TEMPLATE_TYPES`, `VALID_CEFR_DIMENSIONS`, `VALID_CEFR_LEVELS`,
   `VALID_SEL_VALENCE`), and asks it to propose, for **this one utterance only**:
   `template_type`, and whichever of `cefr_dimension` / `cefr_level_observed` /
   `cefr_direction` / `sel_domain` / `sel_valence` / `urgency_flag` apply. Anything the
   model can't confidently place is left `null` — the model is instructed to leave
   fields blank rather than guess, mirroring `extraction_engine.py`'s existing
   grounding discipline.
4. The response **pre-fills the same dropdowns and fields the manual form already
   has**. Nothing is written yet. The teacher sees what the app inferred, corrects
   anything wrong (including "the model got the whole thing wrong, I'll just fill it
   in myself" — the manual path still works, untouched), and hits the same **Save**
   button as today.
5. **Save behaves exactly as it does now** — same `saveObservation()` →
   `/api/observe/capture` → `ObservationCapturePipeline.capture()` →
   `append_observation()`. No new write path, no new validation, no new tables.

This is the load-bearing simplification: **the LLM never writes anything.** It only
autofills form fields a human already reviews before the existing, unchanged Save
action fires. That sidesteps the entire "verified / needs_confirmation / unsupported"
status machinery `extraction_engine.py` needed for *unattended* file-batch ingestion —
here, every proposal passes through a human in the same click they'd make anyway, so v1
needs no separate confirmation UI at all. If usage shows teachers rubber-stamping bad
suggestions without reading them, that's the trigger for a v2 confidence/highlight
treatment — not needed to ship v1.

## 4. Field-Fill Target: mirrors `Observation`, not a new schema

No new dataclass, no new store. The classifier's output shape is exactly the
already-optional fields on `Observation` (`student_lens.py:76-103`):

| Field | Source of truth for valid values |
|---|---|
| `template_type` | `VALID_TEMPLATE_TYPES` — `literacy, cefr, sel_incident, sel_positive, rti_flag` |
| `cefr_dimension` | `VALID_CEFR_DIMENSIONS` — `reading, writing, speaking, listening` |
| `cefr_level_observed` | `VALID_CEFR_LEVELS` — `A1..C2` |
| `cefr_direction` | free text convention (`progressing`/`plateaued`/`regressing`/`mixed`) — left `null` unless the utterance itself states a trend ("she's improved" vs. a single-point remark) |
| `sel_domain` | free text label (no enum in `student_lens.py`) |
| `sel_valence` | `VALID_SEL_VALENCE` — `positive, concern, neutral` |
| `urgency_flag` | bool |

`raw_transcript` is passed through unedited (the teacher can hand-edit the text box
same as today) — the classifier never rewrites what was said, only tags it.

## 5. Hard Rules (carried over from existing frozen decisions, not new)

- **`urgency_flag` proposals must always render as an explicit, visible checkbox the
  teacher affirms** — never auto-checked silently, never hidden behind a generic
  "looks good" confirm. `urgency_flag=True` triggers RTI Rule B
  (`immediate_notification`, `student_lens.py:626-632`) the moment `append_observation`
  runs, so a false-positive here has real downstream effect. Same logic as the frozen
  `trauma_flag` rule in `SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` §4 — a different
  field, same principle: anything that triggers escalation must be human-affirmed, not
  inferred-and-trusted.
- **`trauma_flag` is out of scope for this pipeline entirely.** It isn't part of
  `Observation` — there is no updater for it anywhere in `student_lens.py` today (only
  set once, at `create_lens()`). This spec does not add one. If a spoken observation
  sounds trauma-relevant, the UI should surface it as a plain-text flag for the teacher
  to act on manually (e.g. "this sounded like it may need a trauma-flag conversation —
  update the student's profile directly"), not attempt to write a field that has no
  write path.
- **No change to `observation_capture.py`'s existing rule** that tags are accepted "as
  explicit values rather than inferring them with an LLM" — this spec doesn't violate
  that rule, it satisfies it a different way: the LLM's proposal *becomes* the explicit
  value only once a human looks at the pre-filled form and hits Save. The pipeline
  still never trusts an LLM output it hasn't shown a person.
- **Never block on a missing/unavailable model.** If `ReasoningEngine.reason()`
  degrades to `model_used="none"` (already its documented behavior,
  `reasoning.py:69-75`), `/api/observe/classify` returns an empty/all-null proposal —
  the form falls back to exactly today's blank-dropdown manual entry. The feature is
  additive convenience, never a hard dependency for capturing an observation at all.

## 6. Lens Visualization (the other half of the ask)

No new backend work: `GET /api/students/{student_id}/lens` already returns everything
needed (`cefr_snapshot`, `rti_current_tier`, `sel_summary`, last observations,
`avoid_pairing_with`) via `export_lens()`. Today this only renders in the roster view
(`loadLens()`, `static/index.html:809-837`).

**Change**: call the same `loadLens()` render path from within the `Observe` view,
keyed off the same student-picker dropdown Observe already has, so the teacher sees the
student's current lens (skills snapshot, RTI tier, recent observation history) in the
same screen where they're capturing a new one — not a second navigation away. Layout is
implementer's call (side-by-side panel vs. collapsible section above the capture form);
functionally this is wiring, not new logic.

## 7. What Is Explicitly Deferred (not in scope for v1)

- Any auto-confirmation / auto-write path for LLM-proposed tags — every proposal goes
  through the existing manual Save click, always. No "verified" tier for this pipeline
  yet (contrast with `extraction_engine.py`, which does need one because it runs
  unattended over file batches).
- Multi-turn / conversational disambiguation ("did you mean 3rd or 4th grade?") — same
  deferral already stated in `SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` §6, semantic
  engine work, ~2 weeks out per operator.
- Continuous/streaming mic capture, diarization, or multi-student-in-one-session
  parsing — v1 assumes one student selected, one utterance, one Save, same as today.
- Any addition to `Observation`'s field set or a `trauma_flag` updater — both out of
  scope; flagged as future work only if the operator decides it's needed.
- Confidence-scored or highlighted UI treatment of which proposed fields the model was
  unsure about — v1 shows one flat pre-filled form; revisit only if rubber-stamping
  becomes a real observed problem.

## 8. Build Order

1. `POST /api/observe/classify` — new `src/web.py` route, calls
   `ReasoningEngine().reason()` with a system prompt scoped to §4's field list. Returns
   the proposal dict, nothing else. No DB writes.
2. Frontend: wire the mic-stop (or a "Suggest" button) to call this endpoint and
   pre-fill the existing dropdowns/checkboxes in the Observe form. `saveObservation()`
   itself does not change.
3. Frontend: render the existing `loadLens()` panel inside the `Observe` view, driven
   by the same student-picker.
4. Update `dev/INDEX.md` with this spec's status once built.

## 9. Definition of Done

- [ ] `/api/observe/classify` exists, degrades gracefully with no model available,
      makes zero writes
- [ ] Observe form's CEFR/SEL/urgency fields pre-fill from the proposal but remain
      fully editable before Save
- [ ] `urgency_flag` always renders as an explicit affirm-or-not checkbox, never
      silently pre-checked-and-hidden
- [ ] Existing manual entry (no mic, type/pick everything by hand) still works
      unchanged
- [ ] `saveObservation()` / `/api/observe/capture` / `append_observation()` are
      byte-for-byte unmodified by this work
- [ ] Current lens snapshot renders inside the Observe view for the selected student
- [ ] `dev/INDEX.md` updated

## 10. Provenance

Grounded in live inspection this session: `student_lens.py` (full file — `Observation`
dataclass, valid enums, append-only guarantee confirmed against
`tests/test_student_lens.py`'s `test_observations_are_append_only`), `observation_capture.py`
(explicit no-LLM-inference rule at lines 84-90), `static/index.html`'s Observe view
(`startSpeech()`, `saveObservation()`, `loadLens()`), `src/web.py`'s `/api/observe/*`
and `/api/students/{id}/lens` routes, `reasoning.py`'s `ReasoningEngine` calling
convention, and `extraction_engine.py` as the closest existing precedent for
"unstructured input → schema-shaped fields via LLM," whose verified/needs_confirmation
machinery this spec deliberately does *not* copy wholesale — that engine runs
unattended over files, this one always has a teacher in the loop before a single
byte is written.
