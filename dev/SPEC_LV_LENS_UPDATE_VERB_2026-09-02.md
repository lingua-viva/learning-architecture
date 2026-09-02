# SPEC: `lv lens-update` — CLI + API Verb for Document-to-Lens Updates

**Date**: 2026-09-02
**Status**: READY TO BUILD
**Deadline**: before LV demo Thu Sep 4
**Contract**: `dev/SPEC_LV_FOLDER_TO_LENS_2026-09-02.md` (pipeline invariants)

## What This Is

A single verb — `lv lens-update` on CLI, `POST /api/lens/update` on API —
that takes local documents and updates student lenses through the governed
5-stage pipeline. The same verb shape ports to Trop (`trop lens-update`)
and MC (`mc lens-update`) later.

**Everything behind the verb already exists and is tested.** This is wiring,
not new pipeline work.

## The Verb

### CLI

```
lv lens-update FILE [FILE...] [--preview-only] [--student STUDENT_ID] [--json]
```

| Flag | Default | Meaning |
|---|---|---|
| `FILE` | required | One or more document paths (PDF, DOCX, XLSX, CSV, TXT) |
| `--preview-only` | false | Show what would change, don't write |
| `--student` | auto-detect | Target a specific student (skip matching) |
| `--json` | false | Machine-readable output |

### API

```
POST /api/lens/update
Content-Type: multipart/form-data
Body: file=<upload>, preview_only=true|false
```

Returns the same shape as the existing `/api/students/import-document` but
combines steps 1+2: preview is the response, apply happens if
`preview_only=false` AND the response includes `"needs_confirmation": true`
fields that require a follow-up `POST /api/lens/update/confirm`.

**Important**: the existing two-step flow (`import-document` + `apply-extractions`)
stays. The new verb is a PARALLEL entry point, not a replacement. Don't break
the web UI.

## Flow

```
lv lens-update report_card.pdf
    │
    ├─ 1. Read file bytes + detect extension
    ├─ 2. extract_plain_text(bytes, ext)                    [extract.py]
    ├─ 3. classify_document_type(text, filename)             [extract.py]
    │     └─ class_list → "Use roster import instead" + exit 0
    │     └─ curriculum/other → "Not a student file" + exit 0
    ├─ 4. Load roster from StudentLensStore.list_lenses()
    ├─ 5. match_document_to_students(text, filename, roster) [lens_match.py]
    │     └─ no matches → "No matching students" + exit 0
    ├─ 6. extract_for_lens_update(bytes, type, matched, store, engine)
    │     └─ THE 5-STAGE PIPELINE (already tested, 192 contract tests)
    ├─ 7. save_extraction_log(results, filename)             [lens_extract.py]
    ├─ 8. PRINT PREVIEW
    │     └─ Per student: display_name, field count, fields with values,
    │        unresolved questions, needs_confirmation fields
    │     └─ If --preview-only: exit 0 here
    ├─ 9. CONFIRM (CLI: y/n prompt; API: separate confirm endpoint)
    ├─ 10. apply_extractions_to_lenses(results, store)       [lens_extract.py]
    └─ 11. PRINT SUMMARY
          └─ Per student: written count, review_required count, notes
```

## Existing Functions to Call (DO NOT rewrite)

| Step | Function | File | Line |
|---|---|---|---|
| Text extraction | `extract_plain_text(content, ext)` | `docpipe/extract.py` | — |
| Doc classification | `classify_document_type(text, filename)` | `docpipe/extract.py` | — |
| Student matching | `match_document_to_students(text, filename, roster)` | `docpipe/lens_match.py` | — |
| Pipeline | `extract_for_lens_update(bytes, type, matched, store, engine)` | `docpipe/lens_extract.py` | :875 |
| Save log | `save_extraction_log(results, filename)` | `docpipe/lens_extract.py` | :1295 |
| Load log | `load_extraction_log(log_path)` | `docpipe/lens_extract.py` | :1342 |
| Apply | `apply_extractions_to_lenses(results, store, confirmed)` | `docpipe/lens_extract.py` | :1387 |
| Write lens | `write_student_lens(result, hint, store)` | `student_lens_writer.py` | :20 |
| Reasoning | `ReasoningEngine()` | `reasoning.py` | — |
| Lens store | `StudentLensStore()` | `education/student_lens.py` | — |

