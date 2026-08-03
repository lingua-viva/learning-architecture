# Lingua Viva QA: Claudia Teacher Readiness — Fix Brief

**Date:** 2026-08-03
**Source:** `qa/2026-08-03_teacher-readiness-claudia.md` (desktop-v0.2.30)
**Author:** kiro.design (analysis only — hand to build window)
**Repo:** `~/learning-architecture` (remote: lingua-viva/learning-architecture)

---

## P0-1: Voice STT Unavailable

### Problem
`GET /api/voice/probe` → `{"stt": {"available": false}}`. `faster-whisper` and/or `av` (PyAV) not importable in the desktop build's Python environment.

### Root Cause
`src/lingua_viva/voice_stt.py:9-23` — `stt_dependencies_available()` tries `import av` and `import faster_whisper`. One or both fail in the packaged app.

The bootstrap (`desktop/electron/bootstrap.ts:261`) installs `faster-whisper==1.1.1` via pip. However:
- `av` (PyAV) is a **transitive** dependency of `faster-whisper` — not explicitly pinned
- `ctranslate2` is another transitive dep (C++ compiled wheel) — platform-specific
- On macOS, `ctranslate2` may fail to install if no compatible wheel exists for the Python version/arch, or if pip resolves a source dist that requires cmake/C++ toolchain
- The pip install uses `--quiet` flag, so failures in transitive deps may not be surfaced

The BUG-2 fix from 2026-08-02 removed the incorrect `shutil.which("ffmpeg")` gate, but the underlying package availability was never verified post-install.

### Fix

**Option A (recommended): Explicitly pin all voice deps + verify post-install**

In `desktop/electron/bootstrap.ts`, add the critical transitive deps explicitly:
```typescript
const deps = [
    // ... existing deps ...
    "faster-whisper==1.1.1",
    "av>=11.0",              // ADD: PyAV (ffmpeg bindings)
    "ctranslate2>=4.0,<5",   // ADD: inference engine for faster-whisper
    // ... rest ...
];
```

Then add a verification step after pip install succeeds:
```typescript
// After all pip attempts complete:
const voiceCheck = spawnSync(pythonCmd, [
    "-c", "import av; import faster_whisper; print('voice_ok')"
], { timeout: 10000 });
if (!voiceCheck.stdout?.toString().includes("voice_ok")) {
    emitProgress(window, "voice_warn", "Voice transcription dependencies could not be installed. Voice input will be unavailable.");
}
```

**Option B (belt + suspenders): Add a voice readiness step to the wizard**

After the Ollama step, add a "Voice" step that:
1. Checks `stt_dependencies_available()` via a Python subprocess
2. If missing, shows "Voice requires additional components" with an Install button
3. Install button runs `pip install av ctranslate2 faster-whisper --force-reinstall`
4. Re-checks after install

### Files to Modify
- `desktop/electron/bootstrap.ts` — add `av`, `ctranslate2` to deps list + post-install verify
- `desktop/electron/main.ts` — optionally add voice readiness step to wizard
- `desktop/electron/setup-wizard.html` — optionally add voice step UI

### Verification
After fix, on a clean macOS install:
```bash
# From within the app's Python:
python3 -c "import av; import faster_whisper; print('ok')"
# Then:
curl -s http://127.0.0.1:8787/api/voice/probe | python3 -c "import sys,json; print(json.load(sys.stdin)['stt']['available'])"
# Must print: True
```

---

## P1-1 / P1-2: No Local Model + No Onboarding Guidance

### Problem
`POST /api/query` → `model_used: "none"`, placeholder text returned. No local Ollama model running. External models correctly blocked (student data detected). Teacher has no way to get reasoning capabilities without knowing what Ollama is.

### Root Cause
`src/lingua_viva/reasoning.py:57-63` — model resolution chain:
1. Explicit model param → none
2. `config.resolve_provider_model()` → none (no providers.json)
3. Ontology default → none
4. `LV_REASON_MODEL` env → not set
5. `self._resolve_best_model()` → calls `config.detect_model()` → queries Ollama → no models found → returns `"ollama/kimi-k2.7-code:cloud"` (cloud fallback) → blocked by exit gate (student data)

The wizard (`desktop/electron/main.ts:130-141`) DOES have Ollama detection and model pull:
- If Ollama detected → `ensureOllamaModel("qwen2.5:3b")` fires but with `.catch(() => {})` — silent failure
- If Ollama not detected → user can "Skip for now" — no model ever
- The wizard runs every app launch (no "already completed" gate) but model pull is non-blocking and unverified

### Fix

**Two-part fix:**

**Part 1: Make the model pull blocking and verified (not fire-and-forget)**

In `desktop/electron/main.ts:136-139`, replace:
```typescript
// BEFORE (silent fire-and-forget):
ensureOllamaModel(process.env.LV_OLLAMA_MODEL || undefined).catch(() => {});

// AFTER (blocking with progress):
emitProgress(window, "model", "Downloading local AI model (first time only)...");
const modelResult = await ensureOllamaModel(process.env.LV_OLLAMA_MODEL || undefined);
if (modelResult.ok) {
    emitProgress(window, "model_ok", "Local AI model ready");
} else {
    emitProgress(window, "model_warn", "Could not download AI model. Ask features will be unavailable until Ollama has a model.");
}
```

**Part 2: If Ollama is missing and user skips, show a clear in-app message**

In `src/web.py` (the `/api/query` response when model_used == "none"), replace the placeholder with an actionable message:
```python
# When no model available:
content = (
    "I need a local AI model to answer questions about your students. "
    "To set this up:\n\n"
    "1. Install Ollama from https://ollama.ai\n"
    "2. Open Terminal and run: ollama pull qwen2.5:3b\n"
    "3. Restart Lingua Viva\n\n"
    "This keeps all student data on your computer — nothing is sent externally."
)
```

