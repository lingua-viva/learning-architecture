# SPEC: Frontend Voice Companion → /api/voice/act Wire

**Created**: 2026-08-01
**Status**: READY TO BUILD
**Depends on**: Voice Intent Router (Spec 4 — done, committed)
**Produces**: The mic button in the UI routes through /api/voice/act, enabling single-shot voice commands

---

## Problem

Today the voice companion in `static/index.html` works like this:

1. User taps mic → browser records audio
2. Audio sent to `/api/voice/stt` → transcript returned
3. Transcript is placed into whichever text field is active (Ask box or Observe form)
4. User must manually press Send/Save

After this change:

1. User taps mic → browser records audio
2. Audio sent to `/api/voice/stt` → transcript returned
3. Transcript sent to `/api/voice/act` → action executed automatically
4. Result spoken back via TTS + UI updated (observation appears, answer shown, materials confirmed)

The user says something and things happen. No forms, no buttons.

---

## Current UI Architecture

The voice companion is in `static/index.html` around lines 680-900. Key components:

- `voiceRuntime` object — manages recognition state, audio, speech queue
- `voiceRuntime.speak(text, tonePrefix)` — sends text to `/api/voice/tts`
- `startVoiceCapture()` — starts browser mic recording
- `stopVoiceCapture()` — stops recording, sends to `/api/voice/stt`
- The `onResult` callback after STT currently fills a text field

The voice companion widget is visible on the right side of the app (the green "Mic / Ready" circle).

---

## Design

### Change: After STT, route through /api/voice/act

Replace the current "fill text field" behavior with:

```javascript
async function handleVoiceResult(transcript) {
    // Show transcript in UI immediately (user feedback)
    showVoiceTranscript(transcript);
    updateVoiceCompanion("processing", "Thinking...");

    try {
        const result = await api("/api/voice/act", { transcript });

        if (result.intent === "observation") {
            if (result.needs_clarification) {
                // Ask which student
                voiceRuntime.speak(result.spoken_confirmation);
                updateVoiceCompanion("clarify", "Which student?");
            } else {
                // Observation saved — confirm and update UI
                voiceRuntime.speak(result.spoken_confirmation, result.tone_prefix);
                updateVoiceCompanion("success", "Saved");
                // Refresh the observation panel if visible
                if (state.view === "observe") await loadLens("obs-lens", false);
            }
        } else if (result.intent === "generate") {
            // Materials ready to generate — confirm
            voiceRuntime.speak(result.spoken_confirmation);
            updateVoiceCompanion("ready", "Ready");
            // Could auto-navigate to materials view
        } else if (result.intent === "question") {
            // Answer received — speak it
            const spoken = result.spoken_response || result.result?.answer || "";
            voiceRuntime.speak(spoken, result.tone_prefix);
            updateVoiceCompanion("idle", "Ready");
            // Show answer in chat panel
            if (result.result) appendChatMessage("assistant", result.result.answer || spoken);
        }
    } catch (error) {
        voiceRuntime.speak("Sorry, something went wrong. Try again.");
        updateVoiceCompanion("error", "Error");
    }

    // Return to idle after a delay
    setTimeout(() => updateVoiceCompanion("idle", "Ready"), 3000);
}
```

### Voice Companion States

Update the companion widget to show status:

| State | Icon/Color | Label |
|---|---|---|
| idle | Green mic | "Ready" |
| listening | Red pulse | "Listening..." |
| processing | Yellow spin | "Thinking..." |
| success | Green check | "Saved" / "Done" |
| clarify | Orange ? | "Which student?" |
| error | Red X | "Error" |

### Transcript Display

Show what was heard in a small toast/bubble above the mic button:
```html
<div id="voice-transcript" class="voice-transcript"></div>
```

This gives the user confidence that the system heard them correctly, and lets them interrupt ("no, not that student") if needed.

### Fallback Behavior

If `/api/voice/act` fails or times out:
- Fall back to the OLD behavior (put transcript in the active text field)
- Show a toast: "Voice action failed — your words are in the text box"
- This ensures nothing is lost

### View-Aware Behavior (Optional Enhancement)

If the user is on the Observe tab and speaks, bias toward observation intent:
```javascript
const payload = { transcript };
if (state.view === "observe") payload.bias = "observation";
if (state.view === "ask") payload.bias = "question";
```

The backend can use this hint to break ties in ambiguous cases.

---

## What NOT to Change

- Don't remove the existing text-input flow — some users will type
- Don't change the STT endpoint itself
- Don't change TTS behavior (it already has the privacy gate)
- Don't break the Observe form (it still works independently for manual entry)

---

## Test Plan (Chip tests manually)

### Test 1: Mic → Observation
1. Navigate to any tab
2. Tap mic, say "Marco helped a classmate find the page during reading"
3. Expected: Voice companion shows "Saved", spoken confirmation "Got it. Observation saved for Marco."
4. Check: Students → Marco → should show new observation

### Test 2: Mic → Question
1. Tap mic, say "What level is Marco at in reading?"
2. Expected: Answer spoken back, answer appears in chat

### Test 3: Mic → Generation
1. Tap mic, say "Create a worksheet for daily routines"
2. Expected: Spoken confirmation "Ready to create materials..."
3. (Full auto-generation is future — for now, confirmation is enough)

### Test 4: Mic → Ambiguous
1. Tap mic, say "reading comprehension"
2. Expected: Treated as a question (safe default), answer spoken

### Test 5: No student detected
1. Tap mic, say "The student struggled with basic greetings today"
2. Expected: Spoken prompt "I heard an observation but I'm not sure which student. Can you say their name?"

### Test 6: Error/offline
1. Stop the backend, tap mic, say anything
2. Expected: Transcript appears in text field (fallback), toast says "Voice action failed"

---

## Files to Modify

| File | Action |
|---|---|
| `static/index.html` | MODIFY — voice companion onResult handler, add transcript display, add status states |

---

## Safety Rules

1. Never auto-execute if confidence is low — fall back to text field
2. Always show the transcript so user can verify what was heard
3. Spoken confirmations go through existing TTS privacy gate
4. If no student detected for observation, NEVER guess — ask

---

## Definition of Done

- [ ] Mic tap → STT → /api/voice/act → action executed → confirmation spoken
- [ ] Observation saves appear in student lens without pressing any buttons
- [ ] Questions get answered and spoken without pressing Send
- [ ] Transcript visible to user after recognition
- [ ] Fallback to text field on error
- [ ] Voice companion shows processing/success/error states
- [ ] All existing tests still pass
- [ ] UI contract bumped
