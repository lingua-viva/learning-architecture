# BUILD PROMPT: Fix Observe/Students Tab State Leak

**Spec:** `dev/SPEC_OBSERVE_STUDENTS_STATE_LEAK_2026-08-12.md`
**Priority:** P0
**Scope:** 3 changes, all in `static/index.html`
**Estimated size:** ~10 lines changed

---

## Context

A QA audit found that selecting a student in the Observe tab causes that
student's data to persist in global state across tab navigations. When the
user then navigates to the Students tab, the stale student context triggers
an auto-load of the student's lens, which can fail and replace the entire
Students page with an error message.

Root cause: `state.selectedStudent` is a global variable set in the Observe
tab but never cleared on navigation. `renderStudents()` unconditionally calls
`loadLens()` which fires against the stale selection.

## What to build

Make exactly three changes in `static/index.html`:

### 1. Clear `state.selectedStudent` in `switchView()`

Find `switchView()` (~line 1565). Add `state.selectedStudent = "";` after
`state.view = view;` and before `voiceLastStudent = null;`.

### 2. Guard `loadLens()` in `renderStudents()`

Find the `await loadLens();` call at the end of `renderStudents()` (~line
2509). Wrap it:

```javascript
if (state.selectedStudent) {
  try {
    await loadLens();
  } catch (err) {
    console.warn("Lens load failed for student:", state.selectedStudent, err);
    const lensEl = $("lens");
    if (lensEl) lensEl.innerHTML = '<div class="panel"><p>Could not load student lens. Please re-select the student.</p></div>';
  }
}
```

### 3. Clear `state.selectedStudent` in `clearObserveForm()`

Find `clearObserveForm()` (~line 2190). Add `state.selectedStudent = "";`
as the first line of the function body.

## What NOT to change

- Do not modify any API endpoints or backend code
- Do not change the lens data model
- Do not modify `state.parentSelectedStudent` (parent portal is separate)
- Do not add new state variables -- the fix is clearing existing state
- Do not change `voiceLastStudent` handling -- already correct

## Verification

Run the 5 kill criteria from the spec:

1. Select student in Observe -> Students tab -> no error, roster visible
2. Select student in Observe -> navigate away -> return -> placeholder shown
3. Select student in Students -> Observe -> back to Students -> no stale data
4. Rapid tab switching (10 cycles) -> no errors
5. All existing tests pass (`python3 -m pytest tests/ -q`)

## One-liner

Clear `state.selectedStudent` on every tab switch so student identity context
never leaks across navigation boundaries.
