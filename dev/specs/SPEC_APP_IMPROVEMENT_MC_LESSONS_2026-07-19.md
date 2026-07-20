# Lingua Viva App Improvement — MC Lessons Pass

**Date**: 2026-07-19
**Status**: READY TO BUILD
**Informed by**: Mission Canvas App Improvement Sweep (`~/fde/mission-canvas/dev/REPORT_APP_IMPROVEMENT_SWEEP_2026-07-18.md` — 13 findings, 12 fixed, 2506 tests)
**Closes the loop**: LV's architecture sweep taught MC (38 findings → 10 lessons, all applied in MC's sweep). This spec sends MC's build learnings back to LV. Second full turn of the cross-repo learning circuit.

**Baseline (verified 2026-07-19)**: 411 app tests + 15 Doctor tests, golden 36/36, Gate 3 15/15, health `doctor=WARN pytest=PASS gauntlet=PASS golden=PASS`, sw.js `lv-pwa-v6`, desktop 0.1.0, ontology 212 nodes.

---

## Rules (inherited from the MC sweep — they worked)

1. **The report is the deliverable.** If you fix 20 things but don't write `dev/REPORT_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md`, the sweep didn't happen.
2. **Every finding gets a disposition**: PASS / FIX / DEFER / WARN. Record it while auditing, not at the end.
3. **Gates stay green throughout**: full suite, golden 36/36, Gate 3 15/15, `health --full`. Record BEFORE/AFTER numbers at each hardening break.
4. **Regression test for every fix.** "Manual probe passed" is not a final state.
5. **Non-mutating eval mode** for all gate scripts (already LV law — `eval_mode: true` in gate3_sweep.sh; keep it).
6. **Build order matters**: hermeticity → tooling → contract → surfaces → features. Endpoint/UI work before test hermeticity would contaminate the audit (LV's own lesson, re-proven at MC).
7. **Do not commit/push** unless the operator asks. Operator queue at end of report.

---

## Build Order

### §1 — Test hermeticity: autouse conftest (P0)

**MC lesson**: MC's `tests/conftest.py` autouse `_hermetic_governance` fixture (delete agent env vars, redirect state home to tmp, patch health-cache path) is why MC's §10 dirty-state audit came back clean on everything that matters. LV has **no `tests/conftest.py` at all** — the baseline failure in the final-polish report (stale `ingest-tmp/tmp*.pdf` in case-studies) was a symptom of this gap, fixed at the instance level, not the class level.

**Build**:
- Create `tests/conftest.py` with an autouse fixture that (a) redirects `~/.lingua-viva/` (traces, privacy events, filemap state) to `tmp_path` via the config module's home-resolution seam, (b) clears any `LV_*` env vars tests don't explicitly set, (c) points ingest temp dirs at tmp.
- Single canonical home-resolution function in `src/lingua_viva/config.py` if one doesn't exist — one seam to patch, not N hardcoded paths (LV's own "one canonical config reader" lesson, extended to state paths).
- **Dirty-state audit**: `git status --porcelain > /tmp/lv-pre-test-state.txt`, run full suite, diff after. Every writer that touches the repo tree gets fixed-or-allowlisted with a comment. MC deferred this fix; LV is 6× smaller — fix it here, don't defer.

**Gate**: full suite green twice in a row with **zero new dirty files** between runs.

### §2 — `lv preflight` (P0)

**MC lesson**: `mc preflight` (5 structural checks, <1.1s) caught a real contract violation **on its first run**. Cheapest tool in the sweep, highest catch rate.

