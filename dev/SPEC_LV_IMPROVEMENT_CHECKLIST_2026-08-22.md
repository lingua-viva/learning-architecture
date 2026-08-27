# Lingua Viva — Comprehensive Improvement Checklist

**Date:** 2026-08-22
**Purpose:** Every single thing that can be checked and improved, ordered by impact.
**How to use:** Open Claude Code in `~/learning-architecture/`, load this file, pick a
section, and grind. Each item is independent unless marked with a dependency.

---

## Severity Guide

- **P0** — Blocks Claudia from daily use or is a security issue
- **P1** — Significantly improves the product experience
- **P2** — Quality improvement, technical debt, or coverage gap
- **P3** — Nice to have, future-proofing, or parity with MC

---

## 1. SECURITY / PRIVACY (check first, always)

### P0-SEC-001: Remove .env with API key from git tracking
`.env` contains `PERPLEXITY_API_KEY` in plaintext and is committed to the repo.
```bash
# Check
git log --all --full-history -- .env
# Fix
echo ".env" >> .gitignore
git rm --cached .env
git commit -m "fix(security): remove .env from tracking — API key was committed"
```
Then rotate the Perplexity API key (the old one is in git history).

### P0-SEC-002: Audit all log/print statements for student name leakage
Search every log, print, and error message for patterns that could contain student names.
```bash
grep -rn "student.*name\|f\".*{.*name\|\.name\}" src/ --include="*.py" | grep -i "log\|print\|error\|warn"
```
Any match that interpolates a real student name into a log message → replace with hash
or generic identifier. The privacy log (`privacy_log.py`) exists — make sure ALL paths use it.

### P0-SEC-003: Verify student data never reaches Rime TTS
The TTS egress gate exists. Verify it catches ALL paths:
```bash
grep -rn "rime\|tts\|text_to_speech" src/ --include="*.py" | head -30
```
The publication safety check must run before EVERY call to Rime. No exceptions.

### P2-SEC-004: Add encryption at rest for local student data
Observations, lenses, and student profiles are stored as plain JSON/YAML files. Consider
encrypting with a user-provided passphrase using the vault pattern from `docpipe/vault.py`
(already implements AES-GCM encryption for sensitive docs).

---

## 2. GOD-FILE SPLITTING (the #1 architecture debt)

### P1-ARCH-001: Split web.py (9,040 lines → ~10 router modules)

`src/web.py` has 176 route handlers. The router pattern already exists (`src/lingua_viva/routers/`)
with 3 modules extracted. Move the remaining 173 routes:

```
src/lingua_viva/routers/
├── sources.py          # EXISTS
├── safeguarding.py     # EXISTS
├── artifacts.py        # EXISTS
├── students.py         # NEW — /api/students/*, /api/observations/*
├── lesson_materials.py # NEW — /api/lesson-plans/*, /api/prepare/*
├── google_drive.py     # NEW — /api/google-drive/*
├── voice.py            # NEW — /api/voice/*
├── ops.py              # NEW — /api/ops/*
├── curriculum.py       # NEW — /api/curriculum/*
├── filemap.py          # NEW — /api/filemap/*
├── admin.py            # NEW — /api/governance/*, /api/admin/*
└── cohort.py           # NEW — /api/cohort-plans/*
```

