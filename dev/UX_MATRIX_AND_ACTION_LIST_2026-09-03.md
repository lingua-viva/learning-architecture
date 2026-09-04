# UX MATRIX + THE HARD LIST — Still I Rise, two weeks

**Date:** 2026-09-03 · **Operator:** Mical Neill · **Seat:** PC-23
**Companion to:** `dev/PLAN_SIR_SPLIT_AND_ONE_LOGIC_2026-09-03.md` (rulings R1–R4, C1–C9)
**Bar (R4):** a teacher uses it **unattended on real work**.

---

## 0. The UX list already exists. It needed finding, not writing.

`qa/2026-08-29_claudia-full-audit/UX_WALKTHROUGH_HARNESS.md` — 19 views, walked
view-by-view, 328 lines. It is Claudia/La Scuola shaped and dated 08-29, so it
is **stale in three specific ways** rather than absent:

1. it walks HOME / DAILY / PLAN / SLACK, which Still I Rise hides (C4);
2. it has no admin surface at all — the three UXs the operator named
   (query lenses, teacher lenses, teacher onboarding) appear nowhere;
3. it predates the ASSESS oral work entirely.

**This file supersedes it as the planning surface.** The harness stays as the
walkthrough script and should be re-cut per profile once §4 lands.

---

## 1. The pipeline, as the operator states it

```
   INFO IN  ──►  PARSE TO LENS  ──►  LENS  ──►  OUTPUT  ──►  QUERY  ──►  MODIFY
                                      │                                     │
                                      └──────────── teacher/admin ──────────┘
                                            always the final view and control
```

Everything below is scored against which stage it serves. The operator's own
reading holds and the tree agrees with it: **the hard part is getting
information into the right field.** The verbs that produce outputs already
exist; they are unwired, not unbuilt. Query is comparatively cheap *once the
lens structure is normalised* — and it is not normalised today (§3.1).

---

## 2. THE UX LIST — what will actually be tested

**T** = teacher · **A** = admin · **SIR** = ships in Still I Rise ·
**LS** = La Scuola only

| # | UX | Who | SIR | Stage | State today |
|---|---|---|---|---|---|
| U1 | Install & first run | T | ✅ | — | **BROKEN — witnessed** (C6) |
| U2 | Import a roster → lenses exist | T | ✅ | in→lens | Reports `done`, creates 0 |
| U3 | Upload a report card → lens updates | T | ✅ | in→lens | **Works as of today** |
| U4 | Observe: speak/type a comment → lens updates | T | ✅ | in→lens | Routing not wired |
| U5 | Assess: oral exam → diagnostic + lens | T | ✅ | in→lens→out | Not built |
| U6 | Assess: written/photo exam → diagnostic + lens | T | ✅ | in→lens→out | Not built, highest risk |
| U7 | View a lens | T | ✅ | lens | Exists |
| U8 | **Edit a lens by hand** | T | ✅ | modify | Not built — makes U4/U5 safe |
| U9 | Prepare: differentiated materials | T | ✅ | lens→out | Exists, the "big one" |
| U10 | Summaries: parent report | T | ✅ | lens→out | Exists |
| U11 | Ask | T | ✅ | query | Partly works (C6) |
| U12 | Sources / file map | T | ✅ | in | Exists |
| U13 | Governance / Why / Privacy / Health | T | ✅ | — | Exists |
| U14 | Profile / Settings | T | ✅ | — | Exists |
| U15 | Home / Daily / Plan | T | ❌ hide | — | Hidden for SIR (C4) |
| U16 | Slack | T | ❌ hide | in | Hidden for SIR |
| U17 | Reflect | T | ✅ | — | Exists |
| **U18** | **Admin: query across lenses** | A | ✅ | query | **Not built** |
| **U19** | **Admin: create/manage teacher lenses** | A | ✅ | in→lens | **Not built** |
| **U20** | **Admin: onboard a teacher** | A | ✅ | — | **Not built** |

`adminNav` already exists in `static/index.html:1495` (programme, evidence,
capacity, trends, knowledge) — so there IS an admin shell. U18–U20 are not
greenfield; they are unwired against a lens store that is not yet queryable.

---

## 3. WHERE THEY CONVERGE

### 3.1 The field contract — serves 13 of 20 UXs

Measured on the tree today. **Four field lists, no authority, disagreeing in
both directions:**

```
data_in_contracts.STUDENT_LENS_FIELDS      58
lens_extract._LENS_FIELD_IDS               10
student_lens.SUPPORT_CATEGORY_IDS           9
store.UPDATABLE_PROFILE_FIELDS              5

only in SUPPORT_CATEGORY_IDS:  advanced_enrichment, personal_context
only in _LENS_FIELD_IDS:       academic_strengths, personal_strengths,
                               strategies_trialed
```

This is the same defect as the three safeguarding detectors, one floor down,
in the same repo, in the same week. It is also *why* the CEFR levels could be
extracted and never written: nothing declares what a lens field IS, so an
extractor can emit a path the writer does not implement and no one is obliged
to notice.

**Serves:** U2 U3 U4 U5 U6 U7 U8 U9 U10 U11 U18 U19 — every stage of the
pipeline except install. It is the highest-convergence item on the board by a
wide margin, and every later input and output gets cheaper behind it.

### 3.2 Editable lens (U8) — serves every automatic-routing UX

U4, U5 and U6 all put a machine's guess into a child's record. None of them is
safe to ship until a teacher can correct the guess in two seconds. U8 is not a
nicety; it is the thing that makes automatic routing acceptable at all, and it
is what the operator described to the customer: *"once it's there you can
modify it and you can change it if you want."*

