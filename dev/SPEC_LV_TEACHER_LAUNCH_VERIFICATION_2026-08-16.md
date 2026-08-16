# SPEC: Lingua Viva Teacher Launch Verification — Every Line, Every Route, Every Surface

**Date**: 2026-08-16
**Status**: READY TO BUILD — tonight session before teacher launch
**Priority**: P0 CRITICAL — teachers start using this tomorrow
**Kill criterion**: Claudia can complete every teacher workflow end-to-end on this machine. Zero crashes, zero data leaks, zero fabricated content rendered as truth.

---

## 0. Context

Tomorrow teachers start using Lingua Viva in real classrooms. Claudia tests tonight.
This spec is a comprehensive verification pass — every Python module, every route,
every UI surface, every privacy boundary. Not a feature build. A verification and
cleanup pass.

**The product**: An AI-powered learning partner for teachers. It observes students,
generates differentiated materials, produces parent reports, and tracks growth — all
governed, all private, all grounded in real observations.

**What just shipped**: Artifact PDF hardening (lesson packets, student lens PDFs with
scoped sharing, rubric export). Desktop v0.2.59 is live.

**What matters most**: Privacy (student data never leaves the machine), honesty
(no fabricated observations, GIR gates delivery), and reliability (every button works,
every route responds, every surface renders).

---

## 1. Rung 1: Backend Verification — Every Route Responds

### 1.1 Route audit

Read `src/web.py` end to end. For EVERY route:

1. Verify it has a handler that doesn't crash on basic input
2. Verify sensitive routes check authentication/access control
3. Verify student data routes are local-only (no external model calls for student PII)
4. List any dead routes (defined but unreachable from UI)

Create a test: `tests/test_launch_route_audit.py`

```python
def test_every_route_responds():
    """Hit every API route with minimal valid input. None should 500."""

def test_student_data_routes_are_local_only():
    """Routes that handle student PII must not call external models."""

def test_no_dead_routes():
    """Every defined route has at least one UI call site."""
```

### 1.2 Pipeline smoke

Run a query through the pipeline and verify the full chain:

```python
def test_pipeline_classify_reason_synthesize():
    """A teacher question classifies, reasons, and synthesizes without error."""

def test_pipeline_student_query_stays_local():
    """A query about a specific student routes local, never external."""
```

### 1.3 Data integrity

```python
def test_student_lens_read_write_roundtrip():
    """Write an observation, read it back, verify identical."""

def test_observation_dedup():
    """Double-submit same observation within 300s returns duplicate:true."""

def test_lesson_materials_generate():
    """Generate lesson materials, verify 3 tiers present."""
```

### Kill criteria (Rung 1)
- [ ] Every route in web.py responds without 500
- [ ] Student data routes verified local-only
- [ ] Pipeline classify→reason→synthesize chain works
- [ ] Observation read/write roundtrip works
- [ ] All new tests pass + all 2244 existing tests pass

---

## 2. Rung 2: Frontend Verification — Every Button Works

### 2.1 UI surface audit

Read `static/index.html` and all JS in `static/`. For every interactive element:

1. Does the click handler call an existing route?
2. Does the response render correctly?
3. Are error states handled (network failure, empty data, model timeout)?

