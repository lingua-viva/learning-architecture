# SPEC: Remove GET /api/students/unobserved — Genuine Duplicate, Confirmed

**Date**: 2026-07-23
**Status**: APPROVED — ready to build
**Author**: Claude, this session
**Trigger**: `contracts/ROUTE_REACHABILITY.yaml`, `GET /api/students/unobserved`,
`deferred_undecided`. Fourth fix in the mount-fix series — the second non-UI resolution, and
**the first confirmed case where the original manual audit's "duplicate" call was actually
right** (contrast `SPEC_LV_RTI_DIRECT_TIER_MOUNT_2026-07-23.md`, where the same audit's
"duplicate" call for a sibling route was wrong). The lesson from this series isn't "never trust
the audit" or "always trust it" — it's "verify each one independently," and this route is the
proof that sometimes the original call holds up.
**Scope**: `src/web.py` (remove the route), `tests/test_unobserved_students.py` (remove — tests
dead functionality once the route is gone), `contracts/ROUTE_REACHABILITY.yaml` (remove the
entry entirely — a deleted route isn't `permanent`, it doesn't exist).
**Risk level**: LOW — confirmed no other code path or test outside its own dedicated test file
depends on this route; the underlying logic it duplicates is separately, adequately tested.

---

## 1. The Problem, Verified Not Assumed

`GET /api/students/unobserved` (`src/web.py:1081`) computes "which students haven't been
observed in N days" directly against the student store. `src/lingua_viva/brief.py`'s
`BriefService._unobserved()` **independently reimplements the identical computation** — and
`GET /api/brief` (confirmed `reachable_from_ui`, consumed by Home) already exposes the result of
that computation as `unobserved_count` + up to 5 `unobserved_students` names.

This is a genuine duplicate, not a mischaracterized-but-actually-distinct case like
`PUT /api/students/{id}/rti` was. Confirmed three ways before concluding this, not assumed from
the original audit alone:
1. Read `BriefService._unobserved()`'s implementation — same stale/recent-observation logic as
   the standalone route.
2. Checked for any consumer of the standalone route besides its own dedicated test file —
   `grep -rln "api/students/unobserved"` across `tests/` finds only
   `tests/test_unobserved_students.py` itself.
3. Confirmed `tests/test_brief_endpoint.py::test_brief_returns_unobserved_students` already
   exercises the same underlying scenario (a student with no observations shows up in
   `unobserved_students`) through the route that's actually used — so removing the standalone
   route's dedicated test file does not create a coverage gap for the shared logic.

## 2. What To Build

1. Remove the `@app.get("/api/students/unobserved")` route and its handler function entirely
   from `src/web.py` (`:1081-` through the end of `unobserved_students()`).
2. Remove `tests/test_unobserved_students.py` — it tests only this route; once the route is
   gone, the file tests nothing live. Do **not** try to repoint it at `BriefService._unobserved()`
   directly — `test_brief_endpoint.py` already covers that path through the route that's real.
3. Remove the `GET /api/students/unobserved` entry from `contracts/ROUTE_REACHABILITY.yaml`
   entirely (not move it to `intentionally_backend_only` — a route that no longer exists isn't
   "backend-only," it's gone; `scripts/check_route_reachability.py` should be confirmed to not
   choke on a manifest entry referencing a route it can no longer find — if it does, that's a
   real bug in the checker worth a one-line note in the report, not a reason to leave the entry
   sitting there).

## 3. What Does NOT Change

- `BriefService._unobserved()` and `GET /api/brief` — untouched; this is the surviving,
  already-correct implementation.
- `test_brief_endpoint.py` — untouched, already sufficient.
- Nothing in `static/index.html` references the removed route today (confirmed — it was never
  wired, that's the entire premise of this spec existing).

## 4. Build Order

1. Remove the route from `src/web.py` (5 min)
2. Remove `tests/test_unobserved_students.py` (2 min)
3. Remove the manifest entry, run `python3 scripts/check_route_reachability.py` — confirm clean,
   note if the checker errors on a stale reference rather than just no longer listing it (5 min)
4. `python3 -m pytest -q tests/` — confirm no drop in pass count beyond the intentionally-removed
   test file's own count, and specifically confirm `test_brief_endpoint.py` still passes (10 min)

**Total**: ~20 min.

## 5. Definition of Done

- [ ] Route and handler removed from `src/web.py`
- [ ] `tests/test_unobserved_students.py` removed
- [ ] `contracts/ROUTE_REACHABILITY.yaml` no longer references this route at all
- [ ] `python3 scripts/check_route_reachability.py` passes cleanly
- [ ] `python3 -m pytest -q tests/` passes; `test_brief_endpoint.py::test_brief_returns_unobserved_students`
      specifically confirmed still passing (this is the test now solely responsible for covering
      the shared unobserved-detection logic)
- [ ] **Reachability-verified, inverted sense**: open the actual app, confirm Home's unobserved
      indicator (the card driven by `/api/brief`) still works exactly as before — a deletion spec's
      "verify reachability" means confirming nothing that WAS reachable broke, not confirming
      something new became reachable
- [ ] `dev/INDEX.md` updated, explicitly noting this is the series' first confirmed-correct
      original-audit "duplicate" call, contrasted with the RTI spec's correction

## 6. Provenance

`BriefService._unobserved()` read in full (`src/lingua_viva/brief.py`). Consumer search
(`grep -rln`) run against all of `tests/`, not just an assumption from file naming.
`test_brief_endpoint.py` read in full to confirm equivalent scenario coverage before scoping the
dedicated test file for removal, not assumed adequate.
