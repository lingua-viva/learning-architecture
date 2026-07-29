# SPEC: Lingua Viva Voice Companion — Sidebar + Unified Flow + CSP Fix

**Date**: 2026-07-29
**Status**: DRAFT — operator review before build
**Lens**: Voice Engineer (primary), Cathy Pearl (UX)
**Depends on**: Existing voice infra (STT, TTS, capture all already built)
**Branch**: `feat/voice-companion`

---

## What Already Works in LV

LV's voice infrastructure is **substantially further along than MC was**. The
following are already built and functional:

| Component | Status | Location |
|---|---|---|
| `WhisperLocalProvider` (local STT) | Built | `src/lingua_viva/voice_stt.py` |
| `POST /api/voice/stt` | Built | `src/web.py:2322-2338` |
| `GET /api/voice/probe` | Built | `src/web.py:2297-2319` |
| Rime TTS with student-data privacy gate | Built | `src/web.py:1703-1782` |
| `getUserMedia` + `MediaRecorder` capture | Built | `static/index.html:571-651` |
| Silence detection (2s, FFT analyser) | Built | `static/index.html:599-606` |
| Electron `setPermissionRequestHandler` | Built | `desktop/electron/main.ts:526-528` |
| Two mic buttons (Observe + Ask) | Built | `static/index.html:1109, 1563` |
| `voiceRuntime` object (capture, speak, cleanup) | Built | `static/index.html:525-741` |
| Italian voice selection for local TTS | Built | `static/index.html:706-711` |
| Voice tests (STT + TTS privacy gate) | Built | `tests/test_voice_stt.py`, `tests/test_voice_tts_privacy_gate.py` |
| `faster-whisper` pip dep | Built | `desktop/electron/main.ts` |

## What's Broken / Missing

### 1. CSP blocks Rime audio playback (BLOCKER)

**Same bug as MC.** `desktop/electron/main.ts:28-38` sets CSP with no
`media-src` directive. When Rime returns audio and the frontend creates a
blob URL for playback, CSP blocks it:

```
Refused to load media from 'blob:...' because it violates Content Security
Policy directive: "default-src 'self' http://127.0.0.1:8787"
```

**Fix**: Add `media-src 'self' blob:` to the CSP.

**Files**: `desktop/electron/main.ts` (1 line)

### 2. No voice companion sidebar

Mic buttons are inline in their respective views (Observe has one at line
1109, Ask has one at line 1563). There's no persistent, always-visible voice
control panel. When the user navigates to a different view, they lose the
mic button.

**What to build**: A right-side voice companion panel identical in function
to MC's — avatar, mic button, state indicator, governance badge. Always
visible across all views.

**Key difference from MC**: LV is vanilla JS/Alpine.js in a single
`static/index.html` file. No React, no TypeScript, no components. The
companion must be built as HTML + vanilla JS inside `index.html`.

### 3. No unified voice flow

When the user speaks via the Ask mic, the transcript and response stay in
the Ask view. There's no guarantee the user sees the response if they're on
a different view. And voice output (TTS) and text output (chat) should
converge to the same display surface.

**What to build**: Voice input from the companion sidebar should feed into
the Ask view's chat thread, auto-switch to Ask if on another view, and
auto-speak the response via Rime.

### 4. Rime exit gate

LV's exit gate (if it has one) may need `users.rime.ai` allowlisted, same
as MC. Verify before assuming TTS works in production.

---

## Design

### Voice Companion Sidebar (right-side, always visible)

```
┌──────────────────────────────────┬──────────┐
│                                  │          │
│   Main content                   │  Avatar  │
│   (Ask, Observe, Sources,        │  ~~~~~~  │
│    Governance, Actions, etc.)    │  [Mic]   │
│                                  │          │
│                                  │ state    │
│                                  │          │
│                                  │ badge    │
│                                  │          │
└──────────────────────────────────┴──────────┘
```

**Elements**:
- Avatar image (LV-specific — use the female MC avatar for now, or a
  LV-specific one if available)
- Mic button — always visible, triggers `voiceRuntime.captureLocalStt()`
- State indicator — "Listening" / "Processing" (text, not just visual)
- Governance badge — "Student data protected" when privacy gate active
- Collapse/expand toggle

**Behavior**:
- Mic click → capture audio → POST `/api/voice/stt` → transcript
- Transcript → inject into Ask view's input + auto-submit
- Auto-switch to Ask view if on another view
- Response streams into Ask chat → auto-speak via `voiceRuntime.speak()`
- Privacy: if student data detected in response, TTS uses local Italian
  voice (existing gate handles this)

### Remove inline mic buttons

