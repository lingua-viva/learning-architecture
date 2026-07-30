# SPEC: GIR → Voice Delivery Tone (Grounding-Aware Speech)

**Date**: 2026-07-29
**Status**: DRAFT — operator review before build
**Lens**: architect (primary), protection (student-safety framing)
**Depends on**: `src/lingua_viva/grounding/` (built earlier today, `faa79a3`), existing voice loop (`voice_stt.py`, `/api/voice/tts`, `/api/query`)
**Branch**: `feat/gir-voice-tone`
**Priority rationale**: highest-leverage item identified in `IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30.md` (S11 A01 + S01 A03) — plumbing exists on both ends already; this is a wiring task, not new architecture. It closes a trust gap specific to a product that speaks answers to children: a confidently-voiced ungrounded answer is a worse failure than a slow one.

---

## What Already Exists (verified by reading, not assumed)

| Component | Status | Location |
|---|---|---|
| `build_grounding_result()` | Built | `src/lingua_viva/grounding/build.py:59` |
| `GroundingResult`/`GIR` dataclasses | Built | `src/lingua_viva/grounding/schema.py` |
| `PathRecord` (per-query trace) | Built, **no grounding fields** | `memory/schema/path.py` |
| `Pipeline.run()` SYNTHESIZE step | Built | `src/pipeline.py:908-916` |
| `Pipeline.run()` STORE step (builds `PathRecord`) | Built | `src/pipeline.py:930-958` |
| `/api/query` route | Built, calls grounding **post-hoc** | `src/web.py:3937-4013` |
| `/api/voice/tts` route | Built, **text-only, no tone input** | `src/web.py:1709-1789` |
| Frontend `speak(text)` | Built, **passes raw text only** | `static/index.html:829-849` |

## The Gap

1. `build_grounding_result()` is called exactly once in the live request path, in `/api/query` (`src/web.py:3999-4011`), **after** `run_teacher_query()` has already returned — a reconstruction from a trace dict, not a verdict computed at the moment of truth. `pipeline.py` itself has zero grounding wiring.
2. `PathRecord` has no `gir_score` / `gir_method` field, so the one grounding computation that does happen has nowhere durable to land per-trace.
3. `/api/voice/tts` (`src/web.py:1709`) takes `text` and nothing else — the spoken audio is generated with zero awareness of how grounded the underlying claim was. Same for the frontend's `speak(text)` (`static/index.html:829`), which posts only `{text: String(text)}`.

Net effect: a low-confidence, thinly-sourced answer is read aloud in exactly the same voice and phrasing as a well-grounded one.

---

## Design

### 1. Compute GIR inline, at the real moment of truth

Move the grounding computation from `web.py` (post-hoc) into `pipeline.py`, immediately after SYNTHESIZE and before STORE (`src/pipeline.py:916`, right after `steps_executed.append("SYNTHESIZE")`, before the Step 6.5 REHYDRATE block). This is LV's version of MC's Prime Directive rule: *"compute the real thing once, at the real moment, in the real code path that has the ground truth... never reconstruct it later from a proxy."*

```python
# after synthesis_result is built, before REHYDRATE
from src.lingua_viva.grounding.build import build_grounding_result

grounding = build_grounding_result(
    trace={
        "trace_id": query_hash,  # or a dedicated id if one exists at this point
        "session_id": session_id,
        "model_used": local_result.model_used,
        "source_citations": synthesis_result.citations,
    },
    classification=classification,
    content=synthesis_result.content,
    query_text=query,
    query_hash=query_hash,
    session_id=session_id,
    intent=classification.default_intent or "",
)
```

Attach the result to `PipelineResult` (new field `grounding: Optional[GroundingResult] = None`, `src/pipeline.py:147-157`) and to `PathRecord` (see schema change below) so it's captured in the permanent record, not just returned to one caller.

### 2. Schema change — `PathRecord` gains grounding fields

`memory/schema/path.py`, add:

```python
gir_score: float = 1.0
gir_method: str = ""
voice_tone: str = "plain"
```

Update `to_dict()`/`from_dict()` accordingly. This is the "verdict, not reconstruction" storage layer — without it, the score computed in step 1 is lost the moment the request ends.

### 3. Tone resolver — new small module, not a full VoiceBridge

`src/lingua_viva/voice_tone.py` (new file):

```python
from __future__ import annotations

# Thresholds start as MC's (≥0.8 / 0.4-0.8 / <0.4) but LV's GIR method is
# `claim_support_v1_heuristic` — a coarse sentence-split + uncertainty-marker
# heuristic, not the same computation MC's inline GIR uses. Treat these as a
# starting point, not a validated calibration. See "Open Risks" below.

PLAIN_THRESHOLD = 0.8
CLARIFY_THRESHOLD = 0.4


def resolve_voice_tone(gir_score: float) -> dict:
    if gir_score >= PLAIN_THRESHOLD:
        return {"tone": "plain", "prefix": ""}
    if gir_score >= CLARIFY_THRESHOLD:
        return {
            "tone": "clarify",
            "prefix": "I'm fairly sure, but let's double check this together. ",
        }
    return {
        "tone": "name_boundary",
        "prefix": "I don't have a solid source for this one, so take it as a starting point, not a final answer. ",
    }
```

