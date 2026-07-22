# Execution Prompt for Kiro: Lingua Viva Demo Readiness Sweep (Demo Tomorrow, 2026-07-23)

Copy everything below into a fresh Kiro session. Working directory: `~/learning-architecture`.

There is a real demo tomorrow. This is not a coverage sprint — it is a **get every piece of this
repo to a genuine, working V1** sprint. The operator has invested a full dedicated session getting
things like the Windows CI signing pipeline this far — the ask now is to close every remaining gap,
not just patch the one bug that's visible. The operator's wife already tried the app and it did not
work like Mission Canvas's onboarding does. Your job: find out exactly why, fix it, then sweep the
**entire** system with the same rigor MC uses (`mc health` / `mc improve` discipline — measure, fix,
re-verify, never trust a doc claim, a green CI run, or a passing test suite without also live-running
the actual behavior a real user would hit), and finish by proving the actual demo script works
end-to-end on the real target machine. "Tests pass" and "CI succeeded" are necessary, not sufficient
— this repo's history (stale AppImage, unsigned Windows build never hand-tested) shows exactly how
those can both be true while the real user experience is still broken. Assume nothing is done until
you've personally watched it work.

The output is not a chat summary. The output is working code, live-verified behavior, and a report
file with evidence — same standard as every prior sweep in this repo
(`dev/REPORT_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md`, `dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`).

---

## How This System Is Meant To Work (read this before touching anything)

