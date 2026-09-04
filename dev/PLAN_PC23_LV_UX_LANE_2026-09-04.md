# PC-23 LANE PLAN — LV UX ROLLOUT, ONE UX AT A TIME

**Date:** 2026-09-04 · **Seat:** PC-23 · **Operator:** Mical (live tester, PC-0)
**Base:** origin/main @ 0d46c98 (v0.2.84 + U1 prompt + synthetic fixtures in `demo-data/`)
**Companion docs on origin:** `dev/PATH_TO_UX_READINESS_2026-09-04.md` (the hard list),
`dev/PROMPT_LV_U1_INSTALL_TO_GREEN_2026-09-04.md` (item 1's full prompt),
`startup/team-tracker.html` in the fde monorepo (the scoreboard — Mical updates it).

## 0. The loop — this is the whole lane

```
BUILD (branch, red-first tests) → suite green → PUSH to main → auto-release (~9 min)
→ MICAL TESTS LIVE (real installed app, demo-data fixtures, click path)
→ FAIL: fix on branch, repeat → PASS: tracker row moves, next UX starts
```

**One UX at a time. The next UX does not start until Mical's live verdict on the current
one is PASS.** A PASS from Mical makes the row "ready for teacher witness" — it does NOT
make it green. Green needs Claudia or Olga. Say so in every report.

## 1. Lane rules (violating any of these stops the lane)

1. **One release at a time.** Before every push to main:
   `gh run list --repo lingua-viva/learning-architecture --workflow=auto-release.yml --limit 3`
   — anything queued/in_progress → WAIT. A commit inside an open window kills the chain silently.
2. **Branch per UX** (`ux/u1-install`, `ux/u13-safeguarding-test`, …), short-lived, merged to
   main only when the UX's own gate passes locally. Push of the branch itself anytime (Install
   Test CI runs on branches, cheap signal).
3. **Every fix is a class fix with a locking test that was red first.** Surface patches without
   a test are not done.
4. **Full suite green before any main push** (`python3 -m pytest tests/ -q` — zero failures is
   the invariant, the count grows). Exit codes read bare, never through a pipe.
5. **After the release chain goes green: verify, then hand off.** Tag pinned, live download
   resolves, THEN tell Mical "vX ready — test U-n with steps §…". Never "done" before the
   live surface shows it.
6. **No fabricated verdicts.** PASS / FAIL / CANNOT-TELL only. "Not enough data" beats a
   false positive. Numbers carry denominators and dates.
7. No ANTHROPIC_API_KEY, ever. No real child data, ever — `demo-data/` (synthetic,
   operator-confirmed) is the fixture set.
8. Append every live-test verdict to `dev/WITNESS_LOG_UX_2026-09.md` (create on first use):
   date, UX, release tag tested, step-by-step PASS/FAIL/CANNOT-TELL, exact wording seen.

## 2. The queue, in order, with why

### #1 — U1: Install & first run to green (level 1 → target: Mical-PASS)
**Why first:** it gates everything. Olga's install was witnessed BROKEN 09-03; both failed
demos trace to the front door. No later UX can be witnessed by anyone if install fails.
**Full prompt:** `dev/PROMPT_LV_U1_INSTALL_TO_GREEN_2026-09-04.md` — four rungs, kill
criteria K1–K5 frozen there. Baseline against the LIVE download (v0.2.84 — verify, don't
quote). Every first-run error named; Doctor green on clean Win + Mac; the `python3`-class
hunted across `desktop/`.
**Done means:** Mical runs the §6 click-path on a live install and every step is PASS.

### #2 — U13: Safeguarding P0 proven, not repaired (CANNOT-TELL → tested)
**Why second:** highest-stakes item in the repo (children's data), and the cheapest — it is
pure test work. Main already carries yesterday's fixes (`f3d6645` detector blind in Italian,
`71b069d` one source for three detectors), but BUG-3/4 status is still CANNOT-TELL because
no test asserts the two halves together: **a RED observation is (a) restricted AND (b) absent
from the normal record.** Write that test red-first (against the pre-fix commit or by
mutation), lock it, and answer the open question: who drains safeguarding notifications.
This is the sensitivity-gate class that also bit MC (08-15 seed kill) and is fenced in Trop
(commercial wall) — fixing it here with a locking test is the class fix.
**Done means:** the two-halves test exists, was demonstrably red first, is green on main;
Mical live-checks a RED observation never surfaces in the normal record or a parent note.

### #3 — C8 durability: install-over-install keeps every lens
**Why third, and why before more features:** this lane's own loop is repeated
install-over-install on Mical's test box — every release he tests could wipe the lenses he
created testing the previous one. Until C8 is locked, each cycle risks destroying the
evidence of the last. Also a hard launch-gate item.
**Done means:** automated test green on both platforms; Mical updates across one release and
his classe-3B lenses survive.

### #4 — U2: Roster honesty (level 3 → Mical-PASS)
**Why fourth:** roster is the entry point to every lens; the two known lies are small:
`approve` alone creates nothing but `done` implies it did, and the Grade column is silently
dropped. Make `done` mean created (or say why not), store `grade_level` from the CSV.
**Done means:** Mical imports `demo-data/classe-3B.csv` live; 6 lenses exist including the
accent names (Lucà, Noëmi); grade visible in the lens.

### #5 — U8: Edit a lens by hand (level 1 → Mical-PASS)
**Why fifth:** reversibility is what makes U3/U4/U5's automatic writes acceptable at all —
"automatic routing is only OK because a teacher can correct it in two seconds." Store ops
exist (`set_avoid_pairing_with`, `replace_support_profile`, confirm/dismiss); build the
endpoints + a two-second confirm/dismiss/correct control in the Students view, and render
`review_required` + `lens_update` so a teacher can SEE what a note did before undoing it.
**Done means:** Mical mis-routes a note on purpose, sees what it did, corrects it in two
clicks, live.

### #6 — SIR profile: hide Home/Daily/Plan/Slack, default view Students
**Why sixth:** Olga's ruling (C4/SIR); small; removes the surfaces that confused the 08-29
walkthrough. Profile flag, keep code, both profiles boot in a test.
**Done means:** SIR profile boots to Students with the four surfaces hidden; test green.

### STOP — handoff line
U3 + U4 with a real model (qwen3:8b) run on **PC-0, not PC-23** (PC-23 has no model). When
#1–#6 are Mical-PASS, this lane's next work is U10 (approve/print + minimum-evidence gate)
per readiness-path day 7 — ask Mical before starting it; the queue may re-rank on what live
testing found.

## 3. What Mical does per cycle (his half of the loop)

1. Wait for "vX ready — test U-n" (never test mid-window).
2. Update/install from the LIVE site button — that IS the C8/durability test after #3.
3. Run the UX's click path with `demo-data/` fixtures. Log PASS/FAIL/CANNOT-TELL per step,
   exact wording, into `dev/WITNESS_LOG_UX_2026-09.md` (or dictate to the orchestrator).
4. FAIL → back to PC-23 with the verbatim error. PASS → tracker row updates
   (blue "Mical-passed, awaiting teacher witness" — NOT green), next UX starts.

## 4. Honest accounting

- Each cycle ends with one line in the witness log and one tracker row change. No row moves
  without a dated artifact.
- A level that goes down is reported as going down.
- End of lane-day: one summary — releases cut (tags), UXs Mical-PASSed (n/6), CANNOT-TELLs
  remaining, and the delta on the sprint metric (level-4-by-intended-user — expected to stay
  0 until Claudia/Olga witness; say so plainly).
