# QA Report: Teacher Readiness — Claudia (2026-08-03)

## Versions Tested

| Item | Value |
|------|-------|
| App version | desktop-v0.2.30 |
| Repo commit | `4ae8d67` |
| Repo state | clean (main) |
| Platform | macOS Darwin 25.3.0 |
| Local URL | http://127.0.0.1:8787 |
| Test data | Synthetic only (Marco Bianchi, Nora Rossi) |

## Summary

Testing covered Rounds 1-3 (checks 1-13) of the 7-round plan. Rounds 4-7 were not reached.

The core observation loop (Round 1) works well. Save, validation, and student creation are solid. Voice transcription (Round 2) is non-functional — `faster-whisper` STT reports `available: false` in the desktop build. The Ask/query system (Round 3) returns no meaningful answer because no local reasoning model is running and external models are correctly blocked by the privacy-first policy.

**Counts: 1 P0, 2 P1, 1 P2, 2 FR**

### P0 Issues

| ID | Description |
|----|-------------|
| P0-1 | **Voice transcription completely non-functional.** STT probe returns `available: false`. The `faster-whisper` Python package is not loadable in the desktop build. Voice is a core teacher workflow (hands-free observation during class) — without it the app loses its primary differentiator. |

### P1 Issues

| ID | Description |
|----|-------------|
| P1-1 | **Ask/query system returns no answer.** Query endpoint responds with `model_used: "none"` and a placeholder `[Local reasoning for LV-STU-002 - no model available]`. Root cause: no local Ollama model running, and external models are (correctly) blocked when student data is involved. The app needs either a bundled local model or clear onboarding to install Ollama. |
| P1-2 | **No connection to external models at install time.** Claudia noted immediately that there was no model connection. The app provides no setup wizard or guidance for connecting a reasoning model. First-time teachers will not know what Ollama is or how to install it. |

### P2 Issues

| ID | Description |
|----|-------------|
| P2-1 | **Unclear save confirmation causes double-save.** Claudia saved Nora's observation twice because the confirmation wasn't obvious enough the first time. The confirmation text appears but may not be visually prominent enough, especially for a teacher working quickly. |

### Feature Requests

| ID | Description |
|----|-------------|
| FR-1 | **Teacher image above the mic.** Replace or supplement the current `mc-avatar.png` with a teacher-appropriate image — something that visually signals "this is your teaching companion," not a generic avatar. |
| FR-2 | **CEFR young learner progressions / can-do lists.** After saving an observation, suggest next steps tied to CEFR young learner descriptors. Connect observations to progression pathways so teachers can see where a student is headed, not just where they are. |

---

## Round-by-Round Checklist

### Round 1 — Core Loop (checks 1-5)

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 1 | Create Marco Bianchi, G3 | PASS | Appears in roster |
| 2 | Create Nora Rossi, G3 | PASS | Appears in roster |
| 3 | Save without observation type | PASS | App refuses to save — correct behavior. Claudia noted this is a good design decision |
| 4 | Save typed observation for Marco (with type) | PASS | Saved with confirmation: "Saved locally. Not uploaded. Not shared." |
| 5 | Save typed observation for Nora (with type) | PASS | Saved, but Claudia double-saved due to unclear confirmation (P2-1) |

### Round 2 — Voice Observations (checks 6-11)

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 6 | Voice: "Marco helped a classmate..." | FAIL (P0-1) | Voice transcription failed 3 times. Tested via text fallback — observation saved correctly under Recent Observations |
| 7 | Spoken confirmation for Marco | NOT TESTABLE | Voice not functional |
| 8 | Marco's record shows new observation | PASS | Observation visible on Marco's record |
| 9 | Voice: "Nora used full sentences..." | FAIL (P0-1) | Tested via text fallback — saved correctly |
| 10 | Ambiguous: "The student struggled..." | PASS | App required explicit student selection — did not guess |
| 11 | Plain note, no invented CEFR level | PASS | Saved as plain note, no language level shown |

### Round 3 — Voice Questions (checks 12-13)

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 12 | "What level is Marco at in reading?" | FAIL (P1-1) | Typed in Ask section. No meaningful answer — model_used: "none" |
| 13 | "How should I group my students?" | NOT TESTED | Session ended before completion |

### Rounds 4-7 — Not Reached

| # | Check | Result |
|---|-------|--------|
| 14-19 | Worksheet generation | NOT TESTED |
| 20-32 | Google Drive | NOT TESTED |
| 33-35 | Cohort lesson planning | NOT TESTED |
| 36-39 | General app health | NOT TESTED |

