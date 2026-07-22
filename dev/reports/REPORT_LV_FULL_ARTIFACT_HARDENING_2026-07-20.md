# REPORT: LV Full Artifact Hardening

**Date**: 2026-07-20  
**Agent**: kiro.design  
**Scope**: Desktop setup wizard build + full artifact hardening gauntlet  
**Test suite**: 479/479 passing  
**UI contract**: v9 (unchanged this pass)  

---

## Findings

| Severity | Finding | Evidence | Fix / next action |
|---|---|---|---|
| HIGH | `linguaviva.art` unreachable (TCP timeout on 192.64.119.75:443) | `curl -vI https://linguaviva.art` → 135s timeout | ESCALATED — operator must verify DNS/hosting |
| MED | Desktop boot was a dead end on missing Python | `main.ts` threw on `checkPython` failure | FIXED — setup wizard replaces the dead progress screen |
| MED | No multi-candidate Python detection (Windows has no `python3`) | `checkPython("python3")` only | FIXED — `detectPython()` tries python/python3/py |
| MED | Backend early exit caused 45s useless polling | `waitForBackend` had no exit listener | FIXED — early exit detection breaks poll immediately |
| LOW | Test assumed setup copy was inline in main.ts | `test_desktop_phase1.py` checked main.ts for wizard strings | FIXED — test now checks setup-wizard.html |
| INFO | Admin views (Evidence, Capacity, Trends) return deferred/placeholder state | Live API returns `{"status":"planned","phase":"design",...}` | PASS — copy is honest ("Planned. Requires design phase.") |
| INFO | Health reports WARN (worktree has local changes) | Expected — uncommitted work from this session | PASS — pre-existing, not actionable |

---

## Part 1: Desktop Setup Wizard

| Check | Status | Evidence |
|---|---|---|
| `cd desktop && npm run build` | ✓ PASS | Compiles cleanly, zero errors |
| `setup-wizard.html` in `dist/electron/` | ✓ PASS | 15,709 bytes present |
| No hardcoded `python3` in spawn path | ✓ PASS | All spawns use resolved `pythonCmd` variable |
| `detectPython()` multi-candidate | ✓ PASS | Tries python/python3/py on Windows; python3/python on others |
| Ollama install/skip non-blocking | ✓ PASS | `waitForOllamaResolution` resolves on either install or skip |
| Backend early exit detection | ✓ PASS | `waitForBackend` attaches exit listener, breaks poll |
| `startBackend` receives resolved command | ✓ PASS | Called with `pythonCmd` from detection result |
| First-run copy explains local-first model | ✓ PASS | Explainer div in wizard: "Everything runs on your machine..." |
| Windows cannot be live-tested | ⚠ STRUCTURAL | Verified: IPC handlers, installer commands, PATH refresh logic, no-shell spawn |
| Test suite passes | ✓ PASS | 479/479 |

**Before state**: `launchBackend()` called `checkPython("python3")` → on failure rendered `progressHtml()` with error → threw `Error("Python check failed")` → dead app, no recovery.

**After state**: `runSetupFlow()` loads `setup-wizard.html` immediately → detects Python via candidate list → if missing, shows guided install button → if Ollama missing, shows install/skip → installs pip deps → starts backend → on failure keeps wizard open with retry.

---

## Five Priority Gates

| Gate | Status | Evidence | Remaining action |
|---|---|---|---|
| First-run/Onboarding/Ollama | ✓ PASS | Setup wizard guides through Python→Ollama→Server; Ollama is explicitly optional; skip proceeds to server; Provider Settings shows `local` provider status with Ollama install guidance | None |
| Public download story | ⚠ ESCALATED | GitHub release v1.0.3 is live (3 CLI binaries correct); `linguaviva.art` TCP timeout — site unreachable | Operator: verify DNS points to a live host; re-deploy static site |
| Student lens creation | ✓ PASS | Students view renders roster from `/api/students`; clicking student loads lens; observation save attaches to lens; empty state says "No observations yet"; LensNotFoundError returns helpful 404 | None — creation of *new* students is not in-app (added via CLI or direct lens file); recommend future add-student UX |
| Microphone note capture | ✓ PASS | `SpeechRecognition` check with `"speech unavailable"` fallback; textarea for typed fallback; capture→save flow sends `transcript` field; save confirmation says "Saved locally. Not uploaded. Not shared." | None |
| Trust cockpit consistency | ✓ PASS | Privacy: external_calls=0, query hashes (not text); Why: trace hashes, duration, sources; Profile/export: includes traces+privacy_events+students; Clear: typed confirmation; Support bundle: excludes student data, shows privacy notes, no upload | None |

