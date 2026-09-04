# PLAN — Still I Rise split, one lens-update logic, and Assess

**Date:** 2026-09-03 · **Operator:** Mical Neill · **Seat:** PC-23
**Deadline named by the operator:** two weeks to have Assess working definitively.
**Status:** plan + open rulings. Nothing built. Every claim below was read off the
tree in this window, with the file and line.

---

## 0. Recon findings that change the shape of the work

### 0.1 The "single logic" already exists. Observe just does not use it.

This is the biggest finding and it makes PROJECT 1 much smaller than it sounds.

`src/lingua_viva/docpipe/lens_extract.py` already is the one logic:

| What | Where |
|---|---|
| parse a document into lens fields | `extract_for_lens_update()` — `lens_extract.py:901` |
| write those fields to the lens | `apply_extractions_to_lenses()` — `lens_extract.py:1413` |
| route a sentence to the right lens field | `_route_to_support_category()` — `lens_extract.py:193` |
| per-student isolation (cross-contamination guard) | section splitter, same file |
| safeguarding gate (restricted vs ordinary lens) | `_is_red_safeguarding()` — repaired 2026-09-03 |
| per-field trust | `verified` / `needs_confirmation` / `classify_failed` |

Observe runs a **different, shorter** path: `src/education/observation_capture.py`
→ `capture_with_safeguarding()`. It shares exactly one function with the document
pipeline — `suggest_support_categories()` — and nothing else. It never calls
`extract_for_lens_update`, so it never gets sentence-by-sentence routing,
per-field confidence, or the review contract.

**So PROJECT 1 is not "build one logic." It is "route Observe through the logic
that already runs for documents."** That is a wiring project with a real test
surface, not a new subsystem.

### 0.2 Report-card → lens probably failed this morning for a nameable reason

`dev/HANDOFF_LV_LENS_UPDATE_VERB_2026-09-02.md`, PC-0's own handoff, says:

> "API endpoint remains intentionally skipped; spec allowed skipping it for demo
> because existing web two-step import/apply route still works."

The new `lv lens-update` verb is **CLI-only**. The app hits the older two-step
web import/apply route. So the thing that was worked on all week is not the thing
the demo exercised. This is a hypothesis with a cheap test (§1.1), not a
conclusion.

### 0.3 The model default is a written decision, not a bug

`src/lingua_viva/config.py`:

- `LOCAL_MODEL_PREFERENCE` (line 16) lists `nemotron-3.5-lightning` **first**,
  then `qwen3:8b`. This is the order you remember.
- `_TIER_MODEL_MAP` (line 46) hardcodes **`qwen3:8b` for all five tiers** —
  `ultra_gpu`, `strong_gpu`, `mid_gpu`, `weak_gpu`, `cpu_only`.
- `default_model()` (line 192) reads the **tier map**, not the preference list.
- Its docstring (line 186-190) states the intent outright: *"qwen3:8b is the
  minimum viable quality floor... Larger models such as nemotron can still be
  used when explicitly configured or detected as an installed fallback, but they
  are not the default pull."*

So Lightning is never selected as the default on any hardware, by design, dated
2026-08-22. The preference list looks like it implements Lightning-first
fallback and does not drive the default at all.

**This needs a ruling, not a fix.** Reverting a documented decision without one
is how the other direction of this defect gets created.

### 0.4 Removing nav is four array entries, behind a contract gate

`static/index.html:1481` — `teacherNav` is a documented tuple contract
`[id, label, icon]`. Removing Home, Daily, Plan and the Slack utility entry is
four deletions. Two constraints:

- the same comment block says *"brand-home resets view to home for teacher"* —
  removing `home` requires naming a new default view;
- `scripts/check_ui_contract.py` gates `static/index.html` (contract v180,
  3 files locked), so the contract version has to move with the edit.

---

## 1. WORKSTREAM A — Still I Rise, the trim (small, this week)

Ordered so each step is independently verifiable and independently revertable.

### A0. Test the demo sheet item by item, before changing anything

Your instruction. Roster worked; report-card→lens did not. Everything else is
unmeasured. One pass, each item recorded PASS / FAIL / CANNOT-TELL with the
command or the click path that produced it. **No fixes during this pass** — the
pass is the baseline, and mixing fixes into it destroys the comparison.

First test, because it settles §0.2 in ten minutes:

```bash
PYTHONPATH=. python3 src/lv_cli.py lens-update <report-card> --preview-only
```

If the CLI previews correctly and the app does not, the defect is the missing
API endpoint, not the extraction logic — and that is a different two days of
work than "the logic is broken."

### A1. Ask must work out of the box

`teacher_readiness.py` already carries the instruments: `_chain_cold_ask()`
(line 338) and `_chain_observe_ask()` (line 247). Those are the acceptance
tests — cold start, nothing configured, no seeded data.

Definition of done: a fresh install on a machine that has never run LV answers
a question, or refuses **by name** with a message that says what to do. LV
already has `ask_not_configured_message()` and `ask_offline_message()` for the
refusal register, so the honest path exists; the work is making sure the cold
path reaches one of the three states and never a blank or a traceback.

### A2. Remove Home, Daily, Plan, Slack — Still I Rise only

Four entries, plus a new default view (recommend `students`, since the whole
product is student-centred and it is the screen a teacher would want on open),
plus a UI-contract version bump. Views' render handlers can stay in place
initially — deleting the nav entry is reversible in one line, deleting the
handler is not.

### A3. The model ruling, applied

Whichever way §0.3 is ruled, the fix is that `LOCAL_MODEL_PREFERENCE` and
`_TIER_MODEL_MAP` must stop disagreeing. Today one is decorative. A test should
pin whichever answer is chosen so the two cannot drift apart again — the same
shape as the safeguarding parity test landed this morning.

---

## 2. WORKSTREAM B — PROJECT ONE: one logic, Observe included

**The target architecture, which is mostly already built:**

```
INPUT ADAPTERS                ONE CORE                        OUTPUT
--------------                --------                        ------
report card / PDF        →                              →     lens update
teacher comment (Observe)→    extract_for_lens_update()  →     lens update
oral recording (Assess)  →    apply_extractions_to_lenses()→   lens update + grade
written exam (Assess)    →                              →     lens update + assessment doc
```

Everything in the middle column exists. The work is adapters on both ends.

### B1. Make the core input-agnostic

`extract_for_lens_update` currently takes document-shaped input. It needs to
accept plain text with a declared source kind (`report_card` / `observation` /
`oral_assessment` / `written_assessment`) so provenance survives — the lens must
record *where a field came from*, and a teacher must be able to see that a
strength came from her own Tuesday comment rather than from a PDF.

### B2. Route Observe through it

Teacher types or speaks a comment → same sentence-by-sentence routing, same
per-field `verified` / `needs_confirmation` contract, same safeguarding gate.
The dropdowns stay (you said leave them) but stop being the primary path.

### B3. The lens becomes directly editable

Your words: *"the teacher can freely see the lens and click in it and update
words they want."* This is the half that makes the automatic routing safe —
if the routing puts a sentence in the wrong field, the teacher fixes it in
two seconds instead of distrusting the whole feature.

**Non-negotiable, and it is already the system's law:** import is not truth.
The writer keeps `needs_confirmation` fields review-required. Automatic routing
must never silently become a confirmed fact.

---

## 3. WORKSTREAM C — PROJECT TWO: Assess

Same core (§2). Different adapters at both ends. This is the two-week item and
the honest reading is that the **input** adapters are the hard part, not the
lens logic.

### C1. Input — oral

Two candidate paths, and they are not equally hard:

- **(a) Record in-app** (reuse Observe's mic surface). Controls quality, one
  code path, no file handling. Risk is a child's voice at classroom distance.
- **(b) Import an existing recording.** No capture problem, but arbitrary
  formats, arbitrary quality, and no control over what arrives.

Recommend building **(a) first** and treating (b) as an import adapter onto the
same transcription step, because (a) is the one where we can influence quality
and it reuses a surface that already exists.

The stated constraint is a min and max duration. That is a real gate and should
refuse by name — too short, too quiet, too long — rather than transcribe
garbage and route it into a child's lens.

### C2. Input — written, possibly handwritten

PDF or phone photos. This is the highest-risk item in the whole plan. Printed
PDF text is solved (`extract_plain_text` already runs). **Handwriting is not**,
and no amount of prompt work makes a bad photo legible.

Recommendation: make the honest failure loud. If OCR confidence is low, the
system shows the teacher what it read and asks her to correct it before
anything touches the lens. A wrong grade from a misread word is worse than
asking.

### C3. Output — grade plus generated assessment

Your architecture, and it is the right one: **the lens holds everything; the
assessment document is produced from the lens.** That means Assess writes the
same fields as everything else, plus a grade, plus evidence in the right box —
and the document is a render, not a separate store. One place to be wrong,
one place to fix.

---

## 4. Sequencing against two weeks

```
Week 1   A0 demo-sheet pass (baseline)      <- first, no fixes mixed in
         A1 Ask cold-start
         A2 nav trim (SIR)
         A3 model ruling applied + pinned
         B1 core accepts a source kind
         B2 Observe routed through the core

Week 2   B3 editable lens
         C1 oral input (record-in-app first)
         C3 grade + assessment rendered from the lens
         C2 written/handwritten — LAST, and the most likely to be cut
```

**Stated plainly: C2 (handwriting) is the item I would expect to miss the two
weeks.** Everything else is wiring over things that exist. Handwriting recognition
of children's work from phone photos is a genuinely hard problem and it is the
one place where the plan depends on something we have not demonstrated once.

Better to say that now than to discover it on day thirteen.

---

## 5. RULINGS — taken 2026-09-03, by the operator

### R1 — Still I Rise ships from ONE codebase, split by a build-time profile

Not a fork. `config/profiles/{la-scuola,still-i-rise}.yaml` selects nav, features
and defaults; two installers come off one tree. The reason is on the record: a
hard fork guarantees drift, and drift is the exact defect repaired this morning
when three safeguarding detectors had stopped agreeing with each other.

**Discipline this ruling requires:** profile branching must live in config and at
the render boundary, never scattered through logic. A test must boot BOTH
profiles, or the second one rots unobserved.

### R2 — qwen3:8b is the documented default. Nemotron stays opt-in.

The 08-22 decision stands and becomes explicit rather than accidental. All recent
testing has been on qwen3:8b and the deadline work will run on what has been
tested. `LOCAL_MODEL_PREFERENCE` is reordered so it stops implying a
Lightning-first fallback that `default_model()` never performed, and a test pins
the documented intent so the two lists cannot silently disagree again.

Lightning-first is not cancelled — it is a separate change, after Assess ships,
with its own test run. Swapping the model underneath Observe and Assess mid-build
would make every quality regression ambiguous.

### R3 — Assess oral input: record in-app first, file import later

Reuse Observe's existing mic surface. One code path, and quality is controllable.
The duration/level gate refuses by name — too short, too quiet, too long — rather
than transcribing noise into a child's lens. File import is an adapter onto the
same transcription step afterwards.

### R4 — "Working definitively" means a teacher uses it UNATTENDED on real work

The highest bar, chosen deliberately. This is not a demo standard.

It converts three things from polish into requirements:

1. **Every failure path is named.** No traceback, no blank, no confident wrong
   answer. The refusal register already exists (`ask_not_configured_message`,
   `ask_offline_message`) and must cover every surface.
2. **Nothing is fabricated.** No seeded data, no invented grades, no placeholder
   student. If the system cannot tell, it says so.
3. **Lens edits are reversible.** Automatic routing is only safe if a teacher can
   correct it in two seconds. Reversibility is what makes §2.3 load-bearing
   rather than convenient.

**And it is worth naming what this bar actually is.** `traces.ndjson` on this
machine reads `operator: 0` across 100 records — no human turn has ever been
recorded through this system. A teacher working unattended on real student work
is the first genuine operator turn the product would ever have. That is the real
deliverable behind the two weeks, and every instrument that currently reads
CANNOT-TELL for want of a denominator starts working the day it happens.

---

## 6. Immediate next step

A0, first item: settle §0.2 with one command before anything is built.

```bash
PYTHONPATH=. python3 src/lv_cli.py lens-update <report-card> --preview-only
```

CLI previews and app does not  ->  missing API endpoint, two days.
CLI also fails                 ->  extraction logic, and a different plan.

---

## 7. CUSTOMER SYNC, 2026-09-03 — corrections to this plan

Source: Still I Rise x Mission Canvas bi-weekly sync, 2026-09-03, with **Olga
Giovani** (Still I Rise). Recap + full transcript. Read after §1-§6 were written;
these supersede the plan where they disagree.

### C1 — ASSESS DOES NOT GRADE. This plan was wrong.

§3.3 said "Output -- grade plus generated assessment", from the operator's
instruction that Assess should be "also placing a grade". The customer agreed
the opposite, in terms, and it was put to her as a direct question:

> **Mical:** "what would help you the most is just to have that kind of like
> **automatically not graded**, but like all of the problems to just kind of
> come out, okay?"
> **Olga:** "Correct."

**Assess produces a diagnostic, not a mark.** §3.3 is struck. Automatic grading
is removed from scope until an operator ruling reverses the customer agreement.

This matters beyond scope: an auto-grade is a decision about a child. Shipping
one the customer explicitly declined would be the product deciding rather than
informing -- the same line the Lens Engine analysis says never to cross
("never ship scoring: ranking/deciding flips every liability shield").

### C2 — the oral output has a named shape, and it is not free text

> "it could still tell me you know whether it's the **flow**, whether it's the
> **syntax** that is very problematic, whether it's the **grammar**, whether
> it's the **vocabulary** that needs further support."

Four dimensions -- fluency/flow, syntax, grammar, vocabulary -- each carrying
"is this the problem area / does this need support". That is the Assess output
contract, and it maps onto lens fields rather than onto a score.

### C3 — three minutes, not "three to four"

> "if it was like a 30 minute oral exam ... it's usually **maximum three
> minutes**"

The duration gate in §3.1 is 3 minutes maximum. The recap's "three- to
four-minute" is looser than what was actually said.

### C4 — HIDE, do not delete

The operator's instruction was "remove". The sync was explicit that this is
reversible and expected to be reversed:

> "I can take away home daily and plan ... it's just a little bit like hide,
> hide ... **I can always throw it back in later**"

§1.A2 already recommended deleting the nav entry and leaving the render
handlers. That is now the requirement, not a recommendation. The Daily view in
particular was described as valuable-but-unbuilt ("taking whatever information
from Slack ... and just bring it into their space"), so its code must survive.

### C5 — Whisper is the named transcription engine, and it already runs

> "the technology underneath it called **Whisper** ... works in many different
> languages"
> "I already have it installed and and working"

§3.1 said "transcription" generically. It is Whisper, multilingual, present.
Italian is explicitly in scope and explicitly weaker than English -- which is
the same asymmetry the safeguarding detector had. **The oral path needs the
Italian-vs-English parity discipline from day one**, not as a later fix.

### C6 — the out-of-box failure is REAL and was witnessed

Olga hit repeated errors installing, live on the call:

> "there are some errors popping up"
> "another error popped up but **I accidentally closed it**"

One of those errors has no record anywhere. That is §1.A1 (Ask/install must
work out of the box) with a named user and a witnessed failure, and it raises
its priority: it is the only item on this plan that has already cost a customer
her time.

The model download was correctly identified as normal first-run behaviour
(the "Quinn" model = qwen3:8b, ruling R2). Worth noting R2 is now
customer-visible: **the thing Olga is waiting on is the Qwen download.**

### C7 — a promise was made about images that the tree has not earned

> "You can even Read pictures. **I haven't tested on that.** If you want me to,
> I can."

§3.2 already named handwritten/photo input as the item most likely to miss two
weeks. It is now also the item a customer has been told "should work". Under R4
(unattended use) an untested "should work" on a child's assessment is the
sharpest risk on this plan.

### C8 — a durability promise now exists about local lenses

> "as you create these things, these lenses, it'd just be saved on your laptop
> and that **should never be overridden**"

Plus a Windows upgrade wrinkle told to the customer: "if you're on a Windows,
sometimes it likes it if you get rid of the old version first."

**This needs a test.** "Never overridden" is a data-durability guarantee about a
teacher's accumulated work, made verbally, currently pinned by nothing. An
install-over-install that wipes a lens store would be unrecoverable and would
end the pilot.

### C9 — confirmations, no change needed

- Observe routed through the document logic is confirmed as the intent, and was
  correctly described to the customer as **not yet built**: "I have an automated
  process that ... tries to guess where to put it. And so I'm going to try and
  make that work for the observer too ... it's not there yet." (= §2, PROJECT 1)
- Same logic for document and oral input: proposed and **approved by Olga**.
- Dropdowns stay: "I'll leave them in case ... the teacher wants to hard code
  these." (= §2.2)
- Editable lens after routing: "once it's there you can modify it and you can
  change it if you want." (= §2.3)
- Oral assessment lives **under Assess**.
- Two weeks, "maybe one".
- La Scuola and Still I Rise work separated (= R1).
