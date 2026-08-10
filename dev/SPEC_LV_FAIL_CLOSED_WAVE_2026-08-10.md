# SPEC — LV Fail-Closed Wave (2026-08-10)

Status: DRAFT — awaiting operator review with the next window.
Priority: F1 = P0, F2 = P0, F3 = P1, F4 = gate.
Origin: three-window reflection synthesis (2026-08-10). Governing finding:
"a fail-open safety feature is worse than its absence — it manufactures
trust." Supporting findings: permanent `expected_fail` masks regressions;
built-but-not-called regenerates after every build and needs a standing
instrument, not another manual audit.

The three build items are independent. F4 is the exit gate.

---

## F1 (P0) — Adversarial safeguarding corpus as a standing fixture

### Problem
`classify_severity()` (`src/lingua_viva/safeguarding.py:202`) once returned
GREEN for "His dad hits him at home" — found by accident. The fix class
(ambiguity round-up at :225-229, personal-context secondary signal at
:237-255) is live, but it is verified only against whatever phrases past
sessions happened to try. There is no adversarial corpus anywhere in
`tests/` (verified by grep 2026-08-10). The corpus must be a *growing*
fixture: every future incident adds a phrase, and the phrase can never
regress again.

### Build
1. Create `tests/fixtures/safeguarding_corpus.yaml` — versioned, reviewed
   like code. Two sections:
   - `must_flag`: entries `{phrase, minimum_tier: AMBER|RED, source: <incident/session ref>, added: <date>}`.
     Minimum tier means: classifier tier rank must be **>=** this rank
     (`_TIER_RANK`, safeguarding.py:74). Round-up above minimum is a pass.
   - `must_stay_green`: entries `{phrase, source, added}` — benign classroom
     phrases (e.g. "he hit the ball hard at recess", "she fell during PE and
     laughed about it") that must remain GREEN. Over-flagging erodes teacher
     trust and buries real signals — alert fatigue is itself a safety failure.
2. Seed corpus (minimum viable, grow from here):
   - `must_flag` ≥ 25 phrases covering: the original incident phrase verbatim;
     verb-form/tense variants (hits/hit/hitting/was hit); passive voice;
     reported speech ("he told me his dad..."); euphemism ("gets in trouble
     at home", "dad gets angry with him"); disclosure-adjacent ("asked me not
     to tell anyone"); physical signs ("unexplained bruising", "flinches when
     approached"); neglect ("comes to school hungry every day", "same clothes
     all week"); each RED_INDICATOR family (:94) and AMBER family (:158)
     represented by at least one *paraphrase that does not literally contain
     the indicator string*.
   - `must_stay_green` ≥ 10 phrases: sports/play contact, fictional/book
     content, idioms ("hit the books"), self-descriptions of ordinary upset.
3. New test `tests/test_safeguarding_corpus.py`:
   - Loads the fixture, runs every `must_flag` phrase through
     `classify_severity()`, asserts tier rank >= minimum rank. On failure the
     assertion message prints phrase + expected + got + rationale (so the red
     is actionable).
   - Runs every `must_stay_green` phrase, asserts tier == GREEN.
   - Asserts the fixture parses, has both sections non-empty, and every entry
     carries `source` and `added` (provenance is mandatory — this is how the
     corpus grows honestly).
4. Harness check **C12** in `src/lingua_viva/teacher_readiness.py` (follow
   `_add_check` pattern, :174): chain `preflight`, severity P0, runs the
   corpus in-process (import the same loader — one implementation, two
   callers; do NOT duplicate the scan logic). Evidence:
   `{"must_flag": N, "must_stay_green": M, "under_classified": [...], "over_classified": [...]}`.
   No `expected_fail`.
5. Document the growth rule at the top of the fixture file: **every
   safeguarding incident or near-miss adds its phrase to `must_flag` in the
   same commit as the fix.** (Same doctrine as "add a test that locks the
   class".)

### Acceptance
- [ ] `pytest -q tests/test_safeguarding_corpus.py` green; corpus ≥ 25 must_flag + ≥ 10 must_stay_green, all with provenance.
- [ ] "His dad hits him at home" is in `must_flag` with `minimum_tier: RED` and passes.
- [ ] Deliberately weakening the classifier (e.g. commenting one RED indicator family locally) turns the corpus test AND C12 red — demonstrated in the session report, then reverted.
- [ ] Harness reports 20/20 (C12 added), 0 stubbed.
- [ ] Classifier changes, if any were needed to pass the corpus, preserve: round-up-only monotonicity (never lower a tier), determinism, glass-box rationale strings.

---

## F2 (P0) — `expected_fail` expiry / linked-work-item mechanism

### Problem
`expected_fail=True` currently lives on C11
(`src/lingua_viva/teacher_readiness.py:356`) and DR (:449) with no expiry and
no linked work item. CLI gating (`src/lingua_viva/cli.py:127`) excludes
expected_fail checks from the failure gate — so a *permanent* expected_fail
is a permanent regression mask on a P0 check. Operator-validated verdict:
expected_fail must carry an expiry date or a linked work item, and goes red
when lapsed.

### Build
1. Extend `ReadinessCheck` (:38) with `expected_fail_until: Optional[str] = None`
   (ISO date) and `expected_fail_ref: Optional[str] = None` (path to a dev/
   spec or work item).
2. `_add_check` (:174): if `expected_fail=True` is passed **without at least
   one of** `expected_fail_until` / `expected_fail_ref`, raise `ValueError`
   at call time (fail the harness loudly at build, not silently at read).
3. Lapse rule: if `expected_fail_until` is set and today (UTC date) is past
   it, the check is treated as a REAL failure — `expected_fail` is forced
   False in the recorded check and evidence gains
   `{"expected_fail_lapsed": "<date>"}`. CLI gating then catches it with no
   change to the gating logic itself (it already keys off `check.expected_fail`).
4. Update the two current carriers:
   - **C11** (:356): `expected_fail_ref` → this spec's F2 section or the STT
     probe-parity work item; `expected_fail_until: "2026-09-10"`.
   - **DR** (:449): `expected_fail_ref` → `dev/SPEC_LV_ONE_ENVELOPE_2026-08-10.md`
     (E2 retires the duplicate engine and removes this expected_fail
     entirely); `expected_fail_until: "2026-08-24"`.
5. Markdown summary table (:555) gains the expiry/ref columns; the expected
   count line (:611) unchanged in meaning.
6. Locking tests in `tests/test_teacher_readiness.py`: (a) `_add_check` with
   bare `expected_fail=True` raises; (b) a lapsed `expected_fail_until`
   records a real failure with lapse evidence; (c) an unlapsed one still
   records `expected_fail=True` on failure; (d) existing 19-check (20 with
   C12) run stays green.

### Acceptance
- [ ] Bare `expected_fail=True` is impossible (test-locked).
- [ ] Lapsed expiry turns a P0 expected_fail into a real red through the existing CLI gate (test-locked with a synthetic past date).
- [ ] C11 and DR both carry ref + expiry; harness stays green today.
- [ ] `grep -n "expected_fail=True" src/` shows no carrier without an adjacent ref/until.

---

## F3 (P1) — Standing built-but-not-called wiring instrument

### Problem
The built-but-not-called class regenerated repeatedly (most recently: the
safeguarding gate existed but was unwired at 3 capture sites until W4).
Manual wiring audits (e.g. `REPORT_LV_WIRING_AUDIT_2026-08-08.md`) found and
fixed instances but decay immediately — the next build can strand a new
module. `preflight` already covers the route side (`route_reachability`:
mounted routes ↔ UI); the inverse — engine code with no caller path from any
entry point — has no instrument.

### Build
1. New module `src/lingua_viva/wiring_audit.py` — deterministic, AST-based,
   no LLM, no network:
   - Build the import/call graph over `src/lingua_viva/**/*.py`,
     `src/education/**/*.py`, `src/web.py`, `src/pipeline.py` using `ast`
     (imports + attribute calls; best-effort on dynamic imports — the
     in-function `from src.lingua_viva.X import Y` pattern used throughout,
     e.g. `web.py:4419`, `lesson_materials.py:1113`, must be caught: walk
     `ast.ImportFrom` at all depths, not just module top level).
   - Entry points (roots): `src/web.py` (routes), `src/lingua_viva/cli.py`
     (commands), `tests/` are NOT roots (a module only reachable from tests
     is exactly the orphan class we hunt).
   - Verdict per module: `wired` (reachable from a root) or `orphan`.
   - Allowlist file `governance/wiring_allowlist.yaml`: entries
     `{module, reason, ref, until}` — **`until` (expiry) or `ref` (linked
     work item) required**, mirroring F2 doctrine. Lapsed entries count as
     orphans. `archive/**` excluded by construction.
2. Self-test requirement (an instrument must prove it can detect): unit test
   plants a synthetic orphan module in a tmp tree and asserts the auditor
   flags it; and asserts a module reachable only via an in-function import IS
   marked wired (the false-positive class that would make teachers of this
   tool distrust it).
3. Wire in as a standing instrument at the chokepoint:
   - `python3 -m src.lingua_viva.cli eval wiring --json` subcommand
     (exit 1 on any non-allowlisted orphan).
   - Harness check **WA** in teacher_readiness.py: chain `preflight`,
     severity P1, evidence `{"modules": N, "orphans": [...], "allowlisted": [...]}`.
     If the current tree has genuine orphans that cannot be wired in this
     wave, allowlist them WITH refs — do not ship a red harness and do not
     silently wire things beyond scope.
4. `tests/test_wiring_audit.py`: graph construction, in-function import
   detection, orphan detection (planted), allowlist expiry lapse, current
   tree verdict.

### Acceptance
- [ ] Planted orphan detected (test-locked); in-function imports do not false-positive (test-locked).
- [ ] Current tree: 0 orphans, or every orphan allowlisted with ref/until — listed in the session report either way.
- [ ] `cli eval wiring --json` exits 1 on non-allowlisted orphan (test-locked via tmp tree).
- [ ] Harness reports 21/21 (C12 + WA), 0 stubbed.
- [ ] Runtime of the audit < 5s (it must be cheap enough to run every build, or it will be skipped).

---

## F4 — Exit gate (grind loop)

Same protocol as Grind Wave 2:
- [ ] `preflight` 6/6; `eval teacher-readiness` 21/21 (C12 + WA added), 0 stubbed.
- [ ] Full suite: `pytest -q tests/` — no regressions (baseline 2225 passed, 13 skipped).
- [ ] Live app walkthrough on `:8765` with `LV_AUTH_MODE=local_header` covering: a `must_flag` phrase captured via the real observation route lands in the restricted ledger and NOT in the student lens stream; a `must_stay_green` phrase flows normally.
- [ ] One deliberate-weakening demonstration for F1 (recorded in report, reverted).
- [ ] Session report `dev/SESSION_REPORT_LV_FAIL_CLOSED_WAVE_2026-08-10.md`: what was built, corpus counts, orphan verdicts, evidence blocks, gaps.
- [ ] Push per Rule 0 (this touches `src/**` → auto-release fires; release is done when 3 assets answer 200 and the pin commit is on origin).
