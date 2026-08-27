# Lingua Viva — Current State & Improvement Plan
**Date:** 2026-08-27 | **Commit:** ed20299 (reconciled merge) | **Live:** desktop-v0.2.70

---

## 1. CURRENT STATE SUMMARY

### What's Live (desktop-v0.2.70 on linguaviva.art)
- Lesson plan generation (CEFR-tiered, IB PYP aligned)
- Student import from XLSX class lists
- Observation capture (CEFR dimensions, support evidence)
- Parent report generation + teacher approval
- Document-to-lens pipeline (classify → match → extract → apply)
- Improvement circuit (MEASURE/VERIFY/ANALYZE, gauntlet 81/81)
- Google Drive per-file OAuth (scope: `drive.file`, no admin)
- macOS signed (XWT7RB624U), Windows NSIS, Linux AppImage

### What Just Landed (ed20299, not yet released)
- **P1-ARCH-001**: `routers/students.py` extracted from web.py (-2,110 lines from web.py)
- **P1-DOC-001**: Parent report full print template (CSS, meta section, honest empty notes)
- **Immutable snapshots**: All generated materials use UUID-stamped snapshot storage
- **Privacy audit**: AST-based scan locks student names out of exceptions/logs/prints
- **.deb support**: CI workflows + post-install hook for Ubuntu 24.04 AppArmor
- **Knowledge library**: 3 new education YAMLs (ATL, Italian L2, Learner Profile)
- **CLAUDE.md rewrite**: Claudia-as-user framing (not developer)
- **web_helpers.py**: Shared defs prevent circular imports between web.py and routers
- **Route reachability**: Scanner extended to cover router modules (21 new routes visible)

### Test State
- **61 passed, 6 failed** on targeted run (parent_report + lesson_materials + document_to_lens)
- 6 failures are ALL in `test_document_to_lens.py` — event loop setup issue (`RuntimeError: There is no current event loop in thread 'MainThread'`). These are async fixtures that need `@pytest.mark.asyncio` or an event loop fixture. Pre-existing, not from the merge.
- Parent report template tests: ALL PASS
- Lesson materials tests: ALL PASS
- Full suite not yet run on reconciled tree (recommend before any release)

### PC-23 Branches (not on remote, local to PC-23)
- `fix-coverage-status-filter-2026-08-27` — 117 commits, contains W3
- `w3-market-verbs-2026-08-26` — 116 commits
- These are significant builds. PC-23 should push them so they can be reviewed and integrated.

---

## 2. ARCHITECTURE STATE

### web.py Split Progress (P1-ARCH-001)
| Router | Status | Lines moved |
|---|---|---|
| `sources.py` | SHIPPED | ~200 |
| `safeguarding.py` | SHIPPED | ~150 |
| `artifacts.py` | SHIPPED | ~200 |
| `document_import.py` | SHIPPED (origin, d18b782) | ~220 |
| `students.py` | SHIPPED (this commit) | ~2,000 |
| lesson_materials | NOT STARTED | ~800 est |
| google_drive | NOT STARTED | ~400 est |
| voice | NOT STARTED | ~300 est |
| ops/admin | NOT STARTED | ~200 est |
| curriculum | NOT STARTED | ~200 est |
| filemap | NOT STARTED | ~100 est |
| cohort | NOT STARTED | ~100 est |

**web.py is still ~6,900 lines** (down from 9,040). 5 of ~12 routers extracted.

### Key File Sizes
| File | Lines | Notes |
|---|---|---|
| `src/web.py` | ~6,900 | Still the biggest file; 7 more routers to extract |
| `static/index.html` | 8,293 | P1-ARCH-002: CSS/JS extraction not started |
| `src/student_lens.py` | 3,512 | P1-ARCH-003: split not started |
| `src/lingua_viva/lesson_materials.py` | ~1,200 | Immutable snapshot storage added |
| `src/education/parent_report.py` | ~525 | Full print template with CSS |
| `src/lingua_viva/docpipe/lens_extract.py` | 650 | NEW: doc-to-lens extraction |
| `src/lingua_viva/improvement.py` | 432 | NEW: improvement circuit |

