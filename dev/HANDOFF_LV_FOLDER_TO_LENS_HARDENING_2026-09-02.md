# HANDOFF - LV Folder-to-Lens Hardening

Date: 2026-09-02
Repo: `/home/mical/learning-architecture`

## Result

Locked the multi-student no-position refusal behavior for the document-to-lens
pipeline.

`src/lingua_viva/docpipe/lens_extract.py` already had the correct production
behavior at handoff time:

- single matched student -> whole document section;
- multiple matched students with locatable names -> position-based sections;
- multiple matched students with no locatable names -> empty sections for each
  student, so extraction surfaces "No content found" instead of copying the
  whole document into every student's lens.

This build added the missing regression test:

- `tests/test_document_to_lens.py::test_multi_student_without_name_positions_refuses_duplication`

## Why It Matters

This closes the trust boundary identified in the shared folder-to-lens plan:
if upstream identity matching says multiple students are candidates but the
section splitter cannot locate their names in the source text, the safe answer
is refusal, not duplicated full-text import.

This aligns LV with Trop's `cannot_split` rule and keeps LV usable as the
reference implementation for Trop Phase B.

## Verification

Commands run:

```bash
pytest tests/test_document_to_lens.py::test_multi_student_without_name_positions_refuses_duplication tests/test_document_to_lens.py::test_multi_student_document_partitions_correctly -q
```

Result: `2 passed in 0.22s`

```bash
pytest tests/test_document_to_lens.py tests/test_batch_classify_provenance.py -q
```

Result: `37 passed in 0.77s`

```bash
pytest tests/golden/test_golden_document_to_lens.py::TestSectionSplitting::test_section_split_golden -q
```

Result: `1 passed in 0.20s`

## Remaining LV Risk

No new production risk found in this narrow pass. The broader parser/span layer
still deserves a future extraction into a shared core only after Trop has passed
Phase B with the same invariants.
