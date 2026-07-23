# SPEC: UI Wiring Fixes — Add Student, Dead RTI Buttons, Ask Error Honesty (LV-DATA-IN-1)

**Date**: 2026-07-22
**Status**: APPROVED — ready to build
**Author**: Claude (this session), operator-directed scope
**Trigger**: First live walkthrough of the app (operator + Claude, 2026-07-22) surfaced
these as concrete, reproduced bugs — not speculative.
**Scope**: `static/index.html` (Students, Ask views), `src/web.py` (new routes),
`src/education/student_lens.py` (one new method)
**Risk level**: LOW — additive routes, no schema migration, no change to existing
observation/lens read paths.
**Depends on**: Nothing. No dependency on `SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` —
this spec can run in full parallel with it and with Specs 2-4.
**Sibling specs**: `SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` (Tier 0, independent)

---

## 1. The Problems (all reproduced live, 2026-07-22)

### 1a. Cannot add a student
`_seed_demo_roster()` (`src/web.py:180-206`) hardcodes exactly 3 students (Marco, Nora,
Luca) on first run. There is no `POST` route to create a new student, and `renderStudents()`
(`static/index.html:809-823`) only renders the existing roster — no add-student form exists
anywhere in the UI. The backend (`StudentLensStore.create_lens()`,
`src/education/student_lens.py:219-277`) fully supports creating a new lens — this is a
missing route + missing form, not a missing capability.

**Operator's own framing**: "if we can't add students, the lenses are not useful."

### 1b. Confirm/Defer buttons do nothing
`loadLens()` (`static/index.html:832`) renders `<button type="button">Confirm</button>
<button type="button">Defer</button>` for the RTI tier-change proposal
(`rti_proposals` field, `src/web.py:701-711`) — **zero event listeners are attached to
either button.** Clicking them is a no-op. No backend route exists to record a teacher's
confirm/defer decision at all.

### 1c. Ask renders a raw Python error as if it were a real answer
Reproduced verbatim by operator: asking "how do i add a lens" returns a chat bubble
styled exactly like a normal governed response — `local` / `model unavailable` / `0.0s`
/ `Manuale v1` / `Why?` badges — but the content is the literal string
`No module named 'ontology.engine'`.

Root cause chain:
- `query_endpoint` (`src/web.py:971`) → `run_teacher_query()`
  (`src/lingua_viva/app.py:16-19`) → `from src.pipeline import Pipeline` →
  `src/pipeline.py:38` does a **module-level** `from ontology.engine import
  OntologyEngine, ClassificationResult`.
- `ontology/` does not exist anywhere in this repo — it's MC-engine code `CLAUDE.md`
  says must stay in `archive/mc-engine/` unless explicitly restored. So **every**
  `/api/query` call fails at import time, before any real query logic runs.
- The backend actually handles this correctly — `except Exception as e: error =
  {"type": "error", "error": str(e), ...}` (`web.py:1065-1068`) returns clean JSON,
  no crash, no leaked traceback.
- The bug is entirely in the frontend: `askQuestion()`
  (`static/index.html:881-906`) does `text: data.result?.content || data.error ||
  "No response."` — an error and a real answer render through the exact same
  code path with the exact same styling.

