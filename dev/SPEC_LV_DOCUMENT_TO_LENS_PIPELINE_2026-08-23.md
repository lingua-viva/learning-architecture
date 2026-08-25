# SPEC: Document-to-Lens Pipeline

> Date: 2026-08-23
> Author: Mical (requirements), Claude (spec)
> Status: READY TO BUILD
> Priority: P0 — core feature, blocks daily teacher use

## Problem

Teachers create student lenses from roster imports (works today). But lenses
are empty shells — no CEFR data, no support profile, no assessment history.
The only way to fill them is manual observation-by-observation entry.

Teachers have rich documents (report cards, progress reports, assessment
summaries, IEP notes) that contain exactly the information lenses need. There
is no way to get that information into lenses automatically.

Previous builds created extraction infrastructure (`extraction_engine.py`,
`data_in_contracts.py`, `student_lens_writer.py`, `document_parser.py`) with
passing eval tests — but zero UI reachability. The code exists but teachers
can't use it.

## What Exists (DO NOT REBUILD)

These files are already built and tested. Wire them, don't replace them:

| File | What it does | Lines |
|---|---|---|
| `src/lingua_viva/extraction_engine.py` | PDF/text chunking, extraction prompts, verification pass | 457 |
| `src/lingua_viva/data_in_contracts.py` | Frozen field contracts, `STUDENT_LENS_FIELDS`, `SUPPORT_PROFILE_CATEGORIES` | ~200 |
| `src/lingua_viva/student_lens_writer.py` | `write_student_lens()` — writes ExtractionResult to lens store | 223 |
| `src/education/document_parser.py` | PDF section chunking, table extraction, PII redaction | 249 |
| `src/education/student_lens.py` | Full StudentLensStore — the target data model | ~1200 |

## Requirements

### R1: Document Classification Before Name Detection

When a file is imported on the Students page, BEFORE scanning for names:

1. Classify the document type: `class_list` | `student_report` | `assessment_summary` | `support_document` | `curriculum` | `other`
2. If `class_list` → current roster-import flow (unchanged)
3. If `student_report` or `assessment_summary` or `support_document` → document-to-lens flow (this spec)
4. If `curriculum` or `other` → tell the teacher plainly: "This doesn't look like a student file. It looks like [type]. To import a class list, use a spreadsheet with student names."

Classification heuristics (no LLM needed):
- Filename contains "report", "progress", "assessment", "IEP", "support" → student document
- Content contains IB report card markers: "Learner Profile", "CEFR", "indicator", "Beginning/Developing/Accomplished/Exemplary" → student report
- Content contains multiple student-column-like tables → class list
- Fallback: ask the teacher "Is this a class list or a student document?"

### R2: Student Matching Against Existing Roster

For student documents, match against the EXISTING roster (lenses already created):

1. Extract candidate student names from the document
2. Match each against known lens display_names using `identity.resolve()`
3. For a single-student document (report card): the student's name is typically in the filename or header. Match it. Confirm with teacher: "This looks like a report for **Abigail Chang**. Update her lens?"
4. For multi-student documents: show all matched students, let teacher confirm/deselect
5. NEVER create new lenses from this flow — only update existing ones

### R3: Line-by-Line Extraction with Heuristic Rules

For each matched student, process the document:

1. **Chunk** the document into sections (use existing `document_parser.py`)
2. **For each chunk**, apply heuristic rules FIRST (no LLM):
   - CEFR levels: regex for A1/A2/B1/B2/C1/C2 with dimension context (reading/writing/speaking/listening)
   - Grade descriptors: Beginning/Developing/Accomplished/Exemplary → map to ordinal scale
   - Assessment scores: numeric patterns with subject context
   - Attendance: absent/present counts, percentages
   - Known IB terminology: ATL skills, Learner Profile attributes → map to specific lens fields
3. **For ambiguous content**, use local model (qwen3:8b) with a tight extraction prompt:
   - Input: the chunk + the lens field schema + what we've already extracted
   - Output: structured JSON mapping chunk content to lens fields
   - `think=false` for qwen3 (avoid hidden token budget drain)
4. **Confidence scoring**: heuristic matches = `verified` (0.95+), LLM matches = `needs_confirmation` (0.6-0.8)

### R4: Internal Ontology — Lens Field Mapping

The extraction must know EXACTLY which fields exist on a lens and map to them.
Use `data_in_contracts.py`'s frozen contracts as the ontology:

