# SPEC: Lingua Viva Monday MVP Sprint

**Created**: 2026-08-01  
**Deadline**: Monday 2026-08-04 EOD  
**Status**: ACTIVE  
**Readiness target**: Education product 35→50% → 55-65% (move the needle on the readiness matrix)

---

## Objective

By Monday EOD, a teacher (Chip testing as proxy) can:

1. Connect Google Drive from the LV app
2. Import student documents (PDF/DOCX) from Drive
3. See student lenses created/updated from those documents
4. Ask for differentiated lesson plans per student group
5. Have those plans shared back to a Drive folder
6. Use voice to take observation notes on students
7. See those notes update the student lens
8. Have lenses auto-sync to a shared Drive folder

**Definition of done**: Chip can complete all 8 steps on her Mac without Mical intervening. The system doesn't need to be perfect — it needs to not break, not lose data, and produce useful output.

---

## Three Build Rotations

We have ~48 hours. Three build→test→fix rotations:

| Rotation | When | Build | Test (Chip) | Fix |
|---|---|---|---|---|
| R1 | Sat morning→afternoon | OAuth + Drive pipeline + voice→lens wire | Chip tests Drive connect + import + voice note | Fix what breaks |
| R2 | Sat evening→Sun morning | Lesson plan generation + Drive export + auto-sync | Chip tests full flow: import→lens→plan→export | Fix what breaks |
| R3 | Sun afternoon→Mon morning | Edge cases, UX polish, fallback messages | Chip runs the "teacher day" scenario end-to-end | Final fixes |

---

## Project 1: Google Drive OAuth End-to-End

### Current State
- OAuth module exists: `src/lingua_viva/google_drive_oauth.py` (323 lines)
- Drive integration exists: `src/lingua_viva/google_drive_integration.py` (951 lines)
- Web routes exist: `/api/google-drive/status`, `/auth/google/start`, folder connect/disconnect, list, import, upload
- **Blocker**: Need to verify OAuth credentials are configured on Chip's machine and the flow actually completes

### What Must Work
1. Teacher clicks "Connect Google Drive" in Settings/Sources
2. Browser opens Google OAuth consent screen
3. After approval, app shows "Connected" with account email
4. Teacher can browse/connect a Drive folder
5. Files from that folder appear in the app's import list

### Implementation Plan

```
Step 1: Verify OAuth config on Chip's machine
  - Check: does ~/.lingua-viva/config.yaml have google_client_id + google_client_secret?
  - If not: Mical must create a GCP OAuth client (one-time, 5 min in console.cloud.google.com)
  - Write the exact credentials Chip needs into her config

Step 2: Test the OAuth redirect loop
  - GET /auth/google/start → must redirect to accounts.google.com
  - Google redirects back to localhost:8787/auth/google/callback
  - Callback exchanges code for tokens, writes to ~/.lingua-viva/google_tokens.json
  - GET /api/google-drive/status → must return {configured: true, signed_in: true}

Step 3: Test folder operations
  - POST /api/google-drive/connect-folder with a Drive folder URL
  - GET /api/google-drive/folders → must list connected folders
  - POST /api/google-drive/list {folder_id, limit: 20} → must return files
```

### Chip's Test Checklist (R1)
- [ ] Click "Connect Google Drive" — does browser open?
- [ ] Complete OAuth — does app show "Connected"?
- [ ] Connect a folder containing 2-3 test PDFs
- [ ] See those files listed in the app

### Known Risks
- GCP OAuth consent screen may need "Internal" vs "External" app type
- Redirect URI must exactly match `http://localhost:8787/auth/google/callback`
- If Chip's machine has no Google OAuth credentials, this is blocked until Mical provisions them

---

## Project 2: Document→Lens Pipeline + Differentiated Lesson Plans

