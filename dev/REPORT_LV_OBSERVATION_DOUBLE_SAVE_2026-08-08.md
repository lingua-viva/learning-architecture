# REPORT — Observation Double-Save Idempotency — 2026-08-08

## Commits

- Pending local commits:
  - `fix(observe): dedupe double-save at observation chokepoint`
  - `fix(observe): surface already-saved duplicate captures`
  - `chore(observe): seal double-save contracts`

## Acceptance vs Spec

- `src/education/student_lens.py` now owns the exact-match duplicate check at `append_observation`.
- UI capture paths pass a 300-second double-submit window through the pipeline to that store chokepoint.
- A duplicate returns the existing observation row with `duplicate: true` and legacy-compatible `deduplicated: true`.
- Duplicate returns skip insertion, lens recalculation, support enrichment, trait/category suggestion writes, route-side routing-memory writes, and Drive sync triggers.
- Legitimate direct/programmatic repeats remain possible unless the caller opts into a duplicate window.
- `static/index.html` now shows `Already saved.` and returns before clearing the form or refreshing the lens.

## Harness Evidence

Fresh teacher-readiness run:

```text
Run timestamp: 2026-08-09T02:13:05.811374Z
Readiness: 84.2% (16/19 checks passed)
double_artifact / C7 Repeated save produces one record / PASS
Evidence: {"created_count": 1, "first_status": 200, "second_status": 200}
```

Out-of-scope harness reds reported but not chased:

- `observe_materials / C1 No bracket placeholder reaches materials` — FAIL P0.
- `model_failure / C9 Ollama-down degradation does not mix no-model with deterministic output` — FAIL P1, expected fail.
- `model_failure / C10 Fake non-listed provider is blocked local with warning and zero egress` — FAIL P0, expected fail.

## Verification

- `pytest -q tests/test_observation_double_save.py tests/test_observation_dedup.py tests/test_student_lens.py tests/test_lens_ui_api_contract.py tests/test_ui_contract.py tests/test_route_reachability.py ...`
  - `65 passed in 7.67s`
- `python3 scripts/check_ui_contract.py`
  - `[ui-contract] OK — contract v133, 3 files locked`
- `python3 scripts/check_route_reachability.py`
  - `[route-reachability] OK — 159 routes classified (131 reachable, 28 backend-only, 17 still deferred_undecided and awaiting an operator decision)`
- `pytest -q tests/`
  - `2077 passed, 13 skipped in 1215.78s (0:20:15)`
- Post-contract correction smoke:
  - `pytest -q tests/test_ui_contract.py tests/test_observation_double_save.py`
  - `14 passed in 2.26s`

## Still Manual

- Browser double-click/touch double-tap should be spot-checked manually in Observe to confirm the toast/status timing feels right.
- No push, release, tag, or production verification performed.
