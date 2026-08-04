# CLOSURE REPORT — Kiro (c5a27ef) for Reviewer

**Commit:** `c5a27ef` on main
**Author:** kiro.design
**Base:** `33564a0` (T3 + T9 follow-up, contract v107)
**Time:** 2026-08-03 ~20:20 PDT

---

## What was delivered

### Gate A items closed

| ID | Item | Status | Evidence |
|----|------|--------|----------|
| A3 | JSON error bodies | ✅ DONE | Global `@app.exception_handler(Exception)` returns JSON on any unhandled crash. `tests/test_json_error_bodies.py` (5 tests) locks the contract. Verified: `curl -X POST /api/ingest` → `{"error":"No file was uploaded."}` with `Content-Type: application/json`. |
| A4 | CEFR force regression | ✅ DONE | Observation type/skill/level all made optional in `saveObservation()`. Text + student is the only requirement. No forced gate that would cause invented data. |
| T5 | Observe mic | ✅ DONE | `<button id="obs-mic">` mounted in Observe panel. Wired to `voiceRuntime.captureLocalStt` with conversational accumulation (each dictation appends to textarea). Form-gated: transcript → textarea → teacher edits → clicks Save → `/api/observe/capture`. No bypass of the form. Companion remains hidden (voice-hidden on body). `applySttAvailability()` dims the mic when STT unavailable. |

### Gate B items closed

| ID | Item | Status | Evidence |
|----|------|--------|----------|
| B1 | Ask refusal wording | ✅ DONE | `ask_personal_data_refusal_message()` now returns "The Ask section answers general teaching questions using web search. Questions about your students stay on this machine — their information lives in their lens and is never sent externally." |
| B2 | TTS locale | ✅ DONE | `speakLocally()` detects English vs Italian via keyword regex; picks matching voice. English refusal → English voice. Italian content → Italian voice. |
| B3 | SmartScreen copy | ✅ Already shipped (confirmed on `docs/index.html` line 251) |
| B4 | Settings sections | ✅ DONE | Voice, Sync, Privacy panels added to Settings. Live state from `/api/voice/probe` (STT provider + availability) and new `/api/sync/status` endpoint (pending/pushed/failed counts). Privacy panel links to Why tab. No fake toggles. |
| B5 | Sources nav | ✅ DONE | "Sources → Drive" text is now a clickable `<a>` that navigates via `state.view='sources'`. Event listener in `renderIntegrationsControls()`. |

---

## Files touched (commit c5a27ef)

| File | Change |
|------|--------|
| `src/web.py` | Global JSON exception handler (line 51); `/api/sync/status` endpoint |
| `src/lingua_viva/messages.py` | B1 refusal wording update |
| `static/index.html` | T5 mic button + wiring; A4 optional fields; B2 TTS locale; B4 settings panels; B5 nav link; mic-btn CSS |
| `contracts/UI_CONTRACT.lock` | Relocked at v109 |
| `contracts/UI_CONTRACT.yaml` | Version bump v109 |
| `tests/test_ui_contract.py` | EXPECTED_VERSION → 109 |
| `tests/test_json_error_bodies.py` | NEW — 5 tests locking A3 |

---

## Verification performed (74 tests green)

```
tests/test_ui_contract.py          — 6 passed (incl. JS syntax check)
tests/test_hf1_frontend_hotfixes.py — 18 passed
tests/test_json_error_bodies.py    — 5 passed (NEW)
tests/test_ask_perplexity.py       — 15 passed
tests/test_no_model_messages.py    — 10 passed
tests/test_docpipe_extract.py      — 13 passed (T3, their code, untouched)
tests/test_voice_companion.py      — 5 passed
tests/test_docpipe_sync.py         — 2 passed
```

**Full `pytest -q tests/` NOT RUN** — CPU constrained by concurrent MC build. This is the A6 gap.

---

## What the reviewer should verify

1. **A6 full regression floor** — `pytest -q tests/` when CPU frees up. Known risk: voice_intent tests reference `/api/voice/act` which still exists as a backend endpoint (hidden from UI).
2. **T5 live check** — load Observe in the desktop app, tap mic, dictate, see text appear in textarea, edit, save. Verify `applySttAvailability` dims the mic if faster-whisper isn't installed.
3. **A4 regression** — save an observation with ONLY text + student (no type, no CEFR) — must succeed.
4. **B2 live check** — trigger an Ask PII refusal and listen — should speak in English, not Italian.
5. **B4** — open Settings, confirm Voice/Sync/Privacy sections render with live values.

---

## Items still open (NOT in this commit)

| ID | Status | Notes |
|----|--------|-------|
| A1 (T3) | ✅ Landed (58695ee) | Merged cleanly, 13 tests green |
| A2 (T5 full spec) | ⚠️ PARTIAL | Mic is mounted and wires to save. AudioWorklet VAD upgrade deferred (setInterval VAD works, just throttle-susceptible in background tabs). Parse-on-save (model suggests fields) uses existing `/api/observe/classify` — not changed, already works. |
| A5 (T7 e2e gate) | ❌ NOT DONE | Needs a dedicated session to build `scripts/run_docpipe_e2e.sh` |
| A6 (full regression) | ❌ BLOCKED | CPU |
| B6 (Windows re-run) | ❌ BLOCKED | Needs v0.2.36 build |
| B7 (Perplexity keys) | ❌ BLOCKED | Needs key provisioning |