### Current State
- Extraction engine exists: `src/lingua_viva/extraction_engine.py` (chunk files, LLM extraction, grounding)
- Student lens writer exists: `src/lingua_viva/student_lens_writer.py` (215 lines, writes to SQLite)
- Web routes: `/api/extraction/run`, `/api/extraction/review`, `/api/students/{id}/lens`
- Observe routes: `/api/observe/capture` (voice→text→observation→lens)
- **Gap**: No automated "import from Drive → extract → write lens" pipeline. These are separate manual steps.

### What Must Work
1. Teacher imports a PDF from Drive → extraction runs automatically
2. Extraction shows results with "Review" button (teacher confirms/rejects fields)
3. Confirmed fields write to student lens
4. Teacher can request "Create a differentiated lesson plan for Group A vs Group B"
5. Lesson plan cites student lens data as evidence
6. Voice observation → saved to correct student → lens updated

### Implementation Plan

```
Step 1: Wire Drive-import → automatic extraction trigger
  - After successful file import (POST /api/google-drive/import returns files),
    immediately call the extraction pipeline on each imported file
  - Return extraction results in the same response (or flag as "processing")
  - Location: src/web.py, after the import loop in google_drive_import()

Step 2: Verify extraction → lens writer pipeline
  - Run: import a test PDF → check extraction results → confirm fields → verify lens updated
  - Fix any broken links between ExtractionResult and write_student_lens()

Step 3: Lesson plan generation endpoint
  - Route: POST /api/lesson-plan/generate
  - Input: {student_ids: [...], topic: "...", grade: "G3", duration: "45min"}
  - Logic: load lens for each student → group by support tier → call reasoning engine
    with prompt: "Create differentiated lesson plan for [topic] with these student groups: ..."
  - Output: {plan_text, student_groups: [{group_name, student_ids, adaptations}], sources_cited}
  - This endpoint likely needs to be NEW (check if something similar exists already)

Step 4: Voice → observation → lens update (verify existing wire)
  - POST /api/voice/stt (audio) → transcript
  - POST /api/observe/capture {student_id, transcript, ...} → observation saved + lens updated
  - Verify the observe_capture endpoint actually calls student lens writer
```

### Chip's Test Checklist (R1 + R2)
- [ ] Import a PDF about a student → see extraction results
- [ ] Confirm extracted fields → check student lens shows new data
- [ ] Record a voice observation → verify it attaches to the correct student
- [ ] Ask for a differentiated lesson plan → get a real plan back
- [ ] Plan references actual student data from the lens

### Known Risks
- Extraction quality depends on Ollama model speed (we just raised timeout to 60s — good)
- If no model is running, extraction will fail silently
- Lesson plan generation is new code — needs to be built

---

## Project 3: Auto-Sync Lenses to Google Drive

### Current State
- Drive upload endpoint exists: `POST /api/google-drive/upload` (takes local paths + folder_id)
- Student lens can be exported: `/api/students/{id}/lens` returns JSON
- **Gap**: No trigger that says "when lens changes, push updated file to Drive"

### What Must Work
1. Teacher designates a "sync folder" in Drive (one-time setup)
2. When any student lens is updated (observation, extraction, manual edit):
   - System exports the lens as a JSON or Markdown file
   - Pushes it to the sync folder, overwriting the previous version
3. Teacher (or another teacher with folder access) can see updated lenses in Drive

### Implementation Plan

```
Step 1: Add "sync folder" setting
  - Store in ~/.lingua-viva/config.yaml: drive_sync_folder_id: "<folder-id>"
  - Add a UI button in Settings/Sources: "Set as lens sync folder" next to connected folders
  - Route: POST /api/settings/drive-sync-folder {folder_id}

Step 2: Build lens export formatter
  - Function: format_lens_for_drive(student_id) → returns markdown string
  - Contents: student name, grade, support profile summary, recent observations,
    CEFR trajectory, last updated timestamp
  - File name: "{student_display_name}_lens_{date}.md"

Step 3: Build post-save sync hook
  - After any lens mutation (observation save, extraction write, manual edit):
    - Check if drive_sync_folder_id is configured
    - If yes: format lens → upload to Drive (overwrite if file exists)
  - Implementation: add a _sync_lens_to_drive(student_id) function
  - Call it from: observe_capture(), write_student_lens(), and any manual edit endpoint
  - Make it fire-and-forget (asyncio.create_task) so it doesn't block the save

Step 4: Handle offline/failure gracefully
  - If Drive upload fails (no network, token expired, folder deleted):
    - Log the failure
    - Don't block or error the original save
    - Show a yellow badge in the UI: "Drive sync pending (last attempt failed)"
  - On next successful Drive operation, retry pending syncs
```

