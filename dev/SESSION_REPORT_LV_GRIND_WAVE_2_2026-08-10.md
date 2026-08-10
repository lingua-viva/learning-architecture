# Lingua Viva Grind Wave 2 Session Report

Date: 2026-08-10
Repo: `/home/mical/learning-architecture`
Prompt: `dev/PROMPT_LV_GRIND_WAVE_2_2026-08-09.md`
Spec: `dev/SPEC_LV_GRIND_WAVE_2_2026-08-09.md`

## Result

G1-G7 were implemented and G8 was run as an actual grind loop, not just a checklist.

Final loop result: no remaining fixable issue found in the built areas after harness, wiring/UI audit, app-boot smoke, and fresh-eyes teacher walkthrough.

No push was performed.

## Commits

- `8f2d03a feat(engine): add restricted safeguarding review workflow`
- `bd1fdf8 feat(app): surface PoI progression in student lens`
- `7a6ba40 fix(engine): harden readiness latency and model-failure exits`
- `f465f79 feat(engine): skip configured holidays in absence escalation`
- `b2a987c fix(app): route parent draft through sharing matrix`
- `3fd72e6 feat(engine): add optional coursework enrichment`
- `54da5d6 fix(engine): cap lesson material prompt budget`
- `53e704c feat(engine): rank library search with bm25 scoring`
- `9f34912 fix(meta): close auto-release tag-trigger gap; C9/C10 gate for real`
- `aec6f88 fix(engine): bound coursework enrichment latency`

## Build Items

G1 - Restricted safeguarding review workflow
- Added coordinator-only status transitions for restricted safeguarding entries.
- Preserved the restricted ledger boundary and used rewrite semantics instead of an unsafe append-only status overlay.
- Added route and regression coverage for role gates and review audit fields.

G2 - Student lens PoI progression
- Mounted the Programme-of-Inquiry progression panel in the selected student lens.
- The panel consumes `/api/poi/progression/{student_id}` and renders phases, trends, evidence notes, and next consolidation target.
- UI contract bumped through the normal protocol.

G3 - Readiness latency and model-failure honesty
- Added step-level C8 evidence for capture/material/report/query duration.
- Fixed deterministic no-model paths so they do not pretend a model answered.
- Blocked unsupported provider configuration locally with zero egress.
- C9/C10 now pass as real checks, not expected failures.

G4 - Absence escalation calendar
- Added optional local holiday calendar support under `<LV_STATE_HOME>/calendar/holidays.yaml|yml|json`.
- Escalation day counts now skip configured holidays while preserving the old no-calendar behavior.
- Added coordinator-only `/api/absences/calendar`.

G5 - Parent draft through sharing matrix
- Routed the final parent recommendation payload through `sharing_matrix.filter_payload(..., "parent")`.
- Kept the legacy response shape while adding defense-in-depth filtering against non-parent-safe fields.

G6 - Optional coursework enrichment
- Added local-only optional enrichment for coursework activities.
- Enrichment degrades to deterministic output on no model, unsafe content, errors, or timeout.
- Teacher and student packet copies remain aligned; teacher-only keys stay out of student copies.

G7 - Library ranking
- Replaced the old search ordering with deterministic BM25-style scoring over chunks plus a title boost.
- Kept filters and response shape stable.

G8 - Grind loop
- First live walkthrough found a fixable issue: optional coursework enrichment could wait on the default reasoning timeout and make a printable packet feel blocked.
- Fixed with a dedicated short enrichment timeout and regression coverage.
- Re-ran the focused tests, live walkthrough, and full suite after the fix.

## Verification

Preflight:
- Command: `unset ANTHROPIC_API_KEY; export MC_AGENT=1; python3 -m src.lingua_viva.cli preflight --json`
- Result: 6/6 passed.
- Checks: `ui_contract`, `golden_parses` (36 queries), `imports`, `ontology` (111 nodes), `no_conflicts`, `route_reachability`.

Teacher-readiness:
- Command: `unset ANTHROPIC_API_KEY; export MC_AGENT=1; python3 -m src.lingua_viva.cli eval teacher-readiness --json`
- Result: 19/19 passed, 0 failed, 0 stubbed, 100% readiness.
- C8 evidence passed for ask, materials, parent report, and cold ask.
- C9/C10 model-failure checks passed with local-only/no-egress evidence.

Focused route/UI audit:
- Command: `pytest -q tests/test_route_reachability.py tests/test_ui_contract.py tests/test_sources_routes.py tests/test_safeguarding.py tests/test_absence_escalation.py tests/test_coursework_pack.py`
- Result: 88 passed.

Focused post-fix checks:
- Command: `pytest -q tests/test_coursework_pack.py tests/test_poi_progression.py`
- Result: 27 passed.
- Command: `pytest -q tests/test_teacher_readiness.py tests/test_lesson_materials.py`
- Result: 24 passed.

Full suite before final G8 fix:
- Command: `pytest -q tests/`
- Result: 2224 passed, 13 skipped.

Full suite after final G8 fix:
- Command: `pytest -q tests/`
- Result: 2225 passed, 13 skipped in 605.89s.

Live app walkthrough:
- App booted with `uvicorn src.web:app --host 127.0.0.1 --port 8765`.
- Final run used `LV_AUTH_MODE=local_header`, synthetic local state, and real HTTP calls.
- Result: passed.
- Covered: root document, health, PoI record/progression, parent summary fail-closed without student, coursework teacher/student packet, library add/search, restricted safeguarding teacher denial, restricted safeguarding coordinator access, absence calendar coordinator access.

## Wiring/UI Audit

Mounted or verified surfaces:
- G1: `/api/safeguarding/restricted` and `/api/safeguarding/restricted/{entry_id}/status` are coordinator-only restricted workflow endpoints with route tests.
- G2: `static/index.html` contains `poi-progression-panel` and calls `/api/poi/progression/{studentId}`.
- G4: `/api/absences/calendar` is coordinator-only and tested.
- G5: `/api/parents/recommendation` is already UI-mounted and now passes through the sharing matrix.
- G6: `/api/artifacts/coursework-pack` returns both teacher and student copies and is tested by API plus live walkthrough.
- G7: `/api/library/search` remains wired to the Sources/library route and passed API/live search checks.

No new unmounted teacher-facing surface was found in the G1-G7 scope.

## Operator-Blocked Boundary

These remain intentionally blocked on operator decisions/secrets:
- Safeguarding Slack/channel and Drive folder values.
- Perplexity key plus `LV_ALLOW_RESEARCH=1`.
- Auto-release PAT secret.
- Production deploy/live release verification.

The build reaches the config boundary for these items and fails closed where the values are absent.

## Worktree Note

Unrelated local files were left untouched, including `ontology/proposals/CAND-B8CCB9C1.yaml` and other untracked dev notes not belonging to this wave.
