# PROMPT — build the lens field contract, four rungs, unattended

**Spec:** `dev/SPEC_LENS_FIELD_CONTRACT_2026-09-03.md` — **read it in full before
you touch anything.** This prompt is the operating procedure; the spec is the
contract. Where they disagree, the spec wins and you report the disagreement.

**Repo:** `C:\Users\spide\lv-work` (`lingua-viva/learning-architecture`)
**Base:** `fix/cefr-write-and-unknown-field-refusal-2026-09-03` @ `d7e83aadd`, or
`main` if that branch has merged by the time you start. **Check, do not assume.**
**Operator:** Mical Neill. Away. Nothing that needs a human decision gets decided.

---

## Before your first edit

```bash
cd /c/Users/spide/lv-work
git status --porcelain          # must end at 0 lines before you build
git rev-parse HEAD              # record it; re-check before every commit
git branch --show-current
git log --oneline -3
```

Then read, in this order:

1. `dev/SPEC_LENS_FIELD_CONTRACT_2026-09-03.md` — the contract
2. `dev/UX_MATRIX_AND_ACTION_LIST_2026-09-03.md` §3.1 — why this is item 1 of 15
3. `dev/PLAN_SIR_SPLIT_AND_ONE_LOGIC_2026-09-03.md` §5 (R1–R4) and §7 (C1–C9)
4. `src/lingua_viva/student_lens_writer.py` — the whole file, it is short
5. `src/lingua_viva/docpipe/lens_extract.py` — the extractor half only:
   `_extract_cefr`, `_route_to_support_category`, `extract_for_lens_update`,
   `apply_extractions_to_lenses`
6. `palette/sdk/integrity_gate.py` — 130 lines, and the reason the contract
   reports instead of blocks

**Stop reading after that.** The failure mode of this seat is reading eleven
files where five would do. If you have read the same file twice without changing
your approach, you are stalling.

---

## The one-paragraph version

Lingua Viva has four lists that each claim to define "a lens field", they
disagree in both directions, and a fifth namespace (`ethos_profile`) is emitted
by the extractor while appearing in none of them and being implemented by
nothing. That is why CEFR levels were extracted at 0.95 confidence, shown in the
preview, and silently dropped for a week. **Declare the field set once, make the
writer resolve every path through it, make drift fail a test, and make it
impossible for a field to enter and be mentioned nowhere in the result.**

---

## RUNG 0 — gate

Back everything before you build. Path-scoped adds only; `git add -A` is
forbidden — `mc improve`-class runs rotate tracked files and a sweep commits
their deletion.

**Exit gate:** clean tree, HEAD recorded, base branch named in your notes.
**If the tree cannot be backed, do not start.**

---

## RUNG 1 — the honest baseline. Fix nothing.

Freeze `dev/BASELINE_LENS_FIELD_CONTRACT_2026-09-03.md` and **commit it before
your first line of implementation.** A before-number reconstructed afterwards is
a proxy, and this run is judged on a delta.

Record B1–B6 from spec §4, each with the command that produced it:

```bash
# B1 — the four lists, read from the tree
PYTHONPATH=. python -c "
from src.lingua_viva.data_in_contracts import STUDENT_LENS_FIELDS as S
from src.education.student_lens import SUPPORT_CATEGORY_IDS, StudentLensStore
from src.lingua_viva.docpipe.lens_extract import _LENS_FIELD_IDS as L
print(len(S), len(SUPPORT_CATEGORY_IDS), len(L), len(StudentLensStore.UPDATABLE_PROFILE_FIELDS))
print('only in SUPPORT:', sorted(set(SUPPORT_CATEGORY_IDS)-set(L)))
print('only in LENS   :', sorted(set(L)-set(SUPPORT_CATEGORY_IDS)))
print('ethos declared :', any(f.startswith('ethos_profile') for f in S))"
```

- **B2** — every distinct `field_path` any extractor in `src/` can emit.
  Enumerate **from source** (grep `field_path=` and read each site), not from a
  single run. A run only shows the paths that fixture happened to trigger.
