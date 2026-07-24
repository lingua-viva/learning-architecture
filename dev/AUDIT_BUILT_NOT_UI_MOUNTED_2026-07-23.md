# AUDIT: Built But Not UI-Mounted (Lingua Viva)

**Status**: REFERENCE — answers one question: *"Of everything genuinely built in this repo, what
would a teacher never encounter just by using the desktop app, and why won't a release-automation
pipeline fix it?"*
**Companion**: `mission-canvas/dev/AUDIT_BUILT_NOT_FIXED_BY_RELEASE_AUTOMATION_2026-07-23.md` (the
sibling audit on MC, same methodology, same day) and
`mission-canvas/dev/MC_SYSTEM_THING_OUTCOME_TAXONOMY_2026-07-15.md` (the shared System taxonomy —
LV's `DLV-PRC-008..013` rows already live in that same document's §13, so the taxonomy is treated
as cross-repo, not MC-only).

## Why this list exists

Same distinction as the MC audit, restated for LV: **delivery-pipeline bugs** (code doesn't reach
the packaged binary — stale tag, missing `extraResources`, wrong write path, crash-looping
backend) are a different bug class from **mount-verification bugs** (code is correctly bundled and
running, but no button, form, or nav item in the actual served page ever calls it). LV's own
`DLV-PRC-008..013` rows (`MC_SYSTEM_THING_OUTCOME_TAXONOMY_2026-07-15.md` §13) already document
five real delivery-pipeline incidents from the 2026-07-22 desktop-onboarding hardening pass — all
fixed. This document is the other class: things that are *already inside the running app* and
still invisible to a user, verified by tracing the real render chain end to end —
`desktop/electron/main.ts:186` (`window.loadURL(BACKEND_URL)`) → `http://127.0.0.1:8787` → FastAPI
root route in `src/web.py` → the single 1914-line `static/index.html` it returns, with every
finding below confirmed by grepping for the literal endpoint string as a `fetch()`/form-action call
site inside that exact file, not by trusting spec status lines (which, separately, were found stale
for the 4 newest 2026-07-23 specs — see note at bottom).

LV's architecture is much flatter than MC's (single inline-JS page, no separate dead module
directory like `desktop/src/sidebar/`), so the shape of this class of bug here is different: not
"a whole subsystem was built and never imported," but "an endpoint was built, tested, and correctly
served — and no UI control was ever wired to call it." 12 of LV's 44 backend routes fall into this
category (~27%, vs. MC's ~80% experience-reachability gap — LV's flatter single-page design
structurally caps how large this gap can get, but it is not zero).

## Table