The two existing mic buttons (Observe at line 1109, Ask at line 1563) should
be removed from their inline positions. The companion sidebar's mic replaces
both. The companion determines which flow to use based on the active view:
- If on Observe view → capture routes to observation flow
- If on any other view → capture routes to Ask flow

### Chat-from-sidebar capability

The user wants to be able to do "whatever we can do in the sidebar with chat
interface." This means:
- The companion sidebar's mic is equivalent to typing in the Ask textarea
  and pressing Send
- Voice input produces the same result as typed input
- The sidebar is a voice-first shortcut to the Ask experience

---

## Implementation Slices

### Slice 1: CSP Fix (XS)

Add `media-src 'self' blob:` to the CSP in `desktop/electron/main.ts`.

**File**: `desktop/electron/main.ts` (1 line added)

**Test**: Rime TTS plays audio in Electron without CSP error in console.

### Slice 2: Voice Companion HTML + JS (M)

Add the companion sidebar to `static/index.html`:

1. Add HTML for the right-side panel after the main content area:
   ```html
   <aside id="voice-companion" class="voice-companion">
     <button id="vc-collapse" class="vc-collapse">▶</button>
     <div class="vc-avatar-container">
       <img src="/static/assets/mc-avatar.png" alt="LV Voice" class="vc-avatar" />
       <div id="vc-visor" class="vc-visor"></div>
     </div>
     <button id="vc-mic" class="vc-mic" aria-label="Start voice input">Mic</button>
     <div id="vc-state" class="vc-state" role="status" aria-live="polite"></div>
     <div id="vc-badge" class="vc-badge"></div>
   </aside>
   ```

2. Add CSS for the companion panel (right-side, fixed, always visible).
   Match MC's visual style: 200px expanded, 60px collapsed, dark background,
   avatar with visor overlay, pulse/wave animations.

3. Wire the mic button:
   ```javascript
   $("vc-mic").addEventListener("click", () => {
     // Stop any ongoing TTS (barge-in)
     voiceRuntime.stopSpeaking();
     // Switch to ask view if not already there
     if (currentView !== "ask") switchView("ask");
     // Use existing captureLocalStt with Ask flow
     voiceRuntime.captureLocalStt({
       statusId: "vc-state",
       micId: "vc-mic",
       inputId: "ask-input",
       onTranscript(text) {
         // Inject into ask input and auto-submit
         $("ask-input").value = text;
         submitAsk();
       }
     });
   });
   ```

4. Wire auto-speak: after Ask response finishes streaming, call
   `voiceRuntime.speak(responseText)`.

**File**: `static/index.html` (HTML + CSS + JS additions)

**Test**: Mic button visible on all views. Click → capture → transcript in
Ask chat → response spoken aloud.

### Slice 3: Remove Inline Mic Buttons (S)

Remove the observation mic button (line 1109) and ask mic button (line 1563)
from their inline positions. All voice input goes through the companion
sidebar.

**File**: `static/index.html` (remove 2 buttons + their event handlers)

**Test**: No duplicate mic buttons. Companion mic works from every view.

### Slice 4: Copy Avatar Asset (XS)

Copy the MC avatar to LV's static assets:
```bash
cp ~/fde/mission-canvas/desktop/src/assets/mc-avatar.png \
   ~/learning-architecture/static/assets/mc-avatar.png
```

Or use a LV-specific avatar if operator provides one.

**File**: `static/assets/mc-avatar.png` (new)

### Slice 5: Exit Gate Check (XS)

Verify `users.rime.ai` is in LV's exit gate allowlist (if LV has one).
If not, add it. MC hit this exact blocker.

**Files**: Check `src/lingua_viva/` for exit gate / firewall module.

---

## Files Touched

| Action | File |
|---|---|
| MODIFY | `desktop/electron/main.ts` (CSP fix — 1 line) |
| MODIFY | `static/index.html` (companion panel HTML/CSS/JS, remove inline mics) |
| NEW | `static/assets/mc-avatar.png` (avatar image) |
| POSSIBLY | Exit gate / firewall module (Rime allowlist) |

## Verification

1. Launch app via `npm run dev` in `desktop/`
2. Companion panel visible on right side across all views
3. Click mic → "Listening" state → speak → "Processing" → transcript in Ask chat
4. Response streams → auto-speak via Rime (Italian voice for student-safe
   content, local Italian for student-data content)
5. No CSP errors in DevTools console
6. Existing tests pass: `pytest -q tests/`
7. `python3 -m src.lingua_viva.cli health` passes

## What This Does NOT Cover

- LV-specific avatar design (uses MC avatar for now)
- Voice-to-observation flow (currently removed — re-add as future
  enhancement with view-aware routing)
- Advanced voice UX (reading-position highlighting, multi-turn)
- Auto-release workflow (separate Stage 0 in the integration spec)
