# Full System Convergence Run — Lingua Viva, Overnight

**Date**: 2026-07-31
**Purpose**: Run the most comprehensive improvement loop LV can currently support —
Doctor + audit + distill + golden workflows + full suite, in a repeated convergence
cycle — fix everything found, then close the documentation drift this session's own
build velocity created. This should take as long as it takes. The goal is to fix as
many things as possible, not to finish fast.

---

## Read this first: LV does not have `mc improve`

Mission Canvas has one command, `mc improve`, that proposes a fix, measures, and
loops. **LV has no equivalent single command.** Verified directly against
`src/lingua_viva/cli.py:440-538` — the full LV CLI surface is:

```text
lv chat | ingest | health | doctor | preflight | serve
lv eval golden
lv audit [--last N] [--journal-write] [--strict] [--json]
lv distill                       (read-only ranked gap-cluster distillation)
lv candidates                    (read-only ontology candidate list)
lv golden-workflows [--hermetic|--live]
lv filemap show|scan|exclude|clear
```

`doctor/support_loop/doctor.py` was confirmed by direct read to be a **static gate
checker** (branch state, required files, YAML validity, revision-log schema, artifact
gauntlet, matrix authority, claim register, publication-safety, README overclaim scan,
bloat, updates, template drift, privacy paths) — it reports PASS/WARN/BLOCKED, it does
not propose or apply fixes. `lv audit` is the closest thing LV has to MC's lagging-
indicator drift detection, but it reads `gap_signals.ndjson`, it does not generate
new work items either.

**This means the convergence loop here is a composition you drive, not a single
command you repeat.** Each iteration below runs the full LV diagnostic stack, you read
every output, you decide what's actionable, you build/fix it yourself (or via
`lv candidates` → build a spec → build the code, same pattern MC uses for
`mc improve-external`), then you loop. Treat the sequence in Phase 3 as the manual
substitute for `mc improve`'s propose step.

---

## Context for this window — what already shipped today (2026-07-30)

Verified directly via `git log --oneline --since="2026-07-30"` — do NOT rebuild any of
this, and do NOT trust `dev/HANDOFF_LINGUA_VIVA_2026-07-20.md` or any handoff dated
before 07-30, they are stale on multiple points (streaming and cohort lesson planning
were both listed as open gaps there and are now built):

```text
5d527ec lv: publication readiness repass — site copy fixes + go/no-go report
03d71bb chore(release): pin desktop-v0.2.23
8dbf4e6 lv: spec status drift checker
f2345e9 lv: defect triage hardening (+34 lines, edge case fixes)
d92b188 chore(release): pin desktop-v0.2.22
7f2b8e2 lv: defect source triage + contract bump + builder fix
157194f chore(release): pin desktop-v0.2.21
b67d736 lv: cohort lesson planning + audit receipt builder fix
f4d0446 lv: exit integrity gates + teacher decision flywheel + document intelligence
73a5104 chore(release): pin desktop-v0.2.20
2fa5cd9 lv: server-side auth + ops request center + schedule acks + session sweep
5824837 chore(release): pin desktop-v0.2.19
247ade8 lv: voice streaming + GIR hardening + golden workflows + SIR absence coverage + grounding calibration
07e572d chore(release): pin desktop-v0.2.18
2a89e62 lv: inline GIR at pipeline step 6.25 + voice tone resolver
```

That is 8 real feature builds plus 6 pinned desktop releases in roughly 24 hours.
Working tree is clean (`git status --short` returns nothing as of this writing) —
everything above is already committed and, per the `desktop-v0.2.2x` tags, released.

**Resolved — confirmed built with passing test files, do NOT rebuild:**
- GIR inline at pipeline step 6.25 + voice tone resolver (`test_voice_tone.py` class)
- Golden voice loop / `GW-VOICE-006` + GIR hardening + grounding calibration fix (the
  "GIR always 1.0" bug documented in `dev/HANDOFF_BUILD_SESSION_2026-07-30.md` §1 —
  fixed: `build_grounding_result()` now requires lexical relevance, not just citation
  presence)
