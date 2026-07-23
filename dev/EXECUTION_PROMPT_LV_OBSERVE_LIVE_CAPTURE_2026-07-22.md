# Prompt: LV Observe Live Capture — Implementation

Copy everything below the line into a fresh agent session, run from the repo root
(`lingua-viva`). No network access needed beyond whatever local model endpoint is
already configured (Ollama at `localhost:11434` by default).

---

You are implementing a small, additive feature in the Lingua Viva (`lingua-viva`)
repo. This is a **build task**, not a review — patch first, test second, explain
third. Do not stop at design unless genuinely blocked.

**Required reading, in order**:
1. `CLAUDE.md` (repo root) — publication-safety rules and repo architecture. You are
   bound by these for anything you write.
2. `dev/specs/SPEC_LV_OBSERVE_LIVE_CAPTURE_2026-07-22.md` — the full spec. Read it
   whole; §3 is the pipeline you're building, §4 is the exact field list, §5 is the
   hard rules (do not skip — one of them, `urgency_flag`, gates real downstream
   behavior), §7 is an explicit exclusion list (don't build any of it), §8 is your
   build order.
3. `src/education/student_lens.py` — read the `Observation` dataclass (lines 76-103)
   and the `VALID_*` enum constants (lines 56-60) in full. This is the exact field
   surface you're filling; do not invent new fields or rename any of these.
4. `src/education/observation_capture.py` (lines 66-150) — note the existing comment
   about tags being accepted as explicit values, never LLM-inferred. Your work does
   not violate this (see spec §5) — understand *why* before you touch anything near
   this file, since it is easy to accidentally cross that line by making the
   classify step write instead of just propose.
5. `static/index.html` — read the current Observe view in full: `startSpeech()`
   (~lines 778-794), the capture form markup (~lines 756-776, student picker,
   textarea, `obs-dim`/`obs-level` dropdowns), `saveObservation()` (~lines 796-807),
   and `loadLens()` (~lines 809-837, the roster-view lens renderer you're reusing).
6. `src/web.py` — read the existing `/api/observe/capture` route (~lines 680-714)
   and `GET /api/students/{student_id}/lens` (~lines 791-805) so your new route
   matches this file's existing conventions (error handling, response shape).
7. `src/lingua_viva/reasoning.py` — read `ReasoningEngine.reason()` (lines 31-75) and
   how `extraction_engine.py`'s `_propose_fields()` calls it (lines 256-280) — match
   this calling convention exactly rather than inventing a new one.

**The task in one sentence**: add `POST /api/observe/classify`, which takes a
transcript and returns a proposal for the Observe form's tag fields via one LLM call,
and wire the frontend to pre-fill the existing form with that proposal and to render
the existing lens panel inside the Observe view — nothing else changes.

**Scope, precisely** (spec §8 build order):
1. New route `POST /api/observe/classify` in `src/web.py`. Request:
   `{student_id, raw_transcript}`. It builds a system prompt listing
   `VALID_TEMPLATE_TYPES`, `VALID_CEFR_DIMENSIONS`, `VALID_CEFR_LEVELS`,
   `VALID_SEL_VALENCE` (imported from `student_lens.py`, not re-typed as string
   literals) and instructs the model to propose `template_type`, `cefr_dimension`,
   `cefr_level_observed`, `cefr_direction`, `sel_domain`, `sel_valence`,
   `urgency_flag` for this one utterance, leaving anything uncertain `null` rather
   than guessing. Calls `ReasoningEngine().reason(...)` once, same pattern as
   `extraction_engine.py`'s `_propose_fields()`. Parses strict JSON out; if parsing
   fails or the model degrades to `model_used="none"`, return an all-null proposal —
   never raise, never block. **Makes zero database writes.**
2. Frontend: on transcript-ready (your call whether that's mic-stop or a new small
   "Suggest" button next to the mic — pick whichever is less likely to fire
   annoyingly mid-sentence), call the new endpoint and pre-fill `obs-dim`/`obs-level`
   and any new SEL/urgency controls you add to the form with the proposal. All
   fields remain fully editable. `saveObservation()` itself must not change — it
   still just reads whatever is currently in the form fields and POSTs to
   `/api/observe/capture` exactly as today.
3. Frontend: render the existing `loadLens()` panel inside the `Observe` view,
   driven by the same student-picker dropdown Observe already has — so selecting a
   student shows their current lens (skills snapshot, RTI tier, recent
   observations) right there, not just in the roster tab. Reuse the existing
   `GET /api/students/{id}/lens` call and rendering logic; don't duplicate it into
   a second implementation — factor it into a shared function if it isn't already
   one.
4. Update `dev/INDEX.md`'s row for `SPEC_LV_OBSERVE_LIVE_CAPTURE` with your actual
   build status and evidence once done.

**Hard constraints**:
- `urgency_flag` must always render as an explicit checkbox the teacher affirms —
  never pre-checked-and-hidden, never silently defaulted from the proposal without
  the teacher seeing it. It triggers RTI Rule B (`immediate_notification`,
  `student_lens.py:626-632`) the instant `append_observation` runs.
- Do not add a `trauma_flag` updater or attempt to write to `trauma_flag` from this
  pipeline. It is not part of `Observation` and has no update path in
  `student_lens.py` today (spec §5) — out of scope, full stop. If you think the
  model output implies something trauma-relevant, surface it as a plain-text note
  for the teacher to act on manually, not as a field write.
- Do not modify `append_observation()`, `saveObservation()`'s POST target/shape, or
  `/api/observe/capture`'s existing behavior. The classify endpoint is purely
  additive — if you find yourself editing the write path, you've drifted out of
  scope.
- Do not build anything from spec §7's exclusion list (no auto-write/verified tier,
  no multi-turn disambiguation chat, no streaming/diarization, no new
  `Observation` fields, no confidence-highlighted UI).
- The classifier must degrade to a fully-manual, fully-functional form when no local
  model is available — verify this by testing with Ollama stopped/unreachable, not
  just by reading the degrade-path code.
- Publication safety (`CLAUDE.md`): no real student data, no institution names, no
  colleague names anywhere you touch, including test fixtures.
- Leave your changes **uncommitted** — the operator holds the sole commit window in
  this repo. Do not run `git commit`.

**Verification, before you call this done**:
- Run the full test suite, report pass/fail counts before and after, and account for
  any new failures (don't wave off unfamiliar reds without checking whether they're
  pre-existing/platform-specific per `dev/INDEX.md`'s recent reports).
- Add at least one test for the new endpoint: a normal proposal, a malformed/empty
  transcript, and the no-model-available degrade path.
- Manually run the app (`python3 -m src.lv_cli serve 8787` or whatever this repo's
  current serve command is — check `dev/INDEX.md`/`README.md` if unsure) and
  live-walk: pick a student, dictate or type an observation, confirm the form
  pre-fills, confirm you can still override every field, confirm Save still writes
  correctly (check the student's lens updated), confirm the lens panel renders
  inside Observe for the selected student.
- Confirm manual entry with the LLM step skipped/failed still works end-to-end —
  this must never become a hard dependency for saving an observation.

When done, give a short final message (under 200 words): what changed (file:line
references), test counts before/after, what you manually verified in the running
app, and nothing else. No restated framing.