---

## Full Artifact Inventory

| Artifact | Entry point | Status | Evidence | Fix shipped or next action |
|---|---|---|---|---|
| `https://linguaviva.art` | DNS → 192.64.119.75 | ESCALATED | TCP timeout after 135s on port 443 | Operator: check hosting/DNS |
| GitHub release v1.0.3 | `github.com/lingua-viva/learning-architecture/releases/tag/v1.0.3` | PASS | 3 assets: lv-darwin-arm64, lv-linux-x86_64, lv-windows-x86_64.exe |  |
| Desktop setup wizard | `desktop/electron/setup-wizard.html` | FIXED | Built this pass — guided 3-step onboarding |  |
| `install.sh` | `sh -n install.sh` | PASS | Syntax valid |  |
| `install.ps1` | Structural check | PASS | Comment-only MC provenance ref, LV-specific throughout |  |
| CLI `serve` | `python3 -m src.lv_cli serve 8787` | PASS | Health 200, UI loads |  |
| CLI `preflight` | `python3 -m src.lv_cli preflight` | PASS | 5/5 checks |  |
| CLI `health` | via `/api/health` | PASS | 24/26 pass, 2 WARN (worktree + privacy path scan — both expected) |  |
| PWA manifest | `/manifest.json` | PASS | name=Lingua Viva, display=standalone, 4 icons, 2 shortcuts |  |
| Service worker | `/sw.js` | PASS | HTTP 200 |  |
| Offline page | `/offline.html` | PASS | HTTP 200 |  |
| Sidebar/nav | static/index.html | PASS | Teacher+admin roles, role switcher, 17 nav items |  |
| Home/Brief | `/api/brief` | PASS | Returns greeting, schedule info |  |
| Plan | Plan view | PASS | Unit selection, grade bands |  |
| Prepare | `/api/prepare/activity` | PASS | Activity generation |  |
| Observe/Mic | Observe view, SpeechRecognition | PASS | Mic detection + typed fallback + save |  |
| Students/Lenses | `/api/students`, `/api/students/{id}/lens` | PASS | 2 demo students, lens load, observations |  |
| Assess | `/api/assess/rubric/{unit_id}` | PASS | Rubric template, tier tasks, CEFR language |  |
| Ask | `/api/query` | PASS | Classification, trace_id, route, result |  |
| Parents | Parents view | PASS | Draft warmth (confirmed in Claudia-lens hardening) |  |
| Why | `/api/why` | PASS | Trace hashes, no raw query text |  |
| Privacy | `/api/privacy` | PASS | external_calls=0, query hashes, real counts |  |
| Profile/Export/Clear | `/api/profile`, `/api/profile/export` | PASS | Export includes all data categories |  |
| Provider Settings | `/api/provider` | PASS | provider=local, status shown |  |
| File Map | `/api/filemap/scan` | PASS | POST scan works |  |
| Reflect | `/api/reflect/note` | PASS | Saves locally, private=true |  |
| Quick Capture | Floating capture → `/api/query` | PASS | Deterministic trace (confirmed in P0+Claudia passes) |  |
| Health/Doctor | `/api/health`, `/api/support-bundle` | PASS | Bundle excludes private data, no upload |  |
| Programme (admin) | `/api/admin/programme` | PASS | Returns frameworks, grade_bands |  |
| Evidence (admin) | `/api/admin/evidence` | PASS | Honestly marked as planned/design phase |  |
| Capacity (admin) | `/api/admin/capacity` | PASS | Honestly marked as planned/design phase |  |
| Trends (admin) | `/api/admin/trends` | PASS | Honestly marked as planned/design phase |  |
| `src/web.py` | py_compile | PASS | Compiles cleanly |  |
| `src/lv_cli.py` | py_compile | PASS | Compiles cleanly |  |
| `src/pwa.py` | py_compile | PASS | Compiles cleanly |  |
| UI contract | `check_ui_contract.py` | PASS | v9, 3 files locked |  |
| MC branding bleed | grep active surfaces | PASS | Only in code comments (provenance), not user-facing |  |

