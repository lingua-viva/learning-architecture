# Lingua Viva Education Ontology

**Status**: `designed` — generated through MC pipeline, pending validation
**Generated**: June 19, 2026
**Method**: 4 MC CREATE passes with Claude Sonnet 4.6

## 30 Education-Specific Nodes Across 6 Domains

| Domain | Prefix | Nodes | Scope |
|--------|--------|-------|-------|
| Curriculum | LV-CUR | 6 | Unit planning, vertical alignment, CEFR mapping, differentiation, assessment design, IB PoI |
| Student | LV-STU | 7 | Intake, lens updates, CEFR tracking, RTI classification, escalation, de-escalation, social-emotional |
| Teacher | LV-TCH | 6 | Observation capture, grouping, routines, help artifacts, institutional memory, onboarding |
| Parent | LV-PAR | 3 | Recommendations (AI-opaque), progress summary, home support |
| Assessment | LV-ASS | 5 | Portfolio, CEFR rubric, mastery check, gap detection, inter-rater calibration |
| Infrastructure | LV-INF | 3 | Offline sync, content pack versioning, device fleet |

Plus 31 MC-native core nodes (MC-GOV, MC-WORK, MC-DATA, MC-DEPLOY, MC-LEGAL, intents) = **61 total system nodes**.

## Files

- `curriculum.yaml` — LV-CUR-001 through LV-CUR-006
- `student.yaml` — LV-STU-001 through LV-STU-007
- `teacher.yaml` — LV-TCH-001 through LV-TCH-006
- `parent.yaml` — LV-PAR-001 through LV-PAR-003
- `assessment.yaml` — LV-ASS-001 through LV-ASS-005
- `infrastructure.yaml` — LV-INF-001 through LV-INF-003

Each node defines: id, name, domain, description, produces, requires, suggests_next, failure_modes (silent + loud), success_conditions, blocks_external, timeout, max_depth, signals.
