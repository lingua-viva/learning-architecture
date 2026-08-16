# Lingua Viva Artifact PDF Hardening Report - 2026-08-15

## Scope

Reviewed the active Lingua Viva repo for the two critical workflows:

1. Local lesson documents/course library material -> tier-differentiated lesson artifacts -> immutable PDF outputs.
2. Student lenses -> differentiated share views where Personal Context is HR-only and teacher/family views contain only non-personal, report-grade data.

Also checked adjacent shareable/internal artifacts, especially assessment rubrics, and verified Mission Canvas four-rung work was still present locally.

## Findings

- Approved lesson packets were still durable Markdown artifacts even though PDF rendering existed.
- Per-tier PDF rendering only handled the older ContentDifferentiator payload shape, not the actual lesson_materials.TierMaterial shape used by packet approval.
- Student lens sharing had a good Drive-safe Markdown filter that omitted Personal Context, but no first-class PDF artifact path and no explicit HR-only view contract.
- Assessment rubrics were JSON-only; there was no immutable PDF export with deliverable/receipt records.
- Initial PDF artifact filenames were timestamped, which would create a new daily copy even when content had not changed.
- New backend routes require route reachability classification and UI contract bump ceremony.

## Changes Made

- Added approved lesson packet PDF creation: one teacher PDF plus three student-tier PDFs.
- Updated lesson packet approval to make the teacher PDF the deliverable location and expose all PDF paths in the response while retaining Markdown/HTML as preview companions.
- Extended the tier PDF renderer to support TierMaterial fields (`instructions_for_student`, `exercise_body`, `scaffolding`).
- Added share-scoped student lens views: `teacher`, `family`, and `hr`. Teacher/family exclude `personal_context` and unconfirmed evidence; HR includes Personal Context but still excludes raw observation narration.
- Added `POST /api/students/{student_id}/lens/pdf`, writing a PDF under the sanctioned artifact directory and recording a `student_lens` deliverable plus audit receipt.
- Added `POST /api/assess/rubric/{unit_id}/pdf`, writing a rubric PDF and recording an `assessment` deliverable plus audit receipt.
- Added `student_lens` deliverable type and local-evidence receipt scope.
- Changed lesson packet, student lens, and rubric PDF paths to content-hash identities so unchanged content reuses the existing file; changed content creates a new immutable PDF.
- Added regression tests for repeated PDF generation returning the same artifact path when content is unchanged.
- Classified the two new PDF routes in `contracts/ROUTE_REACHABILITY.yaml`.
- Bumped UI contract to v147 and updated the pinned contract test version.

## Verification

- `python3 -m py_compile src/education/student_lens.py src/lingua_viva/audit_receipts/builder.py src/lingua_viva/deliverables/schema.py src/lingua_viva/lesson_materials.py src/lingua_viva/pdf_generator.py src/web.py` passed.
- Focused artifact suite passed: lesson packet routes, PDF generator, student lens share-scope/export, Drive-safe lens markdown, Google Drive app integration, teacher API rubric path, and repeated-generation idempotency.
- Gate repair suite passed: `tests/test_lv_preflight.py`, `tests/test_route_reachability.py`, `tests/test_ui_contract.py`.
- Final full suite passed before idempotency: 2231 passed, 13 skipped in 499.09s.
- Final full suite passed after idempotency: 2231 passed, 13 skipped in 420.29s.

## Repo State Notes

- Lingua Viva local branch is still behind `origin/main` by 2 commits. I did not pull or push the held LV work.
- `ontology/proposals/CAND-B8CCB9C1.yaml` was already dirty and unrelated to this pass; I left it untouched.
- The other PC's reported held Lingua Viva commit `86d7c24` was not present in this local checkout during the audit, so this pass reviewed and hardened the current local tree.
