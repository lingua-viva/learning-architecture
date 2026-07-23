# Report: LV File-Map Verification UI

**Date:** 2026-07-22  
**Status:** SHIPPED (uncommitted)

## Delivered

- Domain-tagged file-map entries can be confirmed as `curriculum_source` or `ignore`.
- Confirmations and manual student assignments round-trip through YAML and the API.
- Detected student zones remain collapsed until an explicit teacher click.
- Zone peek lists one level of names, types, sizes, and modification times only.
- Direct files can be assigned manually to an existing student or flagged for a new student.
- `confirmed_extraction_inputs` exposes both `student_lens` and `curriculum_unit`
  target shapes for Spec 5.
- The combined protected UI surface is locked at contract v15 after concurrent
  file-map, Slack, voice, and Observe work converged.

## Privacy and adversarial verification

- `_scan_directory()` is unchanged and still refuses to descend into student zones.
- Diff audit found no added `open`, `read`, `read_text`, or `read_bytes` call in the feature backend.
- A monkeypatched-content-access test passed for `list_files_in_zone()`.
- `/api/filemap/peek` returned 400 for a real directory not present in `student_zones`.
- Assignment accepts only a direct, non-symlink file inside a detected student zone.
- Zones replaced by symlinks after scanning are rejected.
- Unknown student IDs are rejected; unassigning removes the extraction input.
- No automatic filename-to-student matching was added.

## Live verification

An on-disk tree (outside pytest fixtures) containing a curriculum folder and a nested
student zone was scanned through the API:

- scan: 200; one student zone detected but not traversed
- curriculum confirmation: 200
- explicit zone peek: 200
- returned fields: `modified_at`, `name`, `path`, `size_bytes`, `type`
- arbitrary non-zone peek: 400
- unknown-student assignment: 400
- roster-backed manual assignment: 200
- API reload: one curriculum-unit input and one student-lens input persisted

The temporary tree and map file were removed after verification.

## Tests

- `python -m py_compile src/web.py src/lingua_viva/filemap.py`: passed
- Feature behavior after 15 review passes: 42 passed
- UI contract tests pass at the converged v15 lock.
- Full suite: 460 passed, 24 failed on this Windows workstation. Failures are
  environment/pre-existing groups: unavailable/mismatched Ollama embedding endpoint,
  POSIX shell tooling, clean-tree preflight in an intentionally dirty operator tree,
  and Unix `0600` mode assertions on NTFS. Two initial UI lock failures were resolved
  by the required v10 contract bump.

No commit was created.

## Fifteen-pass iteration

The implementation was reviewed and improved through 15 distinct lenses:
contract fidelity, privacy, path security, persistence, API validation,
assignment integrity, Windows path handling, UI behavior, accessibility,
error handling, state refresh, Spec 5 handoff completeness, regressions,
live adversarial behavior, and final diff hygiene.

Material improvements from the cycle:

- stale confirmations and assignments are pruned on rescan/exclusion
- removed student zones no longer remain peekable after rescan
- zone symlink replacement is rejected
- New Student now creates a real roster entry before assignment
- Not Assigned truly removes the file from confirmed extraction inputs
- confirmed curriculum folders now emit direct-file `curriculum_unit` inputs
- API paths remain display-redacted while internal handoff paths remain absolute