| ID | What | Path | System(s) | Artifact(s) touched | Why release automation doesn't fix it |
|---|---|---|---|---|---|
| LV-BLT-001 | External LLM provider connect/disconnect (OpenAI/Groq/Mistral key entry, verification, storage, deletion) — full backend flow, built explicitly for a "Gap 5a onboarding screen" per its own docstring. Settings only reads status (`GET /api/provider`); no key-entry form or Connect/Disconnect button exists anywhere, including the setup wizard. | `src/web.py:1405` (connect), `:1435` (disconnect), `src/provider_config.py` (116 lines, tested) | RTG (Model/Provider Routing), SRF (Surfaces) | Session Snapshot (the connection state itself never becomes visible/editable) | The route works correctly once the app is running — verified logic, has tests. Packaging/signing/tagging ships this exact working-but-uncallable code faithfully; the gap is a missing form, not a missing build. |
| LV-BLT-002 | PDF/document ingestion endpoint — 50MB size guard, PII-redaction hook via `src.lingua_viva.ingest.ingest_document`. No `<input type=file>` or upload control anywhere in `static/index.html`; only reachable via direct HTTP call or the `lv ingest` CLI. | `src/web.py:1585-1660` | KNW (Knowledge/Evidence), SRF | Source Set | Same — the endpoint is live and correct; no upload widget was ever built in the served page. |
| LV-BLT-003 | Teacher-style ingest/holdout — the actual mechanism behind "My Teaching Style." Profile UI literally instructs the teacher to "Ingest past teaching artifacts to build your style profile" but provides no form, button, or file picker to do so. Only reachable via raw API call or its own test file. | `src/web.py:837` (ingest), `:859` (holdout), consumed nowhere in `static/index.html:1438-1457` (`renderTeachingStyle`, read-only) | PRO (Professional Context), SRF | Project State (the teaching-style lens the UI promises but can't build) | This is the sharpest finding in the list — the UI text describes a capability, the capability exists and works, and the UI gives the user zero way to invoke it. Not a packaging defect: the missing piece is a form that calls an already-correct endpoint. |
| LV-BLT-004 | WebSocket `/ws` + query broadcaster — real-time push infrastructure threaded through `/api/query`, with zero subscribers. The "Ask" feature works only because the same HTTP response also returns synchronously; the broadcast side has no listener anywhere in the served page. | `src/web.py:1673-1689` (endpoint), broadcast call sites at ~1460/1526/1536/1546/1551 | OBS (Observability/Audit), SRF | None (infrastructure only) | uvicorn serves `/ws` correctly under any build; no client code was ever written against it. A cleaner build doesn't create a WS client. |
| LV-BLT-005 | Electron IPC bridge — half the exposed `window.lvDesktop` surface (`notify`, `onBackendReady`) has zero call sites in the page that's actually loaded (`static/index.html`); only the separate first-run `setup-wizard.html` uses a different subset. `main.ts:187` fires a `lv:backend-ready` IPC event into a page that never registers a listener for it — broadcast into the void. | `desktop/electron/preload.ts`, `desktop/electron/main.ts:187,440-448` | SRF | None | The IPC channels are correctly registered on the main-process side and would function if invoked — the renderer simply never calls them. No signing/tagging change touches renderer-side JS logic. |
| LV-BLT-006 | 6 backend routes with zero UI call sites, each superseded or duplicated by a route that IS wired: `GET /api/curriculum/unit/{unit_id}` (UI uses the grade-level route instead), `PUT /api/students/{id}/rti` tier-change (UI only wires the separate confirm/defer route), `GET /api/students/{id}/lens-as-of` (no date-picker control exists), `GET /api/teacher/today` and `GET /api/students/unobserved` (both duplicated by `/api/brief`, which Home actually uses), `GET /api/session` (orphaned). | `src/web.py:426,437,1081,1154,1177,1388` | SRF, WKF (Product Workflows) | Varies by route — none reach the user | Mechanically confirmable via source-level grep against the fully-served page; no build/release step could fix a call site that was never written in the frontend. |
| LV-BLT-007 | `GET /api/stats` — returns the exact system-health numbers (`ontology_nodes`, `domains`, `knowledge_entries`, `citations`, `path_records`, `gap_signals`) that `MANIFEST.yaml` reports. Zero references anywhere in `static/index.html`. Likely built for an admin/debug screen that was never added to any of the three nav arrays (`teacherNav`/`adminNav`/`utilityNav`). | `src/web.py:1367` | ONT (Classification/Ontology), KNW, SRF, OBS | None — this is precisely the artifact that would let anyone (teacher, coordinator, or you) *see* the system's own scale/health inside the app, and it doesn't surface | Endpoint correct and live; there is no dashboard element anywhere that renders it. Ships faithfully, unreachable, in every build. |
| LV-BLT-008 | Extract-fill-verify engine — per `dev/specs/SPEC_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md`, SHIPPED + 15-round hardened, safety invariant held across all rounds. Real, tested backend module. No UI entry point anywhere in `static/index.html` triggers an extraction/fill/verify flow on an uploaded document — it sits behind the same missing-upload-control gap as LV-BLT-002. | `src/lingua_viva/extraction_engine.py` (per spec; module not independently re-verified by path in this audit) | KNW, EXE (Action/Execution) | Evidence Pack, Draft Deliverable (the extracted/verified content that would populate Student Lens / Curriculum Unit schemas) | The engine itself is hardened and correct per its own 15-pass loop; the gap is identical to LV-BLT-002/003 — no upload/trigger control exists in the served page. A release pipeline ships the engine exactly as faithfully as everything else. |
| LV-BLT-009 | No knowledge/ontology browser anywhere in the UI. The only place any of the 111 ontology nodes / 25 domains / 178 knowledge entries (per `MANIFEST.yaml:9-16`) surface to a user is one `classification_domain` string per past query in the "Why" trace view — never a list, never all 25 domains, never browsable. | `static/index.html:1356` (Why view), absence of any explorer view | ONT, KNW, SRF | None — same gap as LV-BLT-007, stated at the structural/aggregate level rather than the single-endpoint level | This is a missing UI surface, not a packaging defect — the ontology/knowledge engine itself is correctly bundled and functioning (it answers queries correctly); nothing about signing or tagging creates a browser view that doesn't exist. |

## Non-findings (verified live, not over-reported)

Checked and confirmed correctly wired, so **not** included above:
- Sidebar/nav (`SPEC_LV_SIDEBAR_DESIGN_2026-07-20.md`, `ADDENDUM_THREE_TIER_SIDEBAR_2026-07-16.md`)
  — `teacherNav`/`adminNav`/`utilityNav` (`static/index.html:723-745`) render through real click
  handlers with role-swap logic. No `.slice(0,4)`-style truncation exists anywhere in this file —
  MC's specific sidebar-cap bug (`Sidebar.tsx:43`) has no LV analog.
- File-map / trust UI (Settings view, `:1482-1803`) — scan, confirm, peek, assign, exclude, clear
  all correctly call their matching backend routes.
- Voice — real browser `SpeechRecognition`/`SpeechSynthesis` wired directly into the Ask and
  Observe views (`voiceRuntime` object). Not eval-only, not a separate unmounted bridge module —
  MC's voice-has-zero-UI-hook finding has no LV analog either.
- Curriculum, Student Lens, Observe, Assess, Parents, Slack integration, Admin (evidence/capacity/
  trends deliberately gated as "coming soon" pending pilot data, not silently broken) — all
  confirmed live with real nav entries and wired API calls.
- Logo — `static/index.html` (the file the desktop app actually loads) uses a text "LV" mark, not
  an `<img>`. This is *not* MC's broken-reference case (nothing points at a missing file); LV simply
  never adopted an image logo in-app. Softer finding, no ID assigned.

## Separate housekeeping note (not a mount-verification bug, flagging anyway)

Four of LV's newest specs (all dated 2026-07-22/23 — `SPEC_LV_OBSERVATION_IEP_CLASSIFICATION_
WRITE_PATH`, `SPEC_LV_STUDENT_LENS_JSON_V2_SCHEMA`, `SPEC_LV_GOOGLE_DRIVE_CONNECTOR`,
`SPEC_LV_SLACK_APP_INTEGRATION`) are missing from `dev/INDEX.md` entirely — LV's own designated
single source of truth for spec status. Of these, the first two are genuinely `SPEC-ONLY-NOT-BUILT`
(foundation schema spec for a 5-part chain hasn't been built, so nothing downstream exists yet —
correctly out of scope for this table, which only covers things that ARE built), Slack is
`REACHABLE`/correctly built and wired, and Google Drive connector has no corresponding source file
anywhere. This isn't a mount gap — it's `INDEX.md` itself being stale for the most recent work —
but it means don't trust `INDEX.md` status lines for anything dated 2026-07-22 or later without
spot-verifying, same caution that applied when reading MC's docs this session.

## Read this table as

A correctly-functioning release pipeline for LV (were the same automation pattern from
`mission-canvas/dev/SPEC_DESKTOP_RELEASE_AUTOMATION_2026-07-23.md` applied here) would tag, build,
and ship every row above exactly as reliably as anything else — a smoke test that checks
boot-cleanliness and import-cleanliness doesn't know or care whether a `fetch()` call was ever
written against a given endpoint. Fixing these requires targeted frontend work in
`static/index.html`: a provider key-entry form (LV-BLT-001), a document upload control that also
closes LV-BLT-002/008, a trigger button for the ingest/holdout flow (LV-BLT-003), and — lowest
priority, since nothing user-facing depends on it — either wiring or deleting the dead routes
(LV-BLT-004/005/006) and adding an admin stats/knowledge view (LV-BLT-007/009). None of this is in
scope for release automation, and none of it should block that work — independent bug classes,
independent fixes, same conclusion as the MC audit.
