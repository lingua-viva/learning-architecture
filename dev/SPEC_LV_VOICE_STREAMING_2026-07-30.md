# SPEC: Voice Query Streaming + Early Sentence TTS

**Date**: 2026-07-30
**Status**: DRAFT - operator review before build
**Lens**: runtime/product truth (primary), protection (privacy-preserving voice path)
**Depends on**: `dev/SPEC_LV_GIR_VOICE_TONE_2026-07-29.md` must already be built - this
streaming slice preserves `gir_score`, `voice_tone`, and `tone_prefix` from the inline
pipeline result instead of recomputing grounding.
**Branch**: `feat/lv-voice-streaming`
**Priority rationale**: item 1 of the remaining voice gaps. The Ask voice path is still
strictly serial: browser MediaRecorder -> `/api/voice/stt` -> `/api/query` -> `/api/voice/tts`,
with each request awaiting a complete response before the next begins. That makes spoken
answers feel stalled even when the backend is working.

---

## What Already Exists (verified by reading, not assumed)

| Component | Status | Location |
|---|---|---|
| Browser voice capture -> STT | Built, blocking | `static/index.html:681-812` posts recorded audio to `/api/voice/stt` |
| Spoken playback | Built, blocking Rime call with browser fallback | `static/index.html:829-849`, `src/web.py:1709-1789` |
| Ask submit flow | Built, blocking `/api/query` call | `static/index.html:1836-1889` |
| `/api/query` route | Built, returns one JSON response after full pipeline completion | `src/web.py:3944-4059` |
| GIR/tone fields in response | Built | `src/web.py:4002-4039` |
| Inline GIR in pipeline | Built | `src/pipeline.py:920-996` |
| Reasoning client | Built, **not streaming** | `src/lingua_viva/reasoning.py:31-150` uses blocking chat-completion calls via `asyncio.to_thread` |
| SSE/streaming route | Missing | `rg "StreamingResponse|text/event-stream|EventSource" src static/index.html` returns no live route/UI implementation |

## The Gap

The current voice path serializes the full interaction:

1. Wait for complete local STT JSON.
2. Wait for complete `/api/query` JSON after `run_teacher_query()` finishes.
3. Only then call `/api/voice/tts` with the full answer.

There is no server-sent event stream, no lifecycle feedback from the query route, and no
frontend path that starts speech when the first complete answer sentence is available.
The user hears nothing until all reasoning, synthesis, grounding, response JSON parsing,
and TTS request setup are finished.

## Design Decision

Build an SSE envelope around the real `/api/query` path now, but do not pretend this is
provider-token streaming.

`ReasoningEngine._call_model()` currently posts to OpenAI-compatible chat completions
without `"stream": true` and reads the full response body before returning
(`src/lingua_viva/reasoning.py:103-150`). Adding true token streaming there would touch
provider adapters, local-only privacy behavior, tracing, synthesis, and pipeline contracts.
That is a larger engine change than this voice-loop slice.

This spec's first slice therefore does three concrete things:

1. Adds `/api/query/stream`, an SSE route that emits query lifecycle events and then emits
   complete answer sentences as `answer_sentence` events once the pipeline result exists.
2. Updates the voice frontend to use `/api/query/stream` for voice-originated Ask requests
   and to start TTS on the first complete sentence, while continuing to render the final
   full answer with metadata.
3. Keeps `/api/query` unchanged as the compatibility JSON route for typed Ask requests,
   tests, and non-streaming clients.

This improves the teacher-visible voice loop and creates the stable stream contract needed
for a later true token-streaming `ReasoningEngine` build. It does not yet reduce the time
until the first model token exists.

---

## Event Contract

`POST /api/query/stream`

Request body matches `/api/query`:

```json
{
  "query": "What languages does this school teach?",
  "intent": "TEACH",
  "eval_mode": false,
  "timeout_seconds": 25
}
```

Response headers:

```text
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

Events:

| Event | Data shape | Notes |
|---|---|---|
| `query_received` | `{type, timestamp}` | No raw query text in the SSE payload. The existing broadcaster may still carry query text because it already does today; do not expand privacy exposure in the new stream. |
| `status` | `{type, stage, label, timestamp}` | Minimal lifecycle labels: `thinking`, `grounding`, `ready`. |
| `answer_sentence` | `{type, index, text, tone_prefix, voice_tone, gir_score}` | Emitted after the pipeline result exists, one complete sentence-ish chunk at a time. The first event is the trigger for early TTS. |
| `result` | Same top-level shape as `/api/query` | Final canonical payload, including `grounding`, `gir_score`, `gir_method`, `voice_tone`, `tone_prefix`, `trace_id`, route, sources, and session id. |
| `error` | `{type, error, timeout?, unavailable?, timestamp}` | Mirrors `/api/query` error semantics. |

Use a small helper for SSE formatting:

```python
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
```

Use a small helper for sentence splitting. Keep it conservative and deterministic:

```python
def _answer_sentences(text: str) -> list[str]:
    # Split after ., !, ?, or newline boundaries. Fall back to the whole text.
