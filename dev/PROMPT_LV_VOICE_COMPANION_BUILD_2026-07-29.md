# Build Prompt — Lingua Viva Voice Companion

You are building a voice companion sidebar for Lingua Viva. Read the spec first:

```
dev/SPEC_LV_VOICE_COMPANION_2026-07-29.md
```

## Critical Rules

1. **ALL UI changes go in `static/index.html`** — vanilla JS/Alpine.js. No React, no TypeScript.
2. **ALL backend routes go in `src/web.py`** — FastAPI. No separate server files.
3. **Do NOT create new JS/TS files** — all frontend code lives in `static/index.html`.
4. **Do NOT touch `src/pipeline.py`** or `src/education/`.
5. **The voice infrastructure already exists** — `voiceRuntime` object (line 525-741), `captureLocalStt()`, `speak()`, `speakLocally()`, backend `/api/voice/stt` and `/api/voice/probe` endpoints, `WhisperLocalProvider` in `src/lingua_viva/voice_stt.py`. You are NOT building voice from scratch. You are adding a **sidebar UI** that calls existing functions.

## What LV Already Has (read, don't rebuild)

- `voiceRuntime.captureLocalStt({statusId, micId, inputId, onTranscript})` — captures audio via getUserMedia, runs silence detection, POSTs to `/api/voice/stt`, calls `onTranscript(text)`. Already working.
- `voiceRuntime.speak(text)` — tries Rime TTS via `/api/voice/tts`, falls back to browser Italian voice. Student-data privacy gate on the backend blocks student names from reaching Rime.
- `voiceRuntime.stopSpeaking()` — cancels both Rime audio and browser speech.
- `voiceRuntime.cleanupCapture()` — releases MediaRecorder, AudioContext, stream.
- Two mic buttons at lines 1109 and 1563 — you will remove these and replace with the companion sidebar's mic.

## Build Steps (do in order)

### Step 1: CSP Fix

In `desktop/electron/main.ts`, find the CSP header block (lines 28-38). Add `media-src 'self' blob:` after the `img-src` line. Without this, Rime audio blob URLs are blocked by Content Security Policy and TTS fails silently.

Before:
```
"img-src 'self' data: blob:",
"font-src 'self' data:",
```

After:
```
"img-src 'self' data: blob:",
"media-src 'self' blob:",
"font-src 'self' data:",
```

Verify: `npm run build` in `desktop/` passes.

### Step 2: Copy Avatar

```bash
mkdir -p static/assets
cp ~/fde/mission-canvas/desktop/src/assets/mc-avatar.png static/assets/mc-avatar.png
```

### Step 3: Add Companion Sidebar to index.html

Find the main layout structure in `static/index.html`. Add a right-side `<aside>` element after the main content area. It should contain:

1. Collapse/expand toggle button
2. Avatar image with visor overlay div (CSS-animated per state)
3. Mic button
4. State label (`role="status" aria-live="polite"`) — shows "Listening" / "Processing"
5. Governance badge — shows "Protected" when student data privacy gate is active

Add CSS for the companion panel:
- Fixed right panel, 200px wide (60px collapsed)
- Dark background matching the existing sidebar style
- Avatar: circular, 80px (44px collapsed)
- Visor overlay: CSS animations for idle (dim pulse), recording (waveform), processing (spinner)
- Mic button: circular, 44px, blue highlight when recording, `:focus-visible` outline
- Mobile: auto-collapse to 60px, hide text elements

Add JS to wire the mic button:
```javascript
document.getElementById("vc-mic").addEventListener("click", function() {
  // Barge-in: stop any ongoing TTS
  voiceRuntime.stopSpeaking();
  // Switch to Ask view
  if (typeof switchView === "function") switchView("ask");
  // Use existing capture → Ask flow
  voiceRuntime.captureLocalStt({
    statusId: "vc-state",
    micId: "vc-mic",
    inputId: "ask-input",
    onTranscript: function(text) {
      // Set the ask input and submit
      var input = document.getElementById("ask-input");
      if (input) input.value = text;
      // Trigger the ask submission
      var form = document.getElementById("ask-form");
      if (form) form.dispatchEvent(new Event("submit", {cancelable: true}));
    }
  });
});
```

Important: Find the actual IDs for the Ask input field and form by searching `static/index.html`. The IDs above (`ask-input`, `ask-form`) are guesses — use the real ones.

### Step 4: Wire Auto-Speak

After the Ask response finishes streaming into the chat area, call `voiceRuntime.speak(responseText)`. Find where the Ask response is finalized in the existing code and add the speak call there. Only speak if the response was triggered by voice input (track this with a flag).

### Step 5: Remove Inline Mic Buttons

Remove the observation mic button at line ~1109 and the ask mic button at line ~1563. Remove their click handlers. The companion sidebar mic replaces both.

Keep the `voiceRuntime` object and all its methods — only remove the buttons that call it.

### Step 6: Exit Gate Check

Search `src/` for exit gate, firewall, or allowlist code. If `users.rime.ai` is not in the allowlist, add it. MC hit this exact blocker — the exit gate blocked Rime TTS calls.

## Verification

After all steps:
1. `cd desktop && npm run build` — passes
2. `cd .. && pytest -q tests/` — passes
3. `python3 -m src.lingua_viva.cli health` — passes
4. Launch with `cd desktop && npm run dev`
5. Companion panel visible on right side of every view
6. Click mic → "Listening" → speak → "Processing" → transcript appears in Ask chat
7. Response auto-speaks via Rime (or local Italian voice for student data)
8. No CSP errors in DevTools console (Ctrl+Shift+I)
9. No duplicate mic buttons anywhere

## MC Reference (read-only, for understanding)

These MC files show the pattern you're adapting to vanilla JS:
- `~/fde/mission-canvas/desktop/src/components/VoiceCompanion.tsx` — React companion (adapt to HTML)
- `~/fde/mission-canvas/desktop/src/voice/capture.ts` — capture logic (LV already has this in `voiceRuntime.captureLocalStt`)
- `~/fde/mission-canvas/desktop/src/styles.css` — companion CSS (search for `.voiceCompanion`)
- `~/fde/mission-canvas/desktop/electron/main.ts` — CSP fix at line 561

Do NOT copy React code into LV. Read the pattern, rewrite in vanilla JS.