**Explicitly out of scope for this spec** (operator's own call): making Ask actually
answer questions. That requires porting a real classifier/retrieval engine and is
deferred to the next session (~2 weeks out). This spec only makes the current
non-functional state **honest** instead of broken-looking.

## 2. What To Build

### 2a. Add Student

1. New route `POST /api/students` in `src/web.py`, near the existing `/api/students`
   GET (line 647). Payload: `display_name` (required), `campus`, `grade_level`,
   `home_languages` (list[str]), `learning_differences` (list[str]),
   `rti_current_tier` (default 1). Calls `store.create_lens(**payload)` via the
   existing `_with_student_store()` helper. Returns `{"student_id": ..., "display_name": ...}`.
   - Validate `display_name` is non-empty — return 400 with a clear message if not.
   - Do not touch `_seed_demo_roster()` — it should keep seeding the 3 demo students
     on an empty store; this is additive.
2. In `static/index.html`, `renderStudents()`: add an "Add Student" form (name,
   grade, home language — keep it to the minimum viable fields; campus/learning
   differences can be added later via the lens detail view, not blocking this spec)
   above or beside the Roster panel. On submit, `POST /api/students`, then re-run
   `ensureStudents()` (force a refetch — check whether it currently caches; if it
   does, invalidate the cache) and re-render the roster so the new student appears
   immediately without a manual page reload.

### 2b. Confirm/Defer — wire to a real, small backend

1. Add `StudentLensStore.record_rti_decision(student_id: str, decision: Literal["confirm","defer"], note: str = "") -> None` in `src/education/student_lens.py`. Keep it simple: append to a new `rti_decisions` table
   (`student_id, decision, note, decided_at`) — do NOT try to reconcile this with the
   `rti_tier_history` append-only observation log; it's a separate decision record, not
   an observation.
2. New route `POST /api/students/{student_id}/rti/decision` in `src/web.py`. Payload:
   `{"decision": "confirm" | "defer"}`. Reject anything else with 400.
3. In `static/index.html` `loadLens()`: wire both buttons to this route. On success,
   show a small inline confirmation ("Recorded.") and re-fetch the lens so
   `rti_proposals` reflects the decision (if `evaluate_rti_rules()` naturally stops
   re-proposing after a decision is recorded, great; if it doesn't, that's fine for
   this spec — just recording the decision honestly is the bar here, not building
   full proposal-suppression logic).

### 2c. Ask error honesty

1. **Backend** (`src/web.py`, the `except Exception as e:` block at line 1065):
   catch `ModuleNotFoundError`/`ImportError` specifically and return a distinct,
   non-alarming message instead of the raw exception string — e.g. `"Ask isn't able
   to answer free-form questions in this build yet. Try Plan, Prepare, or Observe for
   now."` Keep the generic `except Exception` fallback for genuinely unexpected
   errors, but don't let a known, permanent condition (missing ontology engine) look
   like a transient crash.
2. **Frontend** (`static/index.html`, `askQuestion()` / `renderMessage()`): give
   error responses (`data.error` present, no `data.result`) a visually distinct
   render — no routing/model/citation badges (those imply a real governed answer
   happened), a clear "error" or "unavailable" styling instead. Do not remove the
   `Why?` link machinery for real responses — only change how an error response
   renders.

## 3. What Does NOT Change

- `_seed_demo_roster()`'s 3 demo students — untouched, still seed on empty store.
- `rti_tier_history` / observation append-only semantics — untouched.
- The actual Ask/query reasoning pipeline — untouched. This spec does not attempt to
  fix `src/pipeline.py`'s `ontology.engine` dependency; it only contains the failure
  honestly. Real fix is 2-weeks-out, separate spec.
- `avoid_pairing_with` / trauma-flag handling — untouched, not in scope here.

## 4. Build Order

1. `StudentLensStore.record_rti_decision()` + `rti_decisions` table (20 min)
2. `POST /api/students` route (20 min)
3. `POST /api/students/{id}/rti/decision` route (15 min)
4. Add Student form in `renderStudents()` (30 min)
5. Wire Confirm/Defer buttons in `loadLens()` (20 min)
6. Ask backend error-message fix (15 min)
7. Ask frontend error-render fix (20 min)
8. Live-verify all 3 flows in the running app (not just curl) — this is a UI-facing
   spec; a passing curl request is not sufficient evidence (30 min)

**Total**: ~2.5 hours

## 5. Definition of Done

- [ ] Can add a new student from the Students tab UI and see it appear in the roster
      immediately, no reload
- [ ] New student is a real `create_lens()` row — verify via `GET /api/students`
- [ ] Confirm/Defer buttons are clickable, record a real decision, show a confirmation
- [ ] Asking any question in Ask no longer shows `No module named 'ontology.engine'`
      styled as a real answer — shows an honest "not available yet" message with
      distinct (non-badge) styling
- [ ] Existing 3 demo students, their lenses, and their observations are unaffected
- [ ] `python3 -m pytest -q tests/` still passes
- [ ] Live-verified in the actual running desktop app (screenshot each of the 3 fixes),
      not just via `curl`/API calls

## 6. Provenance

- All 3 bugs reproduced live by operator + Claude this session (screenshots: Home,
  Observe, Students, Ask). Root-caused by direct code inspection: `static/index.html`
  lines 809-906, `src/web.py` lines 180-206, 647-716, 971-1068, `src/pipeline.py:38`.
- Operator's explicit priority: Add Student first ("if we can't add students, the
  lenses are not useful"); Ask's real fix explicitly deferred 2 weeks by operator.
