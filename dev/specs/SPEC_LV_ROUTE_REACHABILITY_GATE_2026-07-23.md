# SPEC: Route Reachability Gate (LV-BLT-Prevention-0)

**Date**: 2026-07-23
**Status**: SHIPPED (uncommitted)
**Author**: Claude (this session)
**Trigger**: `dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` traced 9 backend
capabilities (`LV-BLT-001..009`) that are built, tested, and sometimes even
hardened 15 times over — with no UI control anywhere in the app that ever
calls them. Its §5 proposed a mechanical fix but explicitly left it unbuilt
("not built by this document — this is the spec for whoever builds it
next"). This spec is that build.
**Scope**: One new manifest, one new checker script, one preflight wire-in,
regression tests. No route was added, removed, or wired to a UI this session
— this spec only makes existing unreachability *visible and enforced*, it
does not resolve any of the 13 gaps it surfaces (see §4).
**Risk level**: LOW — purely additive tooling; the manifest classifies
routes that already exist, it doesn't change any of them.

---

## 1. The problem, restated narrowly

`contracts/UI_CONTRACT.yaml` already hash-locks `static/index.html`/`sw.js`/
`src/web.py` so *unintentional* drift in those files fails preflight. It
answers "did the UI change." It has never answered a different, equally
important question: **"does every backend route have a UI control that
actually calls it?"** Four independent root-cause patterns (wholesale infra
ports, backend-ahead-of-UI, eval-green-mistaken-for-reachable,
partial-batch wiring — see the root-cause doc §3) all produce the same
invisible symptom, and nothing in this repo's tooling has ever caught any of
them before an operator-run manual audit did.

## 2. What was built

- **`contracts/ROUTE_REACHABILITY.yaml`** — every route in `src/web.py`
  (57 at first ship, 55 as of this spec's last edit — 2 dead routes were
  removed by later mount-fix lanes; see §4) classified into exactly one of:
  - `reachable_from_ui`: route + a literal string proven (by the checker,
    every run) to still exist in the file that triggers it — usually
    `static/index.html`, sometimes `static/sw.js` or `static/manifest.json`
    for PWA-infrastructure routes that are triggered by an HTML tag or
    browser API rather than a JS `fetch()`.
  - `intentionally_backend_only`: route + `status` (`permanent` — a real,
    examined decision, e.g. an external system's webhook target — or
    `deferred_undecided` — backend exists, no UI does, and nobody has yet
    decided its fate) + a `reason` grounded in the root-cause doc's commit
    trace where one exists.
- **`scripts/check_route_reachability.py`** — `check()` (default) fails if
  any live route is unclassified, classified in both lists, if a
  `reachable_from_ui` entry's call-site literal no longer exists in its
  target file (this is what catches a future route being silently
  un-wired from its UI — the exact Pattern-D failure mode), if the **same**
  METHOD+path is registered twice in `src/web.py` (FastAPI lets the second
  definition silently shadow the first — a real bug, added during the
  self-repass, §7), or if a manifest entry references a route that's been
  removed (also added during the repass — see §7 for why this needed to be
  in `check()` itself, not just `--sync-stale`). `--sync-stale` still
  exists as a standalone way to see just the stale-entry list.
- **`src/lingua_viva/cli.py`**: wired as preflight check #6, alongside the
  existing `ui_contract` check — same subprocess-and-report pattern, so it
  runs on every `lv preflight` the same way the UI contract check already
  does.
- **`tests/test_route_reachability.py`** — 9 tests: the real check passes
  against the live repo; every live route is classified exactly once;
  every `intentionally_backend_only` entry has a valid status and reason;
  every `reachable_from_ui` entry has a call_site; an unclassified new
  route fails the check; a removed call-site fails the check; a route
  registered twice fails the check; a stale manifest entry fails `check()`
  directly, not just `--sync-stale`; `--sync-stale` correctly reports (not
  deletes) a manifest entry for a route that no longer exists. (All
  fixture-based except the first — none touch the real repo.)

## 3. Design decisions worth stating explicitly

- **Call-site literals are hand-written, not auto-inferred.** An earlier
  attempt at deriving call sites automatically (regex-matching `fetch()`/
  `api()` invocations and their template-literal prefixes) works but is
  fragile and adds a second thing that can silently drift. The manifest
  proposal in the root-cause doc itself says "the exact fetch()/form-action
  call-site string expected" — a human-chosen, human-reviewed literal is
  the more honest version of "prove it," not a weaker one.
