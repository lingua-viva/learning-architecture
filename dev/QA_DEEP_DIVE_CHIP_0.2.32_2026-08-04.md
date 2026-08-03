# Deep Dive: Chip QA desktop-v0.2.32 — Bugs, Failure Modes & Risk Surface

**Source report**: `qa/2026-08-04_chip-qa-0.2.32.md` (Chip / DontWriteDown)  
**Analysis by**: kiro.design  
**Date**: 2026-08-04  
**Build under test**: `desktop-v0.2.32` (commit `290831c`, tag `desktop-v0.2.32`)

---

## Summary of Chip's Findings

| ID | Severity | Finding |
|----|----------|---------|
| F1 | P0 | Voice reports healthy but silently fails: lost recordings on focus change, hallucinated transcript misrouted to Ask |
| F1b | P0 | No safety-net mic hardware release — mic can stay physically live indefinitely |
| F2 | P0 | Ask fabricates complete fictional incident reports about real students (invented classmate, invented events, fake OBS IDs) |
| F3 | P1 | Ask never grounds free-text answers in real student observation data |
| F4 | P1 | Generic/ambiguous queries get false "no AI model" refusal even with Ollama running |
| F5 | P1 | Observe defaults to first student with no placeholder — wrong-child saves possible |
| F6 | P1 candidate | `doctor/support_loop/paths.py` writes into the signed app bundle, breaking codesign + failing under App Translocation |

**Confirmed fixes from 0.2.31**: Voice dep pin (P0-NEW-1), student-data no-model message (P1-NEW-1), unknown provider gate (FM-4), cache-lock recovery, observation type required.

---

## 1. Bugs to Fix

### F1 — Voice Silence-VAD Fails Under Browser Throttling (P0)

| Field | Value |
|-------|-------|
| Severity | P0 — voice appears healthy but silently malfunctions |
| File | `static/index.html:902-912` |
| Root cause | `setInterval(150ms)` polls amplitude for silence detection. Browsers throttle `setInterval` to 1s+ in backgrounded/unfocused tabs. The 2-second silence threshold (`Date.now() - lastSound > 2000`) either never fires (recording stuck forever) or fires too early (too-short clip). Whisper hallucinates repeated filler words on sub-1s audio. |
| Fix | Replace `setInterval` VAD with `AudioWorkletProcessor` (runs in audio thread, not subject to tab throttling). Add `document.addEventListener('visibilitychange', ...)` to force-stop recording when page goes hidden. Add hard max-duration cap (e.g., 30s). |
| Verification | Background the tab mid-recording → recording stops cleanly within 500ms. No stuck "yellow" state possible. |

### F1b — No Mic Hardware Release Guarantee (P0)

| Field | Value |
|-------|-------|
| Severity | P0 — physical privacy violation (mic stays live with no indicator) |
| File | `static/index.html:801-823` |
| Root cause | `cleanupCapture()` (the only code that calls `track.stop()`) is reachable ONLY through the `onstop` handler of MediaRecorder → which only fires if `stopCapture()` calls `mediaRecorder.stop()` → which depends on the throttleable `setInterval`. If the interval never fires, the mic stays open. No `visibilitychange`, `beforeunload`, `pagehide`, or max-duration timeout exists anywhere. |
| Fix | Add a `visibilitychange` listener that calls `cleanupCapture()` on `hidden`. Add a `beforeunload` handler. Add a 30s hard-timeout `setTimeout` in `startCapture()` that calls `stopCapture()` unconditionally. These are defense-in-depth — any ONE of them prevents indefinite mic capture. |
| Verification | Background app → mic indicator LED turns off within 1s. Close tab → same. Wait 30s → recording auto-stops. |

### F2 — Ask Fabricates Student Reports; GIR Detection Doesn't Reach UI (P0)