- Voice query streaming (`SPEC_LV_VOICE_STREAMING_2026-07-30.md`) — `/api/query/stream`
  SSE route + early-sentence TTS trigger
- 3 SIR Slack workflows: absence/coverage MVP, ops request center, schedule-change acks
  (`test_sir_ops_request_center.py`, `test_sir_schedule_acks.py`)
- Server-side auth role gate, middleware pattern (`test_server_side_auth_role_gate.py`)
- Native exit integrity gates (`test_native_exit_integrity_gates.py`)
- Teacher decision flywheel completion (`test_teacher_decision_flywheel.py`)
- Document intelligence (`test_document_intelligence.py`, `test_document_ingest_endpoint.py`)
- Cohort lesson-planning workflow (`test_cohort_lesson_planning.py`)
- Education defect source triage + hardening pass (`test_defect_triage.py`)
- Spec status drift checker module — **but see the gap flagged below, it is not fully
  wired**
- Publication readiness repass — public copy corrected in `docs/index.html` (stale
  `570 tests` claim removed, "no data leaves your computer" language softened to
  local-by-default + gated opt-in connectors). Full detail in
  `dev/reports/REPORT_LV_PUBLICATION_READINESS_REPASS_2026-07-30.md`.

**Confirmed gaps found while preparing this run — fix these early, they're cheap and
real:**

1. **`spec_status.py` is built but not wired into `cli.py`.** Verified: no
   `spec-status` subcommand exists in `lv --help` output despite
   `dev/SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md` specifying an optional
   `python3 -m src.lingua_viva.cli spec-status --json` entry point. Wire it in — this
   is exactly the tool this run needs for Phase 2 below, and it currently can only be
   invoked as `python3 -m src.lingua_viva.spec_status`, not through the project CLI.
2. **`dev/INDEX.md` has zero rows for any 2026-07-30 spec.** Confirmed:
   `grep -n "2026-07-30" dev/INDEX.md` returns nothing. Every spec/prompt/report pair
   built today (10+ files) is undocumented in the index that's supposed to be the
   single source of truth. This is precisely the drift class
   `SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md` was built to catch — but since the
   checker isn't wired into the CLI yet (gap #1), nobody has run it against today's own
   output. Do that first, then fix what it finds.
3. **Current test count, verified fresh while preparing this run**:
   `1692 passed, 13 skipped` (full `pytest tests/ -q`, 332s). This is up from the 1622
   recorded in `dev/HANDOFF_BUILD_SESSION_2026-07-30.md`, which was taken partway
   through the session — the +70 delta matches the feature builds that landed after
   that snapshot (exit gates + flywheel + doc intelligence, cohort lesson planning,
   defect triage + hardening, spec status checker). Use **1692 passed / 13 skipped**
   as the Phase 1 baseline to compare against, not 1622.

**Key lessons from today's session, worth keeping in mind while running this loop**
(full detail in `dev/HANDOFF_BUILD_SESSION_2026-07-30.md`):
- GIR calibration is deterministic but coarse (lexical-relevance guard) — a real
  calibration spec against teacher queries with expected GIR bands is still open. If
  the golden voice loop or GIR hardening scenarios surface miscalibration, that's a
  known-open thread, not a regression.
- The auth gate lives in one middleware (`_enforce_role_gate` in `src/web.py`), not
  per-route. Any new route added during this run must be classified there, not given
  its own ad hoc check.
- Any change to `src/web.py`, `static/index.html`, or `static/sw.js` requires bumping
  `contracts/UI_CONTRACT.yaml` and re-locking before `tests/test_ui_contract.py` will
  pass. This bit the previous session twice from concurrent-window commits — check for
  it explicitly if UI contract tests fail unexpectedly.

---

## The run sequence

### Phase 1: Ground truth — get an accurate baseline before touching anything

