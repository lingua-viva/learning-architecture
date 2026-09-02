# Execution Prompt: Build `lv lens-update` Verb

**Spec**: `dev/SPEC_LV_LENS_UPDATE_VERB_2026-09-02.md`
**Pipeline contract**: `dev/SPEC_LV_FOLDER_TO_LENS_2026-09-02.md`
**Deadline**: before LV demo Thu Sep 4

---

## Context

You are building a CLI verb — `lv lens-update` — that takes local documents
and updates student lenses through an already-tested 5-stage pipeline. Everything
behind the verb exists and passes 192 contract tests + 2917 full suite. You are
writing a ~100-line CLI handler + ~120-line test file. No pipeline work.

## Environment

```bash
cd ~/learning-architecture
export MC_AGENT=1
```

## Pre-flight: baseline must be green

```bash
python3 -m pytest tests/test_lens_from_report_cards.py \
  tests/test_name_match_fold.py \
  tests/test_batch_classify_provenance.py \
  tests/golden/test_golden_document_to_lens.py -v --tb=short
# Must be: 192 passed, 6 xfailed, 0 failed
```

If not green, STOP. Fix before building.

## Step 1: Add CLI parser (cli.py)

Open `src/lingua_viva/cli.py`.

In `build_parser()`, after the last `sub.add_parser(...)` call (around line 816),
add:

```python
lens = sub.add_parser("lens-update", help="Update student lenses from local documents")
lens.add_argument("files", nargs="+", metavar="FILE", help="Document paths (PDF, DOCX, XLSX, CSV, TXT)")
lens.add_argument("--preview-only", action="store_true", help="Show preview without writing")
lens.add_argument("--student", default=None, help="Target student ID (skip auto-matching)")
lens.add_argument("--json", action="store_true")
```

In `main()`, before `return 1` (around line 859), add:

```python
if args.command == "lens-update":
    return asyncio.run(_lens_update(args))
```

## Step 2: Write the handler function

Add `_lens_update()` to `cli.py`. Place it near the other handler functions
(after `_fleet()` or wherever makes sense).

The handler calls ONLY existing functions. Do not rewrite any pipeline logic.