## CLI Implementation Plan

### 1. Parser (in `cli.py:build_parser()`, after line 816)

```python
lens = sub.add_parser("lens-update", help="Update student lenses from local documents")
lens.add_argument("files", nargs="+", metavar="FILE", help="Document paths (PDF, DOCX, XLSX, CSV, TXT)")
lens.add_argument("--preview-only", action="store_true", help="Show preview without writing")
lens.add_argument("--student", default=None, help="Target student ID (skip auto-matching)")
lens.add_argument("--json", action="store_true")
```

### 2. Dispatch (in `cli.py:main()`, before `return 1`)

```python
if args.command == "lens-update":
    return asyncio.run(_lens_update(args))
```

### 3. Handler function (`_lens_update`)

New function in `cli.py`. Approximately 80-100 lines. The logic is:

```python
async def _lens_update(args) -> int:
    # 1. Validate files exist
    # 2. For each file:
    #    a. Read bytes + detect ext
    #    b. extract_plain_text
    #    c. classify_document_type — bail on class_list/curriculum/other
    #    d. Load roster (once, cached across files)
    #    e. match_document_to_students
    #    f. extract_for_lens_update (async — needs ReasoningEngine)
    #    g. save_extraction_log
    #    h. Print preview (per student: fields, values, confidence, questions)
    # 3. If --preview-only: exit 0
    # 4. Prompt "Update N student lens(es)? [y/N]"
    # 5. apply_extractions_to_lenses
    # 6. Print summary
    # 7. Return 0
```

### 4. API endpoint (in `routers/document_import.py`)

Add a new route alongside the existing ones:

```python
@router.post("/lens-update")
async def lens_update(request: Request):
    # Same logic as import_document but:
    # - Accepts preview_only parameter
    # - If not preview_only: applies immediately for confirmed fields
    # - Returns combined preview+result shape
```

**Alternative**: skip the new API route for now. The web UI already works with
the existing two-step flow. The verb is primarily a CLI convenience for the
demo. Add the API route later if needed.

## Output Format (CLI)

### Preview

```
lens-update: report_card_term2.pdf
  Type: student_report
  Students matched: 3

  ┌─ Boyce Aiken (s-boyce)
  │  Fields: 7
  │  ✓ cefr_snapshot.reading: A2 (verified, 0.99)
  │  ? learning_and_cognition: "strong reading comprehension" (needs_confirmation, 0.72)
  │  ? social_skills: "works well in small groups" (needs_confirmation, 0.72)
  │  ...
  │  Unresolved: 1 question
  │    "Sentence 47 could not be classified."
  │
  ├─ Miro Rossi (s-miro)
  │  Fields: 5
  │  ...
  │
  └─ Luca Rossi (s-luca)
     Fields: 6
     ...

Update 3 student lens(es)? [y/N]
```

### After apply

```
Updated 3 student lens(es):
  Boyce Aiken: 5 fields written, 2 need review
  Miro Rossi: 3 fields written, 2 need review
  Luca Rossi: 4 fields written, 2 need review

Extraction log: ~/.lingua-viva/imports/20260902T143000Z_report_card_term2.ndjson
```

### JSON output (`--json`)

```json
{
  "file": "report_card_term2.pdf",
  "document_type": "student_report",
  "students": [
    {
      "student_id": "s-boyce",
      "display_name": "Boyce Aiken",
      "fields": [...],
      "unresolved_questions": [...],
      "written_count": 5,
      "review_required": 2
    }
  ],
  "extraction_log": "~/.lingua-viva/imports/..."
}
```

## Acceptance Criteria

1. `lv lens-update tests/fixtures/sample_report_card.pdf` — runs the full
   pipeline through to preview with no errors.
