# CLOSURE WORKLIST — every open item to get v0.2.36 across the line (2026-08-04)

**Purpose:** the single consolidated fix list from all QA sources, for the closer
(Kiro) to execute. Reviewer (Claude Code, build machine) checks every item against
its DONE-PROOF before anything pushes. Teachers are online TODAY — Gate A is the
morning bar; B is same-day; C is this week.

**Sources consolidated:**
- Windows operator QA report v0.2.35 (checks W/V/H/X/NEW, 2026-08-04 evening session)
- `~/Downloads/POSTMORTEM_WAVE_CONVERGENCE_FAILURE_2026-08-04.md` (wave convergence analysis)
- `qa/2026-08-04_teacher-readiness-claudia.md` (live teacher QA, committed 4b77a04)
- `dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md` (the original bar + rules)
- Pending inputs: Chip's macOS QA report (session in progress), Kiro build audit
  (`dev/AUDIT_KIRO_BUILD_2026-08-04.md`, in progress) — **fold both in on arrival.**

**Standing rules for every item below:**
1. Wrong output is worse than missing output. Honest refusal beats broken feature.
2. Commit only files the item touches, by explicit path. Never `git add -A`.
3. An item is DONE only when its DONE-PROOF command passes. "I fixed it" is not a state.
4. Cross-machine "pushed" claims require the receiving side to run
   `git fetch && git log origin/main --oneline -3` and see the sha. No exceptions —
   this is the exact failure that hollowed v0.2.35.

---

## GATE A — morning bar (block release until ALL green)

### A1 — T3 grounded extraction lands (THE missing fuel)
- **Source:** postmortem §3; Claudia P0-1; Windows V6. Lane never ran; dispatched
  2026-08-04 late night on the build machine (`dev/PROMPT_PAIR_T3_EXTRACTION_2026-08-04.md`).
- **State:** IN FLIGHT on the build machine. Kiro: **integrate, do not rebuild.**
  If not landed by your start, check with operator before touching
  `src/lingua_viva/docpipe/extract.py`, `jobs.py`, `grounding_docs.py`.
- **Includes (folded from Claudia's report):** .txt ingest must work (her progress
  reports are .txt); PDF path must extract or honestly refuse — never crash.
- **DONE-PROOF:** `extract.py` no longer raises NotImplementedError; extraction of
  `tests/fixtures/docpipe/lesson_plan_marco_nora.md` yields schema-valid spans;
  hallucination-drop test passes (ungrounded field → DROPPED).

### A2 — T5 Observe capture lands (THE demo)
- **Source:** postmortem §3; Claudia P1-1 ("no mic button"); Windows W3/NEW-2.
- **State:** IN FLIGHT on the build machine
  (`dev/PROMPT_PAIR_T5_OBSERVE_CAPTURE_2026-08-04.md`). Same rule: integrate, don't rebuild.
- **DONE-PROOF:** Observe tab has a mic; dictation accumulates; SAVE → parsed
  editable record → confirm → lens updated; `grep -n "voice/act" static/index.html src/web.py`
  shows the old direct-save path GONE; ambiguous student always asks.

### A3 — Ingest endpoints return JSON errors, never bare 500 strings
- **Source:** Claudia P0-1 technical appendix — `/api/students/ingest` and
  `/api/ingest` return bare `Internal Server Error`; frontend dies on
  `Unexpected token 'I'`.
- **Files:** `src/web.py` (both ingest endpoints). Fix the CLASS at the endpoint
  layer (error handler wrapping), not per-route patches.
- **DONE-PROOF:** curl a deliberately bad upload to each ingest endpoint → HTTP
  error with `Content-Type: application/json` and an honest `error` message.
  Add a test locking the class.

### A4 — Observation save: CEFR force regression (invented-data risk)
- **Source:** Claudia P1-2. `saveObservation()` (static/index.html ~1860-1869)
  requires type + CEFR skill + level. v0.2.30 allowed save without a level.
  Teachers WILL pick arbitrary levels to pass the gate = invented data.
