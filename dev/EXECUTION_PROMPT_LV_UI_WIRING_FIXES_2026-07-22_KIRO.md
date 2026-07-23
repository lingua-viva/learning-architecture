# Kiro Execution Prompt: LV UI Wiring Fixes (Add Student, RTI Buttons, Ask Honesty)

Copy everything below into a fresh Kiro session. Working directory:
`~/learning-architecture` (or wherever your local clone of
`lingua-viva/learning-architecture` lives).

---

```markdown
You're working in the Lingua Viva repo. This is a small, concrete, 3-part UI wiring
task — all 3 bugs were reproduced live against the running desktop app this session,
not speculative.

The product bar: a teacher can add a real student from the Students tab and see it
appear immediately, can click Confirm/Defer on an RTI proposal and have it actually
record something, and never sees a raw Python error dressed up as a real AI answer
in Ask.

The output is not a chat summary. The output is working code, verified live in the
running app (not just curl), and a short report.

## Execution Contract

Work in this order:

1. Read the required files.
2. Read `dev/specs/SPEC_LV_UI_WIRING_FIXES_2026-07-22.md` in full — it is your spec.
   Do not deviate from its scope. In particular: do NOT attempt to fix the actual
   Ask/query reasoning pipeline (the `ontology.engine` import) — that's explicitly
   deferred. You are only making its failure render honestly.
3. Build §2a (Add Student), §2b (Confirm/Defer), §2c (Ask error honesty) — in that
   order, each one fully working and live-verified before moving to the next.
4. Run the full verification checklist.
5. Update `dev/INDEX.md` with this spec's status.
6. Give the final response under 120 words.

Do not batch all 3 changes together and test once at the end — verify each one live
in the running app as you finish it. If you break one of the other two while building
the third, you will not notice until the end.

## Required Reading (in order)

1. `CLAUDE.md` — repo architecture, runtime boundaries, privacy rules
2. `dev/INDEX.md` — current spec status
3. `dev/specs/SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` — sibling spec, read for
   context only, you have no dependency on it and should not import
   `src/lingua_viva/data_in_contracts.py`
4. `dev/specs/SPEC_LV_UI_WIRING_FIXES_2026-07-22.md` — YOUR SPEC, full detail on all
   3 bugs with exact file:line references for every root cause
5. `static/index.html` — lines 809-906 (Students + Ask views) are what you're editing
6. `src/web.py` — lines 172-230 (student store helpers), 647-716 (students routes),
   971-1068 (`/api/query`, the ontology.engine failure + its exception handling)
7. `src/education/student_lens.py` — `create_lens()` (already works, you're adding
   one new method alongside it, not changing it) and the schema pattern to match
8. `src/pipeline.py` line 38 — confirm for yourself this import is genuinely broken
   (do not try to fix it — just confirm the failure mode matches the spec)

## Why You Specifically

This is the same class of work as your `SPEC_PREREQUISITE_DETECTION_RESOLUTION_LV`
pass — concrete, reproduced bugs, precise file:line root causes already identified,
build-and-verify-live discipline. No architecture decisions left to make; the spec
already made them. Execute it.

## What To Build

Full detail is in the spec (§2a/§2b/§2c) — do not re-derive it here, read the spec.
Summary:

1. `POST /api/students` route + Add Student form in `renderStudents()`.
2. `StudentLensStore.record_rti_decision()` + `rti_decisions` table + `POST
   /api/students/{id}/rti/decision` route + wire the two dead buttons in `loadLens()`.
3. Backend: catch `ModuleNotFoundError`/`ImportError` in `/api/query`'s exception
   handler with a distinct, honest, non-alarming message. Frontend: render error
   responses (`data.error` present) visually distinct from real answers — no
   routing/model/citation badges on an error.

## Hard Rules

- Do not touch `_seed_demo_roster()`'s 3 demo students or their existing data.
- Do not touch `rti_tier_history` / observation append-only semantics.
- Do not attempt to fix `src/pipeline.py`'s `ontology.engine` import — out of scope,
  explicitly deferred by the operator to a session ~2 weeks out.
- Do not commit — leave everything staged for operator.
- No real student data, institution names, or private school documents anywhere.
- If you touch `static/index.html` or `src/web.py`, run
  `python3 scripts/check_ui_contract.py --bump` if that script exists in this repo
  (verify first — do not assume).

## Verification Before Closing

```bash
python3 -m pytest -q tests/
python3 -m py_compile src/web.py src/education/student_lens.py
python3 -m src.lv_cli serve 8787   # then walk it live in browser/app:
                                    #  - add a student, confirm it appears
                                    #  - click Confirm and Defer on an RTI proposal
                                    #  - ask any question in Ask, confirm no raw
                                    #    Python error text appears styled as an answer
```

Live-verify all 3 in the actual running app. A passing `curl` is not sufficient
evidence for a UI-facing spec — say so explicitly in your report if you could not
live-test any one of the three, and why.

## Deliverables

1. Working code for all 3 fixes.
2. `dev/reports/REPORT_LV_UI_WIRING_FIXES_2026-07-22.md` — one row per fix:
   what was broken, what you changed, how you verified it live, any deviation from
   spec and why.
3. `dev/INDEX.md` updated.

## Final Response

Under 120 words. Include only:
- status of all 3 fixes (done / partial / blocked, with why)
- report path
- test result
- anything you deliberately left out of scope per the Hard Rules

Do not restate the whole task.
```
