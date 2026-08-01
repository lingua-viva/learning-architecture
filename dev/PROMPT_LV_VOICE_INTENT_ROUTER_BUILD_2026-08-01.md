# Build Prompt — Voice Intent Router

You are implementing `dev/SPEC_LV_VOICE_INTENT_ROUTER_2026-08-01.md` end to end.

Read first:

```text
dev/SPEC_LV_VOICE_INTENT_ROUTER_2026-08-01.md
src/web.py:2580-2640       (/api/voice/stt — how STT works today)
src/web.py:2886-2935       (/api/observe/capture — observation save endpoint)
src/web.py:4660-4710       (/api/query — question routing endpoint)
src/lingua_viva/voice_tone.py   (resolve_voice_tone — how GIR maps to tone)
src/education/student_lens.py:1242   (list_lenses_for_teacher — roster loading)
static/index.html:830-870  (voiceRuntime.speak — current TTS integration)
```

Also read (if Spec 3 has been built):
```text
src/lingua_viva/lesson_materials.py   (generate_lesson_materials — the generation target)
src/web.py  (grep for lesson-materials/generate)
```

## Objective

Build `POST /api/voice/act` — a single endpoint that takes a transcript (from STT or typed),
classifies it as an observation / generation request / question, executes the appropriate action,
and returns a structured response with spoken confirmation text.

## Hard Rules

1. **No LLM for intent classification.** Use regex signal matching only. The intent router must
   be instant (< 10ms) — it runs on every voice input. LLM calls happen AFTER routing, inside
   the downstream endpoints.
2. **Default to question when uncertain.** Questions are safe (read-only). Observations and
   generation are write actions — require higher signal confidence.
3. **Observations require a detected student.** If the transcript mentions student behavior but
   no student name matches the roster, return `needs_clarification: true` with a spoken prompt
   asking which student.
4. **Never speak full student names via external TTS.** Spoken confirmations use first name only.
   The privacy gate in `/api/voice/tts` already enforces this — but don't put full names in the
   `spoken_confirmation` field either.
5. **Do not commit.** Leave changes as modified/untracked.
6. **Do not modify the existing `/api/voice/stt` endpoint.** The new `/api/voice/act` sits
   downstream of STT — it receives text, not audio.

## Step 1: Create `src/lingua_viva/voice_intent.py`

```python
"""
Voice Intent Router — signal-based classification of teacher voice commands.

Three intents:
  - observation: teacher describing student behavior (write action)
  - generate: teacher requesting materials/plans (write action)
  - question: teacher asking for information (read-only, default)

No LLM needed. Pure regex signal matching with priority ordering.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class IntentClassification:
    intent: str              # "observation" | "generate" | "question"
    confidence: float        # 0.0 - 1.0
    student_id: Optional[str]        # detected student (observations only)
    student_name: Optional[str]      # display name for confirmation
    needs_clarification: bool        # true if observation detected but no student
    observation_context: dict        # parsed CEFR dimension, level hints, etc.
    generation_context: dict         # parsed topic, type hints for material generation
    matched_signals: list[str]       # which signals fired (for debugging)


def classify_intent(transcript: str, roster: list[dict]) -> IntentClassification:
    """Classify a voice transcript into an actionable intent."""
    ...


def detect_student(transcript: str, roster: list[dict]) -> tuple[Optional[str], Optional[str]]:
    """Find which student the transcript refers to. Returns (student_id, display_name)."""
    ...


def parse_observation_context(transcript: str) -> dict:
    """Extract CEFR dimension and level hints from observation text."""
    ...


def parse_generation_context(transcript: str) -> dict:
    """Extract lesson topic and material type from a generation request."""
    ...
```

### Signal Definitions

Observation signals (any match → possible observation):
```python
OBSERVATION_SIGNALS = [
    (r"\b(he|she|they|the student|the learner)\s+\w+ed\b", 0.4),
    (r"\b(helped|read|wrote|said|showed|struggled|completed|participated|used|demonstrated|spoke|asked|answered)\b", 0.3),
    (r"\b(during|while|in class|this morning|today|at recess|in group|in reading|in math)\b", 0.2),
    (r"\b(I (noticed|observed|saw|heard))\b", 0.5),
    (r"\b(observation|note for)\b", 0.6),
]
```

