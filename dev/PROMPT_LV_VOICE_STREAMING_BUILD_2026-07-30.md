# Build Prompt - Voice Query Streaming + Early Sentence TTS

You are building the remaining voice-loop gap: the Ask voice path should have a streaming
query response surface and start spoken playback from the first complete answer sentence.
Read the spec first:

```text
dev/SPEC_LV_VOICE_STREAMING_2026-07-30.md
```

## Hard Prerequisites

1. Run the full test suite before editing. The handoff says the targeted voice/GIR tests passed
   but the full suite had not been run yet.
2. Verify the GIR prerequisite is present:

```bash
grep -n "gir_score\|voice_tone" memory/schema/path.py
grep -n "Step 6.25: GROUND" src/pipeline.py
```

If either check fails, stop and report that the earlier GIR build is not actually landed.

## Critical Rules

1. **Do not commit.** The operator owns the one dedicated commit window for this repo.
2. **Keep `/api/query` compatible.** Existing typed Ask, tests, and clients expect one JSON
   response. Add `/api/query/stream`; do not replace `/api/query`.
3. **Do not recompute GIR in `web.py`.** The stream and JSON route must read
   `result.grounding`, `result.path_record.gir_score`, `result.path_record.gir_method`, and
   `result.path_record.voice_tone`.
4. **Be honest about streaming depth.** `ReasoningEngine` is not token-streaming yet. This
   build creates the SSE/event contract and early sentence TTS once synthesis is available.
   Do not make provider adapter changes in this slice.
5. **Do not weaken the TTS privacy gate.** Spoken segments still go through
   `/api/voice/tts`; student-data text must still fall back to browser-local speech.
6. **No raw query text in new SSE lifecycle payloads.** The final answer is user-visible, but
   lifecycle events should not add new exposure.

## Build Steps

### Step 0: Baseline tests

Run:

```bash
pytest -q
```

Read the output. If it fails, identify whether the failure is pre-existing before editing.

### Step 1: Extract shared query response assembly

In `src/web.py`, extract the success-body assembly currently inside `/api/query` into a helper
that both routes can call. Preserve:

- trace append
- privacy log event
- external/local route derivation from the actual model
- `gir_score`, `gir_method`, `voice_tone`, `tone_prefix`
- session increment behavior
- broadcaster final-result behavior

Do not call `build_grounding_result()` from this helper.

### Step 2: Add SSE helpers and route

Add `StreamingResponse`, `_sse()`, `_answer_sentences()`, and `POST /api/query/stream`.

The route should validate missing `query` with a normal 400 JSON response before opening the
stream. Once streaming starts, yield:

1. `query_received`
2. `status` with `stage: "thinking"`
3. after `run_teacher_query()`, `status` with `stage: "grounding"`
4. one or more `answer_sentence` events
5. final `result`

Timeout and import errors should yield `error` SSE events with the same teacher-facing wording
as `/api/query`.

### Step 3: Frontend streaming path for voice Ask

In `static/index.html`, leave typed Ask on the existing blocking path. For `fromVoice === true`,
call the streaming helper if `ReadableStream` is available; otherwise fall back to the current
blocking flow.

Implement a small POST-fetch SSE parser:

- `fetch("/api/query/stream", {method: "POST", headers, body})`
- `response.body.getReader()`
- decode chunks with `TextDecoder`
- split buffered events on blank lines
- parse `event:` and `data:` fields

### Step 4: Early sentence TTS queue

The existing `voiceRuntime.speak()` cancels current audio at the start, so do not call it for
every streamed sentence. Add a queue/chaining helper that speaks the first sentence when the
first `answer_sentence` event arrives and then speaks later queued sentences without overlap.

Keep the prefix behavior simple and testable:

- apply `tone_prefix` to the first spoken segment
- do not duplicate it on later segments
- keep browser-local fallback prefix-preserving

### Step 5: Tests

Add/update tests for:

- backend SSE happy path with monkeypatched `run_teacher_query()`
- backend SSE timeout/error event
- `/api/query` compatibility after helper extraction
- frontend contract strings: `"/api/query/stream"`, `getReader()`, `answer_sentence`, and the
  queue helper

Run targeted tests first, then full suite:

```bash
pytest -q tests/test_teacher_api_phase2.py tests/test_voice_tts_privacy_gate.py tests/test_ui_contract.py
pytest -q
```

## Verification Summary To Report

Report:

- baseline full-suite result before edits
- files changed
- targeted test result
- final full-suite result
- explicit limitation: this is SSE sentence streaming after pipeline completion, not provider
  token streaming yet

Stop and flag any privacy-gate regression, duplicate GIR computation, or breaking change to
the existing `/api/query` JSON shape.
