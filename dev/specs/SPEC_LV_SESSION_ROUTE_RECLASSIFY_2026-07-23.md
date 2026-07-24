# SPEC: Reclassify GET /api/session — Permanent, Not a UI Gap

**Date**: 2026-07-23
**Status**: APPROVED — ready to build
**Author**: Claude, this session
**Trigger**: `contracts/ROUTE_REACHABILITY.yaml`, `GET /api/session` listed `deferred_undecided`.
Third fix in the mount-fix series — deliberately **not** a UI-mount this time. The manifest's own
philosophy (`contracts/ROUTE_REACHABILITY.yaml` header) treats `deferred_undecided` →
`permanent`-with-evidence as an equally valid resolution to `deferred_undecided` →
`reachable_from_ui`. Building a UI indicator for a value that can structurally never be true
would be actively misleading, not a fix.
**Scope**: `contracts/ROUTE_REACHABILITY.yaml` only, plus a docstring clarification on the route
itself. No UI change, no removal of `src/session.py`'s functions (see §4 — real but
out-of-scope follow-up).
**Risk level**: LOW — a manifest reclassification + a one-line docstring; no runtime behavior
changes at all.

---

## 1. The Problem, And Why It Isn't What It Looks Like

`GET /api/session` (`src/web.py:1388`) returns `session_status()` — reads a `.mc_session` file
and reports `{"active": false}` if it doesn't exist. `contracts/ROUTE_REACHABILITY.yaml` lists
this `deferred_undecided`, same as every other mount-fix target in this series — but this one is
different in kind, confirmed by tracing every possible way `.mc_session` could ever come to
exist:

- `start_session()` (`src/session.py:60`) is the **only** function that creates `.mc_session`.
- `grep -rn "start_session\b"` across the entire repo finds exactly one caller:
  `archive/mc-engine/mc_cli.py:368` — the **archived** legacy Mission Canvas CLI.
- `archive/` is explicitly excluded from the packaged desktop app
  (`desktop/package.json`'s `"!archive/**"` filter, confirmed this session in
  `SPEC_LV_DESKTOP_ONTOLOGY_PACKAGING_2026-07-22.md`) and `CLAUDE.md` states archived legacy
  backend machinery "should stay archived unless explicitly restored."
- `src/lv_cli.py` (Lingua Viva's own, live CLI) has zero reference to session start/end/status.

**Conclusion, not assumption**: `.mc_session` cannot be created by any code path that runs in
this app, ever, under any current build. `GET /api/session` will report `{"active": false}` on
every single real install, permanently — not because a UI is missing, but because the thing it
reports on cannot happen. The module's own docstring confirms the intent was always MC-CLI-only:
*"mc session start ... mc session end ... 5 queries about the same legal matter accumulate paths
in one session"* — a Mission Canvas legal-research use case, never a Lingua Viva one.

Building a "Session: active" indicator in the UI for a value that can never read true would be
worse than the current gap — it would look like a broken feature rather than a correctly-absent
one.

## 2. What To Build

In `contracts/ROUTE_REACHABILITY.yaml`, move `GET /api/session` from `reachable_from_ui`'s
sibling list into `intentionally_backend_only`, `status: permanent`:

```yaml
  - route: "GET /api/session"
    status: permanent
    reason: >-
      Reports on .mc_session, which only src/session.py's start_session() ever creates — and
      that function's only caller anywhere in this repo is archive/mc-engine/mc_cli.py, the
      archived legacy MC CLI (excluded from the packaged app, desktop/package.json
      "!archive/**"). No code path in Lingua Viva's actual runtime (src/lv_cli.py, the desktop
      app, any live route) ever calls start_session() — this route will report
      {"active": false} on every real install, permanently. A UI control for this would be
      misleading, not a fix. See dev/specs/SPEC_LV_SESSION_ROUTE_RECLASSIFY_2026-07-23.md.
```

In `src/web.py`, add a one-line docstring to `session_info()` stating the same thing, so the next
person reading the route itself (not just the manifest) sees why it has no UI:

```python
@app.get("/api/session")
async def session_info():
    """Reports .mc_session status — permanently inactive in this app; only the archived MC CLI
    (archive/mc-engine/mc_cli.py, excluded from the packaged build) ever creates that file.
    See dev/specs/SPEC_LV_SESSION_ROUTE_RECLASSIFY_2026-07-23.md."""
    from src.session import session_status
    status = session_status()
    return status or {"active": False}
```

## 3. What Does NOT Change

- `src/session.py` — untouched. `start_session`/`end_session`/`increment_session`/
  `get_active_session` all remain exactly as they are.
- `/api/query`'s use of `get_active_session()`/`increment_session()` (`src/web.py:1457,1496`) —
  untouched; these no-op safely today (no session ever active) and continue to.
- No UI change anywhere.

## 4. Noticed But Deliberately Not Fixed Here (scope discipline)

`src/session.py`'s functions are themselves only reachable from archived code — a legitimate
future cleanup candidate (either delete them, or formally document them as
kept-for-archive-compatibility). That is a code-deletion decision affecting a different file with
its own blast radius (would need to confirm nothing else, including tests, depends on the
functions existing even if uncalled in practice) — out of scope for this spec, which only
resolves the manifest's `deferred_undecided` entry. Flagging it here rather than silently
noticing and dropping it.

## 5. Build Order

1. Update `contracts/ROUTE_REACHABILITY.yaml` (10 min)
2. Add the docstring to `session_info()` (5 min)
3. `python3 scripts/check_route_reachability.py` — confirm it passes with the route now correctly
   classified (10 min)
4. `python3 -m pytest -q tests/`

**Total**: ~25 min — smallest in the series so far; this is a decision-and-document fix, not a
build.

## 6. Definition of Done

- [ ] `contracts/ROUTE_REACHABILITY.yaml` lists `GET /api/session` under
      `intentionally_backend_only`, `status: permanent`, with the evidence above in `reason`
- [ ] `session_info()` has the clarifying docstring
- [ ] `python3 scripts/check_route_reachability.py` passes
- [ ] `python3 -m pytest -q tests/` passes — no test currently asserts this route is
      `deferred_undecided`, but confirm nothing breaks
- [ ] `dev/INDEX.md` updated, explicitly noting this spec resolved a `deferred_undecided` entry
      by reclassification rather than by building a UI, and logging §4's noticed-not-fixed item
      for whoever picks up repo cleanup next

## 7. Provenance

`grep -rn "start_session\b"` run against the full repo (not just `src/`) — the archive-only
caller is the load-bearing fact this whole spec rests on, confirmed directly, not assumed from
the module docstring alone. `desktop/package.json`'s `archive/**` exclusion cross-checked against
`SPEC_LV_DESKTOP_ONTOLOGY_PACKAGING_2026-07-22.md`, built earlier this session. `src/session.py`
read in full.