**Part 3 (optional, stronger): Bundle Ollama + model in the desktop build**

This is the nuclear option — include Ollama binary + qwen2.5:3b (1.9GB) in the app bundle. Guarantees first-run works with zero teacher intervention. Tradeoff: 2GB+ app size increase. Worth discussing but not blocking for this fix round.

### Files to Modify
- `desktop/electron/main.ts:136-139` — make model pull blocking + verified
- `desktop/electron/setup-wizard.html` — add "model" step UI (downloading/done/failed states)
- `src/web.py` — improve the "no model" placeholder to include setup instructions
- `src/lingua_viva/reasoning.py` — optionally add a `model_available()` check that the query endpoint can call before attempting

### Verification
After fix, fresh install without Ollama:
- Wizard should clearly state "AI features require Ollama" with install button
- If skipped, `/api/query` should return setup instructions, not a cryptic placeholder
- If Ollama IS installed, wizard should BLOCK until model pull completes (with progress bar)

---

## P2-1: Unclear Save Confirmation (Double-Save)

### Problem
Claudia saved Nora's observation twice. The confirmation appears inline in the form area with a brief green flash (0.6s animation, fades to transparent). `clearObserveForm()` fires simultaneously, so the teacher may perceive "form cleared = nothing happened" rather than "form cleared = save succeeded."

### Root Cause
`static/index.html:1889-1901`:
- Confirmation uses `flash-success` class: 0.6s `obs-saved-flash` animation (green → transparent)
- `scrollIntoView` + innerHTML update in `#obs-result`
- `clearObserveForm()` runs immediately after (line 1901) — teacher sees empty form, may think it reset without saving
- No global toast/banner, no persistent success state, no timestamp

CSS at line 243-249:
```css
.panel.flash-success { animation: obs-saved-flash 0.6s ease-out; }
@keyframes obs-saved-flash { 0% { background-color: #c6f6d5; } 100% { background-color: transparent; } }
```

### Fix

Add a persistent toast/banner at the top of the viewport:
```javascript
// After successful save, BEFORE clearObserveForm():
function showSaveToast(studentName, timestamp) {
    const toast = document.createElement("div");
    toast.className = "save-toast";
    toast.innerHTML = `✓ Observation saved for <strong>${escapeHtml(studentName)}</strong> at ${new Date(timestamp).toLocaleTimeString()}`;
    document.body.appendChild(toast);
    // Auto-dismiss after 5 seconds (not 0.6s!)
    setTimeout(() => { toast.classList.add("fade-out"); setTimeout(() => toast.remove(), 300); }, 5000);
}
```

Add CSS:
```css
.save-toast {
    position: fixed;
    top: 16px;
    left: 50%;
    transform: translateX(-50%);
    background: #276749;
    color: white;
    padding: 12px 24px;
    border-radius: 8px;
    font-weight: 500;
    z-index: 9999;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    animation: slide-in 0.3s ease-out;
}
.save-toast.fade-out { opacity: 0; transition: opacity 0.3s; }
@keyframes slide-in { from { transform: translateX(-50%) translateY(-20px); opacity: 0; } }
```

Also: keep the existing inline confirmation (it shows what was saved) but DON'T rely on it as the primary signal. The toast catches the eye; the inline detail is for verification.

### Files to Modify
- `static/index.html:1889-1901` — add `showSaveToast()` call before `clearObserveForm()`
- `static/index.html` (CSS section, ~line 243) — add `.save-toast` styles

### Verification
- Save an observation → prominent green toast appears at top of screen with student name + timestamp
- Toast persists for 5 seconds (not 0.6s)
- Form clears, but the toast makes it unmistakable that a save occurred

---

## FR-1: Teacher Avatar Image

**Priority:** Low
**Location:** `static/index.html:703-712` — voice companion HTML references `/assets/mc-avatar.png` (2.3MB generic avatar)
**Recommendation:** Replace with a teacher-appropriate illustration. Consider multiple options (male/female/neutral) in Settings. This is a branding/UX decision, not a code fix.

---

## FR-2: CEFR Young Learner Progressions

**Priority:** Low (but high teacher value)
**Location:** After observation save, the system could suggest next CEFR descriptors
**Recommendation:** Add a "What's next?" section to the save confirmation that maps the observed level to the next can-do descriptor in the CEFR young learner grid. Data source: `curriculum/cefr_young_learners.yaml` (if it exists) or create one. This is a feature build, not a fix.

---

## Build Sequence

| # | Item | Effort | Blocks |
|---|---|---|---|
| 1 | P0-1: Pin av + ctranslate2 in deps + verify | S | Voice features |
| 2 | P1-1: Make model pull blocking with progress | S | Ask/query system |
| 3 | P1-2: Improve "no model" response text | XS | Teacher understanding |
| 4 | P2-1: Add persistent save toast | S | Confidence in saves |
| 5 | FR-1: Avatar swap | XS | Cosmetic |
| 6 | FR-2: CEFR progression suggestions | M | Feature build |

After fixing 1-4, re-run Rounds 1-3 of the QA packet (`qa/packets/teacher-readiness-2026-08-03/QA_TESTING_PLAN.md`). Specifically verify:
- Check 6/9: Voice transcription → must succeed
- Check 12: Ask query → must return a real answer (with Ollama + model running)
- Check 5: Single-save confirmation → toast visible, no double-save temptation

---

*End of fix brief. Hand to build window with ~/learning-architecture checked out.*