- **B3** — every path `write_student_lens` has a branch for.
- **B4** — `B2 − B3`. Expect at least the whole `ethos_profile` namespace.
- **B5** — the report-card round trip, end to end over HTTP (procedure below).
- **B6** — the bounded test baseline, **full failure list preserved to a file**:

```bash
python -m pytest tests/ -q -p no:randomly -rf \
  -k "lens or extract or writer or docpipe or observation or student or contract" \
  --ignore=tests/test_daily_file.py --ignore=tests/test_document_intelligence.py \
  > scratch/baseline_$(date +%Y%m%d).txt 2>&1
grep '^FAILED' scratch/baseline_*.txt | sed 's/ - .*//' | sort > scratch/before.txt
```

**Do not pipe pytest into `tail` and keep only that** — a truncated capture cost
this seat a re-run today. Redirect the whole thing, then read it.

**Exit gate:** baseline committed. **No source file changed in Rung 1.**

---

## RUNG 2 — build the contract, finish the report-card UX

### Build (spec §5.1)

`src/lingua_viva/lens_field_contract.py`, then make `write_student_lens()`
resolve **every** path through `resolve()` and dispatch on the resolved spec's
`kind` rather than on string prefixes.

Three things that are easy to get wrong:

- **`declared_not_implemented` must exist on the first night.** It is how
  `ethos_profile` is represented honestly: declared, not writable, refusing by
  name. Deleting it to reduce the refusal count is kill criterion K4.
- **Where the four lists disagree, record both — do not pick a side.** Enter the
  category with an explicit `status` and a note naming which list it came from.
  Unifying silently is exactly the defect this contract exists to end.
- **The accounting invariant is the deliverable.** Every field that enters must
  appear in exactly one of `written_fields` / `review_required` /
  `unresolved_questions`. If you cannot satisfy it, that is K3 — stop and report.
  Do not weaken it to finish.

### Then iterate the report-card UX until it is genuinely done

Run it, read the output, fix, run again. **"The tests pass" is not the
acceptance.** The acceptance is the lens contents after an HTTP round trip.

```bash
# sandboxed server — set BOTH home vars; they are two independent seams
SB=/c/Users/spide/AppData/Local/Temp/claude/lv_rung2
rm -rf "$SB"; mkdir -p "$SB"
(LV_CONFIG_HOME="$SB" LV_STATE_HOME="$SB" python src/web.py 8821 > "$SB/server.log" 2>&1 &)
# wait for /api/health, then confirm routers_loaded == routers_expected
```

**Verify the sandbox actually held** before trusting any result:

```bash
ls "$SB/runtime/student_lenses.db"     # must exist
# if it does not, the store wrote to the operator's real home. STOP.
```

The full chain, in order — the roster step is multi-stage and step one reports
success while creating nothing:

```
POST /api/students/ingest              (multipart, Name,Grade CSV)
GET  /api/students/ingest/{job_id}     poll until status is preview or done
POST /api/students/ingest/approve      {"job_id": ...}
GET  /api/students/ingest/{job_id}     poll until done
POST /api/students/ingest/confirm      {"job_id":..., "display_names":[...]}
GET  /api/students                     students must now be non-empty
POST /api/students/import-document     (multipart, the Abigail fixture)
POST /api/students/apply-extractions   {"extraction_log_path":..., "confirmed_students":[...]}
GET  /api/students                     read cefr_snapshot
```

Fixture: `tests/fixtures/docpipe/synthetic_report_card_abigail.txt` (student
"Abigail Chang"). Build the JSON with `json.dumps` — a Windows path pasted into
a shell-quoted JSON body is invalid JSON (`\U` is not an escape) and will cost
you a confusing 400.

**Green means all of:**

- every preview field is accounted for in the apply result;
- `cefr_snapshot` reads reading A2 / writing A1 / speaking A1 / listening A2;
- every refusal names its field and its reason;
- no field is absent from all three result lists;
- the same import run twice does not double-write or corrupt the lens.

**Kill gate K1:** if passing requires widening the contract to accept a path no
store operation can persist, stop. That is the contract bending to fit the bug.

**Exit gate:** the loop is green; the diff touches only the contract module, the
writer, the four lists, and tests.

---

## RUNG 3 — watch every guard fail, then a second UX

