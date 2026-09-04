# SPEC — the lens field contract, four rungs

**Date:** 2026-09-03 · **Author:** PC-23 orchestration seat · **Operator:** Mical Neill
**Companion prompt:** `dev/PROMPT_LENS_FIELD_CONTRACT_4RUNG_2026-09-03.md`
**Plan context:** `dev/PLAN_SIR_SPLIT_AND_ONE_LOGIC_2026-09-03.md` (R1–R4, C1–C9) ·
`dev/UX_MATRIX_AND_ACTION_LIST_2026-09-03.md` (item 1 of 15)
**Prior art:** Palette wire contract V2.2 — `palette/sdk/agent_base.py`,
`palette/sdk/integrity_gate.py`

---

## 0. WILL IMPROVE WHAT · HOW MUCH · HOW VERIFIED

| | |
|---|---|
| **WHAT** | Lingua Viva has **no declared answer to "what is a lens field."** Four lists claim to be it and none is authoritative; a fifth namespace is emitted by the extractor and appears in none of them. This spec declares the field set once, makes the writer resolve every path against it, and makes drift fail a test. |
| **HOW MUCH** | Measured at Rung 1 as *field-path coverage*: of the paths the extractors can emit, how many does the writer implement, and how many resolve in the declared contract. Re-measured at Rung 4 as a delta with denominators. **No target is promised.** Every figure below was read from the tree on 2026-09-03 and will have moved — **read it again, never quote this file.** |
| **VERIFIED** | Every new guard is **observed failing** before it is trusted (Rung 3). A contract nobody has watched reject something is a data structure, not a contract. |

**The bar this serves (R4):** a teacher uses it unattended on real work. That is
why the contract **reports** rather than **blocks** — see §2.4.

---

## 1. The defect, measured

### 1.1 Four lists, no authority

```
src/lingua_viva/data_in_contracts.py:114   STUDENT_LENS_FIELDS       58
src/lingua_viva/docpipe/lens_extract.py:274 _LENS_FIELD_IDS          10
src/education/student_lens.py:63           SUPPORT_CATEGORY_IDS       9
src/education/student_lens.py:1192         UPDATABLE_PROFILE_FIELDS   5
```

Two of them disagree **in both directions**:

```
only in SUPPORT_CATEGORY_IDS : advanced_enrichment, personal_context
only in _LENS_FIELD_IDS      : academic_strengths, personal_strengths,
                               strategies_trialed
```

### 1.2 A whole namespace is emitted, undeclared, and unimplemented

Reproduced by running it, not by reading:

```
field_path  ethos_profile.traits.social_intelligence.evidence   status verified

  emitted by the extractor      lens_extract.py:225                     YES
  present in STUDENT_LENS_FIELDS                                        NO
  implemented by student_lens_writer.py                                 NO

  write_student_lens() ->  written_fields  []
                           review_required []
                           refusal: "'ethos_profile.traits.social_intelligence
                           .evidence' was extracted but this version cannot
                           write it to the lens"
```

It has looked healthy only because ethos fields normally arrive as
`needs_confirmation` and park in review. **A teacher who confirms one gets
nothing.** Before 2026-09-03 she got nothing *silently*.

### 1.3 This is the CEFR defect's parent

`cefr_snapshot.*` was emitted at confidence 0.95, shown in the import preview,
and dropped by the writer because no branch matched the path. Fixed 2026-09-03
(`d7e83aadd`). **The fix was one field. The cause was the missing contract**, and
the cause is still present: any extractor can still invent a path, and the only
thing that now notices is a refusal message added by hand.

### 1.4 It is the same shape as the three safeguarding detectors

Repaired the same week, in the same repository, one floor up: three
vocabularies for one concept, drifting apart, each green in its own tests. That
recurrence is the argument that this is structural and not incidental.

---

## 2. The contract

### 2.1 One module, one registry

**New:** `src/lingua_viva/lens_field_contract.py`

It declares every lens field path the system may write, and for each one:

