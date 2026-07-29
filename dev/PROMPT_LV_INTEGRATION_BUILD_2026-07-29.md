# Build Prompt — Lingua Viva Integration Loop + Voice-First

You are building the integration loop for Lingua Viva. Read the spec first:

```
dev/SPEC_LV_INTEGRATION_PORT_FROM_MC_2026-07-29.md
```

This is a port of Mission Canvas's 5-stage integration loop adapted for LV's education domain. LV already has all UI surfaces built (Sources, Governance, Actions, Credentials, Daily). Your job is adding **durable contracts underneath** those existing surfaces.

## Critical Rules

1. **All routes go in `src/web.py`** (FastAPI). Do NOT create an `api_server.py`.
2. **All runtime code goes in `src/lingua_viva/`**. Do NOT put modules at `src/` root.
3. **All UI changes go in `static/index.html`** (vanilla JS/Alpine.js). There is NO React, NO TypeScript in the frontend.
4. **Do NOT touch `archive/mc-engine/`** — dead code, stays dead.
5. **Do NOT touch `src/pipeline.py`** — legacy, stages wrap around it.
6. **Do NOT touch `src/education/`** — domain logic stays as-is unless wiring a ledger write.
7. **Privacy**: student names, student IDs, and observation text that could identify a child must NEVER appear in exported audit receipts. Hash or strip before export.
8. **MC reference files are for reading, not copying.** LV's architecture is different (FastAPI vs legacy HTTP handler, vanilla JS vs React, 3 source types vs 7). Adapt the concepts.

## MC Reference Files (in ~/fde/mission-canvas/)

Read these to understand the contracts, then adapt for LV:

- `src/sources/schema.py`, `src/sources/ledger.py` — Stage 1 reference
- `src/grounding/schema.py`, `src/grounding/build.py` — Stage 2 reference
- `src/actions/plan_schema.py` — Stage 3 reference
- `src/deliverables/schema.py`, `src/audit_receipts/schema.py`, `src/audit_receipts/builder.py` — Stage 4 reference
- `src/golden_workflows/schema.py`, `src/golden_workflows/runner.py` — Stage 5 reference
- `src/voice/stt.py` — Stage 6 reference
- `desktop/src/voice/capture.ts` — Stage 6 capture logic (adapt to vanilla JS)
- `.github/workflows/auto-release.yml` — Stage 0 reference

## Build Order

Build one stage at a time. Run the focused gate after each. Do not move to the next stage until the current one is green.

### Stage 0 — Auto-Release Workflow

Create `.github/workflows/auto-release.yml` adapted from MC's version:
- Test: `pytest -q tests/`
- Health: `python3 -m src.lingua_viva.cli health`
- Backend smoke: boot `src/web.py`, require `/api/health` 200
- Site pin: update `docs/index.html` tag reference
- Tag pattern: `desktop-v*`
- Package: `lingua-viva-desktop`

Gate: verify workflow file is valid YAML, references correct commands.

### Stage 1 — Source Ledger

Create `src/lingua_viva/sources/` package:
- `__init__.py`
- `schema.py` — `SourceRecord` dataclass with `source_type: local|drive|slack`, `student_data: bool` field. `student_data: true` → `model_context_allowed: false` for external. Deterministic IDs from `(source_type, source_id, container, record_id)`.
- `ledger.py` — NDJSON writer/reader at `~/.lingua-viva/sources/source_records.ndjson` + `source_observations.ndjson`. Dedup current, append-only observations.

Wire into:
- `src/lingua_viva/ingest.py` — filemap scans append SourceRecords
- `src/lingua_viva/google_drive_integration.py` — Drive list/import append SourceRecords
- `src/education/slack_bot.py` — observation capture appends SourceRecords with `student_data: true`

Update `src/web.py`:
- Update existing `GET /api/sources/status` to derive counts from ledger (dual-read fallback)
- Add `GET /api/sources/records?type=&limit=&q=`
- Add `GET /api/sources/observations?source_record_id=&limit=`

Update `static/index.html`:
- Add "Source ledger" expandable section under each source card in `renderSources()`

Create `tests/test_sources_ledger.py` — one fixture per source type, stable IDs, dedup, student_data flag.

Focused gate:
```bash
pytest tests/test_sources_ledger.py -q
python3 -m src.lingua_viva.cli health
python3 -m src.lingua_viva.cli preflight
```

### Stage 2 — Grounding Contract

Create `src/lingua_viva/grounding/` package:
- `schema.py` — `GroundingResult` dataclass. Tiers: `local → drive → slack → knowledge → external(blocked)`.
- `build.py` — Post-hoc builder from pipeline traces + source ledger. GIR via `claim_support_v1_heuristic`. External tier always `status: "blocked"` (local-first policy).

Update `src/web.py`:
- Add `grounding` field to the ask/query response

Update `static/index.html`:
- Show tier used + GIR in `renderGovernance()` evidence panel

Create `tests/test_grounding_result.py`

Focused gate:
```bash
pytest tests/test_grounding_result.py -q
python3 -m src.lingua_viva.cli health
```

### Stage 3 — Source-Backed Action Plan

