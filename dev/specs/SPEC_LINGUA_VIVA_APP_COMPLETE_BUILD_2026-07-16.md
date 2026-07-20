# SPEC: Lingua Viva App — Complete Build

**Date**: 2026-07-16
**Status**: SHIPPED
**Author**: kiro.design (synthesized from separation, migration, and unified build specs)
**Repo**: `/home/mical/learning-architecture` (git@lingua-viva:lingua-viva/learning-architecture.git)
**Branch**: `LINGUA-VIVA-UPDATE`
**Supersedes**: SPEC_LINGUA_VIVA_APP_UNIFIED_BUILD_2026-07-16.md (scope/product-only), SPEC_MC_BACKEND_MIGRATION_2026-07-16.md (Phase 3 complete)
**Companion specs**: SPEC_LINGUA_VIVA_LOCAL_SUPPORT_LOOP_2026-07-16.md, SPEC_LINGUA_VIVA_ACCOUNTABLE_CURRICULUM_SYSTEM_2026-07-16.md, LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md
**Build method**: Phase-gated with hardening sweeps

---

## 0. What We're Building

A local-first teacher app (Electron) that wraps Lingua Viva's curriculum engine, governed privacy model, and Doctor health system into a task-first interface for Italian language teachers. The teacher downloads it, installs it, and from that point forward opens Lingua Viva instead of managing loose .docx files, scattered PDFs, and manual CEFR alignment — because Lingua Viva is the only place where their curriculum, assessment framework, classroom activities, and teacher reflections all meet AI inference safely and privately.

**The design principle (Steph Ango):** Subtraction. Four things in the sidebar (Plan, Prepare, Assess, Reflect). Everything else earned through use. Doctor lives in the quiet utility area — teachers don't think about health until something breaks.

**The privacy principle:** Student data never leaves the machine. Teacher data never leaves the machine. The .docx is authoritative. AI assists; AI never decides, publishes, or speaks on behalf of the teacher.

---

## 1. What Exists Today (Verified Jul 16, commit 64c6760)

| Component | Status | Location |
|---|---|---|
| Native LV module (reasoning, privacy, config, cli, app, ingest) | Working, 18 tests | `src/lingua_viva/` |
| Education pipeline (16 modules) | Working, 313 tests total | `src/education/` |
| Doctor support loop | Working, 15 tests | `doctor/support_loop/` |
| Web UI (chat, PWA, offline queue) | Working, rebranded LV | `static/index.html` (764 lines) |
| Curriculum matrix | Present | `curriculum/lingua_viva_matrix.yaml` |
| Governance rules | Present | `governance/publication_safety.yaml` |
| Evidence register | Present | `claims/evidence_register.yaml` |
| Artifact inventory | Present | `artifacts/inventory.yaml` |
| Reference library (CEFR + Italian curriculum) | Present | `references/` |
| Document ingestion (PDF→embeddings) | Working | `src/lingua_viva/ingest.py` + `src/education/document_*` |
| Ontology (education domain nodes) | Working | `ontology/` |
| Knowledge library (education entries) | Working | `knowledge/` |
| Content differentiator | Working | `src/education/content_differentiator.py` |
| Teacher guide generator | Working | `src/education/teacher_guide.py` |
| Assessment generator | Working | `src/education/assessment_generator.py` |
| Observation capture | Working | `src/education/observation_capture.py` |
| Student lens (privacy-scoped) | Working | `src/education/student_lens.py` |
| Parent report generator | Working | `src/education/parent_report.py` |
| Publication safety rules | Present | `governance/publication_safety.yaml` |
| Artifact gauntlet | Working (3 failures, path issues) | `doctor/lv_artifact_gauntlet.py` |
| API server + WebSocket | Working | `src/web.py` (rebranded) |
| GET /api/health (Doctor endpoint) | Working | `src/web.py` |
| MC-shaped legacy (archived) | Frozen | `archive/mc-engine/` |

