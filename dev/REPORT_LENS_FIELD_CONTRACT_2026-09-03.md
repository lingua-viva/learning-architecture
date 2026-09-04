# REPORT — lens field contract build, 2026-09-03 night window

**Seat:** PC-23 · **Operator:** Mical Neill · **Spec:** `dev/SPEC_LENS_FIELD_CONTRACT_2026-09-03.md`
**Outcome in one line:** Rung 0 and Rung 1 complete and committed; **kill gate K8
fired at B8** and the run stopped before Rung 2, as the spec and the briefing
said it should. Nothing was built. One operator ruling clears it.

---

## 1. State at close

```
branch      fix/cefr-write-and-unknown-field-refusal-2026-09-03
base        a08f1c6  (the spec/prompt/start-here commits; d7e83aadd in ancestry)
committed   aeb33bb  baseline(lens): Rung 1 honest baseline B1-B9, nothing fixed; K8 fires
            + this report (the commit after aeb33bb)
pushed      the branch, after this report — see the closing message
main        untouched. No merge, no tag, no release. origin/main still 7037037.
source      NO source file changed. Diff vs a08f1c6 is dev/BASELINE_*.md + dev/REPORT_*.md only.
scratch/    six probe/driver files left UNTRACKED on purpose (not gitignored):
            b5_roundtrip.py b5_analyze.py b3_b4_probe.py b2_b3_count.py roster_abigail.csv baseline_20260903.txt
sandbox     C:\Users\spide\AppData\Local\Temp\claude\lv_rung1  (server killed, artifacts kept)
real store  ~/.lingua-viva/runtime/student_lenses.db read ONCE read-only; mtime 14:24:03 before and after;
            still 2 rows (Abigail Chang, Marco Rossi — the fixture students the briefing names), 0 observations
```

## 2. The delta

There is no after. Rung 2 did not start. The before is
`dev/BASELINE_LENS_FIELD_CONTRACT_2026-09-03.md`, summarised with denominators:

| | before (tree at a08f1c6) |
|---|---|
| B1 lists | 5 lists: 58 / 9 / 10 / 5 / 10; disagreements exactly as spec §1.1 |
| B2 emittable paths | **72** |
| B3 written when well-formed | **55 / 72** (writer accepts 61; 6 accepted-but-never-emitted) |
| B4 emitted-but-unwritten | **17 / 72** — 1 silently dropped, 14 refused by name, 1 unnamed by design, 1 review by design |
| B5 report card over HTTP | 51 fields → 8 written / 5 review / 38 unresolved (**= 51, accounted by count**); CEFR correct; refusals **not in the HTTP response**; re-import **double-writes** |
| B6 bounded suite | 790 passed / 13 failed, all 13 PC-23 platform artifacts |
| B7 columns | 22 classified, UNCLASSIFIED 0, 1 flagged for ruling |
| B8 bridge | carries 10/10 docpipe fields; **renames 1, drops span_id + numeric confidence** |
| B9 consumers | 13 modules, 4 entry points (+ as-of), fields-read table |

## 3. Every kill gate

| gate | fired? | evidence |
|---|---|---|
| K1 widen contract to fit the bug | not reached | Rung 2 not started |
| K2 Observe needs a field redefined | not reached | Rung 3 not started |
| K3 accounting invariant unsatisfiable | not reached — **but note** the baseline shows it is *currently violated* by one live shape (B4a: `strategies_trialed.evidence` absent from all three). Rung 2 closes that; it is the contract's job, not a reason to weaken it | baseline B4a |
| K4 `declared_not_implemented` deleted | n/a | nothing built |
| K5 HEAD moved between writes | **no** | `a08f1c6` re-checked before the baseline commit; still equal |
| K6 measurement needed the real `~/.lingua-viva` | **no** | sandbox held (`$SB/runtime/student_lenses.db` present); real store proven untouched by mtime + row count |
| K7 origin/shape unclassifiable | **no** — UNCLASSIFIED 0, with one honest flag: `support_profile` is *authored* by the store's laws (no as-of reconstruction) while import appends to it with no observation behind the entry. Recorded for the operator, not decided | baseline B7 |
| **K8 bridge drops or renames** | **YES — FIRED. Success: the gate did its job.** | baseline B8 |

