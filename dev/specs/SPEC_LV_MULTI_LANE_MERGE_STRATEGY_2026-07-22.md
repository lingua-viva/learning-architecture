# SPEC: Multi-Lane Convergence & Commit Strategy — 2026-07-22

**Date**: 2026-07-22
**Status**: APPROVED — reconciliation complete, ready for operator commit decision
**Author**: Claude (this session)
**Trigger**: Five concurrent agent windows ("Filemap Verification UI", "Extract+Fill+Verify
Engine", "Observe Live Capture / Oka voice", "UI Wiring Fixes / Kiro", "Slack App
Integration") all worked directly in the same single working tree at
`fde/lingua-viva` over the course of one day, each reporting its own results
independently. Operator asked for a strategy to understand and merge all of it into
one coherent, working app.
**Scope**: Reconciliation analysis + commit/verification strategy only. No new
feature code. Two small corrections applied directly (see §5).
**Risk level**: LOW for the analysis itself; the *commit* decision this spec leads
to is the one irreversible-ish step, and is explicitly left to the operator (§7).

---

## 1. The actual technical situation (read this first)

This is **not** a git branch-merge problem. All five lanes edited the same
single uncommitted working tree, sequentially, over the same day — there are no
branches to `git merge`, no conflict markers, and nothing to resolve at the VCS
level. Every file `git status` shows as modified already contains the combined,
final text of every lane that touched it. The real task was never "merge N
diffs" — it was **"verify that N lanes' worth of sequential edits to shared
files actually compose into one coherent, correct, tested app,"** which is a
verification problem, not a merge problem. §2-§4 below are that verification.

## 2. Lane inventory

| Lane | Spec | Report | INDEX.md status (now) |
|---|---|---|---|
| File-Map Verification UI | `SPEC_LV_FILEMAP_VERIFICATION_UI_2026-07-22.md` | `REPORT_LV_FILEMAP_VERIFICATION_UI_2026-07-22.md` | SHIPPED (uncommitted), 15-pass hardened |
| Extract+Fill+Verify Engine | `SPEC_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md` | `REPORT_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md` | SHIPPED + 15-round hardening (uncommitted), **§4 GATED** |
| Observe Live Capture ("Oka" voice hardening) | `SPEC_LV_OBSERVE_LIVE_CAPTURE_2026-07-22.md` | `REPORT_LV_OKA_VOICE_15_PASS_HARDENING_2026-07-22.md` | HARDENED ×15 (uncommitted) |
| UI Wiring Fixes | `SPEC_LV_UI_WIRING_FIXES_2026-07-22.md` | *(no separate report; folded into live code + this session's live verification)* | SHIPPED (uncommitted) — **status corrected this session**, was stuck at DRAFT despite being fully built and verified |
| Slack App Integration | `SPEC_LV_SLACK_APP_INTEGRATION_2026-07-22.md` | `REPORT_LV_SLACK_15_PASS_HARDENING_2026-07-22.md` | Implemented MVP |
| Data-In Contracts (foundation) | `SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` | — | SHIPPED (uncommitted), inert (nothing imports it directly outside the engine) |

**Important naming note**: "Oka" is not a sixth, separate initiative — it is the
built-and-hardened implementation of `SPEC_LV_OBSERVE_LIVE_CAPTURE_2026-07-22.md`
(the spec this session wrote earlier today), expanded in scope to also harden the
**Ask** view's voice interaction (the original spec only covered Observe). Don't
go looking for a separate "Oka spec" — there isn't one; it's filed under Observe
Live Capture in `dev/INDEX.md`.

## 3. File-overlap map

| File | Diff shape | Lanes | Verdict |
|---|---|---|---|
| `static/index.html` | +637 / −51 | Filemap UI, Observe/Oka, UI Wiring Fixes, Slack (nav button) | **Already reconciled.** The 51 deletions are real in-place replacements (old `startSpeech()`/`saveObservation()`/dead Confirm-Defer buttons/the old `data.result?.content \|\| data.error \|\| "No response."` line) — not leftover dead code from an unmerged lane. Confirmed coherent: clean JS parse, zero test failures across every lane's own test file. |
| `src/web.py` | +370 / −0 | Filemap UI, Observe/Oka (`/api/observe/classify`), UI Wiring Fixes (`/api/students`, `/api/students/{id}/rti/decision`), Slack (`/api/slack/status`, `/api/slack/events`) | **Purely additive** across every lane. No overlapping edits to reconcile. |
| `contracts/UI_CONTRACT.yaml` / `.lock` | +16 / −1 (yaml) | All UI-touching lanes, sequentially | **Self-healed.** Version climbed v10→v19 as each lane bumped and re-locked in turn; the bump log names each lane's reason. `tests/test_ui_contract.py`'s `EXPECTED_VERSION` now reads `19` and matches the live contract exactly — earlier today it was stuck at a stale `13` against a live `17`/`18`; a later lane closed that gap on its own. Nothing left to fix here. |
| `src/education/student_lens.py` | +28 / −0 | UI Wiring Fixes (`record_rti_decision` + new `rti_decisions` table) | Purely additive, single lane. |
| `src/lingua_viva/filemap.py` | +208 / −2 | File-Map Verification UI | Single lane, additive. |
| `tests/test_ui_contract.py` | +8 / −2 | Whichever lane last reconciled the version constant | Matches live contract, no action needed. |

**Ask-view overlap, specifically** (the one place two lanes' *design intent*
genuinely touched the same functions): UI Wiring Fixes' error-honesty fix and
Observe/Oka's voice hardening both edit `renderMessage()` / `askQuestion()` /
`submitAskText()`. Verified compatible, not colliding: `renderMessage()` still
branches cleanly on `message.isError` into a distinct no-badge render (UI Wiring
Fixes' requirement), and Oka's additions (turn-concurrency guard, `aria-pressed`
mic state, spoken-error boundary) wrap around that same branch without altering
it. Zero failures in either lane's dedicated test file confirms this holds in
practice, not just in the diff.

## 4. Verification already performed (this session, fresh)

- **Live, direct API verification** (not just reading reports) of: Add Student,
  Confirm/Defer, Ask error rendering, Slack status/signature verification
  (401/503/valid-HMAC-200 all confirmed), File-Map scan/peek/confirm/assign
  (including the Spec-5 handoff shape). All passed.
- **Full test suite, fresh run**: 515 passed, 17 failed. Every failure is a
  previously-established environmental category on this Windows box (non-portable
  `chmod 0600` permission assertions, Mac-arch-detection simulation, missing
  shellcheck/pwsh, Ollama embedding-endpoint 404s) — **zero failures** in
  `test_ui_contract.py`, `test_observe_classify.py`, `test_oka_voice_hardening.py`,
  `test_filemap.py` (except the one known permission test), `test_slack_bot.py`,
  or `test_slack_app_integration.py`. No cross-lane regression exists.
- **Extract+Fill+Verify Engine's §4 gate confirmed still respected** — every
  round of its 15-round hardening loop ran only against synthetic fixtures, never
  a real file. This is a deliberately held-open decision, not a gap (§6).

## 5. Corrections applied directly this session (low-risk, done)

1. **`dev/INDEX.md`**: `SPEC_LV_UI_WIRING_FIXES` was still marked `DRAFT —
   assigned to Kiro` despite all 3 fixes being fully built and independently
   live-verified. Corrected to `SHIPPED (uncommitted)` with verification evidence.
2. **`ontology/learned_weights.yaml`**: an earlier verification `/api/query` call
   this session (unrelated to any of the 5 lanes) triggered the auto-learning path
   and added an empty `LV-LRN-001: {}` placeholder entry. Reverted via
   `git checkout` — this file's own header states "Auto-learned from path
   outcomes. Do not edit manually," and an empty placeholder from a test query is
   not real learned signal worth keeping.

## 6. Open items — need an operator decision before commit

1. ~~`doctor/support_loop/doctor.py` — unattributed, untested change~~
   **RESOLVED same day.** Attributed: this session's own earlier
   `System: BLOCKED` → `System: OK` fix, done before the 5 tracked lanes existed
   — confirmed by diff-text match against that session's own comments, not
   guesswork. Tested: `tests/test_doctor_desktop_mode.py`, 7 tests (per-check
   desktop-mode-skip + authoring-mode-still-fails regression guard for each of
   the 4 affected functions, plus a full `run_doctor()` end-to-end check against
   a realistic fixture tree — confirms a genuine desktop install never reports
   `BLOCKED`). All pass.
2. **Extract+Fill+Verify Engine's §4 gate**: the spec has explicitly required
   operator sign-off before this engine ever runs against a real file (as
   opposed to synthetic fixtures) since it was written. Nothing in this
   reconciliation changes that — it is called out again here only so it isn't
   accidentally crossed during whatever commit/deploy step follows this spec.

**New finding, same session, not one of the original 2 open items**: the
`ontology/engine.py`-now-exists-in-repo note in §2's Lane Inventory table
undersold a real, separate, now-fixed bug — `desktop/package.json` never shipped
`ontology/engine.py` or its dependency closure to the actual packaged app, only
the source tree had it working. See `SPEC_LV_DESKTOP_ONTOLOGY_PACKAGING_2026-07-22.md`
for the full trace and live verification — this is now a 7th commit-worthy unit,
not part of any of the original 5 lanes.

## 7. Recommended commit strategy

Given the operator holds the sole commit window in this repo (per `CLAUDE.md`),
and given §3 shows every file's current state is already the correct combined
result — there is no merge conflict to resolve at commit time, only a
**granularity choice**:

- **Recommended: one commit per lane**, in this order, each independently
  revertible and reviewable:
  1. `data-in-contracts` (foundation, inert, zero risk)
  2. `filemap-verification-ui`
  3. `extract-fill-verify-engine` (commit message must state the §4 gate status
     explicitly — this is the one piece of shipped code that must not be
     mistaken for "safe to run against real files")
  4. `ui-wiring-fixes`
  5. `slack-app-integration`
  6. `observe-live-capture` (Oka voice hardening) — last, since it's the most
     recently touched and depends on nothing else landing first
  7. `dev/INDEX.md` + this spec, as a final "convergence" commit
- Do **not** attempt to split `static/index.html` or `src/web.py` per-lane at
  the diff level — §3 already showed these files' changes are interleaved by
  function, not by clean line ranges; a git commit is a snapshot of file state,
  not a diff-ownership record, so committing the whole file once per lane
  (accepting that later lane-commits will show unrelated earlier lines as
  unchanged, which is normal) is simpler and safer than trying to `git add -p`
  hunks apart.
- **Do not commit `doctor/support_loop/doctor.py` until §6 item 1 is resolved.**
  Everything else in this list has no such open question.

## 8. Definition of Done

- [x] All 5 lanes' current file-level state confirmed mutually compatible (§3)
- [x] Full suite run fresh, zero cross-lane regressions (§4)
- [x] `dev/INDEX.md` stale status corrected (§5.1)
- [x] Stray auto-learned test artifact reverted (§5.2)
- [ ] `doctor.py`'s `_desktop_mode()` change attributed + tested (§6.1) —
      **operator action required**
- [ ] Operator commit-granularity decision made (§7) — **operator action required**
- [ ] Extract Engine §4 gate explicitly confirmed or explicitly deferred further
      by operator before any real-file run — **operator action required, not
      blocking commit of the gated engine code itself**

## 9. Provenance

Full fresh survey this session: `git status`, `dev/INDEX.md`, both the original
and 15-round-hardened versions of the Extract Engine report, the Oka voice report
(read in full to resolve the "is this a 6th lane" question), a file-by-file
overlap analysis backed by `git diff --stat`, the current `UI_CONTRACT.yaml`
bump log read in full, and a fresh complete `pytest` run (515 passed / 17
failed). `doctor/support_loop/doctor.py`'s diff read in full directly to confirm
it's well-reasoned but genuinely unattributed and untested before flagging it.
