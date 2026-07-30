# Lingua Viva GIR + Voice Hardening Report - 2026-07-30

## Verdict
- Run status: **15/15 iterations completed** (all reached a final answer or classified fallback)
- Highest severity: **P2** (GIR calibration — source-ledger presence inflates grounding score)
- Release gate: **CONDITIONAL PASS** — GIR/voice/streaming wiring is correct and operational; GIR threshold calibration needs real-query tuning before it becomes a reliable teacher signal. No data leaks, no privacy gate failures, no crashes.

## Environment
- App URL: `http://127.0.0.1:8787` (uvicorn, FastAPI TestClient for controlled passes)
- Model/provider state: Ollama `qwen2.5:3b` installed, OpenAI-compat endpoint (`/v1/chat/completions`) timed out under burst load (circuit breaker tripped after 3 consecutive 20s timeouts). Direct `/api/generate` worked before the burst.
- Rime state: Not configured (`RIME_API_KEY` not set). TTS gracefully returns 503 with `"fallback": "local"`.
- Worktree note: uncommitted changes from GIR voice tone + golden voice loop builds. No commit made by this loop.

## Scenario Results

Two passes were run:
1. **HTTP harness** (15 scenarios via running app) — Ollama circuit-breaker tripped after first 3 queries, remaining 12 got fallback text
2. **TestClient controlled pass** (5 key scenarios + privacy + streaming verification) — clean-state validation of GIR differentiation

### Pass 1: HTTP Harness (full 15 scenarios)

| # | Bucket | Question | Route | GIR | Tone | TTS | Verdict |
|---|---|---|---:|---|---|---|---|
| 1 | strong_local | Grade 3 Italian listening practice | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED (Ollama timeout, fallback text) |
| 2 | strong_local | Introduce classroom greetings | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 3 | strong_local | Evidence before independent speaking | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 4 | thin_source | Lunch supervision rainy days | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED (breaker open) |
| 5 | thin_source | Bus route for new family | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 6 | thin_source | Local train disruption | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 7 | student_support | Student Alpha confidence | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 8 | student_support | Student Beta listening | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 9 | student_support | Student Gamma family progress | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 10 | admin_ops | Slack daily operations | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 11 | admin_ops | Drive import confirmation | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 12 | followup | Make answer shorter | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 13 | followup | What source relied on most | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |
| 14 | stress | Three-sentence mixed-level plan | /api/query | None | - | no_text | TIMEOUT |
| 15 | stress | IB MYP language guide | /api/query/stream | 1.0 | plain | rime_unavailable | DEGRADED |

**Note**: All 15 scenarios completed through `/api/query/stream` without crashes. The DEGRADED verdicts reflect Ollama model timeout then fallback text, not GIR/voice bugs. GIR correctly scores the fallback text it receives. The all-1.0 scores under HTTP reflect pre-existing source records in the ledger making `grounded=True`.

### Pass 2: TestClient Controlled (clean state, no Ollama dependency)

| # | Bucket | Question | GIR | Tone | Prefix | TTS | Verdict |
|---|---|---|---:|---|---|---|---|
| 1 | strong_local | Grade 3 listening | 0.0 | name_boundary | "I don't have a solid source..." | 503:local | OK (correctly hedged) |
| 4 | thin_source | Lunch supervision | 0.0 | name_boundary | "I don't have a solid source..." | 503:local | OK (correctly hedged) |
| 6 | thin_source | Train disruption | 0.0 | name_boundary | "I don't have a solid source..." | 503:local | OK (correctly hedged) |
| 7 | student_support | Student Alpha | 0.0 | name_boundary | "I don't have a solid source..." | 503:local | OK (correctly hedged) |
| 14 | stress | Mixed-level plan | 0.0 | name_boundary | "I don't have a solid source..." | 503:local | OK (correctly hedged) |

### Privacy Gate Verification

| Test | Status | Result |
|---|---|---|
| TTS with roster name "Marco" + tone_prefix | 403 | **PASS** - privacy gate blocked, `fallback: local`, violation reported |
| TTS with clean text | 503 | **PASS** - gate passed, blocked only by missing Rime key |
| tone_prefix included before safety check | Verified | **PASS** - prefix is prepended before `check_publication_safety()` |

### Streaming Verification

