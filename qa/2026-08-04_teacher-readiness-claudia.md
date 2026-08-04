# QA Report: Teacher Readiness — Claudia (2026-08-04)

## Versions Tested

| Item | Value |
|------|-------|
| App version | desktop-v0.2.35 |
| Repo commit | `4ae8d67` |
| Repo state | clean (main) |
| Platform | macOS Darwin 25.3.0 |
| Local URL | http://127.0.0.1:8787 |
| Test data | Synthetic: Aron Park, Jerry Park (aliases over anonymized documents) |

## Summary

Testing covered student creation, manual observations, privacy refusal, sidebar navigation, Doctor/health, and settings review. Document import (the core feature of this build) was completely broken. Voice/mic button was missing from the UI despite the STT backend being available.

**Counts: 1 P0, 3 P1, 4 P2, 2 FR**

---

## P0 Issues

| ID | Description |
|----|-------------|
| P0-1 | **Document import completely broken.** Both .txt and .pdf files return "Internal Server Error" (bare string, not JSON). The `/api/ingest` endpoint rejects .txt with "Only PDF files are supported right now" and crashes on .pdf. The `/api/students/ingest` endpoint returns bare "Internal Server Error" for all file types. This was the core feature under test for this build — reading real documents and building student profiles. |

## P1 Issues

| ID | Description |
|----|-------------|
| P1-1 | **Mic button missing from UI.** Voice companion not visible in the app surface. The STT backend reports `available: true` via `/api/voice/probe`, but there is no mic button for the teacher to tap. Voice was the primary workflow tested in the previous audit and "one of the main things we worked on." |
| P1-2 | **Observation save forces CEFR skill + level.** The app requires three mandatory fields (observation type, CEFR skill, observed level) before allowing save. Teachers should be able to save an observation without assigning a CEFR level. Forcing it risks teachers picking arbitrary levels just to get past the gate — exactly the "invented data" problem this app is built to prevent. |
| P1-3 | **Settings page missing voice, sync, and privacy controls.** Only Google Drive section is visible in Settings. Teachers cannot configure voice, sync behavior, or privacy settings. |

## P2 Issues

| ID | Description |
|----|-------------|
| P2-1 | **Too many macOS permission dialogs during install.** Multiple allow/permission requests appear — should be consolidated or eliminated. Claudia took screenshots of each dialog. |
| P2-2 | **TTS voice reads English with Italian accent.** Privacy refusal message is in English but read aloud with an Italian-accented voice (browser Web Speech API using Italian locale for English content). |
| P2-3 | **Privacy refusal wording unclear.** Message says "Ask answers general teaching questions..." — should say "The Ask section answers general..." for clarity. Claudia's suggestion. |
| P2-4 | **Settings references "Sources -> Drive" but Sources tab not easy to find.** The Settings page says "Set up and sign-in live in Sources -> Drive" — Claudia initially could not find the Sources tab. Navigation between Settings and Sources is not intuitive. |

## Feature Requests

| ID | Description |
|----|-------------|
| FR-1 | **Recommendation based on observation.** After saving an observation, suggest next steps or recommendations based on what was observed — connects to the CEFR young learner progressions / can-do lists request from the previous audit. |
| FR-2 | **Teacher image above mic.** (Carried forward from 2026-08-03 audit.) Replace generic avatar with a teacher-appropriate image. |

---

## Checks Completed

### Setup

| # | Check | Result | Notes |
|---|-------|--------|-------|
| - | App launch + health | PASS | All 29 health checks pass |
| - | Create Aron Park, G3 | PASS | Shows "CEFR trajectory: insufficient data" — correct |
| - | Create Jerry Park, G3 | PASS | |

### Document Import (Round 1 — blocked by P0-1)

| # | Check | Result | Notes |
|---|-------|--------|-------|
| - | Import Aron progress report (.txt) | FAIL (P0-1) | "Unexpected token 'I', 'Internal S'... is not valid JSON" |
| - | Import G3 unit PDF | FAIL (P0-1) | Same error |
| - | Profile building from document | NOT TESTED | Blocked by import failure |
| - | Field-by-field verification | NOT TESTED | Blocked by import failure |

### Manual Observations

| # | Check | Result | Notes |
|---|-------|--------|-------|
| - | Save observation for Aron (with forced type + CEFR) | PASS | Saved locally. Required type, CEFR skill, and level (P1-2) |
| - | Save observation for Jerry (with forced type + CEFR) | PASS | Same mandatory fields issue |
| - | Aron lens shows only teacher-entered data | PASS | No invented data |

### Privacy (Round 3)

| # | Check | Result | Notes |
|---|-------|--------|-------|
| - | Ask "What level is Aron at in reading?" | PASS | App refuses: "Ask answers general teaching questions from the web. Information about your students lives in their lens — nothing personal is ever sent off this machine." |
| - | Refusal wording judgment | P2-3 | Claudia: should start with "The Ask section..." for clarity |
| - | TTS voice quality | P2-2 | English text read with Italian accent |

### App Health

| # | Check | Result | Notes |
|---|-------|--------|-------|
| - | All sidebar tabs | PASS | No crashes, no blank screens |
| - | Doctor / Health page | PASS | No PRIVATE_RISK false positive |
| - | Settings | P1-3 | Only Drive visible — no voice, sync, or privacy controls |
| - | Sources → Drive | NOTED | Found but says "not configured on this machine" |

### Voice

| # | Check | Result | Notes |
|---|-------|--------|-------|
| - | Mic button visible | FAIL (P1-1) | Not present in the UI |
| - | Voice STT backend | PASS (backend only) | `/api/voice/probe` returns `stt.available: true` |

