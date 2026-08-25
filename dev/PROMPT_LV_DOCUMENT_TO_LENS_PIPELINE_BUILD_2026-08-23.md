# BUILD PROMPT: Document-to-Lens Pipeline

> Spec: `dev/SPEC_LV_DOCUMENT_TO_LENS_PIPELINE_2026-08-23.md`
> Read the spec FIRST. Every requirement is numbered R1-R8.

## Context

You are building the document-to-lens pipeline for Lingua Viva. Teachers have
student lenses (created from roster import). They need to UPDATE those lenses
with data from report cards, progress reports, and assessment documents.

**This is not greenfield.** Significant infrastructure already exists:

```
src/lingua_viva/extraction_engine.py    — PDF/text chunking, extraction prompts, verification
src/lingua_viva/data_in_contracts.py    — Frozen field contracts, STUDENT_LENS_FIELDS
src/lingua_viva/student_lens_writer.py  — write_student_lens() → lens store
src/education/document_parser.py        — PDF section chunking, table extraction
src/education/student_lens.py           — StudentLensStore (the target)
src/lingua_viva/docpipe/identity.py     — identity.resolve() for name matching
src/lingua_viva/docpipe/extract.py      — Document extraction (name detection etc)
src/education/ethos.py                  — Ethos trait taxonomy + match_traits() keyword routing
src/education/observation_capture.py    — Category suggestion logic for support profiles
```

**CRITICAL: Read the spec's R4b (Routing Logic) section.** The routing problem
is the hardest part. You are NOT building routing from scratch — `ethos.py`
has `match_traits()` with signal_keywords for ethos evidence routing, and
`observation_capture.py` has category suggestion for support profiles. Wire them.

Output to lens fields must be **keywords and summaries**, never full sentences.
Example: "demonstrates strong reading comprehension and can retell stories" →
`academic_strengths`: `"reading comprehension, story retelling"`.
The LLM's job (when used) is to CONDENSE, not to ELABORATE.

**Read ALL of these files before writing any code.** The previous build failed
because code was rebuilt instead of wired. DO NOT REBUILD what exists.

## Build Order (follow exactly)

### Step 1: Document Classifier

File: `src/lingua_viva/docpipe/extract.py` (modify existing)

Add a function `classify_document_type(text: str, filename: str) -> str` that returns
one of: `class_list`, `student_report`, `assessment_summary`, `support_document`,
`curriculum`, `other`.

Heuristics (no LLM):
- Filename patterns: "report" → student_report, "assessment" → assessment_summary,
  "IEP"/"support" → support_document, "roster"/"class list" → class_list
- Content markers:
  - IB report card: "Learner Profile", "CEFR", "indicator", scale words
    (Beginning/Developing/Accomplished/Exemplary) → student_report
  - Student column tables (existing detection logic) → class_list
  - Curriculum terms without student names → curriculum
- Default: `other`

Modify the import flow so that when a non-class-list document is detected, it
returns `document_type` in the extraction result instead of forcing name detection.

### Step 2: Student Matcher

File: `src/lingua_viva/docpipe/extract.py` or new `src/lingua_viva/docpipe/lens_match.py`

Function: `match_document_to_students(text: str, filename: str, roster: list[dict]) -> list[dict]`

1. Check filename for student names (e.g., "Abigail_Chang_..." → "Abigail Chang")
2. Check document header/first 500 chars for roster name matches
3. Use `identity.resolve()` against the roster
4. Return `[{"student_id": ..., "display_name": ..., "match_source": "filename"|"content", "confidence": float}]`
5. For single-student documents, return one match. For multi-student, return all.

### Step 3: Extraction Pipeline

Wire the existing `extraction_engine.py` into a new function:

File: `src/lingua_viva/docpipe/lens_extract.py` (new)

```python
async def extract_for_lens_update(
    document_bytes: bytes,
    document_type: str,
    matched_students: list[dict],
    lens_store: StudentLensStore,
    engine: ReasoningEngine | None = None,
) -> dict[str, ExtractionResult]:
    """Extract lens-update data from a student document.

    Returns {student_id: ExtractionResult} for each matched student.
    """
```

Pipeline:
1. Parse document into chunks (existing `document_parser.py`)
2. For each chunk, apply heuristic extractors:
   - CEFR regex: `r'\b(A1|A2|B1|B2|C1|C2)\b'` with dimension context
   - Grade scale: Beginning/Developing/Accomplished/Exemplary
   - Numeric scores with subject context
   - Known IB Learner Profile attributes (the official 10)
   - ATL skills
3. For ambiguous chunks, if engine available, call with tight extraction prompt
   - Use `local_only=True`, `think=False` for qwen3 models
   - Input: chunk text + target field schema
   - Output: JSON with `{field_path: value, confidence: float}`
4. Map all extractions to `STUDENT_LENS_FIELDS` from `data_in_contracts.py`
5. Anything that doesn't map → `open_questions`
6. Apply safety rules: trauma_flag NEVER auto-set, RED content → restricted