- **`deferred_undecided` is a real status, not a euphemism for "later."**
  13 of the 57 routes landed there when this manifest first shipped. That
  number is deliberately uncomfortable — it is the accurate count of
  routes this manifest could not, in good conscience, call either
  "reachable" or "permanently backend-only." Shrinking that number is real
  follow-up work (§4), not something this spec quietly resolves by
  reclassifying entries `permanent` to make the count look better. (It is
  already shrinking for the right reason: a concurrent lane picked up
  `GET /api/stats` within the hour and moved it to `reachable_from_ui` by
  actually wiring a UI control — see §4's note on `SPEC_LV_BLT007_SYSTEM_STATS_MOUNT`.
  12 remain as of this spec's last edit.)
- **This manifest found 13 gaps, not the root-cause doc's 9.** Building the
  actual enumeration (rather than relying on a prior manual audit) surfaced
  4 more: `GET /api/curriculum/unit/{unit_id}`, `GET /api/teacher/today`,
  and `GET /api/session` were not named in `LV-BLT-001..009` at all. This
  is itself evidence for the root-cause doc's central claim — a mechanical
  check finds what a vigilance-based audit, done carefully, still misses.

## 4. What this spec deliberately does NOT do

- Does not wire any of the 13 `deferred_undecided` routes to a UI control.
  That is 13 separate, real decisions (build a UI, delete the route, or
  reclassify `permanent`) — collapsing them into this spec would repeat
  the exact "backend shipped, UI deferred to an unnamed follow-up" pattern
  this spec exists to stop enabling.
- Did not fix the pre-existing, unrelated `ui_contract` preflight failure
  found while wiring this in (hash mismatch on the 3 protected files at the
  then-current v21 lock, with no intervening commit touching them per
  `git log` — looked like a line-ending/checkout artifact, not real
  content drift). Flagged, not fixed, in this spec's first draft — a
  concurrent lane (`SPEC_LV_BLT007_SYSTEM_STATS_MOUNT`) independently
  re-locked the contract to v22 shortly after, which resolved it. Left the
  root cause of the v21 drift itself uninvestigated — if it recurs, it's
  worth understanding rather than just re-locking again each time.
- Does not reclassify `WS /ws` or `GET /api/stats` even though
  `EXECUTION_PROMPT_LV_BLT007_SYSTEM_STATS_MOUNT_2026-07-23.md` (found
  in-repo, apparently an in-flight concurrent lane) suggests someone may
  already be acting on `LV-BLT-007` directly. If that lane lands a UI call
  site for `/api/stats`, this manifest's entry for it must move from
  `intentionally_backend_only` to `reachable_from_ui` in the same change —
  noted here so it isn't missed.

## 5. Definition of Done

- [x] All live routes in `src/web.py` classified in
      `contracts/ROUTE_REACHABILITY.yaml` (57 at ship, 55 now)
- [x] `scripts/check_route_reachability.py` passes against the real repo
- [x] Wired into `lv preflight` as check #6
- [x] 9 regression tests, all passing
- [x] Every `deferred_undecided`/`permanent` entry has a grounded reason,
      citing the root-cause doc's commit trace where one exists
- [x] Self-repass done (§6): fixed one dead-code comment that asserted
      nothing, and closed a real gap where stale manifest entries could
      only be seen via a separate manual command
- [ ] 8 `deferred_undecided` routes resolved (down from 13 at ship, via
      other concurrent lanes) — explicitly out of scope for this spec,
      tracked here as the honest remaining count

## 6. Self-repass (same day, after initial ship)

Asked to review my own work rather than assume the first pass was correct.
Found two real issues by re-reading the checker script fresh:

1. **Dead code that claimed to check something it didn't.** The original
   `check()` built a `seen_dupes` dict with a comment claiming duplicate
   route strings needed handling, then never used it for anything —
   an abandoned thought that looked like a check but wasn't one. Fixed:
   `live_routes()` now documented as duplicate-preserving (not silently
   deduplicated into a set before anyone can inspect it), and `check()`
   now actually fails if the same METHOD+path is registered twice in
   `src/web.py` — a real bug class (FastAPI's second definition silently
   shadows the first, so the code as read isn't the code as it runs), not
   hypothetical.
2. **Stale manifest entries were only visible on request, not by default.**
   `--sync-stale` reported them, but `check()` — the thing that actually
   runs in `lv preflight`, on every run — did not. That meant catching a
   stale entry still depended on someone remembering to run a second
   command, which is precisely the failure mode this whole gate exists to
   remove ("prove it, don't rely on vigilance"). Fixed: `check()` now
   fails on any manifest entry whose route no longer exists in
   `src/web.py`, in addition to everything it already checked.

Neither issue had actually caused a problem yet — a fresh check confirmed
zero true duplicates and zero stale entries in the real manifest at repass
time (other lanes cleaned up their own entries correctly when they removed
routes). This was a repass for latent gaps, not a bug report from
production. 2 new tests added (9 total); full targeted suite re-run clean
before and after.

## 7. Provenance

Built directly against `src/web.py` (regex-parsed for the live route list,
cross-checked by hand against `grep -oE` output — 57 routes, exact match),
`static/index.html`/`static/sw.js`/`static/manifest.json` (read to confirm
each `reachable_from_ui` call-site literal actually exists verbatim before
writing it into the manifest, not assumed from memory), and
`dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` (source of the 9 named
findings' reasons and commit citations). Checker run against the live repo
before and after fixing 14 initially-wrong call-site literals (POST routes'
`api()` calls take a second argument, so a literal ending in a bare `")`
never matches — caught by running the checker, not by inspection).
