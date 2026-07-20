# Report: App Improvement — MC Lessons (2026-07-19)

**Spec**: [SPEC_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md](specs/SPEC_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md)
**Baseline**: 411 tests passing (pre-sweep MANIFEST.yaml), no `tests/conftest.py`, no `lv preflight`, no UI bundle contract, ontology docs claiming 137 nodes against a live loader count of 212, `/api/profile/clear` with no export right, `runtime/hub/` undispositioned, no request-outcome log.
**Final**: 437 tests passing, `tests/conftest.py` hermeticity fixture (2 gaps found and closed — see §1 below), `lv preflight` (5 checks, <1s), UI bundle contract at v4, ontology docs and live loader agree at 111 nodes / 25 domains, `/api/profile/export` ships before every clear, `runtime/hub/` archived with rationale, `_log_request_outcome` middleware + zero-500 health gate.
**Informed by**: Mission Canvas's own build-hardening lessons (conftest hermeticity, preflight, UI/wizard contract, SW/surface parity, request-outcome logging, count-truth pinning, data-rights export tier, release ceremony, dev/INDEX.md).

## Summary

| § | Finding | Fixed | Deferred | Status |
|---|---|---|---|---|
| 1 | No test hermeticity — tests could dirty real `~/.lingua-viva/` and tracked repo files | `tests/conftest.py` autouse fixture; **2nd-pass gap found during §9**: `sanitizer/app.py`'s `DATA_DIR`/`FIREWALL_LOG` were module-level constants computed at import time, so the fixture's env var never took effect — converted to a lazy `_data_dir()` function (same seam as `traces.trace_path()`) | — | DONE |
| 2 | No fast structural pre-commit check | `lv preflight` — 5 checks (UI contract, golden parse, imports, ontology/MANIFEST parity, anchored conflict-marker scan), 0.4–0.5s | — | DONE |
| 3 | No hash-lock on the UI bundle (`static/index.html`, `static/sw.js`, `src/web.py`) — silent drift risk | `contracts/UI_CONTRACT.yaml` + `.lock`, `scripts/check_ui_contract.py --bump`, enforced by `tests/test_ui_contract.py`. Bumped v1→v4 across this sweep (§5 middleware, §7 quick capture, §8 export) | — | DONE |
| 4 | Two undispositioned surfaces: `runtime/hub/` (fork-era, only reachable via already-broken `setup.sh`) | Archived to `archive/mc-engine/runtime/hub/` with `ARCHIVED.md` rationale; `runtime/package.json` dangling scripts removed; `tests/test_sw_surface_parity.py` pins exactly one live `sw.js` | — | DONE |
| 5 | No request-outcome log — LV could not prove zero unhandled 500s, unlike MC's longitudinal firewall history | `src/lingua_viva/request_log.py` (NDJSON, path-templated, 0600, no query content) + `_log_request_outcome` middleware in `src/web.py` + `lv health --full` gains a `server_5xx` check | — | DONE |
| 6 | Doc counts stale (137/212-node claims vs. live loader); 111 fork-era `ai-enablement` nodes never re-audited | Live loader, MANIFEST.yaml, README.md, CLAUDE.md all pinned to 111 nodes/25 domains via `tests/test_doc_counts.py`. Of 111 `ai-enablement` nodes, 101 archived to `archive/mc-engine/ontology/domains/`; 10 kept live in `ontology/domains/ai-enablement-core.yaml` — the exact transitive `escalates_to`/`resolves_to`/`parent` closure required by `strategy`/`financial`/`business_planning`/`enablement`/`safety` domain edges. Golden eval 36/36 both configurations; graph integrity (`test_no_broken_edges`) only holds with the 10-node closure kept | — | DONE |
| 7 | No fast-capture path — desktop has no renderer views, web UI required full navigation for a quick note | Ctrl/Cmd+K overlay in `static/index.html`, posts free text through the existing governed `/api/query` endpoint (same `EntryGate.scan()` privacy path as Ask) | — | DONE |
| 8 | `/api/profile/clear` was all-or-nothing deletion with no export — for data about children | `GET /api/profile/export` (traces, privacy events, full student lens + observation history, revision log, filemap — one local-download JSON); UI clear flow now warns to export first; smoke test export→clear→export empty | — | DONE |
| 9 | Desktop stuck at 0.1.0, no rebuild/re-lock ceremony documented | `desktop/package.json` → 0.2.0, `npm run build` clean, AppImage built (108MB, `desktop/release/`), contract re-locked after build (unaffected — build doesn't touch UI-contract files), preflight + Gate 3 re-verified after | — | DONE |
| 10 | 17 specs in `dev/specs/` with no index — statuses scatter and go stale | `dev/INDEX.md` — table of all 17 specs + 3 reports, status + evidence pointer | — | DONE |

## MC Lessons Applied

| MC Lesson | Applied? | Note |
|---|---|---|
| conftest.py autouse hermeticity fixture | Yes | Plus a 2nd-pass fix (sanitizer module-constant gap) found via the same dirty-tree discipline this lesson teaches |
| Fast structural preflight (<5s) | Yes | `lv preflight`, 0.4-0.5s |
| UI/wizard bundle hash-lock contract | Yes | Cloned shape from MC's `WIZARD_CONTRACT.yaml`/`check_wizard_contract.py` |
| SW/surface parity (single cache definition) | Yes | One live `sw.js`; second surface (`runtime/hub/`) archived |
| Request-outcome NDJSON log + zero-500 gate | Yes | `request_log.py` + `_log_request_outcome` middleware |
| Single source of truth for counts | Yes | `test_doc_counts.py` pins MANIFEST/README/CLAUDE.md to the live ontology loader |
| Data rights: export/remove/purge tiers | Partial | Export added (§8). LV has no multi-tier remove/purge distinction yet (MC's operator-lens rights model is heavier than LV's single-teacher-workspace scope) — N/A at LV's current scale, noted as future work if multi-teacher support is added |
| Version bump + rebuild + re-lock-after-build ceremony | Yes | Desktop 0.2.0, re-lock verified unaffected, preflight/Gate 3 re-run after |
| dev/INDEX.md as single spec-status source | Yes | `dev/INDEX.md` seeded from all 17 specs + 3 reports |

## Detailed Findings — Notable Dispositions

**§6 (largest finding of this sweep)**: The original plan (per spec: "run the eval both ways, bring the numbers") treated golden-eval parity as sufficient evidence to archive the full 111-node `ai-enablement` import. Archiving all 111 passed golden eval (36/36) but broke `test_ontology.py::test_no_broken_edges` — 13 dangling `escalates_to` edges from five other live domains. Golden-eval accuracy and graph referential integrity are separate signals; the first was not sufficient evidence for the second. A transitive-closure computation over `escalates_to`/`resolves_to`/`parent` found the true minimal live-required subset was 10 nodes (not the 8 initially assumed from direct references alone — `RIU-534` itself referenced two further nodes). Final state: 101/111 archived, 10/111 live, golden 36/36 both ways, zero broken edges.

**§9 (hermeticity gap found via the desktop build)**: Building the AppImage and re-running the full suite surfaced a 2,357-line diff to the tracked `sanitizer/data/firewall_log.ndjson` — the §1 conftest fixture's `LV_SANITIZER_DATA_DIR` env var had no effect because `sanitizer/app.py` computed `DATA_DIR`/`FIREWALL_LOG` as module-level constants at import time (before any per-test `monkeypatch.setenv` runs). Fixed by converting to a lazily-evaluated `_data_dir()` function, matching the lazy-path-function pattern already used everywhere else in the codebase (`traces.trace_path()`, `privacy_log.privacy_log_path()`, `request_log.request_log_path()`). Regression test added: `tests/test_sanitizer_unified.py::test_firewall_log_honors_hermeticity_override`. Re-ran the full suite twice after the fix — tracked file stayed byte-identical both times.

## Final Gate Table

| Gate | Baseline | HB1 (after §6) | HB2 (final, after §9) |
|---|---|---|---|
| Full test suite | 411 passed | 431 passed | **437 passed** |
| Doctor tests | — | 15/15 | 15/15 |
| Golden eval | — | 36/36 | 36/36 |
| Gate 3 sweep | — | 15/15 | 15/15 |
| `lv health --full` | — | PASS (doctor=WARN, accepted) | PASS (doctor=WARN, accepted) |
| `lv preflight` | n/a (didn't exist) | 5/5 | 5/5 |
| Desktop build | 0.1.0, not rebuilt this sweep | — | PASS — 0.2.0, AppImage built |
| Artifact gauntlet | — | — | PASS (15 files, 7 gates) |
| Forbidden-branding grep | — | — | 0 real hits (only detector code/dev-comments referencing MC by name) |
| `.docx` source document | — | — | untouched |
| Port 8787 | — | — | free after Gate 3 |
| Zero new dirty tracked files after full suite | — | — | confirmed (only pre-existing, pre-session dirty state remains) |

## Operator Queue

1. **§6 disposition — confirm**: 101 of 111 fork-era `ai-enablement` nodes archived to `archive/mc-engine/ontology/domains/ai-enablement.yaml`; 10 kept live in `ontology/domains/ai-enablement-core.yaml` (transitive closure required by cross-domain edges). Golden eval and graph integrity both hold. No action needed unless the archived 101 are wanted back for a use case not covered by golden eval.
2. **§7 disposition — confirm**: quick capture lives in `static/index.html` (desktop has no renderer view layer to hang a command on). If a native desktop command is wanted later, it would need a renderer build first — out of this sweep's scope.
3. **§4 disposition — confirm**: `runtime/hub/` archived as legacy (single fork-import commit, only referenced by an already-broken `setup.sh`). `runtime/broker/` was untouched — out of §4's scope, only referenced by already-archived `mc_cli.py`.
4. **Data rights parity gap (MC Lessons table, "Partial")**: LV has export but not MC's fuller remove/purge tier distinction. Not built this sweep — flag if LV grows beyond a single-teacher-workspace model where that distinction would start to matter.
5. **Desktop AppImage artifact**: `desktop/release/Lingua Viva-0.2.0.AppImage` (108MB) was built locally and is gitignored (`desktop/release/`) — not committed. If a v0.2.0 release/tag is wanted, that's a separate, explicit release step this sweep did not take.
6. **Pre-existing uncommitted changes**: `git status` shows a number of modified files unrelated to this sweep (e.g. `docker-compose.yml`, `install.sh`, `mc.spec`→`lv.spec` rename, several `dev/specs/*.md`, `ontology/learned_weights.yaml`) that predate this session and were left untouched — not reviewed or dispositioned as part of this report.
7. **No commit/push performed.** Per the spec's rules, all work above is staged in the working tree only, pending operator review.