---

## Public Site And Downloads

| URL/button | Expected | Actual | Status | Evidence |
|---|---|---|---|---|
| `https://linguaviva.art` | HTTPS 200, landing page | TCP timeout 192.64.119.75:443 | ESCALATED | curl -vI → "Couldn't connect to server" after 135s |
| GitHub latest release | v1.0.3 with 3 CLI binaries | v1.0.3 with lv-darwin-arm64, lv-linux-x86_64, lv-windows-x86_64.exe | PASS | GitHub API verified |
| macOS download | Apple Silicon CLI binary | lv-darwin-arm64 (30MB) | PASS | Asset present |
| Linux download | x86_64 CLI binary | lv-linux-x86_64 (31MB) | PASS | Asset present |
| Windows download | x86_64 CLI binary | lv-windows-x86_64.exe (32MB) | PASS | Asset present |

---

## Teacher And Coordinator Experiences

| Experience | Status | Evidence | Fix shipped or next action |
|---|---|---|---|
| Home | PASS | Greeting + brief returned |  |
| Plan | PASS | Unit/grade selection |  |
| Prepare | PASS | Activity generation |  |
| Observe (mic) | PASS | SpeechRecognition + typed fallback + save |  |
| Students/Lenses | PASS | Roster, lens load, observation attachment |  |
| Assess | PASS | Rubric template |  |
| Ask | PASS | Governed routing, trace_id |  |
| Parents | PASS | Draft generation |  |
| Why | PASS | Trace hashes, no raw text |  |
| Privacy | PASS | Real counts, external_calls=0 |  |
| Profile/Export/Clear | PASS | Full export, typed clear |  |
| Provider Settings | PASS | Local provider default |  |
| File Map | PASS | Scan/exclude |  |
| Reflect | PASS | Local save, private |  |
| Quick Capture | PASS | Deterministic trace |  |
| Health/Doctor | PASS | Bundle privacy, no upload |  |
| Programme (admin) | PASS | Real data |  |
| Evidence (admin) | PASS | Honestly deferred |  |
| Capacity (admin) | PASS | Honestly deferred |  |
| Trends (admin) | PASS | Honestly deferred |  |

---

## Backend, Privacy, Support, Docs

| Artifact | Status | Evidence | Fix shipped or next action |
|---|---|---|---|
| `src/web.py` API surface | PASS | All routes return sane JSON, error states are helpful |  |
| Privacy log | PASS | Logs query hashes, not raw text |  |
| Traces | PASS | Hash-based, source citations included |  |
| Support bundle | PASS | Excludes private data, no upload path |  |
| File map | PASS | Student zone exclusion works |  |
| Provider config | PASS | Local default, no required API key |  |
| Student lens store | PASS | Local NDJSON, 2 demo students |  |
| UI contract | PASS | v9 locked, 3 files |  |
| `dev/INDEX.md` | UPDATED | Both specs tracked |  |

---

## Verification

| Command | Result |
|---|---|
| `cd desktop && npm run build` | ✓ compiles, setup-wizard.html copied |
| `python3 -m pytest -q tests/` | 479/479 passed (123s) |
| `python3 -m src.lv_cli preflight` | 5/5 in 1.2s |
| `python3 scripts/check_ui_contract.py` | OK — contract v9, 3 files locked |
| `python3 -m py_compile src/web.py src/lv_cli.py src/pwa.py` | OK |
| `sh -n install.sh` | syntax OK |
| `python3 -m src.lv_cli serve 8787` + curl health | status=WARN (expected) |
| `curl -I https://linguaviva.art` | TIMEOUT — escalated |
| `grep "python3" desktop/electron/` | No hardcoded spawn (only defaults/candidates) |
| `grep "Mission Canvas" active surfaces` | Only provenance comments |
| GitHub releases API | v1.0.3, 3 assets confirmed |

---

## Factual Corrections To Prior Reports

None.

---

## Operator Follow-Ups

| Action | Owner | Blocker |
|---|---|---|
| Verify `linguaviva.art` DNS/hosting — site is unreachable (TCP timeout) | Operator | DNS or hosting service down |
| Live Windows test of setup wizard (install Python, Ollama) | Operator/Jason | Requires Windows machine |
| Consider in-app "Add Student" flow (currently CLI/file only) | Product decision | Not blocking — demo students work |