```python
async def _lens_update(args: argparse.Namespace) -> int:
    """Update student lenses from local documents."""
    import json as json_mod
    from pathlib import Path

    from src.lingua_viva.docpipe.extract import (
        classify_document_type,
        extract_plain_text,
    )
    from src.lingua_viva.docpipe.lens_extract import (
        apply_extractions_to_lenses,
        extract_for_lens_update,
        save_extraction_log,
    )
    from src.lingua_viva.docpipe.lens_match import match_document_to_students
    from src.education.student_lens import StudentLensStore

    # Validate files
    paths = []
    for f in args.files:
        p = Path(f).expanduser().resolve()
        if not p.is_file():
            print(f"Error: {f} does not exist or is not a file.")
            return 1
        paths.append(p)

    # Load roster once
    store = StudentLensStore()
    try:
        lenses = store.list_lenses()
        roster = [
            {"student_id": l["student_id"], "display_name": l["display_name"]}
            for l in lenses
        ]
    except Exception as exc:
        print(f"Error loading student roster: {exc}")
        store.close()
        return 1

    # Get reasoning engine (optional — heuristics still work without it)
    engine = None
    try:
        from src.lingua_viva.reasoning import ReasoningEngine
        engine = ReasoningEngine()
    except Exception:
        pass

    all_results: dict[str, dict] = {}      # student_id → ExtractionResult
    all_logs: list[str] = []
    json_output: list[dict] = []

    try:
        for path in paths:
            # Read
            content = path.read_bytes()
            ext = path.suffix.lower()
            filename = path.name

            # Extract text
            try:
                text = extract_plain_text(content, ext)
            except Exception:
                try:
                    text = content.decode("utf-8", errors="replace")
                except Exception:
                    text = ""

            if not text.strip():
                print(f"  {filename}: empty or unreadable — skipped")
                continue

            # Classify
            doc_type = classify_document_type(text, filename)
            if doc_type == "class_list":
                print(f"  {filename}: class list — use roster import instead")
                continue
            if doc_type in ("curriculum", "other"):
                print(f"  {filename}: {doc_type} document — not a student file, skipped")
                continue

            if not args.json:
                print(f"\nlens-update: {filename}")
                print(f"  Type: {doc_type}")

            # Match students
            if args.student:
                matched = [s for s in roster if s["student_id"] == args.student]
                if not matched:
                    print(f"  Student {args.student} not found in roster.")
                    continue
            else:
                matched = match_document_to_students(text, filename, roster)

            if not matched:
                print(f"  No matching students found.")
                continue

            if not args.json:
                print(f"  Students matched: {len(matched)}")

            # Extract (THE 5-STAGE PIPELINE)
            results = await extract_for_lens_update(
                document_bytes=content,
                document_type=doc_type,
                matched_students=matched,
                lens_store=store,
                engine=engine,
            )

            # Save extraction log
            log_path = save_extraction_log(results, filename)
            all_logs.append(str(log_path))

            # Print preview
            file_json = {
                "file": filename,
                "document_type": doc_type,
                "students": [],
                "extraction_log": str(log_path),
            }

            for student_id, result in results.items():
                display_name = next(
                    (s["display_name"] for s in matched if s["student_id"] == student_id),
                    student_id,
                )
                active_fields = [f for f in result.fields if f.status != "classify_failed"]
                confirmed = [f for f in active_fields if f.status == "verified"]
                needs_review = [f for f in active_fields if f.status == "needs_confirmation"]

                student_json = {
                    "student_id": student_id,
                    "display_name": display_name,
                    "field_count": len(active_fields),
                    "verified": len(confirmed),
                    "needs_confirmation": len(needs_review),
                    "unresolved_questions": result.unresolved_questions,
                }

                if not args.json:
                    marker = "verified" if not needs_review else "needs_confirmation"
                    print(f"\n  {display_name} ({student_id})")
                    print(f"    Fields: {len(active_fields)} ({len(confirmed)} verified, {len(needs_review)} need review)")
                    for f in active_fields[:10]:
                        icon = "✓" if f.status == "verified" else "?"
                        print(f"    {icon} {f.field_path}: \"{f.value[:60]}\" ({f.status}, {f.confidence:.2f})")
                    if len(active_fields) > 10:
                        print(f"    ... and {len(active_fields) - 10} more")
                    for q in result.unresolved_questions:
                        print(f"    ⚠ {q}")

                file_json["students"].append(student_json)

            json_output.append(file_json)

            # Accumulate for apply
            for sid, res in results.items():
                all_results[sid] = res

        # If --json + --preview-only, dump and exit
        if args.json and args.preview_only:
            print(json_mod.dumps(json_output, indent=2, default=str))
            return 0

        if args.preview_only:
            return 0

        if not all_results:
            if not args.json:
                print("\nNo student data extracted from any file.")
            return 0

        # Confirm
        total = len(all_results)
        if not args.json:
            try:
                answer = input(f"\nUpdate {total} student lens(es)? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
                return 0
            if answer not in ("y", "yes"):
                print("Cancelled.")
                return 0

        # Apply
        summaries = await apply_extractions_to_lenses(
            results=all_results,
            lens_store=store,
        )

        # Print summary
        if args.json:
            for fj in json_output:
                for sj in fj["students"]:
                    sid = sj["student_id"]
                    if sid in summaries:
                        sj["written_count"] = len(summaries[sid].get("written_fields", []))
                        sj["review_required"] = len(summaries[sid].get("review_required", []))
            print(json_mod.dumps(json_output, indent=2, default=str))
        else:
            print(f"\nUpdated {len(summaries)} student lens(es):")
            for sid, summary in summaries.items():
                written = len(summary.get("written_fields", []))
                review = len(summary.get("review_required", []))
                name = next(
                    (s["display_name"] for s in roster if s["student_id"] == sid),
                    sid,
                )
                print(f"  {name}: {written} fields written, {review} need review")
            if all_logs:
                print(f"\nExtraction log(s): {', '.join(all_logs)}")

        return 0
    finally:
        store.close()
```

**CRITICAL**: The above is the reference implementation. You may adjust
formatting and error handling, but DO NOT:
- Rewrite `extract_for_lens_update` or any pipeline function
- Add new extraction logic
- Change the lens writer
- Skip `save_extraction_log` (the log is the audit trail)
- Auto-confirm without the y/N prompt (invariant 5: import ≠ truth)

## Step 3: Write tests

Create `tests/test_cli_lens_update.py`:

```python
"""Tests for the lv lens-update CLI verb."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.lingua_viva.cli import main


# --- Fixtures ---

@pytest.fixture
def sample_report(tmp_path):
    """A minimal student report for testing."""
    report = tmp_path / "report.txt"
    report.write_text(
        "Boyce Aiken\n\n"
        "Boyce demonstrates strong reading comprehension and analytical thinking. "
        "He works well in small groups and shows leadership during collaborative tasks.\n"
    )
    return report


@pytest.fixture
def empty_file(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("")
    return f


# --- Tests ---

def test_nonexistent_file_exits_1():
    assert main(["lens-update", "/nonexistent/file.pdf"]) == 1


def test_preview_only_writes_nothing(sample_report, tmp_path):
    """--preview-only must not modify the lens store."""
    # This test needs a real or mocked store with at least one student.
    # The handler loads the store, matches, extracts, previews, and exits.
    # Verify no write_student_lens calls happen.
    result = main(["lens-update", str(sample_report), "--preview-only"])
    assert result == 0


def test_json_flag_produces_valid_json(sample_report, capsys):
    """--json --preview-only produces parseable JSON."""
    result = main(["lens-update", str(sample_report), "--preview-only", "--json"])
    assert result == 0
    out = capsys.readouterr().out.strip()
    if out:  # may be empty if no students matched
        parsed = json.loads(out)
        assert isinstance(parsed, list)


def test_empty_file_skipped(empty_file, capsys):
    result = main(["lens-update", str(empty_file), "--preview-only"])
    assert result == 0
    assert "empty or unreadable" in capsys.readouterr().out
```

**Adapt these tests to work with the actual store and engine fixtures.**
The important invariants to test:

1. `--preview-only` never writes to any lens
2. Nonexistent file → exit 1
3. `--json` → valid JSON output
4. Empty file → skip with message
5. Class list file → polite refusal
6. The handler calls `extract_for_lens_update` (not a reimplementation)

Use `monkeypatch` or mocks for the ReasoningEngine where needed — the
existing `_StubEngine` in `test_batch_classify_provenance.py` is a good
model. But prefer testing through the real pipeline path where possible.

## Step 4: Run tests

```bash
# New tests
python3 -m pytest tests/test_cli_lens_update.py -v --tb=short

# Contract tests (must still pass)
python3 -m pytest tests/test_lens_from_report_cards.py \
  tests/test_name_match_fold.py \
  tests/test_batch_classify_provenance.py \
  tests/golden/test_golden_document_to_lens.py -v --tb=short
# 192 passed, 6 xfailed

# Full suite
python3 -m pytest tests/ -q
# >= 2917 passed, 0 failed
```

**Exit gate**: all three pass. If any fail, fix before committing.

## Step 5: Manual smoke test

```bash
# Does the verb exist?
python3 -m src.lv_cli lens-update --help

# Preview a test fixture (if one exists)
python3 -m src.lv_cli lens-update tests/fixtures/sample_report_card.pdf --preview-only 2>&1

# If no fixture, use any .txt with a student name that's in the store
echo "Boyce Aiken shows strong progress in reading." > /tmp/test_report.txt
python3 -m src.lv_cli lens-update /tmp/test_report.txt --preview-only 2>&1
```

Record the output. If it shows matched students and field previews, the verb
works. If it says "No matching students", that's correct for an empty store —
note it and move on.

## Step 6: Commit

```bash
git add src/lingua_viva/cli.py tests/test_cli_lens_update.py
git commit -m "feat: lv lens-update CLI verb — document-to-lens in one command

Wires the existing 5-stage extraction pipeline (192 contract tests) into
a CLI verb: lv lens-update FILE [--preview-only] [--student ID] [--json].
Preview → confirm → apply flow. No pipeline changes. Audit trail via
save_extraction_log.

New tests: tests/test_cli_lens_update.py"
```

## Step 7: Verify against the spec

Read `dev/SPEC_LV_LENS_UPDATE_VERB_2026-09-02.md` acceptance criteria and
check each one:

1. `lv lens-update FILE` → runs pipeline → preview
2. `--preview-only` → preview only, no writes
3. Confirmation → writes, summary matches preview
4. Nonexistent file → clean error, exit 1
5. Class list → polite refusal
6. Multiple files → processes both
7. `--student` → filters to one student
8. `--json` → machine-readable
9. 7 governance invariants hold (existing 192 tests)
10. Full suite green (>=2917)

Report each as PASS/FAIL.

## What This Enables for the Demo (Thu Sep 4)

If this works, Claudia can see:
```
$ lv lens-update ~/Documents/report_cards/term2.pdf --preview-only

lens-update: term2.pdf
  Type: student_report
  Students matched: 6

  Boyce Aiken (s-boyce)
    Fields: 7 (2 verified, 5 need review)
    ✓ cefr_snapshot.reading: "A2" (verified, 0.99)
    ? learning_and_cognition: "strong reading comprehension" (needs_confirmation, 0.72)
    ...
```

That's the demo beat: "your documents become student lenses, governed,
grounded, nothing writes without your confirmation."