---

## Teacher Feedback (Claudia's Notes)

- **Observation type requirement is good**: "I think it is a good thing that we need to categorize what type of observation that is."
- **"Saved locally" message is noted**: Claudia observed the local-only save status.
- **CEFR progression gap**: After saving an observation, there is no way to connect it to CEFR young learner progressions or can-do lists. Claudia asked: "How can we make this observation meaningful? Do you have a way to suggest next steps considering CEFR young learner progressions or can-do lists?"
- **No external model connection**: First thing noticed at install — no guidance on how to connect a reasoning model.
- **Voice is expected to work**: The mic button is prominent but non-functional, which will frustrate teachers on first use.
- **Teacher image needed**: The avatar above the mic should be a teacher-appropriate image, not a generic avatar.

---

## Technical Appendix

### Voice Infrastructure — Deep Dive

**Architecture** (all local, no remote API):
- Browser captures audio via `navigator.mediaDevices.getUserMedia()` with WebM/Opus codec
- Audio posted to `POST /api/voice/stt` which calls `faster-whisper` (local Whisper)
- Intent classified by signal-based router in `voice_intent.py` (no LLM needed)
- Student matched via 3-pass detection: exact > fuzzy (80% cutoff) > possessive strip

**Root cause of P0-1 (voice failure)**:
- `GET /api/voice/probe` returns `{"stt": {"available": false}}`
- `src/lingua_viva/voice_stt.py:9-23` — `stt_dependencies_available()` checks for `av` and `faster_whisper` packages
- One or both packages are not importable in the desktop build's Python environment
- Historical context: BUG-2 (fixed 2026-08-02) removed an incorrect `shutil.which("ffmpeg")` gate — but the underlying package availability issue persists in the packaged app
- **Files to investigate**:
  - `src/lingua_viva/voice_stt.py:9-23` — dependency probe
  - `src/lingua_viva/voice_stt.py:32-69` — `WhisperLocalProvider` class
  - `desktop/electron/bootstrap.ts` — Python environment setup during app launch
  - Desktop packaging config — whether `faster-whisper` and `av` are included in the build

**Key files**:

| File | Lines | Role |
|------|-------|------|
| `src/lingua_viva/voice_stt.py` | 9-69 | Local Whisper STT provider + dependency check |
| `src/lingua_viva/voice_intent.py` | 124-445 | Intent classification + student detection |
| `src/lingua_viva/voice_tone.py` | full | GIR-based spoken delivery tone mapping |
| `src/web.py` | 2608-2628 | `GET /api/voice/probe` |
| `src/web.py` | 2631-2647 | `POST /api/voice/stt` |
| `src/web.py` | 2650-2942 | `POST /api/voice/act` — full voice action pipeline |
| `src/web.py` | 1979-2073 | `POST /api/voice/tts` — text-to-speech with privacy gate |
| `static/index.html` | 802-890 | Browser mic capture (`captureLocalStt()`) |
| `static/index.html` | 703-712 | Voice companion HTML (avatar + mic button) |
| `static/index.html` | 367-452 | Voice companion CSS (states: listening/processing/error) |

### Query/Ask System — Deep Dive

**Architecture** (8-step governed pipeline):
1. SCAN — Entry gate, detects student data, forces local-only
2. CLASSIFY — Ontology engine (111 nodes, 25 domains)
3. EXECUTE — Education executor retrieves student lens + RTI data
4. RETRIEVE — Knowledge library + document search
5. REASON — Calls local or cloud LLM (Ollama preferred)
6. SYNTHESIZE — Composes answer with GIR grounding
7. STORE — Persists path record

**Root cause of P1-1 (no answer)**:
- `POST /api/query` returns `model_used: "none"` with `gir.score: 0.0`
- Entry gate correctly detects student data (`forced_local: true`, `reason: "student_data_local_only"`)
- No local Ollama model running — all tier attempts return `miss` or `blocked`
- The pipeline gracefully degrades: returns a placeholder instead of crashing, but the placeholder is not useful to a teacher
- **Resolution**: Either bundle a small local model (e.g., qwen2.5:3b) with the desktop app, or provide a first-run setup wizard that guides the teacher through Ollama installation

**Model resolution order** (`src/lingua_viva/reasoning.py:57-63`):
1. Explicit model parameter
2. User provider config (`~/.lingua-viva/config/providers.json`)
3. Ontology default model
4. `LV_REASON_MODEL` env var
5. Best available Ollama model (auto-detected)

