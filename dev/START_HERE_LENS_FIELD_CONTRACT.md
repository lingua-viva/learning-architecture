# START HERE — lens field contract build

You are a fresh window with no prior context. This file is your entire briefing.

**Repo:** `C:\Users\spide\lv-work` — `lingua-viva/learning-architecture`
**Operator:** Mical Neill. Away for the night. Nothing needing a human decision
gets decided — record it and move on.

---

## The framing, from the operator

**This system is OVER-built, not under-built.** Two months of pieces exist and
work. Ten deliverable types, eight action verbs, thirteen modules that read a
lens, a full extraction pipeline, an evidence-chained lens implementation, a
SQLite lens store. **Nothing here needs authoring. It needs wiring.**

Your job is not to add capability. It is to make one declared contract that all
three sides can live with — the producers that put information in, the lens that
holds it, and the consumers that turn it into something for a teacher. Every
time you feel the pull to build a new feature tonight, that is the wrong
instinct. Wire what is there.

## What you are building, in one paragraph

Lingua Viva stores a "lens" per student — the accumulating record a teacher
builds up. Information reaches it from report cards, teacher observations, and
soon oral and written assessments. **There is currently no declared answer to
"what is a lens field."** Four separate lists each claim to be it and they
disagree with each other; at least four more namespaces are written by code and
appear in none of them. That is why CEFR levels were extracted at 0.95
confidence, displayed in the import preview, and silently dropped for a week.
You are declaring the structure once, making every write resolve through it, and
making drift fail a test.

---

## Read these four, in this order, before touching anything

```
1. dev/SPEC_LENS_FIELD_CONTRACT_2026-09-03.md      the contract + the 4 rungs
2. dev/PROMPT_LENS_FIELD_CONTRACT_4RUNG_2026-09-03.md   your operating procedure
3. dev/UX_MATRIX_AND_ACTION_LIST_2026-09-03.md     why this is item 1 of 15
4. dev/PLAN_SIR_SPLIT_AND_ONE_LOGIC_2026-09-03.md  the rulings (R1-R4, C1-C9)
```

Then read only these source files:

```
src/lingua_viva/student_lens_writer.py             all of it, it is short
src/lingua_viva/docpipe/lens_extract.py            the extractor half only
src/education/student_lens.py                      the store API and its laws
palette/sdk/integrity_gate.py                      130 lines of prior art
```

**Then stop reading and start.** Reading an eleventh file when five would do is
the known failure mode of this seat.

---

## Then run it

Follow `PROMPT_LENS_FIELD_CONTRACT_4RUNG_2026-09-03.md` rung by rung.

```
RUNG 0   back everything up          exit: clean tree, HEAD recorded
RUNG 1   the honest baseline B1-B9   exit: baseline committed, NOTHING fixed
RUNG 2   build it + report cards     exit: report card -> lens works end to end
RUNG 3   sabotage it + THREE SIDES   exit: every guard watched failing, and
                                           one producer + the store's laws +
                                           one consumer all satisfied
RUNG 4   sweep, reconcile, report    exit: report written, branch pushed
```

**Nine baselines (B1-B9) and eight kill gates (K1-K8).** Read spec §4 and §9 for
both lists. Three of them exist because a contract drafted from one side only
is the defect that produced four disagreeing field lists in the first place.

Do not start a rung before the previous rung's exit gate.

---

## The seven things that will actually bite you

1. **A push to `main` IS a desktop release.** `auto-release.yml` fires on push
   to main and its paths filter includes `src/**`. All of this work is in
   `src/`. **Push branches freely. Never push `main`, never merge to `main`,
   never tag.**

2. **Sandbox isolation needs BOTH variables, and verify it held.**
   `LV_CONFIG_HOME` redirects the lens store. `LV_STATE_HOME` does **not** —
   they are two independent seams despite the code claiming one. Set both, then
   check the sandbox DB actually exists:
   ```bash
   ls "$SB/runtime/student_lenses.db"   # if absent, you are writing to the
                                        # operator's REAL store. Stop.
   ```
   This exact trap put two fixture students into his real data today.

3. **`scripts/check_ui_contract.py` FAILS on this machine and the failure is
   false.** It hashes raw bytes; Windows CRLF differs from the LF-locked digest
   for a byte-identical file. **Never run `--bump`** — it would lock the CRLF
   digest and break PC-0 and CI.

4. **Read exit codes bare.** `cmd | tail; echo $?` gives you the pipe's status.
   That has produced a false green here.

5. **Never `git add -A`.** Path-scoped adds only. Some runs rotate tracked
   files and a sweep commits their deletion.

6. **Write file content with a file-writing tool, never a bash heredoc.**
   Heredocs mangle escapes on this box and have corrupted a source file.

7. **`python3` is not on PATH in Git Bash here. Use `python`.**

---

## The rule that IS the deliverable

Every field that enters the writer must end up in exactly one of
`written_fields`, `review_required`, or `unresolved_questions`.

Nothing may be absent from all three. That single invariant is what makes
"silently dropped" structurally impossible instead of merely currently-absent,
and it is the whole point of the night. **If you cannot satisfy it, stop and
report — do not weaken it to finish.**

Taken from Palette's wire contract, which also supplies the constraint that
keeps it humane: *warnings are informational, not blocking — glass-box, not
gatekeeping.* One drifted field refuses that field. It must never cost a teacher
her whole import.

---

## When you finish

Write `dev/REPORT_LENS_FIELD_CONTRACT_2026-09-03.md` with: state at close, the
before/after delta with denominators, every kill gate and whether it fired,
every sabotage and what it turned red, **what you got wrong**, what is open and
whose it is, and every CANNOT-TELL named rather than rendered as clean.

A kill gate that fired and stopped the run is a **success**. Say so plainly.

Claims cite `file:line`, a commit SHA, or output from a command you ran. Disk is
truth. Every number in the spec was true on 2026-09-03 and is expected to have
moved — **read the tree, never quote the spec.**
