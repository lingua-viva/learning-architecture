# REPORT — lens field contract build, 2026-09-03 night window

**Seat:** PC-23 · **Operator:** Mical Neill · **Spec:** `dev/SPEC_LENS_FIELD_CONTRACT_2026-09-03.md`
**Baseline:** `dev/BASELINE_LENS_FIELD_CONTRACT_2026-09-03.md` (Rung 1, committed before any build)

**Outcome in one line:** all four rungs ran. Rung 1 stopped at kill gate K8
(the bridge renames a field); the operator ruled **A** ("the store's
namespace is the contract; docpipe.lens.v1 is a producer; the bridge's mapping
is declared as-is") and Rungs 2–4 ran on that ruling. The accounting
invariant is in code and was watched failing. No source line was touched on
`main`.

---

## 1. State at close

```
branch      fix/cefr-write-and-unknown-field-refusal-2026-09-03
base        a08f1c6  (spec/prompt/start-here; d7e83aadd in ancestry)
commits     aeb33bb  baseline(lens): Rung 1 honest baseline B1-B9, nothing fixed; K8 fires
            f0ba78d  report(lens): K8 fired — run stopped after Rung 1 (superseded by this file)
            fcc4afe  feat(lens): the lens field contract — one registry, resolve() is the only way in (Rung 2)
            90d2888  feat(lens): Rung 3 — five guards watched failing; Observe and Prepare through the contract
            fd98e8c  feat(lens): Rung 4 sweep — producer drift alarm, bridge parity, router resolves before the store
            + this report
pushed      the branch, after this report. main untouched (origin/main still 7037037). No merge, no tag, no release.
files       NEW  src/lingua_viva/lens_field_contract.py · src/lingua_viva/observe_to_lens.py
                 tests/test_lens_field_contract.py (31) · tests/test_observe_to_lens.py (8)
            MOD  src/lingua_viva/student_lens_writer.py (rewritten) · src/lingua_viva/routers/document_import.py
                 src/lingua_viva/routers/students.py (one endpoint) · src/education/content_differentiator.py
            the four lists (data_in_contracts / lens_extract / student_lens) are UNTOUCHED — parity is asserted, not rewritten
scratch/    untracked drivers, kept: b5_roundtrip.py b5_analyze.py b3_b4_probe.py b2_b3_count.py sabotage.py
            baseline_20260903.txt after_20260903.txt before.txt after.txt roster_abigail.csv
real store  ~/.lingua-viva read ONCE read-only in Rung 0; every measurement ran on a sandbox
            (lv_rung1 / lv_rung2 / lv_rung4, both home vars set, sandbox DB existence verified each time)
```

## 2. The delta, with denominators

| | before (a08f1c6) | after (fd98e8c) |
|---|---|---|
| B1 lists | 5 lists: 58 / 9 / 10 / 5 / 10, disagreeing both ways | unchanged on disk; **each asserted against the registry** (6 parity tests) |
| B2 emittable paths | 72 | 72 |
| B3 written when well-formed | **55 / 72** | **60 / 72** |
| B4 emitted-but-unwritten | **17 / 72**: 1 silently dropped, 1 uncaught exception, 14 refused by name, 1 unnamed, 1 review-by-design | **12 / 72**: 9 ethos `declared_not_implemented` (refused by name, on purpose), `display_name` read-only (says it was used), `unclassified` marker (named, content-free), `trauma_flag` review-by-design. **Silently dropped: 0. Exceptions: 0.** |
| B5 report card over HTTP (Abigail) | 51 → 8 / 5 / 38 accounted by count; **refusals not in the HTTP response**; **re-import double-writes** (8 CEFR obs, 4 duplicate entries) | 51 → 8 / 5 / 38 with a 51-row `accounting` ledger **in the HTTP response**; CEFR A2/A1/A1/A2; **second apply: 0 new rows** (4 CEFR obs, 0 duplicates) |
| B6 bounded suite | 790 passed / 13 failed | **829 passed / 13 failed — the same 13** (`comm`: 0 new, 0 fixed); all 13 are PC-23 platform artifacts (baseline B6 table) |
| B7 columns | 22 classified, UNCLASSIFIED 0, 1 flagged | every column has a registry entry (test) |
| B8 bridge | renames 1, drops span_id + confidence → K8 | declared as-is (ruling A): `rehome` + `docpipe_field_id` on the spec; 4 bridge targets asserted to resolve |
| B9 consumers | 13 modules, 4 entry points, none declared | 1 consumer (Prepare) through `requires()`; the other 12 enumerated, not converted (§6.3) |

**Also measured:** Doctor (`python -m doctor.support_loop doctor`) **crashes on
this box** — `doctor.py:254` runs `["python3", ...]` and Windows has no
`python3`. Same class as 3 of the 13 B6 failures. Not a PC-23 quirk: any
Windows install without a `python3` alias gets `/api/health` = degraded.
Fixed in the next slice, not this one (outside the lens contract).

## 3. Every kill gate

| gate | fired? | evidence |
|---|---|---|
| K1 widen contract to fit the bug | **no** | every `writable` entry names a store op that exists (validated at import; sabotage S2 proves the validator bites). `strategies_trialed` persists through the same op the bridge already uses. |
| K2 Observe needs a field redefined | **no** | `test_no_existing_field_changes_meaning`; the only re-home is the one the bridge already applies in production |
| K3 accounting invariant unsatisfiable | **no** | satisfied over 16 mixed fields, over every writable path (72), over every producer path (72), and over HTTP (51/51) |
| K4 `declared_not_implemented` deleted | **no** | ethos + unclassified still declared; sabotage S5 shows the test that guards it |
| K5 HEAD moved between writes | **no** | re-checked before each of 5 commits |
| K6 needed the real `~/.lingua-viva` | **no** | three sandboxes; DB existence verified each time |
| K7 unclassifiable origin/shape | **no** — with the `support_profile` flag carried forward (§6.2) | baseline B7 |
| **K8 bridge drops/renames** | **FIRED at Rung 1 — success.** Cleared by operator ruling A. | baseline B8; f0ba78d |

## 4. Every sabotage (Rung 3.1, `scratch/sabotage.py`)

Each planted, the suite run (`test_lens_field_contract.py` + `test_lens_writer_field_coverage.py`, 35 tests), then restored by inverse edit and verified by sha256. Baseline 35 passed; after all restores 35 passed.

| sabotage | what turned red |
|---|---|
| S1 remove `academic_strengths` from the registry (extractor still emits it) | 3 tests; the writer refused the field **by name** (not silence) |
| S2 point `avoid_pairing_with` at `store:no_such_op` | `LensContractError` at import → both test files error at collection. A startup error, not a runtime AttributeError. |
| S3 CEFR validator accepts anything | `test_invalid_cefr_level_is_refused_by_name` red; probe: **Z9 written to the lens** |
| S4 bypass `resolve()` for one path in the writer | 2 tests red; the writer's own assertion fires: *"1 fields entered, 0 accounted"* |
| S5 make ethos `writable` (delete `declared_not_implemented`) | 1 test red; the write still refuses (no dispatch for that kind), so the guard is two-deep |

**No sabotage changed nothing.** Two sha mismatches on S1/S4 were the first
text-mode write rewriting LF→CRLF on this box (content identical, git saw no
diff); normalised back to LF afterwards.

## 5. What I got wrong

Carried from the Rung 1 report (items 1–7 there still stand: "four lists" was
five; the silent-drop class was one branch wider; the HTTP payload dropped
refusals; idempotency is the writer's, not the contract's; scratch is not
gitignored; hand-count 61 ≠ measured 55; the diff fence excluded the router).
New in Rungs 2–4:

8. **The first OUT-filter declaration was wrong.** I declared `cefr_snapshot`
   *essential* for Prepare. The tree has an operator ruling (2026-07-22) that
   missing CEFR means `foundational` by default. Making it essential would have
   turned a ruled default into a refusal. Corrected to *enriching*, and the
   output now names that it fell back. Declaring a consumer's needs from the
   spec instead of from the consumer's code is the same defect as declaring
   fields from one side.
9. **Observe's confirm path was not exercised.** On the real comment every
   support candidate came out `verified` (confidence ≥ 0.7), so
   `test_confirming_a_candidate_writes_it_with_provenance` **skipped**. The
   path is covered by the report-card tests (`confirmed_fields`), but not on
   an Observe comment. Named, not rendered as green.
10. **I described the diff fence as widened "deliberately" in a commit
    message before writing it down here.** It is here now: the router file is
    inside the fence for this build because the teacher-visible defect lived
    there. If the operator disagrees, `document_import.py` is a 7-line revert.
11. **Rung 4's "convert every call site" is not what I did.** I converted one
    (the support-entry endpoint), checked eight by test (producers, bridge),
    and left four in `observation_capture.py` alone under K2. The spec's
    "route it through resolve()" for *producers* is satisfied by the drift
    alarm (a producer building an undeclared path fails a test), not by
    editing eleven emit sites — the contract's IN filter is the writer, and
    wrapping every emitter would have moved refusals out of the one place
    that accounts for them.

## 6. Open, and whose

### 6.1 The operator's

- **`support_profile` origin (B7 flag).** Authored, append-only through store
  ops, not reconstructed as-of; import appends with no observation behind an
  entry. If "everything about a child derives from an append-only record" is
  the intent, say so and the writer will route support entries through an
  observation the way CEFR already does. Registry note carries the flag.
- **`strategies_trialed` re-home.** Declared and applied per ruling A
  (`learning_and_cognition`, bucket by outcome else `open_questions`), and the
  result says so. If you would rather it refuse until it has a home of its own
  (option C), it is one line: `status="declared_not_implemented"` on that spec
  and a test flips.
- **Ethos writes.** `add_ethos_evidence` exists; the contract refuses ethos on
  purpose (spec §5.1.4). Nine refusals per report card until you rule on the
  review semantics.
- The two fixture rows in your real store. Untouched. Gone on your word.

### 6.2 The next window's

- Wire `observe_to_lens` into `/api/observe` (`web.py:3196-3215`) behind the
  existing safeguarding wrapper; return `candidate_fields` so U8 (editable
  lens) has something to confirm. Then retire the four direct store writes in
  `observation_capture.py:335-486` once a teacher has used the new path.
- OUT filter for the other 12 consumers, `drive_sync` first (it reads the most
  fields, B9). Each is a `requires()` entry + one `read_for` call.
- Roster ingest does not set `grade_level` from the CSV's Grade column (B5).
- Provenance gap the bridge drops (`span_id`, numeric confidence): its own
  build, as the ruling said.
- `check_app_reality.py`: 24 pre-existing MEDIUM findings in
  `static/index.html` (unescaped template values). Not touched tonight.

## 7. Every CANNOT-TELL

- **No local model on PC-23.** 38 of 51 report-card sentences and most of the
  Observe comment went `classify_failed`. The classifier-routed paths (the
  strategies_trialed re-home included) are proven in-process and by test, not
  over HTTP with a model. On PC-0 with qwen3:8b the written/review split will
  differ; the accounting invariant will not.
- Whether `_split_into_student_sections` + `_is_red_safeguarding` behave the
  same for a 30-word comment as for a document with a model in the loop.
  Measured only without one.
- Whether the UI renders `unresolved_questions` / `accounting` now that the
  apply response carries them. The payload is there; the UI was not walked.
- Whether the five `sha256 does not match` B6 failures are CRLF specifically
  (same 5 before and after; classed by error line only).
- The ~17 ported MC verbs (carried from the spec).

## 8. Fences, honoured

No push to main, no merge, no tag. Path-scoped adds only (five commits). No
heredoc wrote file content. Exit codes read bare. `check_ui_contract.py --bump`
never run. Both sandbox variables set and the DB verified before any result
was trusted. No student data invented. `python`, not `python3` — which is
also, it turns out, the Doctor's bug.