Lingua Viva is a local-first FastAPI + vanilla-JS + Electron app, forked from Mission Canvas's
engine and re-pointed at K-5 education (originally built for Still I Rise, rebranded 2026-07-18 for
Claudia Canu Fautré's own Italian program — same codebase, don't be confused by old `sir`/
`still-i-rise` naming you'll still see in comments/history).

- **Binary**: `lv`. **Install dir**: `~/.lingua-viva/`. **Default port**: `8787`.
- **Pipeline** (`src/`): governed request path — entry gate (PII scan) → ontology classify
  (`ontology/`, 111 nodes / 25 domains, education-specific) → retrieve → reason (local Ollama
  first, cloud provider only if the teacher explicitly connects one) → respond. Same governance
  shape as MC: local-first is a product differentiator, not a limitation — never propose routing
  around it.
- **Education modules** (`src/education/`): `student_lens.py` (per-student profile: CEFR
  language-level snapshot + RTI intervention tier 1-3, built from teacher observations),
  `content_differentiator.py` (turns one lesson into 3 tiers — foundational/on_track/extended —
  either templated or, when a document store has content, **adapted from real ingested curriculum
  documents** via `generate_from_documents()`), `document_parser.py` / `document_store.py` /
  `document_retrieval.py` (PDF → PII-redacted chunks → local vector search, Ollama
  `nomic-embed-text`), `assessment_generator.py`, `parent_report.py`.
- **Three UI tiers** (`static/index.html`, client-side DOM toggle, no server auth): Teacher
  (mostly real), Admin/Coordinator (mostly stubbed — evidence/capacity/trends are honest
  `{"status": "deferred"}` responses, not bugs), Student (does not exist, correctly deferred to
  Phase 4+). **Do not build out Admin or Student tiers for this pass** — out of scope, not needed
  for tomorrow.
- **Sweep/verification tooling that already exists — use it, don't rebuild it**:
  - `python3 -m src.lingua_viva.cli doctor` — governance/publication-safety/privacy checks
  - `python3 -m src.lingua_viva.cli preflight` — <5s structural gate (UI contract, imports, ontology/MANIFEST parity)
  - `python3 -m src.lingua_viva.cli health --full --json` — doctor + full pytest + `doctor/lv_artifact_gauntlet.py` + golden classification eval + 5xx log check, all in one command. **This is the LV equivalent of `mc health` — run it first and last.**
  - `scripts/gate3_sweep.sh 15` — 15x non-mutating live endpoint sweep against a running server
  - `python3 -m pytest tests/ -q` — full suite, currently 479/479 passing, ~2 min
- **Standing rule — do not violate**: the operator runs one dedicated commit window across parallel
  sessions on this repo. **Do not `git commit` yourself, even after fixing real bugs.** Leave changes
  staged/uncommitted and report exactly what changed and why. (This may be relaxed for tonight given
  the deadline — if so, the operator will tell you explicitly; otherwise assume it still applies.)

---

## Part 0 — Confirmed demo target (operator answered directly, do not re-ask)

1. **Demo machine**: the operator's own **Linux** machine, tomorrow, 2026-07-23. But **a Windows
   machine must be tested first, tonight/before the demo** — this is a real dry run, not
   hypothetical, and it has apparently never happened for this repo (see risk finding below).
2. **Surface**: **Electron desktop app only.** The operator will not show localhost/browser at all
   — teachers see only the packaged app. This simplifies Part 1: you do not need to build out the
   browser `/setup` parity gap for tomorrow (still worth naming as a real gap in the report, just
   not in scope tonight).
3. **Ollama/model state**: not yet confirmed present on the Windows test machine or the Linux demo
   machine — do not assume either is pre-warmed. Verify and pre-pull explicitly as part of your
   sweep; do not rely on a live pull happening successfully during the actual demo.
4. **Open decision, needs your input in the report, not a unilateral call**: whether to show the
   local-first onboarding/model-setup sequence live during the demo at all, versus starting the
   demo from an already-onboarded app. Recommendation to weigh: skip performing live Ollama/model
   setup in front of the audience — it is slow and network-dependent — pre-warm the demo machine
   beforehand and begin the demo from a working app; at most mention local-first as a one-line
   claim. State your own recommendation plus the tradeoff in the report so the operator can decide
   same-day.

### Correction: the Windows CI pipeline exists and works — the open risk is narrower

An earlier pass at this prompt wrongly claimed Windows had never been built. Corrected facts,
verified via `gh run view` / `gh release view`:
- `.github/workflows/desktop-release.yml` exists, ported from Mission Canvas, triggers on
  `desktop-v*` tags, matrix-builds macOS/Windows/Linux.
- It ran successfully today: run `29887964883`, tag `desktop-v0.2.0`, published
  2026-07-22T03:16:40Z. All three matrix jobs (`macos-latest`, `windows-latest`, `ubuntu-latest`)
  passed. The release has real assets: `LinguaViva-Setup.exe`, `LinguaViva.dmg`,
  `LinguaViva.AppImage`.
- **What's still actually unverified**: the workflow has **no signing step** for any platform (no
  Azure Trusted Signing, no Apple notarization — unlike MC's dedicated signing session). The
  Windows `.exe` and macOS `.dmg` are both unsigned. Unsigned Windows installers commonly trigger
  SmartScreen ("Windows protected your PC") on first run — a CI build succeeding proves the
  installer *compiles*, not that a real user double-clicking it on real Windows hardware gets a
  clean launch. As far as we know, **nobody has actually run this built `.exe` on physical Windows
  hardware yet.**

**Action**: download `LinguaViva-Setup.exe` from the `desktop-v0.2.0` release (or build fresh via
`npm run dist:win` if a Windows machine is available tonight), actually install and launch it on
real Windows hardware, and report plainly: does SmartScreen block it, does it get through
onboarding, does it reach a working app. Do not treat "CI succeeded" as equivalent to "verified
working for a user" — that gap is exactly the kind of stale-artifact trap that caused the Linux
regression in Part 1 below.

---

## Part 1 — Fix the onboarding regression (PRIORITY, do not defer)

### What's already known (verified by a prior session tonight, don't re-derive, build on it)

- The Electron setup wizard (`desktop/electron/main.ts`, `bootstrap.ts`, `preload.ts`,
  `desktop/electron/setup-wizard.html`) was shipped in commit `41a929f` ("feat(desktop): ship
  Electron onboarding wizard + desktop release pipeline") and is a correct, working port of
  Mission Canvas's own wizard (`~/fde/mission-canvas/desktop/electron/main.ts`,
  `setup-wizard.html` — read these as the reference, do not modify them). Sequence: Python
  detection (multi-candidate) → Ollama check (skippable, never blocks) → pip deps → server
  start → auto-navigate into the app. This was rebuilt from source and run in dev mode
  (`node_modules/.bin/electron --no-sandbox --disable-gpu .` from `desktop/`) tonight and
  confirmed working: real HTTP 200 from the app, real doctor payload from `/api/health`.
- **The bug**: `desktop/release/Lingua Viva-0.2.0.AppImage` on disk was built **Jul 19, before**
  the wizard existed. Unpacking its `app.asar` shows the *old* boot code — `checkPython()`
  failure throws inside an unhandled `app.whenReady().then(async () => {...})` with no
  `.catch()`, no retry button, no recovery path. If Python isn't found (or isn't found via
  whatever `PATH`/candidate list that old build used), the window just freezes.
  **This stale artifact is the single most likely thing "the wife" actually launched.**
