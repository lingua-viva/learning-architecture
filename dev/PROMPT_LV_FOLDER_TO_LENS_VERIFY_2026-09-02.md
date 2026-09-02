# Execution Prompt: Verify LV Folder-to-Lens Pipeline

**Purpose**: End-to-end verification that Lingua Viva's document-to-lens pipeline
works correctly. Run this before the demo (Thu Sep 4) and after any pipeline change.

**Contract**: `dev/SPEC_LV_FOLDER_TO_LENS_2026-09-02.md`

---

## Context

You are verifying Lingua Viva's folder-to-lens pipeline — the system that takes
classroom documents (report cards, CSVs, teacher notes) and produces per-student
lenses with grounded, human-confirmable fields.

LV is the reference implementation. If this passes, the pipeline shape is proven
and can be ported to Trop AI and Mission Canvas.

## Environment

```bash
cd ~/learning-architecture
export MC_AGENT=1   # mandatory: agent traffic never trains weights
```

## Step 1: Baseline — existing tests MUST be green

```bash
python3 -m pytest tests/test_lens_from_report_cards.py \
  tests/test_name_match_fold.py \
  tests/test_batch_classify_provenance.py \
  tests/golden/test_golden_document_to_lens.py -v --tb=short
```

**Exit gate**: zero failures. If any fail, STOP — fix before proceeding.

Record: test count, pass count, xfail count, wall time.

## Step 2: Verify the 7 governance invariants

For each invariant, find the code that enforces it and the test that locks it.
Report as a table:

| # | Invariant | Enforced at | Locking test | Verdict |
|---|---|---|---|---|
| 1 | Model routes, never authors | lens_extract.py phrase substring check | ? | PASS/FAIL/CANNOT-TELL |
| 2 | No data > fake data | ? | ? | ? |
| 3 | Ambiguity = question | identity.py queue verdict | ? | ? |
| 4 | Provenance threaded | lens.py _assert_grounded | ? | ? |
| 5 | Import ≠ truth | needs_confirmation status | ? | ? |
| 6 | Sanctioned comparators only | fold_text / normalize_name | test_name_match_fold.py | ? |
| 7 | Refuse > mis-split | lens_extract.py:321 | test_section_split_no_positions_refuses_rather_than_duplicates | ? |

For each: read the code, find the enforcement point, find or write the test.
Verdict is PASS if both exist and the test passes. CANNOT-TELL if enforcement
exists but no locking test. FAIL if neither.

## Step 3: Verify P0 closures

P0-1 (paging), P0-2 (chunk provenance), P0-3 (classify_failed) were closed in
fdbe0de. Verify by reading `tests/test_batch_classify_provenance.py` and
confirming:

- P0-1: a >40 sentence input produces classified results for ALL sentences
- P0-2: every batched field has non-empty `supporting_chunk_ids`
- P0-3: a mocked LLM failure produces `classify_failed` entries, not silence

Report: which specific test functions cover each P0, and their pass/fail status.

## Step 4: Verify split refusal

The no-position multi-student fallback was fixed 2026-09-02. Verify:

```bash
python3 -m pytest tests/test_lens_from_report_cards.py::test_section_split_no_positions_refuses_rather_than_duplicates -v
```

Also verify the code change in `lens_extract.py` — line ~321 should return
empty strings, NOT the full text.

## Step 5: End-to-end surface test (if Ollama is available)

Only if `ollama list` shows a model:

```bash
# Start the app
python3 -m src.web &
WEB_PID=$!
sleep 3

# Health check
curl -s http://localhost:8787/api/health | python3 -m json.tool

# Import a test document through the actual API
# (use test fixtures, not real student data)
curl -s http://localhost:8787/api/import/document \
  -F "file=@tests/fixtures/sample_report_card.pdf" | python3 -m json.tool

# Check extraction results
curl -s http://localhost:8787/api/students | python3 -m json.tool | head -50

kill $WEB_PID
```

If no test fixture exists at that path, note it as NOT-TESTED rather than
creating synthetic data.

## Step 6: Full suite regression

```bash
python3 -m pytest tests/ -q --tb=line
```

Record: total passed, skipped, xfailed, failed, wall time.

**Exit gate**: zero failures. Test count must be >= 2917 (the v0.2.81 baseline).

## Report Format

```
FOLDER-TO-LENS VERIFICATION — Lingua Viva
Date: YYYY-MM-DD
HEAD: <commit hash>
Spec: dev/SPEC_LV_FOLDER_TO_LENS_2026-09-02.md

STEP 1 — Baseline tests
  Contract tests: X/Y passed, Z xfailed, Ws wall time
  Verdict: PASS | FAIL

STEP 2 — Governance invariants
  [table from above]
  Invariants verified: N/7
  Verdict: PASS | PARTIAL | FAIL

STEP 3 — P0 closures
  P0-1 paging: PASS | FAIL (test function: ...)
  P0-2 provenance: PASS | FAIL (test function: ...)
  P0-3 failure mode: PASS | FAIL (test function: ...)
  Verdict: PASS | FAIL

STEP 4 — Split refusal
  Code correct: YES | NO
  Test passes: YES | NO
  Verdict: PASS | FAIL

STEP 5 — E2E surface
  Ollama available: YES | NO
  API health: PASS | FAIL | NOT-TESTED
  Document import: PASS | FAIL | NOT-TESTED
  Verdict: PASS | FAIL | NOT-TESTED

STEP 6 — Full suite
  Total: X passed, Y skipped, Z xfailed, W failed
  Baseline met (>=2917): YES | NO
  Verdict: PASS | FAIL

OVERALL: PASS | FAIL | PARTIAL
  [If PARTIAL or FAIL: list what's broken and whether it blocks the demo]
```

## Demo Guidance (Thu Sep 4)

If OVERALL = PASS:
- Demo on fresh v0.2.81 download
- Lead with: observation capture → lens → Trust view
- Show folder-to-lens if asked: upload a report card → preview → confirm
- Steer around: T1.1 (accented CSV roster), T5.2 (sibling ambiguity), parent summary fabrication

If OVERALL = FAIL:
- Identify which step failed
- If Step 1/4/6: fix before demo — pipeline contract is broken
- If Step 5 only: demo without live import, show pre-populated lenses
- Report to operator immediately
