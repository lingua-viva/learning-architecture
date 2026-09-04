# BUILD PROMPT — U1: INSTALL & FIRST RUN TO GREEN

**Date:** 2026-09-04 · **Repo:** `~/learning-architecture` (Lingua Viva) · **Priority:** 1 of the UX-enablement sprint — **U1 gates everything**.
**You are a build agent.** This prompt is self-contained; do not assume conversation context.

## 0. Why this exists

Olga (Still I Rise, customer) tried to install on 2026-09-03, witnessed: repeated errors, one
install lost entirely. Doctor crashed on every Windows box until `3eaa943`. Two demos have now
failed at the front door. Nine schools and hundreds of students launch in two weeks ONLY if
U1 reaches level 4: **a named teacher installs unassisted on her own machine and minute one
works, or says exactly what is wrong.** Current proven level: 1.
Full context: `dev/PATH_TO_UX_READINESS_2026-09-04.md` (§2 U1 row, §4 day 1–2) on branch
`fix/cefr-write-and-unknown-field-refusal-2026-09-03`.

## 1. Fences — read before any command

- **NEVER push to `main`.** LV main fires auto-release. All work on a branch
  (`fix/u1-install-to-green-2026-09-04`). Merge is operator-gated.
- **No ANTHROPIC_API_KEY. Ever.** `unset ANTHROPIC_API_KEY`. Subscription auth only.
- Do not edit anything under `qa/` — witnessed records are append-only evidence.
- Exit codes read bare, never through a pipe (`cmd; echo $?` — not `cmd | tail; echo $?`).
- Every number you report carries a denominator and a date. CANNOT-TELL is a verdict, not a
  gap to paper over. "Not enough data" beats a fabricated pass.
- The sandbox trap: set BOTH home variables when sandboxing (`HOME` + `USERPROFILE` /
  platform equivalent). This is a test, not a memory.

## 2. Kill criteria — FROZEN NOW, before any build

The build is killed (and that is a successful outcome to report) if:

- K1: any first-run failure path still surfaces a raw traceback or a blank screen after Rung 2.
- K2: Doctor reads anything other than green on a clean machine after Rung 2 (a "degraded"
  that is actually fine = fix Doctor's honesty, not the wording).
- K3: install-over-install loses any lens (durability promise C8).
- K4: the fix set requires touching the release workflow in a way that can only be tested by
  cutting a live release — stop, report, operator rules.
- K5: witness session (Rung 4) finds a NEW error class not caught by Rungs 1–3 — the harness
  was insufficient; extend the harness first, then re-run, then re-witness.

## 3. Rung 1 — BASELINE (measure the live product, not the tree)

1. Identify the **live** download: the tag the public site actually points at, and confirm the
   asset resolves (HTTP status, size). Record tag + date. Do not quote a remembered version.
2. On a **clean Windows** box/VM and a **clean Mac** (no dev tools, no Python assumption, no
   prior install): download by clicking the same button a teacher clicks. Install. First run.
3. Record EVERY error verbatim — exact text, where it appeared, what a teacher would do next.
   Screenshot or transcript per error. Reproduce Olga's 09-03 path as closely as possible.
4. Run Doctor on both; record full output.
5. Hunt the known class: `python3`-class bugs across `desktop/` (hardcoded interpreter names,
   dev-box path assumptions, missing-binary assumptions). Grep the whole install/first-run
   path, list every instance found — this class already crashed Doctor once (`3eaa943`).
6. Commit `dev/BASELINE_U1_INSTALL_2026-09-04.md`: live tag, per-platform error register
   (numbered E1, E2, …), Doctor outputs, class-hunt results. Baseline is evidence — no fixes
   in this rung.

## 4. Rung 2 — BUILD (fix the class, not the surface)

For each numbered error: fix the **class** it belongs to, add a locking test that was red
first, and give the failure path a **named message** — which check failed, on what, and what
the teacher should do. No traceback, no blank, no confident wrong answer.

Required end-state:
- Every first-run failure path in the register returns a named message.
- Doctor green on clean Windows AND clean Mac (K2).
- Install-over-install keeps every lens — write the C8 durability test now (it is day-3 work
  in the readiness path, but U1's fix wave is when it is cheapest to break, so it locks here).
- Full suite green (2917+ at last count — the count grows; zero failures is the invariant).

## 5. Rung 3 — SABOTAGE (the harness attacks the installer)

Each scenario must either work or produce a named error. Automate what can be automated;
record manual runs with transcripts:

- S1: no local model installed (Ollama absent).
- S2: no network at first run.
- S3: non-admin user account.
- S4: non-ASCII username / install path; spaces in path.
- S5: OneDrive-redirected home directory (Windows).
- S6: second install over a first that has real lenses (C8 must hold).
- S7: kill the app mid-first-run; relaunch (no corrupted half-state, or a named recovery).
- S8: Doctor run on each sabotaged state — it must NAME the sabotage, not read green over it.

Commit `dev/REPORT_U1_INSTALL_2026-09-04.md`: per-scenario verdict PASS / FAIL / CANNOT-TELL,
with the exact message shown.

## 6. Rung 4 — WITNESS (real time, real humans)

**Step 1 — Mical, real time.** Deliver a numbered click-path script the operator runs alongside
the build the moment it lands (his rule: "no future demos ever go like the last two"):

```
1. Click the download button on the live site (not a direct asset URL).
2. Open the installer. Note every dialog verbatim.
3. First launch. Start a timer. Minute one: what is on screen?
4. Run Doctor from the UI. Expected: green, in plain words.
5. Create one student from the sample roster. Expected: lens exists, visible.
6. Quit. Relaunch. Expected: the student is still there.
7. Disconnect network. Relaunch. Expected: works, or names exactly what is unavailable.
Log each step PASS / FAIL / CANNOT-TELL with the exact wording seen.
```

**Step 2 — Olga, unassisted.** Only after Step 1 is fully PASS: Olga installs on her own
machine with her own hands, witnessed, no help given. Each finding logged
PASS / FAIL / CANNOT-TELL with the click path. **This is the acceptance. U1 is level 4 when
Olga succeeds — not when the tests pass.**

## 7. Deliverables

1. Branch `fix/u1-install-to-green-2026-09-04` — fixes + locking tests. NOT merged, NOT pushed
   to main.
2. `dev/BASELINE_U1_INSTALL_2026-09-04.md` (Rung 1).
3. `dev/REPORT_U1_INSTALL_2026-09-04.md` (Rungs 2–3, updated with Rung 4 witness logs).
4. The operator click-path script (in the report, §Rung 4).
5. A one-paragraph honest summary: what moved U1 from 1 to what proven level, with evidence
   paths — and what is still CANNOT-TELL (the Mac install state is CANNOT-TELL today; end
   that).