**Build**: `preflight` subcommand in `src/lingua_viva/cli.py`:
1. UI contract valid (see §3 — build §3 first or stub this check until it lands)
2. `tests/golden_education_v1.yaml` parses, query count reported
3. Key imports: `web` app object, `reasoning`, `privacy`, `filemap`
4. Ontology loads — assert node count matches MANIFEST (this makes doc drift a *failing check*, see §6)
5. No staged conflict markers — **use anchored `git diff --cached -G '^<{7} '`**, never `-S "<<<<<<<"` (MC hit the false-positive: `-S` flags any file that merely *mentions* the marker, including preflight's own source)

Print ✓/✗ per check, `Preflight: N/5 in X.Xs`, exit 0/1. Target <5s. Tests for each check including the conflict-marker anchoring.

### §3 — UI bundle contract (P1)

**MC lesson**: the wizard contract (hash-lock over `static/index.html` + server file, version-pinned in a test) went v26→v29 during MC's sweep and caught silent drift twice — including the trap where a **desktop build regenerates static asset hashes after the lock is taken**. LV has no contract at all: `static/index.html` (49.5KB, the whole teacher UI) and `src/web.py` (40+ endpoints) can drift silently.

**Build**:
- `contracts/UI_CONTRACT.yaml` + `.lock`: SHA-256 over `static/index.html`, `static/sw.js`, `src/web.py`. Version field starting at v1.
- `scripts/check_ui_contract.py` with `--bump` (port MC's `check_wizard_contract.py` shape — clone, don't redesign).
- Pin test: `tests/test_ui_contract.py::test_version_bumped_exactly_one_from_live` with a comment line per bump explaining why (MC's ceremony discipline — the comments are the changelog).
- **Ceremony rule in the contract file header**: any build step that writes `static/` must be followed by contract re-lock. Lock AFTER build, never before.

### §4 — Service worker + surface parity (P1)

**MC lesson**: MC found `docs/sw.js` a full version behind `static/sw.js` — dual-surface drift that ships stale caches to the public surface.

**Audit**:
- LV has one `static/sw.js` (v6) — PASS likely, but add a test asserting `CACHE_NAME` version appears in exactly one place, and that any second surface (`runtime/hub/index.html` — role currently unclear) either has no sw.js or is byte-identical.
- Disposition on `runtime/hub/`: is it live, legacy, or archivable? If legacy, archive it (LV's own "don't keep fork-era assets" lesson). Don't leave it undispositioned.
- Bump to v7 only if this pass changes any cached asset.

### §5 — Zero-500 + event audit (P1)

**MC lesson**: MC audited its full firewall history (50,180 events — 0 unhandled, 464 blocked, 5 malicious_response) and could *prove* zero 500s. LV probed 10 invalid payloads in its sweep; good, but not longitudinal, and `uvicorn log_level="error"` (src/web.py:1061) means there's no request log to audit at all.

**Build**:
- Lightweight request-outcome log (NDJSON, `~/.lingua-viva/request_events.ndjson`, hash-only like traces, 0600 perms): timestamp, method, path-template, status. No query content — privacy first.
- `lv health --full` gains a check: scan the event log, fail on any 5xx count > 0.
- One-time audit of `privacy_events.ndjson` history: every event_type accounted for, no silent categories.

### §6 — Single source of truth for counts (P1)

**MC lesson**: MC's §14 found 5 stale doc entries (node counts 312→320 etc.). LV is worse: **CLAUDE.md claims "137-node classification system"; actual is 212** (verified: 38 education + 63 core/domains + **111 in `ontology/domains/ai-enablement.yaml`**). Knowledge claims ("148 entries, 526 citations") vs MANIFEST ("178 entries, 559 citations") also disagree.

**Build**:
- Fix CLAUDE.md counts from live data.
- Preflight check #4 (§2) asserts loader count == MANIFEST count — after this, doc drift fails preflight instead of accumulating.
- **Finding to disposition, not auto-fix**: should a teacher app carry 111 `ai-enablement` nodes? That's 52% of the ontology from the MC fork era — routing-dilution risk for education queries and a fork-asset smell (LV's own anti-pattern). Options: (a) keep + measure golden impact, (b) archive to `archive/mc-engine/` and re-run golden 36/36 + Gate 3. **Run golden with and without; let the eval decide** (MC lesson: trust the instrument over intuition — same method that safely zeroed learned weights in the final polish).

### §7 — Desktop quick capture (P2, the feature)

**MC lesson**: Ctrl+K quick-capture overlay (§13 of MC's sweep) — open, type, Enter, toast with routed node, brief refreshes. ~150 lines of renderer code, disproportionate daily value.

**LV fit is better than MC's**: Claudia's core loop is capturing student observations *mid-class*. Today that's navigate-to-view + form. Quick capture makes it two keystrokes.

**Build** (in `desktop/` renderer — note: LV desktop is currently 3 TS files with no views; if there's no renderer UI to host it, put the overlay in `static/index.html` instead, where the actual teacher UI lives — **decide based on what Claudia actually uses**):
- Ctrl/Cmd+K opens centered overlay; Esc / click-outside closes; input placeholder: "Quick capture — an observation, a note… (Enter to save, Esc to close)".
- Enter → POST `/api/query` (or `/api/observe/capture` when the text matches an observation pattern — let the classifier route it; that's the whole point of the ontology).
- **Privacy**: capture text goes through EntryGate/privacy layer like any query — student-name detection must fire here too. Add a regression test: quick capture with a student name in text → blocked/redacted event logged.
- Toast on success: `Captured → <node>`; on error keep overlay open with inline message.
- New bundle → §3 contract ceremony (this is the deliberate first exercise of the v-bump).

### §8 — Data rights: export before clear (P2)

**MC lesson**: MC ships export/remove/purge tiers (operator lens rights). LV's `/api/profile/clear` is **all-or-nothing deletion with no export** — and LV's data is observations about children, the highest-stakes data in either system.

**Build**:
- `GET /api/profile/export` — zip/JSON of traces (hashed), student lens store, revision log, privacy events. Local download only.
- Clear endpoint unchanged, but the UI clear flow offers export first.
- Smoke test: export → clear → export returns empty.

### §9 — Desktop 0.2.0 rebuild + release ceremony (P2)

**MC lesson**: version bump + rebuild + **re-lock after build** (the v27→v28 trap: MC locked the contract, then the build regenerated `static/index.html` hashes, invalidating the lock — preflight caught it).

**Build**: `desktop/package.json` 0.1.0 → 0.2.0, `npm run build --prefix desktop`, AppImage via electron-builder, then §3 contract re-lock, then preflight, then Gate 3.

### §10 — dev/INDEX.md (P3)

**MC lesson**: MC's `dev/INDEX.md` is the one place spec statuses live; LV has 16 specs in `dev/specs/` with **no index** — status claims scatter into individual files and go stale (LV's sweep already had to correct spec statuses once).

**Build**: `dev/INDEX.md` table — spec, date, status (SHIPPED/DRAFT/TRIAGE), one-line evidence. Seed from the 16 existing specs + 3 reports.

---

## Hardening Breaks

**HB1 (after §4)**: full suite + Doctor tests, golden 36/36, Gate 3 15/15, `health --full`, preflight. Record numbers.
**HB2 (after §9, final)**: same, plus desktop build PASS, artifact gauntlet PASS, forbidden-branding grep 0 hits, `.docx` untouched, port 8787 free after Gate 3, **zero new dirty files after full suite** (§1's promise, re-verified).

## Report Template

`dev/REPORT_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md`: header (Baseline/Final/Informed-by), Summary table (§1–§10 × Findings/Fixed/Deferred/Status), Detailed Findings with dispositions, **MC Lessons Applied** table (which of the 9 MC lessons implemented/deferred/N-A), Final Gate table (Baseline/HB1/HB2), Operator Queue.

## Known open questions for the operator

1. §6: keep or archive the 111 ai-enablement nodes? (Spec says: run the eval both ways, bring the numbers.)
2. §7: quick capture in desktop renderer or static/ web UI — where does Claudia actually work?
3. §4: `runtime/hub/` — live or legacy?

## Out of scope

Exit/Integrity gate implementations (explicitly DEFERRED with owner in final polish — still correct: external research is off), curriculum/publication content (governed by publication-policy.md), the lv-def-001..007 publication questions (need human owners, not code).