- Secondary, real but lower-severity inconsistency found: the Electron wizard defaults to Ollama
  model `qwen2.5:3b` (`bootstrap.ts:10`) while `install.sh` (the separate CLI installer path)
  pulls `qwen3:8b` (`install.sh:79-83,234`). Pick one and reconcile — teacher-facing surfaces
  should not disagree about what model gets installed.
- The plain-browser path (`python3 -m src.lv_cli serve 8787` → open localhost) currently has
  **zero guided onboarding** — no first-run redirect, no `/setup` route, unlike MC which serves
  the identical onboarding wizard whether you're in Electron or a plain browser
  (`_needs_setup()` redirect in MC's `src/api_server.py`). LV's only in-app provider affordance
  is a small non-blocking panel in `static/index.html` supporting `openai/groq/mistral` only (not
  Claude/Gemini in the reasoning call path — `src/web.py:876-899`, comment at 881-882 admits this).

### What to actually do

1. Based on Part 0's answer, produce a **correct, fresh, working artifact for the actual demo
   surface**:
   - If desktop app on this machine: delete or ignore the stale `Lingua Viva-0.2.0.AppImage`;
     produce a fresh dev-mode launch (`npm run build --prefix desktop` then run Electron directly)
     or a freshly packaged AppImage via `electron-builder`, whichever is more reliable tonight —
     your call, but state which one you did and why, and prove it works with a live run, not a
     build-succeeded log.
   - If browser/localhost path: since there's genuinely no onboarding wizard there today, the
     realistic fix for *tomorrow* is not "build MC's full `/setup` route from scratch" (too big
     for one night) — it's making sure Ollama + model are pre-verified present (per Part 0) so the
     teacher never needs onboarding at all, and that the existing inline provider panel in
     `static/index.html` is not confusing or broken. Say plainly if you think the full `/setup`
     port is small enough to also do tonight; don't guess — check the size of MC's `src/onboarding.py`
     (437 lines) and `static/onboarding/index.html` first.
2. Reconcile the `qwen2.5:3b` vs `qwen3:8b` model-name mismatch (pick the model that's actually
   pullable/fast enough to matter for a live demo — smaller is safer for tomorrow).
3. **Live-verify, don't just read code**: actually launch whatever surface Part 0 selected, from a
   clean-ish state if you can simulate one, and confirm a person with zero terminal experience
   would get from "double-click the app" or "open the browser" to "the app is usable" without
   getting stuck. If you find another dead-end like the AppImage's unhandled throw, fix it the
   same way MC's wizard already handles it (retry/install buttons, never a bare throw).

---

## Part 2 — Full system sweep (mirror the MC health discipline)

Run, in order, and fix anything that isn't green — same standard as
`SPEC_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md` and `SPEC_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`,
both of which found real live bugs that passing tests alone missed:

1. `python3 -m src.lingua_viva.cli health --full --json` — baseline. As of tonight this should
   read doctor=WARN (expected privacy-only), pytest=PASS (479/479), gauntlet=PASS, golden_eval=PASS,
   server_5xx=PASS. If anything regresses from this baseline, that's a real new bug — fix it.
2. `python3 -m src.lingua_viva.cli preflight`
3. `python3 -m src.lingua_viva.cli doctor` (or via the health view in the running app) — confirm
   WARN only, and that the WARN is still the same known/reviewed privacy-exclusion, not something new.
4. Start the real server (`python3 -m src.lv_cli serve 8787` or via the Electron app, whichever
   Part 0 selected) and run `scripts/gate3_sweep.sh 15` against it.
5. **Live-walk the actual teacher-facing experiences that matter for tomorrow's demo** (see Part 3
   for the exact script) — not by reading `src/web.py`, by actually calling the endpoints/clicking
   the UI against the running server, the same live-verification method used in the P0 improvement
   cycle (`dev/LV_HAPPY_STATE_P0_2026-07-20.md` is the reference list of what "known-good" looks
   like if you need a template for how thorough to be).