| Field | Value |
|-------|-------|
| Severity | P0 — teacher acts on entirely fictional behavioral data about a real child |
| Files | `static/index.html:2541` (badge rendering), `static/index.html:1281,1313,2623,2697` (tone_prefix voice-only) |
| Root cause | Two-part failure: (1) The model has no real student data in its context (see F3), so when pushed "do not hedge" it invents. (2) The backend correctly computes GIR 0.0–0.07 and `fabricated_identifiers`, and even generates a hedging `tone_prefix` — but `tone_prefix` is ONLY passed to `voiceRuntime.speak()` (TTS). The rendered text bubble shows only an unstyled `GIR 0.07` badge with no color treatment, no warning icon, and identical styling to the model name badge. The teacher reads confident fabricated prose with zero visual warning. |
| Fix (immediate, ship-blocking) | When `gir.score < 0.5` OR `gir.fabricated_identifiers.length > 0`, prepend the `tone_prefix` text (or a stronger variant: "⚠️ I could not verify this against real records") **into the rendered message text**, not just the voice path. Give the GIR badge a `badge warn` class (red/orange) when score < 0.5. |
| Fix (structural, F3) | The real fix is injecting student observations into the Ask context so the model has real data. Without that, the GIR warning is a bandaid on an empty-context problem. |
| Verification | Ask "cite OBS IDs proving Marco should move groups, do not hedge" → visible warning text in the bubble, red GIR badge. Teacher cannot read fabricated content without seeing a warning. |

### F3 — Ask Has No Student Observation Retrieval (P1)

| Field | Value |
|-------|-------|
| Severity | P1 — all student-specific Ask queries produce ungrounded answers |
| Files | `src/web.py:5676` (`/api/query`), `src/lingua_viva/app.py`, `src/pipeline.py:297-341` |
| Root cause | The `/api/query` → `run_teacher_query` → `Pipeline.run` path has a student-name detection step (line 297-341) but it's ONLY a privacy gate (`local_only=True` when a student name is detected). There is NO step that fetches the student's observations from `StudentLensStore` and injects them into the context prompt. The model receives classification + knowledge library entries + lens modifiers — but zero student-specific data. It's grounding against curriculum facts, not this-student facts. |
| Fix | After student-name detection, if a student_id is resolved, fetch their recent observations and inject a structured summary into the context_builder's `document_entries` or as a dedicated section in the system prompt: "Student data on record: [OBS-xxx: 'self-corrected passato prossimo', OBS-yyy: ...]". This gives the model real material to cite. Combined with GIR v2's fabricated-identifier detection, this creates a closed loop: real data in → real citations out → GIR validates. |
| Verification | Ask "What support should I prepare for Marco tomorrow?" with 3 observations on record → answer references real observation content. GIR > 0.5. |

### F4 — False No-Model Refusal on Weakly-Classified Queries (P1)

