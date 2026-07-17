# ADDENDUM: Three-Tier Sidebar Design (Iterated)

**Amends**: SPEC_LINGUA_VIVA_APP_COMPLETE_BUILD_2026-07-16.md §Phase 2
**Date**: 2026-07-16
**Author**: kiro.design
**Source**: 5 iterations against Still I Rise case study (architecture/, teacher-use-cases.md, ADMIN_GUIDE.md, LINGUA_VIVA_FORK_SPEC.md), Claudia sync notes, ontology/education/*.yaml (40+ nodes across 6 domains)

---

## The Problem With the Original Spec's Sidebar

The original spec proposed: `Plan | Prepare | Assess | Reflect` — four items for everyone.

After reading the full documentation, this is wrong for three reasons:

1. **Still I Rise has 3 distinct user tiers** (admin, teacher, student) with radically different workflows. A coordinator viewing programme-wide CEFR trends and a classroom teacher capturing a 30-second observation note are not the same person doing the same work.

2. **Observation capture is the killer feature** — not an afterthought inside "Assess". The Claudia sync (Use Case 1, 6, 7) makes clear: the teacher needs to talk into the phone, tag a student, and be done in <30 seconds. That's a primary sidebar action, not buried inside another view.

3. **Student lens (per-student profiles) IS the core product motion** — the case study explicitly says this. Teachers need to SEE a student's profile, not just have the system silently use it. The student lens viewer needs its own sidebar item.

---

## Iteration 1: What the Ontology Already Tells Us

The `ontology/education/` directory has 6 domains with 40+ nodes:

| Domain | Nodes | Primary User |
|--------|-------|-------------|
| `admin.yaml` | LV-ADM-001 through LV-ADM-003 | Coordinator/Head |
| `curriculum.yaml` | LV-CUR-001 through LV-CUR-007 | Teacher (planning) |
| `teacher.yaml` | LV-TCH-001 through LV-TCH-006 | Teacher (execution) |
| `student.yaml` | LV-STU-001 through LV-STU-007 | Teacher (per-student) |
| `assessment.yaml` | LV-ASS-001 through LV-ASS-005 | Teacher (portfolio) |
| `parent.yaml` | LV-PAR-001 through LV-PAR-003 | Teacher (communication) |

These cluster naturally into sidebar items by workflow, not by ontology domain.

---

## Iteration 2: Teacher Use Cases → Sidebar Mapping

From the Claudia sync (case-studies/04-still-i-rise/context/teacher-use-cases.md):

| Use Case | What Teacher Does | Sidebar Item |
|----------|------------------|-------------|
| UC1: Per-Student Lens | View student profile, get differentiated content | **Students** |
| UC2: Tiered Intervention | Check RTI tier, escalation gates | **Students** |
| UC3: Help Artifacts | Generate checklist + timer for specific student | **Prepare** |
| UC4: Content Differentiation | 3-level lesson (foundational/on-track/extended) | **Prepare** |
| UC5: Social-Emotional | Seating/grouping with conflict awareness | **Students** (grouping) |
| UC6: Weekly Routines | Track conjugation errors, generate targeted practice | **Plan** |
| UC7: Parent Recommendations | Draft parent-safe messages, no AI attribution | **Parents** |
| UC8: Student AI Exposure | Structured tasks, not direct AI interaction | **Students** (future) |

The original 4-item sidebar loses UC1, UC2, UC5 (all student-lens work) and UC7 (parent communication) — they have nowhere natural to live.

---

## Iteration 3: Admin vs Teacher Separation

From ADMIN_GUIDE.md and the ontology admin domain:

**Admins never need**: Observation capture, student lens, content differentiation, parent messages
**Teachers never need**: Programme of Inquiry map, accreditation bundles, staffing/capacity

Mixing these creates noise. The app must detect role.

---

## Iteration 4: The Refined Sidebar (Role-Gated)

### Teacher Sidebar (7 items + 3 utility)

```
┌── Sidebar (200px) ──────┐
│                          │
│  [LV mark]               │
│                          │
│  📋 Plan                 │  ← Curriculum navigator + weekly routines
│  ✏️ Prepare              │  ← Activity generator, 3-level packs, help artifacts
│  👁️ Observe              │  ← Speech-to-text capture (<30s per note)
│  👤 Students             │  ← Per-student lens, RTI tiers, grouping
│  📊 Assess              │  ← Rubrics, portfolios, CEFR gap detection
│  💬 Ask                  │  ← Free-form question (fallback)
│  👨‍👩‍👧 Parents             │  ← Recommendation drafts (AI-opaque)
│                          │
│  ──────────────────      │
│  ❤️ Health               │  ← Doctor
│  🔒 Privacy              │  ← Data transparency
│  ⚙ Settings             │  ← Model, config
│  💭 Reflect              │  ← Private notes, revision proposals
└──────────────────────────┘
```

**Why 7, not 4:**
- **Observe** is separated from Assess because observation is CAPTURE (fast, in-the-moment, <30 seconds) while Assess is DESIGN (rubrics, portfolio review, thoughtful). Different cognitive modes.
- **Students** is separated because the student lens is THE core product motion. Teachers need to SEE a student, understand their profile, propose tier changes. It's not a sub-feature of assessment.
- **Parents** is separated because parent communication has its own governance rule (zero AI attribution) and its own workflow (draft → review → send). It doesn't belong inside any other view.
- **Ask** stays because teachers have questions that don't fit workflows: "How do I teach articles to mixed-level G3?" — routes through reasoning engine.

**Reflect** moves to utility bar because it's meta-work (private journaling about teaching practice) not classroom-facing work. Teachers journal at the end of the day, not during instruction.

---

### Admin Sidebar (4 items + 3 utility)

```
┌── Sidebar (200px) ──────┐
│                          │
│  [LV mark]               │
│                          │
│  🗺️ Programme            │  ← Full K-5 PoI map, unit status
│  📦 Evidence             │  ← Accreditation bundle packaging
│  👥 Capacity             │  ← Staffing assessment, coverage gaps
│  📊 Trends              │  ← School-wide CEFR, RTI distribution (anonymized)
│                          │
│  ──────────────────      │
│  ❤️ Health               │
│  🔒 Privacy              │
│  ⚙ Settings             │
└──────────────────────────┘
```

---

### Student Surface (Future, Separate — NOT Phase 1-3)

```
┌── Simple view ───────────┐
│                           │
│  📝 My Tasks              │  ← Checklist + timer (teacher-assigned)
│  📖 Practice              │  ← Targeted exercises from lens
│  🎨 Portfolio             │  ← View own work + growth
│                           │
└───────────────────────────┘
```

No sidebar complexity. No AI chat. No settings. Teacher assigns, student sees tasks. Period.

---

## Iteration 5: Validating Against Real Workflows

**Monday morning (teacher arrives):**
1. Opens app → **Plan** → sees this week's units, CEFR targets, weekly routines
2. Clicks into Grade 3 "La Famiglia" → sees materials needed, last year's notes
3. Switches to **Prepare** → generates 3-level activity pack for today's lesson
4. Prints foundational tier (for 3 students who need visual scaffolds)

**During class (10am):**
5. Student Marco self-corrects passato prossimo → teacher taps **Observe**
6. Speech-to-text: "Marco self-corrected passato prossimo, used essere correctly in context" → tagged to Marco, 15 seconds total
7. Student Nora can't start writing → teacher had already prepared a checklist artifact in **Prepare**

**After class (11:30am):**
8. Opens **Students** → views Nora's profile → sees RTI Tier 2, consistent non-initiation
9. System proposes: "Consider Tier 2 → Tier 3 escalation (4 weeks sustained non-initiation)" → teacher reviews, defers decision for now
10. Opens Marco's profile → sees 3 recent observations, all positive → CEFR A1→A2 progression visible

**End of day (3pm):**
11. Opens **Parents** → drafts message for Nora's parents: "A creative quiet workspace at home would help Nora start tasks more independently" → reviews, strips any AI language, sends through normal channel
12. Opens **Reflect** (utility bar) → notes: "The checklist artifact worked for Nora today — she completed 3/4 tasks. Adding movement break earlier next time."

**This workflow validates:** Plan, Prepare, Observe, Students, Parents, and Reflect all got used in a single day. Assess was NOT needed today (no portfolio review or rubric design scheduled), but it's there for assessment-heavy weeks. Ask wasn't needed because the teacher knew what she was doing — but it's there for "how do I handle this?" moments.

---

## API Endpoints (Updated for Three-Tier)

### Teacher endpoints:
```
GET  /api/curriculum/overview
GET  /api/curriculum/grade/<grade>
GET  /api/curriculum/unit/<unit_id>
POST /api/prepare/activity
POST /api/prepare/help-artifact         # Checklist + timer for specific student
POST /api/observe/capture               # Speech-to-text → structured note
GET  /api/students                      # Class roster with lens summaries
GET  /api/students/<student_id>/lens    # Full student lens
POST /api/students/<student_id>/rti     # Confirm/defer tier change
GET  /api/students/grouping/<unit_id>   # Suggested groupings
GET  /api/assess/rubric/<unit_id>
POST /api/assess/portfolio-entry
GET  /api/assess/gaps/<student_id>      # What's next for this student
POST /api/parents/recommendation        # Draft parent message
POST /api/query                         # Free-form Ask
POST /api/reflect/note                  # Private journal entry
```

### Admin endpoints:
```
GET  /api/admin/programme               # Full PoI map
POST /api/admin/evidence-bundle         # Generate accreditation bundle
GET  /api/admin/capacity                # Staffing report
GET  /api/admin/trends                  # Anonymized school-wide data
```

### Shared:
```
GET  /api/health                        # Doctor
GET  /api/publication/status            # Readiness audit
```

---

## Key Design Decisions from This Iteration

1. **Observe is PRIMARY, not secondary.** It's the flywheel: observations feed student lenses, lenses feed differentiation, differentiation feeds better instruction, better instruction generates more observations. If Observe is hard to reach, the flywheel breaks.

2. **Students is a viewer AND a decision gate.** Teachers don't just read profiles — they make RTI decisions FROM this view. System proposes, teacher confirms. This is the "teacher decision gate" pattern from the architecture docs.

3. **Parents is isolated for governance.** The zero-AI-attribution rule is strict. Parent messages are the ONE output that reaches people outside the school. Giving it its own view makes the governance boundary visible in the UI.

4. **Reflect is quiet.** Teachers don't journal during class. It's end-of-day work. Utility bar is appropriate.

5. **Admin is a SEPARATE login, not tabs.** Admins and teachers have fundamentally different mental models. A teacher accidentally seeing "Capacity & Staffing" is confused. An admin accidentally editing a student observation is dangerous.

6. **Student surface is NOT built now.** Students interact with teacher-prepared artifacts (printed checklists, assigned exercises). The app serves teachers. Student-facing features are Phase 4+ after teacher adoption is proven.

---

## What This Changes in the Build Spec

| Original | Updated |
|----------|---------|
| 4-item sidebar (Plan, Prepare, Assess, Reflect) | 7-item teacher sidebar + role detection |
| Single user type | Three tiers (admin, teacher, student-future) |
| No observation capture in sidebar | Observe is 3rd sidebar item |
| Student lens invisible | Students is 4th sidebar item |
| Parent comms buried | Parents is 7th sidebar item, governance-isolated |
| Reflect in main sidebar | Reflect moves to utility bar |
| No role detection | First-run asks: "I am a coordinator / I am a teacher" |
| Generic ask-first | Ask is 6th item (fallback), not the default view |

The Phase 2 build should implement the teacher tier first (7+4 items), with admin tier as a Phase 3 addition (the data it needs — school-wide trends — requires enough teacher observations to be meaningful).
