# REPORT — Full-System Wiring Audit — 2026-08-08

- **HEAD at audit**: `e239b12` (`chore(release): pin desktop-v0.2.46`, == origin/main)
- **Mode**: AUDIT ONLY — no code changes, no fixes. Every claim carries file:line. "Cannot tell" is first-class.
- **Method**: each load-bearing conclusion verified with two differently-shaped instruments (static grep/trace + live runtime probe), per the audit prompt's rules.

---

## STEP 0 — Harness Reconciliation

**Question**: prompt claimed the on-disk JSON showed 73.7% / 5 P0s while the MD showed 84.2% / 16 passed.

**Finding: the discrepancy does not exist on disk today.**

- `~/.lingua-viva/reports/TEACHER_READINESS.json` and `.md` agree exactly at every run observed this session (both at `c4b2e4a`, preserved to `/tmp/tr-c4b2e4a.{json,md}`, and at HEAD `e239b12`, preserved to `/tmp/tr-e239b12.{json,md}`).
- The 73.7%/5-P0 artifact is not on disk anywhere (searched `~/.lingua-viva/reports/`, `dev/reports/`). Most likely a **stale pre-move artifact**: the write-location seal (`e2ecb4b`) moved harness output from `dev/reports/` to `~/.lingua-viva/reports/`, and each run overwrites the single file pair. **CANNOT-TELL** what that JSON contained — it was overwritten before this audit began.
- **Instrument gap this exposes (P2)**: the harness keeps no run history. One file pair, overwritten per run — any regression between runs is unrecoverable.

**Fresh run at HEAD `e239b12`** (started 2026-08-09T04:54:00Z, 312s):

| Metric | Value |
|---|---|
| Readiness | **84.2% (16/19)** |
| Fails | C8 (P1, `expected_fail: false`), C9 (P1, expected), C10 (P0, expected) |

C8 evidence: `{"duration_ms": 60435, "capture_status": 200, "materials_status": 422, "materials_error": "generation_failed"}` — root-caused in §6.

---

## 1. Role Walks

**Premise correction**: the prompt asked for Teacher/Parent/Student walks. **There are no Parent or Student surfaces.** The role selector offers exactly two roles — `data-role="teacher"` and `data-role="coordinator"` (static/index.html:774-775). Role choice is client-side only (localStorage, index.html:1556-1563). `ROLE_HIERARCHY` has no parent/student entries (src/lingua_viva/access_roles.py:28-33). Parents receive material only through the teacher-mediated copy/print exits (Student Summary finish, no send mechanism by design). Students have no login and no surface.

### Teacher walk (teacherNav, index.html:1454-1463) — all WIRED

| View | Renderer | Primary routes (all verified live in src/web.py) |
|---|---|---|
| Daily | renderDaily :6070 | `/api/daily/briefing`, `/api/ops/daily`, `/api/ops/records`, `/api/ops/setup/*`, `/api/ops/staffing-summary`, `/api/slack/ops/status` |
| Plan | renderPlan :1714 | `/api/curriculum/grade/{g}` |
| Prepare | renderPrepare :1757 | `/api/lesson-materials/{generate,today,roster-split,packet/preview,packet/approve,library,library/pull}`, `/api/actions/registry` |
| Observe | renderObserve :2114 | `/api/observe/capture`, `/api/observe/classify`, `/api/students/growth` |
| Students | renderStudents :2443 | `/api/students`, `/api/students/{id}`, `/api/students/ingest*` |
| Assess | renderAssess :3267 | `/api/assess/rubric/{g}` |
| Ask | renderAsk :3301 | `/api/ask`, `/api/query`, `/api/query/stream` |
| Summaries | renderParents :3865 | `/api/parents/recommendation`, `/api/action-plans/*`, `/api/governance/trust`, `/api/audit-receipts/export`, `/api/deliverables` |

Ask → pipeline verified with a second instrument: live TestClient probe of `POST /api/query` returned `pipeline.steps` containing 7 of 8 pipeline stages (§3).

### Coordinator walk (adminNav, index.html:1468-1474) — all WIRED