Generation signals:
```python
GENERATION_SIGNALS = [
    (r"\b(create|generate|make|build|prepare|write|design)\b.*\b(worksheet|lesson|plan|exercise|material|activity|handout)\b", 0.7),
    (r"\b(worksheet|lesson plan|exercise|handout|activity|materials)\b.*\b(for|about|on|covering)\b", 0.5),
    (r"\b(differentiated|customized|adapted|tiered)\b", 0.3),
    (r"\b(for (my class|the class|tomorrow|next week|today))\b", 0.2),
]
```

Question signals:
```python
QUESTION_SIGNALS = [
    (r"^(what|how|when|where|which|who|is|are|can|should|does|do|did|will|would)\b", 0.5),
    (r"\?\s*$", 0.6),
    (r"\b(tell me|explain|show me|describe|summarize)\b", 0.4),
    (r"\b(what (level|tier|progress|status))\b", 0.5),
]
```

Classification logic:
1. Score each intent by summing weights of matched signals
2. Observation requires: score >= 0.5 AND (student detected OR generic student reference)
3. Generation requires: score >= 0.5
4. Question is default when neither observation nor generation meets threshold
5. If observation scores high but no student detected → `needs_clarification = true`

### Student Detection

```python
def detect_student(transcript: str, roster: list[dict]) -> tuple[Optional[str], Optional[str]]:
    transcript_lower = transcript.lower()
    for student in roster:
        display_name = student.get("display_name", "")
        if not display_name:
            continue
        # Match full name or first name
        if display_name.lower() in transcript_lower:
            return student["student_id"], display_name
        first_name = display_name.split()[0].lower()
        if len(first_name) > 2 and re.search(rf"\b{re.escape(first_name)}\b", transcript_lower):
            return student["student_id"], display_name
    return None, None
```

### Observation Context Parsing

```python
def parse_observation_context(transcript: str) -> dict:
    context = {"cefr_dimension": "speaking", "cefr_level_hint": "A1+", "direction": "progressing"}

    dimension_keywords = {
        "reading": ["read", "reading", "book", "text", "page", "passage"],
        "writing": ["wrote", "write", "writing", "sentence", "paragraph", "spelled"],
        "speaking": ["said", "spoke", "speaking", "oral", "pronunciation", "conversation", "discussed"],
        "listening": ["listened", "heard", "understood", "comprehension", "followed instructions"],
    }
    for dim, keywords in dimension_keywords.items():
        if any(kw in transcript.lower() for kw in keywords):
            context["cefr_dimension"] = dim
            break

    level_keywords = {
        "Pre-A1": ["no words", "gesture only", "silent", "refused", "no attempt"],
        "A1": ["basic", "single words", "one word", "beginning to"],
        "A1+": ["short sentences", "simple", "helped", "starting to", "with support"],
        "A2": ["connected", "actively", "described", "participated", "independently"],
        "B1": ["fluently", "complex", "explained", "argued", "debated", "detailed"],
    }
    for level, keywords in level_keywords.items():
        if any(kw in transcript.lower() for kw in keywords):
            context["cefr_level_hint"] = level
            break

    # Direction
    if any(w in transcript.lower() for w in ["struggled", "difficulty", "refused", "silent", "no attempt"]):
        context["direction"] = "emerging"
    elif any(w in transcript.lower() for w in ["fluently", "complex", "independently", "confidently"]):
        context["direction"] = "secure"

    return context
```

## Step 2: Add `/api/voice/act` to `src/web.py`