| attribute | meaning |
|---|---|
| `path` | canonical field path, or a pattern with a named segment (`support_profile.categories.{category}.{slot}`) |
| `kind` | `scalar` · `cefr` · `support_profile` · `ethos_profile` |
| `writer` | the store operation that persists it — the capability must exist |
| `requires_sources` | must the field carry `supporting_chunk_ids` |
| `validator` | optional value check (CEFR level ∈ `VALID_CEFR_LEVELS`, tier ∈ 1–3) |
| `sensitivity` | `normal` · `restricted` — `trauma_flag` and safeguarding-adjacent fields are never auto-written |
| `status` | `writable` · `declared_not_implemented` · `read_only` |

`declared_not_implemented` is load-bearing and must exist from day one. It is
how `ethos_profile` is represented honestly on the first night: **declared, not
writable, refusing by name.** Deleting it from the registry to make a number
look better is a kill criterion (§6).

### 2.2 Resolution is the only way in

```python
resolve(field_path) -> FieldSpec | None
```

`student_lens_writer.write_student_lens()` resolves **every** field path through
this function before doing anything with it. There is no second route, no
`startswith` chain beside it, and no branch that writes a field the registry
does not describe. That is the whole mechanism: today the writer's `if/elif`
chain *is* the de-facto contract, and it is invisible, unenumerable and untested.

### 2.3 The four existing lists become derived or checked

- `STUDENT_LENS_FIELDS` — derive from the registry, or assert equality against it.
- `_LENS_FIELD_IDS`, `SUPPORT_CATEGORY_IDS` — one must derive from the other;
  the disagreement in §1.1 is resolved **by operator ruling recorded in the
  registry**, never by an agent picking a side silently.
- `UPDATABLE_PROFILE_FIELDS` — assert it is a subset of the registry's
  `writable` scalars.

**Where the lists disagree, the tree decides and the disagreement is recorded.**
Any category present in one list and absent from another is entered in the
registry with an explicit `status` and a one-line note saying which list it came
from. **No silent unification.**

### 2.4 Glass-box, not gatekeeping — the rule taken from Palette

`palette/sdk/integrity_gate.py` states it in its own docstring:

> *"Warnings are informational, not blocking — glass-box, not gatekeeping."*

and carries the invariant

> *"Non-success status has blockers (glass-box invariant)."*

Applied here, and this is a **design constraint, not a preference**:

- an unresolvable field path **refuses that field, by name, with a reason**;
- it **never voids the document**. A teacher who imports a report card with one
  drifted path keeps the other fourteen fields;
- a refusal is always **visible in the result payload**, never a log line;
- `written_fields`, `review_required` and `unresolved_questions` must together
  account for **every field that entered**. Nothing may be absent from all three.

That last line is the testable form of the glass-box invariant and is the single
most important assertion in this spec. It is what makes "silently dropped"
structurally impossible rather than currently-absent.

### 2.6 THE DEFINITIVE LENS STRUCTURE — declared here, or the contract is half-built

**Operator finding, 2026-09-03: "the lens is the linchpin... I don't see us choose
a data structure for the definitive lens structure."** Correct, and §2.1-§2.5
above did not close it. A registry of writable *paths* floating above an
undeclared *shape* is half a contract. The registry must declare the shape too.

What a lens actually is today, read from the store:

```
students          22 columns. SIX are JSON blobs with no declared internal shape:
                  cefr_snapshot · support_profile · strengths_profile
                  ethos_profile · sel_summary · rti_tier_history
observations      30 columns, APPEND-ONLY. The source of truth for derived fields
evidence_records  provenance: kind, target_type, target_id, source_ref, confidence
```

**`strengths_profile` appears in none of the four lists in §1.1.** Neither do
`sel_summary`, `background_notes`, or `avoid_pairing_with`. So the count of
undeclared namespaces is not one (`ethos_profile`) but at least four.

The registry therefore declares, per field, one more attribute — **`origin`**:

| origin | meaning | write rule |
|---|---|---|
| `authored` | a teacher or an import sets it directly | writable through its declared store operation |
| `derived` | computed from the append-only observation log | **NEVER written directly.** The writer appends an observation; the projection updates |
| `projection` | a read-only view over other fields | not writable at all; consumers may read it |

`cefr_snapshot` is `derived`. This is not a style preference — `set_initial_cefr`'s
docstring carries the law: *"cefr_snapshot must stay derived from the
append-only observation log so get_lens_as_of reconstruction holds — the same
law that keeps rti_current_tier out of update_profile()."* A contract that lets
an importer write `cefr_snapshot` directly would pass its own tests and silently
destroy point-in-time reconstruction, which is the property the whole evidence
model rests on.

`rti_current_tier` is `derived` for the same reason. `rti_tier_history` is its log.

**For each of the six JSON blobs the registry declares its internal shape** — the
keys a consumer may rely on. Undeclared keys inside a blob are the same defect as
undeclared paths outside it, one level down, and are exactly where the next CEFR
will hide.

**Rung 1 gains a measurement, B7:** every column of `students`, classified
`authored` / `derived` / `projection` / **`UNCLASSIFIED`**. `UNCLASSIFIED` is an
honest verdict and is expected to be non-zero on the first pass. Report the count;
do not guess a classification to drive it to zero. A wrong `authored` on a
derived field is worse than an honest `UNCLASSIFIED`.

**Kill gate K7:** if a field cannot be classified without an operator ruling —
in particular if a blob's internal shape is genuinely undecided rather than merely
unwritten — record it `UNCLASSIFIED`, leave it unwritable, and report it. Choosing
the shape of a student's record is an operator decision, not a builder's.

### 2.7 ALIGNMENT WITH THE 2026-08-10 LENS CONVERGENCE BRIEF

`mc-a0-mutant-20260828/dev/CONVERGENCE_BRIEF_LENS_SYSTEM_2026-08-10.md`, with the
operator's inline rulings. Read before building. Three things in it change this
spec, and one changes what the spec is FOR.

#### 2.7.1 What it changes about the stakes

The operator's own annotation:

> *"We would need the YAML structures defined somewhere where there is only ADD
> to fields, never overlap by design ... Look at the Lingua Viva JSON structure
> as a good example. That is just the student lens [subject]."*

**The LV student lens is the reference structure for Mission Canvas's entire lens
system.** What this contract declares is not an LV repair; it is the shape MC
inherits. The brief also records the cost of getting it wrong: three divergent
Claudia lenses already exist across palette / LV / MC.

#### 2.7.2 Composition is additive by construction — a design law

Operator ruling, verbatim:

> *"ONE LENS PER SLOT. ALWAYS ADDING FIELDS FOR STACKED LENSES, NEVER HAVE THE
> SAME FIELD SAY TWO THINGS EXCEPT FOR ID — WHICH WILL CONTAIN ALL IDS OF THE
> LENSES USED."*

The registry must therefore make same-field collision **structurally impossible**,
not merely resolved-by-precedence. Two lenses composing may only ever ADD fields.
The one field that carries plurality is the ID, which holds every constituent ID.

This spec's §2.1–§2.6 declares fields for **one** lens (the subject class). It
must not bake in anything that prevents the other three classes — **perspective**
(scopes access), **institution** (vocabulary), **jurisdiction** (egress) — from
composing additively later. Concretely: **`kind` in §2.1 is a STORAGE taxonomy,
not the governance taxonomy.** Do not conflate them. A field's governance class
is a separate attribute; the student lens is entirely `subject`.

#### 2.7.3 Evidence chain — already shipped, and stronger than this spec's rule

The brief names `docpipe.lens.v1` as the precedent MC should inherit wholesale:

> *"every value carries an evidence chain (source_ref/span_id/confidence/added_by)
> → merge_observation() appends, never replaces → _assert_grounded() (no value
> without evidence) → merge_events[] audit trail ... **This is GIR applied to
> identity**: the lens never claims anything about the person without a source."*