- **State:** folded into T5's in-flight scope (it owns the Observe region). Verify
  T5 actually fixed it; if not, fix post-T5-land.
- **DONE-PROOF:** an observation with text + student only saves; type/skill/level
  optional; regression test added.

### A5 — T7 e2e + grounding audit runs and passes (the designed release gate)
- **Source:** runbook Wave 4; postmortem §6.3 (the gate that would have caught the
  hollow release). Never dispatched.
- **Action:** once A1+A2 land, execute
  `dev/PROMPT_PAIR_T7_E2E_AUDIT_2026-08-04.md` (spec then implementation). The
  local-only variant is acceptable (Drive hops SKIPPED, never fake-passed).
- **DONE-PROOF:** single command (`scripts/run_docpipe_e2e.sh` or `lv eval docpipe`)
  exits 0; grounding audit reports ZERO ungrounded fields; failure-mode tests pass
  (kill mid-write, model timeout) — cover Windows check V7 while you're here.

### A6 — Full regression floor before pin
- **DONE-PROOF:** `pytest -q tests/` fully green;
  `lv eval teacher-readiness` ≥ 16/19 with C9/C10 green;
  `python3 -m src.lingua_viva.cli health` all-pass.

---

## GATE B — same-day (ship in v0.2.36 or a fast-follow, none may regress Gate A)

### B1 — Ask refusal wording (teacher-requested)
- **Source:** Claudia P2-3, verbatim: start with "The Ask section answers…".
- **Files:** `src/lingua_viva/messages.py` (the refusal is a routed message class —
  change it THERE, not in templates/UI strings).
- **DONE-PROOF:** refusal message starts "The Ask section answers general teaching
  questions…"; message-class tests updated, C9/C10 unaffected.

### B2 — TTS locale mismatch (English text, Italian voice)
- **Source:** Claudia P2-2. Browser `speechSynthesis` fallback uses Italian locale
  for English refusal text (`static/index.html` ~968-980).
- **DONE-PROOF:** language of the TEXT selects the voice; English refusal reads in
  an English voice; Italian content still reads in Italian.

### B3 — SmartScreen copy on the download page
- **Source:** Windows W1. Unsigned Windows build → "Windows protected your PC"
  with Run-anyway hidden behind "More info". Teachers will bounce.
- **Files:** `docs/index.html` (the live site — this is a DELIBERATE site change,
  allowed under runbook rule 10). One honest line near the Windows button:
  "Windows will warn because this build isn't signed yet — click More info →
  Run anyway."
- **DONE-PROOF:** live site shows the copy (curl the live page after Pages deploy).

