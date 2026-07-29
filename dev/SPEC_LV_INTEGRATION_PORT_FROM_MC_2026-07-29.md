# SPEC — Lingua Viva: Port MC Integration Loop + Voice-First

Date: 2026-07-29  
Status: DRAFT — operator review before build  
Reference: MC's `dev/SPEC_INTEGRATION_LOOP_SEQUENCE_2026-07-28.md` and 5 stage specs  
MC commit baseline: `4f5c0c1c` (all 5 stages + voice + Drive OAuth + CI fixes)

---

## Why This Port

MC just shipped a 5-stage integration loop (ingest → ground → act → deliver → prove) plus voice-first architecture. LV has all the UI surfaces already built (6 workstation slices shipped: Sources registry, Governance control plane, Action queue, Credentials/Slack setup, Daily briefing, Action dispatcher). What's missing is the **durable contracts underneath** those surfaces — the data models that make provenance traceable, actions auditable, and readiness provable.

### What LV Has (UI surfaces — already built)
- `GET /api/sources/status` — 6-row source registry (local, Drive, Slack, curriculum, knowledge, ontology)
- `GET /api/governance/trust` + `/observation-export` + `/verify-pack` — governance control plane with trust status, observation export, evidence tabs
- `GET /api/actions/registry` + `/history` — 7+ action registry with governance badges, activity feed
- `GET/PUT/DELETE /api/slack/credentials` — in-app Slack token setup
- `GET /api/daily/briefing` — daily widgets (unobserved, RTI, unconfirmed)
- Italian voice (Web Speech API `it-IT` in `static/index.html`)
- Drive OAuth (`src/lingua_viva/google_drive_oauth.py` — fully implemented)
- Slack ops bot + observation capture (Socket Mode + Events API)
- Rime TTS with student-data privacy gate

### What LV Is Missing (durable contracts — this spec)
- No `SourceRecord` NDJSON ledger — sources are status-only, not persisted/queryable
- No `GroundingResult` envelope — pipeline classifies but doesn't report tier/GIR per query
- No `ActionPlan` — actions execute but aren't source-backed or approval-gated
- No `DeliverableRecord` — deliverables exist informally (Drive export, parent report) but aren't tracked
- No `AuditReceipt` — governance export exists but doesn't join source→route→action→deliverable
- No E2E golden workflow runner — gauntlet/golden tests exist but don't prove the full loop
- No local STT — Web Speech API is broken in Electron (same root cause as MC)
- No auto-release workflow — manual tag push only

---

## Critical LV Differences From MC

Do NOT blindly copy MC code. LV has structural differences that change every stage:

| Dimension | MC | LV |
|---|---|---|
| Repo | `~/fde/mission-canvas/` (subtree) | `~/learning-architecture/` (standalone, single remote) |
| Web server | `src/api_server.py` (legacy HTTP, 2700+ lines) | `src/web.py` (FastAPI, 4000+ lines) — ALL new routes go here |
| Frontend | React/TypeScript/Vite in `desktop/src/` | Vanilla JS/Alpine.js in `static/index.html` (single-file SPA) — ALL UI changes go here |
| Desktop | Electron + React renderer | Electron shell loading FastAPI HTML (no React) |
| Pipeline | `src/pipeline.py` (4600+ lines, 12-step) | `src/pipeline.py` (970 lines, 8-step legacy fork) |
| Actions | 63 YAML-defined in `actions/*.yaml` | 7 code-defined in `src/lingua_viva/actions.py` |
| Domain | General-purpose workstation | Education: teachers, students, observations, parent reports |
| Privacy | PII/PHI entry gate, PROTECT | Student-data-stays-local, no student names externally, FERPA |
| Source types | local, drive, email, calendar, slack, library, external | local, drive, slack (no email, no calendar) |
| Runtime code | `src/` (flat) | `src/lingua_viva/` (runtime) + `src/education/` (domain) |
| Push protocol | `git push origin main` + 3 subtree pushes | `git push origin main` (one remote) |
| Release | Auto-release on desktop-relevant push | **Manual tag push only** |
| Live site | `missioncanvas.ai` (separate repo, GitHub Pages) | `linguaviva.art` (GitHub Pages from `main:/docs`) |
| Desktop version | 0.2.19+ | 0.2.15 |