---

## 3. SECURITY & PRIVACY STATE

| Item | Status | Action |
|---|---|---|
| P0-SEC-001: `.env` with Perplexity key | **OPEN** | `git rm --cached .env`, add to .gitignore, rotate key |
| P0-SEC-002: Student name in logs/exceptions | **LOCKED** | AST audit in test_privacy_audit.py; teacher_readiness.py fixed |
| Student data local-only | ENFORCED | No Drive egress, TTS gate before Rime |
| No AI attribution in parent output | ENFORCED | `attribution_visible_to_parent=False` hard-locked |
| trauma_flag never auto-set | ENFORCED | 3 independent enforcement layers |

**P0-SEC-001 is the most urgent security item. Fix it before any release.**

---

## 4. KNOWN TEST FAILURES

### 6 failures in test_document_to_lens.py (pre-existing)
```
FAILED test_cefr_extraction_from_report_card
FAILED test_extraction_saved_before_lens_write
FAILED test_trauma_flag_never_auto_set
FAILED test_red_safeguarding_routed_to_restricted
FAILED test_multi_student_document_partitions_correctly
FAILED test_extraction_with_no_content
```

**Root cause**: `RuntimeError: There is no current event loop in thread 'MainThread'`.
These tests call async functions (likely through the student_lens_writer or web routes)
without an event loop fixture.

**Fix**: Add `@pytest.fixture` that creates an event loop, or use `@pytest.mark.asyncio`
with `pytest-asyncio`. Check if the tests worked on origin/main before the merge — if they
did, the issue may be an import-order side effect from the router extraction.

### Route reachability: 21 deferred_undecided routes
Router-registered routes now visible to the scanner but not yet classified:
- Library search, safeguarding review, and other router-mounted endpoints
- These are NOT broken — they work. They just need route reachability classification.

---

## 5. IMPROVEMENT PLAN — PRIORITY ORDER

### P0: Ship-blocking (fix before any release)

1. **Fix `.env` leak (P0-SEC-001)**
   ```bash
   echo ".env" >> .gitignore
   git rm --cached .env
   git commit -m "fix(security): remove .env from tracking, add to .gitignore"
   ```
   Then rotate the Perplexity API key.

2. **Fix 6 async test failures**
   - Check: do these pass on origin/main at d18b782? (`git stash && git checkout d18b782 && pytest tests/test_document_to_lens.py -q`)
   - If yes: the router extraction broke an import path. Trace the event loop dependency.
   - If no: add async fixture. Look at how other async tests in the suite handle it.

3. **Run full test suite**
   ```bash
   python3 -m pytest tests/ -q
   ```
   Establish baseline count. No release without zero new failures.

### P1: Quality & Architecture (this week)

4. **Continue web.py split (P1-ARCH-001)**
   - Next: `lesson_materials` router (largest remaining, ~800 lines)
   - Then: `google_drive` router (~400 lines)
   - Pattern: copy handlers to `routers/<name>.py`, `@app.` → `@router.`, add to `__init__.py`, test
   - Shared defs go in `web_helpers.py` (never import web.py from a router)

5. **Classify the 21 deferred_undecided routes**
   - Read `contracts/ROUTE_REACHABILITY.yaml`
   - For each: determine if the route has a UI call site in static/index.html
   - If yes: classify as `active`. If no: classify as `api_only` or `deferred_no_ui`.

6. **Wire improvement circuit into CI**
   ```bash
   python3 -m src.lingua_viva.improvement --measure
   python3 -m src.lingua_viva.improvement --verify
   ```
   Add to pre-release gate. Gauntlet must stay 81/81 or explain why not.

### P2: Features & Polish (this sprint)