6. Anything you fix here, add a regression test for it (this repo's convention — every fix in
   every prior sweep shipped with new tests).

---

## Part 3 — Prove the actual demo script works, live, and write a runbook

The demo the operator wants to give tomorrow: **create student lenses, then generate a lesson plan
from existing documentation, differentiated for multiple levels in the class at the same time, and
show how it's evaluated.** This is not a new feature — it is exactly what
`ContentDifferentiator.generate_from_documents()` already does (its own docstring: *"The demo path:
adapt this existing module for my three groups"*), paired with `student_lens.py`'s
`create_lens()`/`get_lens()` and `assign_tier_for_student()`/`assign_packs_for_roster()` for mapping
a real roster onto the three tiers by RTI tier + CEFR level. Your job is to prove this whole chain
works live, end-to-end, through whatever surface (UI or API) the demo will actually use — and write
down the exact steps.

Concretely:
1. Ingest a real curriculum document (there's a real one in this repo:
   `Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx`, or use `POST /api/ingest` / `lv ingest`
   with a suitable PDF/doc) into the document store.
2. Create 2-3 student lenses with genuinely different profiles (different CEFR snapshots and RTI
   tiers), via `StudentLensStore.create_lens()` / whatever the UI's Students view calls.
3. Generate a lesson pack from the ingested document via `generate_from_documents()`, and show
   `assign_packs_for_roster()` correctly splitting the 2-3 students across foundational/on_track/
   extended tiers based on their lenses — confirm the tier assignment logic in
   `assign_tier_for_student()` (RTI tier 3→foundational, RTI tier 2→foundational unless CEFR≥B1,
   RTI tier 1→on_track unless CEFR≥B2→extended) actually produces sensible, different outputs for
   your 2-3 test students, not all landing on the same tier by accident.
4. Show "how it's evaluated" — this can be `lv eval golden` (the golden classification suite) or,
   more relevant for a lesson-quality demo, the `source_mode: "adapted"` / `source_provenance` field
   on the returned `ContentPack` (proves the content came from the real ingested document, not a
   template — this is the "glass box" story, same differentiator MC leans on: show your work, not
   just an answer).
5. Write `dev/DEMO_RUNBOOK_2026-07-23.md`: a literal, numbered, copy-pasteable script — exact
   commands or exact UI clicks, in order, that the operator can follow live tomorrow without
   improvising. Include what to say if something is slow (e.g., "first Ollama call is loading the
   model, this can take 10-20s") so a live hiccup doesn't look like a broken product.

---

## Explicit non-goals for tonight (do not build these, even if you notice the gap)

- Admin/Coordinator analytics (`/api/admin/evidence`, `/capacity`, `/trends`) — honest deferred stubs, out of scope.
- Student-facing tier/login — correctly deferred to Phase 4+, out of scope.
- `POST /api/students/{id}/rti` decision-gate, grouping endpoint, portfolio-entry write path — real gaps, documented in `dev/HANDOFF_LINGUA_VIVA_2026-07-20.md` §5.1, not needed for the demo script above.
- ExitGate/IntegrityGate no-ops — known, deferred, not demo-relevant (local-only Ollama has nothing to exit-scan).
- The full MC-style `/setup` web wizard port — only attempt if Part 1 shows it's small; don't let it eat the night.
- Windows/Mac live testing — only in scope if Part 0 says that's the actual demo machine.

## Verification standard

Every claim in your final report must trace to something you actually ran (a command, a curl, a
UI click you performed), not something you read in a docstring or a spec. If you find a spec or
report in this repo claiming something is "SHIPPED" or "verified" and your own live check
disagrees, say so explicitly — this repo has already had specs go stale before (that's why
`dev/INDEX.md` exists as the single source of truth; update it in the same pass).

## Deliverables

1. Working, live-verified fix for the onboarding regression (Part 1).
2. Full sweep results, with every fix accompanied by a regression test (Part 2).
3. `dev/DEMO_RUNBOOK_2026-07-23.md` (Part 3).
4. One report file: `dev/reports/REPORT_LV_DEMO_READINESS_2026-07-22.md`, evidence-based, same
   format as prior sweep reports in this repo.
5. `dev/INDEX.md` updated with this spec/report's row.
6. Final chat response under 200 words: status of Parts 1-3, anything you could not verify or
   fix in time, and the single highest-risk thing left for tomorrow if there is one.
