# REPORT: Built-to-Shipped Sync — Track B (2026-07-25)

Spec: `mission-canvas/dev/SPEC_LINGUA_VIVA_EXTERNAL_FEEDBACK_AND_APP_SYNC_2026-07-25.md` §3.
Executed at HEAD `3dde2a4`. Companion (Track A):
`REPORT_LV_EXTERNAL_FEEDBACK_TRANSFER_2026-07-25.md`.

**Nothing committed** — LV's operator holds the only commit window. All changes staged
and reported here. Teachers open the app Monday 2026-07-27; the lens applied throughout
was "does the built thing actually reach Claudia's hands?"

## 1. Route-reachability re-audit (vs the 07-23 LV-BLT baseline)

Fresh runs, both green:

- `lv preflight` (source-level): **6/6** — ui_contract, golden_parses (36), imports,
  ontology (111 nodes), no_conflicts, route_reachability.
- `scripts/check_route_reachability.py`: **64 routes classified — 56 reachable,
  8 backend-only, 4 deferred_undecided** (after this session's manifest fix; was
  reported 53/11/7 before it).

### Diff against `AUDIT_BUILT_NOT_UI_MOUNTED_2026-07-23.md` (LV-BLT-001..009)

**Shipped and reachable (closed since the audit):**

| ID | Status | Evidence |
|---|---|---|
| LV-BLT-001 provider connect/disconnect | **CLOSED** (ff2401e) | Settings form wired: `static/index.html:1903` (connect), `:1920` (disconnect) |
| LV-BLT-003 teaching-style ingest | **CLOSED (ingest half)** (ff2401e) | My Teaching Style form: `static/index.html:1757` |
| LV-BLT-006 six dead routes | **CLOSED** | `GET /api/teacher/today` + `GET /api/students/unobserved` removed from `src/web.py` (d1b1846, unobserved-removal spec); `PUT .../rti` mounted; `unit/{id}`, `lens-as-of`, `session` reclassified `permanent` with evidence |
| LV-BLT-007 `/api/stats` | **CLOSED** (0b809c9) | Health view + Knowledge browser: `static/index.html:1573`, `:2490` |
| LV-BLT-008 extract-fill-verify | **CLOSED (UI trigger)** | `/api/extraction/{sources,run,review}` all UI-reachable (7ddf6bf review modal) |
| LV-BLT-009 knowledge/ontology browser | **CLOSED** (57ae72b) | `/api/ontology/domains` wired: `static/index.html:2491` |

**Deferred by design (still backend-only, correctly classified, reasons on file):**

- `POST /api/slack/events` — Slack's servers call it, never the teacher UI (`permanent`).
- `GET /api/students/{id}/lens-as-of`, `GET /api/curriculum/unit/{id}`,
  `GET /api/session` — `permanent`, evidence-based reclassifications from the
  mount-fix series.
- LV-BLT-004 `WS /ws` — `deferred_undecided`, awaiting the delete-vs-build-vs-permanent
  operator call (MC-fork debug console, zero teacher value today).
- LV-BLT-002 `POST /api/ingest` — `deferred_undecided`; still no upload control.
  **This is now the sharpest remaining teacher-facing gap**: the injection guard built
  in Track A protects this exact path, and extraction (LV-BLT-008) is UI-triggerable,
  but a teacher still cannot upload a document from inside the app.
- LV-BLT-003 holdout half (`POST /api/teacher/holdout`) — `deferred_undecided`,
  eval-harness-only; reason text updated this session to stop pointing at the
  now-wired ingest route.
- `GET /api/categories` — `deferred_undecided`, new since the baseline (surfaced by
  the 07-23 evening rebase), no product decision yet.
- LV-BLT-005 Electron IPC (`window.lvDesktop` `notify`/`onBackendReady`) — unchanged,
  zero renderer call sites in `static/index.html` (re-verified by grep today). Not
  route-manifest-tracked; harmless but dead.

**Deferred by oversight — found and fixed this session:**

1. **`contracts/ROUTE_REACHABILITY.yaml` was factually wrong for 3 routes.**
   `POST /api/provider/connect`, `POST /api/provider/disconnect`, and
   `POST /api/teacher/ingest` were wired into the UI by ff2401e (2026-07-23 19:49)
   but still classified `intentionally_backend_only`/`deferred_undecided` — the
   manifest update lane (5b72fb2, same evening) missed them. Reclassified to
   `reachable_from_ui` with verified call-site literals; checker re-run green
   (56/8/4), `route_reachability` + `ui_contract` test groups 16/16.