2. `lv lens-update --preview-only FILE` — shows preview, exits 0, writes
   nothing to the lens store.
3. `lv lens-update FILE` with `y` confirmation — writes fields, summary
   matches what preview showed.
4. `lv lens-update nonexistent.pdf` — clean error, exit 1.
5. `lv lens-update class_list.csv` — tells user to use roster import, exit 0.
6. Multiple files: `lv lens-update a.pdf b.pdf` — processes both, single
   confirmation for all.
7. `--student s-boyce` — skips matching, processes only for that student.
8. `--json` — machine-readable output for all of the above.
9. All 7 governance invariants hold (tested by existing 192 contract tests).
10. Full suite stays green (>=2917 tests).

## What NOT to Build

- **Don't rewrite the pipeline.** Call the existing functions.
- **Don't add a new router module.** Add the endpoint to `document_import.py`
  or skip the API route entirely for now.
- **Don't change the web UI.** The existing two-step flow works.
- **Don't add folder scanning.** Single files only. Folder scanning is a
  later feature (`--from PATH` in the cross-repo recipe).
- **Don't add progress bars or streaming.** The LLM call takes 15-112s on
  CPU hardware — that's the UX caveat noted in the status report. A spinner
  or progress indicator is nice-to-have, not P0.
- **Don't change the lens writer.** `write_student_lens` works and is tested.

## Test Plan

### New tests to add

```python
# tests/test_cli_lens_update.py

def test_lens_update_preview_only_writes_nothing(tmp_path):
    """--preview-only must not modify the lens store."""

def test_lens_update_nonexistent_file_exits_1():
    """Clean error for missing file."""

def test_lens_update_class_list_exits_0():
    """Roster documents are politely refused."""

def test_lens_update_single_file_e2e(tmp_path, stub_engine):
    """Full flow: read → extract → preview → apply → verify lens updated."""

def test_lens_update_json_output(tmp_path, stub_engine):
    """--json produces valid JSON with required keys."""

def test_lens_update_student_filter(tmp_path, stub_engine):
    """--student restricts processing to one student."""
```

### Existing tests (must not break)

```bash
python3 -m pytest tests/test_lens_from_report_cards.py \
  tests/test_name_match_fold.py \
  tests/test_batch_classify_provenance.py \
  tests/golden/test_golden_document_to_lens.py -v
# 192 passed, 6 xfailed

python3 -m pytest tests/ -q
# 2917+ passed
```

## Files to Modify

| File | Change | Lines |
|---|---|---|
| `src/lingua_viva/cli.py` | Add parser + dispatch + handler | ~100 new lines |
| `tests/test_cli_lens_update.py` | New test file | ~120 lines |
| `src/lingua_viva/routers/document_import.py` | Optional: add `/api/lens/update` | ~40 lines |

## Dependencies

- `extract_plain_text` — already in extract.py
- `classify_document_type` — already in extract.py
- `match_document_to_students` — already in lens_match.py
- `extract_for_lens_update` — already in lens_extract.py, 192 contract tests
- `save_extraction_log` / `load_extraction_log` — already in lens_extract.py
- `apply_extractions_to_lenses` — already in lens_extract.py
- `write_student_lens` — already in student_lens_writer.py
- `ReasoningEngine` — already in reasoning.py
- `StudentLensStore` — already in education/student_lens.py

Zero new dependencies. Zero new pipeline code. This is a CLI wrapper.

## Port Shape (for Trop + MC later)

The verb signature is product-neutral:

```
<product> lens-update FILE [FILE...] [--preview-only] [--entity ENTITY_ID] [--json]
```

What changes per product:
- `--student` → `--customer` / `--employee` / `--entity`
- `classify_document_type` → product-specific classifier
- `match_document_to_students` → product-specific entity matcher
- `extract_for_lens_update` → product-specific extraction config
- `write_student_lens` → product-specific lens writer
- `StudentLensStore` → product-specific entity store

The handler function structure is identical. The spec + prompt pair for each
port starts from this one.