Pure function, unit-testable in isolation, no dependency on the pipeline or web layer.

### 4. Wire into `/api/query` response

Replace the post-hoc `build_grounding_result()` call in `src/web.py:3996-4013` with reading `result.grounding` (now computed inline in step 1) and `result.path_record.voice_tone`. Add `gir_score`, `gir_method`, `voice_tone`, `tone_prefix` to the JSON response payload so the frontend has them without a second round trip.

### 5. Wire into `/api/voice/tts`

Extend the request body accepted by `voice_tts()` (`src/web.py:1709`) to optionally include `tone_prefix: str`. If present, prepend it to `text` **before** the publication-safety gate check (`check_publication_safety`, line 1740) and before sending to Rime — the prefix itself is static, non-student-data copy, so it doesn't change the gate's behavior, but it must be included before the character-limit check (`RIME_MAX_CHARS`, line 1734).

### 6. Wire into the frontend

`static/index.html`:
- Where the `/api/query` response is handled (~line 1845 area), capture `tone_prefix` alongside the response text.
- `speak(text)` (line 829) gains an optional second parameter; the POST body at line ~833 includes `tone_prefix` when calling `/api/voice/tts`.
- `speakLocally(text)` (the browser-TTS fallback used for student-data text) should also receive the prefix-prepended text, so the tone signal survives the privacy fallback path too — otherwise low-GIR answers about a specific student would silently lose their hedge.

---

## Implementation Slices

| Slice | Size | Files |
|---|---|---|
| 0. Schema — `gir_score`/`gir_method`/`voice_tone` on `PathRecord` | XS | `memory/schema/path.py` |
| 1. Inline GIR at SYNTHESIZE, attach to `PipelineResult` | S | `src/pipeline.py` |
| 2. Tone resolver (pure function) | XS | `src/lingua_viva/voice_tone.py` (new) |
| 3. `/api/query` reads inline result instead of recomputing | S | `src/web.py:3937-4013` |
| 4. `/api/voice/tts` accepts + applies `tone_prefix` | S | `src/web.py:1709-1789` |
| 5. Frontend passes `tone_prefix` through query → speak | S | `static/index.html` |
| 6. Tests: resolver thresholds, inline-vs-post-hoc parity, TTS prefix applied | S | `tests/` (new + existing) |

## Files Touched

| Action | File |
|---|---|
| MODIFY | `memory/schema/path.py` |
| MODIFY | `src/pipeline.py` |
| NEW | `src/lingua_viva/voice_tone.py` |
| MODIFY | `src/web.py` (`/api/query`, `/api/voice/tts`) |
| MODIFY | `static/index.html` |
| NEW/MODIFY | `tests/test_voice_tone.py`, relevant existing pipeline/web tests |

## Verification

1. `pytest -q tests/` green, including new `test_voice_tone.py`.
2. Manual: ask a question with strong knowledge-base coverage → response spoken plainly, no prefix.
3. Manual: ask a question with thin/no source coverage → response spoken with a hedging prefix.
4. Confirm `golden_workflows/runner.py:55`'s existing `build_grounding_result()` call still works unchanged (it computes its own grounding independently of the live pipeline path — not touched by this spec, but check it doesn't now double-compute or diverge).
5. Confirm student-data text still triggers the local-fallback TTS path with the prefix intact (privacy gate unaffected by tone change).

## Open Risks / What This Does NOT Cover

- **Threshold calibration is unvalidated.** `claim_support_v1_heuristic` is a coarse heuristic (sentence count + uncertainty-word matching); MC's thresholds were tuned against MC's own GIR computation, not LV's. Expect to need real query data before trusting 0.8/0.4 as final.
- **No chat-UI trust badge.** The tone prefix is spoken/prepended to synthesized speech only; there's no visual indicator in the Ask chat thread showing grounding strength. Could be a fast follow.
- **Not a full `VoiceBridge`/VIU system.** This is a minimal resolver function, not MC's class-based delivery-tone architecture — intentionally scoped smaller since LV doesn't have MC's broader VIU/lens machinery to hook into.
- **Does not address the sequential round-trip voice architecture** (STT → query → TTS as three separate blocking calls, no streaming). That's a separate, independent gap — this spec makes the eventual spoken answer more honest, not faster.
- **Does not touch golden-voice-loop instrumentation or gap→eval enrichment** — those depend on this landing first and are explicitly out of scope here.
