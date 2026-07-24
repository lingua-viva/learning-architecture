# SPEC: Mount /api/stats — System Panel in the Health View (LV-BLT-007)

**Date**: 2026-07-23
**Status**: SHIPPED (uncommitted)
**Author**: Claude, this session
**Trigger**: `AUDIT: Built But Not UI-Mounted (Lingua Viva)` (LV-BLT-007) + this session's own
`dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` — chosen as the deliberate first rep of fixing
this bug class: lowest complexity (one GET, zero params, no form, no write path), so the
fetch->render pattern gets exercised cleanly before the harder items (forms, uploads, writers)
that all build on it.
**Scope**: `static/index.html` only (`renderHealth()`). No backend change — `/api/stats`
(`src/web.py:1367`) is already correct.
**Risk level**: LOW — read-only addition to an existing, already-wired view.

---

## 1. The Problem

`/api/stats` returns real system-scale numbers (`ontology_nodes`, `domains`,
`knowledge_entries`, `citations`, `path_records`, `gap_signals` — matching `MANIFEST.yaml`'s
111 nodes / 178 knowledge entries / 559 citations). Its only consumer anywhere in this codebase
is `FALLBACK_HTML` (`src/web.py:1707`), a break-glass page that only renders if the real
`static/index.html` can't be found — meaning in a working install, this endpoint has **zero real
consumers**. Confirmed by direct grep against the actual served file, not assumed.

Per `ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` Pattern A: this traces to `c2a9bf5`, the initial
wholesale port of Mission Canvas's engine — this was MC's internal dev-debug readout, carried over
before Lingua Viva's own teacher-facing design existed. It was never wired because it was never
decided whether it should be.

**Decision made here**: yes, it should be a real feature — "see the system's own scale/health
inside the app" is a legitimate thing for a teacher or coordinator to be able to check, and the
data is already correct and free (no new backend work). Home for it: the existing **Health**
view (`renderHealth()`, `static/index.html:1334`) — it already exists, already shows system
status (Doctor checks), and already has a nav entry. No new nav item needed.

## 2. What To Build

In `renderHealth()`, after the existing Doctor-checks panel, add a second panel: fetch
`/api/stats` and render its 6 fields as stat cards, matching the exact visual pattern already
used in `renderPrivacy()` (`static/index.html:1379-1383`, `<div class="grid three">` of
`<div class="panel"><h3>${number}</h3><p>label</p></div>` cards) — reuse the existing style, don't
invent a new one.

```
async function renderHealth() {
  setTitle("Health", "doctor");
  $("content").innerHTML = `<div class="panel"><h2>Running Doctor...</h2></div>`;
  const data = await api("/api/health");
  let stats = null;
  try { stats = await api("/api/stats"); } catch {}
  const bundleButton = ...  // unchanged
  $("content").innerHTML = `
    <div class="view-head">...</div>          <!-- unchanged -->
    <div class="panel">...</div>               <!-- unchanged Doctor checks panel -->
    ${stats && !stats.error ? `
      <div class="panel" style="margin-top:14px;">
        <h3>System</h3>
        <div class="grid three" style="margin-top:10px;">
          <div class="panel"><h3>${stats.ontology_nodes}</h3><p>ontology nodes</p></div>
          <div class="panel"><h3>${stats.domains}</h3><p>domains</p></div>
          <div class="panel"><h3>${stats.knowledge_entries}</h3><p>knowledge entries</p></div>
          <div class="panel"><h3>${stats.citations}</h3><p>citations</p></div>
          <div class="panel"><h3>${stats.path_records}</h3><p>reasoning paths recorded</p></div>
          <div class="panel"><h3>${stats.gap_signals}</h3><p>gap signals</p></div>
        </div>
      </div>` : ""}`;
  ...
}
```

Exact UI call site this creates (per `ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` §6.1 — state it,
don't leave it implicit): `renderHealth()` in `static/index.html`, `try { stats = await
api("/api/stats"); }`, triggered whenever a teacher/coordinator opens the Health nav item — no
new nav entry, no new button, reuses the existing one.

Fail open: if `/api/stats` errors (matches the route's own existing `except Exception as e: return
{"error": str(e)}` shape) or the fetch throws, the System panel simply doesn't render — Doctor
checks above it are unaffected. This mirrors `renderPrivacy()`'s own `try {...} catch {}` pattern
for its two API calls, not a new convention.

## 3. What Does NOT Change

- `/api/stats` itself — untouched, already correct.
- Doctor checks panel, support-bundle button — untouched, unchanged behavior.
- No new nav item, no new route, no new backend code at all.

## 4. Build Order

1. Add the `stats` fetch + System panel to `renderHealth()` (15 min)
2. Live-verify — see §5, both senses (10 min)
3. `python3 scripts/check_ui_contract.py --bump` (this changes `static/index.html`) (5 min)

**Total**: ~30 min — deliberately small, this is the first rep.

## 5. Definition of Done

Per `ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` §6.3: state which kind of verification each item
is, don't blur "I called the route" with "I used the app."

- [ ] `renderHealth()` renders a System panel with all 6 stat fields, styled consistently with
      the existing Privacy view's stat-card pattern
- [ ] **Reachability-verified** (not just correctness-verified): open the actual running app
      (dev server or installed desktop app), click the Health nav item, see real numbers —
      not a curl call to `/api/health` or `/api/stats` in isolation
- [ ] If `/api/stats` is made to fail (e.g. temporarily break an import), confirm the Health view
      still renders the Doctor panel correctly and simply omits the System panel — no crash, no
      blank page
- [ ] UI contract bumped, `python3 -m pytest -q tests/` passes
- [ ] `dev/INDEX.md` updated with this spec's row, referencing this as the first fix applied from
      `ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md`'s list

## 6. Provenance

`/api/stats` read in full (`src/web.py:1367-1385`). `FALLBACK_HTML`'s exclusive-consumer status
confirmed by direct grep + read this session (see `ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md`
§3, Pattern A, §8 for full trace). `renderHealth()` and `renderPrivacy()` read in full
(`static/index.html:1334-1344`, `:1373-1383`) to match existing visual/error-handling
conventions rather than inventing new ones.