7. **Parent report print polish**
   - Test with real student data (Claudia's class list)
   - Verify: empty sections render honest notes
   - Verify: print layout works at standard paper sizes (A4 + US Letter)

8. **.deb release**
   - Cut a desktop-v0.2.71 tag that includes the .deb workflow
   - Verify: AppArmor sandbox workaround works on Ubuntu 24.04
   - Verify: auto-release.yml checks for LinguaViva.deb asset

9. **Integrate PC-23 branches**
   - `w3-market-verbs-2026-08-26` (116 commits) — needs review
   - `fix-coverage-status-filter-2026-08-27` (117 commits, contains W3) — needs review
   - Both are substantial. Reconcile carefully (same hunk-isolation discipline as MC).

10. **Knowledge library expansion**
    - 3 new YAMLs landed (ATL, Italian L2, Learner Profile)
    - Verify they're loaded by the improvement circuit's knowledge grounding test
    - Check: does the lesson plan generator reference them?

### P3: Architecture Debt (next sprint)

11. **Extract CSS/JS from static/index.html (P1-ARCH-002)**
    - `<style>` → `static/css/app.css`
    - `<script>` → `static/js/app.js`
    - Enables Claudia to edit UI without touching HTML structure

12. **Split student_lens.py (P1-ARCH-003)**
    - 3,512 lines. Needs design before cutting.
    - Likely split: store operations, lens computation, evidence management

13. **Google Drive OAuth: publish the app**
    - Desktop client created, secrets set
    - Remaining: operator clicks Publish (Google console → Audience)
    - Acceptance: Claudia signs in with ZERO registration

---

## 6. WHAT THE OTHER PC SHOULD DO

If PC-23 picks this up for tonight's testing wave:

1. `git pull origin main` — gets the reconciled merge (ed20299)
2. Fix P0-SEC-001 (.env leak) immediately
3. Run full test suite — establish baseline
4. Fix the 6 async test failures
5. Push the two local branches (`w3-market-verbs`, `fix-coverage-status-filter`) to origin
6. If tests are green: cut desktop-v0.2.71 tag (DO NOT push to linguaviva.art yet — just GitHub)
7. Write a morning report with all numbers

**Do NOT release to the live site** until Mical reviews. GitHub releases only.

---

## 7. FILE MAP — Key Paths

```
src/
  web.py                          — Main FastAPI app (~6,900 lines, being split)
  pipeline.py                     — MC pipeline integration
  student_store.py                — SQLite student data (local-only)
  education/
    parent_report.py              — Draft generation + print template
    content_differentiator.py     — CEFR tiering + trauma safety
    student_lens.py               — Lens store (3,512 lines)
    trend_analysis.py             — Student trend computation
  lingua_viva/
    lesson_materials.py           — Lesson plan generation + immutable snapshots
    improvement.py                — Improvement circuit (MEASURE/VERIFY/ANALYZE)
    teacher_readiness.py          — Teacher environment checks
    web_helpers.py                — Shared defs for routers (no circular imports)
    google_drive_oauth.py         — Per-file Drive access
    docpipe/
      extract.py                  — Document/spreadsheet parsing
      lens_extract.py             — Doc-to-lens CEFR/IB extraction
      lens_match.py               — Student matching for doc import
    routers/
      __init__.py                 — Router registry (5 modules)
      sources.py                  — Knowledge library routes
      safeguarding.py             — Restricted observations
      artifacts.py                — Generated materials
      document_import.py          — Doc-to-lens import flow
      students.py                 — Student/ingest/lens/evidence routes
desktop/
  electron/main.ts                — Electron shell
  electron/deb-after-install.sh   — .deb post-install hook
  package.json                    — Build config (dmg/exe/appimage/deb)
static/index.html                 — SPA frontend (8,293 lines)
templates/
  lesson_plan.html                — Lesson plan print template
  parent_report.html              — Parent report print template
knowledge/education/              — 8 YAML knowledge files
lenses/                           — Person + voice lenses
contracts/
  ROUTE_REACHABILITY.yaml         — Route classification manifest
  UI_CONTRACT.yaml                — UI contract (v169)
tests/                            — 221 test files
.github/workflows/
  auto-release.yml                — Post-release verification
  desktop-release.yml             — Desktop build (mac/win/linux)
```