### Step 4: Persistence

File: `src/lingua_viva/docpipe/lens_extract.py` (same file)

Before writing to lenses, save extraction results:

```python
def save_extraction_log(
    results: dict[str, ExtractionResult],
    source_filename: str,
    state_home: Path = Path.home() / ".lingua-viva",
) -> Path:
    """Save extraction results as NDJSON. Returns the log path."""
```

Location: `~/.lingua-viva/imports/{timestamp}_{filename}.ndjson`
Format: one JSON line per extracted field, with source chunk reference.

### Step 5: Batch Lens Writer

Wire existing `student_lens_writer.py`:

```python
async def apply_extractions_to_lenses(
    results: dict[str, ExtractionResult],
    lens_store: StudentLensStore,
) -> dict[str, dict]:
    """Write all extractions to their target lenses. Returns per-student summary."""
```

Use `write_student_lens()` from `student_lens_writer.py`. Respect all its
safety rules (trauma_flag, source_ref_ids, confidence tracking).

### Step 6: API Routes

File: `src/web.py` (add routes)

```
POST /api/students/import-document
  - Accepts file upload (same as roster import)
  - Calls classify → match → extract → persist
  - Returns JSON: {document_type, matched_students, extractions_preview}

POST /api/students/apply-extractions
  - Accepts {extraction_log_path, confirmed_students: [student_id, ...]}
  - Loads saved extraction, writes to lenses
  - Returns {updated_students: [{student_id, fields_written, ...}]}
```

Two-step: extract+preview first, then teacher confirms and applies.

### Step 7: UI

File: `static/index.html`

Add a second import section on the Students page, below "Import your roster":

**"Update lenses from documents"**

- File chooser (reuse existing upload pattern)
- After upload: show classification result + matched students
- Expandable per-student detail: what fields will be updated, source text
- "Update all lenses" / "Cancel" buttons
- Progress indicator for long extractions

### Step 8: Tests

File: `tests/test_document_to_lens.py` (new)

Required tests:
1. `test_classify_report_card_not_as_roster` — Claudia's PDF must classify as `student_report`
2. `test_ib_terminology_not_detected_as_students` — "Learner Profile", "Cordiali Saluti" etc → 0 false positives
3. `test_single_student_matched_from_filename` — "Abigail_Chang_..." matches Abigail's lens
4. `test_cefr_extraction_from_report_card` — A1/A2/B1 levels extracted correctly
5. `test_extraction_saved_before_lens_write` — NDJSON log exists before write
6. `test_trauma_flag_never_auto_set` — hard rule, even if document mentions trauma
7. `test_red_safeguarding_routed_to_restricted` — never to lens
8. `test_lens_update_persists_after_app_restart` — data in ~/.lingua-viva survives
9. `test_multi_student_document_partitions_correctly` — per-student extraction
10. `test_gauntlet_still_passes` — existing tests not broken

Create a synthetic report card fixture at:
`tests/fixtures/docpipe/synthetic_report_card_abigail.pdf`
(or `.txt` if PDF generation is complex — the extraction works on text too)

## Critical Rules

1. **Read before writing.** Every file listed in "what exists" must be read
   before any code is written. Understand the interfaces.
2. **Wire, don't rebuild.** The extraction engine, contracts, writer, and parser
   exist. Connect them to a UI-reachable path.
3. **Local model only.** All LLM calls use `local_only=True`. The model is
   qwen3:8b via Ollama on localhost:11434.
4. **Heuristics first, LLM second.** Regex/pattern matching for CEFR levels,
   grade scales, IB terminology. LLM only for ambiguous natural language.
5. **Two-step flow.** Extract → preview → teacher confirms → write. Never auto-write.
6. **Persist before write.** Extraction log saved BEFORE any lens modification.
7. **Safety is non-negotiable.** trauma_flag, RED safeguarding, name-in-logs rules.
8. **Run tests after every step.** `python3 -m pytest tests/ -q` must pass.
9. **The gauntlet must pass.** `python3 -m pytest tests/gauntlet/ -q` (phases 1, 2, 6).

## What NOT to Build

- New lenses from documents (roster-only for creation)
- WebSocket streaming progress
- Google Drive integration for this flow (file upload only for now)
- School-wide analytics
- Automatic re-extraction
- Any external API calls

## Acceptance Test

After the build, this window will run:

```bash
# 1. Existing tests still pass
python3 -m pytest tests/ -q

# 2. New document-to-lens tests pass
python3 -m pytest tests/test_document_to_lens.py -v

# 3. Gauntlet phases 1, 2, 6 pass
python3 -m pytest tests/gauntlet/test_01_import_detection.py tests/gauntlet/test_02_student_lens.py tests/gauntlet/test_06_privacy.py -v

# 4. Manual: upload Claudia's report card PDF through the UI
# 5. Manual: verify Abigail's lens has real data after import
```
