# REPORT — Pending Evidence Review Loop — 2026-08-08

## Commit

- Pending local commit: `feat(evidence): add pending evidence review loop`

## Acceptance vs Spec

- Store chokepoints added in `src/education/student_lens.py`:
  - pending report payload now carries `id`, `evidence_type`, `source_observation_id`, and `created_by`;
  - `confirm_profile_strength` / `dismiss_profile_strength`;
  - `confirm_ethos_evidence` / `dismiss_ethos_evidence`;
  - confirm flips to `teacher_confirmed` and bumps `profile_version`;
  - dismiss sets `active = False` and preserves the stored item;
  - ethos confirm updates the matching `evidence_records.confidence_level` row.
- Routes added in `src/web.py`:
  - `GET /api/students/{student_id}/evidence/pending`;
  - `POST /api/students/{student_id}/evidence/confirm`;
  - missing students return 404, off-map ids/kinds/traits return 422 with zero writes.
- Students lens UI in `static/index.html` now renders `Waiting for your confirmation (N)`,
  grouped pending strengths and trait evidence, per-row Confirm/Dismiss, the kept-out-of-parent-reports
  house language, refresh/toast behavior, and the empty state.
- Ceremony completed:
  - both routes classified in `contracts/ROUTE_REACHABILITY.yaml`;
  - UI contract bumped from v130 to v131 and lock regenerated;
  - surface-lock coverage added in `tests/test_pending_evidence_review.py`.

## Verification

- `pytest -q tests/test_ethos.py tests/test_pending_evidence_review.py tests/test_ui_contract.py tests/test_route_reachability.py`
  - `74 passed in 6.23s`
- `python3 scripts/check_ui_contract.py`
  - `[ui-contract] OK — contract v131, 3 files locked`
- `python3 scripts/check_route_reachability.py`
  - `[route-reachability] OK — 159 routes classified (131 reachable, 28 backend-only, 17 still deferred_undecided and awaiting an operator decision)`
- `pytest -q tests/`
  - `2066 passed, 13 skipped in 1071.03s (0:17:51)`

## Still Manual

- Browser-level clickthrough remains manual: open a student with model-suggested strength/trait evidence,
  confirm one item, dismiss one item, and visually confirm the queue refreshes.
- No push, release, tag, or production verification performed.
