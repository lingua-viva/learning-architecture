# PROMPT: Lingua Viva Teacher Launch Verification

**Spec**: `dev/SPEC_LV_TEACHER_LAUNCH_VERIFICATION_2026-08-16.md`
**Date**: 2026-08-16
**Urgency**: Teachers start using this tomorrow. Claudia tests tonight.
**Kill criterion**: Every teacher workflow completes end-to-end. Zero crashes, zero
data leaks, zero fabricated content rendered as truth.

---

## Context

You are verifying Lingua Viva — an AI learning partner for teachers — the night
before real teachers start using it with real students. This is not a feature build.
This is a comprehensive verification and cleanup pass.

The product runs as an Electron desktop app wrapping a Python backend. Student data
is private — it never leaves the machine. The app uses local models for student-facing
work and can optionally hand off to cloud models for curriculum/general questions only.

**Read the spec carefully**: `dev/SPEC_LV_TEACHER_LAUNCH_VERIFICATION_2026-08-16.md`

**Also read first**:
- `AGENTS.md` — the project rules (especially the Definition of "Pushed")
- `src/web.py` — every API route (this is the backbone)
- `src/lingua_viva/student_lens.py` — student data storage
- `src/lingua_viva/model_gate.py` — external model blocking

---

## Build Order (4 rungs, strict)

### Rung 1: Backend — Every Route Responds

Read `src/web.py` line by line. For every `@app.route` or `@app.post`:
1. Does it have a handler?
2. Does it handle errors?
3. If it touches student data, is it local-only?
4. Is there a dead route with no UI caller?

Create `tests/test_launch_route_audit.py` with tests for route health, student
data locality, and dead route detection.

Run the pipeline end-to-end with a test query. Verify classify → reason → synthesize.

**Commit**: `test(launch): Rung 1 — route audit + pipeline smoke`
**Gate**: All new tests pass + full suite (2231+) passes

### Rung 2: Frontend — Every Button Works

Read `static/index.html`. Trace every button/form submission to its route.
Verify the response renders. Focus on the 7 teacher workflows:
Observe, Ask, Materials, Packet, Parent Report, Student Summary, Morning Brief.

Verify all PDF generation: teacher/student lesson packets, scoped student lens
PDFs, rubric export. The privacy scoping rules are non-negotiable.

**Commit**: `test(launch): Rung 2 — UI surface + PDF verification`
**Gate**: All PDF scoping tests pass + teacher workflows verified

### Rung 3: Privacy & Safety — The Non-Negotiables

Verify:
- Student PII never sent to external models
- GIR gates every student-facing response
- No fabricated observations in student lens
- Demo student fallback removed (fail-closed 400/404)
- No cross-student data leaks

These are the tests that determine whether the product is safe to use with
real children's data. If any fail, the launch doesn't happen.

**Commit**: `test(launch): Rung 3 — privacy + safety verification`
**Gate**: Zero external model calls with student PII. Zero fabrication paths.

### Rung 4: End-to-End Teacher Day

Simulate Claudia's full day: morning brief → observe → ask → materials →
packet → parent report → student summary. Then test error recovery:
network offline, model timeout, empty student.

Run the full verification suite:
```bash
python3 -m pytest tests/ -q --tb=short
python3 -m src.lv_cli eval teacher-readiness
python3 -m pytest tests/test_route_contract.py tests/test_ui_contract.py -v
```

**Commit**: `test(launch): Rung 4 — teacher day simulation`
**Gate**: Full teacher day completes. All 2231+ tests pass.

---

## Cleanup Pass (alongside verification)

As you read each file:
- Delete dead code (functions never called)
- Remove stale imports
- Remove debug print/console.log statements
- Delete commented-out code
- Convert remaining `student-nora` demo references to fail-closed errors
- Resolve or document TODOs

**Do NOT**: refactor, add features, change behavior, or restructure.

**Commit cleanup separately**: `chore(launch): cleanup dead code + stale imports`

---

## Standing Rules

- **Privacy is non-negotiable** — student data leak = launch cancelled
- **Verification, not building** — do not add features
- **Full suite after every commit** — 2231+ tests must pass
- **Do NOT push** — operator drives pushes
- **Test on THIS machine** with desktop v0.2.59
- **Report any finding that blocks launch** immediately — don't silently fix
  something that might indicate a deeper problem

---

*"Tomorrow teachers trust this with their students.
Tonight we verify every line deserves that trust."*