```bash
python3 -m pytest tests/ -q 2>&1 | tail -20
python3 -m src.lingua_viva.cli preflight
python3 -m src.lingua_viva.cli doctor --json
python3 -m src.lingua_viva.cli audit --json
python3 -m src.lingua_viva.cli eval golden
python3 -m src.lingua_viva.cli golden-workflows --hermetic
```

Record the exact pass/fail/skip counts and every Doctor WARN/BLOCKED line. This
replaces MC's `mc health && mc ignition` step — LV's equivalent ground-truth gate is
`doctor` + `preflight` + a green full suite. If anything here is unexpectedly red
(not a known-open item from the list above), fix it before proceeding — a convergence
loop built on a red baseline just compounds confusion.

### Phase 2: Close the documentation drift this session's velocity created

1. Wire `spec-status` into `src/lingua_viva/cli.py` per
   `dev/SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md`'s "Optional project CLI"
   section (`python3 -m src.lingua_viva.cli spec-status --json`). This is a small,
   low-risk wiring fix — the module (`src/lingua_viva/spec_status.py`) already exists
   and is tested (`tests/test_spec_status.py`); it just isn't reachable from the CLI
   dispatch table.
2. Run it:
   ```bash
   python3 -m src.lingua_viva.cli spec-status --markdown
   ```
3. Fix what it finds for the 2026-07-30 spec batch specifically — at minimum, add
   `dev/INDEX.md` rows for every top-level `dev/SPEC_LV_*_2026-07-30.md` and its
   paired `dev/PROMPT_LV_*_2026-07-30.md`, using the same table format the rest of
   `dev/INDEX.md` already uses. Cross-check status headers inside each spec against
   what actually shipped (some may still say DRAFT despite being built and tested —
   update them to reflect reality, don't leave the checker's own findings
   unaddressed).
4. Do not let this become a rabbit hole — it's a documentation-honesty pass, not a
   rebuild. Budget it as a fast early phase, not the main loop.

### Phase 3: The manual convergence loop (LV's substitute for `mc improve`)

Run this composition repeatedly until it stabilizes — meaning a full pass surfaces no
new actionable findings, or everything remaining is a genuine human-judgment call
(publication/launch-readiness calls, privacy-policy language, anything the
`dev/reports/REPORT_LV_PUBLICATION_READINESS_REPASS_2026-07-30.md` "No-go until owner
review" section already flagged as owner-only):

```bash
for i in $(seq 1 15); do
  echo "=== LV convergence iteration $i ==="
  python3 -m src.lingua_viva.cli doctor --json
  python3 -m src.lingua_viva.cli audit --json
  python3 -m src.lingua_viva.cli distill
  python3 -m src.lingua_viva.cli candidates
  python3 -m src.lingua_viva.cli golden-workflows --hermetic
  python3 -m src.lingua_viva.cli eval golden
  python3 -m pytest tests/ -q
  # Review every output above:
  #   → Doctor WARN/BLOCKED that isn't a known-open item: fix it.
  #   → audit: new lagging-indicator drift since last --journal-write baseline: fix it,
  #     or if there is no baseline yet, run `lv audit --journal-write` once now to
  #     establish one, then treat subsequent iterations' deltas as the signal.
  #   → distill: read the ranked gap clusters. Pick the highest-ranked cluster that
  #     is genuinely actionable (not already a known-open item above). If it names a
  #     code fix: build it, test it. If it names a missing KL/ontology entry: research
  #     it (this is LV's equivalent of `mc improve-external` — there is no dedicated
  #     command, so this means actually reading source material and adding the entry
  #     yourself) and add it.
  #   → candidates: review proposed ontology nodes. Promote genuinely warranted ones,
  #     leave the rest for explicit operator review — do not auto-promote.
  #   → golden-workflows / eval golden: any FAIL is a real regression or a real gap.
  #     Fix it before moving on; don't let it carry into the next iteration.
  # If a full iteration finds NOTHING actionable across all six commands: the system
  # has converged. Stop, even if you're on iteration 3 instead of 15.
done
```

**Key principle, carried over from the MC template**: this loop is meant to catch as
much as possible and run for as long as it takes. There is no value in it running fast
but missing things. Push each iteration for real findings before declaring
convergence — a loop that "converges" on iteration 1 because you didn't look closely
enough is worse than no loop at all.

**Use `lv golden-workflows --live` sparingly and deliberately.** Per the operator
ruling already made for MC's identical golden voice loop (`mc improve` real-HTTP
principle, `dev/CONVERGENCE_BRIEF_TRUST_HANDOFF_2026-07-21.md`): if you want to
validate the voice path end-to-end against the actual running app rather than the
hermetic fixture path, start `lv serve` first and expect it to be slow and
occasionally blocked by local model availability (Ollama, Whisper). If the server or
model is down, that is expected behavior — diagnose, fix, and re-run, don't skip past
it. Reserve `--live` for a deliberate pass, not every loop iteration; `--hermetic`
is the right default for the repeated Phase 3 cycle.

