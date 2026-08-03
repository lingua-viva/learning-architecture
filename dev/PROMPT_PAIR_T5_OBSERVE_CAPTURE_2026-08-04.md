# T5 — Observe Capture Path (Wave 3 — CRITICAL PATH, the demo)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Operator: *"If one thing needs to work tomorrow that is it."*

Prereqs: T0 committed (contracts), HF1 committed (index.html released). Build
against T0 fixtures + lens stubs until T4 lands.
Read first: `dev/CONTRACTS_V1_2026-08-04.md`, `dev/SPEC_T4_LENS_2026-08-04.md`
(if available), `dev/LV_BUILD_BRIEF_2026-08-04.md` §4,
`dev/QA_DEEP_DIVE_CHIP_0.2.32_2026-08-04.md` §F1,
`dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: the Observe region of `static/index.html`, observe/voice endpoints in
`src/web.py`, + tests. Stay out of the Ask and Students regions (T8/T9 own them).

## Phase 1 — Spec prompt

Spec the Observe capture path. Output `dev/SPEC_T5_OBSERVE_2026-08-04.md`, no code.

The flow:
```
mic in Observe → conversational dictation, transcript accumulates
→ teacher says or taps SAVE
→ local LLM parses transcript into the observation JSON structure
→ rendered human-readably, EVERY FIELD EDITABLE IN PLACE
→ teacher edits → confirms
→ lens.merge_observation → vault write → Drive sync queue
```

Cover:
- **Mounting a real mic button in the Observe view** — it never navigates away
  from Observe. Route through the existing `voiceRuntime.captureLocalStt`
  chokepoint (index.html:867) — do NOT add a second STT path. The orphaned
  `toggleObserve()` (:1130) is the starting point. Respect
  `applySttAvailability()` dimming off `/api/voice/probe`.
- **F1 capture hardening**: replace the throttleable `setInterval` VAD
  (index.html:902-912) with an `AudioWorkletProcessor`-based approach (audio
  thread, immune to tab throttling), keeping HF1's visibilitychange/beforeunload/
  max-duration guarantees intact. Long dictation makes this mandatory, not
  optional.
- **Accumulating dictation**: a conversation, not a single utterance. Specify
  start/stop/pause and how the teacher sees what's been captured so far.
- **Parse-on-save only.** Nothing hits the model until the teacher says/taps save.
- **The parse prompt**: transcript → observation JSON with `support_category`
  (Christi's categories), strategy trialed + outcome, strengths/traits, CEFR/SEL.
  Reuse `/api/observe/classify` (web.py:3487 — `writes_made:0`,
  `teacher_confirmation_required:true`) as the parse engine; extend rather than
  duplicate. The model proposes field placement; the teacher corrects it.
- **Inline editing**: every field clickable and changeable in real time — a live
  editable record, not a review-then-commit modal (operator ruling, brief §8.1).
- **Student resolution**: from a student's profile → default that student; from
  Observe → require detection or confirmation; ambiguous → ASK, never guess.
  HF1's placeholder rule (no auto-selected first student) stays.
- **Retire speak-and-commit**: the `/api/voice/act` direct observation save
  (web.py:2795 via ObservationCapturePipeline) is REMOVED. No voice transcript
  reaches `/api/observe/capture` without a form interaction.
- Save → existing toast (+ spoken confirmation — keep it, hands-busy affordance,
  brief §8.4 default) → `lens.merge_observation` → vault → sync queue enqueue
  (queue drain is T6's job; you only enqueue).

## Phase 2 — Implementation prompt

Implement your spec. Acceptance:

- Real mic mounted in Observe; never leaves the view.
- Conversational transcript accumulation through `captureLocalStt`; AudioWorklet
  VAD; HF1 release guarantees still hold (test by backgrounding mid-dictation).
- Parse fires only on save; parsed observation renders human-readably with every
  field editable inline; nothing is written before the teacher confirms.
- Confirm → `lens.merge_observation` → vault write → sync enqueue; every written
  field carries evidence pointing at the observation id.
- Ambiguous student prompts for confirmation; never guesses.
- `/api/voice/act` direct observation save removed — grep-verifiable: no path
  from voice transcript to `/api/observe/capture` that bypasses a form
  interaction. Update/remove the tests that locked the old direct-save behavior;
  add tests locking the new contract.
- Existing tests green; `lv eval teacher-readiness` ≥ 16/19.

Commit ONLY owned files by explicit path, message
`observe: dictation → parse-on-save → editable record → lens merge (T5)`.