### 3.3 Install (U1) — gates literally everything

Olga hit repeated errors live on the call, and one of them exists in no log:
*"another error popped up but I accidentally closed it."* Every other UX on
this list is unreachable behind it, and it is the only item that has already
cost a customer her time.

### 3.4 Query (U18) — cheap AFTER 3.1, expensive before

The operator's read is right. A query surface over four disagreeing field
vocabularies has to special-case each one; over a declared contract it is a
projection. **Sequencing U18 before the contract would cost roughly double.**

---

## 4. THE HARD LIST — 15 items, in order

Ordered by convergence, then by what blocks what. Each is small enough to
finish, test end to end, and stop touching.

| # | Action | Serves | Size | Why here |
|---|---|---|---|---|
| **1** | **Lens field contract** — one declared registry; writer enforces it; test fails on drift | 13 UXs | 1d | Highest convergence. Everything downstream gets cheaper |
| **2** | **Install/first-run to green** — reproduce Olga's errors, name every failure | all | 1–2d | Gates everything; already cost a customer |
| **3** | **Roster flow: `done` must mean created** — or refuse by name | U2 | 0.5d | U3–U6 are unreachable without students |
| **4** | **Lens durability test** — install-over-install must never drop a lens | all | 0.5d | A verbal promise (C8) pinned by nothing |
| **5** | **Editable lens (U8)** | U4 U5 U6 | 1–2d | Makes automatic routing safe to ship |
| **6** | **SIR profile: hide Home/Daily/Plan/Slack** (keep handlers) | U15 U16 | 0.5d | Committed to the customer; reversible |
| **7** | **Observe → the document logic** (Project 1) | U4 | 2d | The operator's stated #1; cheap behind #1 |
| **8** | **Model ruling R2 applied + pinned** | U1 U11 | 0.5d | Two lists disagree; customer-visible download |
| **9** | **Oral input: record-in-app, 3-min gate, Whisper** | U5 | 2d | R3; Whisper already installed |
| **10** | **Oral diagnostic output** — flow/syntax/grammar/vocabulary → lens | U5 | 2d | C2. **No grade** (C1) |
| **11** | **Dimension indicators (literacy 8/10)** as *calibration evidence* | U5 U6 U18 | 1d | Operator ruling; see §5 guardrail |
| **12** | **Assessment document rendered FROM the lens** | U5 U6 | 1d | Lens is the store; the doc is a view |
| **13** | **Admin: query across lenses (U18)** | U18 | 1–2d | Cheap only after #1 |
| **14** | **Admin: teacher lenses + onboarding (U19/U20)** | U19 U20 | 2d | Shell exists in `adminNav` |
| **15** | **Written/photo assessment (U6)** | U6 | ?? | **Most likely to miss. Schedule last** |

**Weeks 1–2 realistically covers 1–10.** Items 11–14 are the following sprint.
**Item 15 is the one to expect to slip**, and the operator has already told the
customer pictures "should work" while telling her it is untested (C7).

---

## 5. THE GRADING GUARDRAIL (operator ruling, 2026-09-03)

The operator's clarification and the customer's agreement reconcile, but only
with a line drawn:

- **The system never emits THE grade.** Olga declined that in terms: *"automatically not graded ... Correct."*
- **The system MAY emit per-dimension indicators** (literacy 8/10) to normalise
  across teachers. This is not new scope — `ontology/education/assessment.yaml`
  already carries `calibration`, and the LV fork spec names
  `LV-ASS-005: Inter-rater Calibration (teacher consistency)`.

**The guardrail:** the indicator lands in the lens as **evidence with a source**,
and the teacher's grade is a **separate, teacher-authored field**. The moment an
indicator can become the grade without a teacher touching it, the product has
built the thing the customer declined — and the thing the Lens Engine analysis
says flips every liability shield (*"never ship scoring"*).

---

## 6. PRIOR ART — Palette's wire contract

The operator's instinct was right; the mechanism transfers almost unchanged.

`palette/sdk/agent_base.py` + `sdk/integrity_gate.py`, wire contract V2.2:

- a **fixed envelope**: 7 canonical fields in, 7 out, linked by ID;
- **every ID reference validated against a registry** (taxonomy / library) —
  a reference that does not resolve is reported;
- the **glass-box invariant**: *"if status != success, blockers MUST explain
  why"*;
- and the property that makes it usable rather than hated:
  *"Warnings are informational, not blocking — **glass-box, not gatekeeping**."*

Mapped onto the lens:

| Palette | Lens |
|---|---|
| envelope schema | the declared field registry |
| RIU/LIB reference must resolve in taxonomy | field_path must resolve in the registry |
| non-success ⇒ blockers explain why | unwritable field ⇒ named refusal (**shipped today**) |
| warnings inform, never gatekeep | a bad field never voids a teacher's whole import |

The glass-box invariant landed in `student_lens_writer.py` this morning,
independently, before this file was written. The contract is the other half.

---

## 7. What I would do first, and why it is not the exciting one

**Item 1, the field contract.** Not Observe, not oral.

It is one module, four lists collapsed to one, roughly a day, and a parity test
holds it so it genuinely never has to be touched again. It converts every later
input from *a fresh integration* into *one row*. And without it, items 7, 9, 10,
11, 13 and 14 each re-create the CEFR defect in a new place — because each one
adds field paths to a writer that, until this morning, could receive a field it
did not implement and say nothing at all.