`§2.1 requires_sources` is a weaker restatement of `_assert_grounded()`. **Adopt
the stronger form**: for a subject-class field, a value without an evidence chain
is not a low-confidence value, it is not a value at all.

#### 2.7.4 THE UNRESOLVED ONE — there are two lens structures, and a bridge

Measured 2026-09-03:

```
src/lingua_viva/docpipe/lens.py     schema_version "docpipe.lens.v1"  (492 lines)
    profile: {field_id: {value, evidence: []}}   evidence-chained JSON
    PROFILE_FIELDS = 10   <- a FIFTH field list
    _assert_grounded() · merge_observation() appends · merge_events[] audit
    live in production at class_folder_ingest.py:157

src/education/student_lens.py       the SQLite store  (22 columns)
    six undeclared JSON blobs (§2.6)
    what the report-card path actually writes

bridged by  docpipe/lens.py::sync_to_student_lens_store()
```

The lists line up like this:

```
PROFILE_FIELDS (10)  ==  _LENS_FIELD_IDS (10)     identical — the docpipe world agrees with itself
SUPPORT_CATEGORY_IDS (9)                          overlaps the above by only 7 of 10
```

So the disagreement in §1.1 is not four arbitrary lists. It is **two coherent
worlds that disagree with each other across a bridge**: the docpipe/extraction
world (evidence-chained, 10 fields) and the store world (SQLite, 9 categories).

**Which is the definitive lens structure is an OPERATOR RULING, not a builder's
choice.** The convergence brief blesses the *shape* of `docpipe.lens.v1`; the
product *writes* to the store. Both are true today.

**Rung 1 gains B8:** what does `sync_to_student_lens_store()` actually carry
across, and what does it drop? Enumerate field by field. **Read the bridge before
declaring the contract** — a contract declared over one side of an undocumented
bridge is a contract over half the system.

**Kill gate K8:** if B8 shows the bridge drops or renames fields, **stop and
report**. Do not "fix" the bridge tonight. Reconciling two lens structures is the
operator ruling this spec exists to inform, and it is exactly the decision the
convergence brief reserved to him.

### 2.8 TWO FILTERS, NOT ONE — the contract serves OUT as well as IN

**Operator framing, 2026-09-03:** *"multi-input → lens → multi-output ... we just
need to wire them all into the same filter-to-lens-in and filter-from-lens-out
logic."*

§2.1–§2.7 specify the **IN** filter. That was half the job. The OUT filter is a
peer, not an appendix, and measurement says it is the **larger** surface:

```
IN   writers        student_lens_writer.write_student_lens()  — one choke point
                    (plus docpipe/lens.py's own path, §2.7.4)

OUT  readers        13 modules, FOUR entry points, no declared contract:
       get_lens · export_lens · export_lens_view · export_ethos_report

       content_differentiator.py   Prepare — differentiated materials
       parent_report.py            Summaries
       help_artifacts.py           help artifacts
       cohort_planning.py          grouping
       trend_analysis.py           Trends (admin)
       access_control.py           authorization  <- the PERSPECTIVE class, already real
       drive_sync.py               export
       governance.py / activity.py ethos reports
       pipeline_execute.py         the action loop
```

Four read entry points with no declared contract is the same defect as four
field lists — multiple doors into one structure, none of them authoritative.

#### 2.8.1 The OUT filter, stated

```python
requires(output_id) -> tuple[FieldRequirement, ...]
```

Every output **declares the lens fields it consumes**, resolved through the same
registry the writer uses. One registry, two directions.

Each requirement carries whether the field is `essential` (the output is not
honest without it) or `enriching` (it improves the output and its absence is
survivable).

#### 2.8.2 The honesty rule — glass-box, pointed outward

The IN filter's law is: *a field that enters is written, queued, or refused by
name — never silently dropped* (§2.4).

The OUT filter's law is its mirror, and it is the one that makes agentic output
trustworthy:

> **An output must be able to say what it did not have.**

A parent report generated from a lens with 3 of 10 fields populated must not
read as though it had 10. Concretely, every output carries:

- `fields_used` — resolved, with their evidence chains;
- `fields_missing` — declared `essential`, absent from this lens;
- and it **refuses to render** if an `essential` field is missing, naming it,
  rather than producing a confident document with a hole in it.

This is GIR applied to outputs. It is the same rule as the input side, and the
project already has the language for it: *a CANNOT-TELL must never share a
channel with a clean verdict.*

**Why it matters more here than on the input side:** a dropped input field costs
a teacher a re-import. A silently-thin output is a document about a child that
reads as complete and is not — and under R4 it is going out unattended.

#### 2.8.3 What this does NOT authorize tonight

Do not convert 13 modules. **Declare the OUT filter and prove it on ONE
consumer** (Rung 3, §6.2). The sweep of the rest is Rung 4's enumeration and, if
it is large, its own build. The operator's read holds — *"we have the verbs"* —
the verbs exist and are unwired; this is wiring, not authoring. But wiring 13
consumers in one night is how a night is lost.

**Rung 1 gains B9:** enumerate every OUT consumer and which read entry point it
uses, and for each, which lens fields it actually reads. Read the code; do not
infer from the function name. That table is the OUT filter's denominator and
nothing can be reported as a fraction without it.

### 2.5 What the contract is NOT

- Not a schema migration. No stored lens changes shape.
- Not a gate on imports. §2.4.
- Not an envelope. Palette's 7-field envelope is an agent-to-agent message
  shape; lens fields are a namespace. Copying the envelope literally would be
  cargo-culting the prior art rather than using it.
- Not a rename. Existing field paths keep their names; drift is recorded, not
  "cleaned up".

---

## 3. RUNG 0 — gate, before any rung starts

1. `git status --porcelain` in `~/lv-work`. Anything untracked or modified is
   committed to its own branch, **path-scoped**. `git add -A` is forbidden.
2. Record `git rev-parse HEAD` and the current branch. Re-check HEAD before
   every commit; if it moved, stop and report.
3. Confirm `origin/main` and note whether the working branch is behind.
4. **If the tree cannot be backed, the run does not start.**

Base for this work: `fix/cefr-write-and-unknown-field-refusal-2026-09-03`
(`d7e83aadd`) — it carries the refusal rule this contract formalises. If it has
merged to `main` by run time, branch from `main` instead and say so.

**Exit gate:** clean tree, HEAD recorded, base named.

---

## 4. RUNG 1 — the honest baseline

Frozen and committed **before the first line of implementation.** A
before-number reconstructed afterwards is a proxy.

Measure and record, each with its command:

| # | Measurement |
|---|---|
| B1 | The four list lengths and their pairwise differences (§1.1), read from the tree |
| B2 | **Emittable field paths**: every distinct `field_path` any extractor in `src/` can produce. Enumerate from source, not from a run |
| B3 | **Writer-implemented paths**: every path `write_student_lens` has a branch for |
| B4 | `B2 − B3` — emitted but unwritable. §1.2 says this is at least the ethos namespace |
| B5 | End-to-end report-card import on the Abigail fixture: `written_fields`, `review_required`, `unresolved_questions`, and the resulting lens |
| B6 | Bounded test baseline, full failure list preserved (see §7 for the command) |
| B7 | Every `students` column classified `authored`/`derived`/`projection`/`UNCLASSIFIED` (§2.6) |
| B8 | What `sync_to_student_lens_store()` carries and what it drops, field by field (§2.7.4) |
| B9 | Every OUT consumer, its read entry point, and the lens fields it actually reads (§2.8.3) |

**Do not fix anything in Rung 1.** Mixing fixes into the baseline destroys the
comparison. Every failure found here is written down and left alone.

**Exit gate:** all six recorded in
`dev/BASELINE_LENS_FIELD_CONTRACT_2026-09-03.md`, committed.

---

## 5. RUNG 2 — build the contract, and take the report-card UX to 100%

### 5.1 Build