### B4 — Settings: voice / sync / privacy sections missing
- **Source:** Claudia P1-3 + her confusion quote ("Where to find voice, sync, and
  privacy?"). Only Drive is visible.
- **Scope call (operator ruled thin-is-fine):** minimum honest version — Settings
  shows the three sections with real state (voice: STT available/provider; sync:
  queue length + last drain; privacy: local-only status + link to privacy log),
  even if controls are read-only for now. No fake toggles.
- **DONE-PROOF:** Settings renders the three sections with live values from
  existing endpoints (`/api/voice/probe` etc.); no dead controls.

### B5 — Sources ↔ Settings navigation
- **Source:** Claudia P2-4 — Settings says "Sources → Drive" but she couldn't find
  Sources. Cheapest honest fix: make that text a working link/button that switches
  to the Sources view.
- **DONE-PROOF:** clicking it navigates; wording matches the actual tab name.

### B6 — Re-run the aborted operator checks on v0.2.36
- **Source:** Windows report — H9 (never-guess live), H11 (stop/restart playback),
  H12 (offline observe + queue drain), X13 (freestyle abuse), V7 (kill
  mid-extraction — now testable once T3 lands).
- **DONE-PROOF:** operator (or Kiro on the Windows box) reports each check
  PASS/FAIL with evidence; failures loop back into this list.

### B7 — Perplexity key installed on each test machine
- **Source:** Windows recovery plan item 4. Ask currently shows honest "not set
  up" — correct behavior, but testers can't exercise the answer path.
- **DONE-PROOF:** a clean general question returns a spoken summary + citations on
  each QA machine; `external_calls` increments ONLY for clean queries.

---

## GATE C — this week (tracked, not tonight)

### C1 — Windows code signing (Azure Trusted Signing port from MC)
- Windows W1 real fix. 3 AZURE_* secrets + workflow step; needs org-admin + Azure
  values. Cut into the first release after secrets exist. DONE-PROOF:
  `Get-AuthenticodeSignature` on the shipped exe shows signed; SmartScreen copy
  (B3) can then be removed.

### C2 — PYTHONDONTWRITEBYTECODE=1 in desktop bootstrap
- Windows W4b: bundled Python litters `__pycache__` through `resources/app/` —
  will dirty signed bundles (same class as F6). Fix in the bootstrap spawn env
  BEFORE C1 lands. DONE-PROOF: fresh install + full session → zero .pyc under the
  install dir.

### C3 — T1 Drive ingest lane (slipped by rule, still owed)
- Runbook fallback invoked: local-file loop is day-one acceptable. Build T1 per
  `dev/PROMPT_PAIR_T1_DRIVE_INGEST_2026-08-04.md`; then T6's queue drains for real
  (Windows H12 completes) and NEW-1 (Drive connect broken/absent on Windows) gets
  its repro pass — determine OAuth config vs. platform bug.

### C4 — T7 wired as a CI release gate
- Postmortem §7.4: auto-release's test gate must fail if `extract_document` is a
  stub while the ingest UI is mounted, and must run `tests/e2e_docpipe/` when
  present. Never again ship a NotImplementedError on the critical path.
  DONE-PROOF: a deliberate stub-revert branch fails CI.

### C5 — macOS permission-dialog pileup at install
- Claudia P2-1 (screenshots exist). Audit which permissions are requested and
  when; consolidate/defer to first use.

### C6 — Mojibake check in teacher-facing copy
- Windows NEW-4: em-dashes rendered as "â" in PowerShell console — verify app UI
  renders correctly (likely console-only). DONE-PROOF: one screenshot of the
  affected strings in-app on Windows.

### C7 — Operator/demo hygiene
- Windows NEW-3: the operator Windows box has stale dev roster state — wipe
  `~\.lingua-viva\` before any demo on that machine. (Fresh installs verified
  clean — no seeding.)

### C8 — Credential + token hygiene
- Postmortem §7.5: rotate the GitHub token that was pasted in chat; confirm both
  machine accounts hold org write access (the silent-revoke burned hours).

### C9 — Feature requests (parked, tracked)
- FR-1 recommendation-after-observation (ties to CEFR young-learner
  progressions ask from the 2026-08-03 audit).
- FR-2 teacher image above mic (carried from 2026-08-03).
- Re-issue Chip's QA packet — her pre-wave prompt tests removed flows
  (runbook §8 already flags this).

---

## Release sequence (Kiro executes, reviewer verifies, THEN push)

1. Gate A items all DONE-PROOF green locally.
2. Gate B items done or explicitly deferred by operator ruling (one line each).
3. Reviewer (build-machine Claude window) re-runs: full pytest, teacher-readiness
   harness, T7 gate, and spot-checks every DONE-PROOF above.
4. Push → auto-release cuts v0.2.36 → run the AGENTS.md **7-step verification**
   (incl. macOS signature log check and single-version-live: retire v0.2.35).
5. Operator + Claudia re-run: Claudia Rounds 1/2/4 (blocked tonight), Windows
   B6 checks. New findings loop back here.

**The bar, restated from the runbook:** Observe works end-to-end by voice;
students-from-file produces real, grounded lenses; nothing lies and nothing
leaks; Ask answers by voice; offline is a supported state. Working at all beats
polished — but a green release only counts when the T7 gate has actually run.
