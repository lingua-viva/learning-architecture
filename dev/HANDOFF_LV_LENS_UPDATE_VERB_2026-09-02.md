# HANDOFF - LV Lens Update Verb

Date: 2026-09-02
Repo: `/home/mical/learning-architecture`
Branch: `main`

## Current State

`lv lens-update` is implemented, committed, and merged to `origin/main`.

Commit:

```bash
21f6b59 Add LV lens-update CLI verb
```

Committed files:

- `src/lingua_viva/cli.py`
- `tests/test_cli_lens_update.py`

Uncommitted files at handoff:

- `tests/test_document_to_lens.py` - prior hardening lock for multi-student
  no-position refusal.
- `dev/HANDOFF_LV_FOLDER_TO_LENS_HARDENING_2026-09-02.md` - prior hardening
  handoff.
- `dev/SPEC_LV_LENS_UPDATE_VERB_2026-09-02.md` - operator-provided spec.
- `dev/PROMPT_LV_LENS_UPDATE_VERB_BUILD_2026-09-02.md` - operator-provided
  build prompt.

`origin/main` also contains the follow-up spec/prompt docs and the
`desktop-v0.2.83` release/site pins:

```bash
a9f7f2c docs: lens-update verb spec, build prompt, and hardening handoff
12f8f5d chore(release): prepare desktop-v0.2.83
293eb36 chore(release): pin desktop-v0.2.83
```

## What Was Built

CLI:

```bash
lv lens-update FILE [FILE...] [--preview-only] [--student ID] [--json]
```

Implementation location:

```bash
src/lingua_viva/cli.py
```

The handler is intentionally thin. It calls existing pipeline functions only:

- `extract_plain_text`
- `classify_document_type`
- `match_document_to_students`
- `extract_for_lens_update`
- `save_extraction_log`
- `apply_extractions_to_lenses`
- `StudentLensStore`
- `ReasoningEngine` when available

No docpipe extraction, matching, writer, or lens-store internals were changed.

## Behavior

For each file:

1. Validates the path.
2. Extracts plain text using the existing parser.
3. Classifies the document.
4. Refuses class lists with a roster-import message.
5. Refuses curriculum/other documents as not student files.
6. Loads the existing student roster from `StudentLensStore`.
7. Either matches students automatically or uses `--student`.
8. Runs `extract_for_lens_update`.
9. Saves the extraction log before any write.
10. Prints preview or JSON.
11. If not preview-only, asks for CLI confirmation unless `--json`.
12. Applies through `apply_extractions_to_lenses`.

Multi-file runs merge extraction results per student before apply. This avoids
the spec prompt's overwrite hazard where later files for the same student could
replace earlier file results in `{student_id: result}`.

## Tests Added

New file:

```bash
tests/test_cli_lens_update.py
```

Coverage:

- preview-only writes nothing;
- nonexistent file exits 1 cleanly;
- class-list documents exit 0 with roster-import guidance;
- single-file e2e apply;
- `--json` produces machine-readable output;
- `--student` skips matching and targets the requested student.

## Verification Run

```bash
pytest tests/test_cli_lens_update.py -q
```

Result:

```text
6 passed in 0.68s
```

```bash
pytest tests/test_cli_lens_update.py tests/test_document_to_lens.py tests/test_batch_classify_provenance.py -q
```

Result:

```text
43 passed in 0.86s
```

Prompt baseline:

```bash
python3 -m pytest tests/test_lens_from_report_cards.py \
  tests/test_name_match_fold.py \
  tests/test_batch_classify_provenance.py \
  tests/golden/test_golden_document_to_lens.py -q --tb=short
```

Result:

```text
192 passed, 6 xfailed in 94.02s
```

Syntax check:

```bash
python3 -m py_compile src/lingua_viva/cli.py
```

Result: passed.

CLI help smoke:

```bash
PYTHONPATH=. python3 src/lv_cli.py lens-update --help
```

Result: passed.

Note: `python3 src/lv_cli.py ...` without `PYTHONPATH=.` fails with
`ModuleNotFoundError: No module named 'src'`. That appears to be the repo's
existing direct-script import-path behavior, not a `lens-update` regression.

## Important Semantics

The existing writer does not auto-write every previewed field.

- `verified` deterministic support-profile fields can write.
- `needs_confirmation` fields are kept review-required unless explicitly
  confirmed by the lower-level writer contract.
- `classify_failed` fields remain visible but are refused by the writer.

This is correct for the governance model: import is not truth.

## Suggested Next Window

1. Decide whether to commit the prior hardening lock:
   `tests/test_document_to_lens.py` plus
   `dev/HANDOFF_LV_FOLDER_TO_LENS_HARDENING_2026-09-02.md`.
2. Decide whether the operator-provided spec/prompt files should be committed.
3. Run one real local smoke against a teacher/demo DB with an existing student:

```bash
PYTHONPATH=. python3 src/lv_cli.py lens-update <report-file> --preview-only
```

4. If demo needs a no-prompt path, use `--json`; current behavior applies
   without interactive confirmation when `--json` and not `--preview-only`.
5. API endpoint remains intentionally skipped; spec allowed skipping it for
   demo because existing web two-step import/apply route still works.

## Demo-Eve Consolidation Check

2026-09-02 evening:

- Fast-forwarded local `main` to `origin/main` at `293eb36`.
- Confirmed `origin/LINGUA-VIVA-UPDATE` is an ancestor of `origin/main`.
- Confirmed GitHub Pages serves `linguaviva.art` from `main:/docs`.
- Confirmed live site download buttons point at `desktop-v0.2.83`.
- Confirmed release assets answer 200 for Mac, Windows, and Linux.
- Corrected GitHub release metadata so `desktop-v0.2.83` is prerelease, keeping
  CLI latest on `v1.0.6`.
- Moved old ignored local readiness state out of the repo to
  `/home/mical/.lv_teacher_readiness-backup-20260902-212725`.

Verification:

```text
python3 -m pytest tests/ -q
2926 passed, 13 skipped, 6 xfailed in 778.06s

python3 scripts/check_ui_contract.py
[ui-contract] OK — contract v180, 3 files locked

python3 scripts/check_route_reachability.py
[route-reachability] OK — 196 routes classified

python3 scripts/check_app_reality.py
exit 0; no critical/high findings

npm run build --prefix desktop
passed

Local server smoke on clean LV_STATE_HOME:
/api/health -> 200, routers_loaded=5, routers_expected=5, version=1.0.7
/api/students -> 200
/api/sources/records -> 200
/api/sources/observations -> 200
/api/students/growth -> 200
/api/students/support-summary -> 200
```
