# PROMPT — LV Grind Wave 2 (paste into a fresh window in ~/learning-architecture)

You are taking over the Lingua Viva repo (`~/learning-architecture`) for a solo grind
session. The operator is away; his standing mandate applies to you directly:

> "100% take the reins and drive that repo all the way to being able to be used by
> teachers tomorrow... just grind until cannot grind anymore. identify everything and
> anything that we don't know."

The previous window (2026-08-09) shipped all five LV goals live — desktop-v0.2.47 is
downloadable at linguaviva.art, contract v136, suite 2204 green. Your job is NOT new
goal areas. Your job is to close every gap that wave left open, then keep auditing and
fixing until a full pass surfaces nothing new you can fix. Working teachers depend on
this; the safeguarding paths in particular must never regress.

## Read first, in this order (disk is truth — never trust summaries over files)

1. `AGENTS.md` — rule 0 defines "pushed/done". Nothing counts until the download is
   live-verified with real bytes.
2. `CLAUDE.md` + `publication-policy.md` — privacy rules, synthetic-names-only.
3. `dev/SESSION_REPORT_LV_BUILD_WAVE_2026-08-09.md` — what shipped, how, and the 7 gaps.
4. `dev/SPEC_LV_GRIND_WAVE_2_2026-08-09.md` — YOUR spec. G1–G8 with acceptance criteria.
5. `contracts/UI_CONTRACT.yaml` bump log (v134–v136) + `src/lingua_viva/routers/__init__.py`
   — the router plug-in pattern. New API surface goes in routers, never web.py edits
   without a contract bump.

## Execution order

- **G1** restricted-ledger review workflow → **G2** PoI UI (needs a contract bump — batch
  protected-file changes coherently) → **G3** C8 root-cause (measure first) → **G4**
  holiday calendar → **G5** sharing-matrix unification → **G6** coursework enrichment →
  **G7** search ranking (stretch) → **G8** grind loop.
- G1/G3/G4 are independent — parallelize with builder agents on the router plug-in
  pattern if useful (three agents did this with zero collisions last wave). You integrate;
  agents never edit web.py or the contract.
- Commit in reviewable slices with the repo convention `<type>(<scope>): <description>`.

## Discipline (each of these was learned the hard way — do not relearn them)

- **Verify before ledgering.** A thing is done when its test runs green NOW, not when the
  code looks right. `cmd | tail; echo $?` reports tail's exit — use `${PIPESTATUS[0]}`.
- **Failure-class fixes**: when a test or audit finds a bug, fix the class at the
  chokepoint and add a test that locks the class. Precedent: last wave, "his dad hits him
  at home" classified GREEN — the fix broadened the pattern class and class-locked it.
- **Live-wire audit**: after building anything, prove production call sites actually use
  it. Last wave the safeguarding gate existed with ZERO callers until integration caught
  it. Grep for the call sites; don't assume.
- **Protected files**: `src/web.py` changes require `scripts/check_ui_contract.py --bump`,
  a reverse-chronological bump-log comment in `contracts/UI_CONTRACT.yaml`, and moving
  `EXPECTED_VERSION` in `tests/test_ui_contract.py`.
- **Background runs**: alive = output file growing (check twice); pgrep is never proof.
- **Privacy**: no real names ever — students are Nora Rossi / Marco Bianchi / Rafael;
  the school is "a 4-campus IB international school". RED safeguarding content never
  leaves the restricted store — every change near capture paths re-runs
  `tests/test_safeguarding.py` and `tests/test_brief_extensions.py`.

## Blocked-on-operator (surface, don't solve)

Safeguarding channel/Drive-folder config values, `PERPLEXITY_API_KEY` live-fire, and the
auto-release PAT secret are operator decisions. Build code up to the config boundary,
then list exactly what he must set (key names + where) in your closing report. When
shipping, execute the known manual PAT-gap step: delete + re-push the release tag with
non-Actions credentials (v0.2.46/47 precedent), then watch the Desktop Release build and
verify assets with a ranged GET.

## Definition of "cannot grind anymore"

You are done only when: (1) G1–G6 shipped with tests and G8's audit loop — harness,
wiring audit, UI-mount audit, fresh-eyes teacher walkthrough — completes a full pass
finding nothing new you can fix; (2) full suite green, preflight 6/6, harness ≥17/19
with C8 fixed or honestly measured and ledgered; (3) the release is live-verified per
rule 0; (4) `dev/SESSION_REPORT_LV_GRIND_WAVE_2_<date>.md` records per-item outcomes,
new gaps found, and the exact operator config list. If you run out of context, write the
report FIRST at whatever state you reached — an honest partial report beats a silent
partial build.

Now read the five documents above and begin.