1. `src/lingua_viva/lens_field_contract.py` per §2.1–§2.3.
2. `write_student_lens()` resolves every path through `resolve()`. The existing
   `if/elif` chain becomes dispatch **on the resolved spec's `kind`**, not on
   string prefixes.
3. The §2.4 accounting invariant is enforced in code: every incoming field
   lands in exactly one of `written_fields` / `review_required` /
   `unresolved_questions`.
4. `ethos_profile.*` is entered as `declared_not_implemented` and refuses by
   name. **Do not implement ethos writes tonight** — that is a separate build
   with its own review semantics, and pretending otherwise is how scope eats a
   night.

### 5.2 Iterate the report-card UX until it is actually finished

Target UX: **U3, upload a report card → lens updates** (`UX_MATRIX §2`).

Loop until all of the following hold on the Abigail fixture, end to end through
HTTP on a sandboxed state home:

- every field in the import preview is accounted for in the apply result;
- `cefr_snapshot` shows reading A2 / writing A1 / speaking A1 / listening A2;
- every refusal names its field and its reason;
- no field is absent from all three result lists;
- re-running the same import twice does not double-write or corrupt the lens.

**"Iterate until it works" means: run it, read the output, fix, run again.** Not
"the tests pass". The acceptance is the lens contents after an HTTP round trip.

**Kill gate K1:** if making the report-card path pass requires *widening* the
contract to accept a path no store operation can persist, **stop.** That is the
contract being bent to fit the bug. Report and leave it.

**Exit gate:** the loop above is green, and the diff touches only the contract
module, the writer, the four lists, and tests.

---

## 6. RUNG 3 — a second UX, and every guard observed failing

### 6.1 Observe every new guard fail, on purpose

For each guard introduced in Rung 2, **plant the failure and watch it fire**:

| Sabotage | Must produce |
|---|---|
| Remove a field from the registry that the extractor still emits | a named refusal, not silence |
| Point a registry entry at a store operation that does not exist | a startup or resolve-time error, not a runtime `AttributeError` at write |
| Make a validator accept anything | the CEFR "Z9" test goes red |
| Bypass `resolve()` in the writer for one path | the §2.4 accounting test goes red |
| Delete `declared_not_implemented` on ethos | the ethos refusal test goes red |

An instrument nobody has watched fail is a claim, not a result. Restore each
sabotage **by inverse edit**, never `git checkout` on a file carrying your own
work.

### 6.2 The second UX — one write path AND one read path

The operator's priority is **Observe (U4)**, and it is the second write path.
Wire it through the contract: a teacher's comment is parsed sentence by
sentence, each candidate field resolved through `resolve()`, same refusal
semantics, same accounting invariant.

**AND** prove one **read** consumer against the contract — `Summaries` (U10) or
`Prepare` (U9). A contract proven only on writes is half-proven: the whole point
of `lens → output` is that consumers read a declared shape. Pick whichever
consumer reads lens fields most directly; name the choice in the report.

**Kill gate K2:** if Observe cannot be routed without changing the *meaning* of
an existing field (re-purposing a support-profile slot, say), **stop and report**.
Wiring Observe by redefining a field a teacher already has data in is worse than
not wiring it.

**Exit gate:** Observe writes through the contract on a real comment; one read
consumer resolves its fields through the contract; every sabotage in §6.1
observed failing and restored.

---

## 7. RUNG 4 — full wiring sweep, reconcile, report

1. **Sweep every remaining call site.** Find every place in `src/` that writes a
   lens field or names a field path, and route it through `resolve()`. Enumerate
   them first, then convert; report the count both ways.
2. **Re-measure B1–B6.** Report as a delta with denominators.
3. **Compare the failure set to Rung 1, test-id for test-id.** New failures are
   reported as new failures — never explained away, never absorbed.
