# THE UX SET ACROSS THE THREE REPOS — what we are trying to enable, and where each one stands

**Date:** 2026-09-04 · **Operator:** Mical Neill · **Seat:** PC-23
**Companion:** `dev/PATH_TO_UX_READINESS_2026-09-04.md` (the level scheme and Lingua Viva's hard list). This document applies the same scheme to Mission Canvas and Trop AI, from two read-only surveys run today (paths cited are inside each repo; MC paths are objects on `mc/main`).
**Levels:** 0 not built · 1 backend exists · 2 reachable in a UI · 3 works end to end on a fixture, result inspected · 4 works for the intended user on real data, witnessed · 5 unattended for a week. A UX gets the highest level **proven**.

---

## 1. What the three repos are, in one line each, and who has used them

| repo | what it is | intended user | real-user evidence |
|---|---|---|---|
| **Lingua Viva** (`learning-architecture`) | the education fork of the MC engine; a teacher's local app: roster → report card / Observe → student lens → materials, parent notes, admin queries | teachers (Claudia, La Scuola; Olga, Still I Rise), admins | **yes, twice**: Claudia's 08-29 walkthrough (6 BUG / 20 FRICTION / 31 GOOD, two P0 safeguarding), Olga's 09-03 install attempt (broken, witnessed) |
| **Trop AI** (`trop-ai`) | a vertical of the MC pipeline for an IT-hardware distributor: order spreadsheets → lifecycle store → morning brief, risk, scorecard, governed Ask, customer drafts | Luis (Director General) and four team personas (`lenses/LENS-ORG-TROPICAL-IT-001.yaml:140-231`) | **a tester, not the customer**: Chip ran the 57-check plan (0 P0 · 10 P1 · 4 P2, `qa/RETEST_HARNESS_2026-09-02.md:4`). *"No operator-clicked import has ever landed"* (`QA_TESTING_PLAN.md:98`). No evidence Luis has ever used it; the 09-03 demo is not recorded in the repo. |
| **Mission Canvas** | the engine: governed pipeline, ontology, lenses, 15 primitives, desktop with 14 canvases × 74 experiences, CLI, MCP, voice, phone projection | operator/founder, domain professionals per canvas, agents as consumers, a phone holder | **almost none, and it says so**: run-record surface matrix 1/5 (`dev/BASELINE_FOUR_INSTRUMENTS_2026-09-01.md` §0.1); turn-cost history file does not exist — *"no completed real turn has passed the choke point since it landed"*; 16 of 218 routable nodes ever exercised by anything counted operator-origin (`dev/INDEX.md:12-13`); GIR@L1 = 0.000 over 564 claims. Genuinely real events: one `organize` run on the operator's Documents, one live calendar fetch, one 3,387-byte companion push, three weeks of egress logs, the published voice audio. |

The three repos already share one **shape** — the operator's own words, 2026-09-03: *"multi-input → lens → multi-output"* — and one **discipline**: classify before reasoning, commercial/child data never leaves the box, absence is a verdict, approval before anything outbound.

## 2. The UX families — the set, stated once, instantiated three times

Every UX any of the three repos is trying to enable is one of these ten. The table gives, per family, the concrete UX in each repo and its **proven** level today.

| family | the experience, said once | Lingua Viva | Trop AI | Mission Canvas |
|---|---|---|---|---|
| **F1 Install & first run** | a stranger with none of your data installs it and minute one works, or says exactly what is wrong | U1 — **1** (Olga: broken, witnessed; Doctor crashed on Windows until 09-03) | UX-18 — **3** (headless smoke ×3 platforms green; GUI = CANNOT_TELL by design, `dev/TROP_AI_REPO_STATE_2026-09-01.md:107-125`) | G7/G8 wizard — **3** (contract v9, 10/10 checks; install workflows in CI) |
| **F2 Ingest into the lens** | messy real-world input (roster, report card, order sheet, folder) becomes structured lens data, with every field accounted for and unknowns named, never guessed | U2 roster — **3**; U3 report card — **3** (51 fields, 8/5/38 accounted, idempotent; not yet with a model) | UX-1 import — **4 by a tester** ("60 imported / 18 customers / 2 named unknown", `RETEST_HARNESS:113`); the demo's headline beat D3 | organize / sources / GW-DRIVE/CALENDAR/IMAP — **3** (golden workflows need a running server); organize — **4** once on the operator's own Documents (MC-PC-005) |
| **F3 Capture a human's own words into the lens** | a person says or types what they saw and it lands in the right place, with provenance, reversibly | U4 Observe — **3** (typed and voice routes both, as of today) | UX-12 CRM log/commit — **3** (CLI, tests) | the operator lens grown from every query — **the north star, not built**: `filemap.generate_lens_claims()` emits the seed and drops it (`CONVERGENCE_BRIEF_LENS_SYSTEM_2026-08-10.md` §1) |
| **F4 See the lens** | the accumulated record, with where each entry came from | U7 — **2** (witnessed 08-29; safeguarding content visible = P0) | UX-9 customer dossier — **4 by a tester** (accent search cut) | G2 `mc lens` — **2** (done_claim 85, no proof gate) |
| **F5 Correct the lens** | confirm, dismiss, edit in two seconds; purge on request | U8 — **1** (store ops, no endpoints, no UI) | import-mapping confirm / manifest accept-reject — **3** | G2/G3 approve/reject/purge — **2** (done 90, UI) |
| **F6 Ask, governed and honest** | a question routes through the ontology, private data never leaves, a thin answer says so | U11 — **2** (BUG-5: fabricated claims despite "unverified") | UX-6/7/8 — **4 by a tester** (the commercial wall "held perfectly across all four money questions"; cannot-tell is the P0 check) | the 74 canvas rows — **2–3** (proof gates on ~half; 31 action rows "structurally invisible to MEASURE") |
| **F7 Produce from the lens** | an artifact a third party reads, built only from what the lens holds, saying what it lacked, approval-gated | U9 Prepare — **2–3**; U10 parent note — **3** (reads the support profile as of today) | UX-2 brief, UX-3 scorecard, UX-4 risk, UX-5 priorities — **3–4**; UX-10 approval-gated draft — **3** (refuses on a thin order) | the 15 primitives — **1** (one of fifteen built as of 08-22; later mounts "by produces-class alone"); documents/typst — **1** |
| **F8 Govern: why, what left, is it healthy** | "why did you answer that way", the egress statement, the health verdict | U13 — **2** (Health read degraded on Windows until 09-03) | UX-11 trust console — **4 by a tester** | G1 why / G5 health / G6 firewall — **2–3** (`mc health` cannot emit exit 2 — a defect) |
| **F9 Across lenses (admin / team)** | a question over many records, deterministic, projected as codes not names | U18 — **1** (`lv lens-query`, 12 questions, no panel); U19/U20 — **0–1** | UX-5 per-team priorities, UX-3 scorecard — **3** | none found (fleet-shaped queries exist only in LV) |
| **F10 Voice, end to end** | say it, the right thing happens, the answer is spoken; the same governance as typed | voice Observe — **3** (route wired today; Whisper local) | UX-13 — **2, degraded** ("voice not available" on the tester's device) | UX-VOICE — **3** (golden voice loop; public audio real); Nemotron voice-inadmissible ruling stands |
| **(F11) Leave the desk** | the box pushes a projection to the phone; the phone never asks | — | — | companion push — **4 once** (3,387 bytes, gate pass); *"transport and the surface itself do not [exist]"* (`LEDGER_MOBILE_SURFACE`) |

**Honest totals across the three repos:** no UX is at level 5 anywhere. Level 4 by the *intended* user: **zero**. Level 4 by a non-developer tester: Trop AI has five (import, dossier, Ask, the commercial wall, trust console). Level 4 once by the operator himself: MC organize and the companion push. Lingua Viva has the most real users and the most real bugs, which is the right way round.

## 3. What each repo's "one verb" is — read from the repo, not assigned

The 09-03 ruling: one verb driven all the way to voice, LV → Trop → MC. Each repo names its own, with varying clarity:

- **Lingua Viva — Observe.** Named by the operator as priority (plan §2, C9), measured today: typed comment → the right lens section → parent note. The verb is *capture into the lens* (F3), and its voice form already has a route. Remaining to voice-grade: the UI shows what the note did, and U8 lets the teacher undo it.
- **Trop AI — "What's at risk today?"** The repo declares one workflow, *promise-date risk for active orders* (`docs/ONE_PAGER.md:78`), and one voice vision, Luis says "what are my top priorities today?" and gets a panel plus a spoken top three (`dev/SPEC_TROP_4RUNG_VOICE_DASHBOARD_2026-08-27.md:15-21`). The verb is *prioritize* (F7), with *draft* (F7, approval-gated) as the second in the same chain. The repo never uses the word "verb"; this is a reading of two documents.
- **Mission Canvas — the operator lens.** MC's own north star (`SNAPSHOT_LENS-NORTH-STAR-001_happy_place.yaml`, the convergence brief §0): *the first lens is the user, created at install, grown from every query*. That is F3 and F4 for the operator himself, and it is the one UX the engine cannot inherit from a vertical because it **is** the engine's reason to exist. G1/G2/G3 (why / show me my lens / purge) are already the highest-confidence rows in the 74; the gap is one file write (seed the lens from the filemap claims that are generated and dropped today).

Read together, the three verbs are the same verb at three altitudes: **something true about a person or an order enters the lens, with a source, and comes back out in a form someone can act on** — a parent note, a morning priority list, the operator's own profile.

## 4. What the shape implies for a shared definition of "working"

The five properties in the readiness path hold in all three repos already, in their own words:

| property | LV says | Trop says | MC says |
|---|---|---|---|
| every failure path named | refusal register; `unresolved_questions` on the wire | *"unknowns are named, never guessed"* (D3); honest cannot-tell is the P0 check (D7) | *"absence is a verdict"*; CANNOT-TELL never shares a channel with clean |
| nothing fabricated | every parent-note sentence cites an observation or entry id | *"on a thin order it refuses"* (D8) | GIR — *"the lens never claims anything about the person without a source"* |
| reversible | U8 (not built) | import preview → confirm; manifest accept/reject; `trop organize undo`-class | `mc organize … undo`; lens approve/reject/purge |
| private by construction | student data local; personal_context never to family | *"100% of what we show has to work"*; LOCAL ONLY chip on commercial data | `blocks_external` socket-level; the phone never receives the corpus |
| measured, not asserted | walkthrough harness + nightly chain | 57-check plan, three-valued verdicts, 855 tests | `mc improve --measure`, `mc eval existence` — and the repo's own record that a refusal once wrote *"a receipt indistinguishable from a success on THREE surfaces"* |

So the cross-repo UX set does not need a new vocabulary. It needs one hard list per repo in the same ten families, each row at its proven level, re-measured every night, and a teacher or Luis or the operator moving rows to level 4 by hand.

## 5. Where the leverage is, per repo, if the goal is level 4

- **Lingua Viva:** the readiness path's day 1–5 (install, safeguarding test, roster, durability, editable lens). It has users; it needs F1 and F5 to stop losing them.
- **Trop AI:** put the app in front of Luis. Five families are already tester-level-4; the only thing between them and level 4 is the intended user. Connectors (F2 live pulls) are the one family at level 1 that the customer will ask for first (Monday.com, HubSpot: *"none proven against live accounts"*).
- **Mission Canvas:** seed the operator lens at first run (one write, zero latency) and make the run-record surfaces persist a real turn (matrix 1/5 → 5/5). Until a human turn is recorded, every instrument computes over an empty denominator — the 09-03 phase-close finding, unchanged.

## 6. CANNOT-TELL

- Whether the 09-03 Trop demo happened and what Luis saw (nothing after 09-02 in the repo).
- Chip's run-2 verdicts (the retest request exists; her report file is not in the repo).
- MC's current primitive count (1 of 15 as of 08-22; later mounts recorded, net unknown) and current `mc eval experiences` coverage (not run).
- MC's seven chat bridges (`bridges/`): no test, eval, matrix row or manifest found — reachability unknown.
- Four MC product docs with UX-inventory titles were not read for budget (`docs/product/FIRST_60_SECONDS.md`, `UNIFIED_PRODUCT_THESIS.md`, `docs/specs/THE_SPECIALIST_UX_SPEC.md`, `docs/product/rossi-mission/ux_modes_spec.md`). If MC keeps a persona × mode matrix, it is there.
- The literal "operator: 0 across 100 records" figure from the 09-03 ledger was not found as a string in `mc/main`; the adjacent, verified facts (turn-cost file absent; 11 mislabeled operator rows purged; 16/218 exercised) point the same way.