```
STUDENT_LENS_FIELDS:
  - cefr_snapshot.{reading,writing,speaking,listening}
  - cefr_trajectory_30d
  - rti_current_tier
  - home_languages
  - learning_differences
  - sel_summary
  - support_profile.{9 categories}.{6 buckets}

SUPPORT_PROFILE_CATEGORIES (9 categories × 6 buckets):
  - learning_and_cognition
  - communication_and_language
  - executive_functioning
  - social_skills
  - emotional_regulation
  - physical_sensory_needs
  - attendance_and_engagement
  - advanced_enrichment
  - personal_context

SUPPORT_PROFILE_BUCKETS (per category):
  - needs
  - strengths
  - strategies_worked
  - strategies_not_worked
  - evidence
  - open_questions

ADDITIONAL LENS FIELDS:
  - academic_strengths (list)
  - personal_strengths (list)
  - background (text notes)
  - poi_progression (Programme of Inquiry objectives + phases)

ETHOS EVIDENCE (9 traits from ethos.py seed, school-configurable):
  - self_worth         (value)
  - self_discipline    (value)
  - critical_thinking  (learner_attribute)
  - emotional_intelligence (learner_attribute)
  - self_organization  (learner_attribute)
  - grit               (learner_attribute)
  - social_intelligence (learner_attribute)
  - entrepreneurship   (learner_attribute)
  - integrity          (learner_attribute)

EVIDENCE CATEGORIES (per-category ledger entries with source attribution):
  - Each of the 9 support profile categories has its own evidence list
  - Each ethos trait has its own evidence list
  - Evidence entries have: text, source_ref, confidence, timestamp
```

Every extracted datum must map to exactly one of these fields. If it doesn't
map, it goes into `open_questions` for teacher review. Nothing is discarded
silently.

### R4b: Routing Logic — The Critical Problem

Routing = deciding WHERE a piece of extracted information goes. This is
the difference between useful and garbage. Getting "shows empathy with peers"
into `social_skills.strengths` AND `ethos.social_intelligence` (not into
`emotional_regulation` or `personal_context`).

**The routing system already exists in two places. USE THEM:**