### Rounds Not Tested

| Round | Reason |
|-------|--------|
| Round 1: Document → profile building | Blocked by P0-1 (import broken) |
| Round 2: Additional document types | Blocked by P0-1 |
| Round 4: Google Drive integration | Drive not configured in this build |
| Worksheet generation | Not reached |
| Cohort lesson planning | Not reached |

---

## Teacher Feedback (Claudia's words, verbatim)

1. **What worked?** "Inserting observations"
2. **What didn't work?** "The voice, the document import, the mic button missing"
3. **What was confusing?** "Where to find voice, sync, and privacy?"
4. **Do the observation fields match how you think about your students?** "It does!"
5. **Generated materials usable as-is?** Not tested — document import was broken
6. **What would make you quit on a busy teaching day?** "If the voice doesn't work and I have to type everything manually"
7. **Feature requests:** "Maybe a recommendation based on the observation shared?"

---

## Technical Appendix

### Document Import — Root Cause

**Endpoints tested:**

| Endpoint | Method | Result |
|----------|--------|--------|
| `/api/ingest` | POST (multipart, .txt file) | `{"error":"Only PDF files are supported right now."}` |
| `/api/ingest` | POST (multipart, .pdf file) | `Internal Server Error` (bare string) |
| `/api/students/ingest` | POST (multipart, .txt file) | `Internal Server Error` (bare string) |

**Key issue:** All ingest endpoints return bare "Internal Server Error" strings instead of JSON error bodies. The frontend tries to parse the response as JSON and fails with the "Unexpected token" error the teacher sees. The PDF path crashes server-side despite `/api/ingest` supposedly accepting PDFs.

**Files to investigate:**
- `src/web.py` — `/api/ingest` endpoint, `/api/students/ingest` endpoint
- `src/lingua_viva/` — document parsing/extraction pipeline
- Desktop build packaging — whether PDF parsing dependencies (e.g., `pdfplumber`, `PyPDF2`) are bundled

### Voice/Mic — Root Cause

**Backend is ready:**
- `/api/voice/probe` returns `{"stt":{"available":true,"provider":"faster-whisper","decoder":"pyav","local_only":true}}`
- STT, intent routing, and TTS endpoints all exist and respond

**Frontend missing:**
- Voice companion HTML exists in `static/index.html:703-712` (avatar, mic button, state visor)
- The component may be hidden via CSS or a feature flag in this build
- **Files to investigate:**
  - `static/index.html:703-712` — voice companion markup
  - `static/index.html:367-452` — voice companion CSS (`.voice-companion.collapsed` hides it)
  - Any build-time or runtime feature flag that controls voice companion visibility

### Forced CEFR Level — Root Cause

- `static/index.html:1860-1869` — `saveObservation()` validation gates
- The validation requires CEFR skill and level as mandatory fields before allowing POST
- In v0.2.30, check 11 confirmed the app could save without a level — this is a regression
- **Files to investigate:**
  - `static/index.html` — observation form validation logic
  - `src/web.py` — `/api/observe/capture` endpoint validation

### TTS Italian Accent on English Text

- `static/index.html:968-980` — browser fallback TTS uses `window.speechSynthesis` with Italian locale
- When the response text is English (e.g., privacy refusal), the Italian voice reads it with an accent
- **Fix:** Detect response language and set TTS locale accordingly, or use English voice for English text

### Environment

| Item | Value |
|------|-------|
| OS | macOS Darwin 25.3.0 |
| Session folder | `~/qa-sessions/lingua-viva-2026-08-04_1822/` |
| Health endpoint | All 29 checks PASS |
| Voice probe | STT: available=true, TTS: rime_configured=false, local_fallback=true |
| External calls | false |

### Event Log

```
[2026-08-03T01:38:18Z] SESSION START — Teacher Readiness v0.2.35 (Claudia)
[2026-08-04T01:22:00Z] NOTE (Claudia): Multiple macOS allow/permission requests during install
[2026-08-04T01:22:00Z] App version confirmed: desktop-v0.2.35
[2026-08-04T01:22:00Z] P1: No mic button visible in the UI
[2026-08-04T01:25:00Z] Aron Park created, G3, CEFR trajectory: insufficient data
[2026-08-04T01:25:00Z] Jerry Park created, G3
[2026-08-04T01:27:00Z] P0: Import of aron_progress_report .txt fails — Unexpected token error
[2026-08-04T01:27:00Z] Root cause: /api/ingest rejects .txt; /api/students/ingest returns bare Internal Server Error
[2026-08-04T01:28:00Z] P0: PDF import also fails — same Internal Server Error
[2026-08-04T01:30:00Z] Observation saved for Aron — required type, CEFR skill, and level (P1)
[2026-08-04T01:32:00Z] Observation saved for Jerry — same mandatory fields
[2026-08-04T01:34:00Z] Aron lens: shows observation + CEFR level, nothing invented — PASS
[2026-08-04T01:35:00Z] All sidebar tabs — no crashes — PASS
[2026-08-04T01:36:00Z] Doctor/Health — PASS, no PRIVATE_RISK
[2026-08-04T01:37:00Z] Settings: only Drive visible, no voice/sync/privacy controls (P1)
[2026-08-04T01:38:00Z] Sources → Drive: found but "not configured on this machine"
[2026-08-04T01:40:00Z] Privacy refusal test: PASS — app refuses with redirect to lens
[2026-08-04T01:40:00Z] TTS reads English with Italian accent (P2)
[2026-08-04T01:40:00Z] Claudia: wording should start "The Ask section..." (P2)
[2026-08-04T01:45:00Z] SESSION END
```