`programme`, `evidence`, `capacity`, `trends` all fetch through the **dynamic call site** `/api/admin/${state.view}` (index.html:7099; programme also direct at :7090); `knowledge` uses `/api/ontology/domains`, `/api/query`, `/api/stats` (renderKnowledge :7185).

### The real boundary

- Server binds `127.0.0.1` only (src/web.py:7343).
- `LV_AUTH_MODE` defaults to `off` → the role-gate middleware returns early (web.py:87-88) and every request is treated as `admin` (access_roles.py:71).
- **Consequence**: any process on the machine can read all student data regardless of the UI's role toggle. The trust boundary is *the machine*, not the role. This matches the local-first design but must be stated plainly: the role selector is UX shaping, not access control, unless `LV_AUTH_MODE=local_header` is set.

---

## 2. Route Table Sweep

**Counts reconcile exactly**: 159 routes registered in src/web.py (my first sweep said 158 — my regex missed `@app.patch`, web.py:4669; the checker's own regex includes it, scripts/check_route_reachability.py:34-36). Contract `contracts/ROUTE_REACHABILITY.yaml`: 131 `reachable_from_ui` + 28 `intentionally_backend_only` = 159. **Zero unclassified routes, zero stale contract entries, zero duplicate registrations.**

Independent caller sweep (literal + template-piece search over static/index.html, static/sw.js, desktop/) found 17 routes with no current-UI caller. Every one is in the contract's backend-only list. Cross-check details:

### False positives/negatives in my own sweep (resolved, both directions)
- **3 admin routes** (`GET /api/admin/{evidence,capacity,trends}`) looked ORPHANED to literal search but are WIRED via the dynamic `/api/admin/${state.view}` call site (index.html:7099, views registered :1469-1473). Contract had this right.
- **13 backend-only routes** looked called, but the "callers" were: the bundled snapshot under `desktop/release/linux-unpacked/resources/app/` (a stale copy of the whole repo — exclude it from any future sweep), the `legacyBackendRouteMarkers` documentation array (index.html:1464-1467 — strings, not calls), and substring collisions (`sync-folder` matching `sync-folder-map`).

### Contract mislabels found (conservative direction, P2)
- `GET /api/sync/status` — labeled `intentionally_backend_only: permanent`, but the UI calls it (index.html:4758) and the entry's own reason says "for the Settings panel (B4)". Should be `reachable_from_ui`.
- `GET /api/voice/probe` — labeled backend-only "diagnostics", but the UI fetches it live (index.html:886 and :4750).
- **Why the gate missed this**: check_route_reachability.py verifies `reachable_from_ui` call-sites still exist (:119-138) but never detects a backend-only route that has *gained* a UI caller (:139-148 checks only status/reason). Asymmetric instrument — it can only catch drift in one direction.

### Dormant-wired (matches operator ruling)
- `POST /api/voice/act` — caller exists (index.html:1322) but the global voice companion is hidden for day one via `body.voice-hidden` (index.html:724-727, HF1 §8.2 operator ruling). Contract says `deferred_undecided` — honest.

### Final classification
- **WIRED: 131** (128 confirmed by independent literal search + 3 via dynamic admin call site).
- **API-ONLY: 28** (11 `permanent` with reasons; **17 `deferred_undecided` awaiting operator decision** — the standing preflight output flags these every run).
- **ORPHANED: 0.**
- Deferred list (needs operator ruling, unchanged from contract): google-drive/sync-folder (GET+POST), cohort-plans (preview/approve/list), voice/act, help-artifact (preview/approve), portfolio-entry (preview/approve), ops/request-summary, ops/schedule-ack-summary, action-plans/preview, categories, WS /ws, ingest, teacher/holdout.

### Role-gate coverage per route (web.py:81-137, active only when `LV_AUTH_MODE≠off`)
- ADMIN_ONLY: `/api/slack/credentials`, `/api/ops/setup/`, `/api/provider/`, `/api/settings/keys`, `/api/google-drive/` (:93-96)
- COORDINATOR_OR_ADMIN: `/api/admin/*`, observation/audit exports, ops summaries (:97-102)
- Per-teacher scoping: `/api/ops/daily`, `/api/ops/records` (:103-113)
- TEACHER_OR_HIGHER: `/api/observe/`, `/api/students*`, `/api/teacher/`, `/api/cohort-plans*`, `/api/extraction/`, profile routes, `POST /api/parents/recommendation` (:114-125)
- **Everything else passes ungated even in `local_header` mode** (:127-128) — including `/api/ask`, `/api/query`, `/api/query/stream`, `/api/lesson-materials/*`, `/api/voice/*`, `/api/assess/*`, `/api/daily/briefing`. These routes surface student-derived content (Ask answers cite observations). If `local_header` mode is ever relied on as a real boundary, this is a hole — flagged for operator ruling (§7).

---

## 3. Pipeline Live-Wiring (8 steps from run_teacher_query)

**Premise correction**: `run_teacher_query` is at `src/lingua_viva/app.py:4-36`, not `src/app.py` as the prompt stated.

Three production callers: `POST /api/ask` (web.py:2050), `POST /api/voice/act` (web.py:3486), `POST /api/query` (web.py:7044).

Two instruments: static trace of `Pipeline.run` (src/pipeline.py:629, `steps_executed.append` at :662/:699/:714/:768/:808/:953/:975/:1043) **and** a live TestClient probe of `POST /api/query` whose response `pipeline.steps` listed the stages actually run.

| Step | Status | Evidence |
|---|---|---|
| SCAN | **LIVE** | EntryGate.scan called at pipeline.py:661-662; blocks on `contains_private_runtime_data` (:71-81); observed in probe |
| CLASSIFY | **LIVE** | observed in probe |
| EXECUTE | **LIVE (conditional)** | only 4 ontology nodes have handlers — `NODE_HANDLERS` maps LV-CUR-002/LV-TCH-002/LV-STU-003/LV-ASS-001 (src/education/pipeline_execute.py:58-63); all other nodes return None and the step is skipped |
| RETRIEVE | **LIVE** | observed in probe |
| RESEARCH | **DEAD BY DESIGN** | `needs_external` hard-returns False — "Intentionally disabled: Lingua Viva teacher workflows are local-only" (pipeline.py:192-199); RESEARCH block gated on it (:797-808) |
| REASON | **LIVE** | observed in probe |
| SYNTHESIZE | **LIVE** | observed in probe |
| STORE | **LIVE** | observed in probe |

**Stub gates found on the exit side (not in the prompt's list, but load-bearing):**
- `ExitGate.scan_response` always returns `(True, [])` — DEFERRED stub since 2026-07-18 (pipeline.py:83-96). The response-side twin of EntryGate does not exist.
- `IntegrityGate.check` returns empty — DEFERRED stub (pipeline.py:103-117).

These are honest deferrals with comments, but they mean **outbound pipeline responses have no gate**; parent-summary output safety is enforced at the route layer only (§4).

---

## 4. Safety Chokepoints

### 4a. Parent-summary redaction — WIRED, with a characterized limit
- `POST /api/parents/recommendation` (web.py:6103-6187): blank/missing student → `400 student_id_required`; unknown → `404 unknown_student`, no draft body. Demo-student fallback removed.
- `_strip_parent_output` (web.py:1668) applied at :6143-6146: bans AI-attribution phrases, replaces student names with "your child", runs `redact_runtime_text`.
- `check_publication_safety` runs **post-strip** and is **flag-never-block** by explicit comment (web.py:6155-6166). The teacher is the send gate by design (copy/print exits only, no send mechanism).
- **Characterization**: `_strip_parent_output` is best-effort string replacement (case-sensitive replace). It is a cleanup pass, not a guarantee. Acceptable *only because* a human teacher reviews before anything leaves the machine. If a send mechanism is ever added, this chokepoint must be hardened first — flagged for operator awareness (§7).
- **No P0 leak found.** No other route emits parent-framed output. A hypothetical parent caller on localhost would (in default off-mode) be admin like everyone else — see §1 "real boundary".

### 4b. Privacy EntryGate — LIVE
Called unconditionally at pipeline.py:661-662 before any reasoning; blocked queries get a redacted SensitivityReport (:71-81). Verified live in the §3 probe.

### 4c. Zero-egress instrument — covers async, with two named residual gaps
- Guard patches `socket.socket.connect` at **class level** (teacher_readiness.py:142-159), allowlist {127.0.0.1, ::1, localhost}; scoped firewall evidence at :358-382; engaged for the whole harness run at :541.
- **Second instrument (runtime)**: a TEST-NET (`192.0.2.1`) connect attempt via async httpx on the default event loop *inside the guard* was recorded and blocked (`attempts: [{'host': '192.0.2.1'}]`). Async coverage is empirically proven, not assumed.
- **Residual gap 1 (P2)**: `uvloop` is installed. uvloop connections go through libuv, not Python `socket.socket` — a server run under uvicorn with `loop=auto` would bypass the patch. The harness itself uses TestClient (in-process asyncio) so its own evidence is sound, but the instrument does not cover the production loop configuration.
- **Residual gap 2 (P2)**: DNS (`getaddrinfo`) is unguarded — a resolution attempt leaks the queried hostname even when the subsequent connect would be blocked.

### 4d. Server-side role gate — EXISTS, OFF BY DEFAULT
Middleware web.py:81-137; `LV_AUTH_MODE=off` default short-circuits it entirely (:87-88). In `local_header` mode it trusts client-supplied `X-LV-*` headers (access_roles.py) — a cooperative boundary, not an adversarial one. Credential routes have the separate `_require_local` host check (web.py:425-444). Bind is 127.0.0.1 (web.py:7343).

---

## 5. Instrument Audit — can each check actually fail?

| Instrument | Fail-capable? | Notes |
|---|---|---|
| `lv doctor` (16 checks, doctor/support_loop/doctor.py:427-445) | Checks: YES. Exit code: **BROKEN for PRIVATE_RISK** | cli.py:99 returns 0 for `("OK","WARN","FIXABLE","PRIVATE_RISK")`. The doctor's own summary for PRIVATE_RISK is "I found a privacy risk and stopped" (doctor.py:423) — yet the exit code says success. Any `lv doctor && …` chain proceeds through a privacy risk. Second instrument confirming this is wrong-by-inconsistency: `lv health --full` correctly excludes PRIVATE_RISK from its passing set (cli.py:190). **P1.** |
| `lv eval teacher-readiness` | Report: YES. Exit code: **NO — always returns 0** (cli.py:110-118) | A 0% run with five P0s exits 0. The harness can never gate a script or CI job. **P1.** |
| `lv health --full` (cli.py:156-195) | YES | All five components (doctor status, pytest, gauntlet, golden eval, 5xx count) individually fail the exit code. |
| `lv preflight` (cli.py:198-301) | YES | 6 checks: ui_contract, golden_parses, imports, ontology-vs-MANIFEST count, staged conflict markers, route_reachability — each independently fail-capable. |
| `check_ui_contract.py` | YES | SHA-256 hash lock; any byte change to a protected file without `--bump` → exit 1 (:54-81). |
| `check_route_reachability.py` | YES, asymmetric | Fails on unclassified/stale/duplicate/missing-call-site (:72-154). Cannot detect backend-only→now-called drift (§2). **P2.** |
| Doctor `privacy_path_scan` | YES | Live-triggered this session by `.lv_teacher_readiness/` harness scratch (gitignored, .gitignore:36) → PRIVATE_RISK. The check works; the exit code (above) doesn't. |

### Red-forever checks (measurement-discipline flag)
- **C9** (P1) and **C10** (P0) carry `expected_fail: true` since 2026-08-03. They have been red at every observed run and cap readiness at 89.5% permanently. Per the measurement discipline (PC 1 lesson 7): a red-forever check is worse than a deleted one — it trains readers to skim past FAIL rows and buries a *new* unexpected fail in familiar noise. C10 is doubly bad: a **P0 labeled expected** is a contradiction in terms. Recommendation in §7: either build the degradation behaviors they measure, or re-mark them as explicit `stubbed`/`todo` states excluded from the FAIL rendering.

---

## 6. Known Open Items — current state

### C8: observe → materials 422 / 60s latency — ROOT-CAUSED, not a wiring gap
- Chain: harness capture succeeds (200), then materials generation calls `engine.reason()` per tier (src/lingua_viva/lesson_materials.py:437-444). `LV_REASON_TIMEOUT_SECONDS` defaults to 60 (src/lingua_viva/reasoning.py:228). Evidence `duration_ms: 60435` = one full timeout, then the fail-closed guard raises `generation_failed` (lesson_materials.py:449-453 — deliberate P1-2 ruling from Claudia QA 2026-08-03: no stub materials, fail closed with the teacher-facing setup message) → 422 at web.py:5668/:5771.
- Ollama **is** up on this machine with `qwen2.5:3b` (probed live). The model simply cannot complete the materials-tier prompt within 60s on this hardware.
- So: **route wired correctly, failing closed by design; the red is a model-capacity/latency problem**, and the check conflates two concerns (latency envelope + generation success). Fix options need an operator ruling (§7): longer materials-specific timeout, smaller/faster prompt, or pre-generation.

### Auto-release tag gap — STILL OPEN, documented in-line
- `.github/workflows/auto-release.yml:115-130`: tag pushed with `GITHUB_TOKEN` never triggers `desktop-release.yml` (GitHub recursion guard). Every auto-created `desktop-v*` tag requires manual delete + re-push with real credentials to build — exactly what shipping v0.2.46 required this session. Fix options (already written in the workflow comment): PAT-backed secret, or restructure desktop-release as `workflow_call`.

---

## 7. Prioritized Fix List

### P1
1. **Doctor exits 0 on PRIVATE_RISK** — src/lingua_viva/cli.py:99: remove `"PRIVATE_RISK"` from the passing tuple. One-token change; aligns with health --full's own treatment (cli.py:190).
2. **teacher-readiness exit code is unconditionally 0** — src/lingua_viva/cli.py:118: return nonzero when any non-`expected_fail` check fails (or when `highest_severity=="P0"` and not expected). Makes the harness usable as a gate.
3. **Red-forever C9/C10** — needs operator ruling: build the two degradation behaviors, or add a `stubbed` status in `src/lingua_viva/teacher_readiness.py` so expected-fails stop rendering as FAIL and stop capping readiness. (Blast radius: changes the readiness number's meaning — ruling required.)
4. **C8 materials timeout** — needs operator ruling on the fix shape: materials-specific timeout override vs. prompt slimming vs. pre-generation. (Blast radius: teacher-facing latency expectations.)
5. **Auto-release PAT** — needs operator action (create PAT secret) or ruling to restructure as `workflow_call` (.github/workflows/auto-release.yml:115-130).

### P2
5a. **`server_5xx` health check has no time window** — src/lingua_viva/request_log.py:66-68: any historic 5xx fails `lv health --full` forever (42 events from Jul 24–Aug 6, all TTS/Drive 503s, keep it red today). Options: window the count (e.g., last 24h/7d), or reset the log on release, or exclude 503-from-unconfigured-optional-services. Needs a small operator ruling on the window.
5b. **`health --full` discards pytest failure identity** — src/lingua_viva/cli.py:176 keeps only the last output line. Keep the `FAILED …` lines too, so a 1-fail run is diagnosable after the fact (this audit could not name its one failing test because of this).
6. **Contract mislabels** — move `GET /api/sync/status` and `GET /api/voice/probe` from `intentionally_backend_only` to `reachable_from_ui` with their real call sites (contracts/ROUTE_REACHABILITY.yaml; call sites index.html:4758 and :886/:4750).
7. **Reachability-gate asymmetry** — scripts/check_route_reachability.py: also grep static/index.html for each backend-only route's path and fail (or warn) when a backend-only route has a live caller. Exclude `legacyBackendRouteMarkers` and `desktop/release/` from the search space.
8. **Harness run history** — teacher_readiness.py: append a timestamped copy (or one NDJSON summary line per run) so regressions between runs are recoverable. Would have made the STEP 0 73.7% question answerable.
9. **Zero-egress uvloop + DNS gaps** — document in the harness report that the guard covers the default asyncio loop only; optionally patch `socket.getaddrinfo` and/or run one probe under uvloop.
10. **ExitGate/IntegrityGate stubs** (pipeline.py:83-96, :103-117) — fine as deferrals while no send mechanism exists; must be revisited before any outbound/send feature.

### Needs operator ruling (blast-radius items, no action taken)
- **R-A**: The 17 `deferred_undecided` backend-only routes (§2) — wire, keep, or delete each.
- **R-B**: Role-gate scope in `local_header` mode — `/api/ask`, `/api/query`, `/api/lesson-materials/*` and other student-content routes are ungated (web.py:127-128). Decide whether `local_header` mode is a real boundary; if yes, these need TEACHER_OR_HIGHER.
- **R-C**: C9/C10 expected-fail handling (item 3).
- **R-D**: C8 fix shape (item 4).
- **R-E**: `_strip_parent_output` hardening is a **precondition** for any future send mechanism (§4a) — record as a standing constraint.

---

## Appendix — health --full at HEAD `e239b12`

```text
Doctor: PRIVATE_RISK
Pytest: FAIL — 1 failed, 2076 passed, 13 skipped in 1954.51s (0:32:34)
Gauntlet: PASS
Golden eval: PASS
Server 5xx: FAIL (42 5xx responses logged)
```

Triage of each red, with second-instrument verification:

1. **Doctor: PRIVATE_RISK** — known cause: `.lv_teacher_readiness/` harness scratch (`student_lenses.db`) trips `check_privacy_paths` (doctor.py:397-413). The path is gitignored (.gitignore:36) and cannot be committed. The check is doing its job; the exit-code bug (§5) is the real issue.
2. **Pytest: 1 failed / 2076 passed — failing test identity: CANNOT-TELL.**
   - `health --full` captures pytest output but keeps only the last line (`pytest_summary`, cli.py:176) — the failing test's name was discarded at the source.
   - `.pytest_cache/v/cache/lastfailed` was not usable as a second instrument: it held 9 accumulated entries, at least two with **stale node IDs for tests that no longer exist** (`test_ethos.py::TestCaptureWiring::test_capture_returns_suggestions_never_auto_writes`, `test_error_handling_sweep.py::test_observe_without_type_is_rejected_not_defaulted`) — cruft from older sessions, not this run's record.
   - Re-running all 8 candidate files whole: **140 passed in 19.9s** — everything plausible passes in isolation.
   - Context: this pytest ran **concurrently with the fresh teacher-readiness harness run** (both competing for Ollama + CPU); wall time 1954s vs the same suite's ~1215s clean run earlier today, and the full suite passed 2077/2077 at `c4b2e4a` this same day. **Verdict: near-certainly a contention flake; identity unrecoverable.**
3. **Server 5xx: 42 logged — all historic, none from this audit.** Log analysis (`~/.lingua-viva/request_events.ndjson`, 1641 events): 38× `POST /api/voice/tts` 503 + 1× 502 (Rime TTS not configured), 3× Google Drive 503 (not connected); earliest 2026-07-24, latest 2026-08-06. `count_5xx` (request_log.py:66-68) counts the **entire log history with no time window** — once any 5xx is ever logged, health fails forever until the log is manually cleared. A red-forever instrument by construction. Also worth a ruling: 503 from an *optional unconfigured* service (TTS) is arguably not the error class this check should fail on.
4. **Exit-code observation**: the background wrapper reported exit 0 despite three reds. The CLI's own logic returns 1 for this result (cli.py:189-195 — doctor PRIVATE_RISK is excluded from the passing set, pytest≠0, 5xx>0), so the 0 is almost certainly the shell wrapper's (pipe) exit status, not health's. **CANNOT-TELL definitively without a re-run; treat piped invocations of `lv health` as masking the exit code.**