Focus areas (the teacher's daily workflow):

| Surface | What teacher does | Route | What to verify |
|---------|------------------|-------|---------------|
| **Observe** | Records an observation about a student | POST /api/observe/capture | Observation saved, lens updated, no duplicate |
| **Ask** | Asks a question about a student or curriculum | POST /api/ask | Response grounded, GIR shown, local for student data |
| **Materials** | Generates differentiated lesson materials | POST /api/lesson/generate | 3 tiers generated, preview renders, print works |
| **Packet** | Approves and prints a lesson packet | POST /api/lesson/approve | PDF generated, teacher + student versions |
| **Parent Report** | Generates parent-facing summary | POST /api/parents/recommendation | Grounded in observations, no fabrication |
| **Student Summary** | Views student lens data | GET /api/students/:id/lens | All sections render, pending evidence shown |
| **Morning Brief** | Views daily brief | GET /api/brief | Today's plan, flagged students, upcoming |

### 2.2 Print/PDF verification

The artifact PDF hardening just shipped. Verify:

```python
def test_lesson_packet_pdf_teacher_version():
    """Teacher PDF includes individual support section."""

def test_lesson_packet_pdf_student_version():
    """Student PDF excludes individual support (privacy)."""

def test_student_lens_pdf_teacher_scope():
    """Teacher-scoped PDF excludes Personal Context."""

def test_student_lens_pdf_family_scope():
    """Family-scoped PDF excludes Personal Context."""

def test_student_lens_pdf_hr_scope():
    """HR-scoped PDF includes Personal Context."""

def test_rubric_pdf_export():
    """Rubric exports as immutable PDF."""

def test_pdf_idempotent_regeneration():
    """Same content → same PDF path, no duplicate."""
```

### Kill criteria (Rung 2)
- [ ] Every teacher workflow button calls the right route
- [ ] Observe → save → lens update chain works
- [ ] Materials → 3 tiers → preview → print chain works
- [ ] Packet → approve → PDF (teacher + student versions) chain works
- [ ] Parent report → grounded summary chain works
- [ ] All PDF scoping rules verified (teacher/family/HR)

---

## 3. Rung 3: Privacy & Safety — The Non-Negotiables

### 3.1 Student data never leaves the machine

```python
def test_student_pii_never_sent_to_external_model():
    """Any query containing student name/ID routes local. Never external."""

def test_observation_content_local_only():
    """Observation text is never sent to cloud models."""

def test_parent_report_local_only():
    """Parent report generation is entirely local."""

def test_exit_gate_blocks_student_data():
    """Exit gate refuses to transmit content with student identifiers."""
```

### 3.2 No fabricated content presented as fact

```python
def test_gir_gates_delivery():
    """Response with GIR < threshold shows grounding warning, not confident text."""

def test_no_fabricated_observations():
    """Student lens only contains teacher-submitted observations, never model-generated."""

def test_ask_grounding_surface():
    """Ask response shows GIR score. Fabricated answers show warning."""
```

### 3.3 Access control

```python
def test_demo_student_fallback_removed():
    """POST /api/parents/recommendation with unknown student_id returns 400, not demo data."""

def test_no_cross_student_data_leak():
    """Query about student A never returns data from student B."""
```

### Kill criteria (Rung 3)
- [ ] Zero external model calls with student PII
- [ ] GIR gates every student-facing response
- [ ] No fabricated observations in student lens
- [ ] Demo student fallback removed (fail-closed)
- [ ] No cross-student data leaks

---

## 4. Rung 4: End-to-End Teacher Day Simulation

### 4.1 Claudia's morning workflow

Simulate a full teacher day:

1. **Morning**: Open app → morning brief loads → view today's students
2. **Observe**: Record 3 observations for different students
3. **Ask**: "What patterns am I seeing with Student A this week?"
4. **Materials**: Generate a differentiated lesson for today's topic
5. **Review**: Preview lesson packet → approve → print teacher + student versions
6. **End of day**: Generate parent report for one student → review → send
7. **Student summary**: View full student lens → check pending evidence → confirm one

### 4.2 Error recovery

8. **Network offline**: Disconnect wifi → app still works (local model)
9. **Model timeout**: If local model takes >60s, show honest timeout message
10. **Empty student**: New student with zero observations → honest "no data" message

### 4.3 Smoke test commands

```bash
# Full suite
cd ~/learning-architecture
python3 -m pytest tests/ -q --tb=short

# Focused teacher readiness
python3 -m src.lv_cli eval teacher-readiness

# Contract gates
python3 -m pytest tests/test_route_contract.py tests/test_ui_contract.py -v

# Desktop build
cd desktop && npm run build

# Ignition
python3 -m src.lv_cli ignition
```

### Kill criteria (Rung 4)
- [ ] All 10 steps of the teacher day simulation complete without error
- [ ] Network-offline still works (local model)
- [ ] Model timeout shows honest message
- [ ] Empty student shows "no data" (not fabricated content)
- [ ] Full suite: 2231+ passed
- [ ] Teacher readiness eval: all checks pass
- [ ] Desktop build: green

---

## 5. Cleanup Pass — While Verifying

As you verify each module, clean up:

- **Dead code**: functions that are never called → delete
- **Stale imports**: unused imports → remove
- **TODO comments**: resolve or convert to tracked issues
- **Hardcoded demo data**: any remaining `student-nora` references → fail-closed
- **Console.log / print statements**: remove debug output
- **Commented-out code**: delete (it's in git)

**Do NOT**: refactor working code, add features, change behavior, or restructure modules.
This is a verification and cleanup pass, not a build.

---

## 6. Files to Read (in order)

| Priority | File | What to verify |
|----------|------|---------------|
| 1 | `src/web.py` | Every route, auth checks, local-only enforcement |
| 2 | `src/lingua_viva/student_lens.py` | Observation storage, lens read/write, dedup |
| 3 | `src/lingua_viva/lesson_materials.py` | Tier generation, packet creation, PDF output |
| 4 | `src/lingua_viva/deliverables/` | PDF generation, scoped sharing |
| 5 | `src/pipeline.py` | Classify → reason → synthesize chain |
| 6 | `src/lingua_viva/model_gate.py` | External model blocking for student data |
| 7 | `src/education/parent_report.py` | Parent summary generation, grounding |
| 8 | `src/lingua_viva/brief.py` | Morning brief generation |
| 9 | `src/education/observation_capture.py` | Observation recording |
| 10 | `static/index.html` | UI surface, button handlers, render logic |
| 11 | `desktop/electron/main.ts` | Electron shell, window config |
| 12 | `src/lingua_viva/audit_receipts/` | Audit trail for all artifacts |

---

## 7. Standing Rules

- **This is verification, not a build** — do not add features
- **Privacy is non-negotiable** — any student data leak is a showstopper
- **Commit cleanup separately from verification tests** — so cleanup can be reverted if needed
- **Run full suite after every change** — 2231+ tests must pass
- **Do NOT push** — operator drives all pushes
- **Test on THIS machine** with the real app (desktop v0.2.59)

---

*"Tomorrow teachers trust this with their students.
Tonight we verify every line deserves that trust."*
