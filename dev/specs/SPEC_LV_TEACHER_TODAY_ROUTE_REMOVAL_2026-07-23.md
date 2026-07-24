# SPEC: Remove GET /api/teacher/today — Genuine Duplicate, Confirmed

**Date**: 2026-07-23
**Status**: APPROVED — ready to build
**Author**: Claude, this session
**Trigger**: `contracts/ROUTE_REACHABILITY.yaml`, `GET /api/teacher/today`, `deferred_undecided`.
Fifth fix in the mount-fix series, same shape as `SPEC_LV_UNOBSERVED_ROUTE_REMOVAL_2026-07-23.md`
— a second confirmed case where the original manual audit's "duplicate" call holds up. With this
one, every route that was ever labeled a duplicate in the original audit has now been
individually re-verified rather than taken on faith (one turned out wrong — RTI — two turned out
right — unobserved, this one).
**Scope**: `src/web.py` (remove the route + its private helper `_today_from_schedule`, now
unused by anything else), `tests/test_teacher_schedule.py` (remove), one-line cleanup in
`tests/test_teacher_ui_phase2.py` (drop the dead OR-branch), `contracts/ROUTE_REACHABILITY.yaml`
(remove the entry).
**Risk level**: LOW — same evidence shape as the unobserved removal; confirmed no other consumer.

---

## 1. The Problem, Verified Not Assumed

`GET /api/teacher/today` (`src/web.py:437`) calls `_today_from_schedule()` (`src/web.py:366`),
which resolves the configured day's schedule entry into `{day, configured, grade, unit, unit_id,
cefr_targets, source, source_citation}`. `BriefService._today()` (`src/lingua_viva/brief.py:56-74`)
**independently reimplements the identical logic** — same schedule-lookup, same field shape
(minus `source_citation`, a cosmetic difference) — and `GET /api/brief`'s response already
includes it verbatim under the `"today"` key.

Verified three ways, not assumed:
1. Read both implementations side by side — same day-key resolution, same "not configured"
   short-circuit, same unit-lookup call into `CurriculumService`.
2. Checked every consumer of the standalone route: `grep -rln "api/teacher/today"` across
   `tests/` and `static/index.html` finds `tests/test_teacher_schedule.py` (tests the route
   directly, both its scenarios) and `tests/test_teacher_ui_phase2.py` — the latter's own
   assertion, `assert "/api/teacher/today" in html or "My Schedule" in html`, is an OR that has
   **always** been passing on its second branch: the literal route string does not appear
   anywhere in `static/index.html` today (confirmed by direct grep), so this test's real,
   load-bearing assertion has only ever been "My Schedule" text exists (`static/index.html:859`,
   Home's "Set up your schedule in Settings → My Schedule" copy) — independent of this route
   entirely.
3. `test_brief_endpoint.py::test_brief_returns_today_when_schedule_configured` and
   `::test_brief_returns_unconfigured_today_when_no_schedule` already cover both branches of the
   shared logic through the route that's actually wired.

## 2. What To Build

1. Remove `@app.get("/api/teacher/today")` / `teacher_today()` from `src/web.py`.
2. Remove `_today_from_schedule()` (`src/web.py:366-382`) — confirm via grep it has no other
   caller before deleting (only `teacher_today()` calls it today).
3. Remove `tests/test_teacher_schedule.py` — both its tests are scenario-duplicates of
   `test_brief_endpoint.py`'s existing coverage.
4. In `tests/test_teacher_ui_phase2.py`, change
   `assert "/api/teacher/today" in html or "My Schedule" in html` to
   `assert "My Schedule" in html` — the OR-branch that was actually passing, stated plainly
   instead of left as a stale reference to a route that no longer exists.
5. Remove the `GET /api/teacher/today` entry from `contracts/ROUTE_REACHABILITY.yaml`.

## 3. What Does NOT Change

- `BriefService._today()` / `GET /api/brief` — untouched, the surviving correct implementation.
- `CurriculumService.get_unit()`/`get_grade()` — untouched, used by both the old and surviving
  path; only the duplicate caller in `web.py` goes away.
- Home's "My Schedule" copy and behavior — untouched, was never driven by the removed route.

## 4. Build Order

1. Confirm `_today_from_schedule()` has no other caller (2 min)
2. Remove route + helper from `src/web.py` (5 min)
3. Remove `tests/test_teacher_schedule.py`, fix the OR-assertion in
   `tests/test_teacher_ui_phase2.py` (5 min)
4. Remove the manifest entry, run `python3 scripts/check_route_reachability.py` (5 min)
5. `python3 -m pytest -q tests/` — confirm `test_brief_endpoint.py`'s two today-tests and the
   fixed `test_teacher_ui_phase2.py` assertion pass (10 min)

**Total**: ~25 min.

## 5. Definition of Done

- [ ] Route, handler, and now-orphaned `_today_from_schedule()` helper removed from `src/web.py`
- [ ] `tests/test_teacher_schedule.py` removed
- [ ] `tests/test_teacher_ui_phase2.py`'s assertion no longer references the removed route
- [ ] `contracts/ROUTE_REACHABILITY.yaml` no longer references this route
- [ ] `python3 scripts/check_route_reachability.py` passes cleanly
- [ ] `python3 -m pytest -q tests/` passes; `test_brief_endpoint.py`'s two today-scenario tests
      specifically confirmed passing — they're now solely responsible for this logic's coverage
- [ ] **Reachability-verified, inverted sense** (per the unobserved spec's same convention): open
      the actual app, confirm Home's "Set up your schedule..." copy and any today's-plan display
      still work exactly as before
- [ ] `dev/INDEX.md` updated, noting this closes out the last "possibly-duplicate" route the
      manifest hadn't yet individually re-verified

## 6. Provenance

`_today_from_schedule()` and `BriefService._today()` read side by side in full. Consumer search
run against `tests/` and `static/index.html` directly — the `test_teacher_ui_phase2.py`
OR-assertion's actual passing branch confirmed by grepping `static/index.html` for the literal
route string (zero matches) before concluding which side of the OR was load-bearing, not guessed
from the assertion's phrasing alone.
