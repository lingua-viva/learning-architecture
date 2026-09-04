# LV LANE STATE — the picture, as the PC-23 orchestration seat takes the lane

**Date:** 2026-09-04 (afternoon) · **Seat:** PC-23, now the LV orchestration agent (operator's word, 2026-09-04) · **Operator / live tester:** Mical (PC-0) · **Teacher witnesses:** Claudia (La Scuola), Olga (Still I Rise) · **Scoreboard:** the live team tracker (Mical, Jason, Chip — not a file in this repo)
**Governing plan:** `dev/PLAN_PC23_LV_UX_LANE_2026-09-04.md` (PC-0 orchestration, on `main` at `38e7298`). This document does not replace it; it records where everything is before the lane's first cycle, so nothing is lost and nothing is assumed.

---

## 1. Where the code is, verified by object

| line | tip | contains | verified how |
|---|---|---|---|
| `origin/main` | `38e7298` | v0.2.84 (live), the Italian safeguarding fix `71b069d`, the U1 prompt, `demo-data/` (classe 3B, 9 files), the lane plan | `git fetch`; auto-release run on `71b069d` completed **success** 2026-09-03 19:08Z (public API); `https://linguaviva.art/` pins `desktop-v0.2.84` (curl, today) |
| `fix/cefr-write-and-unknown-field-refusal-2026-09-03` | `de4a857` = remote | **main + 27 commits**: the lens field contract, the writer with the accounting invariant, Observe → lens (typed and voice), Prepare and the parent note reading the lens through the OUT filter, CEFR plus levels, import-log source names, the Doctor `python3` fix, the trash-collector census, `lv lens-query` (U18), the four readiness/UX-set documents, three specs and one prompt | rebased onto `38e7298` this afternoon with a published one-file conflict map (`desktop/package.json`, different hunks, both kept); 27/27 preserved; the three load-bearing files byte-identical to the pre-rebase backup tag `backup/lv-branch-pre-sync-2026-09-04` |
| PC-23 local tree | clean; `scratch/` untracked by design | — | `git status --porcelain` |

**Nothing on the branch is on `main`. Nothing on the branch is in any download.** By `AGENTS.md`'s definition, all 27 commits are *not pushed*. That is the first fact of the lane.

## 2. What the 27 commits do for the queue (why they go first)

The plan's queue is U1 → U13 → C8 → U2 → U8 → SIR profile. Four of those six lean on the branch:

| queue item | what the branch already carries | what is still to build |
|---|---|---|
| **#1 U1 install** | the Doctor crash on every Windows box is fixed (`sys.executable`, four sites); `/api/health` no longer reads "degraded" for that reason | everything in the U1 prompt's Rungs 1–3: the clean-machine baseline, the error register, the `python3`-class hunt across `desktop/`, sabotage S1–S8, the click path |
| **#2 U13 safeguarding** | the spec that reframes it (`SPEC_SAFEGUARDING_P0_END_TO_END`), corrected twice today; the route-level and surface-level assertions designed; the pending-count route designed | the tests themselves (two halves, red first), the pending route + badge |
| **#4 U2 roster** | the finding (Grade dropped; `approve` creates nothing) is measured and written down | the fix |
| **#5 U8 editable lens** | the contract's `review_required` / `lens_update` / `accounting` payloads exist on the wire; the store ops are enumerated; the endpoint gap is named in the census | the endpoints and the two-second control in the Students view |
| (foundation) | U3 report card and U4 Observe at level 3 on a fixture; U10 parent note reads the lens; refusals on the wire; re-import idempotent | witness by Mical, then a teacher |

**Proposal for cycle 0:** the branch goes to `main` as one merge *before* U1's branch is cut — it is the ground the UX branches stand on, and the Doctor fix is U1's first error class already closed. It follows every lane rule except one it cannot satisfy on this box (§3). Mical's word decides.

## 3. The lane rules, checked against this box today

| rule | status on PC-23 |
|---|---|
| 1 one release at a time (`gh run list`) | `gh` 2.99 is installed but **not logged in**; the public API answers without auth and shows **0 runs in flight** as of this document. Either `gh auth login` on this box, or the seat checks the window through the API and says which it used. |
| 2 branch per UX | will do: `ux/u1-install` next; the 27-commit branch is the foundation, not a UX |
| 3 class fix + red-first locking test | the branch's fixes carry 111 new tests across seven files; every guard was watched failing (sabotage tables in the reports) |
| 4 full suite green before a main push | **running now** on the rebased tree (`scratch/full_suite_20260904.txt`); the bounded suites read 843 passed / 10 failed this morning, all 10 Windows artifacts (sqlite_vec, CRLF sha256, CRLF ui-contract). The plan's "zero failures" invariant is measured on PC-0/CI; this box reports its delta against the Windows baseline and names every failure |
| 5 verify live, then "vX ready — test U-n" | understood; never before the download resolves and contains the commit |
| 6 PASS / FAIL / CANNOT-TELL only | as in every report this week |
| 7 no API key, no real child data | no key on this box; the fixture students were removed from the real store on 09-04 morning on Mical's word; `demo-data/` is the fixture set from here |
| 8 witness log | `dev/WITNESS_LOG_UX_2026-09.md` created on first live verdict |

## 4. What I am carrying from Mission Canvas and Trop AI into this lane

- **The lens contract is the same shape in all three.** LV's student lens is the reference; MC's soul seed (built today, `docs/spec-operator-lens-seed-2026-09-04`, Rungs 1–2) inherited its evidence-chain law; Trop's import preview ("unknowns named, never guessed") is LV's accounting invariant on a spreadsheet. A fix in one is a class to check in the others.
- **The sensitivity gate is one class across all three.** MC's 08-15 seed kill (high pointers rendered verbatim) is the same defect as LV's BUG-4 and the same fence as Trop's commercial wall. U13 here should reuse the "withhold and count" shape landed in MC today.
- **Chip's retest harness** (Trop, `qa/2026-09-03_chip-retest/`, 11 checks against 11 fixed findings) is the format the witness log should copy: one row per fixed finding, PASS/FAIL/CANNOT-TELL, verbatim wording.
- **PC-0 also mirrors MC commits into the retired `pretendhome/pretendhome` remote**; that is the two-remote pattern and nothing to act on, but it is why "is it on main" must always be answered by object, never by memory.

## 5. CANNOT-TELL, right now

- Full-suite result on this tree (running).
- Whether Claudia ran the 09-02 safeguarding retest; her Part 3 answers.
- The Mac install state (the U1 prompt ends that; not started).
- Whether the live tracker's current ordering matches the plan's queue (the tracker is not visible from this box; the plan is the authority I have).
