# SPEC — Lingua Viva Drive Workspace

**Date:** 2026-07-27
**Status:** Phase 1 BUILDING (this session) / Phase 2 DRAFT — awaiting operator ruling on auto-sync governance
**Origin:** Operator direction + Claudia-Canu UX-lens trace (2026-07-27 evening, Slack #ai-lingua-viva context)
**Prereq:** Drive round-trip build 2026-07-27 (path-mismatch fix + `POST /api/google-drive/upload`, UI contract v34)

---

## 1. Problem

Google Drive import/share-back shipped inside **Settings**. The UX trace's core finding:
Drive is not a setting — it is one of the core daily work surfaces of Lingua Viva. The
current panel asks teachers to think in system concepts (folder ID, MIME type,
extraction-ready, runtime cache) instead of teacher intent ("I have files in Drive; I
want Lingua Viva to use them to prepare lessons / personalize work / update a student
record after I approve it").

## 2. North star

> Slack captures daily operational signals. Drive brings in durable classroom materials
> and shared school documents. Lingua Viva is the local place where both become useful,
> reviewable, and teacher-controlled.

The teacher's mental model: **Drive is the shared shelf. Lingua Viva makes a local
working copy.** Never "Drive and local are magically the same."

## 3. Phase 1 (built this session)

### 3.1 Navigation
- `Drive 📁` added to `utilityNav` directly after `Slack` — daily-use surface.
- Settings' Google Drive panel is replaced by a one-line pointer to the Drive view.

### 3.2 Connect Folder (URL paste, not folder IDs)
- Teacher pastes a normal Drive folder link: `https://drive.google.com/drive/folders/<id>?...`
- Backend parses the ID from any of: full folder URL, `?id=` share links, or a bare ID
  (fallback for power users).
- On connect, Lingua Viva **verifies access live** (metadata get on the folder) before
  saving — a bad link or missing permission fails immediately with plain language.
- Teacher names the folder and chooses **what it's for** (purpose-first):
  - Classroom materials (`curriculum_unit_source`)
  - Student evidence for review (`student_lens_source`)
  - Teacher artifacts (`teacher_artifact_source`)
  - General / unassigned
- Registry stored at `~/.lingua-viva/runtime/drive_folders.json` (0600, override
  `LV_GOOGLE_DRIVE_FOLDERS_PATH`). Fields: id, name, purpose, connected_at,
  last_checked, share_back (bool, default false).

### 3.3 Import experience (teacher language)
- Browse per connected folder (card → "Browse files"), or search across the configured root.
- Labels translate system concepts:
  - `application/vnd.google-apps.document` → "Google Doc"; pdf → "PDF"; docx → "Word document"; etc.
  - `supported_for_extraction` → "Ready to read"
  - `supported_for_import=false` → "Can't use this file yet"
  - Raw MIME/paths demoted to a collapsed "details" line.
- Import purpose inherits the folder's purpose (student-evidence folders require picking
  a student first).
- **Import always ends with a next action** per file:
  - Ready to read → "Review now" (jumps into extraction with the file pre-selected)
  - Otherwise → "Available in your library" + details.
- Import auto-refreshes the view (fixes the stale-sources wrinkle from v34).

### 3.4 Student-evidence guardrail language
Every student-related import surfaces:
> Nothing is added to the student lens until you approve it.
Flow stays review-first: import → extract → teacher reviews → teacher approves → lens updates.

### 3.5 Share back
- Share panel lives in the Drive view: choose a deliverable (student lens snapshot now;
  see Phase 2 for lesson plans/adapted materials), choose destination from connected
  folders (or configured root).
- Student-lens share shows the colleague-snapshot warning before sending.
- Unchanged backend guarantees: only lv-home files can leave, destination folder
  required, privacy-logged (`drive_upload_shared`), export manifest.

### 3.6 Explicitly NOT in Phase 1
- Google Picker / in-app OAuth ceremony (creds remain env-configured, operator-set).
- Auto-sync of any kind (see §4 — governance).
- Share-back of non-lens deliverables (needs a deliverables registry first).
- Sources/Documents primary-nav restructure (Drive utility button first; promote later
  when Slack + local + Drive converge into one Sources surface).

## 4. Phase 2 — auto-sync ("Keep this folder updated") — OPERATOR RULING REQUIRED

**The governance issue:** the app's published privacy posture is `mode: explicit_import`
— *nothing* comes onto the machine unless the teacher chooses it, file by file. Auto-sync
changes that promise. This must be a deliberate, operator-approved posture change, and
teacher-facing copy/threat-model claims must be updated in the same change.

**Proposed compromise (per UX trace):**
- Never call it "auto sync." Per-folder toggle: **"Keep this folder updated"**.
- Cadence options: *Check when Lingua Viva opens* (default) / *Check every morning* /
  *Check every hour while open*. No true background daemon.
- Three per-folder modes, defaulting to **Review Before Use**:
  1. Import Only — copies down, nothing back
  2. Review Before Use — new/changed files land in a **Needs Review** queue before any use
  3. Share Back Allowed — explicit outputs may go to this folder
- Student-evidence folders can NEVER auto-use; review is mandatory regardless of mode.
- On-open check produces the badge count on the Drive nav button ("3 new files") and
  feeds the **daily file** ("New From Drive" section) alongside Slack's daily ops.

**Build items when approved:** on-open check hook, per-folder mode/cadence storage,
Needs Review queue + view, changed-file detection (modifiedTime vs last_checked),
nav badge, daily-file writer integration, threat-model/copy updates, eval coverage.

## 5. Phase 3 (direction, not scheduled)
- Sources primary-nav view unifying Drive + Slack + local + curriculum folders, tabs:
  Import / Review / Student Lenses / Shared Back.
- Purpose-first entry ("What do you want to bring into Lingua Viva?") ahead of source choice.
- Deliverables registry so share-back covers lesson plans, adapted materials, substitute
  plans, weekly summaries.
- Review-checkbox polish: pre-check acceptable for curriculum content; student-lens
  updates require active approval (unchecked by default) with Add / Don't add / Edit first.
- Extraction copy shift: "Ready to Add" / "Needs Your Review" / "Questions Lingua Viva
  Could Not Answer"; human-readable field names ahead of field paths.

## 6. Ceremony
- UI contract bump (v35) + bump-log; new routes classified in ROUTE_REACHABILITY.yaml;
  EXPECTED_VERSION updated in test_ui_contract.py; full suite green before handoff.
- No commits by agent — operator commit window only (feedback_lv_commit_window).
