# Lingua Viva Support Loop MVP Hardening Report

**Date**: 2026-07-16  
**Branch gate**: `LINGUA-VIVA-UPDATE`  
**Status**: Passed  
**Scope**: Phase A diagnostic MVP plus app-first `Doctor` button wiring.

## Implemented

- Local Doctor engine under `dev/support_loop/`.
- CLI fallback through `dev/lv_support.py doctor` and `dev/lv_support.py doctor --json`.
- App endpoint: `GET /api/lingua-viva/doctor`.
- App button: `Doctor` in the branch-local web app navigation.
- Teacher-readable app result with collapsed details.
- Phase A result contract with `support_bundle_available: false`.

## Boundaries Preserved

- No `.docx` edits.
- No curriculum matrix promotion.
- No curriculum content rewrite.
- No destructive Git behavior.
- No external calls.
- No support bundle, repair, update, incident, or improvement workflow exposed in Phase A.
- Doctor privacy scan lists path-level risk only and does not read private contents.

## Focused Hardening Sweep

| # | Gate | Evidence | Result |
|---:|---|---|---|
| 1 | Healthy path | `python3 dev/lv_support.py doctor` ran and returned teacher-readable `WARN` only for local worktree visibility and expected `.docx` exclusion. | PASS |
| 2 | Missing file fixture | `test_missing_file_fixture_is_blocked` simulates a missing required file. | PASS |
| 3 | YAML parse failure fixture | `test_yaml_parse_failure_fixture_is_blocked` simulates invalid YAML. | PASS |
| 4 | NDJSON schema failure fixture | `test_ndjson_schema_failure_fixture_is_blocked` simulates an incomplete revision-log entry. | PASS |
| 5 | README overclaim detection | `test_readme_overclaim_fixture_is_blocked` plus forbidden-pattern coverage test. | PASS |
| 6 | Matrix authority failure detection | `test_matrix_authority_failure_fixture_is_blocked` simulates promoted/authoritative matrix state. | PASS |
| 7 | Gauntlet failure propagation | `test_gauntlet_failure_propagates` simulates `lv_artifact_gauntlet.py` failure. | PASS |
| 8 | Branch mismatch behavior | `test_branch_mismatch_blocks` simulates a non-`LINGUA-VIVA-UPDATE` branch. | PASS |
| 9 | Dirty worktree visibility | `test_dirty_worktree_is_visible` simulates local Lingua Viva package changes. | PASS |
| 10 | Privacy-risk path detection | `test_privacy_risk_path_detection` simulates an IEP-like private path and confirms contents are not needed. | PASS |
| 11 | JSON output validity | `python3 dev/lv_support.py doctor --json \| python3 -m json.tool` parsed successfully. | PASS |
| 12 | App button render/action smoke | `tests/test_pwa_assets.py` checks `doctor-btn`, `runDoctor()`, and `/api/lingua-viva/doctor`; `tests/test_pwa_routes.py` checks endpoint response. | PASS |
| 13 | No external calls | Doctor result returns `external_calls: false`; endpoint test runs locally through FastAPI TestClient. | PASS |
| 14 | `.docx` no-diff | `git status --short -- implementations/education/lingua-viva/Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` returned no file status. | PASS |
| 15 | Final branch/status check | `git -C /home/mical/fde branch --show-current` returned `LINGUA-VIVA-UPDATE`. | PASS |

## Validation Commands

```bash
python3 -m pytest /home/mical/fde/implementations/education/lingua-viva/dev/support_loop/tests -q
python3 -m pytest tests/test_pwa_assets.py tests/test_pwa_routes.py -q
python3 /home/mical/fde/implementations/education/lingua-viva/dev/lv_support.py doctor
python3 /home/mical/fde/implementations/education/lingua-viva/dev/lv_support.py doctor --json
python3 /home/mical/fde/implementations/education/lingua-viva/dev/lv_artifact_gauntlet.py
python3 -m py_compile /home/mical/fde/implementations/education/lingua-viva/dev/lv_support.py /home/mical/fde/implementations/education/lingua-viva/dev/support_loop/*.py src/web.py
```

## Deferred Phase B/C Work

- Redacted support bundle from the app.
- Safe repair rule engine.
- Safe update preflight.
- Incident log and support improvement proposal workflow.
- Teacher packaging/polish beyond the first app button.
