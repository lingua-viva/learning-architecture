# SPEC: Voice Intent Router — Actions vs Questions

**Created**: 2026-08-01
**Status**: READY TO BUILD
**Depends on**: Observation capture (exists), Lesson materials (Spec 3), Query pipeline (exists)
**Produces**: Single-shot voice commands that DO things (save observations, generate materials) without manual form interaction

---

## Problem

Today the voice path is a **transcription shortcut**: mic → text → user manually routes it.

- To save an observation: mic → transcript appears in form → user selects student → presses Save
- To ask a question: mic → transcript appears in Ask box → user presses Send
- To generate a lesson plan: no voice path at all

A teacher in a classroom cannot do 3-step interactions. They need:

- "Marco helped a classmate find the page" → **observation saved automatically**
- "Create a worksheet for tomorrow's lesson on daily routines" → **materials generated**
- "What level is Nora at in reading?" → **answer spoken back**

The missing piece is an **intent router** at the front of the voice pipeline that classifies the transcript and routes it to the correct action endpoint.

---

## What Exists Already

| Component | Location | What it does |
|---|---|---|
| `/api/voice/stt` | `src/web.py:2580` | Transcribes audio → returns text |
| `/api/query` | `src/web.py:4660` | Routes questions through classification → reasoning |
| `/api/observe/capture` | `src/web.py:2886` | Saves an observation to a student lens |
| `/api/lesson-materials/generate` | (Spec 3 — being built) | Generates differentiated worksheets |
| `/api/cohort-plans/preview` | `src/web.py:3622` | Generates a teacher guide with tier groupings |
| `OntologyEngine.classify()` | `src/pipeline.py` | Routes queries to ontology nodes |
| GIR + voice tone | `src/lingua_viva/voice_tone.py` | Adjusts spoken delivery based on grounding quality |

**What's missing**: A classifier that sits AFTER STT and BEFORE routing, that decides:
1. Is this an **observation** about a student? → route to observe/capture
2. Is this a **generation request** (make something)? → route to lesson-materials/generate
3. Is this a **question** (ask something)? → route to /api/query

---

## Design

### New Endpoint
```
POST /api/voice/act
```

Input:
```json
{
  "transcript": "Marco helped a classmate find the right page during reading",
  "audio_blob_id": "optional — if STT was already done externally"
}
```

Output:
```json
{
  "intent": "observation",
  "action_taken": "saved",
  "result": { ... observation result ... },
  "spoken_confirmation": "Got it. Observation saved for Marco.",
  "tone_prefix": "Confirmed. ",
  "gir_score": 1.0
}
```

Or for a question:
```json
{
  "intent": "question",
  "action_taken": "answered",
  "result": { ... query response ... },
  "spoken_response": "Marco is currently at A1+ in reading...",
  "tone_prefix": "Based on 4 observations, ",
  "gir_score": 0.85
}
```

Or for generation:
```json
{
  "intent": "generate",
  "action_taken": "materials_created",
  "result": { ... materials response ... },
  "spoken_confirmation": "Done. I've created 3 differentiated worksheets for daily routines. They're in your Drive folder.",
  "tone_prefix": "",
  "gir_score": 1.0
}
```

### Intent Classification Logic

**No LLM needed for intent detection.** Use signal-based routing (same philosophy as the ontology engine):

```python
OBSERVATION_SIGNALS = [
    # Past tense actions describing student behavior
    r"\b(helped|read|wrote|said|showed|struggled|completed|participated|used|demonstrated)\b",
    # Student name + verb pattern
    r"^(Marco|Nora|Luca|the student|the learner|she|he)\s+\w+ed\b",
    # Observation framing
    r"\b(during|while|in class|this morning|today|at recess|in group)\b.*\b(he|she|they|the student)\b",
    # Direct observation markers
    r"\b(I (noticed|observed|saw|heard)|observation:)\b",
]

GENERATION_SIGNALS = [
    r"\b(create|generate|make|build|prepare|write)\b.*\b(worksheet|lesson|plan|exercise|material|activity)\b",
    r"\b(worksheet|lesson plan|exercise|handout|activity)\b.*\b(for|about|on)\b",
    r"\b(differentiated|customized|adapted)\b.*\b(for|per|by group)\b",
]

QUESTION_SIGNALS = [
    r"\b(what|how|when|where|which|who|is|are|can|should|does)\b.*\??\s*$",
    r"\b(tell me|explain|show me|what level|what tier)\b",
]
```

Classification priority: observation > generation > question (default)