### 3.1 Sabotage first. An instrument nobody has watched fail is a claim.

Run each row of spec §6.1, record the before/after counts, and **restore by
inverse edit** — never `git checkout` a file carrying your own work (that has
cost this project a full refactor twice).

Sabotage that changes nothing is the most valuable result available: it means
the suite cannot see the property it claims to guard. If that happens, **fix the
suite, not the sabotage**, and say so in the report.

### 3.2 Second UX — one write path and one read path

**Observe (U4)** is the operator's priority: a teacher's comment, parsed
sentence by sentence, each candidate field resolved through `resolve()`, same
refusal semantics, same accounting invariant.

**And one read consumer** — `Summaries` (U10) or `Prepare` (U9) — must resolve
its fields through the contract too. A contract proven only on writes is
half-proven; the point of `lens → output` is that consumers read a declared
shape. Name which you chose and why.

**Kill gate K2:** if Observe cannot be routed without changing the *meaning* of
an existing field, stop and report. Redefining a field a teacher already has
data in is worse than leaving Observe unwired.

**Exit gate:** Observe writes through the contract on a real comment; one read
consumer resolves through it; every sabotage observed failing and restored.

---

## RUNG 4 — sweep, reconcile, report

1. **Enumerate every remaining site** in `src/` that writes a lens field or
   names a field path. Report the count, then convert them, then report the
   count again. Enumerate before converting — a sweep you cannot count is a
   sweep you cannot verify.
2. Re-measure B1–B6. Report as a delta **with denominators**.
3. Re-run the bounded suite and diff the failure set against
   `scratch/before.txt`, test-id for test-id:
   ```bash
   grep '^FAILED' scratch/after_*.txt | sed 's/ - .*//' | sort > scratch/after.txt
   comm -13 scratch/before.txt scratch/after.txt   # NEW failures
   comm -23 scratch/before.txt scratch/after.txt   # FIXED
   ```
   **New failures are reported as new failures.** Not explained away, not
   absorbed into "pre-existing".
4. Run `check_route_reachability.py` and `check_app_reality.py`; report both.
   **`check_ui_contract.py` fails falsely on this machine (CRLF vs the
   LF-locked digest). DO NOT run `--bump`** — see spec §7.4.
5. Write `dev/REPORT_LENS_FIELD_CONTRACT_2026-09-03.md`.

**Exit gate:** report written, branch pushed, nothing merged to `main`.

---

## Fences — no exceptions

Spec §8 in full. The four that will bite you tonight:

- **A push to `main` IS a desktop release.** `auto-release.yml` fires on push to
  main with a paths filter including `src/**`, and this work is entirely inside
  `src/`. Push branches freely; never `main`.
- **`LV_CONFIG_HOME` redirects the lens store. `LV_STATE_HOME` does not.** They
  are two independent seams (50 sites vs 30) despite `config.py:215` claiming
  one canonical one. Set both, then *verify the sandbox DB exists* before
  trusting isolation. This seat leaked two fixture students into the operator's
  real store today by trusting the wrong variable.
- **Read exit codes bare.** A pipe reports the pipe's status; that has produced
  a false green here.
- **Write file content with a file-writing tool, never a heredoc.**

---

## The report

`dev/REPORT_LENS_FIELD_CONTRACT_2026-09-03.md`, in this order:

1. **State at close** — branch, HEAD, what is pushed, what is not.
2. **The delta** — B1–B6 before and after, with denominators.
3. **Every kill gate**, and whether it fired. A gate that fired and stopped the
   run is a **success**, not a failure — say so plainly.
4. **Every sabotage** and what it turned red. Any sabotage that changed nothing
   gets its own section.
5. **What I got wrong** — corrections to your own claims during the run. This
   section is not optional and it is the most useful part of every report this
   project has produced.
6. **Open, and whose** — operator vs next window.
7. **Every CANNOT-TELL**, named, never rendered as clean.

Claims cite `file:line`, a commit SHA, or command output you ran this session.
Anything else is `CANNOT-TELL`. **Disk is truth.** A figure quoted from the spec
instead of read from the tree is the defect this whole contract exists to end —
every number in that spec was true on 2026-09-03 and is expected to have moved.
