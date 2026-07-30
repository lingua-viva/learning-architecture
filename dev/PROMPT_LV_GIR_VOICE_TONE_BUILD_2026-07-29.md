# Build Prompt — GIR → Voice Delivery Tone

You are wiring grounding-awareness into Lingua Viva's spoken responses. Read the spec first:

```
dev/SPEC_LV_GIR_VOICE_TONE_2026-07-29.md
```

## Why This Matters

Lingua Viva speaks answers aloud to teachers and, indirectly, to children. Right now a
thin, poorly-sourced answer is spoken in exactly the same voice as a well-grounded one.
The grounding machinery (`build_grounding_result()`) already exists — it's just never
called before the moment of truth, and never reaches the voice output. This is a wiring
task, not new architecture. Do not build a bigger system than the spec describes.

## Critical Rules

1. **Do not touch the golden-workflow grounding call** at
   `src/lingua_viva/golden_workflows/runner.py:55` — it's independent of the live
   pipeline path and out of scope here. Verify it still passes after your changes; do
   not modify it.
2. **Compute GIR once, inline, in `pipeline.py`.** Do not add a second computation
   elsewhere. The `/api/query` route in `web.py` should *read* the result already
   attached to `PipelineResult`, not recompute it. This is the "verdict, not
   reconstruction" rule — if you find yourself calling `build_grounding_result()` more
   than once per request, stop and re-read the spec.
3. **`voice_tone.py` is a pure function module.** No pipeline imports, no web imports,
   no I/O. It takes a float, returns a dict. Keep it that way so it's trivially
   unit-testable.
4. **Don't touch the sequential STT → query → TTS architecture.** That's a separate,
   already-identified gap (no streaming/early-TTS). This build makes the eventual
   spoken answer more honest, not faster. Resist the urge to fix both at once.
5. **The privacy gate in `/api/voice/tts` (`check_publication_safety`) must still run on
   the full text**, including any prepended tone prefix, before the character-limit
   check and before the Rime call. Do not reorder this.
6. **Don't invent new GIR thresholds without flagging it.** Ship with the 0.8/0.4
   starting values from the spec. If you think they're wrong, say so in your summary —
   don't silently change them.

## Build Steps (do in order, run tests after each)

### Step 0: Schema — `PathRecord` grounding fields

`memory/schema/path.py`: add `gir_score: float = 1.0`, `gir_method: str = ""`,
`voice_tone: str = "plain"` to the `PathRecord` dataclass. Update `to_dict()` and
`from_dict()` to include them. Run `pytest -q tests/ -k path` (or the relevant schema
test file) before moving on.

### Step 1: Inline GIR computation in `pipeline.py`

In `src/pipeline.py`, right after the SYNTHESIZE step (`steps_executed.append("SYNTHESIZE")`
at line ~916) and before the REHYDRATE block, call `build_grounding_result()` using
`classification`, `synthesis_result`, `query`, `query_hash`, `session_id` — all already
in scope at that point (see the spec's exact snippet).

- Add `grounding: Optional[GroundingResult] = None` to the `PipelineResult` dataclass
  (~line 147-157).
- Populate `path_record.gir_score`, `path_record.gir_method`, `path_record.voice_tone`
  when constructing `PathRecord` in the STORE step (~line 937-953). Use
  `resolve_voice_tone()` from Step 2 to get `voice_tone` — meaning Step 2 must exist
  before this line compiles cleanly; write `voice_tone.py` first if your editor order
  differs from this doc's.
- Return `grounding=grounding` in the `PipelineResult(...)` constructor (~line 960).

### Step 2: Tone resolver

Create `src/lingua_viva/voice_tone.py` exactly as specified — `resolve_voice_tone(gir_score: float) -> dict` returning `{"tone": ..., "prefix": ...}` with the three tiers
(plain ≥0.8, clarify 0.4-0.8, name_boundary <0.4). Copy the docstring noting the
threshold-calibration caveat.

### Step 3: `/api/query` reads the inline result

In `src/web.py`, replace the post-hoc `build_grounding_result()` call (lines
~3996-4013) with reading `result.grounding` and `result.path_record.voice_tone` /
`result.path_record.gir_score`. Add `gir_score`, `gir_method`, `voice_tone`,
`tone_prefix` to the JSON response payload. Delete the now-redundant `try/except`
grounding-recompute block — don't leave dead code behind.

### Step 4: `/api/voice/tts` accepts a tone prefix

In `src/web.py`'s `voice_tts()` (~line 1709), accept an optional `tone_prefix` field
in the POST body. If present and non-empty, prepend it to `text` **before** the
`check_publication_safety()` gate call and before the `RIME_MAX_CHARS` length check.

### Step 5: Frontend wiring

In `static/index.html`:
- Where the `/api/query` response is handled, capture `tone_prefix` from the response.
- Update `speak(text)` (~line 829) to accept the prefix and include `tone_prefix` in
  the POST body sent to `/api/voice/tts`.
- Ensure the browser-TTS fallback (`speakLocally`, used for student-data text) also
  receives prefix-prepended text — search for where it's called and confirm the prefix
  survives that path too. This matters: low-GIR answers *about* a specific student are
  exactly the ones that hit the privacy fallback, so don't let the hedge silently drop
  there.

### Step 6: Tests

- `tests/test_voice_tone.py` (new): unit tests for all three threshold tiers plus the
  boundary values (exactly 0.8, exactly 0.4).
- Add/update a test confirming `/api/query`'s response includes `gir_score` sourced
  from the inline pipeline computation (not a second `build_grounding_result()` call —
  you can assert this by checking the route no longer imports `build_grounding_result`
  directly, since it now only reads `result.grounding`).
- Add/update a test confirming `/api/voice/tts` prepends `tone_prefix` when supplied.

## Verification

1. `pytest -q tests/` — full suite green.
2. `python3 -m src.lingua_viva.cli health` (or equivalent Doctor check) passes.
3. Manual: ask a question with strong knowledge-base coverage → response spoken
   plainly, no prefix, `voice_tone: "plain"` in the network response.
4. Manual: ask a thin-coverage question → hedging prefix audible, `voice_tone` is
   `"clarify"` or `"name_boundary"`.
5. Confirm `tests/` covering `golden_workflows/runner.py` still pass unchanged.
6. Confirm student-data queries still route to local fallback TTS with the prefix
   intact — this is a privacy-adjacent path, verify by hand, don't just trust the diff.

## What NOT To Build

- No chat-UI trust badge (visual indicator) — spoken tone only, for this pass.
- No `VoiceBridge` class or broader VIU system — the resolver is a single pure function.
- No streaming/early-TTS changes.
- No golden-voice-loop instrument or gap→eval enrichment — both explicitly deferred in
  the spec, both depend on this landing first.

If you hit a design question not covered here or in the spec (e.g. the resolver
thresholds look clearly wrong against real data, or `query_hash`/`trace_id` naming
doesn't line up cleanly between `pipeline.py` and `grounding/build.py`), stop and flag
it rather than improvising a bigger fix.