4. Run the repo's own gates and report each honestly:
   ```
   python -m pytest tests/ -q -p no:randomly -rf \
     -k "lens or extract or writer or docpipe or observation or student or contract" \
     --ignore=tests/test_daily_file.py --ignore=tests/test_document_intelligence.py
   python scripts/check_route_reachability.py
   python scripts/check_app_reality.py
   ```
   **`scripts/check_ui_contract.py` will FAIL on this machine and the failure is
   false** — it hashes raw bytes and Windows CRLF checkouts differ from the
   LF-locked digest for a byte-identical file (locked `990e4239c08dd1b6`,
   LF-normalised `990e4239c08dd1b6`, CRLF on disk `b86e20a78fab84ac`).
   **DO NOT run `--bump`.** It would lock the CRLF digest and turn a false local
   failure into a real one on PC-0 and in CI.
5. Write `dev/REPORT_LENS_FIELD_CONTRACT_2026-09-03.md`: what moved, what did
   not, every kill gate evaluated, every CANNOT-TELL named.

**Exit gate:** report written, branch pushed, **nothing merged to `main`.**

---

## 8. Fences — in force all night, no exceptions

- **No push to `main`. No merge to `main`. No tag. No release.**
  LV's `auto-release.yml` fires on push to `main` with a paths filter that
  includes **`src/**`** — so a push to main *is* a desktop release. This work is
  entirely inside `src/`. The operator cuts releases, nobody else.
- **Branch pushes are fine** and expected.
- **`git add -A` is forbidden.** Path-scoped adds only.
- **No bare `git stash`. No `git checkout <file>` on a file carrying your own
  uncommitted work** — revert by inverse edit.
- **Write file content with a file-writing tool, never a bash heredoc** —
  heredocs mangle escape sequences on this box and have broken a source file
  before.
- **Read exit codes bare, never through a pipe.** `cmd | tail; echo $?` reports
  `tail`'s status and has produced a false green here.
- **Never point a test at the operator's real state home.** `LV_CONFIG_HOME`
  redirects the lens store; `LV_STATE_HOME` does **not** — they are two
  independent seams (50 call sites vs 30) despite `config.py:215` claiming one
  canonical one. Set **both**, and verify the sandbox DB was actually created
  before trusting isolation.
- **No student data invented, seeded, or committed.** Fixtures use fictional
  names and live only in `tests/`, which is not bundled into the installer.
- **`python3` is not on PATH in this box's Git Bash — use `python`.**

---

## 9. Kill criteria — stop and report, do not work around

- **K1** — the contract has to be widened to accept a path nothing can persist (§5.2).
- **K2** — Observe cannot be wired without redefining an existing field's meaning (§6.2).
- **K3** — the §2.4 accounting invariant cannot be satisfied without dropping a
  field from the accounting. **The invariant is the deliverable**; weakening it to
  make the run finish is the one outcome worse than not finishing.
- **K4** — `declared_not_implemented` is deleted, or ethos is quietly made
  "writable" without a store operation behind it, to reduce the refusal count.
- **K5** — HEAD moves between writes (another window on this shared tree).
- **K6** — any measurement requires the operator's real `~/.lingua-viva`.
- **K7** — a field's origin or a blob's shape cannot be classified without an operator ruling (§2.6). Record `UNCLASSIFIED`, leave it unwritable, report it.
- **K8** — the docpipe/store bridge drops or renames fields (§2.7.4). Stop and report. Reconciling the two lens structures is the operator's ruling, not tonight's build.

---

## 10. What would make this run wrong

- It starts a rung before the previous rung's exit gate.
- It reports a figure quoted from **this document** instead of read from the tree.
  Every number in §1 was true on 2026-09-03 and is expected to have moved.
- It ships a guard nobody watched fail.
- It renders a `CANNOT-TELL` as clean, or omits an instrument that could not run.
- It "resolves" a list disagreement by picking a side silently instead of
  recording both (§2.3).
- It implements ethos writes because refusing them looks untidy.
- It makes the contract a hard gate, so one drifted field costs a teacher her
  whole import (§2.4).
- It pushes to `main`, merges, tags, or releases.
- It touches `static/index.html` and then runs `check_ui_contract.py --bump`.
