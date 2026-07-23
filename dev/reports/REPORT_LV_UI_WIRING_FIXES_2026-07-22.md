# Report: UI Wiring Fixes — Add Student, RTI Buttons, Ask Error Honesty

**Date**: 2026-07-22  
**Spec**: `dev/specs/SPEC_LV_UI_WIRING_FIXES_2026-07-22.md`  
**Builder**: Kiro CLI  
**Status**: SHIPPED (uncommitted)

## Fixes

| # | Bug | What Changed | Verified |
|---|-----|-------------|----------|
| 1 | Cannot add a student | `POST /api/students` route in `src/web.py`; Add Student form (name, grade, home language) in `renderStudents()` (`static/index.html`); on submit POSTs then refetches roster immediately | API: POST returns `student_id` + `display_name`, new student appears in GET /api/students. Validation: empty name → 400. Browser live-test not possible from CLI. |
| 2 | Confirm/Defer buttons do nothing | `StudentLensStore.record_rti_decision()` + `rti_decisions` table in `src/education/student_lens.py`; `POST /api/students/{id}/rti/decision` route in `src/web.py`; buttons in `loadLens()` now have ids + event listeners that call the route and show "Recorded." | API: confirm/defer both return `{"status":"recorded"}`. Invalid decision → 400. Browser live-test not possible from CLI. |
| 3 | Ask renders raw `ModuleNotFoundError` as a real answer | Backend: `except (ModuleNotFoundError, ImportError)` now returns `"Ask isn't able to answer free-form questions in this build yet."` + `unavailable: true`. Frontend: `askQuestion()` separates error from result paths; `renderMessage()` renders error with `unavailable` badge only (no route/model/citation/Why? badges). | Unit tests confirm: ModuleNotFoundError → honest message, no raw exception. Generic errors still pass through. On this machine `ontology.engine` imports fine, so the real app returns real answers; the error path was verified via mocking. |

## Test Results

- **530 passed**, 20 failed (all pre-existing Windows-only: file-permission checks, POSIX shell tests, Ollama embedding service)
- `py_compile` passes for both `src/web.py` and `src/education/student_lens.py`
- UI contract bumped to v18 — `test_ui_contract.py` passes

## Files Modified

- `src/web.py` — POST /api/students route, POST /api/students/{id}/rti/decision route, ModuleNotFoundError/ImportError handler
- `src/education/student_lens.py` — `rti_decisions` table in schema, `record_rti_decision()` method
- `static/index.html` — Add Student form in `renderStudents()`, Confirm/Defer button wiring in `loadLens()`, error-distinct render in `askQuestion()`/`renderMessage()`
- `contracts/UI_CONTRACT.yaml` — v18 bump-log entry

## Files Added (tests)

- `tests/test_ask_error_honesty.py` — 3 tests (ModuleNotFoundError, ImportError, generic Exception)
- `tests/test_ui_wiring_fixes.py` — 5 tests (add student success/validation, RTI confirm/defer/invalid)

## Explicitly Not Touched (per spec Hard Rules)

- `_seed_demo_roster()` — 3 demo students unchanged
- `rti_tier_history` / observation append-only semantics — unchanged
- `src/pipeline.py`'s `ontology.engine` import — not fixed, out of scope (deferred ~2 weeks)
- No commit made — everything staged for operator

## Limitation

Could not browser-live-test from CLI. All 3 features verified via API calls against the running server (port 8787) and via httpx/TestClient unit tests. The frontend JavaScript changes (form submission, button handlers, error render styling) are structurally correct but were not exercised in a real browser during this session.
