# Build Prompt — Frontend Voice Companion Wire to /api/voice/act

You are implementing `dev/SPEC_LV_FRONTEND_VOICE_WIRE_2026-08-01.md`.

Read first:

```text
dev/SPEC_LV_FRONTEND_VOICE_WIRE_2026-08-01.md
static/index.html   (full file — focus on lines 680-900 for voiceRuntime, and the STT result handler)
src/web.py          (grep for /api/voice/act — the endpoint you're wiring to)
src/web.py          (grep for /api/voice/stt — how STT currently works)
```

## Objective

Modify `static/index.html` so that after the mic captures audio and STT returns a transcript,
the transcript is automatically sent to `/api/voice/act` which executes the appropriate action
(save observation, answer question, or prepare generation). The user no longer needs to press
Send/Save after speaking.

## Hard Rules

1. **Do not remove existing text-input flows.** The Ask form, Observe form, and all manual
   buttons must continue to work exactly as before. Voice-act is an additional path, not a
   replacement.
2. **Always show the transcript.** Before sending to /api/voice/act, display what was heard
   so the user can verify. Use a small toast/overlay near the voice companion widget.
3. **Fallback on error.** If /api/voice/act fails (network error, timeout, 500), put the
   transcript into the currently active text field (old behavior) and show a toast explaining.
4. **Do not modify any Python files.** This is a pure frontend change.
5. **Do not commit.** Leave changes for the operator.
6. **Bump the UI contract** when done: `python3 scripts/check_ui_contract.py --bump` and
   update EXPECTED_VERSION in `tests/test_ui_contract.py`.

## Step 1: Find the current STT result handler

Search `static/index.html` for where the STT response transcript is currently used. It will
look something like:
- A fetch to `/api/voice/stt`
- The response `.transcript` or `.text` being placed into a form field
- Possibly updating `state.chat` or a textarea value

Identify all places where STT output is consumed.

## Step 2: Add the voice-act flow

After STT returns a transcript, BEFORE placing it in a text field, add:

```javascript
async function handleVoiceActResult(transcript) {
    // 1. Show transcript immediately
    showVoiceTranscript(transcript);
    updateVoiceCompanion("processing", "Thinking...");

    try {
        const response = await fetch("/api/voice/act", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ transcript })
        });

        if (!response.ok) throw new Error(`Voice act failed: ${response.status}`);
        const result = await response.json();

        if (result.intent === "observation") {
            if (result.needs_clarification) {
                voiceRuntime.speak(result.spoken_confirmation || "Which student?");
                updateVoiceCompanion("clarify", "Which student?");
            } else {
                voiceRuntime.speak(result.spoken_confirmation || "Saved.", result.tone_prefix || "");
                updateVoiceCompanion("success", "Saved");
                // Refresh lens if on observe tab
                if (state.view === "observe" || state.view === "students") {
                    try { await loadLens("obs-lens", false); } catch(e) {}
                }
            }
        } else if (result.intent === "generate") {
            voiceRuntime.speak(result.spoken_confirmation || "Ready to create materials.");
            updateVoiceCompanion("ready", "Ready");
        } else {
            // question (default)
            const spoken = result.spoken_response || (result.result && result.result.answer) || "I don't have an answer.";
            voiceRuntime.speak(String(spoken).slice(0, 500), result.tone_prefix || "");
            updateVoiceCompanion("idle", "Ready");
            // Optionally append to chat
            if (result.result && result.result.answer) {
                appendChatMessage("assistant", result.result.answer);
            }
        }
    } catch (error) {
        // Fallback: put transcript in active field (old behavior)
        voiceActFallback(transcript);
        showToast("Voice action failed — your words are in the text box.");
        updateVoiceCompanion("error", "Error");
    }

    setTimeout(() => updateVoiceCompanion("idle", "Ready"), 4000);
}
```

## Step 3: Add helper functions

```javascript
function showVoiceTranscript(text) {
    const el = $("voice-transcript");
    if (!el) return;
    el.textContent = `"${text}"`;
    el.classList.add("visible");
    setTimeout(() => el.classList.remove("visible"), 5000);
}

function voiceActFallback(transcript) {
    // Put transcript in whatever text field is appropriate for the current view
    if (state.view === "observe") {
        const field = $("obs-text");
        if (field) { field.value = transcript; return; }
    }
    if (state.view === "ask") {
        const field = $("ask-input") || $("chat-input");
        if (field) { field.value = transcript; return; }
    }
    // Generic fallback: show as toast
    showToast(transcript);
}

function appendChatMessage(role, text) {
    // Append to the chat panel if it exists
    // Look for the existing chat message rendering pattern in the file
    // and follow it
}
```

## Step 4: Add the transcript display element

Near the voice companion widget (the mic circle on the right side), add:

```html
<div id="voice-transcript" class="voice-transcript"></div>
```

CSS:
```css
.voice-transcript {
    position: fixed;
    bottom: 120px;
    right: 20px;
    max-width: 300px;
    padding: 8px 12px;
    background: rgba(0,0,0,0.85);
    color: #fff;
    border-radius: 8px;
    font-size: 13px;
    opacity: 0;
    transition: opacity 0.3s;
    pointer-events: none;
    z-index: 1000;
}
.voice-transcript.visible {
    opacity: 1;
}
```

## Step 5: Update voice companion status display

The companion widget already shows a label ("Ready"). Update `updateVoiceCompanion` to
handle the new states:

```javascript
function updateVoiceCompanion(status, label) {
    const widget = $("voice-companion") || $("vc-status");
    if (!widget) return;
    // Update label text
    const labelEl = widget.querySelector(".vc-label") || widget.querySelector("span");
    if (labelEl) labelEl.textContent = label;
    // Update visual state (color/animation)
    widget.className = widget.className.replace(/vc-state-\w+/g, "") + ` vc-state-${status}`;
}
```

Add CSS for the states:
```css
.vc-state-processing { animation: pulse 1s infinite; }
.vc-state-success .vc-label { color: #48bb78; }
.vc-state-error .vc-label { color: #f56565; }
.vc-state-clarify .vc-label { color: #ed8936; }
```

## Step 6: Wire the STT result

Find the point where STT returns the transcript (after the fetch to `/api/voice/stt`
succeeds and the transcript is extracted from the response). Replace or augment:

```javascript
// OLD:
// someTextField.value = transcript;

// NEW:
handleVoiceActResult(transcript);
```

Keep the old code as the fallback path inside `voiceActFallback()`.

## Step 7: Bump UI contract

```bash
python3 scripts/check_ui_contract.py --bump
```

Update `contracts/UI_CONTRACT.yaml` bump log:
```
# v91 (2026-08-01): Frontend voice wire — mic button routes through
#     /api/voice/act for single-shot voice commands (observation save,
#     question answering, material generation trigger).
```

Update `tests/test_ui_contract.py`: `EXPECTED_VERSION = 91`

## Step 8: Verify

```bash
python3 -m src.lingua_viva.cli preflight
python3 -m pytest tests/test_ui_contract.py -q
```

Manually verify:
- Open `http://localhost:8787`
- Check the voice companion still appears
- Check that text input paths (typing in Ask, typing in Observe) still work normally
- If STT is available, test a voice interaction

## Definition of Done

- [ ] STT → /api/voice/act flow wired
- [ ] Transcript displayed to user after recognition
- [ ] Observation intent auto-saves and confirms via TTS
- [ ] Question intent answers and speaks
- [ ] Fallback to text field on error
- [ ] Companion widget shows status (processing/success/error)
- [ ] All existing text-input paths unchanged
- [ ] UI contract bumped
- [ ] Preflight passes