Create `src/lingua_viva/action_plans/` package:
- `schema.py` — `ActionPlan` linking `grounding_id` + `source_record_ids` to action
- `store.py` — NDJSON at `~/.lingua-viva/actions/plans.ndjson`

Update `src/web.py`:
- `POST /api/action-plans/preview`
- `POST /api/action-plans/approve`
- `POST /api/action-plans/reject`
- `GET /api/action-plans/history`
- Update action execution to accept optional `action_plan_id`

Update `static/index.html`:
- Show plans with source badges and approve/reject in `renderActions()`

Create `tests/test_action_plans.py`

Focused gate:
```bash
pytest tests/test_action_plans.py -q
python3 -m src.lingua_viva.cli health
```

### Stage 4 — Deliverable + Audit Receipt

Create `src/lingua_viva/deliverables/` package:
- `schema.py` — `DeliverableRecord` (types: `parent_report|daily_file|assessment|drive_export|observation_export|none`)
- `store.py` — NDJSON at `~/.lingua-viva/deliverables/records.ndjson`

Create `src/lingua_viva/audit_receipts/` package:
- `schema.py` — `AuditReceipt` with `missing_join_keys`
- `builder.py` — Join source→grounding→action→deliverable. **CRITICAL**: strip/hash all student-identifiable data before building receipt. Never include student names, IDs, or raw observation text in exported receipts.

Update `src/web.py`:
- `GET /api/deliverables`
- `POST /api/audit-receipts/export`
- Migrate `/api/governance/observation-export` and `/api/governance/verify-pack` to call receipt builder internally

Update `static/index.html`:
- Add scope selector and incomplete badge to governance export in `renderGovernance()`

Create `tests/test_deliverables.py`, `tests/test_audit_receipts.py`

Focused gate:
```bash
pytest tests/test_deliverables.py tests/test_audit_receipts.py -q
python3 -m src.lingua_viva.cli health
```

### Stage 5 — Golden Workflows

Create `src/lingua_viva/golden_workflows/` package:
- `schema.py` — `GoldenWorkflowResult`
- `runner.py` — 5 education-specific workflows:
  - GW-EDU-001: Observation → student lens → parent report → Drive export
  - GW-EDU-002: Daily file from local + Drive → deliverable
  - GW-EDU-003: Teacher question → grounded answer → assessment
  - GW-DRIVE-004: Drive folder → import → answer → export back
  - GW-SLACK-005: Slack observation → source ledger → lens update

Each hermetic workflow exercises: SourceRecord → GroundingResult → ActionPlan → DeliverableRecord → AuditReceipt.

Add `lv golden-workflows` CLI command to `src/lingua_viva/cli.py` with `--hermetic`, `--live`, `--only`, `--json` flags.

Create `tests/test_golden_workflows.py`

Focused gate:
```bash
python3 -m src.lingua_viva.cli golden-workflows --hermetic
pytest tests/test_golden_workflows.py -q
```

### Stage 6 — Voice-First Local STT

Create `src/lingua_viva/voice_stt.py`:
- `WhisperLocalProvider` wrapping `faster-whisper` (CPU, int8, tiny model)
- Italian auto-detected by Whisper (no explicit lang override needed)

Update `src/web.py`:
- `POST /api/voice/stt` — accept audio blob, return transcript
- `GET /api/voice/probe` — runtime capability check

Update `desktop/electron/main.ts`:
- Add mic permission handler: `session.defaultSession.setPermissionRequestHandler`
- Add `faster-whisper` to pip deps
- Add voice model download to setup flow

Update `static/index.html`:
- In `voiceRuntime.toggleAsk()` and `voiceRuntime.toggleObserve()`: replace `SpeechRecognition` / `webkitSpeechRecognition` with:
  1. `navigator.mediaDevices.getUserMedia({ audio: true })`
  2. `new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })`
  3. Silence detection (2000ms threshold via AnalyserNode)
  4. `fetch('/api/voice/stt', { method: 'POST', body: audioBlob })`
  5. Transcript callback
- Keep Rime TTS as-is (already working with student-data gate)
- Keep barge-in: call TTS stop before starting capture

Add voice health checks to `lv health` in `src/lingua_viva/cli.py`

Create `tests/test_voice_stt.py` with `skipif not ffmpeg` guards.

Focused gate:
```bash
pytest tests/test_voice_stt.py -q
python3 -m src.lingua_viva.cli health
```

## Commit Convention

```
chore(meta): add auto-release workflow
feat(engine): Stage 1 — Source Ledger
feat(engine): Stage 2 — Grounding Contract
feat(engine): Stage 3 — Action Plans
feat(engine): Stage 4 — Deliverable + Audit Receipt
feat(engine): Stage 5 — Golden Workflows
feat(engine): Stage 6 — Voice-First Local STT
```

## After Each Stage

1. Run the focused gate
2. Run `pytest -q tests/` (full suite must stay green)
3. Commit
4. Move to next stage

## After All Stages

```bash
python3 -m src.lingua_viva.cli golden-workflows --hermetic
python3 -m src.lingua_viva.cli health
pytest -q tests/
git push origin main
```

If auto-release is built (Stage 0), a new desktop tag will be cut automatically. If not:
```bash
git tag desktop-v0.2.16
git push origin desktop-v0.2.16
```