**Supported local models**: phi4:14b, qwen2.5:14b, llama3.1:8b, qwen2.5:7b, mistral:7b, qwen2.5:3b

**Key files**:

| File | Lines | Role |
|------|-------|------|
| `src/web.py` | 5676-5832 | `POST /api/query` endpoint |
| `src/lingua_viva/app.py` | 4-36 | `run_teacher_query()` bridge |
| `src/pipeline.py` | 590-1006 | 8-step governed pipeline |
| `src/lingua_viva/reasoning.py` | 27-327 | Reasoning engine + model resolution |
| `src/lingua_viva/config.py` | 1-200 | Provider config + API key lookups |
| `src/education/pipeline_execute.py` | 216-285 | Student data retrieval for queries |
| `src/education/student_lens.py` | 1-200 | Local SQLite student storage |

### Observation Save Flow — Deep Dive

**Root cause of P2-1 (double save)**:
- `static/index.html:1853-1908` — `saveObservation()` function
- Button IS disabled during the request (line 1871), so true double-click is prevented
- Confirmation appears ONLY after successful save (lines 1889-1901) as text in the form area
- **The issue**: confirmation is textual and blends into the form. On a quick save, the teacher may not notice it appeared, especially if the form clears simultaneously (line 1901)
- **No server-side deduplication**: no idempotency key or timestamp check to detect duplicate submissions
- **Recommendation**: Add a more prominent visual confirmation (toast/banner with timestamp), and add server-side deduplication via observation UUID

**Key files**:

| File | Lines | Role |
|------|-------|------|
| `static/index.html` | 1853-1908 | `saveObservation()` — frontend save flow |
| `src/web.py` | 3231-3338 | `POST /api/observe/capture` — backend capture |
| `src/education/observation_capture.py` | 165-189 | `ObservationCapturePipeline.capture()` |

### UI Architecture

- **Desktop shell**: Electron v31.3.1
- **Backend**: FastAPI + Uvicorn on localhost:8787
- **Frontend**: Vanilla JavaScript (5,868 lines in single `static/index.html`)
- **No framework**: Pure DOM manipulation with custom `$()` selector
- **Voice companion**: Right sidebar with avatar (`/assets/mc-avatar.png`, 2.3 MB), mic button, and state visor (listening/processing/error/success states via CSS classes)

### Environment

| Item | Value |
|------|-------|
| OS | macOS Darwin 25.3.0 |
| Session folder | `~/qa-sessions/lingua-viva-2026-08-03_1837/` |
| Health endpoint | All 29 checks PASS |
| Voice probe | STT: available=false, TTS: rime_configured=false, local_fallback=true |
| External calls | false (confirmed by health + query trace) |

### Event Log

```
[2026-08-03T01:38:18Z] SESSION START
[2026-08-03T01:38:18Z] App healthy at http://127.0.0.1:8787
[2026-08-03T01:38:18Z] Health: all 29 checks PASS, external_calls=false
[2026-08-03T01:38:18Z] Repo commit: 4ae8d67, tag: desktop-v0.2.30
[2026-08-03T01:38:18Z] NOTE (Claudia): No connection to external models
[2026-08-03T04:00:55Z] Check 1: PASS — Marco Bianchi created, appears in roster
[2026-08-03T04:04:05Z] Check 2: PASS — Nora Rossi created, appears in roster
[2026-08-03T04:06:00Z] Check 3: PASS — App refuses save without observation type
[2026-08-03T04:10:00Z] Check 4: PASS — Marco observation saved
[2026-08-03T04:12:00Z] Check 5: PASS — Nora observation saved (double-save due to unclear confirmation)
[2026-08-03T04:15:00Z] Check 6: FAIL — Voice transcription failed x3, text fallback used
[2026-08-03T04:15:00Z] Check 7: NOT TESTABLE — Voice not functional
[2026-08-03T04:17:00Z] Check 8: PASS — Marco record shows observation
[2026-08-03T04:19:00Z] Check 9: PASS — Nora observation via text fallback
[2026-08-03T04:21:00Z] Check 10: PASS — App requires explicit student selection
[2026-08-03T04:23:00Z] Check 11: PASS — Plain note, no invented CEFR level
[2026-08-03T04:25:00Z] Check 12: FAIL — Ask returns no answer (no model available)
[2026-08-03T04:27:00Z] Check 13: NOT TESTED — Session ended
[2026-08-03T04:27:00Z] SESSION END
```