**Use the lenses.** Read `src/lingua_viva/lenses/` (or wherever LV's lens files live —
check for a Claudia person-lens equivalent and any pedagogy/privacy lenses) when a
finding needs a perspective shift: Is this a privacy problem? Load the protection
framing. Is this a teacher-workflow problem? Load the pedagogy framing. Don't force
every finding through a single lens.

### Phase 4: Verification gate

After the loop stabilizes:

```bash
python3 -m pytest tests/ -q
python3 -m src.lingua_viva.cli preflight
python3 -m src.lingua_viva.cli doctor --json
python3 -m src.lingua_viva.cli eval golden
python3 -m src.lingua_viva.cli golden-workflows --hermetic
python3 -m src.lingua_viva.cli audit --strict --json
python3 -m src.lingua_viva.cli spec-status --json   # after Phase 2 wires this in
```

All must be green (Doctor: no unexplained WARN/BLOCKED; audit --strict: exit 0 or
only pre-acknowledged drift; spec-status: no new fail-severity findings for anything
touched this run).

### Phase 5: Do NOT commit or push

This repo's convention (`memory/feedback_lv_commit_window.md`, confirmed operator
instruction across multiple sessions): the operator owns the single dedicated commit
window for this repo. **Build and fix everything, but leave the working tree
uncommitted.** This differs from the MC template, which has the agent commit and push
in its own Phase 4 — do not port that step here. Instead, close this run with a
handoff document.

---

## What "done" looks like

- Phase 1 baseline captured with real, current numbers (not the stale 1622 figure)
- `spec-status` wired into the CLI and run at least once against the full 07-30 spec
  batch, with `dev/INDEX.md` drift fixed
- The Phase 3 loop has run enough iterations that it either:
  - Finds nothing actionable across `doctor`/`audit`/`distill`/`candidates`/
    `golden-workflows`/`eval golden` in a full pass (converged), or
  - Only remaining items are explicit owner/operator-judgment calls (list them, don't
    guess at them — e.g. anything from the publication-readiness "No-go until owner
    review" list)
- `pytest tests/ -q` is fully green with an exact, current count recorded
- `lv preflight`, `lv doctor`, `lv eval golden`, `lv golden-workflows --hermetic` all
  pass
- `lv audit --strict` shows no unacknowledged drift
- Working tree is left **uncommitted** — do not commit, do not push, do not tag a
  release
- A handoff document exists at `dev/HANDOFF_LV_CONVERGENCE_RUN_2026-07-31.md`
  summarizing: exact before/after test counts, every fix made and why, every
  `distill`/`candidates` finding reviewed and its disposition (fixed / deferred with
  reason / owner-review-required), and the final verification-gate state from Phase 4

Take as long as you need. The goal is the system's best possible state — and closing
the documentation gap this session's own speed created, so the next agent doesn't
have to re-derive "what's actually built" from `git log` the way this prompt did.