1. **`ethos.py` — `match_traits(text, ethos)`**: word-boundary keyword matching
   against each trait's `signal_keywords`. Returns trait IDs. Already handles
   false positives (e.g., "scared" doesn't match "care"). Use this for ethos
   evidence routing.

2. **`observation_capture.py` — category suggestion logic**: maps observation
   text to support profile categories. Use this for support profile routing.

**Routing rules (heuristic, no LLM):**

For each extracted text snippet:

1. **CEFR data** → `cefr_snapshot.{dimension}` (regex: A1/A2/B1/B2 + context)
2. **Grade scale** (Beginning/Developing/Accomplished/Exemplary) → evidence for
   the subject category + PoI progression phase mapping
3. **Learner Profile attributes** (the official IB 10: Inquirers, Knowledgeable,
   Thinkers, Communicators, Principled, Open-minded, Caring, Risk-takers,
   Balanced, Reflective) → `academic_strengths` + ethos trait match if applicable
4. **ATL skills** (thinking, social, communication, self-management, research)
   → `academic_strengths` + relevant support category
5. **Ethos signal keywords** → `ethos_profile.traits.{trait_id}.evidence`
   via `match_traits()` from `ethos.py`
6. **Support-category text** → route to the correct category using keyword
   overlap with category definitions in `student_lens.py` lines 160-194
7. **Personal/family context** → `personal_context` (RESTRICTED — teacher
   confirmation required, never auto-written)
8. **Attendance data** → `attendance_and_engagement`
9. **Unroutable** → `open_questions` (surfaced to teacher, never discarded)

**Output format — keywords and summaries, NOT full sentences:**

When writing to lens fields, extract and condense:
- "Abigail demonstrates strong reading comprehension and can retell stories
  with key details" → `academic_strengths`: `"reading comprehension, story retelling"`
- "Shows growing empathy when working with peers during group activities" →
  `social_skills.strengths`: `"growing empathy in group work"` +
  `ethos.social_intelligence.evidence`: `"empathy with peers in group activities"`
- "CEFR Speaking: A2 — Can sustain short exchanges" →
  `cefr_snapshot.speaking`: `"A2"`
- "Developing in Environmental Studies" →
  PoI evidence with phase `"developing"` for Environmental Studies objective

**Anti-hallucination rules:**
- NEVER invent data not present in the source text
- NEVER upgrade a CEFR level (if doc says A1, write A1, not "progressing toward A2")
- NEVER interpret absence of data as data ("not mentioned" ≠ "no issues")
- If the LLM is used for ambiguous routing, its output MUST be verified against
  the source chunk — if the chunk doesn't contain the routed content, drop it
- Confidence < 0.6 → `open_questions`, not a field write

### R5: Batch Lens Update

1. Collect all extractions for all matched students
2. Show the teacher a review summary: "Found X pieces of information for Y students"
3. Teacher can expand each student to see what will be written
4. "Update all lenses" button — writes everything in one batch
5. Each written field gets a `source_ref` pointing back to the document + chunk

### R6: Data Persistence Safety

Lens data is sacred. It must survive app updates:

1. Lens SQLite DB lives in `~/.lingua-viva/` (NOT in the repo)
2. Every lens update is append-only with timestamps and source attribution
3. The extraction results (what was found, where, confidence) are saved as
   NDJSON in `~/.lingua-viva/imports/` before any lens write happens
4. If the app is updated/reinstalled, `~/.lingua-viva/` is never touched
5. Import history is queryable: "what was imported for this student and when?"

### R7: UI Integration

Add to the Students page, BELOW the existing roster import:

```
┌─────────────────────────────────────────────────┐
│ Update lenses from documents                     │
│                                                  │
│ Upload a report card, assessment, or progress    │
│ report. The system will extract information and  │
│ update your student lenses.                      │
│                                                  │
│ [Choose File]  [Import from Drive]               │
│                                                  │
│ Processing: ████████░░ 80% (12/15 sections)     │
│ Found information for 3 students:                │
│  ✓ Abigail Chang — 8 fields updated             │
│  ✓ Marco Bianchi — 5 fields updated             │
│  ✓ Nora Rossi — 3 fields updated                │
│                                                  │
│ [Review details]  [Update all lenses]  [Cancel]  │
└─────────────────────────────────────────────────┘
```

### R8: Safety Rules (Non-negotiable)

1. `trauma_flag` is NEVER auto-set from document extraction — hard rule from existing `student_lens_writer.py`
2. RED safeguarding content is detected and routed to `safeguarding/restricted.ndjson`, never to lens
3. No student names in any log, error message, or telemetry
4. Document content stays in `~/.lingua-viva/` — never sent externally
5. All LLM calls use local Ollama only — enforced by `local_only=True`

## Non-Goals (Explicit)

- Creating new lenses from document import (roster-only for creation)
- School-wide analytics across lenses
- Real-time streaming extraction progress via WebSocket
- Teacher competency tracking
- Automatic re-extraction when documents change

## Test Contract

The gauntlet (tests/gauntlet/) must still pass after this build. Additionally:

1. A synthetic report card fixture must round-trip: PDF → extract → match student → update lens → verify lens fields
2. The 75 false-positive name detections from Claudia's test (IB terminology) must be zero
3. `trauma_flag` must never be auto-written in any test scenario
4. Multi-student document must correctly partition information per student
5. Extraction results must be persisted to `~/.lingua-viva/imports/` before lens write

## Build Order

1. Document classifier (R1) — heuristic, no LLM
2. Student matcher against roster (R2) — uses existing `identity.resolve()`
3. Wire existing extraction engine to new flow (R3) — chunk → heuristic → LLM fallback
4. Lens field mapper / ontology (R4) — uses existing `data_in_contracts.py`
5. Batch lens writer (R5) — uses existing `student_lens_writer.py`
6. Persistence layer (R6) — NDJSON import log
7. UI (R7) — Students page, below roster import
8. API routes in `src/web.py` — POST /api/students/import-document, GET /api/students/import-status
9. Tests — synthetic report card fixture, false-positive regression, safety rules

## Success Criteria

Claudia uploads `Abigail_Chang_3_PYP_Progress_Report2025-26Semester_2.pdf`.
The app:
1. Classifies it as `student_report` (not a roster)
2. Matches "Abigail Chang" to her existing lens
3. Extracts CEFR levels, assessment grades, teacher comments, learner profile observations
4. Shows Claudia what it found, organized by lens field
5. Claudia clicks "Update lens" and Abigail's lens now has real data
6. The extraction is saved locally and survives app updates