```python
@app.post("/api/voice/act")
async def voice_act(payload: dict):
    """Voice intent router — classify transcript and execute the appropriate action."""
    from src.lingua_viva.voice_intent import classify_intent
    from src.education.student_lens import StudentLensStore

    transcript = str(payload.get("transcript") or "").strip()
    if not transcript:
        return JSONResponse({"error": "transcript is required"}, status_code=400)

    # Load teacher roster for student detection
    store = StudentLensStore()
    try:
        roster = store.list_lenses_for_teacher("local-teacher")
    finally:
        store.close()

    classification = classify_intent(transcript, roster)

    if classification.intent == "observation":
        if classification.needs_clarification:
            return {
                "intent": "observation",
                "action_taken": "needs_clarification",
                "spoken_confirmation": "I heard an observation but I'm not sure which student. Can you say their name?",
                "tone_prefix": "",
                "needs_clarification": True,
                "transcript": transcript,
            }
        # Execute observation save
        from src.education.observation_capture import ObservationCapturePipeline
        store = StudentLensStore()
        try:
            pipeline = ObservationCapturePipeline(store=store)
            ctx = classification.observation_context
            result = pipeline.capture(
                student_id=classification.student_id,
                teacher_id="local-teacher",
                raw_transcript=transcript,
                template_type="cefr",
                cefr_dimension=ctx.get("cefr_dimension", "speaking"),
                cefr_level_observed=ctx.get("cefr_level_hint", "A1+"),
                cefr_direction=ctx.get("direction", "progressing"),
            )
        finally:
            store.close()

        # Trigger Drive sync
        from src.lingua_viva.drive_sync import trigger_sync
        trigger_sync(classification.student_id)

        first_name = (classification.student_name or "").split()[0]
        return {
            "intent": "observation",
            "action_taken": "saved",
            "result": result,
            "spoken_confirmation": f"Got it. Observation saved for {first_name}.",
            "tone_prefix": "Confirmed. ",
            "gir_score": 1.0,
        }

    elif classification.intent == "generate":
        # Route to lesson materials generation
        # For now, return a structured prompt for the frontend to show a form
        # (full auto-generation requires lesson params we can't always infer from voice)
        gen_ctx = classification.generation_context
        return {
            "intent": "generate",
            "action_taken": "ready_to_generate",
            "generation_context": gen_ctx,
            "spoken_confirmation": f"Ready to create materials about {gen_ctx.get('topic', 'that topic')}. Which students should I include?",
            "tone_prefix": "",
            "gir_score": 1.0,
            "needs_confirmation": True,
        }

    else:
        # Default: route to query pipeline
        from src.lingua_viva.app import run_teacher_query
        try:
            result = await asyncio.wait_for(
                run_teacher_query(transcript, intent=None, session_id=None, eval_mode=False),
                timeout=25,
            )
            response = _build_query_response(result, transcript, None, False)
            spoken = str(response.get("answer", ""))[:300]
            tone_prefix = str(response.get("tone_prefix", ""))
            gir = float(response.get("gir_score", 1.0))
            return {
                "intent": "question",
                "action_taken": "answered",
                "result": response,
                "spoken_response": spoken,
                "tone_prefix": tone_prefix,
                "gir_score": gir,
            }
        except asyncio.TimeoutError:
            return {
                "intent": "question",
                "action_taken": "timeout",
                "spoken_confirmation": "That's taking too long. Try asking a simpler question.",
                "tone_prefix": "",
                "gir_score": 0.0,
            }
```

## Step 3: Register the route

Add to `contracts/ROUTE_REACHABILITY.yaml` under `intentionally_backend_only`:
```yaml
  - route: "POST /api/voice/act"
    status: deferred_undecided
    reason: >-
      MVP sprint Spec 4 (2026-08-01). Voice intent router — classifies transcripts
      and executes actions; UI voice companion wire deferred.
```

## Step 4: Write tests

`tests/test_voice_intent.py`:

1. `test_observation_detected` — "Marco helped a classmate" → intent=observation, student=marco
2. `test_generation_detected` — "Create a worksheet about daily routines" → intent=generate
3. `test_question_default` — "What level is Nora at?" → intent=question
4. `test_ambiguous_defaults_to_question` — "Marco reading" → intent=question
5. `test_observation_no_student_needs_clarification` — "The student struggled" → needs_clarification
6. `test_student_detection_first_name` — "nora participated actively" → student_id=student-nora
7. `test_observation_context_parsing` — "read aloud with pronunciation" → dimension=reading
8. `test_generation_context_parsing` — "worksheet for daily routines" → topic="daily routines"

All tests are pure unit tests — no LLM, no database, no network.

## Step 5: Verify

```bash
pytest -q tests/test_voice_intent.py
python3 -m src.lingua_viva.cli preflight
```

Then integration test (needs the app running):
```bash
curl -X POST http://localhost:8787/api/voice/act \
  -H "Content-Type: application/json" \
  -d '{"transcript": "Marco helped a classmate find the right page during group reading"}'
```

## Definition of Done

- [ ] `src/lingua_viva/voice_intent.py` created — signal-based classifier
- [ ] `/api/voice/act` endpoint routes to correct action
- [ ] Observations auto-save with student detection
- [ ] Generation requests return structured context
- [ ] Questions route to existing query pipeline
- [ ] No student names in spoken confirmations via external TTS
- [ ] 8+ tests passing
- [ ] Preflight 6/6
- [ ] Full test suite still passes