### Chip's Test Checklist (R2 + R3)
- [ ] Set a Drive folder as "sync folder" in Settings
- [ ] Save an observation → check Drive folder for updated lens file
- [ ] Import a document + confirm extraction → check Drive folder updated
- [ ] Disconnect wifi → save observation → no error shown → reconnect → lens appears in Drive

### Known Risks
- Drive API rate limits (unlikely with 1 teacher, but design for it)
- Token expiry mid-session (refresh tokens should handle, but verify)
- File naming collisions if two students have the same display name

---

## Annotation/Testing Handoff for Chip

### What Chip Needs Before R1 Testing

1. **Working app on her machine** — `git pull` + `uv run` + confirm localhost:8787 loads
2. **Google OAuth credentials in her config** — Mical must provide these
3. **A test Drive folder** with 2-3 student PDFs (made-up data, not real students)
4. **A test checklist** (the checkboxes above, printed or in a shared doc)

### What Chip Reports Back

For each test step:
- **Pass/Fail**
- **Screenshot** (especially on failure)
- **What she expected vs what happened**
- **Any error messages (console, app UI, or toast)**

### File for Chip's results:
```
qa/2026-08-01_mvp-sprint-r1.md
qa/2026-08-02_mvp-sprint-r2.md
qa/2026-08-03_mvp-sprint-r3.md
```

---

## Build Order (Today, Saturday)

### Morning (now → noon): Blocker Removal

1. **Verify/fix OAuth flow** — if creds don't exist, create them now
2. **Fix any Drive import→extraction gap** — wire auto-extraction on import
3. **Verify voice→observe→lens pipeline** — run it once end-to-end locally

### Afternoon (noon → evening): New Code

4. **Build lesson plan generation endpoint** — new route, uses reasoning engine
5. **Build Drive auto-sync hook** — the fire-and-forget post-save trigger
6. **Add "sync folder" setting** — UI button + config persistence

### Evening: Push + Handoff to Chip

7. Push all changes
8. Write Chip's R1 test instructions (concrete steps, not abstract)
9. Chip tests Saturday night or Sunday morning → reports back

---

## Success Metrics

| Metric | Current | Monday Target |
|---|---|---|
| Drive OAuth works on Chip's machine | ❌ unverified | ✅ |
| Import PDF → lens created | ❌ untested end-to-end | ✅ |
| Voice observation → lens updated | ⚠️ wired but unverified | ✅ |
| Lesson plan uses student data | ❌ endpoint doesn't exist | ✅ |
| Lens auto-syncs to Drive | ❌ not built | ✅ |
| Chip completes full flow without help | ❌ | ✅ |
| Internal readiness: education | 35-50% | 55-65% |

---

## Definition of Shipped (for this sprint)

- [ ] Chip completed all 8 MVP steps on her Mac, unassisted
- [ ] No data loss during the flow
- [ ] Errors are communicated (not silent failures)
- [ ] At least one full "teacher day" scenario works end-to-end
- [ ] QA report exists in `qa/` with screenshots
- [ ] All tests still pass (1694+ current baseline)

---

## What This Does NOT Include (explicit non-goals)

- Streaming voice (sequential is fine for MVP)
- Multi-teacher / multi-school isolation
- Beautiful UI (functional is fine)
- Release pipeline fixes (that spec exists separately)
- Cross-domain (legal, healthcare, construction) features
- Public deployment / production hosting