2. **Root cause, flagged not built: the checker is one-directional.**
   `scripts/check_route_reachability.py` proves every `reachable_from_ui` entry's
   call-site literal still exists, but for `intentionally_backend_only` entries it
   validates only status+reason — it never checks that a call site *doesn't* exist.
   Any route wired into the UI after being classified backend-only passes silently
   (exactly what happened here). A reverse-direction grep (fail if a backend-only
   route's path literal appears in `static/index.html`) would close this. Left as an
   operator-approvable follow-up — touching the gate script 2 days before Monday was
   judged out of scope.

**Routes added since 07-23 without manifest entries: zero** — the gate enforces this
mechanically (unclassified route = exit 1) and it passed before any of today's edits.

## 2. dev/INDEX.md refresh

The spec's two claims, verified before editing:

- **Install/release hardening "shows DRAFT"** — already corrected before today
  (shows SHIPPED with evidence; `tests/test_install_hardening.py` +
  `tests/test_install_launcher_scripts.py` both exist). No edit needed; spec claim
  was stale.
- **Claudia-Lens Repass "shows DRAFT"** — confirmed wrong and **fixed**: the review
  pass ran 2026-07-20 (`REPORT_LV_CLAUDIA_LENS_REPASS_2026-07-20.md`, 18 experiences
  live-checked) and its findings shipped via the hardening pass. Verified live:
  `src/education/parent_report.py` exists, `static/manifest.json` carries LV-native
  shortcuts. Status now EXECUTED with correction note.

**4 missing 07-22/23 specs added** (statuses verified against live code, not spec
status lines):

| Spec | Status recorded | Verification |
|---|---|---|
| SPEC_LV_SLACK_APP_INTEGRATION_2026-07-22 | SHIPPED (Implemented MVP) | `GET /api/slack/status` UI-reachable; 15-pass hardening report on file |
| SPEC_LV_STUDENT_LENS_JSON_V2_SCHEMA_2026-07-23 | SHIPPED (`f3dc10a`/`7ddf6bf`) | `support_profile_default()` + normalization live in `src/education/student_lens.py:249-285` |
| SPEC_LV_OBSERVATION_IEP_CLASSIFICATION_WRITE_PATH_2026-07-23 | SHIPPED (`f3dc10a`) | 1257-insertion commit: capture pipeline, web routes, Observe UI, 271 lines of tests |
| SPEC_LV_LENS_UI_API_CONTRACT_2026-07-23_GAGNE_REVISION | SHIPPED (folded into spec 3) | Revision doc of the already-SHIPPED Lens UI/API contract spec |

Also added both of today's reports to the Reports table.

## 3. Desktop v0.2.8 content check

**PASS — v0.2.8 contains every 07-22/23 demo-readiness fix.**

- Tag `desktop-v0.2.8` → `eeb0f5c` (2026-07-23, after 57ae72b), which includes: the
  5-spec sequence (7ddf6bf), observation write path (f3dc10a), provider +
  teaching-style forms (ff2401e), stats mount (0b809c9), knowledge browser (57ae72b),
  and the desktop ontology packaging fix.
- GitHub release published **2026-07-24T06:50Z**, `prerelease: true` (correct — keeps
  the CLI's "latest" slot for `install.sh`), all 3 assets present:
  `LinguaViva.dmg`, `LinguaViva-Setup.exe`, `LinguaViva.AppImage`.
- Only `3dde2a4` (mc push — dev tooling, no app code) and today's uncommitted Track A
  work postdate the tag.

**Spec correction (release automation):** the spec's step "flag the missing
tag-triggered auto-release equivalent" is based on a stale premise — LV already has
`.github/workflows/desktop-release.yml` (triggered on `desktop-v*` tags, adapted from
MC's, with signing/notarization secrets wired) plus `release.yml` (`v*` CLI tags),
`install-test.yml`, and `check-signing-secrets.yml`. Nothing to flag as missing; the
v0.2.8 release itself is the proof it works end to end.

## 4. What today's uncommitted work means for shipping

After the operator's commit window, reaching teachers requires:

1. **Commit** (operator-only) — injection guard + wirings, `lv candidates`, 38 new
   tests, manifest fix, INDEX refresh, 2 reports.
2. **CLI**: new `v1.0.x` tag → `release.yml` rebuilds `lv` binaries (the installed
   `~/.local/bin/lv` is compiled v1.0.3 and lacks `lv candidates`).
3. **Desktop**: `desktop/package.json` version bump + new `desktop-v0.2.9` tag →
   `desktop-release.yml`. The injection guard rides along automatically (it lives in
   `src/`, which ships via `extraResources`).

None of these steps were performed — all are operator-window actions.

## 5. Final regression run

Baseline (pre-change, this session): **704 passed, 13 skipped** — matched the spec's
expected baseline exactly.

Final full-suite run after both tracks: **742 passed, 13 skipped in 272s** — exactly
baseline (704) + the 38 new tests, zero regressions, zero new skips.

## 6. Files touched this session (all uncommitted, staged for the operator)

- `src/lingua_viva/injection_guard.py` — new (Track A item 2)
- `src/education/document_parser.py`, `src/lingua_viva/extraction_engine.py`,
  `src/pipeline.py` — injection guard wirings
- `src/lingua_viva/cli.py` — `lv candidates` subcommand (Track A item 3)
- `tests/test_injection_guard.py` (34), `tests/test_cli_candidates.py` (4) — new
- `contracts/ROUTE_REACHABILITY.yaml` — 3 stale entries reclassified + holdout reason
  corrected
- `dev/INDEX.md` — 1 status fix, 4 missing specs added, 2 reports added
- `dev/reports/REPORT_LV_EXTERNAL_FEEDBACK_TRANSFER_2026-07-25.md` — Track A record
- `dev/reports/REPORT_BUILT_TO_SHIPPED_SYNC_2026-07-25.md` — this report

**Deliberately left UNSTAGED — pre-existing modifications not from this session,
isolate before committing** (per the shared-repo concurrent-sessions discipline):

- `dev/specs/SPEC_LV_INGESTION_EXTRACTION_MAPPING_V2_2026-07-23.md` — a 551-line
  Gagné-revision expansion from another lane (adds "§0 Gagné Learning Engineering
  Summary" + Nine-Events coverage table). Unattributed; verify against its lane
  before trusting.
- `desktop/package-lock.json` — lockfile drift from a local `npm install`
  (`version: 0.1.0 → 0.2.7`, ~1655 lines). Harmless-looking but not this session's
  work.