**Why K8 fired, precisely.** `docpipe/lens.py::_bridge_one_field` (`:372-446`):
`strategies_trialed` has no category in docpipe.lens.v1; the bridge hardcodes
it into `support_profile.categories.learning_and_cognition` and picks a bucket
from an `outcome` key. Per evidence item it forwards `source_id`, `obs_id`,
`added_by` and drops `span_id`, the float `confidence` (coarsened to
`imported_verified`/`teacher_confirmed`), `added_at`, `path`. Nine store
namespaces have no docpipe counterpart at all. Two coherent worlds, one lossy
one-way bridge, live in production on the roster path
(`routers/students.py:141`) and the class-folder path (`class_folder_ingest.py:157`).

## 4. Every sabotage

None run. Rung 3 was not reached. No guard was introduced, so there was nothing
to watch fail. (The baseline *did* watch the existing writer fail — B4a is five
inputs that produce silence or an uncaught exception today.)

## 5. What I got wrong

The spec and prompt were written by this seat earlier today. The tree corrected them:

1. **"Four lists."** Five. `docpipe/lens.py::PROFILE_FIELDS` is the fifth and
   is the one that makes the disagreement legible (it equals `_LENS_FIELD_IDS`,
   so the split is docpipe-world vs store-world, not four random lists).
   §2.7.4 half-knew this; §1.1 still says four.
2. **"Silent drop closed 2026-09-03 by the refusal rule."** Closed at the *end
   of the loop*. Not closed inside the `support_profile.categories.` branch,
   which has its own bare `continue` (`student_lens_writer.py:174-199`). A path
   the extractor is explicitly told to emit — `strategies_trialed` — still
   vanishes without a word. I fixed one CEFR and declared the class closed; the
   class was one branch wider than I looked.
3. **I assumed the HTTP response carried the writer's refusals.** It does not
   (`routers/document_import.py:221-228` returns three keys and drops
   `unresolved_questions`). The glass-box invariant I called "shipped" holds in
   the function and is invisible on the wire the teacher uses. Spec §2.4 says a
   refusal must be "visible in the result payload"; I never checked *which* payload.
4. **Rung 2's acceptance "re-running the same import twice does not
   double-write"** was written as if the contract module would deliver it. It
   will not — that is writer idempotency (the bridge has it via
   `synced_evidence_keys`; the writer has nothing). It belongs in Rung 2's scope
   but as its own line item with its own key, not as a side effect of resolve().
5. **I assumed `scratch/` was gitignored.** It is not. Files left untracked
   deliberately; the failure list is reproduced inside the committed baseline so
   nothing depends on them.
6. **My hand count of the writer's accepted set (61) is not B3 (55).** The
   difference is real and explained (5 `personal_context` buckets nobody emits
   + `trauma_flag` going to review), but I first wrote them as if they were the
   same number. Measured beats counted.
7. **The spec's diff fence for Rung 2** ("only the contract module, the writer,
   the four lists, and tests") **excludes the router** — yet the biggest teacher-
   visible defect in B5 lives in the router. The fence needs one line added
   before Rung 2 runs, or the teacher keeps seeing 8-and-5 and never the 38.

## 6. Open, and whose

### 6.1 THE RULING THAT CLEARS K8 — operator

**Question:** which structure is the definitive student lens, and what does the
registry say about the bridge between them?