Confidence threshold: if no signals match strongly, default to **question** (safest — doesn't take action).

### Student Detection

For observations, we need to identify WHICH student is being observed:
```python
def detect_student(transcript: str, roster: list[dict]) -> str | None:
    """Match student name in transcript against the teacher's roster."""
    for student in roster:
        name = student.get("display_name", "").lower()
        if name and name in transcript.lower():
            return student["student_id"]
    # Pronoun fallback: if only one student was recently discussed, use them
    return None
```

If no student detected → ask for clarification (don't guess).

### Observation Auto-Parse

For observations, extract CEFR dimension and level from the transcript:
```python
def parse_observation_context(transcript: str) -> dict:
    """Best-effort extraction of observation metadata from natural speech."""
    # Detect CEFR dimension from keywords
    dimensions = {
        "reading": ["read", "reading", "book", "text", "page"],
        "writing": ["wrote", "write", "writing", "sentence", "paragraph"],
        "speaking": ["said", "spoke", "speaking", "oral", "pronunciation"],
        "listening": ["listened", "heard", "understood", "comprehension"],
    }
    # Detect level indicators
    level_hints = {
        "pre-A1": ["struggling", "no words", "gesture only", "silent"],
        "A1": ["basic", "simple words", "one word", "beginning"],
        "A1+": ["short sentences", "helped", "starting to"],
        "A2": ["connected sentences", "actively", "described", "participated"],
        "B1": ["fluently", "complex", "explained", "argued", "debated"],
    }
    ...
```

### Flow

```
Voice input (audio)
    │
    ▼
/api/voice/stt → transcript
    │
    ▼
/api/voice/act (this spec)
    │
    ├─ intent=observation → extract student + context → /api/observe/capture → confirm via TTS
    │
    ├─ intent=generate → extract lesson params → /api/lesson-materials/generate → confirm via TTS
    │
    └─ intent=question → /api/query → answer via TTS (with GIR tone)
```

### Frontend Integration

In `static/index.html`, the voice companion's `onResult` handler currently puts the transcript into a text field. Change it to:

```javascript
// After STT returns transcript:
const actResponse = await api("/api/voice/act", {transcript});
if (actResponse.spoken_confirmation) {
    voiceRuntime.speak(actResponse.spoken_confirmation, actResponse.tone_prefix);
}
// Update UI based on intent (show observation in panel, show materials, show answer)
```

This is a **stretch goal** for the frontend — the backend can work independently via curl/API calls even if the frontend wire isn't done.

---

## Test Plan

### Test 1: Observation intent detected
```
Input: "Marco helped a classmate find the right page during reading"
Expected: intent=observation, student_id=student-marco
```

### Test 2: Generation intent detected
```
Input: "Create a worksheet for tomorrow's lesson on describing daily routines"
Expected: intent=generate
```

### Test 3: Question intent detected (default)
```
Input: "What level is Marco at in reading?"
Expected: intent=question
```

### Test 4: Ambiguous → defaults to question (safe)
```
Input: "Marco reading"
Expected: intent=question (not enough signal for observation)
```

### Test 5: Observation saves and confirms
```
Input: "Nora used A2-level Italian to describe her weekend in group discussion"
Expected: observation saved, spoken_confirmation contains "Nora"
```

### Test 6: No student detected → clarification
```
Input: "The student struggled with basic greetings"
Expected: intent=observation, but needs_clarification=true, asks which student
```

---

## Files to Create/Modify

| File | Action |
|---|---|
| `src/lingua_viva/voice_intent.py` | NEW — intent classifier + student detector + observation parser |
| `src/web.py` | ADD — `/api/voice/act` route |
| `contracts/ROUTE_REACHABILITY.yaml` | ADD — new route |
| `tests/test_voice_intent.py` | NEW — unit tests for classification |
| `static/index.html` | MODIFY (stretch) — wire voice companion to use /api/voice/act |

---

## Safety Rules

1. **Observations always require a detected student.** If no student can be identified, don't save — ask for clarification.
2. **Generation never includes student names in the LLM prompt.** Same rule as Spec 3.
3. **Default to question when uncertain.** Questions are read-only and safe. Observations and generation are write actions — need higher confidence.
4. **All spoken confirmations go through the privacy gate.** Never speak a student's full name over external TTS — use first name only or say "the student."

---

## Definition of Done

- [ ] `/api/voice/act` endpoint classifies transcripts into 3 intents
- [ ] Observation intent auto-saves and confirms
- [ ] Generation intent triggers material creation
- [ ] Question intent routes to existing query pipeline
- [ ] Student detection works against the teacher's roster
- [ ] All safety rules enforced
- [ ] 6+ tests passing
- [ ] Preflight 6/6
- [ ] Full test suite still passes
