# SPEC: GIR + Voice Real-App Hardening Loop

**Date**: 2026-07-30
**Status**: SHIPPED - committed `247ade8`, tested
**Lens**: product truth (primary), protection (student-data/privacy gates), measurement
**Depends on**:
- `dev/SPEC_LV_GIR_VOICE_TONE_2026-07-29.md`
- `dev/SPEC_LV_GOLDEN_VOICE_LOOP_2026-07-30.md`
- `dev/SPEC_LV_VOICE_STREAMING_2026-07-30.md`

**Priority rationale**: the operator's success criterion is not "the route exists" or
"unit tests pass." It is: teacher questions actually work through the real Ask/voice path,
GIR acts as a grounding voice, and spoken delivery stays honest when evidence is thin. This
loop is the first product-reality pass after the voice/GIR/streaming wiring.

---

## What Already Exists (verify again before running)

| Component | Expected current state | Verification target |
|---|---|---|
| Inline GIR | Pipeline computes GROUND after SYNTHESIZE and before STORE | `src/pipeline.py` contains `Step 6.25: GROUND` |
| Durable GIR fields | `PathRecord` has `gir_score`, `gir_method`, `voice_tone` | `memory/schema/path.py` |
| Query JSON route | `/api/query` returns `grounding`, `gir_score`, `gir_method`, `voice_tone`, `tone_prefix` | `src/web.py` |
| Streaming query route | `/api/query/stream` emits SSE `answer_sentence` + final `result` | `src/web.py` |
| Voice frontend | voice-originated Ask uses `/api/query/stream` when available and queues sentence TTS | `static/index.html` |
| TTS privacy gate | `/api/voice/tts` prepends `tone_prefix` before checking publication safety and before external Rime | `src/web.py` |
| Golden workflow | `GW-VOICE-006` exercises STT -> pipeline -> grounding -> tone -> hermetic TTS prefix | `src/lingua_viva/golden_workflows/runner.py` |

If any prerequisite is missing, stop. Do not compensate with a parallel grounding check or a
test-only fake route.

---

## Goal

Run at least 15 real-app Ask/voice passes and produce a report that distinguishes:

- questions that are answered correctly and grounded well
- questions that are answered but overconfidently grounded
- questions that should hedge because local evidence is thin
- privacy-sensitive questions that must stay local and preserve tone prefix behavior
- streaming/early-sentence playback failures
- defects that require code fixes before Monday

The loop must use synthetic inputs only. Do not use real student names, private school data,
or live family records.

---

## Definition of a Pass

Each iteration must include both a human-product observation and system evidence.

### Human Track

For each question, record:

- the exact synthetic teacher question
- whether the UI/status made sense while waiting
- whether the final answer was useful to a teacher
- whether the spoken response started as soon as the first answer sentence was available
- whether the spoken wording included a hedge when GIR was low or moderate
- whether anything felt misleading, frozen, duplicated, or out of order

### Observability Track

For each question, capture:

- endpoint path used: `/api/query/stream` preferred, `/api/query` fallback if streaming fails
- SSE events seen: `query_received`, `status`, `answer_sentence`, `result`, `error`
- final `classification.node`, `classification.domain`, confidence
- `gir_score`, `gir_method`, `voice_tone`, `tone_prefix`
- `grounding.tier_used`
- `route`, `model_used`, `external_calls`
- source citations
- whether `/api/voice/tts` was called for the first sentence
- whether `/api/voice/tts` returned audio, local fallback, or privacy refusal
- trace id and whether the trace/export path contains only hashed query data

Use app endpoints or an actual running server, not isolated calls to `resolve_voice_tone()`.

---

## Required Scenario Mix

Run at least 15 iterations across these buckets:

| Bucket | Minimum | Purpose |
|---|---:|---|
| Strong local curriculum coverage | 3 | Prove high-GIR answers stay plain and useful |
| Thin/no local source coverage | 3 | Prove GIR drops or hedges when sources are weak |
| Student-support/lens-style question with synthetic names only | 3 | Prove privacy/local behavior and hedge preservation |
| Admin/operations question | 2 | Prove non-curriculum teacher tasks do not break voice metadata |
| Follow-up/context question | 2 | Probe whether answer quality degrades across session increments |
| Streaming/voice stress case | 2 | Long answer, multi-sentence answer, TTS fallback, or timeout-style behavior |

Negative controls are required:

- one deliberately out-of-scope question with no local source
- one synthetic student-data question that must not reach external TTS
- one long enough answer to produce multiple `answer_sentence` events

---

## Suggested Synthetic Question Set

The runner may replace these with equivalent teacher-style questions, but must preserve the
bucket coverage above.

1. "What should Grade 3 students practice for Italian listening this week?"
2. "How should I introduce classroom greetings to beginners?"
3. "What evidence should I collect before moving a student to more independent speaking?"
4. "What is the school's policy for lunch supervision on rainy days?"
5. "Which bus route should a new family take to campus tomorrow?"
6. "What does Lingua Viva know about the IB MYP language acquisition guide?"
7. "Marco is a synthetic student. How should I support his confidence in speaking?"
8. "Amina is a synthetic student. Draft a cautious next step for her listening practice."
9. "Leo is a synthetic student. What should I tell his family about progress?"
10. "What Slack daily operations messages should I expect from the assistant?"
11. "How do I confirm a Google Drive import became an extraction source?"
12. "Follow up: make that answer shorter and teacher-ready."
13. "Follow up: what source did you rely on most?"
14. "Give me a three-sentence plan for a mixed-level Italian class."
15. "Explain something Lingua Viva probably cannot know: the latest local train disruption near school."

If any question could accidentally use a real student name from the demo roster, replace it with
an obviously synthetic token such as `Student Alpha`.

---

## Severity

Use this severity scale in the report and defect log:

- **P0**: data leak, student/private text sent to external TTS, raw query exposed where only hash
  should be stored, app cannot open, or route crashes for normal voice use.
- **P1**: core Ask/voice workflow blocked, no final answer, no spoken output when fallback should
  work, `/api/query/stream` broken, or GIR/tone fields missing.
- **P2**: answer succeeds but grounding/tone is misleading, overconfident, duplicated, late, or
  confusing enough that a teacher may need help.
- **P3**: polish issue, awkward label, non-blocking copy/status mismatch.

Every P0/P1 found during the loop must have a retest case before the run closes.

---

## Implementation / Run Deliverables

### 1. Optional harness

If manual browser testing alone is too slow, add a small helper script:

`scripts/run_lv_voice_gir_hardening.py`

Requirements:

- starts from a running app URL or defaults to `http://127.0.0.1:8787`
- posts to `/api/query/stream`
- parses SSE events
- posts the first `answer_sentence` text plus `tone_prefix` to `/api/voice/tts`
- records JSONL evidence under `dev/reports/artifacts/`
- uses only synthetic questions
- never requires real Rime credentials; if Rime is unavailable, record fallback status rather
  than failing the whole run

The harness is an aid, not a substitute for the human-product notes.

### 2. Hardening report

Write:

`dev/reports/REPORT_LV_GIR_VOICE_HARDENING_2026-07-30.md`

Report sections:

1. Verdict: CLEAN / BLOCKED, highest severity, release gate recommendation.
2. Environment: commit/worktree note, app URL, model/provider state, Rime state.
3. Scenario table: 15 rows with question, bucket, route, GIR, tone, TTS result, verdict.
4. Findings: each defect with severity, user symptom, system evidence, fix status, retest.
5. Open risks: especially true token streaming, threshold calibration, and any local-source gaps.
6. Follow-up specs needed, if any.

### 3. Fixes

Fix real P0/P1 defects found by the loop if they are tightly scoped and do not require an operator
product decision. Do not invent lesson-planning-per-cohort or new ingestion architecture during
this run. If the finding is bigger than the voice/GIR path, document it and stop for operator
scoping.

---

## Clean-Run Criteria

The loop can close only when:

- all 15 iterations are recorded
- every iteration reaches a final answer or has a classified defect
- no P0/P1 remains open
- low/no-source questions do not get confidently spoken as fully grounded
- synthetic student-data TTS attempts do not leave the machine
- `/api/query/stream` final `result` matches the `/api/query` metadata contract
- `python3 -m pytest -q` passes after any fixes
- `python3 -m src.lingua_viva.cli preflight` passes

---

## What This Does NOT Cover

- Does not build true provider-token streaming. That belongs in a future
  `ReasoningEngine` streaming-adapter spec.
- Does not benchmark Whisper transcription quality beyond the existing golden workflow.
- Does not verify Slack, Drive, desktop document ingestion, or lesson planning per cohort. Those
  are the next Monday-essentials review after this loop.
- Does not commit or push. Leave the working tree for the operator.
