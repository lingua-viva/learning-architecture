# WITNESS LOG — LV UX lane, September 2026

Append-only. One entry per live test. PASS / FAIL / CANNOT-TELL per step, exact wording seen, the release tag tested. A row on the tracker moves only with an entry here.
Rule (plan §0): a Mical PASS = "ready for teacher witness", not green. Green needs Claudia or Olga.

---

## Cycle 0 — 2026-09-04 — main `30f5e03` → auto-release run 33908229547

**What is in it:** the 29 commits of `fix/cefr-write-and-unknown-field-refusal-2026-09-03` (lens field contract; report card → lens with every field accounted for and idempotent re-apply; Observe → lens, typed and voice; Prepare and the parent note reading the lens; CEFR plus levels; Doctor `python3` fix; `lv lens-query`; the readiness path, the UX set, three specs, one prompt). Full suite on PC-23: 2,987 passed / 34 failed, all 34 identical on untouched main.

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
