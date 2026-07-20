# Report: Doctor Sweep — 2026-07-20

**Scope**: Run the local Doctor loop one finding at a time, fix stale checks only after confirming the underlying code/repo state, and verify with tests between findings.

## Findings handled

1. **Fixed: stale branch gate**
   - Starting state: `python3 -m doctor.support_loop doctor` returned `BLOCKED`.
   - Finding: `FAIL: Branch must be LINGUA-VIVA-UPDATE; current branch is main.`
   - Cause: Doctor still encoded the feature-branch build convention from the 2026-07-16 specs, but merged work now lives on `main` and the handoff identifies the `main` block as stale.
   - Change: `doctor/support_loop/doctor.py` now treats `main` as the current expected branch and preserves `LINGUA-VIVA-UPDATE` as an allowed legacy branch. The JSON output also exposes `branch_allowed`.
   - Test coverage: added hardening tests for `main`, `LINGUA-VIVA-UPDATE`, and unexpected branch rejection.

2. **Reviewed and deferred: `privacy_path_scan` WARN**
   - Final finding: `Expected private-source exclusions are present and were not read.`
   - Detail: `Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` and `resume-cv/Claudia_CanuFautre_Resume.docx`.
   - Decision: leave as WARN. This is a privacy notice, not a defect: Doctor is correctly detecting private/source `.docx` files by path and explicitly not reading their contents.

3. **Reviewed: `worktree_status` WARN during the sweep**
   - Cause: the Doctor fix and report edits themselves made the worktree dirty while Doctor was running.
   - Decision: no code change. This clears once the reviewed sweep is committed.

## Verification

- `python3 -m doctor.support_loop doctor` after branch fix: `WARN` only.
- `python3 -m pytest doctor/support_loop/tests/ -q`: `17 passed`.
- `python3 -m pytest tests/ -q`: `437 passed in 89.81s`.

Final gate commands were run after this report was written; see the committing window/final response for their exact output.
