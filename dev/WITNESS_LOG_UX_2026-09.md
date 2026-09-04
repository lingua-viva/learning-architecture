# WITNESS LOG — LV UX lane, September 2026

Append-only. One entry per live test. PASS / FAIL / CANNOT-TELL per step, exact wording seen, the release tag tested. A row on the tracker moves only with an entry here.
Rule (plan §0): a Mical PASS = "ready for teacher witness", not green. Green needs Claudia or Olga.

---

## Cycle 0 — 2026-09-04 — main `30f5e03` → auto-release run 33908229547

**What is in it:** the 29 commits of `fix/cefr-write-and-unknown-field-refusal-2026-09-03` (lens field contract; report card → lens with every field accounted for and idempotent re-apply; Observe → lens, typed and voice; Prepare and the parent note reading the lens; CEFR plus levels; Doctor `python3` fix; `lv lens-query`; the readiness path, the UX set, three specs, one prompt). Full suite on PC-23: 2,987 passed / 34 failed, all 34 identical on untouched main.

**Outcome of run 33908229547 (`30f5e03`): FAILED at "Test gate"** — Health, Backend smoke, desktop-release and pin-site skipped; nothing shipped; v0.2.84 stayed live.
**Cause, proven on Linux/Python 3.11 (WSL clone at `30f5e03`, LF bytes):** `src/web.py` is a contract-protected file (`contracts/UI_CONTRACT.yaml`, v180) and cycle 0 changed it without a bump — `test_ui_contract_check_passes` and `test_ui_contract_lock_matches_live_files` fail (`locked f9d50f5c… / actual 2dc3cb74…`). On PC-23 those two tests already fail for CRLF reasons (Windows baseline rows 32–33), which is why the Windows "0 new failures" could not see it. Class: **a Windows-baselined test can mask a real Linux failure** — the CI replica in WSL now exists so this class is measurable here.
**Fix:** `fix/ui-contract-v181-lens-routes` = `604a823` (bump-log v181, `EXPECTED_VERSION = 181`) + `f22e7a6` (lock re-taken by `check_ui_contract.py --bump` on the Linux LF checkout; every hash equals the git blob's sha256; contract tests 8 passed / 1 skipped on Linux).
**Re-push:** `f22e7a6` -> `main` at 2026-09-04 after a second window check (0 in flight). Full suite on Linux/3.11 in WSL at `f22e7a6`: **3,035 passed / 5 failed / 34 skipped / 32 xfailed in 1m45s**; the same 5 fail identically at `71b069d` (the last green CI commit) in that environment — repo dir name (`lv-ci-full` != `learning-architecture`), root user (read-only file test), and a `pytest` NameError in `test_ask_grounding_surface.py` — so 0 new failures on Linux against the last green commit.

**Release tag:** _(filled in when the chain completes)_
**Live download contains `30f5e03`:** _(verified before "ready" is said)_

### Mical — U1 click path (prompt §6) on the live download

| step | expected | verdict | wording seen |
|---|---|---|---|
| 1 download button → tag served | desktop-v0.2.85 | | |
| 2 installer dialogs | none unexpected | | |
| 3 first launch, minute one | app usable, no traceback | | |
| 4 Governance → Doctor | green, plain words | | |
| 5 Students → classe-3B.csv → approve → confirm | 6 lenses, accents intact | | |
| 6 quit, relaunch | 6 students still there | | |
| 7 network off, relaunch | works or names what is unavailable | | |

### Mical — the chain that is level 3 on a fixture (cheat-sheet beats 3, 5, 6, 7)

| step | expected on v0.2.85 | verdict | wording seen |
|---|---|---|---|
| A upload `pagella_abigail_chang.txt` → Update lenses | CEFR reading A2 / writing A1 / speaking **A1+** / listening A2; the apply result lists what was written, what needs confirmation, and **names every field it refused** | | |
| B apply the same report card again | nothing doubles (same counts on the lens) | | |
| C Observe (typed): `Abigail finished early again and could benefit from extension activities. Listening: A2+.` | saved; the lens gains an Advanced/Enrichment entry marked as a teacher note; listening moves to A2+ | | |
| D Students → Abigail → lens | report entries and the note both visible, with where each came from | | |
| E Student Summary → Draft | the note mentions the listening progress AND a strength from the report card; nothing invented | | |

_(FAIL → verbatim error back to PC-23. PASS → tracker row to "Mical-passed, awaiting teacher witness".)_