---

## Stages

### Stage 0: Auto-Release Workflow (PREREQUISITE)

**Why first**: Without this, nothing reaches the downloadable app. MC lost 14 days to this gap. LV has the identical problem — `desktop-release.yml` only triggers on `desktop-v*` tag push.

**What to do**:

1. Create `.github/workflows/auto-release.yml` adapted from MC's version:
   - Test gate: `pytest -q tests/` (LV's test command)
   - Health: `python3 -m src.lingua_viva.cli health`
   - Backend smoke: boot `src/web.py`, require `/api/health` 200 (LV already has this in `desktop-release.yml` — reuse)
   - Site pin: `docs/index.html` — grep for `desktop-v*` and update to new tag
   - Tag pattern: `desktop-v*` (same as MC)
   - Package name: `lingua-viva-desktop`
2. Test: push a trivial commit to main, verify auto-release creates tag + builds + updates `docs/index.html`

**MC reference**: `.github/workflows/auto-release.yml`

**LV files to create**: `.github/workflows/auto-release.yml`

**Gate**: Push to main → tag auto-created → CI builds → `docs/index.html` pin updated → `linguaviva.art` serves new version.

---

### Stage 1: Source Ledger

**What it adds**: Durable `SourceRecord` NDJSON store underneath the existing `/api/sources/status` surface.

LV already shows 6 source rows. This stage makes those rows queryable, persistent, and traceable — so Stage 2 (grounding) can point to specific source records.

**LV source types** (3, not MC's 7):
- `local` — filemap folders (wired from `src/lingua_viva/ingest.py`)
- `drive` — Google Drive folders/files (wired from `src/lingua_viva/google_drive_integration.py`)
- `slack` — captured observations (wired from `src/education/slack_bot.py`)

**What to do**:

1. Create `src/lingua_viva/sources/` package:
   - `__init__.py`
   - `schema.py` — `SourceRecord` dataclass. Same shape as MC's but:
     - `source_type` enum: `local|drive|slack` (not 7 types)
     - Add `student_data: bool` field (LV-specific — marks records containing student observations)
     - `sensitivity_hint` must enforce: `student_data: true` → `model_context_allowed: false` for external calls
   - `ledger.py` — Writer/reader for `~/.lingua-viva/sources/source_records.ndjson` + `source_observations.ndjson`. Same semantics as MC: deterministic stable IDs from `(source_type, source_id, container, record_id)`, dedup current records, append-only observations.

2. Wire into existing sources (best-effort, never break the underlying feature):
   - `src/lingua_viva/ingest.py` — filemap scans append SourceRecords
   - `src/lingua_viva/google_drive_integration.py` — Drive list/import append SourceRecords
   - `src/education/slack_bot.py` — observation capture appends SourceRecords with `student_data: true`

3. Update existing `GET /api/sources/status` in `src/web.py` to derive counts from ledger (dual-read: fall back to current logic when ledger not initialized)

4. Add routes to `src/web.py` (FastAPI):
   - `GET /api/sources/records` — query params: `type`, `limit`, `q`
   - `GET /api/sources/observations` — query params: `source_record_id`, `limit`

5. Update `renderSources()` in `static/index.html` — add a "Source ledger" expandable section under each source card showing real records with retrieval scope and sensitivity badges

6. Add `tests/test_sources_ledger.py` — hermetic fixtures per source type, stable ID test, dedup test, student_data flag test

**MC reference** (read, adapt, do NOT copy verbatim):
- `src/sources/schema.py`, `src/sources/ledger.py`
- `tests/test_sources_ledger.py`

**LV files to create**:
- `src/lingua_viva/sources/__init__.py`
- `src/lingua_viva/sources/schema.py`
- `src/lingua_viva/sources/ledger.py`
- `tests/test_sources_ledger.py`

**LV files to modify**:
- `src/web.py` — update `/api/sources/status`, add 2 new routes
- `src/lingua_viva/ingest.py` — wire ledger writes
- `src/lingua_viva/google_drive_integration.py` — wire ledger writes
- `src/education/slack_bot.py` — wire ledger writes with `student_data: true`
- `static/index.html` — add ledger detail to `renderSources()`

**Focused gate**:
```bash
pytest tests/test_sources_ledger.py -q
python3 -m src.lingua_viva.cli health
python3 -m src.lingua_viva.cli preflight
```

---

### Stage 2: Grounding Contract

**What it adds**: `GroundingResult` envelope on every ask response, showing which source tier answered, what was used, and GIR.

LV's pipeline is 8-step. The tier hierarchy for LV is simpler (RESEARCH step is disabled — local-first policy):
1. `local` — filemap files
2. `drive` — connected Drive content
3. `slack` — captured observations
4. `knowledge` — knowledge library entries (178 entries, 559 citations)
5. `external` — disabled by policy, always recorded as `blocked`

**What to do**:

1. Create `src/lingua_viva/grounding/` package:
   - `schema.py` — `GroundingResult` dataclass (same shape as MC, fewer tiers, `external` always blocked)
   - `build.py` — Post-hoc builder from LV pipeline traces. Map LV's step results to tier attempts. Assemble from existing trace fields + source ledger lookups.

2. GIR calculator: heuristic `claim_support_v1_heuristic`, same formula as MC. LV's education domain makes this more concrete — observations and lesson plans are either sourced or not.

3. Add `grounding` field to ask response — update the `/api/ask` or `/api/query` handler in `src/web.py`

4. Update governance section in `static/index.html` — show tier used + GIR score in `renderGovernance()` evidence panel

5. Add `tests/test_grounding_result.py`

**MC reference**: `src/grounding/schema.py`, `src/grounding/build.py`

**LV files to create**:
- `src/lingua_viva/grounding/__init__.py`
- `src/lingua_viva/grounding/schema.py`
- `src/lingua_viva/grounding/build.py`
- `tests/test_grounding_result.py`

**LV files to modify**:
- `src/web.py` — add grounding to ask response
- `static/index.html` — grounding display in governance view

**Focused gate**:
```bash
pytest tests/test_grounding_result.py -q
python3 -m src.lingua_viva.cli health
```

---

### Stage 3: Source-Backed Action Plan

**What it adds**: `ActionPlan` linking grounded context to action execution, with approval gate and source provenance.

LV has 7 actions. The plan is lighter than MC's but still gives the teacher: "here's what MC will do, here's what data it's using, approve or reject."

**What to do**:

1. Create `src/lingua_viva/action_plans/` package:
   - `schema.py` — `ActionPlan` dataclass (links `grounding_id` + `source_record_ids` to action)
   - `store.py` — NDJSON at `~/.lingua-viva/actions/plans.ndjson`

2. Add routes to `src/web.py`:
   - `POST /api/action-plans/preview`
   - `POST /api/action-plans/approve`
   - `POST /api/action-plans/reject`
   - `GET /api/action-plans/history`

3. Update existing action execution path to accept optional `action_plan_id`

4. Update `renderActions()` in `static/index.html` — show durable plans with source badges, approve/reject buttons

5. Add `tests/test_action_plans.py`

**MC reference**: `src/actions/plan_schema.py`, `src/actions/plan_store.py`

**Focused gate**:
```bash
pytest tests/test_action_plans.py -q
python3 -m src.lingua_viva.cli health
```

---

### Stage 4: Deliverable + Audit Receipt

**What it adds**: `DeliverableRecord` tracking every produced output + `AuditReceipt` joining the full chain.

LV deliverables are education-specific: parent reports, daily files, assessments, Drive exports, governance observation exports. These already exist as outputs — this stage tracks them durably and makes proof exportable.

**What to do**:

1. Create `src/lingua_viva/deliverables/` package:
   - `schema.py` — `DeliverableRecord` (types: `parent_report|daily_file|assessment|drive_export|observation_export|none`)
   - `store.py` — NDJSON at `~/.lingua-viva/deliverables/records.ndjson`

2. Create `src/lingua_viva/audit_receipts/` package:
   - `schema.py` — `AuditReceipt` with `missing_join_keys` support
   - `builder.py` — Join across pipeline traces, source ledger, grounding, action plan, deliverable. Student data fields are NEVER included in exported receipts.

3. Add routes to `src/web.py`:
   - `GET /api/deliverables`
   - `POST /api/audit-receipts/export`

4. Migrate existing `/api/governance/observation-export` and `/api/governance/verify-pack` to call the receipt builder internally

5. Update governance export in `static/index.html` — add scope selector, incomplete badge

6. Add `tests/test_deliverables.py`, `tests/test_audit_receipts.py`

**MC reference**: `src/deliverables/`, `src/audit_receipts/`

**Privacy rule**: `AuditReceipt` export must NEVER contain student names, student IDs, or observation text that could identify a child. The builder must strip or hash student references before export. This is LV-specific and does not exist in MC.

**Focused gate**:
```bash
pytest tests/test_deliverables.py tests/test_audit_receipts.py -q
python3 -m src.lingua_viva.cli health
```

---

### Stage 5: Golden Workflows (Education-Specific)

**What it adds**: E2E workflow runner proving the full loop for education use cases.

LV already has `tests/test_e2e_still_i_rise.py` (Slack → observation → lens → differentiation) and layer 4/5 gauntlets. This stage adds the formal runner with hermetic + live modes and contract chain verification.

**LV golden workflows** (5 education-specific):

| ID | Goal | Hermetic Setup |
|---|---|---|
| GW-EDU-001 | Observation → student lens update → parent report → Drive export | Fixture observation + temp student folder |
| GW-EDU-002 | Daily file generation from local + Drive sources → deliverable | Fixture filemap + Drive mock |
| GW-EDU-003 | Teacher question → grounded answer → assessment generation | Fixture knowledge entries |
| GW-DRIVE-004 | Drive folder → import → grounded answer → export back | Mock Drive responses |
| GW-SLACK-005 | Slack observation capture → source ledger → lens update | Fixture Slack event |

Each hermetic workflow must exercise the full contract chain: `SourceRecord → GroundingResult → ActionPlan → DeliverableRecord → AuditReceipt`.

**What to do**:

1. Create `src/lingua_viva/golden_workflows/` package:
   - `schema.py` — `GoldenWorkflowResult` (same shape as MC)
   - `runner.py` — 5 workflow implementations

2. Add CLI command `lv golden-workflows` with `--hermetic`, `--live`, `--only GW-*`, `--json` flags — add to `src/lingua_viva/cli.py`

3. Add `tests/test_golden_workflows.py`

4. Optionally add workflow matrix display to `static/index.html` governance section

**MC reference**: `src/golden_workflows/`

**Gate**:
```bash
python3 -m src.lingua_viva.cli golden-workflows --hermetic
pytest tests/test_golden_workflows.py -q
```

---

### Stage 6: Voice-First (Local STT)

**What it adds**: Local Whisper STT replacing broken Web Speech API in Electron. Independent of Stages 1-5 — can be built in parallel.

LV's voice is Italian-first. The browser `SpeechRecognition` with `lang: "it-IT"` works in Chrome but silently fails in Electron (no Google cloud speech API keys). Same root cause as MC.

**What to do**:

1. Create `src/lingua_viva/voice_stt.py` — `WhisperLocalProvider` wrapping `faster-whisper` (CPU, int8, tiny model). Italian default. Port from MC's `src/voice/stt.py`.

2. Add routes to `src/web.py`:
   - `POST /api/voice/stt` — accepts audio blob, returns transcript
   - `GET /api/voice/probe` — runtime capability check (ffmpeg, STT, TTS status)

3. Add Electron mic permission handler to `desktop/electron/main.ts`:
   ```typescript
   session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
     callback(permission === 'media');
   });
   ```

4. Replace Web Speech API in `static/index.html`:
   - In `voiceRuntime.toggleAsk()` and `voiceRuntime.toggleObserve()`: replace `SpeechRecognition` with `navigator.mediaDevices.getUserMedia()` → `MediaRecorder` (webm/opus) → silence detection → `fetch('/api/voice/stt')` → transcript callback
   - Keep Rime TTS as-is (already working with student-data gate)
   - Keep `lang: "it-IT"` — Whisper auto-detects Italian

5. Add `faster-whisper` to pip deps in `desktop/electron/main.ts`

6. Add voice model download to setup flow in `desktop/electron/main.ts`

7. Add voice health checks to `lv health`

8. Add `tests/test_voice_stt.py` with `skipif not ffmpeg` guards

**MC reference**:
- `src/voice/stt.py` — WhisperLocalProvider
- `desktop/src/voice/capture.ts` — capture logic (adapt to vanilla JS for `static/index.html`)
- `desktop/electron/main.ts` — mic permission (line 744), pip dep, model download

**LV files to create**:
- `src/lingua_viva/voice_stt.py`
- `tests/test_voice_stt.py`

**LV files to modify**:
- `src/web.py` — add STT + probe routes
- `desktop/electron/main.ts` — mic permission, pip dep, model download
- `static/index.html` — replace Web Speech API with MediaRecorder + fetch

**Gate**: Mic button works in Electron. Voice → transcript → pipeline → response in Italian. `lv health` includes voice checks.

---

## Build Order

```
Stage 0 (auto-release)     ← PREREQUISITE, do first
    │
Stage 1 (source ledger)    ← contracts under existing Sources UI
    │
Stage 2 (grounding)        ← contracts under existing Governance UI
    │
Stage 3 (action plans)     ← contracts under existing Actions UI
    │
Stage 4 (deliverable+audit)← contracts under existing Governance export
    │
Stage 5 (golden workflows) ← proves the loop
    │
Stage 6 (voice-first)      ← independent, can parallel with 3-5
```

**2-PC split** (if available):
- PC-A: Stages 0-5 (sequential, contracts)
- PC-B: Stage 6 (voice, independent)

---

## Files That Must NOT Be Touched

- `archive/mc-engine/` — dead, stays dead (CLAUDE.md rule 6)
- `src/pipeline.py` — legacy, scheduled for replacement; stages wrap around it
- `src/education/` — domain logic stays as-is; stages add contracts above it, never break education features

---

## Commit Convention

Per CLAUDE.md: `<type>(<scope>): message`. Scope: `engine`.

```
chore(meta): add auto-release workflow
feat(engine): Stage 1 — Source Ledger
feat(engine): Stage 2 — Grounding Contract
feat(engine): Stage 3 — Action Plans
feat(engine): Stage 4 — Deliverable + Audit Receipt
feat(engine): Stage 5 — Golden Workflows
feat(engine): Stage 6 — Voice-First Local STT
```

---

## Push Protocol

Single remote:
```bash
git push origin main
```

If auto-release (Stage 0) is built, desktop tag is cut automatically. If not yet, manual:
```bash
git tag desktop-v0.2.16 && git push origin desktop-v0.2.16
```

Verify per AGENTS.md 7-step checklist before saying "pushed."

---

## Estimated Effort

| Stage | Size | Notes |
|---|---|---|
| 0. Auto-release | S | Adapt MC's workflow |
| 1. Source ledger | M | Wire under existing Sources UI |
| 2. Grounding | M | Wire under existing Governance UI |
| 3. Action plans | M | Wire under existing Actions UI |
| 4. Deliverable + audit | M | Wire under existing Governance export |
| 5. Golden workflows | M | Education-specific E2E |
| 6. Voice-first | L | Replace Web Speech API with Whisper |

Total: ~5-7 sessions sequential, ~4-5 if voice parallels.
