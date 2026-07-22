# Prompt: LV Sidebar Design — Phase 1+2 Implementation (Codex variant)

Copy everything below the line into a fresh Codex session, run from the repo root (`learning-architecture`). Codex has shell + file access in this repo; no network access is needed.

---

You are running as Codex inside the `learning-architecture` repo (Lingua Viva). This is a **build task**, not a review — patch first, test second, explain third. Do not stop at design unless genuinely blocked.

**Required reading, in order**:
1. `CLAUDE.md` (repo root) — publication-safety rules and repo architecture. You are bound by these for anything you write.
2. `dev/specs/SPEC_LV_SIDEBAR_DESIGN_2026-07-20.md` — the full spec. Read §1-§3 closely: §1 is the confirmed current state of `static/index.html`'s sidebar (line references included), §2 is an explicit exclusion list (do not build any of it — it's there so it isn't silently re-proposed), §3 is the two-phase scope you're implementing.
3. `static/index.html` — read the actual current markup/JS this spec is patching: the `<aside class="sidebar">` block (~line 418-427), the `role-choice` modal (~442-453), the `teacherNav`/`adminNav`/`utilityNav` arrays (~480-503), `renderShell()` and `navButton()` (~529-551), and the `.sidebar`/`.nav`/`.nav button` CSS (~78-137).
4. `contracts/UI_CONTRACT.yaml` and `tests/test_ui_contract.py` — understand what the UI contract actually guards before deciding whether your changes require a bump. The spec's own guess (attribute-only additions likely don't require one) is not authoritative — verify against the real contract scope.

**The task in one sentence**: implement Phase 1 (accessibility + token naming, §3.3-§3.4 of the spec) and Phase 2 (nav-item contract + test coverage, §3.1-§3.2 and §3.5 row 4) exactly as scoped — no more, no less. This is a small, low-risk patch, not a redesign.

**Scope, precisely**:
- Phase 1: in `navButton()`, add `aria-current="page"` to the active button. Add `aria-label="Primary"` to `#primary-nav` and `aria-label="Utility"` to `#utility-nav`. Add a `:focus-visible` CSS rule to `.nav button` (the existing reset zeroes `border-color` — make sure focus is actually visible against it, don't just add a rule that gets overridden). Name the three literals in §3.4 as CSS custom properties (`--lv-sidebar-width`, `--lv-nav-gap`, `--lv-nav-row-min-height`) and use them at their existing call sites (`static/index.html:75`, `:119`, and the responsive breakpoint at `:393-413`) — this is a rename, not a value change; visual output must not shift.
- Phase 2: write down the `NavItem` shape from spec §3.1 (as a comment or a small doc block near the nav arrays — your call on the lightest-weight form that's still genuinely checkable, not a runtime type system LV doesn't otherwise have). Add a test to `tests/test_ui_contract.py` asserting the nav item counts (8 teacher / 4 admin / 6 utility) and that every id referenced in the arrays has a corresponding view handler — whatever the existing test file's idiom is for this kind of structural assertion, match it rather than inventing a new pattern.

**Hard constraints**:
- Do not build anything listed in the spec's §2 exclusion table (Canvas/Experience tiles, voice command contract, gravity/recede, domain-accent theming, canvas-seeding onboarding). If you find yourself writing more than the nav arrays + a few CSS rules + one test addition, you have drifted out of scope — stop and re-read §2.
- Do not change role-switch behavior, view routing, or any `/api/*` call. Acceptance criterion #5 in the spec requires the existing suite stays green — run it and confirm the count, don't just assume it.
- Do not touch `ADDENDUM_THREE_TIER_SIDEBAR_2026-07-16.md`'s role/item decisions (which items exist, which role sees which) — this pass is structural/a11y only, not a nav redesign.
- If your markup change ends up structural (not just attribute additions) and trips `python3 scripts/check_ui_contract.py`, run it with `--bump` and say so explicitly in your summary — don't silently bump, and don't silently skip a needed bump either.
- Publication safety (`CLAUDE.md`): no real student data, no institution names, no colleague names anywhere you touch.
- Whatever you change, leave it **uncommitted** — the operator holds the sole commit window in this repo. Do not run `git commit`.

**Verification, before you call this done**:
- Run the full test suite and report the pass count (expect it to match or exceed the current baseline — check `dev/INDEX.md`'s most recent P0 report for that number, don't guess it).
- Manually verify in the running app (`python3 -m src.lv_cli serve 8787`) that: the active nav button has `aria-current="page"` in the rendered DOM, tabbing through the sidebar shows a visible focus ring, and the visual layout is unchanged (the token rename must be a no-op visually).
- Confirm role switching (teacher ↔ coordinator) still swaps the nav set correctly — this is the one behavior this patch must not touch, so it's worth a direct check.

When done, give a short final message (under 150 words): what changed (file:line references), the test count before/after, whether a UI_CONTRACT bump was needed and whether you applied it, and nothing else. No restated framing.
