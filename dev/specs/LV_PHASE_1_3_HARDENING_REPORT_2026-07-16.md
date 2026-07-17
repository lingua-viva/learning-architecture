# Lingua Viva Phase 1-3 Hardening Report

**Date**: 2026-07-16  
**Status**: Passed  
**Scope**: Phase 1 structured tracking, Phase 2 non-authoritative source-candidate matrix, Phase 3 lightweight checker, README publication-wording revision.

## Implemented

- Phase 1 structured tracking:
  - `artifacts/inventory.yaml`
  - `claims/evidence_register.yaml`
  - `governance/publication_safety.yaml`
  - `dev/lv_revision_log.ndjson`
  - `dev/lv_deferred_candidates.yaml`
- Phase 2 source migration candidate:
  - `curriculum/lingua_viva_matrix.yaml`
  - Status remains `draft_extracted_source_candidate`
  - Authority remains `non_authoritative`
  - Promotion decision remains `Do not promote yet.`
- Phase 3 checker:
  - `dev/lv_artifact_gauntlet.py`
  - Checks required artifacts, required claims, CEFR designed-to wording, unsupported uniqueness classification, publication safety rules, matrix authority, README overclaims, and revision-log JSON.
- Public-facing wording hardening:
  - `README.md` now uses designed/proposed language, assessment coherence wording, potential transferability, and publication exploration language.

## 15-Iteration Hardening Sweep

| Iteration | Gate | Result |
|---:|---|---|
| 1 | `dev/lv_artifact_gauntlet.py` | PASS |
| 2 | Python compile check for checker | PASS |
| 3 | YAML parse for structured files | PASS |
| 4 | NDJSON parse for revision log | PASS |
| 5 | README forbidden overclaim scan | PASS |
| 6 | Matrix authority/non-promotion/G1-G5 check | PASS |
| 7 | Inventory required artifact IDs check | PASS |
| 8 | Claim register uniqueness/CEFR wording check | PASS |
| 9 | Manual and audit file presence check | PASS |
| 10 | `.docx` no-diff check | PASS |
| 11 | README safe wording anchors check | PASS |
| 12 | Phase 0 audit required-section anchors check | PASS |
| 13 | Checker executable bit check | PASS |
| 14 | `mc health` under `MC_AGENT=1` | PASS |
| 15 | Git status visibility check | PASS |

## Checker Bootstrap Review

The first automated checker was manually reviewed against the Phase 0 audit before being treated as a release gate. The fixtures enforced by `dev/lv_artifact_gauntlet.py` map to the audit's required artifact inventory, claim audit, CEFR designed-target rule, publication/privacy rules, source-of-truth decision, README wording recommendations, and revision-log requirements.

Follow-up hardening after review strengthened the checker so every revision-log entry must include the full schema fields: `timestamp`, `revision_id`, `artifact_id`, `artifact_path`, `defect_class`, `origin`, `instrument_that_found_it`, `instrument_touched`, `independent_cross_check`, `decision`, `proof`, `reviewer`, `teacher_contribution_involved`, and `privacy_review`.

## Remaining Boundaries

- The `.docx` remains authoritative; the YAML matrix is not promoted.
- No Mission Canvas machinery was copied into Lingua Viva.
- The checker is a release gate, not a runtime service and not evidence of learning efficacy.
- Reference redistribution, institution-identifying language, and Indicazioni coverage remain review-needed.

## Whole-Build Hardening Sweep

**Requested**: 2026-07-16  
**Status**: Passed  
**Branch gate**: `LINGUA-VIVA-UPDATE`

| Iteration | Gate | Result |
|---:|---|---|
| 1 | Branch is `LINGUA-VIVA-UPDATE` | PASS |
| 2 | Lingua Viva artifact gauntlet | PASS |
| 3 | Checker `py_compile` | PASS |
| 4 | Structured YAML parse | PASS |
| 5 | Revision log full schema and boolean fields | PASS |
| 6 | README forbidden overclaim scan | PASS |
| 7 | README safe wording anchors | PASS |
| 8 | Phase 0 audit required-section anchors | PASS |
| 9 | Claim register classifications and CEFR wording | PASS |
| 10 | Matrix non-authoritative source-candidate status and G1-G5 coverage | PASS |
| 11 | Inventory source-of-truth and key artifact IDs | PASS |
| 12 | `.docx` no-diff check | PASS |
| 13 | Active-surface MC-bloat scan | PASS |
| 14 | `mc health` under `MC_AGENT=1` | PASS |
| 15 | Final branch and package status visibility | PASS |

Note: transfer/spec documents intentionally mention excluded MC machinery as excluded bloat. The active-surface scan therefore covers README, audit, structured registers, matrix, governance, and dev surfaces while excluding archived/spec transfer evidence.

## Local Support Loop Addendum

**Requested**: 2026-07-16  
**Status**: Passed  
**Branch gate**: `LINGUA-VIVA-UPDATE`

Implemented a local teacher-mode support loop under `dev/support_loop/` with `dev/lv_support.py` as the command entry point.

Validated gates:

- `python3 -m pytest implementations/education/lingua-viva/dev/support_loop/tests -q` passed.
- `python3 -m py_compile implementations/education/lingua-viva/dev/lv_support.py implementations/education/lingua-viva/dev/support_loop/*.py` passed.
- `python3 implementations/education/lingua-viva/dev/lv_support.py doctor` reports `WARN` only for the expected `.docx` bundle exclusion.
- `python3 implementations/education/lingua-viva/dev/lv_support.py gauntlet --ci` passed with scoped Lingua Viva checks.
- `python3 implementations/education/lingua-viva/dev/lv_support.py repair --safe` only created `.lv_support/` runtime directories.
- `python3 implementations/education/lingua-viva/dev/lv_support.py support-bundle` created a redacted local bundle under ignored `.lv_support/` state.

Boundaries preserved:

- No `.docx` edits.
- No curriculum matrix promotion.
- No destructive git commands.
- No student-data export.
- Support bundle git status is scoped to the Lingua Viva package, not the full monorepo.
