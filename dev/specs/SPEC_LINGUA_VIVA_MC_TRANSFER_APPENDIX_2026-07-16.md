# Lingua Viva Mission Canvas Transfer Summary

**Date**: 2026-07-16  
**Main spec**: `SPEC_LINGUA_VIVA_ACCOUNTABLE_CURRICULUM_SYSTEM_2026-07-16.md`  
**Full archived table**: `archive/SPEC_LINGUA_VIVA_MC_TRANSFER_FULL_TABLE_2026-07-16.md`

This appendix keeps the useful transfer decisions readable. The full 198-row review table is archived for audit history, not meant as a working document.

## Coverage

| Source group | Actions/rules reviewed | Included | Adapted | Reused existing | Excluded | Deferred |
|---|---:|---:|---:|---:|---:|---:|
| MC master layered table and layer specs | 130 | 11 | 16 | 13 | 85 | 5 |
| Patent readiness verified | 29 | 3 | 6 | 2 | 17 | 1 |
| Patent readiness addendum | 16 | 2 | 3 | 1 | 9 | 1 |
| Measurement integrity spec | 11 | 7 | 3 | 0 | 1 | 0 |
| Classify regression triage spec | 12 | 3 | 3 | 4 | 0 | 2 |
| **Total** | **198** | **26** | **31** | **20** | **112** | **9** |

## Included Or Adapted

| Transfer | Why it helps Lingua Viva | Main spec location |
|---|---|---|
| Source/publication scan | Student, teacher, colleague, and institution-private content must not leak into README/manual/download surfaces. | Governance Rules; Publication Checklist |
| Claim/evidence grounding | Public claims need support, maturity labels, and safe wording. | Public Claim Audit |
| Source-of-truth/freshness distinction | The `.docx`, README, future matrix, and downloads need a clear authority chain. | Immediate Source-Of-Truth Decision |
| Measurement integrity | Rubric/checker changes must not masquerade as learning improvement. | Assessment And Measurement Integrity |
| Defect-source triage | Separate curriculum content, assessment instrument, evidence interpretation, publication wording, source drift, privacy, and ambiguity. | Assessment And Measurement Integrity |
| Append-only review habit | Lingua Viva needs review memory, but only after the human audit proves structured logging is useful. | Implementation Phases |
| Deferred candidate discipline | Ambiguous/risky findings should be held rather than forced into bad changes. | Implementation Phases; Deferred Questions |
| Publication/IP readiness, not patent machinery | Originality/publication claims need evidence, but patent reporting does not belong in Lingua Viva. | Public Claim Audit; Explicit Non-Goals |

## Reused Instead Of Duplicated

| Existing learning-architecture surface | Reuse decision |
|---|---|
| `ontology/education/*` | use as existing education taxonomy; review Indicazioni coverage before final publication reliance |
| `knowledge/education/*` | use as evidence-tiered education knowledge |
| `lenses/education/*` | use for curriculum, assessment, parent voice, multilingual, observation, RTI, school-leader, and trauma-informed reasoning |
| `tests/golden_education_v1.yaml` | keep routing/golden coverage in learning-architecture |
| `src/education/slack_bot.py` | keep Slack observation capture in runtime/tool layer |
| `src/education/student_lens.py`, `access_control.py`, `observation_capture.py` | keep student data local/private in runtime layer |
| `src/education/document_parser.py`, `document_store.py`, `document_retrieval.py` | reuse only if source processing becomes automated |
| `src/education/parent_report.py` | reuse no-AI-attribution and parent-safe precedent |
| `src/education/content_differentiator.py`, `assessment_generator.py`, `teacher_guide.py` | keep deterministic classroom artifact helpers outside the LV package |

## Excluded As Bloat

Mission Canvas features that do not belong in the Lingua Viva package now:

- action registry and action candidates
- connector framework, credential vault, OAuth, circuit breakers
- CRM, PSA, support, sales, marketing, finance, HR, operations, and real-estate executors
- voice backend, STT/TTS vendors, telephony transport
- executable canvas manifests
- generalized document rendering subsystem
- patent evidence CLI and prior-art reporting
- recursive improvement service
- broad automated gauntlet before a human audit proves need

## Deferred

| Deferred item | Decision needed |
|---|---|
| Structured Markdown/YAML source migration | decide after auditing the `.docx` |
| One-click download artifact contract | define expected artifact format and release flow |
| Public redistribution of references | verify licensing/public status |
| Automated checker | build only after package size or release cadence justifies it |
| Additional publication/IP evidence | gather only for claims the curriculum owner wants to keep |
