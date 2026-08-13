# SPEC: Observe/Students Tab State Leak + Router Registration Failure

**Date:** 2026-08-12
**Reporter:** Chip (QA audit)
**Priority:** P0 (privacy-adjacent UX bug + broken feature routes in packaged app)
**Status:** BUILT — uncommitted (operator commit window)

---

## Two Bugs, Not One

Chip's report describes symptoms produced by TWO independent bugs that compound
in the UI. Her theory ("two privacy-sensitive tabs fighting over placeholders")
is observationally correct — she localized both bugs from behavior alone — but
mechanistically it's simpler: stale global state + a dead router import.

Fairness note on Chip's privacy theory: LV does have a real deny-as-404
pattern (`safeguarding.py` returns 404 for restricted entries so restricted
content is indistinguishable from absent content), so "privacy placeholders
fighting" wasn't an unreasonable prior — it's just not what's firing here.

---

## Bug 1: `state.selectedStudent` leaks across tab navigation

### Symptoms (Chip's report)

1. Click on a student in the Observe tab — student data loads and displays.
2. Navigate away from Observe. Student data **stays visible** — the dropdown
   never reverts to the "Choose a student..." placeholder.
3. Navigate to the Students tab. A **large error message** appears.
4. The error disappears if all students are deleted from the roster.
5. The error only occurs between the two data-sensitive tabs (Observe and
   Students), not from other tabs to Students.

### Root Cause (verified against `origin/main`)

**`state.selectedStudent`** is a single global variable shared across all tabs.
It is set when a student is picked in Observe (`static/index.html:2175`) but
**never cleared** when navigating away:

- `switchView()` (line 1565) sets `state.view` and clears `voiceLastStudent`
  but does NOT touch `state.selectedStudent`.
- `clearObserveForm()` (line 2190) clears form fields but does NOT touch
  `state.selectedStudent`.

When `renderStudents()` runs (line 2517), it unconditionally calls
`await loadLens()`, which fires API calls against the stale student. If the
stale ID is still valid, you see the wrong student pre-selected plus the
inline POI 404 (Bug 2). If the stale ID becomes invalid (e.g., the student
was archived — the Archive button is visible in Chip's screenshots, suggesting
this reproduction chain), `loadLens()` genuinely 404s and `renderView()`'s
catch block (line 1661) replaces the **entire page** with an error panel.

**Why deleting students fixes it:** with an empty roster,
`state.selectedStudent` holds a now-invalid ID, but `loadLens()` already
has an early guard (`if (!state.selectedStudent)`) that shows a placeholder.
With no students to select, the stale ID can't survive a page reload.

### What it is NOT

This is NOT a privacy-gate conflict between tabs. The privacy/governance
system (`governance.py`, `check_publication_safety`) operates on the
`/api/query` pipeline path, not on lens fetches. No privacy gate fires on
tab navigation.

---

## Bug 2: `/api/poi/progression/{student_id}` returns 404 in packaged app

### Symptoms

"Programme of Inquiry Progression: Request failed: 404" appears consistently
in the Students detail view (Chip's screenshots 18-06-47, 18-06-50, 18-07-40,
18-07-50) and as a toast in the Observe tab (screenshots 18-05-44, 18-06-14).

### Root Cause (confirmed by code and build-spec inspection)

`lv.spec`'s `hiddenimports` lists `src.web` (with a comment explaining the
PyInstaller static-analysis blind spot) — but **none** of
`src.lingua_viva.routers.*` are listed, and `web.py:60-61` loads them
dynamically via `importlib.import_module()`. That's the exact same
static-analysis blind spot the spec's own comment describes, one paragraph up.

In the packaged desktop build, the import fails.
`except ImportError: pass` (line 63) swallows it. Zero routers register.

**Blast radius is bigger than POI.** All three registered routers — sources,
safeguarding, artifacts — die together. Every `/api/sources/*`,
`/api/safeguarding/*`, `/api/artifacts/*`, and `/api/poi/*` route 404s in
the desktop build.

The handler itself is clean — `poi_progression()` just returns
`store.student_summary()`, no 404 path. The route exists and loads correctly
in dev (`python src/web.py`); it only vanishes in the packaged binary.

---

## Fix (six changes across four files)

### F1: Clear `state.selectedStudent` on tab switch (`static/index.html`)

In `switchView()`, clear `state.selectedStudent = ""` before clearing
`voiceLastStudent`.