```

Do not include raw student names or query text in helper logs or event payloads beyond
the existing final answer behavior.

---

## Implementation Slices

| Slice | Size | Files |
|---|---|---|
| 0. Extract shared query-result payload builder from `/api/query` | S | `src/web.py` |
| 1. Add SSE helpers and `/api/query/stream` route | S | `src/web.py` |
| 2. Frontend stream consumer for voice-originated Ask | M | `static/index.html` |
| 3. Early sentence TTS queue | M | `static/index.html` |
| 4. Tests for SSE contract and UI wiring | S | `tests/` |

### Slice 0: Shared query payload builder

Avoid duplicating the fragile `/api/query` response assembly. Extract a helper in
`src/web.py` that takes `result`, `query_text`, `session_id`, and `eval_mode`, appends the
trace/privacy events exactly once, handles `increment_session()` exactly once, and returns
the same response dict `/api/query` returns today.

Acceptance:

- `/api/query` response shape is unchanged.
- The helper still reads `result.grounding` and `result.path_record.*`; it does not call
  `build_grounding_result()`.
- `increment_session()` still happens only after a successful non-eval query.

### Slice 1: `/api/query/stream`

Add:

```python
from fastapi.responses import StreamingResponse
```

and:

```python
@app.post("/api/query/stream")
async def query_stream_endpoint(payload: dict):
    ...
    return StreamingResponse(generator(), media_type="text/event-stream", headers={...})
```

The generator should:

1. Validate `query` before starting the stream; bad input returns normal 400 JSON, not an SSE
   stream.
2. Yield `query_received`.
3. Yield `status: thinking`.
4. Await the same `run_teacher_query()` call as `/api/query`, with the same timeout budget.
5. Yield `status: grounding` once the pipeline returns.
6. Yield `answer_sentence` events built from `result.synthesis.content` and inline GIR/tone.
7. Yield final `result`.
8. Broadcast the final result just like `/api/query`.

Errors should yield one `error` SSE event after the stream has started. Pre-stream validation
errors can stay JSON.

### Slice 2: Frontend stream consumer

In `static/index.html`, typed Ask can continue using `/api/query`. Voice-originated Ask
(`fromVoice === true`) should call a new helper such as `submitAskTextStream(text)`.

Use `fetch()` and parse `response.body.getReader()` rather than `EventSource`, because the
route is a POST with a JSON body. Implement a minimal SSE parser that buffers text until
`\n\n`, reads `event:` and `data:` lines, and dispatches JSON payloads.

Acceptance:

- If streaming fetch or `ReadableStream` is unavailable, fall back to the existing blocking
  `/api/query` path.
- If the stream emits `error`, render the same error state the blocking path renders.
- The final `result` event updates chat state with the same metadata as the existing JSON
  path.

### Slice 3: Early sentence TTS queue

When the first `answer_sentence` event arrives for a voice-originated request:

- Start spoken playback with that sentence and `tone_prefix`.
- Queue subsequent sentence text locally.
- Do not overlap audio. The current `voiceRuntime.speak()` stops existing speech at the
  beginning of every call, so add a small queue helper such as `voiceRuntime.speakQueue(items,
  tonePrefix)` or a `speakSegment()` path that chains `onended`.

If Rime refuses a segment because it mentions student data, the existing local fallback must
still include the same `tone_prefix`.

Acceptance:

- First sentence begins TTS before the final `result` event is processed.
- Later sentences do not interrupt earlier audio.
- Final rendered answer remains the full answer, not just the first sentence.
- `tone_prefix` is applied once per spoken segment or once at the beginning of the queue, but
  never doubled within a segment.

---

## Tests

Add focused tests rather than broad UI automation for this slice:

1. Backend: `POST /api/query/stream` returns `text/event-stream` and emits at least
   `query_received`, `status`, `answer_sentence`, and `result` for a monkeypatched
   `run_teacher_query()`.
2. Backend: no `answer_sentence` event is emitted before a successful pipeline result; timeout
   produces an `error` event with `timeout: true`.
3. Backend: `/api/query` JSON response remains unchanged for the same monkeypatched result.
4. Frontend contract: `static/index.html` includes `"/api/query/stream"`, reads
   `response.body.getReader()`, and calls the queue/early-sentence speech helper from the
   `answer_sentence` event path.
5. Frontend contract: fallback path to blocking `/api/query` remains present.

Run:

```bash
pytest -q tests/test_teacher_api_phase2.py tests/test_voice_tts_privacy_gate.py tests/test_ui_contract.py
pytest -q
```

---

## Open Risks / What This Does NOT Cover

- **Not provider-token streaming.** First audio still waits for `run_teacher_query()` to return,
  because `ReasoningEngine` does not expose streamed tokens or partial synthesis yet.
- **No streamed STT partials.** `/api/voice/stt` still returns one transcript JSON after local
  transcription completes.
- **No WebSocket rewrite.** This uses SSE over POST fetch streams because it is the smallest
  change to the existing FastAPI route shape and browser code.
- **No second grounding computation.** The stream reads the inline GIR result already attached
  to `PipelineResult`.
- **No privacy weakening.** Do not send student data to Rime; `/api/voice/tts` remains the only
  external speech path and keeps its publication-safety gate.
