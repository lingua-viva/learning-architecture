# SPEC: Mount PUT /api/students/{id}/rti — Direct Support-Tier Override

**Date**: 2026-07-23
**Status**: SHIPPED (uncommitted)
**Author**: Claude, this session
**Trigger**: `contracts/ROUTE_REACHABILITY.yaml` (built by `SPEC_LV_ROUTE_REACHABILITY_GATE_2026-07-23.md`),
`deferred_undecided`. Second fix in the mount-fix series, chosen deliberately as the first
**write-path** rep — `SPEC_LV_BLT007_SYSTEM_STATS_MOUNT_2026-07-23.md` proved the read-only
fetch->render pattern; this one adds a control + validation + error handling, one level up in
complexity, in a view (`loadLens()`) whose sibling control (Confirm/Defer) was already
successfully wired earlier today — same file, same proven conventions, minimal new pattern risk.
**Scope**: `static/index.html` only (`loadLens()`). No backend change — the route
(`src/web.py:1154`) and its store method (`student_lens.py:511`) are already correct and
already have their own docstring explaining the design.
**Risk level**: LOW — additive control in an already-wired view; write path but well-guarded
(int validation, 404 on unknown student, already server-side).

---

## 1. The Problem

`PUT /api/students/{student_id}/rti` lets a teacher directly set a student's RTI support tier
(1/2/3) as an independent decision — the route's own docstring is explicit that this is
**distinct** from the tier changes that ride along with an observation, and
`StudentLensStore.update_rti_tier()`'s docstring further distinguishes it from the
already-wired Confirm/Defer flow: Confirm/Defer responds to a *system-suggested* tier change;
this route is for a tier decision a teacher makes independently (its own docstring example: "a
team meeting decision"). **The original manual audit (`LV-BLT-006`) mischaracterized this route
as a duplicate of Confirm/Defer** — `contracts/ROUTE_REACHABILITY.yaml`'s more careful pass
corrected that: it's a genuinely distinct, valuable capability with zero UI anywhere.

No UI control anywhere in `static/index.html` calls this route today (confirmed via
`contracts/ROUTE_REACHABILITY.yaml`, which lists it as `deferred_undecided`, and via direct grep
against the served file).

## 2. What To Build

In `loadLens()` (`static/index.html:1161`), inside the existing `decisionControls` block (only
shown when `showDecisionControls` is true — confirmed via all 5 call sites that this flag is
`false` exactly when `loadLens` renders into the read-only Observe-view side panel, `obs-lens`,
where a mid-observation tier change would be the wrong affordance) — add a tier-select dropdown
+ "Set Tier" button alongside the existing Confirm/Defer buttons, visually and functionally
distinct so a teacher doesn't confuse "confirm the system's suggestion" with "override the tier
myself":

```
const decisionControls = showDecisionControls ? `
  <div class="source-line"><span class="badge warn">System suggests; teacher reviews before any support-tier decision</span></div>
  <div class="row"><button type="button" id="rti-confirm">Confirm</button><button type="button" id="rti-defer">Defer</button><span id="rti-decision-status"></span></div>
  <div class="row" style="margin-top:8px;">
    <label>Set support tier directly
      <select id="rti-tier-select">
        <option value="1" ${lens.rti_current_tier === 1 ? "selected" : ""}>Tier 1</option>
        <option value="2" ${lens.rti_current_tier === 2 ? "selected" : ""}>Tier 2</option>
        <option value="3" ${lens.rti_current_tier === 3 ? "selected" : ""}>Tier 3</option>
      </select>
    </label>
    <button type="button" id="rti-set-tier">Set Tier</button>
    <span id="rti-tier-status"></span>
  </div>` : "";
```

Handler, added alongside the existing `handleRtiDecision`, same fetch/status-span conventions:

```
async function handleSetTier() {
  const newTier = Number($("rti-tier-select").value);
  const res = await fetch(`/api/students/${state.selectedStudent}/rti`, {
    method: "PUT", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({new_tier: newTier})
  });
  const data = await res.json();
  if (res.ok) {
    $("rti-tier-status").textContent = "Tier updated.";
    await loadLens(targetId, showDecisionControls);   // refresh — new tier now shown in the header line too
  } else {
    $("rti-tier-status").textContent = data.error || "Failed.";
  }
}
$("rti-set-tier").addEventListener("click", handleSetTier);
```

`trigger` is deliberately omitted from the request body — the route already defaults it to
`"teacher_decision"` server-side (`src/web.py:1161`), which is exactly right for a manual UI
action; no need to expose that as a field.

Exact UI call site this creates (state it, per `ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` §6.1):
`loadLens()` in `static/index.html`, `handleSetTier()`, `fetch(\`/api/students/${state.selectedStudent}/rti\`, {method: "PUT", ...})`
— reachable only from the Students tab's lens panel (`showDecisionControls=true`), never from the
Observe-view read-only panel.

## 3. What Does NOT Change

- The route, `update_rti_tier()`, and their existing validation/error shapes — untouched, already
  correct.
- Confirm/Defer flow — untouched, remains the separate suggestion-response mechanism.
- The read-only Observe-view lens panel (`obs-lens`, `showDecisionControls=false`) — gets no new
  control, matches its existing read-only intent.

## 4. Build Order

1. Add the tier-select + button markup inside `decisionControls` (10 min)
2. Add `handleSetTier()` + event listener (10 min)
3. Live-verify — see §5, both senses (15 min): includes confirming the 400 (invalid tier — not
   reachable via the dropdown's own constrained options, but confirm the route's own validation
   still holds if hit directly) and 404 (unknown student) paths render `data.error` in
   `#rti-tier-status` rather than throwing
4. `python3 scripts/check_route_reachability.py` — must now show this route moved out of
   `deferred_undecided` (update `contracts/ROUTE_REACHABILITY.yaml`'s entry to
   `reachable_from_ui` with this call site)
5. `python3 scripts/check_ui_contract.py --bump`

**Total**: ~45 min.

## 5. Definition of Done

- [ ] `loadLens()` renders the tier-select + Set Tier control whenever `showDecisionControls` is
      true, and does not render it in the Observe-view read-only panel
- [ ] **Reachability-verified** (not just correctness-verified): open the actual running app,
      go to Students, select a student, change the tier dropdown, click Set Tier, see "Tier
      updated." and the header's "support tier N" line reflect the new value — not a curl call to
      the PUT route in isolation
- [ ] Error path reachability-verified: trigger a failure (e.g. stop the server mid-request, or
      temporarily break the route) and confirm `#rti-tier-status` shows the error text, no crash
- [ ] `contracts/ROUTE_REACHABILITY.yaml` updated: this route moves from
      `intentionally_backend_only` (`deferred_undecided`) to `reachable_from_ui`
- [ ] `python3 scripts/check_route_reachability.py` passes
- [ ] UI contract bumped, `python3 -m pytest -q tests/` passes
- [ ] `dev/INDEX.md` updated, referencing this as the second fix in the mount-fix series and the
      correction to `LV-BLT-006`'s original mischaracterization

## 6. Provenance

Route and store method read in full (`src/web.py:1154-1174`, `student_lens.py:511-...`) —
the docstrings' own "distinct from Confirm/Defer" claim is what overturned the original audit's
"duplicate" characterization, not assumed. `loadLens()` and all 5 of its call sites read in full
to confirm `showDecisionControls`'s existing semantics before reusing it, rather than guessing.
`contracts/ROUTE_REACHABILITY.yaml` (built earlier today by a separate lane) is this spec's
source of truth for which routes remain unaddressed — read in full before selecting this one.