**How to do it safely:**
1. Pick ONE router (start with `/api/students/*` — it's self-contained)
2. Create `routers/students.py` with a FastAPI `APIRouter`
3. Move the route handlers from web.py to the new file
4. Import and mount the router in web.py: `app.include_router(students_router)`
5. Run tests: `python3 -m pytest tests/ -q`
6. Repeat for the next router

**Do NOT refactor logic during the move.** Copy the functions exactly. Refactor later.

### P2-ARCH-002: Extract CSS/JS from static/index.html (8,293 lines)

Not a full rewrite — just move the embedded CSS and JS to separate files:
```
static/
├── index.html      # HTML only, links to css/js
├── css/app.css     # All embedded <style> blocks
└── js/app.js       # All embedded <script> blocks
```

This makes the UI editable by Claudia (she can change CSS without touching HTML structure).

### P2-ARCH-003: Split student_lens.py (3,512 lines)

Suggested split:
```
src/education/
├── student_lens/
│   ├── __init__.py        # Public API
│   ├── model.py           # Data model (StudentLens, Evidence, Observation)
│   ├── operations.py      # CRUD operations (create, update, merge, archive)
│   ├── query.py           # Query layer (get by name, filter by tier, search)
│   └── builder.py         # Lens building from documents (the docpipe integration)
```

---

## 3. DOCUMENT GENERATION (templates are the product)

### P1-DOC-001: Add parent report template
Currently `src/education/parent_report.py` generates reports with inline reportlab code.
Create `templates/parent_report.html` with:
- Student name, grade, reporting period
- Strengths section (from observation evidence)
- Growth areas section
- Next steps / recommendations
- Teacher signature line

Wire it into the generation flow so the template controls layout, not Python code.

### P1-DOC-002: Add observation summary template
Create `templates/observation_summary.html`:
- Student name, date range
- Observations grouped by domain (academic, social, behavioral)
- Evidence tags
- Trend indicators (improving, stable, concerning)

### P1-DOC-003: Add assessment rubric template
Create `templates/assessment_rubric.html`:
- Rubric title, subject, grade
- Criteria rows with level descriptors (Beginning, Developing, Meeting, Exceeding)
- Student-specific checkboxes or highlighting per tier

### P1-DOC-004: Enrich the lesson plan template
`templates/lesson_plan.html` is 48 lines. Expand to include:
- IB PYP central idea and lines of inquiry
- Approaches to Learning (ATL) skills targeted
- Learner Profile attribute connections
- Differentiation section with 3-tier visual layout
- Materials checklist with quantities
- Cross-curricular connections
- Assessment criteria linked to curriculum standard
- Reflection space for teacher notes after delivery

### P2-DOC-005: Add revision loop to parent reports
Lesson plans have a revision loop (`revise_lesson_plan_artifact()`). Parent reports don't.
Add the same pattern: teacher reads the generated report, says "make the strengths section
more specific about her reading progress" → report revises.

### P3-DOC-006: Evaluate Typst integration
MC uses Typst (Apache-2.0, 55K stars) for PDF rendering. LV uses reportlab. Typst produces
better-looking documents with less code. Evaluate: is the quality improvement worth adding
Typst as a dependency? If yes, port the lesson plan template to `.typ.j2` format.

---

## 4. KNOWLEDGE / CURRICULUM (grounding is everything)

### P1-KL-001: Add IB Approaches to Learning entries
IB PYP has 5 categories of Approaches to Learning skills: Thinking, Research, Communication,
Social, Self-management. Each has sub-skills. These should be KL entries so lesson plans can
cite them.

### P1-KL-002: Add IB Learner Profile attribute entries
10 attributes: Inquirers, Knowledgeable, Thinkers, Communicators, Principled, Open-minded,
Caring, Risk-takers, Balanced, Reflective. Each needs a KL entry with the IB definition so
the system can reference them in lesson plans and reports.

### P1-KL-003: Add Italian language pedagogy entries
Claudia teaches Italian immersion. The knowledge base needs:
- L2 acquisition stages for young learners (Krashen, Cummins BICS/CALP)
- TPR methodology for vocabulary introduction
- Italian phonological patterns (consonant doubling, vowel endings)
- Common false friends English/Italian
- Grade-specific vocabulary expectations (family, body, animals, food, etc.)

### P2-KL-004: Add subject-specific standards for other subjects
Claudia teaches Italian but the system should support other subjects at her school:
- Math (IB PYP Math scope and sequence)
- Science (IB PYP Science and Technology)
- Social Studies (IB PYP Social Studies)

### P2-KL-005: Add grade-level language progression maps
CEFR-aligned progression for Italian immersion K-5:
- K: A1.1 (pre-production, Total Physical Response)
- Grade 1: A1.2 (early production, single words/phrases)
- Grade 2: A1.3 (speech emergence, short sentences)
- Grade 3: A2.1 (intermediate fluency, connected discourse)
- Grade 4: A2.2 (advanced fluency, paragraph-level writing)
- Grade 5: B1.1 (beginning independence)

### P2-KL-006: Review the 42 ontology proposals
`ontology/proposals/` has 42 CAND-*.yaml files. These are proposed nodes that haven't been
accepted or rejected. Review each:
- Does it describe a real concern Claudia has?
- Does it have a unique signal that won't collide with existing nodes?
- Is it routable (should a query hit this node)?
Accept or reject each one. Don't leave them in limbo.

---

## 5. TEST COVERAGE GAPS

### P1-TEST-001: Add golden queries for lesson plan generation
Current golden queries (36) test classification. None test the lesson plan artifact workflow.
Add 5-10 goldens:
```yaml
- query: "Create a lesson plan for Grade 3 Italian, family vocabulary, 45 minutes"
  expected_node: LV-CUR-001
  expected_artifact: lesson_plan
- query: "Make the warm-up shorter and add a song"
  expected_node: LV-CUR-001
  expected_intent: revision
```

### P1-TEST-002: Add golden queries for parent report workflows
```yaml
- query: "Write a parent report for Sofia's reading progress"
  expected_node: LV-PAR-001
  expected_artifact: parent_report
```

### P2-TEST-003: Test the revision loop
Create `tests/test_lesson_plan_revision.py`:
- Generate a lesson plan → revise "add a song" → verify warm-up section changed
- Generate → revise "make extension harder" → verify extension tier modified
- Generate → revise with nonsense → verify graceful handling
- Generate → revise without model (deterministic fallback) → verify result

### P2-TEST-004: Add bridge tests or archive bridges
`bridges/` has 7 implementations with 0 tests. Either:
- Write basic import + initialization tests for each bridge
- OR confirm these are dead code and archive the directory

### P2-TEST-005: Expand memory tests
`memory/` has 6 Python files but only 11 tests. Add:
- Compaction tests (does memory compact correctly?)
- Store persistence tests (write → restart → read back)
- Redis vs NDJSON adapter parity tests

### P2-TEST-006: Add privacy audit test
Create `tests/test_privacy_audit.py`:
```python
def test_no_student_names_in_logs():
    """Scan all log statements for PII interpolation patterns."""
    # grep through source files for log/print calls that interpolate
    # student name fields without hashing
```

---

## 6. STUDENT DATA PIPELINE

### P1-PIPE-001: Verify the K-5 support detection (just built)
Stream 1 of the 10-stream build added `per_class_sheet_support` detection. Verify:
```bash
python3 -m pytest tests/test_docpipe_extract.py tests/test_students_ingest.py -q
```
Precision ≥0.90, recall ≥0.60 on the K-5 holdout. If not, diagnose.

### P1-PIPE-002: Verify student count gate
Stream 5 confirmed 18/18 students for Grade 3 Verdi. Gate file at
`dev/GATE_STUDENT_COUNT_CONFIRMED_2026-08-22.md`. Verify this is accurate
on the current build.

### P2-PIPE-003: Add PPTX support to docpipe
Some schools distribute curriculum materials as PowerPoint. Add:
```python
# In docpipe/extract.py
from pptx import Presentation  # python-pptx, MIT license
```

### P2-PIPE-004: Add OCR for scanned PDFs
Some documents Claudia receives are scanned (image-based PDFs). Current extraction
returns empty text for these. Options:
- Docling (Apache-2.0, handles OCR via Granite-Docling VLM)
- Tesseract OCR (Apache-2.0, mature)
- Keep it simple: detect image-only PDFs and warn "this appears to be a scanned document — please use a text-based version"

### P2-PIPE-005: Add batch import
Claudia imports files one at a time. Add batch support:
"Import all files in this folder" → process each, show progress, report results.

---

## 7. VOICE IMPROVEMENTS

### P2-VOICE-001: Voice-triggered lesson plan generation
Claudia says "Create a lesson plan for tomorrow's Italian class on family vocabulary."
Currently, voice commands support observation capture and general questions.
Add lesson plan generation to the voice intent regex in `voice_intent.py`:
```python
LESSON_PATTERNS = [
    r"create a lesson plan",
    r"plan a lesson",
    r"prepare (a )?lesson",
    r"lesson for tomorrow",
]
```

### P2-VOICE-002: Voice-triggered observation with student name resolution
"Sofia showed great progress in reading today" → detect student name "Sofia" →
match against class roster → capture observation for the right student.
The voice_intent.py has regex for observations. Verify the student name resolution
path works end-to-end with voice input.

### P3-VOICE-003: Voice feedback for tier changes
When the system recommends a tier change for a student (based on observations),
read it aloud: "Based on 3 recent observations, Sofia may be ready to move to
the Core tier for reading."

---

## 8. GOOGLE DRIVE INTEGRATION

### P0-DRIVE-001: Set OAuth credentials (operator task)
`LV_GOOGLE_OAUTH_CLIENT_ID` and `LV_GOOGLE_OAUTH_SECRET` are not set on this machine.
Drive sign-in shows "not available on this build."
Follow `docs/DRIVE_SETUP.md` (just written in Stream 5) to configure.

### P2-DRIVE-002: Add Drive-based lesson plan storage
After generating a lesson plan, offer: "Save to Google Drive?" → upload to the
teacher's class folder. Currently lesson plans are stored locally only.

### P2-DRIVE-003: Auto-sync class folder on app start
When LV starts and Drive is configured, auto-check the class folder for new files.
Surface: "2 new files in your class folder since yesterday. Import?"

---

## 9. DESKTOP / DISTRIBUTION

### P2-DESK-001: Audit desktop electron files for dead code
- `main.ts` is 25,303 lines
- `bootstrap.ts` is 27,992 lines
- `setup-wizard.html` is 18,241 lines

These are extremely large for an Electron shell. Check for dead code paths,
unused imports, commented-out features.

### P2-DESK-002: Verify all 3 platform builds
```bash
gh run list --repo lingua-viva/learning-architecture --workflow=desktop-release.yml --limit 3
```
Confirm macOS DMG, Windows NSIS, and Linux AppImage all build and produce
downloadable artifacts.

### P2-DESK-003: Verify Mac install path for Claudia
If Claudia is on macOS, verify the DMG install flow:
1. Download DMG from linguaviva.art
2. Open DMG → drag to Applications
3. First launch → setup wizard
4. Model download (Ollama + qwen3:8b)
5. LV web UI opens in the app
6. Everything works without terminal

---

## 10. DEAD CODE / CLEANUP

### P2-CLEAN-001: Audit bridges/ (7 files, 0 tests)
```bash
grep -rn "from bridges\|import bridges" src/ --include="*.py"
```
If nothing imports them → they're dead code ported from MC. Archive to `archive/bridges/`.

### P2-CLEAN-002: Audit skills/ (0 tests)
```bash
grep -rn "from skills\|import skills\|skill_loader" src/ --include="*.py"
```
Same check. If unused, archive.

### P2-CLEAN-003: Review palette_imported.yaml (628KB, 131 entries)
131 non-education entries imported from Palette. Are any of these actually used in
LV's education context? If not, archive or remove. They're 628KB of grounding data
for domains LV doesn't serve.

### P2-CLEAN-004: Clarify pipeline.py vs pipeline_execute.py
- `src/pipeline.py` (1,232 lines) — MC-style full pipeline
- `src/education/pipeline_execute.py` (302 lines) — education-specific execution

Which one runs? Which is legacy? Document or consolidate.

### P2-CLEAN-005: Fix version mismatch
`pyproject.toml` says 1.0.7, `__init__.py` says 1.0.6. Sync them.

### P2-CLEAN-006: Archive old dev/ specs
`dev/` has 224 files. Specs from June/July that are fully implemented don't need to be
top-level. Create `dev/archive/` and move completed specs there. Keep the INDEX.md current.

---

## 11. ONTOLOGY WIRING (MC parity — strategic)

### P3-ONT-001: Verify all 38 LV-* nodes are wired to actions
```python
# For each LV-* node in ontology/education/*.yaml:
# Check: does an action in src/lingua_viva/actions.py reference this node?
# Check: does a route in web.py handle queries classified to this node?
```
MC's finding: 296/329 nodes had no executable action. Check if LV has the same gap.

### P3-ONT-002: Add action entries for lesson plan nodes
LV-CUR-001 (Curriculum Content Generation) should map to the lesson plan generator.
LV-PAR-001 (Parent Communication) should map to the parent report generator.
LV-OBS-001 (Observation Capture) should map to the observation workflow.
Verify these mappings exist and are tested.

### P3-ONT-003: Apply the primitive composition pattern
MC uses 15 primitives composed per node. LV could adopt the same:
- LV-CUR-001: template → review → render (lesson plan)
- LV-PAR-001: extract(observations) → summarize → template → render (parent report)
- LV-OBS-001: extract(voice/text) → record → receipt (observation capture)

This is strategic — only do it if LV is adopting MC's action registry pattern.

---

## 12. QUALITY OF LIFE

### P2-QOL-001: Add "What's new" on app start
When a new version is installed, show a brief changelog on first launch.
The user should know what improved.

### P2-QOL-002: Add keyboard shortcuts
The web UI (static/index.html) uses mouse-only navigation. Add:
- `Ctrl/Cmd + N` → new observation
- `Ctrl/Cmd + L` → new lesson plan
- `Ctrl/Cmd + P` → print current view
- `Ctrl/Cmd + S` → save/export current artifact

### P2-QOL-003: Add offline indicator
When Ollama is not running or the model is not loaded, show a clear indicator
in the UI: "Offline — some features are limited." Don't let queries silently fail.

### P2-QOL-004: Add progress indicators for long operations
Lesson plan generation takes 13-36 seconds. Show a progress bar or spinner with
stage indicators: "Classifying... Retrieving curriculum... Generating plan..."

---

## Execution Order (recommended)

**Day 1:** P0-SEC-001 (remove .env), P0-SEC-002 (audit logs for PII), P0-SEC-003 (verify TTS gate)
**Day 2:** P1-DOC-004 (enrich lesson plan template), P1-DOC-001 (parent report template)
**Day 3:** P1-KL-001 (ATL entries), P1-KL-002 (Learner Profile), P1-KL-003 (Italian pedagogy)
**Day 4:** P1-ARCH-001 (split web.py — start with students router)
**Day 5:** P1-TEST-001 (lesson plan goldens), P1-TEST-002 (parent report goldens)
**Week 2:** P2 items in any order, parallelizable
**Week 3+:** P3 items (MC parity) — only after P0 and P1 are all green

---

*This checklist was produced by auditing every file in the codebase (182 test files,
60+ source modules, 224 dev specs, 18 lenses, 7 knowledge files, 105 ontology nodes,
48 lines of template) and comparing against the patterns established in Mission Canvas.
Every item is independently verifiable and independently buildable.*