**What does NOT exist:**
- Electron shell (no native window, no dock icon)
- Task-first sidebar (current UI is chat-first, branded "Still I Rise")
- Plan/Prepare/Assess/Reflect workflows as distinct views
- Curriculum browser (teacher can't navigate the matrix visually)
- Activity generator UI (content_differentiator exists, no UI)
- Support bundle endpoint (Phase B spec exists, not built)
- Publication status display
- Source-of-truth status indicators (what's authoritative vs derivative)
- Cross-platform installers

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Electron Shell                        │
│  - Spawns LV API server as child process                │
│  - Window management, state persistence                 │
│  - File system IPC (for curriculum file access)         │
│  - Native OS integration (dock, tray)                   │
│  - Auto-update                                          │
└───────────────┬─────────────────────────────────────────┘
                │ IPC (preload bridge)
┌───────────────▼─────────────────────────────────────────┐
│                Teacher Interface (HTML/JS)               │
│  - Sidebar: Plan, Prepare, Assess, Reflect              │
│  - Utility bar: Health, Settings, Privacy               │
│  - Main pane: selected teacher workflow                  │
│  - Source status indicators on all content              │
│  - Privacy indicators (what stays local)                │
└───────────────┬─────────────────────────────────────────┘
                │ HTTP to localhost:8787
┌───────────────▼─────────────────────────────────────────┐
│              Lingua Viva API Server (Python)             │
│  - src/lingua_viva/ (reasoning, privacy, config)        │
│  - src/education/ (16 teacher-facing modules)           │
│  - doctor/support_loop/ (health + diagnostics)          │
│  - Local Ollama inference only                          │
│  - curriculum/ + knowledge/ + ontology/                 │
│  - .docx remains untouched source of truth              │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Build Phases (Ordered by Value)

### Phase 1 — The Shell (Days 1-2)

**Goal:** Lingua Viva runs as a native desktop app. Download → Install → Launch → See the teacher interface in a native window.

#### 1.1 Electron main process

Create `desktop/electron/main.ts`:

```
App lifecycle:
  - ready → create window, spawn backend
  - window-all-closed → quit (macOS: hide)
  - activate → recreate window if needed

Backend spawn:
  - python3 src/web.py (or src/lingua_viva/app.py once it serves)
  - Health probe: GET http://127.0.0.1:8787/api/health
  - Restart on crash (max 3 retries)

Window:
  - BrowserWindow → http://127.0.0.1:8787
  - 1100×800, min 600×400
  - Title: "Lingua Viva"
  - State persistence (position, size)
  - CSP hardened
  - Context isolation, no node integration, sandbox
```

#### 1.2 Preload bridge

Create `desktop/electron/preload.ts` (~30 lines):

```typescript
contextBridge.exposeInMainWorld('lvDesktop', {
  readFile: (path) => ipcRenderer.invoke('lv:fs:readFile', path),
  getVersion: () => ipcRenderer.invoke('lv:version'),
  notify: (title, body) => ipcRenderer.invoke('lv:notify', title, body),
  onBackendReady: (cb) => ipcRenderer.on('lv:backend-ready', cb),
});
```

#### 1.3 First-run bootstrap

On first launch:
1. "Starting Lingua Viva..."
2. Check Python 3.10+
3. Check Ollama (prompt install if missing)
4. Pull model if available
5. Launch API server
6. Open window

#### 1.4 Packaging

```json
{
  "name": "lingua-viva",
  "productName": "Lingua Viva",
  "version": "0.1.0",
  "build": {
    "appId": "app.linguaviva.teacher",
    "productName": "Lingua Viva",
    "extraResources": [
      { "from": "../src", "to": "lv/src" },
      { "from": "../ontology", "to": "lv/ontology" },
      { "from": "../knowledge", "to": "lv/knowledge" },
      { "from": "../curriculum", "to": "lv/curriculum" },
      { "from": "../doctor", "to": "lv/doctor" },
      { "from": "../references", "to": "lv/references" },
      { "from": "../static", "to": "lv/static" }
    ],
    "mac": { "icon": "assets/icon.icns", "category": "public.app-category.education" },
    "win": { "icon": "assets/icon.ico" },
    "linux": { "icon": "assets/icon.png", "category": "Education" }
  }
}
```

**Deliverable:** `lingua-viva-0.1.0.dmg`, `lingua-viva-0.1.0-setup.exe`, `lingua-viva-0.1.0.AppImage`

---

### 🔒 HARDENING GATE 1

Run before proceeding to Phase 2:

```bash
python3 -m pytest tests/ -q                          # 313+ pass
python3 -m pytest doctor/support_loop/tests/ -q      # 15 pass
python3 -m doctor.support_loop doctor                 # Not CRITICAL
```

Plus 15-iteration Electron sweep:
- Launch, health probe succeeds, window renders
- Quit, no orphaned processes, port freed
- Relaunch, no port conflict
- Window state persists across restart

---

### Phase 2 — The Teacher Interface (Days 3-5)

**Goal:** Replace the chat-first "Still I Rise" UI with a task-first teacher workbench.

#### 2.1 New static/index.html

Replace the 764-line chat UI with a teacher-first layout. Pure HTML/CSS/JS (no React — keep it deployable as a single file like the current app):

```
┌── Sidebar (200px) ──┐  ┌── Main Pane ──────────────────────┐
│                      │  │                                    │
│  [LV mark]           │  │  (content changes based on         │
│                      │  │   sidebar selection)               │
│  📋 Plan             │  │                                    │
│  ✏️ Prepare          │  │                                    │
│  📊 Assess           │  │                                    │
│  💭 Reflect          │  │                                    │
│                      │  │                                    │
│                      │  │                                    │
│                      │  │                                    │
│  ──────────────      │  │                                    │
│  ❤️ Health           │  │                                    │
│  🔒 Privacy          │  │                                    │
│  ⚙ Settings         │  │                                    │
└──────────────────────┘  └────────────────────────────────────┘
```

#### 2.2 View descriptions

**Plan** — Curriculum navigator
- Shows grade bands (G1-G5)
- Shows CEFR alignment targets (designed-to language, not achievement)
- Shows .docx source status ("Authoritative source: Manuale v1")
- Shows matrix entries for selected grade
- Teacher can browse the progression, see what comes next
- No editing of .docx from here

**Prepare** — Activity generator
- Teacher selects grade + unit from Plan
- System generates classroom-ready activity drafts using content_differentiator
- Source material: .docx content + knowledge library
- Output: printable activity sheet, differentiated for ability levels
- Source indicators: "Generated from Manuale §4.2, Grade 3, Unit: La Famiglia"
- Teacher can ask free-form questions (routes to reasoning engine)

**Assess** — Assessment design aid
- Shows CEFR-informed structures for the selected unit
- "Designed to target A1 listening comprehension" (never "students achieve A1")
- Rubric templates aligned to school assessment framework
- Observation capture: teacher notes what happened in class (private, local only)
- No auto-grading, no outcome claims

**Reflect** — Teacher journal + revision
- Private implementation notes
- Anonymized revision suggestions (what worked, what didn't)
- Logged to `dev/lv_revision_log.ndjson` with accountable proof
- Teacher can propose curriculum adjustments (creates deferred candidate)
- Zero student data in this view

**Health** — Doctor
- Runs doctor/support_loop diagnostics
- Shows status (OK / WARN / FIXABLE / PRIVATE_RISK)
- Offers "Create Support Bundle" when non-OK (Phase B)
- Shows publication readiness status
- Shows gauntlet results

**Privacy** — Data transparency
- Shows what stays local (everything)
- Shows what would be in a support bundle (redacted summary)
- Shows .lv_support/ contents if any
- Confirms: no uploads, no cloud, no student data leaves

**Settings** — Model and config
- Ollama model selection
- Port configuration
- Reference file paths

#### 2.3 API endpoints (add to src/web.py or src/lingua_viva/app.py)

```python
# Curriculum
GET  /api/curriculum/overview          # Grade bands + unit counts
GET  /api/curriculum/grade/<grade>     # Units for a grade band
GET  /api/curriculum/unit/<unit_id>    # Activities, CEFR targets, materials

# Prepare
POST /api/prepare/activity             # Generate activity draft
     { "grade": "G3", "unit": "la-famiglia", "ability_level": "mixed" }

# Assess
GET  /api/assess/rubric/<unit_id>      # Rubric template for unit
POST /api/assess/observation           # Save observation note (private)
     { "unit_id": "...", "note": "...", "date": "..." }

# Reflect
POST /api/reflect/note                 # Save reflection
     { "note": "...", "tags": [...] }
GET  /api/reflect/history              # Read past reflections
POST /api/reflect/revision-proposal    # Propose curriculum change
     { "unit_id": "...", "suggestion": "...", "evidence": "..." }

# Health (already exists)
GET  /api/health                       # Doctor result

# Support bundle (Phase B — add in Phase 3)
POST /api/support-bundle               # Create redacted bundle

# Publication
GET  /api/publication/status           # Readiness audit summary

# Chat fallback (keep existing)
POST /api/query                        # Free-form question → reasoning engine
```

#### 2.4 Curriculum data layer

Create `src/lingua_viva/curriculum.py`:

```python
class CurriculumService:
    """Read-only access to curriculum data. Source: .docx (authoritative) + matrix (derivative)."""
    
    def __init__(self):
        self.matrix = self._load_matrix()  # curriculum/lingua_viva_matrix.yaml
    
    def get_overview(self) -> dict:
        """Grade bands with unit counts."""
    
    def get_grade(self, grade: str) -> list[dict]:
        """Units for a grade band."""
    
    def get_unit(self, unit_id: str) -> dict:
        """Full unit detail: CEFR targets, materials, activities."""
    
    def source_status(self) -> dict:
        """Returns authoritative source info + derivative status."""
        return {
            "authoritative": "Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx",
            "authoritative_modified": False,  # git status check
            "derivative": "curriculum/lingua_viva_matrix.yaml",
            "derivative_status": "non-authoritative until promotion",
        }
```

---

### 🔒 HARDENING GATE 2

```bash
python3 -m pytest tests/ -q                    # 313+ pass (no regressions)
python3 -m pytest doctor/support_loop/tests/ -q  # 15 pass
python3 -m doctor.support_loop doctor           # OK or WARN (not CRITICAL)
```

Plus 15-iteration teacher workflow sweep:
- Each sidebar item loads its view
- Plan shows grade bands from the matrix
- Prepare generates an activity (if Ollama running)
- Assess shows rubric structure
- Reflect saves a note to revision log
- Health shows doctor result
- Privacy shows "all local" confirmation
- No "Still I Rise" or "Mission Canvas" visible anywhere
- .docx is never modified

---

### Phase 3 — Support Bundle + Publication Status (Days 5-6)

**Goal:** Phase B of the Doctor spec. Teacher can create a support bundle when something breaks.

#### 3.1 Support bundle

Implement `POST /api/support-bundle`:
- Runs Doctor
- Runs gauntlet
- Creates `.lv_support/bundles/lv-support-{timestamp}/`
- Contents: redacted doctor result, gauntlet output, git status, manifest
- Excludes: .docx, student data, observations, IEPs, progress reports, secrets
- Redaction report shows what was excluded and why
- No upload, no zip, no screenshots

#### 3.2 Publication status endpoint

Implement `GET /api/publication/status`:
- Reads `governance/publication_safety.yaml`
- Reads `claims/evidence_register.yaml`
- Returns: which claims are safe to publish, which need evidence, which are blocked
- Matches the readiness audit findings

#### 3.3 Source of truth indicators

Every response from Prepare/Assess should include:
```json
{
  "source": "Manuale §4.2, Grade 3",
  "source_status": "authoritative",
  "claim_maturity": "designed-to-target",
  "note": "CEFR A1 listening — design target, not measured outcome"
}
```

---

### 🔒 HARDENING GATE 3 — Final Gate Before Ship

```bash
python3 -m pytest tests/ -q
python3 -m pytest doctor/support_loop/tests/ -q
python3 -m doctor.support_loop doctor
python3 doctor/lv_artifact_gauntlet.py
rg "Mission Canvas|Still I Rise|MC_|mc\." static/ src/ tests/
git status --short -- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx
```

Plus 15-iteration full-app sweep:
- Install from package → first-run bootstrap → teacher sees sidebar
- Plan → browse Grade 3 → see CEFR targets with "designed-to" language
- Prepare → generate activity for Grade 3 → source citation visible
- Assess → view rubric → no achievement claims, only design targets
- Reflect → save note → appears in revision log
- Health → OK status → Support Bundle available
- Privacy → confirms all local, no uploads
- Support bundle → creates bundle → excludes .docx + student data
- Publication status → shows "not publication-ready" per audit
- .docx never modified
- No MC/StillIRise branding anywhere
- No student data in any response, log, or bundle

---

## 4. File Structure (Target)

```
learning-architecture/
├── desktop/                            # NEW — Electron shell
│   ├── electron/
│   │   ├── main.ts                     # App lifecycle, backend spawn
│   │   ├── preload.ts                  # IPC bridge
│   │   └── bootstrap.ts               # First-run flow
│   ├── assets/                         # Icons
│   ├── package.json
│   └── vite.config.ts
├── src/
│   ├── lingua_viva/                    # NATIVE MODULE (exists)
│   │   ├── __init__.py
│   │   ├── app.py                      # App bridge (exists)
│   │   ├── reasoning.py               # Ollama (exists)
│   │   ├── privacy.py                 # Student data rules (exists)
│   │   ├── config.py                  # Model config (exists)
│   │   ├── cli.py                     # lv CLI (exists)
│   │   ├── ingest.py                  # Doc ingestion (exists)
│   │   ├── curriculum.py              # NEW — curriculum data layer
│   │   ├── publication.py             # NEW — publication status
│   │   └── support_bundle.py          # NEW — bundle creation
│   ├── education/                      # PRODUCT CODE (exists, 16 modules)
│   ├── web.py                          # HTTP server (exists, rebranded)
│   ├── pipeline.py                     # Legacy (exists, stubs)
│   ├── provider_config.py             # Model detection (exists)
│   └── session.py                      # Sessions (exists)
├── doctor/                             # HEALTH (exists)
│   ├── support_loop/
│   ├── lv_support.py
│   └── lv_artifact_gauntlet.py
├── static/                             # TEACHER UI
│   ├── index.html                      # NEW — task-first teacher interface
│   ├── sw.js                           # PWA worker (exists, rebranded)
│   ├── manifest.json                   # PWA manifest (exists)
│   └── offline.html                    # Offline page (exists, rebranded)
├── curriculum/                         # DATA (exists)
│   └── lingua_viva_matrix.yaml
├── governance/                         # RULES (exists)
│   └── publication_safety.yaml
├── claims/                             # EVIDENCE (exists)
│   └── evidence_register.yaml
├── artifacts/                          # INVENTORY (exists)
│   └── inventory.yaml
├── references/                         # SOURCE (exists)
│   ├── CEFR_can_do_lists.pdf
│   ├── CEFR_Young_Learners.pdf
│   └── ...Italian curriculum docs
├── ontology/                           # DOMAIN NODES (exists)
├── knowledge/                          # KNOWLEDGE ENTRIES (exists)
├── tests/                              # TESTS (exists, 313 passing)
├── archive/mc-engine/                  # FROZEN MC LEGACY
├── dev/                                # SPECS + LOGS
│   ├── specs/
│   ├── lv_revision_log.ndjson
│   └── lv_deferred_candidates.yaml
├── Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx  # SOURCE OF TRUTH
├── CLAUDE.md
└── README.md
```

---

## 5. What We Deliberately Don't Build

| Feature | Why not |
|---|---|
| Cloud sync | Local-first. Teacher data never leaves. |
| Auto-grading | No outcome claims. Assessment is design aid only. |
| Student database | Privacy. Observations are private teacher notes. |
| Parent portal | Separate concern. Parent reports are generated docs, not live views. |
| Multi-user | Each teacher has their own installation. |
| .docx editor | .docx is authoritative source, read-only from app. |
| Curriculum publishing | Not publication-ready per audit. |
| AI-attributed content | Zero-AI-attribution rule for anything public. |
| MC pipeline / gates / gateway | Archived. LV uses simple local reasoning. |
| External research | Local-only. No Perplexity, no web search. |
| Action registry / connectors | MC pattern. LV has direct function calls. |
| Chat history sidebar | Teachers do tasks, not conversations. |

---

## 6. Curriculum Governance (Enforced by Code)

These are not guidelines. They are enforced constraints:

1. **`Manuale_*.docx` is NEVER modified** — `git status --short -- Manuale*` must always be empty
2. **Matrix is non-authoritative** — UI shows "derived from" label, not "this IS the curriculum"
3. **CEFR claims use designed-to language** — "Designed to target A1 listening" not "Students achieve A1"
4. **Public claims need evidence** — `claims/evidence_register.yaml` gates what can be displayed publicly
5. **Student data never leaves** — privacy.py blocks student names, grades, observations from any output
6. **Zero-AI-attribution** — generated content that reaches external surfaces must not say "AI-generated"
7. **Revision accountability** — every curriculum change logged to `dev/lv_revision_log.ndjson` with timestamp, author, evidence

---

## 7. Privacy Model (Not MC Gates — Education-Specific)

MC uses enterprise PII gates (SSN, credit cards, HIPAA). LV uses education-specific privacy:

| Data Type | Rule | Enforcement |
|---|---|---|
| Student names | Never in any output or log | `src/lingua_viva/privacy.py` |
| Student grades/scores | Never leaves app | privacy scan on all responses |
| Observations/IEPs | Private teacher notes only | excluded from support bundles |
| Parent communications | Never in any output | excluded from bundles |
| Teacher reflections | Local only, never uploaded | stored in revision log |
| Institution names | Allowed in private, blocked from public | publication_safety.yaml |
| Colleague names | Blocked from public outputs | privacy scan |
| .docx content | Never sent to any model as training data | ingest creates embeddings only |

---

## 8. Success Criteria

**For first teacher (target: end of July):**
- [ ] Downloadable .app/.dmg (macOS priority — Mical's machine)
- [ ] Installs in <2 minutes
- [ ] Sidebar with Plan/Prepare/Assess/Reflect
- [ ] Plan shows Grade 3 curriculum with CEFR targets
- [ ] Prepare generates a classroom activity from .docx source
- [ ] Source citations visible on every generated output
- [ ] "Designed to target" language everywhere (no achievement claims)
- [ ] Health shows Doctor status
- [ ] Privacy confirms all-local
- [ ] .docx untouched throughout entire session

**For publication readiness (future — after teacher feedback):**
- [ ] README wording approved per readiness audit
- [ ] Gauntlet passes clean
- [ ] Doctor reports OK
- [ ] No institution-identifying details in public surfaces
- [ ] Evidence register reviewed with co-author

---

## 9. Validation Commands (Run After Each Phase)

```bash
# Core
python3 -m pytest tests/ -q
python3 -m pytest doctor/support_loop/tests/ -q
python3 -c "from src.lingua_viva import reasoning, privacy, config, cli, app, ingest; print('OK')"

# Doctor
python3 -m doctor.support_loop doctor

# Gauntlet
python3 doctor/lv_artifact_gauntlet.py

# Boundary check
rg "Mission Canvas|Still I Rise|MC_|mc\." static/ src/lingua_viva/ tests/
git status --short -- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx

# Privacy check
rg "student.*name|grade.*\d|IEP|parent.*contact" static/ src/lingua_viva/
```

---

*This spec synthesizes: the MC App Complete Build pattern (architecture, phases, hardening gates), the Lingua Viva Unified Build spec (product shape, teacher tasks), the Accountable Curriculum System spec (governance rules), the Publication Readiness Audit (claim constraints), the Local Support Loop spec (Doctor integration), and the MC Sidebar/CX Design spec (task-based navigation principle). Everything the teacher app needs, in one place. Build from here.*
