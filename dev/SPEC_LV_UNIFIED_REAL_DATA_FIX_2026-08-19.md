# SPEC_LV_UNIFIED_REAL_DATA_FIX — 2026-08-19

**Status: DRAFT — Phase 0 is buildable immediately; STEPs 3, 5, 9 and the preview default
carry operator rulings (§8). Build order in this spec is BINDING and deliberately differs
from filed priority order.**

**Inputs (read both before building):**
- `dev/FINDINGS_REAL_DATA_PIPELINE_AUDIT_2026-08-19.md` — C1–C5, L1–L10, six failure classes
- `~/Downloads/NEXT_STEPS_REAL_DATA_PIPELINE_2026-08-19.md` — MC-wave sequencing guidance
  (local file, not committed; its ordering and [MC] precedents are adopted wholesale here)

**Privacy:** this spec contains no student names, no colleague names, no school name.
The real test files live at `~/Downloads/LV-lenses-test/` and
`~/Downloads/Lizard BrainWizard Brain - Instinct vs. Reason.pdf` — they are NEVER
committed, and neither is anything derived from them that contains a real name
(including the labelled corpus, §2B). All committed fixtures use synthetic names.

---

## 1. Root diagnosis and why the order is what it is

> The pipeline destroys the structure that contains the answer, then tries to recover the
> answer by guessing at text.

The files carry ground truth in their *layout*: the class list encodes teacher→class→roster
positionally (row 2 of each grade sheet names the teachers; the roster sits below); the 3V
support file has literal `Student` and `class` column headers; the K-5 file puts categories
in named columns. Extraction flattens all of it to one span, then a capitalized-bigram
regex guesses at prose. That one root produces both 637 false positives on the class list
AND 0 detections on the most relevant file.

**Therefore L9 (filed P2) builds FIRST.** It is the direct cause of L3.2, L4, and L5 —
three P0s sit on one P2. Fixing in filed order means building workarounds for a problem
this spec removes in STEP 1.

The content pipeline (C-findings) shares two of the six failure classes — silent
degradation and ungoverned model pick — so its fixes ride the same wave: STEP 8 fixes
C1's cause, STEP 10 fixes C2/C3's dishonesty, STEPs 11–12 close C4/C5.

---

## 2. Phase 0 — mandatory before ANY fix touches real data

### 2A. Close the one-way door: preview/dry-run import (from L2)

`BULK_IMPORT_CONFIRMATION_THRESHOLD = 2` (web.py:2378) auto-creates every detection above
2 and enqueues per-student Drive lens sync. One misfire during this build creates hundreds
of lenses in a real teacher's Drive. Drive writes are the least reversible thing this
system does.

**Build:** a preview mode for `/api/students/ingest` — extract, detect, report the full
would-be result (per-student: name, confidence, source spans, class attribution when
STEP 4 lands), create NOTHING, sync NOTHING. Preview is the default entry from the UI;
creation requires an explicit confirm step that displays the preview first.

- Operator ruling §8-1 decides whether always-preview or threshold-preview ships as the
  final default. **Until that ruling, this build behaves as ALWAYS-preview** (the
  threshold is what produced the 940-lens scenario).
- UI change → UI contract bump + route-reachability classification for any new route
  (per `ROOT_CAUSE_BUILT_NOT_MOUNTED` §6 checklist).
- **Class lock (test):** preview never writes — no student-store write, no Drive enqueue,
  no vault mutation beyond the already-safe write-before-process. String-locked assertion
  on the store row count before/after preview.
- **Gate:** no subsequent STEP may run against the real files until 2A is merged and its
  lock test is green.

### 2B. Build the measurement instrument: labelled corpus + scorer + sealed holdout

There is currently no way to tell whether a fix worked — "students detected" has no
denominator. Build the corpus BEFORE fixes:

1. **Hand-label the 5 real files** (locally, never committed): per file, the exact
   expected student set (names as they appear in that file); for the class list, the
   teacher→class→roster mapping including the target teacher's row-2 cell ⇒ her class
   column ⇒ the 20 names in HER class column below it (CORRECTED 08-19 eve by human
   hand-count: a grade sheet holds TWO class columns side by side, 41 students total;
   the audit's "~39" wrongly counted both columns — her column alone is ground truth);
   for curriculum mapping and 6-day calendar, the
   **empty set** (the most valuable rows — the false-positive traps); for 3V, the 6
   students, which 3 are hers, and the category→column mapping; known cross-file identity
   collisions (same child, multiple spellings).
2. **Scorer:** per file, report **precision, recall, and false-positive count** — never
   "students detected" alone. A single number that goes up when you detect more is the
   metric that produced 637.
3. **Freeze + hash** the corpus (record the hash in the build report). **Seal a holdout**
   — one file or a held-back sheet — that NO fix is tuned against; it is opened exactly
   once, at the end (§6).
4. **Committed mirror:** a synthetic-name fixture set replicating the four structural
   shapes (grade-sheet class list with teacher row + class column-pairs; single-sheet
   support file with Student/class columns and abbreviated names; per-class-sheet K-5
   file with category columns incl. a Medical column; a zero-student curriculum/calendar
   pair with non-English capitalized bigrams). CI runs the scorer against the synthetic
   corpus; the real corpus runs locally only.

**Gate:** STEPs 1–9 each verify against this scorer. No corpus, no fix.

---

## 3. Lens-pipeline fix sequence (STEPs 1–9, order binding)

### STEP 1 — Preserve structure at extraction (L9)
Rows, columns, sheet names, header rows survive into spans. Minimum: one span per row
with column identity retained. Applies to the generic xlsx path
(`docpipe/extract.py`).
- **Unlocks:** per-row grounding (L3.2), class membership (L4), column→field routing
  (L5), positional evidence for detection (L1).
- **Verify:** the 3V-shaped fixture yields 6 spans, not 1; real 3V file locally likewise.

### STEP 2 — Detect from structure, not text shape (L1, L3)
Replace "capitalized bigram not in an English blocklist" with positional evidence: a
value in a column whose header matches a student-name concept, on a sheet that is a
class. The bigram regex survives ONLY as a fallback for unstructured documents, and its
output is a lower-confidence class.
- Non-English titles stop being students because a story title is not in a `Student`
  column — **not** via blocklist additions. Say where to go, not where not to go.
- Abbreviated names ("First L-W" style) are detected because they sit in the Student
  column — the structural path has no full-bigram requirement.
- **Verify (scorer):** curriculum + calendar fixtures → 0 detections; 3V fixture → 6.

### STEP 3 — Confidence discriminates, or the gate is deleted (L1) — ruling §8-3 adjacent
`VERBATIM_STUDENT_CONFIDENCE = 0.99` flat makes `INGEST_CONFIDENCE_THRESHOLD = 0.7` dead
code that reports as a working gate. Two acceptable outcomes:
- Derive confidence from evidence class (structural position > header match > regex
  fallback) and **prove on the corpus that it discriminates** — high-confidence
  detections must be right more often than low-confidence ones; or
- Delete the threshold and stop implying a check that does not happen.
- **Unacceptable:** a new hardcoded number and a gate that still cannot fail. [MC: never
  gate on a confidence signal until measured predictive — MC found theirs anti-predictive.]

### STEP 4 — Class membership and "my class" (L4) — the actual product requirement
With structure preserved, read the class list's teacher row: teacher → class → roster.
Detected students carry `class`, `grade`, `teacher_attribution`. Import gains a scope
option ("only my class"). Teachers stop being ingested as students — position says row 2
is a teacher row. Wire attribution into the existing `teacher_roster` table.
- **Verify (scorer):** class-list fixture → roster attributed to the correct teacher,
  teachers not in the student set. The teacher wants her 20, not 41 and not 400 —
  a grade sheet is two classes, and attribution must split at the class COLUMN.

### STEP 5 — Identity resolution (L8) — ruling §8-3
`student_id = slug(display_name)` makes identity BE the spelling. Needed: canonical id +
set of observed surface forms, resolution scoped to a class roster (matching within ~20
names, not globally), and an **unresolved queue for a human** rather than a silent guess
(reuse the existing unattributed-review queue pattern, `/api/students/ingest/unattributed`).
- Default until ruling §8-3 says otherwise: **always queue, never auto-merge** —
  confidence currently measures nothing (STEP 3).
- [MC precedent: `same_person_as` relation, not a new entity type — read MC's lens
  field-allocation work before designing.]
- **Verify:** abbreviated support-file fixture names resolve to class-list fixture
  students or land in the queue; zero silent duplicate lenses.

### STEP 6 — Give enrichment a veto (L7)
`_model_enrich_students` is additive-only; a pipeline that can only add cannot converge
on truth. Enrichment may propose *removal*, gated by review. Note: urgency drops after
STEP 2 (the false positives largely stop existing) — which is why this is STEP 6, not 2.

### STEP 7 — ONE canonical normalizer + fix the misreport (L6)
Extract a single model-name normalizer; `model_gate.is_provably_local_model` and
config's installed-match both call it. **Do not patch `:latest` handling on one side** —
that leaves two normalizers that agree today.
- **Class-lock test:** fails if a second normalization path appears (grep-level or
  import-level assertion).
- Fix the misreport: a privacy refusal (`none:local_only`) must never surface as
  `model_enrichment_discarded: invalid JSON after retry`. A system must report the true
  reason for its own failure — that misreport is how L6 stayed invisible.

### STEP 8 — Model governance (L6, L10, C1)
- A local-model detector must **never** return a cloud model. Delete the
  `ollama/{CLOUD_FALLBACK}` last resort from `detect_model()` (config.py:468); fail
  closed to "no local model available" and say so. **Class-lock test:** detector output
  never matches `:cloud`.
- `LocalModelClient.complete` (docpipe/model.py) stops hard-coding
  `model=config.detect_model()`; `LV_REASON_MODEL` override works everywhere. Log which
  model was actually used, on every call.
- **Thinking models: send `"think": false`** in the ollama request (MC-proven fix for
  empty visible content), and treat empty-content-with-no-error as a failure signal, not
  a success. Nemotron declares `thinking` in its capabilities — required parameter, not
  tuning.
- Model auto-pick accounts for VRAM residency [MC-measured: ~4s prefill + 29ms/token
  CPU-offloaded vs ~100ms + 0.1ms/token resident — residency matters more than which
  model]. Minimum: prefer a resident-fit model over a larger offloaded one.
- **Verify:** on this machine, a single tier call with the auto-picked model returns
  non-empty visible content within budget, or an honest failure — never empty-silent.

### STEP 9 — Medical category (L5) — GATED on ruling §8-2
The K-5 shape has a Medical-needs column; `PROFILE_FIELDS` has no medical category and
allergies are not `physical_sensory_needs`. Governing test: does it own information no
existing category can own? Yes. **But medical data may warrant different retention/
disclosure handling — that is an operator ruling, not an implementation detail. Do not
build STEP 9 until §8-2 is ruled.**

---

## 4. Content-pipeline fix sequence (STEPs 10–12, after STEP 8)

### STEP 10 — Generation honesty (C2, C3)
- `_generate_tier_material` fallback to `_deterministic_material_fields` becomes LOUD:
  the returned material, the API response, and the UI carry a generation-status signal
  (mirror the existing `sync_status` pattern from the Drive leg). The teacher must be
  able to see "AI generation did not run; this is template text."
- The foundational-tier deterministic fallback must never render blank
  `instructions_for_student` / blank `exercise_body` / `[]` scaffolding. The weakest
  students' tier degrading to *nothing* is the worst possible failure shape.
- **Class lock:** no template-fallback output without its status signal (same class as
  SPEC_LV_VOICE_SCOPE_NARROWED §1: no answer surface without its grounding verdict).

### STEP 11 — Metadata detection from structure (C4)
`parse_lesson_metadata` picks the letterhead line as title and misses grade. Same root
as the lens side: prefer document structure (title line position, "Author:"/grade
patterns) over first-plausible-line. Verify against the real PDF locally: title = the
actual document title, grade detected, not the letterhead.

### STEP 12 — Excerpt budget revisit (C5) — only after STEP 8 lands
`_SOURCE_EXCERPT_CHARS = 1500` loses ~40% of even a 2-page doc. A faster resident model
(STEP 8) buys headroom. Re-derive the budget from measured tokens/sec of the governed
pick; keep a documented cap. Not a bug fix — a trade-off revision, lowest priority.

---

## 5. Prohibitions (verbatim from NEXT_STEPS, binding)

- Do not hand the fix agent sixteen findings — six classes, in this order.
- Do not fix in filed priority order — L9 (P2) unlocks three P0s.
- Do not extend the blocklist — it is an infinite list of things that are not students.
- Do not tune to the five files — the holdout stays sealed until §6.
- Do not fix the `:latest` mismatch by patching one side — one normalizer.
- Do not add a new hardcoded confidence — discriminate on the corpus or delete the gate.
- Do not let any fix run against real data before §2A lands.
- Do not commit real names — corpus and real files stay local; fixtures are synthetic.
- Do not touch the uncommitted .deb WIP files in the working tree.

---

## 6. Binding acceptance gates

On the frozen corpus, per file (scorer output, not eyeballs):

| file (shape) | expected | the number that matters |
|---|---|---|
| Curriculum mapping | **0** | false positives — must be 0 |
| 6-day calendar | **0** | false positives — must be 0 |
| 3V support | **6** | recall — currently 0 |
| Class list (target teacher's class column) | **20, attributed to her class** (grade sheet total = 41 across two class columns — both-columns = FAIL) | precision AND attribution |
| K-5 support | ~76 | precision (no roles as students) |

**End-to-end assertion (the product requirement, one check):** import all five real
files → 20 lenses for the target teacher's class (support-file matches ENRICH existing
lenses — the count stays 20, never grows), enriched from the support files,
**zero** lenses from the curriculum map or the calendar.

**Content side:** the real IB PDF → 3 genuinely file-grounded tiers within the timeout
budget with an honest generation-status, on the auto-picked governed model.

**Then the holdout, opened exactly once**, to say whether it generalised or was fitted.

---

## 7. Standing build constraints

- `MC_AGENT=1` on every run.
- Preview UI + any new routes: UI contract bump, route-reachability classification
  (`ROOT_CAUSE_BUILT_NOT_MOUNTED` §6).
- Mandatory Claudia-lens UX audit before push (standing practice per 08-19 ship).
- PUSH = downloadable on the live site NOW — AGENTS.md 7-step checklist, nothing less.
- Hunk-isolated commits; the .deb WIP uncommitted files are untouchable.
- Drive model changed 2026-08-19 (`SPEC_LV_DRIVE_PER_FILE_ACCESS_2026-08-19.md`):
  scope is now `drive.file` (per-file access, never widen). Credentials are DONE
  (GitHub secrets set 08-19). Drive-LINK ingest of pre-existing school files is
  permanently out under this scope — it degrades honestly to direct upload, which is
  this spec's ingest path anyway. Local-file ingest covers every STEP.

---

## 8. Operator rulings needed (with recommended defaults)

1. **Preview-before-create:** always preview, or only above a threshold?
   *Recommended: always — the threshold is what produced this.* Build behaves as
   always-preview until ruled.
2. **Medical category:** add an eleventh `PROFILE_FIELD`? (lens.py:14 has 10 today.)
   Different retention/disclosure handling? *Recommended: add it; handling decision is
   genuinely the operator's.* STEP 9 is gated on this.
3. **Identity resolution:** auto-merge above a confidence, or always queue for the
   teacher? *Recommended: always queue until STEP 3 proves confidence discriminates.*
   Build defaults to queue-only.
4. **Historical files / school-year dimension:** the K-5 file is last year; current 3V
   students' history is on the "2V" sheet. Does ingest carry a school-year dimension?
   *Recommended: out of scope for this build; record source-file year in provenance so
   the dimension can be added later without re-ingest.*

---

## 9. Stop points

The build is cleanly stoppable after: Phase 0 (safety + instrument, immediately
valuable alone) → STEP 2 (false positives dead) → STEP 4 (product requirement met for
creation) → STEP 8 (both pipelines model-governed) → full. Each stop point requires the
scorer run + report evidence for everything landed so far.