**Deliberate UX decision, not just a bugfix:** clearing on every tab switch
means a teacher who picks a student in Students, hops to Observe, and comes
back loses their selection. This is the safest behavior for a
privacy-sensitive app — student data should not persist across navigation
contexts without explicit re-selection. Decided, not inherited.

### F2: Guard `loadLens()` in `renderStudents()` with roster membership check

The guard checks `state.selectedStudent` exists in `state.students`, not just
truthiness — truthiness alone doesn't catch stale-but-nonexistent IDs (an
archived student's ID is truthy but not in the roster). If the student is in
the roster and `loadLens()` fails, only the `#lens` panel shows an error —
the roster, growth data, and overview remain visible.

### F3: Clear `state.selectedStudent` in `clearObserveForm()`

Belt-and-suspenders with F1. Any code path that clears the Observe form also
clears the student context.

### F4: Graceful POI degradation, 404 only (`static/index.html`)

`renderPoiProgression()`'s catch block now maps 404 specifically to
"No PoI activity recorded yet" (honest empty state). Any other failure (500,
network) still surfaces the real error message. Blanket-softening would hide
breakage behind a friendly empty state — the same optimistic drift this fix
is cleaning up.

### F5: Add router modules to `lv.spec` hiddenimports

Added `src.lingua_viva.routers`, `.sources`, `.safeguarding`, `.artifacts`,
and their transitive dependencies (`poi_progression`, `coursework_pack`,
`pdf_generator`) to `hiddenimports`.

**Comment-pact** added: every module added to `ROUTER_MODULES` in
`src/lingua_viva/routers/__init__.py` MUST also be added to `lv.spec`.
The split-across-two-files failure mode is exactly how this recurs.

### F6: Loud failure + health surface + CI canary (`src/web.py`, `auto-release.yml`)

Three layers to prevent silent regression:

1. **`web.py`**: The `except ImportError: pass` is replaced with per-module
   try/catch that logs each failure at ERROR level, plus a summary WARNING
   showing `routers_loaded: N/M`. "Cannot load" no longer shares a channel
   with "fine."

2. **`/api/health`**: Now includes `routers_loaded` and `routers_expected`
   fields so packaged-build failures are visible in the health probe.

3. **`auto-release.yml`**: Backend smoke test now asserts
   `routers_loaded == routers_expected && routers_loaded > 0` after health
   passes. A future `lv.spec` drift fails the release instead of shipping
   a build with dead routes.

---

## Kill Criteria

- [ ] K1: Select student in Observe → navigate to Students → no error,
      roster displays normally, lens panel shows "Choose a student" placeholder
- [ ] K2: Select student in Observe → navigate away → return to Observe →
      dropdown shows "Choose a student..." placeholder, not the last student
- [ ] K3: Select student in Students → lens loads → navigate to Observe →
      dropdown shows placeholder → back to Students → no stale lens, no error
- [ ] K4: With 5+ students in roster, rapid tab switching between Observe and
      Students (10 cycles) produces no errors
- [ ] K5: Archive a student while viewing their lens → navigate to another
      tab → navigate back to Students → no full-page error, roster visible
- [ ] K6: POI panel shows "No PoI activity recorded yet" (not "Request
      failed: 404") when no POI data exists
- [ ] K7: `/api/health` returns `routers_loaded == routers_expected`
- [ ] K8: All existing tests pass (`python3 -m pytest tests/ -q`)

---

## What This Does NOT Change

- The `/api/students/{id}/lens` endpoint behavior — unchanged
- The privacy/governance pipeline (`governance.py`) — unchanged
- The lens data model or evidence system — unchanged
- Voice companion student context (`voiceLastStudent`) — already cleared in
  `switchView()`, no change needed
- Parent portal behavior (`state.parentSelectedStudent`) — separate variable,
  unaffected

---

## Patent Relevance (note for the record)

Chip's QA finding constitutes **dated evidence of perspective enforcement in
operation** in the LV embodiment. The privacy-sensitive behavior she observed
— student data that should not persist across viewing contexts — is exactly
the cross-person composition scenario described in Patent Family C (P3),
Claim 10 and section 5. The bug is that enforcement is incomplete (clears on
Students but not on Observe), not that enforcement is absent. The fix
completes the enforcement by clearing identity context on every navigation
boundary.

Chip's independent discovery of this cross-person context-leak behavior is
dated evidence that the perspective enforcement mechanism in Claim 10/§5 is
real and consequential in the LV embodiment. Preserve Chip's report and this
spec in the evidence archive.
