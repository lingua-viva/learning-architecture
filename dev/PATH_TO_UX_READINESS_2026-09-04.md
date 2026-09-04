# PATH TO UX READINESS — Lingua Viva, two weeks, nine schools

**Date:** 2026-09-04 · **Operator:** Mical Neill · **Seat:** PC-23
**Why this document:** Lingua Viva is the only repo of the three with UXs that work end to end, the only one with real users, and the only one with real feedback. If every UX on the list works in two weeks, it launches in nine schools and reaches hundreds of students. That is worth a harder definition of "works" than "the code doesn't break", and an honest current state per UX.

Everything marked **measured** below was produced by a command run on 2026-09-03/04 (`dev/NIGHT_SUMMARY_2026-09-03.md`, `dev/DIAGNOSTIC_UX_CENSUS_2026-09-03.md`, and the chain run in this session). Everything marked **witnessed** comes from a real teacher (Claudia's audit, `qa/2026-08-29_claudia-full-audit/UX_REPORT.md`, desktop-v0.2.72) or the customer sync (Olga, 2026-09-03). Everything else is CANNOT-TELL and says so.

---

## 1. What "working" means — the definition of done for a UX

"The code doesn't break" is level 1 below. A UX is **ready** at level 4. A UX is **launch-grade** at level 5. Nothing lower goes in front of a school.

| level | name | the test that proves it | who can run the test |
|---|---|---|---|
| 0 | not built | — | — |
| 1 | backend exists | routes classified reachable or backend-only; unit tests pass | a machine |
| 2 | reachable in the UI | a teacher can click to it; `check_route_reachability` has a call-site literal for every route it uses | a machine |
| 3 | works on a fixture, end to end | the whole chain runs over HTTP on a sandbox with a fictional student and the **result is inspected**, not the status code; every failure path returns a named message, never a traceback or a blank | an agent, every night |
| 4 | works for a real teacher on real data, witnessed | a named teacher does it on her own machine with her own students, unassisted, and it produces what she needed; each finding logged PASS / FAIL / CANNOT-TELL with the click path | Claudia or Olga, with the walkthrough harness |
| 5 | unattended for a week | the same teacher used it for five school days with no support message; nothing fabricated, nothing lost, nothing leaked; the durability promise (C8) held across one update | the pilot itself |

**Five properties every level ≥ 3 must have** (from R4, the customer sync, and the contract work):

1. **Every failure path is named.** A refusal says which field, which file, which student, and what to do. No traceback, no blank, no confident wrong answer.
2. **Nothing fabricated.** Every sentence about a child cites an observation id or a lens entry id. If the lens does not have it, the output says what it did not have (`fields_missing`). Zero data reads as "not enough data", never as zero.
3. **Reversible.** Automatic routing is only acceptable because a teacher can correct it in two seconds (U8). No one-way write to a child's record without a teacher touch.
4. **Private by construction.** Personal context and safeguarding content never reach a parent or a projected admin surface; names never leave the machine; the sandbox trap (both home variables) is a test, not a memory.
5. **Measured, not asserted.** A number with a denominator, produced by a command, on a date.

---

## 2. THE HARD LIST — every UX, current level, evidence, what moves it

Levels are conservative: a UX gets the highest level **proven**, not the highest level plausible. "Fixture chain" = the sandbox run in this session (roster → report card → Observe → lens → summaries).

| # | UX | level | evidence | what moves it to 4 |
|---|---|---|---|---|
| U1 | Install & first run | **1** | witnessed BROKEN (Olga, 2026-09-03: repeated errors, one lost); Doctor crashed on every Windows box until `3eaa943` | reproduce on a clean Windows and a clean Mac; every first-run error named; then Olga installs again, witnessed. **Gates everything.** |
| U2 | Roster → lenses exist | **3** | fixture chain: `ingest → preview → approve → confirm` creates the lens; `approve` alone creates nothing (by design, confusing); Grade column is NOT stored | make `done` mean created or say why; store grade_level from the CSV; witness with a real roster (Claudia's 40) |
| U3 | Report card → lens | **3** | fixture chain: 51 fields, 8 written / 5 review / 38 named refusals, CEFR incl. plus levels, idempotent re-apply, refusals on the wire. **Not witnessed with a model** (PC-23 has none) | run on PC-0 with qwen3:8b; witness with a real report card; confirm the UI shows `unresolved_questions` and a confirm control for `review_required` |
| U4 | Observe → the right section | **3** (as of this session) | fixture chain: typed comment → `advanced_enrichment.evidence` (teacher note) + CEFR A2+; voice route too. UI does not yet render `lens_update` | UI shows what the note did to the lens; witness with a real comment; the four legacy direct-writes in `observation_capture.py` retired |
| U5 | Assess: oral → diagnostic + lens | **0** | `assessment_generator.py` is the MYP generator, not this. Whisper provider exists. Change log: `dev/ASSESS_CHANGES_NEEDED_2026-09-03.md` | S1 ruling (storage shape) → S2–S6 |
| U6 | Assess: written/photo | **0** | not built; customer told "should work"; highest risk | schedule last; OCR-with-confirmation |
| U7 | View a lens | **2** | witnessed 08-29 (Students view; "insufficient data" uniform; safeguarding content visible in normal record = BUG-4 P0) | verify BUG-4 is closed with a test; lens shows provenance (report / teacher note) per entry |
| U8 | Edit a lens by hand | **1** | store ops exist (`set_avoid_pairing_with`, `replace_support_profile`, confirm/dismiss); **no endpoints, no UI**; census §4.2 | endpoints + a two-second correct/dismiss control in the Students view. **Makes U3/U4 safe.** |
| U9 | Prepare: differentiated materials | **2–3** | fixture: `roster-split` and `prepare/activity` run without a model; `generate` returns 3 tier cards without a model **and does not say so**; witnessed 08-29 BUG-1 (ignores uploaded content), FRICTION-7/8 (tiers) ; course-file text bypasses the injection guard | `generate` says what it had and did not have (OUT filter); guard the course file; witness BUG-1 fixed with Claudia's own unit |
| U10 | Summaries: parent report | **3** (as of this session) | fixture chain: note carries CEFR progression + report-card strength; `fields_used` / `source_entry_ids` on the wire; needs/personal context excluded by test. Witnessed 08-29 BUG-6 (fabricated recommendations), FRICTION-16 (tone) | approve/print route (census: `approve`, `to_print_html`, `render_parent_report_pdf` on no route); minimum-evidence gate; tone; witness |
| U11 | Ask | **2** | witnessed 08-29 BUG-5 (fabricated claims despite "unverified"); C6 partly works; no model here | minimum-evidence refusal; cold-start refuses by name (A1); witness |
| U12 | Sources / file map | **2–3** | witnessed 08-29 mostly GOOD; knowledge library not parsed through the guard (latent) | parse library through `document_parser`; witness |
| U13 | Governance / Why / Privacy / Health | **2** | exists; Health read "degraded" on Windows until `3eaa943`; safeguarding P0s BUG-3/4 status **CANNOT-TELL** (gate repaired 09-03, not re-witnessed) | a test that a RED observation is restricted AND absent from the normal record, then witness |
| U14 | Profile / Settings | **2** | exists; provider-connect door CANNOT-TELL (census) | witness connect/disconnect on a clean machine |
| U15 | Home / Daily / Plan | hide (SIR) | witnessed 08-29 "not sure it helps"; C4 hide, keep code | profile flag (item 6) |
| U16 | Slack | hide (SIR) | FRICTION-17 | profile flag |
| U17 | Reflect | **2** | exists; not witnessed | witness |
| U18 | Admin: query across lenses | **1** (as of this session) | `lv lens-query L1..L12` + `/api/admin/lens-query` over the store, 11 tests; **no admin UI panel**; fleet engine reads the vault, not the store | panel in `adminNav`; witness with an admin |
| U19 | Admin: teacher lenses | **1** | `teacher_lens_builder`, `access_control` exist, unreached | build the flow |
| U20 | Admin: onboard a teacher | **0** | not built | build |

**Honest totals:** 0 UXs at level 4 or 5. Two at level 3 that were at 1–2 yesterday (U4, U10), two at 3 that were untested end to end yesterday (U2, U3). Nothing has been witnessed by a real teacher since 2026-08-29, and that audit found 6 bugs, 2 of them P0 safeguarding.

## 3. The chain that is now measured end to end (this session)

```
roster (1 student)  -> lens created
report card (51 fields) -> 8 written / 5 review / 38 named refusals; CEFR A2 / A1 / A1+ / A2
                           second apply: 0 new rows
typed Observe comment -> advanced_enrichment.evidence (teacher_note), listening A2 -> A2+
lens              -> both sources with provenance, 5 CEFR observations, 4 support entries
lens markdown     -> renders all of it (one route, no model)
parent note       -> "In listening, your child's progress is visible..." (from the log)
                     "At school, your child shows strength in ATL: thinking, social..." (from the report card)
                     fields_used [display_name, strengths_profile, support_profile]; missing [grade_level, home_languages]
```

What it exposed and fixed today: Observe was wired to the voice route only; plus levels were dropped by both CEFR extractors; applied imports lost their source filename; the parent note never read the support profile. What it exposed and did not fix: `grade_level` is never set from the roster; "ATL: thinking, social, ..." is report-card jargon in a parent's note (FRICTION-16 class — the mechanism works, the wording needs the voice lens).

## 4. The two weeks — in order, with the launch gate

Ordered by what blocks what (UX_MATRIX §4, revised by tonight's measurements). Each item ends at **level 3 by an agent at night** and **level 4 by a teacher the next day**, or it is not done.

| day | item | serves | done means |
|---|---|---|---|
| 1–2 | **U1 install to green** on clean Windows + Mac; every first-run error named; `python3`-class bugs hunted across `desktop/` | all | Olga installs unassisted |
| 2 | **safeguarding P0 closed with a test** (RED → restricted, absent from normal record, notification drained by something) | U4 U7 U13 | test red before, green after; witnessed |
| 3 | **U2 roster**: `done` = created; grade stored | U3–U6 | Claudia's roster, witnessed |
| 3 | **durability test** (install-over-install keeps every lens, C8) | all | test |
| 4–5 | **U8 editable lens**: confirm / dismiss / correct in two seconds; UI shows `review_required` and `lens_update` | U3 U4 U5 | Claudia corrects a mis-routed note, witnessed |
| 5 | **SIR profile**: hide Home/Daily/Plan/Slack; default view Students | U15 U16 | both profiles boot in a test |
| 6 | **U3 + U4 on PC-0 with qwen3:8b**; report card and Observe witnessed with real data | U3 U4 | levels 4 |
| 7 | **U10 approve/print route**; minimum-evidence gate; tone through the voice lens | U10 | Claudia sends one real note |
| 8 | **U9 honesty**: `generate` says what it had; course file guarded; BUG-1 re-tested with Claudia's unit | U9 | witnessed |
| 9 | **U11 Ask**: minimum-evidence refusal, cold start refuses by name | U11 | witnessed |
| 10 | **U5 oral**: S1 ruling → S2 registry → S3 gate → S4 Whisper parity | U5 | level 3 |
| 11 | **U5 diagnostic + document** (S5, S6) | U5 | level 3, then witnessed |
| 12 | **U18 admin panel** over `lens_query` | U18 | an admin runs L7 in the UI |
| 13 | **U6 written/photo** — first honest slice: PDF text only, photos refused by name | U6 | level 3 |
| 14 | **launch gate** (below) | — | — |

**The launch gate for nine schools** — all of these, or the launch waits:

1. U1, U2, U3, U4, U7, U8, U10, U13 at **level 4** (witnessed by a teacher who is not the developer).
2. Safeguarding P0s closed by a test that was red first.
3. Durability test green across one update on each platform.
4. Zero fabricated sentences in a 20-report sample: every parent-note sentence resolves to an observation id or entry id.
5. A Doctor run on each teacher's machine reads green (not "degraded").
6. Italian parity: every detector and extractor has an Italian test row beside its English one.
7. The two model fences hold: qwen3:8b default (R2); no external call without the egress sanitizer.

**What launches at level 3 with a label, not level 4:** U5 (oral) if S1–S6 land; U18 admin; U17 Reflect. **What does not launch:** U6 written/photo (say so to Olga before day 14, not after), U19/U20.

## 5. How this stays honest

- The walkthrough harness (`qa/.../UX_WALKTHROUGH_HARNESS.md`) is re-cut per profile and run by a teacher, not by the person who wrote the code; findings are PASS / FAIL / CANNOT-TELL with the click path.
- Every night the chain in §3 runs on a sandbox and the levels table is regenerated from it; a level that goes down is reported as going down.
- `scripts/trash-collector.py` runs after every wiring change; a UX whose code is "reached only from tests" is level 1, whatever its route manifest says.
- No number in this document is quoted forward. Re-read the tree.

## 6. CANNOT-TELL, today

- Whether BUG-3/4 (safeguarding P0, 08-29) are closed. The gate was repaired 09-03; no test asserts the two halves together.
- Whether the UI renders `unresolved_questions`, `review_required`, `lens_update`, `fields_used` — no UI walk since 08-29; the payloads exist.
- Everything that needs a local model, until PC-0 runs the chain.
- Who drains safeguarding notifications outside `src/`.
- The state of the Mac install.