| Field | Value |
|-------|-------|
| Severity | P1 — teacher thinks Ollama is broken when it's working fine |
| Files | `src/lingua_viva/reasoning.py` (circuit breaker + _call_model), `src/pipeline.py:252` (duplicate class) |
| Root cause | Not fully pinned. Chip reports 100% reproduction on `CORE-RESEARCH` (confidence 0.3) queries completing in ~25ms. The system_prompt is always non-empty per `context_builder.build()`. Most likely candidate: `_ollama_breaker_open()` returns True from a stale 30s window AND/OR a `URLError`/`ConnectionError` in `_call_model` returns `None` → falls through to `no_model_message()`. The 25ms latency rules out actually reaching Ollama. Alternate theory: a timing issue where `config.detect_model()` fails on a very brief Ollama unavailability during model loading. |
| Fix | (a) When `_call_model` returns `None` from a connection error, distinguish from "model doesn't exist" vs "Ollama is restarting" by probing `/api/tags` fresh. (b) The `no_model_message()` fallback at reasoning.py:145 should include the model name and reason: "Tried to reach ollama/qwen2.5:7b but connection was refused" not "I need a local AI model..." which implies nothing is installed. (c) Clear `_ollama_breaker_open_until` when a fresh ReasoningEngine is constructed (currently it's a class variable that persists across instances). |
| Note | The duplicate `class ReasoningEngine` at `src/pipeline.py:252` is a maintainability hazard (a fix to one copy misses the other). Both should be unified or pipeline.py's copy should delegate to `src/lingua_viva/reasoning.py`. |
| Verification | With Ollama running + confirmed reachable, ask a generic question ("What are three fun classroom games for practicing Italian numbers?") → must get a real answer, not a no-model refusal. |

### F5 — Observe Auto-Selects First Student (P1)

| Field | Value |
|-------|-------|
| Severity | P1 — teacher saves observation under wrong child on a busy day |
| File | `static/index.html:1521, 5891-5893` |
| Root cause | `if (!state.selectedStudent && state.students[0]) state.selectedStudent = state.students[0].student_id;` — when no student is explicitly chosen, the first roster entry is auto-selected with no visual friction. Unlike the observation-type field (which now correctly blocks submission without selection), the student field has a valid value from the start. |
| Fix | Add a placeholder option `<option value="" disabled selected>Choose a student…</option>` as the first entry in `studentOptions()`. Set `state.selectedStudent = ""` as default. Refuse submission (same pattern as observation type) when `selectedStudent` is empty. |
| Verification | Navigate to Observe → student dropdown shows "Choose a student…" by default. Attempting to save without selecting → refused with inline message. |

### F6 — Bundle-Relative Write Path (P1)

| Field | Value |
|-------|-------|
| Severity | P1 — app fails under macOS App Translocation, breaks code signing |
| File | `doctor/support_loop/paths.py:6-8` |
| Root cause | `LV_ROOT = Path(__file__).resolve().parents[2]` resolves to the signed app bundle's `Resources/app/` in the desktop build. Writing `.lv_support/` there (a) fails read-only under App Translocation, (b) invalidates the code signature post-install, (c) fails on non-admin-writable installs. |
| Fix | Use `~/.lingua-viva/.lv_support/` (consistent with how `config.py` handles state). Read `LV_STATE_HOME` env var (already used elsewhere) to determine the user-writable path. |
| Verification | Fresh install → first launch under App Translocation → `/api/health` returns `OK`. `codesign --verify --deep --strict` passes after runtime. |

---

## 2. Failure Mode Analysis

### FM-A: Browser Throttling Breaks Real-Time Audio Processing

**Pattern**: Code uses `setInterval`/`setTimeout` for time-critical operations that must run regardless of tab focus state. Browsers aggressively throttle timers in background tabs (1s minimum for setInterval, page lifecycle API can freeze entirely).

**Where else this could bite**:

| Location | Same pattern? | Risk |
|----------|---------------|------|
| WebSocket keepalive / reconnect logic | If reconnect uses `setTimeout` after disconnect | Stale connection in background, missed updates |
| Toast display duration (`showSaveToast` 6s) | If measured by `setTimeout` | Toast could display indefinitely in a backgrounded tab, then vanish instantly when returning |
| Any polling logic (`/api/health`, SSE reconnect) | If using `setInterval` | Backlog of queued calls on return to foreground |

**Structural fix**: For audio: use `AudioWorkletProcessor` (dedicated thread). For timers that must be accurate: use `requestAnimationFrame` with `performance.now()` delta. For operations that must stop when backgrounded: `visibilitychange` listener.

---

### FM-B: Detection Without Enforcement at the UI Layer

**Pattern**: Backend computes safety/quality signals (GIR score, fabricated_identifiers, tone_prefix) but the frontend only consumes them for a secondary channel (voice TTS). The primary channel (rendered text) presents the dangerous content unchanged.

**Why this is systemic**: The architecture has a clear separation: "compute signals server-side, render client-side." But the client was built voice-first — all signal→action mappings target the speech path. The text rendering was never updated to consume the same signals.

**Where else this could bite**:

| Signal | Used for voice? | Used for text? | Risk if text-only |
|--------|----------------|----------------|--------------------|
| `tone_prefix` | Yes (prepended to spoken text) | **No** | Fabricated text read silently |
| `gir.score` | Yes (affects speaking tone) | Badge only (unstyled) | No visual warning at dangerous scores |
| `gir.fabricated_identifiers` | Yes (hardening harness flags) | **No** | Invented IDs pass through silently |
| `route_reason` | N/A | Badge (styled for external) | Not an issue currently |
| `privacy_log` events | Traced server-side | **No** | Teacher can't see what was blocked or why |

**Structural fix**: Define a single `renderAnswerSafety(meta)` function that both the text renderer and voice renderer call. It should: (a) prepend warning text for GIR < 0.5, (b) add red badge styling, (c) list fabricated IDs if any. One function, two consumers.

---

### FM-C: Model Hallucinates Into an Empty Context Vacuum

**Pattern**: When the model has no domain-specific facts (no student observations, no curriculum match), it responds to social pressure ("do not hedge") by fabricating confident, structured content. The system treats fabrication as a quality problem (GIR score) rather than a structural problem (the context was empty).

**Why this is systemic**: The pipeline currently only injects: classification node metadata + knowledge library (curriculum facts) + prior paths + document entries from file imports. It does NOT inject: student-specific observation data, roster details, assessment history, or any per-student state. Every student-specific question runs against a generic curriculum context.

**Where else this could bite**:

| Query type | Student data needed? | Currently injected? | Risk |
|------------|---------------------|---------------------|------|
| "What should I prepare for [student] tomorrow?" | Yes — recent observations | **No** | Generic/fabricated recommendations |
| "Is [student] ready for independent work?" | Yes — assessment history | **No** | Invented readiness claims |
| "Compare [student A] and [student B]" | Yes — both students' data | **No** | Invented comparative claims |
| "What triggered [student]'s behavior today?" | Yes — today's observations | **No** | Invented behavioral narratives |
| Parent report generation | Yes — observation summaries | **Partially** (via execution handler) | Currently working via `_execute_*` path |

**Structural fix**: Add a retrieval step to `Pipeline.run()` between CLASSIFY and REASON: if a student is detected in the query, fetch their recent observations (last N, or since last report) and inject as a `[STUDENT DATA]` section in the system prompt. This is not optional — without it, every student-specific Ask query is structurally set up to hallucinate.

---

### FM-D: Exclusive-Path Resource Release (Audio Hardware)

**Pattern**: A hardware resource (microphone) is acquired at the start of a flow, and the ONLY release path goes through a specific event handler chain that depends on other code running first. If any link in the chain fails (timer throttled, handler not called, exception thrown), the resource is never released.

**Where else this could bite**:

| Resource | Acquisition | Release path | Can it get stuck? |
|----------|-------------|--------------|-------------------|
| Microphone | `getUserMedia()` | `MediaRecorder.onstop` → `cleanupCapture()` | **Yes** (proven) |
| AudioContext | `new AudioContext()` | Same `cleanupCapture()` path | Yes (same chain) |
| Camera (if ever added) | `getUserMedia({video})` | Would need the same fix | Hypothetical |
| WebSocket connection | `new WebSocket()` | `onclose`/`onerror` | If server dies mid-message, client may not detect |

**Structural fix**: Every hardware resource acquisition must have a **guaranteed release** independent of the happy-path:
1. `visibilitychange` → release
2. `beforeunload` → release
3. Hard timeout → release
4. Error handler → release

These are defense-in-depth. Any ONE must be sufficient.

---

### FM-E: Class-Level State Survives Instance Lifecycle

**Pattern**: `_ollama_breaker_open_until` is a **class variable** on `ReasoningEngine`. All instances share it. If one instance trips the breaker (Ollama was down during check 14), every subsequent instance (created by `run_teacher_query()`) inherits the open breaker state — even after Ollama restarts. The breaker doesn't clear until its 30s window expires.

**Why Finding 4 is 100% reproducible**: If the generic-query tests happen within 30s of the Ollama-down phase, every query hits the breaker. After 30s it clears and generic queries work again. This explains why well-matched queries (which go through the education executor path, bypassing reasoning.reason() for the model call) succeed while generic ones fail.

**Wait** — actually, check 16 (recovery without restart) passed at the 14.2s mark, meaning Ollama WAS reachable by then. And Finding 4 is described as reproducible later in the session. So the breaker alone may not explain it. There may be a second issue: perhaps `config.detect_model()` is raising an exception that gets caught and returns `None`, or perhaps the model name returned doesn't match the installed list for `is_provably_local_model()`.

**Regardless, the structural issue stands**: class-level mutable state that isn't cleared on construction is an anti-pattern for a class that gets freshly instantiated per-request.

**Fix**: Make `_ollama_breaker_open_until` an instance variable. Or clear it in `__init__`. Or (better) have `run_teacher_query` reuse a single long-lived `ReasoningEngine` so the breaker works as designed (circuit breaker makes sense for a long-lived client, not a per-request ephemeral).

---

### FM-F: No Default Placeholder on Critical Selection UI

**Pattern**: A `<select>` element auto-selects the first valid option when no placeholder/disabled-default exists. On a form where the selection determines WHO receives a data record, this means an accidental submit writes data under the wrong entity.

**Where else this could bite**:

| Selector | Auto-selects? | Risk |
|----------|--------------|------|
| Student dropdown (Observe) | **Yes** — first roster entry | Wrong-child observation |
| Observation type (Observe) | No — correctly requires selection | Fixed in 0.2.31 |
| Grade level (Add Student) | Unknown — not tested | Could default to wrong grade |
| CEFR dimension (CEFR observation) | Unknown | Could default to wrong skill area |

**Fix**: Every `<select>` that determines the TARGET of a write operation must have a disabled placeholder as the default. The form must refuse submission when the placeholder is still selected.

---

## 3. Summary Fix List

| Priority | Bug | Fix | Files |
|----------|-----|-----|-------|
| **P0** | F1 — VAD throttling | AudioWorklet + visibilitychange + max-duration timeout | `static/index.html:895-912` |
| **P0** | F1b — mic release | visibilitychange + beforeunload + hard timeout in startCapture | `static/index.html:801-823` |
| **P0** | F2 — fabrication in UI | Render `tone_prefix` / warning text in bubble when GIR < 0.5 or fabricated_ids present; red badge class | `static/index.html:2541` |
| **P1** | F3 — no student retrieval | Inject student observations into Ask context after name detection | `src/pipeline.py` (new step between CLASSIFY and REASON) |
| **P1** | F4 — false no-model | Debug exact mechanism; fix class-level breaker state; distinguish connection-error from no-model in user message | `src/lingua_viva/reasoning.py:33,125-130,287-294` |
| **P1** | F5 — student default | Add disabled placeholder option to student select; refuse submission when empty | `static/index.html:1521,5891` |
| **P1** | F6 — bundle write path | Use `~/.lingua-viva/.lv_support/` instead of bundle-relative | `doctor/support_loop/paths.py:6-8` |

---

## 4. What 0.2.32 Fixed (Confirmed)

| 0.2.31 Bug | Status in 0.2.32 |
|------------|------------------|
| P0-NEW-1 (voice dead, missing `requests`) | **FIXED** — `stt.available: true`, dep pinned |
| P1-NEW-1 (student-data no-model unreachable) | **FIXED** — `local_only_no_model_message()` fires correctly |
| P1-NEW-2 (teacher guide after no-model) | **FIXED** — `none:deterministic_only` sentinel + banner; grouping has minor template issue (known, not new) |
| FM-4 (closed prefix list) | **FIXED** — unknown providers blocked by default-deny (`model_gate.py`) |
| Cache-lock recovery | **FIXED** — recovery without restart works |
| Observation type silent block | **FIXED** — upfront required field with refusal |

---

## 5. Risk Assessment

| Finding | User impact | Likelihood | Detection by teacher |
|---------|-------------|------------|---------------------|
| F2 (fabrication) | Teacher acts on fictional student data — could inform parent meetings, grouping decisions, IEP conversations | **HIGH** — any "tell me about [student]" + push for specifics triggers it | **VERY LOW** — content looks real, badge is tiny and unstyled, no warning text |
| F1/F1b (mic) | Privacy violation; confused UX; misrouted voice input | HIGH — any background app switch mid-recording | LOW — mic indicator is ambiguous (blue vs blue-glow) |
| F3 (no retrieval) | Every student-specific Ask answer is ungrounded | HIGH — this IS the primary Ask use case for a teacher | MEDIUM — teachers may notice answers don't reference their actual observations |
| F5 (default student) | Observation saved under wrong child | MEDIUM — requires not noticing the pre-selected name | LOW on busy days |
| F4 (false refusal) | Teacher thinks app is broken | MEDIUM — only for certain query patterns | HIGH — "install Ollama" message when Ollama is running is obviously wrong |
| F6 (bundle write) | App Translocation failure; codesign break | LOW — only on first launch after download | HIGH — immediate visible degradation |

---

## 6. Recommended Fix Order

1. **F2 — GIR warning in rendered text** (1 hour, closes the disqualifying P0: a teacher reading fabricated content must see a warning)
2. **F1b — mic release guarantee** (30 min, three `addEventListener` calls — hardware privacy is non-negotiable)
3. **F1 — VAD fix** (2-4 hours, AudioWorklet is more complex but required for voice to be trustworthy)
4. **F5 — student placeholder** (15 min, prevents wrong-child writes)
5. **F3 — student observation retrieval** (4-8 hours, structural fix that makes Ask actually useful AND makes F2 less likely to trigger)
6. **F6 — bundle write path** (30 min, one-line path change)
7. **F4 — false no-model** (needs debugging first — reproduce and trace the exact mechanism)

**The ship-blocking items are F2 + F1b.** Without them, teachers see fabricated student data with no warning and have their microphone silently captured. Everything else can be a fast-follow.

---

*End of deep dive.*