| Test | Result |
|---|---|
| `/api/query/stream` returns SSE events | **PASS** - events: `query_received`, `status`, `answer_sentence`, `result` |
| Final `result` event includes `gir_score`, `voice_tone` | **PASS** |
| `answer_sentence` events fired before `result` | **PASS** |
| Fallback to `/api/query` when streaming fails | **PASS** (scenario #14 fell back cleanly) |

## Findings

| ID | Severity | User symptom | System evidence | Fix status | Retest |
|---|---|---|---|---|---|
| F1 | P2 | GIR always 1.0 when source ledger has any records | `build_grounding_result()` treats ANY `source_citations` (including default `"Manuale v1"`) as `knowledge_hit=True` -> `grounded=True` -> `unsupported_claims=0` -> `score=1.0` regardless of actual source relevance | **OPEN** - this is the threshold calibration issue the spec already flagged | Requires real-query data to calibrate |
| F2 | P2 | GIR scores error/fallback text identically to real answers | Ollama down -> pipeline returns `"Ollama appears to be down"` -> GIR scores that string, not the answer quality. No distinction between "well-grounded answer" and "error message" | **OPEN** - consider checking `confidence=0.0` or content patterns before computing GIR | N/A |
| F3 | P3 | TTS always unavailable without Rime key | `/api/voice/tts` returns 503 when `RIME_API_KEY` not set | **BY DESIGN** - local browser TTS fallback is the intended private path | N/A |
| F4 | P3 | Ollama circuit breaker trips after 3 timeouts, stays open 30s | `ReasoningEngine._record_ollama_failure()` opens breaker after 3 consecutive failures, 30s cooldown | **BY DESIGN** - prevents cascading timeouts | N/A |
| F5 | INFO | Synthetic student names ("Student Alpha") do NOT trigger privacy gate | Privacy gate matches against the demo roster (`Marco`, `Nora`, `Luca`), not arbitrary student-like text. This is correct: the gate protects real student names, not the concept of "student" | **BY DESIGN** | N/A |

## Open Risks

1. **GIR threshold calibration is unvalidated** (F1). The `claim_support_v1_heuristic` treats any citation presence as grounded. A future pass should: (a) weight citation relevance to the actual query, (b) distinguish "this is a real source for this question" from "a default citation exists." This requires real teacher queries with known ground truth.

2. **GIR scores error fallbacks as if they were real answers** (F2). When the model is unavailable, `confidence=0.0` is set on the `ReasonResult` but GIR only looks at claim text and citations, not the confidence. A simple guard (`if synthesis_result.confidence < 0.1: score = 0.0`) would prevent error messages from appearing well-grounded.

3. **No Rime key configured** - spoken voice quality is untestable beyond the browser-TTS fallback. The TTS wiring (tone_prefix prepend, privacy gate ordering) is verified at the route level.

4. **Ollama `/v1/chat/completions` under load** - the OpenAI-compat endpoint becomes unresponsive after a burst of concurrent requests while `/api/generate` continues working. This is an environment/Ollama issue, not a Lingua Viva code issue.

5. **No true provider-token streaming** - this loop validates sentence-level SSE streaming and GIR/tone behavior. True token streaming from the model requires a separate `ReasoningEngine` streaming-adapter spec.

## Follow-Up Specs Needed

1. **GIR Calibration Spec** - define what "grounded" means beyond citation presence: relevance scoring, domain match, source freshness. Requires a corpus of known-answer queries with expected GIR ranges.

2. **GIR Error-State Guard** - skip or floor GIR computation when `synthesis_result.confidence < threshold` (e.g., 0.1). Small, tightly scoped fix to prevent F2.

3. **Rime Integration Testing** - once a key is available, run the 15 scenarios again to verify: audio returned for clean text, privacy refusal for student data, tone prefix audible in spoken output.

## Review Addendum - 2026-07-30

Follow-up review closed the immediate F1/F2 implementation defects:

- `build_grounding_result()` now requires simple query/source relevance before ledger records or generic citations can ground an answer. This prevents unrelated durable source records from making every answer score `1.0`.
- Generic `Manuale v1` citations are no longer treated as universal support; they only ground curriculum/manuale-shaped queries.
- Low-confidence synthesis results (`synthesis_confidence < 0.1`) now floor GIR to `0.0`, so model outage/error fallback text cannot receive a high grounding score.
- `/api/query` no longer invents `Manuale v1` when `result.synthesis.citations` is empty; `sources` stays empty and `source_citation` is `""`.

Retest after review:

- `python3 -m src.lingua_viva.cli golden-workflows --only GW-VOICE-006` -> `1/1 passed`
- `python3 -m src.lingua_viva.cli preflight` -> `6/6`
- `python3 -m pytest -q` -> `1575 passed, 13 skipped`

Remaining calibration risk: the lexical relevance guard is deliberately conservative and deterministic. A future GIR calibration spec should still define richer source relevance and expected GIR bands against real teacher queries.