| option | what it means | cost / consequence |
|---|---|---|
| **A — the store's namespace is the contract; docpipe.lens.v1 is a producer** *(recommended)* | The registry declares the store's paths (what the product writes). docpipe's evidence discipline — `_assert_grounded`, evidence-key dedupe, `merge_events` — becomes a **requirement the contract imposes on every producer** (the strong form of `requires_sources`, §2.7.3), not a second storage shape. The bridge's mapping is *declared in the registry as-is*: `strategies_trialed` recorded as a dated re-home into `learning_and_cognition.{strategies_worked,strategies_not_worked,open_questions}`, and the `span_id`/confidence drop recorded as a provenance gap with its own build. | Rung 2 starts immediately, unchanged in shape. MC inherits the store shape plus the producer discipline. Nothing stored changes shape (§2.5 holds). |
| B — docpipe.lens.v1 is definitive; the store is a projection | Every writer, the report-card path included, goes through docpipe's merge; the store is rebuilt from it. | `PROFILE_FIELDS` (10) must first grow to cover `cefr_snapshot`, `trauma_flag`, the 6 scalars, `ethos_profile`, `advanced_enrichment`, `personal_context` — ≥ 20 fields — before it can be definitive. Changes what the product writes. A build of its own, not a night. |
| C — A, but refuse `strategies_trialed` by name at the bridge until it has a real home | Same as A except the re-home is treated as a defect: the bridge refuses the field (visible), and a 10th support category or a strategies namespace is designed later. | Honest but loses data on the two live paths today until the home exists; the alternative "add a category" is a stored-shape change §2.5 forbids tonight. |

**Recommendation: A.** One line from the operator — *"A"*, or *"A but refuse
strategies_trialed"* (= C) — and the next window runs Rung 2 without re-reading
anything: the baseline is committed and the probes are on disk.

### 6.2 Also the operator's

- **`support_profile` origin** (B7 flag). Today: authored, append-only through
  store ops, not reconstructed as-of; import appends with no observation
  behind the entry. If the intent is "every claim about a child derives from
  an append-only record", say so and Rung 2 routes import entries through an
  observation the way CEFR already does. If not, `authored` stands.
- The two fixture rows in the real store (`Abigail Chang`, `Marco Rossi`).
  Still there, still not touched. Gone on your word, by a command you run.

### 6.3 The next window's (Rung 2, once 6.1 is answered)

- Close B4a: route `support_profile.categories.*` through `resolve()` so a
  category or bucket the registry does not know is a **named refusal** and a
  bad bucket is a refusal, not an uncaught `ValueError` that voids the import.
- Return `unresolved_questions` from `/api/students/apply-extractions`
  (`routers/document_import.py:221`). **This is outside the spec's Rung 2 diff
  fence** — add the router to the fence explicitly, or the fence stays and the
  teacher stays blind.
- Writer idempotency: an entry key (path + text + source refs) so the same
  import applied twice writes once. Own line item, own test.
- `academic_strengths` / `personal_strengths` / `home_languages` /
  `learning_differences`: the store has operations for all four
  (`add_profile_strength`, `update_profile`). Enter them `writable` in the
  registry with the store op named — this is wiring, exactly the operator's
  framing, and it is 4 of the 17 in B4.
- `display_name` is consumed at `:74-81` then refused at `:293`. Enter it
  `read_only` after creation (or `writable` via nothing) so the refusal stops
  lying about a field that was in fact used.
- Roster ingest does not set `grade_level` from the CSV's Grade column (B5).
  Not this build; noted so it is not rediscovered.

## 7. Every CANNOT-TELL

- **No local model on PC-23.** 38 of 51 report-card sentences `classify_failed`
  (`local_only_no_model`). The LLM-routed paths — including the live silent drop
  — were proven only in-process (`scratch/b3_b4_probe.py`), never over HTTP on
  this box. On PC-0 with qwen3:8b, B5's numbers will differ.
- Where the pipeline backfills `supporting_chunk_ids` for heuristic-extracted
  fields (every heuristic emits `[]`; all 51 arrived with ids). Not traced —
  past the briefing's stop line.
- Whether the UI renders the import *preview's* `unresolved_questions` (step 1
  returns them) or offers a confirm control for `review_required`. No UI walk.
- Which UX reaches `extraction_engine.extract` (`web.py:4467/4522/6167`); its
  58-path emission is by constant, not by run.
- Whether the five `sha256 does not match` failures in B6 are CRLF specifically.
  Classed by the error line only.
- The ~17 ported MC verbs (carried from the spec; still unverified).

## 8. Fences, honoured

No push to main, no merge, no tag. Path-scoped adds only. No heredoc wrote
file content (commit message via file; scripts via the file tool). Exit codes
read bare. `check_ui_contract.py --bump` not run. Both sandbox variables set
and the sandbox DB's existence verified before any result was trusted. No
student data invented; the one fixture is the repo's own, in a temp sandbox.
`python`, not `python3`.
