# SPEC: LV Sidebar Design — Pertinent Subset from MC's Sidebar App Design Doc

**Source**: adapted from `mission-canvas/dev/SIDEBAR_APP_DESIGN_DOC_2026-07.md` (MC's Canvas-Tile-Rail sidebar architecture — 24 canvases, voice-command contract, gravity/recede mechanics), selectively mined for what actually applies to LV's much smaller surface.
**Status**: DRAFT, unbuilt
**Date**: 2026-07-20

---

## 0. Why This Spec Exists, and Why It's Small

MC's sidebar doc solves problems LV doesn't have: 24 canvases across verticals that a single user pins/expands/recedes, a voice-command channel that can mutate UI state, gravity-based re-ranking of tiles by usage, domain-accent theming across 8+ professional verticals. LV is one product (K-5 Italian curriculum) with one flat, role-swapped nav list and no voice output layer (explicit non-goal — see `dev/LV_HAPPY_STATE_P0_2026-07-20.md`'s "What This Document Deliberately Does Not Claim").

Confirmed against running source, not assumed: LV's nav is 8 teacher items + 4 admin items + 6 shared utility items = 17 buttons total, rendered from three flat JS arrays (`static/index.html:480-503`), swapped wholesale on role switch. No nesting, no drag-and-drop, no collapse/expand, no shelf of hidden items.

Most of MC's doc has no LV analog and would be over-engineering for a 17-button nav. What's actually useful, ported down and rescaled: (1) turning today's implicit nav-item tuples into a documented, testable contract; (2) an accessibility pass MC's doc specifies well that LV's current markup lacks; (3) explicit state-transition documentation; (4) a lightweight design-token naming pass; (5) the acceptance-criteria and phased-build discipline as a *pattern*, cut down to LV's actual size.

---

## 1. What LV's Sidebar Actually Is Today (confirmed against source, 2026-07-20)

- `static/index.html:418-427` — `<aside class="sidebar">` containing a brand button (`#brand-home`), `<nav id="primary-nav">`, `<nav id="utility-nav">`. Single level. No nesting, no Canvas/Experience hierarchy.
- Nav items are plain `[id, label, icon]` tuples in three JS arrays (`static/index.html:480-503`):
  - `teacherNav` (8): home, plan, prepare, observe, students, assess, ask, parents
  - `adminNav` (4): programme, evidence, capacity, trends
  - `utilityNav` (6, shared by both roles): why, health, privacy, profile, settings, reflect
- `renderShell()` (`static/index.html:529-546`) selects `teacherNav` or `adminNav` wholesale based on `state.role`, re-renders both `<nav>` lists on every state change, and rebinds click handlers each time. No incremental patching, no per-item persisted state beyond `active` class matching `state.view`.
- Role switching is a full nav-set swap via the `role-choice` modal (`static/index.html:442-453`) → `setRole()` (`static/index.html:520-527`), persisted to `localStorage["lvRole"]`. The topbar "Change role" button re-opens the modal. No third (student) role — explicitly deferred, `ADDENDUM_THREE_TIER_SIDEBAR_2026-07-16.md` §Iteration 4 ("Student Surface (Future, Separate — NOT Phase 1-3)").
- Sidebar is a fixed 200px column (`static/index.html:75`), single flat color scheme via CSS custom properties (`--brand`, `--ink`, `--muted`, `--line`), no per-domain accent theming, no "More" shelf — there's nothing to shelve; 17 buttons fit without scrolling on any reasonable viewport.
- Gaps confirmed by reading the markup, not assumed: no `aria-current` on the active nav button (only a CSS class, `.active`), no explicit `:focus-visible` styling (button reset at `static/index.html:121-131` zeroes `border-color`, default focus ring is unverified), no `aria-label` distinguishing the two `<nav>` elements.

This is deliberately minimal and it works for LV's scope. The goal of this spec is **not** to grow LV's sidebar toward MC's complexity — it's to close a few concrete, low-risk gaps using MC's doc as a source of good patterns, scaled to a 17-button nav instead of a 24-canvas rail.

---

## 2. Explicitly Out of Scope (present in MC's doc, deliberately not ported to LV)

| MC concept | Why it doesn't apply to LV |
|---|---|
| Canvas Tile / Experience Tile two-level model | LV has one product, not a multi-vertical rail — nothing to nest |
| Voice command contract, `VoiceRuntime`, `AppShellObserver`, `screen_payload.sidebar_command` | LV has no voice output layer (confirmed non-goal, happy-state doc) |
| Gravity/recede, usage-based re-ranking, "More Canvases" shelf | Nothing to recede — 17 static buttons, no overflow |
| Domain-accent color system (Legal/Healthcare/Finance/etc. hex tokens) | LV is single-domain; no per-vertical accent need |
| Onboarding-to-sidebar seeding (multi-select domains → seed tiles) | LV's onboarding is one binary choice (teacher/coordinator), already built and sufficient |
| Conversation Flow Coupling / Screen Observer Integration | Both voice-dependent, N/A |

If any of these become relevant later (e.g. LV grows a voice layer, or the deferred student surface turns into a real multi-tile workspace), MC's source doc remains the pattern to port then — not something to pre-build now against a hypothetical.

---

## 3. What's Pertinent, Adapted to LV's Scale

### 3.1 Nav Item Contract (from MC's Tile schema, flattened to one level)

Turn the implicit `[id, label, icon]` tuple into a documented shape, so future additions aren't guessing at structure and drift is catchable:

```
NavItem {
  id: string                              // matches state.view and data-view attr
  label: string                           // visible text
  icon: string                            // single emoji glyph
  roles: ("teacher" | "coordinator")[]    // which role array(s) include it
  group: "primary" | "utility"
}
```

This describes what already exists (`teacherNav`/`adminNav`/`utilityNav`) — it is not a new mechanism. The value is having one canonical shape to test against, the same way `contracts/UI_CONTRACT.yaml` already guards other surfaces from silent drift.

### 3.2 Explicit State Declaration (from MC's State Machine section, trimmed)

LV's sidebar-relevant state is two fields: `state.role` (`""` | `"teacher"` | `"coordinator"`) and `state.view` (a nav item id). Document the legal transitions so a future contributor doesn't have to reverse-engineer `renderShell`/`setRole`:

- `role: "" → "teacher" | "coordinator"` — via the role-choice modal (first load, or explicit "Change role")
- `view: any → any nav item id valid for the current role` — via nav button click, or `brand-home` click (resets to the role's default view: `home` for teacher, `programme` for coordinator)

No new state is being proposed here — just a written-down contract for what's already true in code.

### 3.3 Accessibility Pass (from MC's Accessibility section — the sharpest actionable gap)

MC's doc requires WCAG AA, full keyboard nav, and explicit active-state signaling for every tile. LV's current nav buttons (`navButton()`, `static/index.html:548-551`) have none of:

- `aria-current="page"` on the active nav button — currently signaled only via the `.active` CSS class, invisible to screen readers
- A visible `:focus-visible` outline — relies on browser default, unverified against the button-reset styles that zero `border-color` (`static/index.html:121-131`)
- `aria-label` on the two `<nav>` elements, so assistive tech can distinguish "primary" navigation from "utility" navigation

Concrete, low-risk fix: add `aria-current` inside `navButton()`, add `aria-label="Primary"` / `aria-label="Utility"` to the two `<nav>` tags, add one `:focus-visible` CSS rule to `.nav button`. Markup/CSS only, no logic change. Does not require a UI_CONTRACT bump unless the button's structural shape changes (attribute additions alone should not require one — confirm against `contracts/UI_CONTRACT.yaml`'s actual scope before treating this as certain).

### 3.4 Lightweight Design Tokens (from MC's Visual Design spec, trimmed from ~40 tokens to 3)

MC's doc defines dimension/motion/typography tables sized for a rail with expand/collapse animation LV doesn't have — LV needs no transition timing for collapse, because nothing collapses. What's worth naming, for consistency if the nav ever grows: values that are currently inline literals, not custom properties:

- `--lv-sidebar-width: 200px` (literal today at `static/index.html:75`, also needed in the responsive breakpoint at lines 393-413)
- `--lv-nav-gap: 4px` (literal today at `static/index.html:119`)
- `--lv-nav-row-min-height` (currently implicit via button padding, not a named value)

This is a naming/DRY pass on values LV already uses, not new visual design. MC's actual color and motion values are not portable — different brand, different product.

### 3.5 Acceptance Criteria (adapted from MC's Acceptance Criteria table, cut to what's testable here)

| # | Criterion | How verified |
|---|---|---|
| 1 | Active nav item has both `.active` class and `aria-current="page"` | Manual check + grep after fix |
| 2 | Both `<nav>` elements have a distinct `aria-label` | Manual check + grep after fix |
| 3 | Full keyboard tab order reaches every nav button; focus state is visibly rendered | Manual keyboard walk against the running app |
| 4 | Nav item counts (8 teacher / 4 admin / 6 utility) match a documented contract, asserted by a test | New/extended assertion in `tests/test_ui_contract.py` |
| 5 | No change to role-switch behavior, view routing, or any API call | Existing suite stays green (476/476 as of the P0 pass) |
| 6 | UI_CONTRACT bump applied only if markup structure changes beyond attribute additions | `python3 scripts/check_ui_contract.py --bump`, run only if needed |

### 3.6 Build Order (adapted from MC's 6-phase order, cut to 2 — there's nothing else to sequence)

1. **Phase 1 — Accessibility + token naming** (§3.3, §3.4): CSS/markup only, no behavior change, lowest risk, ships alone.
2. **Phase 2 — Nav contract + test coverage** (§3.1, §3.2, §3.5 row 4): formalizes the existing arrays into a documented, tested shape so future nav-item additions can't silently drift from the role/group model.

There is no Phase 3+. There is no gravity, voice, or multi-canvas seeding to build toward. If LV's product surface grows beyond one role-swapped flat list — e.g. the deferred student surface in `ADDENDUM_THREE_TIER_SIDEBAR_2026-07-16.md` §Iteration 4 becomes real — MC's fuller doc becomes relevant again and should be re-consulted at that point, not pre-built now against a hypothetical.

---

## 4. Relationship to Existing Specs

- Does **not** amend or contradict `ADDENDUM_THREE_TIER_SIDEBAR_2026-07-16.md` — that spec's role/item decisions were re-confirmed against current code in §1 above and are out of scope for revision here.
- Companion to, not a replacement for, `SPEC_LV_CLAUDIA_LENS_REPASS_2026-07-20.md` — that pass reviews copy/voice/UX-sequencing; this spec is structural/accessibility only, no copy changes.

## 5. Deliverable

If executed: a small diff to `static/index.html` (Phase 1: `navButton()` + two `<nav>` tags + one CSS rule) and `tests/test_ui_contract.py` (Phase 2: nav-item-count assertion), left **uncommitted** per this repo's standing convention — the operator holds the sole commit window.
