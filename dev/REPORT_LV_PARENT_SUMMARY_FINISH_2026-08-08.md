# REPORT — Student Summary Finish Line — 2026-08-08

## Window

Student Summary finish line: fail closed on student identity, keep C6 traceability locked, and give the teacher local copy/print exits.

## Commits

- `ee8fe89` — `fix(parent-summary): fail closed on student identity`
- `8749626` — `feat(parent-summary): add copy and print exits`
- `1c2491f` — `chore(parent-summary): bump UI contract to v132`

## Acceptance

- `POST /api/parents/recommendation` now returns `400 {"error": "student_id_required"}` for blank or missing student IDs.
- Unknown students now return `404 {"error": "unknown_student"}` with no draft body.
- The demo-student fallback was removed from `src/web.py`; `student-nora` no longer appears in that file.
- `source_observation_ids` is locked for students with observations: non-empty and owned by the requested student.
- Student Summary drafts now render `Copy final text` and `Print` controls after the editable textarea.
- Copy uses the current edited subject/body text, not the original draft payload.
- Print builds a minimal local HTML document from the current edited text and sends it through the existing `printPacketHtml(...)` chokepoint, preserving the single print invocation site.
- Safety warnings and the “Review before sending. No AI attribution in final message.” label remain visible and non-blocking.

## Verification

Run from clean detached worktree `/tmp/lv-parent-summary-verify-l71xUc` at `1c2491f`:

- `pytest -q tests/test_parent_summary_finish.py tests/test_packet_print.py tests/test_ui_contract.py tests/test_route_reachability.py tests/test_parent_report.py tests/test_parent_report_safety_gate.py` — `46 passed`
- `python3 scripts/check_ui_contract.py` — OK, contract v132
- `python3 scripts/check_route_reachability.py` — OK, 159 routes classified
- `pytest -q tests/` — interrupted after `476 passed, 13 skipped` in `1101.42s`; no failure had been reported. A separate full-suite pytest process from the concurrent observation window was still running in the main repo during this attempt.

## Manual / Context

- No push performed.
- Actual family sending remains human/manual by design; this build provides copy and print exits only.
- The shared main worktree still contains unrelated observation double-save edits and a v132 contract draft from that window. Parent-summary contract files were generated and staged from a clean detached worktree to avoid committing those in-flight changes.
