# Session Summary — LV Unified Real-Data Fix Wave: Execution → Ship

**Date**: 2026-08-19 (session window)
**Spec**: `dev/SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.md` (BINDING)
**Full evidence report**: `dev/REPORT_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.md`
**Outcome**: **desktop-v0.2.65 LIVE on linguaviva.art** — all steps closed, one push, full 7-step verification. Demo-ready for 2026-08-20.

---

## 1. What shipped (commit chain)

16 commits ahead of the previous origin/main (`521737c`), pushed as ONE push:

| Commit | Content |
|---|---|
| f7ff76c, 167270d | Pre-wave: Drive per-file access (drive.file scope + honest degradation) |
| 1dc887e | Phase 0A: preview/dry-run ingest + preview-never-writes lock test |
| d6c8860 | Phase 0B: labelled corpus + scorer + sealed holdout + synthetic fixtures |
| 8a9b2a8 → 793ed3c | STEPs 1–7: structure-preserving extraction, structural detection (replaces bigram guessing), confidence gate, class membership + "my class" scope, identity resolution + unresolved queue, enrichment veto, canonical normalizer + honest failure reporting |
| b5e4b0c | STEP 8+10 combined: model governance + generation honesty, ONE 3-run verification battery |
| d363984 | STEP 11: metadata from structure (title above label block, Grade/Author/Subjects labels, `_grade_from_text` normalization) + 4 tests |
| 2a3bf39 | §6 wave-end docs: holdout opening + e2e assertion recorded |
| 2a7a097 | STEP 12 docs: excerpt-cap derivation comment in `lesson_materials.py` |
| ee07770 | **Final tree** — Claudia-lens audit P0 fix (v165) |

STEP 9 skipped per directive (unruled §8-2 — "skip and continue, do not stall").

## 2. Key results

### Scorer baseline (held at every checkpoint)
- Curriculum / calendar: **0 false-positive students**
- 3V support: 6/6, precision 1.00 / recall 1.00
- Class list: 334 TP / 0 FP, precision 1.00 / recall 0.80

### §6 Holdout opening (exactly once) — HONEST FAIL
- Expected 230 detections, got 1 (0 TP, 1 FP) → 0.00/0.00.
- Genre miss: 12 per-class sheets (KV…6), name column with **no header**, names as "Firstname + initial" — single-capital surname defeats the bigram pair pattern; no labelled column.
- **No post-hoc fix** — an in-sample patch would not be generalization evidence. Recorded as next-wave work: per-class-sheet genre rule + fresh verification data.

### §6 E2E assertion — PASS (TestClient, isolated store)
- Curriculum + calendar → **0 lenses** (always-preview gate holds)
- Class-list approve scoped to her class ("Grade 3 Verdi") → **35 lenses, 0 FP** (FN entirely grades 6–8; spec's "~39" was a pre-labelling estimate)
- 3V support → 3 identity-linked + 3 created (35→38, no duplicates)
- Finding recorded: model-enrichment leg nondeterministically adds 1–7 low-confidence `evidence=None` candidates on non-student docs (scorer doesn't measure it; preview gate holds lenses at zero) — next-wave governance item.

### STEP 12 — excerpt cap measured, kept at 1500
Governed pick nemotron, 3-tier, 400 max_tokens; Ollama serializes parallel calls (worst ≈ 3× single):
- 1500 chars → 36.0s worst (24s margin) ✅ **kept**
- 2000 → 58.8s; 2400 → 55.0s (within ±10s noise of each other)
- 3000 → 60s TIMEOUT (template_fallback)
Derivation documented in code above `_SOURCE_EXCERPT_CHARS`.

### Claudia-lens UX audit — FAIL → P0 fixed
- **P0 (fixed, ee07770)**: class-folder ingest rendered raw confidence numbers (`0.98`) and internal method tokens (`filename_roster_exact`…) beside student names — violated the "raw confidence never renders" rule. Replaced with plain-English `attributionLabel()` map; UI contract bumped to **v165**; class-locking asserts added to `test_preview_controls_wired`.
- **P1 (recorded, NOT fixed — ONE-push rule)**: failure badges name no recovery step; approve/cancel errors silent (bare Retry); pre-fill overwrites typed topic.
- **P2**: low-confidence badge wording inconsistency; raw exception text to UI.

## 3. Pre-push gates (operator directive — all met with evidence)

1. **Quartet clean** ✓ — `.github/workflows/auto-release.yml`, `desktop-release.yml`, `desktop/package.json`, `deb-after-install.sh` in **zero** of 16 outgoing commits (`git log origin/main..HEAD -- <paths>` empty; full outgoing diff contains none); nothing staged — WIP stayed unstaged in the working tree.
2. **Claudia-lens audit** ✓ — done, noted in report, P0 fixed.
3. **Green on final tree** ✓ — suite on ee07770: **2458 passed / 13 skipped, exit 0** (10:36); scorer green on same tree.
4. **ONE push** ✓ — `git push origin main` → `521737c..ee07770`, rev-list 0/0.

## 4. Post-push: AGENTS.md 7-step verification (all passed)

| Step | Evidence |
|---|---|
| 1. Synced | `git rev-list --left-right --count origin/main...HEAD` → 0 0 |
| 2. Release + CI green | desktop-v0.2.65 created; run 32310216708 all 8 jobs success (auto-release, backend-smoke, mac/win/linux builds, appimage-fresh-boot, release, pin-site) |
| 3. macOS signed | `Signed by team: TeamIdentifier=XWT7RB624U`; notarization `status: Accepted` |
| 4. Site pinned | origin `docs/index.html` → desktop-v0.2.65 only (pin commit 5f96992) |
| 5. Live site | `curl -sI https://linguaviva.art/` → HTTP 200 |
| 6. Download resolves | LinguaViva.dmg release asset → 302 |
| 7. One version live | desktop-v0.2.64 deleted (release + tag); remaining: desktop-v0.2.65 + CLI v1.0.6 (load-bearing) |

## 5. Loose ends (none blocking)

- **Local main was left 2 behind origin** (CI's release-prepare 8555e05 + pin 5f96992 commits). `git pull --ff-only` aborted because the quartet WIP touches `desktop/package.json`. Resolve WIP, then pull.
- Untracked in working tree: `desktop/electron/deb-after-install.sh`, `static/assets/still-i-rise-topbar.jpg`.
- **Next cycle backlog**: audit P1s/P2s; per-class-sheet holdout genre rule + fresh verification data; model-enrichment leg governance on non-student docs; STEP 9 if §8-2 ruled.

## 6. Discipline notes

- Real student/staff names never committed — counts and shapes only in all docs and probes.
- Holdout opened exactly once; FAIL recorded without in-sample repair (measurement integrity).
- STEP 12 noise handled honestly: 2000 measured *worse* than 2400 (generation-length variance dominates) — kept the only point with real margin rather than guessing an unmeasured intermediate.
- No edits while the suite ran; hunk-isolated commits by explicit path throughout.
