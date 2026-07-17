# Lingua Viva Publication Readiness Audit

**Status**: Phase 0 human audit complete; package is not publication-ready yet  
**Date**: 2026-07-16  
**Scope**: Publication readiness, source-of-truth status, privacy risk, public claim support, learning-architecture reuse boundary. This audit creates no YAML schemas, Python checkers, runtime code, gauntlets, migrations, or `.docx` edits.

## Source Files Reviewed

- `/home/mical/fde/implementations/education/lingua-viva/README.md`
- `/home/mical/fde/implementations/education/lingua-viva/Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx`
- `/home/mical/fde/implementations/education/lingua-viva/references/*`
- `/home/mical/fde/implementations/education/lingua-viva/palette_imported.yaml`
- `/home/mical/fde/implementations/education/lingua-viva/import_palette.py`
- `/home/mical/learning-architecture/publication-policy.md`
- `/home/mical/learning-architecture/case-studies/03-lingua-viva/README.md`
- `/home/mical/learning-architecture/ontology/education/*`
- `/home/mical/learning-architecture/knowledge/education/*`
- `/home/mical/learning-architecture/lenses/education/*`
- `/home/mical/learning-architecture/src/education/*`
- `/home/mical/learning-architecture/tests/golden_education_v1.yaml`

## Artifact Inventory

| Artifact | Current role | Source/derivative/reference/legacy status | Public status | Publication risk | Required action |
|---|---|---|---|---|---|
| `README.md` | Public/professional narrative | Derivative | Review-needed | Overclaims on uniqueness, transferability, outcomes, and publication | Revise to designed/proposed wording |
| `Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` | Current curriculum/manual draft | Authoritative source draft | Internal/review-needed | Names/identifies school context and contains strong global/market claims | Keep authoritative; do not publish externally before review |
| `references/CEFR_Young_Learners.pdf` | CEFR young learner reference | External reference | Review-needed | Redistribution rights not verified | Cite/link only after license check |
| `references/CEFR_can_do_lists.pdf` | CEFR can-do/case-study reference | External reference | Review-needed | Redistribution rights not verified | Cite/link only after license check |
| `references/Criteri_Fondanti_Curricolo_Italiano_K-5.pages` | Editable local criteria file | Local source/reference candidate | Private/review-needed | Contains local curriculum structure/assets | Keep internal until ownership and redaction review |
| `references/Criteri_Fondanti_Curricolo_Italiano_K-5.pdf` | Local criteria/reference PDF | Local source/reference candidate | Private/review-needed | Names school/San Francisco and includes uniqueness claims | Redact/downgrade before public use |
| `references/Criteri_Fondanti_Curricolo_Italiano_K-5_v2.pdf` | Revised local criteria PDF | Local source/reference candidate | Private/review-needed | References local POI/planner materials | Keep internal until approved |
| `references/D.M.211-2025-GU-26012026-Nuove-Indicazioni-nazionali.pdf` | Italian standards/government reference | External standards reference | Likely public, review-needed | Filename says D.M.211 while PDF text says Decreto n. 221; citation mismatch | Verify official citation |
| `palette_imported.yaml` | Imported Palette knowledge snapshot | Legacy/reference | Internal | Could confuse LV provenance | Treat as reference-only |
| `import_palette.py` | Legacy Palette import utility | Legacy tooling | Internal | Could imply MC machinery belongs in LV | Decide later whether to archive/remove |

## Source-Of-Truth Decision

`Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` is the current authoritative curriculum/manual draft. `README.md`, future matrices/downloads, and app/public copy are derivative until a future migration is explicitly approved. References support the manual; they are not the manual. `palette_imported.yaml` and `import_palette.py` are legacy/reference surfaces.

`.docx` drift rule: after structured derivative files exist, any direct edit to the `.docx` must create a review note or revision-log entry with `defect_class: source_artifact_drift`, unless formatting-only. A matrix remains `draft/extracted` until the operator explicitly promotes it. If promoted, the structured source becomes authoritative and the `.docx` becomes generated/derivative output.

## README/Manual Claim Audit

| Claim | Source surface | Support currently found | Classification | Maturity label | Publication-safe wording | Required action |
|---|---|---|---|---|---|---|
| Four-framework integration: Indicazioni, CEFR, IB PYP, Reggio | README, `.docx`, Criteri refs, LA ontology | Supports design intent; independent coherence review not found | Supported as design intent | Designed/proposed | "Designed to integrate Italian national standards, CEFR-informed language progression, IB PYP inquiry, and Reggio-inspired multimodal documentation." | Keep designed-to wording |
| CEFR A1-B1 progression | README, `.docx`, CEFR refs | Targets/mapping intent found; validated achievement evidence not found | Supported as target, unsupported as outcome | Designed/proposed | "Designed to target a CEFR-informed progression toward A1-B1 across K-5." | Do not claim achievement |
| Transferability | README | Plausible design argument; no external implementation evidence | Aspirational | Proposed | "May be useful to comparable contexts after adaptation." | Downgrade from proven |
| Uniqueness/global rarity | README, `.docx`, Criteri PDFs | No market scan/IB/publisher proof | Unsupported | Proposed at most | "Rare, to the author's knowledge." | Replace global uniqueness |
| Editorial publication | README, `.docx` | Future possibility only | Aspirational | Proposed | "Could be explored after review, anonymization, and rights clearance." | Keep as option |
| Measurable outcomes/assessment coherence | README, `.docx`, LA assessment/runtime | Assessment design exists; LV-specific outcome data not found | Partially supported as design intent | Designed/proposed | "Intended to connect to CEFR indicators and school assessment tools so progress can be documented consistently." | Separate design from learning gains |
| 3-year timeline | README, `.docx` | Stated consistently | Supported as plan | Proposed | "Planned as a three-year initiative." | Keep as plan |
| 50% standardized / 50% flexible | README, LA curriculum node | Design principle found; efficacy not validated | Supported as design principle | Designed | "Balances common objectives/rubrics/activities with teacher adaptation." | Do not claim efficacy |
| App/tool surfaces | LA runtime files, implied future surfaces | Runtime exists outside LV; one-click format undefined | External dependency/review-needed | Proposed | "Related tools may support future private workflows, subject to owner review." | Do not promise from LV |

## CEFR Claim Wording Rule

Use "curriculum designed to target CEFR A1-B1" for intent. "Students achieve CEFR A1-B1" is an outcome claim and requires validated external assessment evidence. Designed/proposed maturity must use designed-to wording.

## Publication And Privacy Review

- Student names or identifiable student work: none found in sampled LV text; future examples must be anonymized.
- Individual assessment records/scores and IEPs/progress reports: none found in LV package; learning-architecture contains local/private tooling that must not be copied into public LV artifacts.
- Colleague identifiers: no individual colleague names found; teacher contribution wording must avoid identification without consent.
- Institution-identifying/confidential details: present in manual/Criteri references; public use requires authorized review.
- Unpublished internal school documents: Criteri files reference POI/planner materials; treat as private unless approved.
- Private/licensed references: CEFR/Eaquals redistribution rights not verified.
- Proprietary curriculum structure: present in `.docx`, Criteri PDFs, and Pages file.
- AI attribution: public curriculum/assessment decisions must be human-owned; no AI attribution as assessor/decision-maker.

## Teacher Contribution Boundary

Teacher activities, observations, rubric feedback, and implementation notes can enter the curriculum only after anonymization, owner review, and classification as activity idea, rubric feedback, implementation note, observation pattern, or revision suggestion. Identifiable teacher/student/classroom evidence is private by default. Public-safe wording: "developed with input from teaching teams" or "refined through reviewed teacher implementation feedback."

## Stakeholder And Adoption Notes

- Curriculum owner/operator approves source status, wording, maturity, and release.
- Teaching team reviews classroom usefulness and collaboration channels.
- School leadership or authorized delegate reviews institution-identifying language and school-owned content.
- Runtime/tool owner reviews one-click download, Slack bot, app, and student-data surfaces.
- Adoption path: use this audit as a review document, not a finished mandate.

## Learning-Architecture Reuse Verification

| Surface | Relevant coverage | Boundary/gap |
|---|---|---|
| `ontology/education/*` | Curriculum, assessment, student, teacher, parent, planning, admin, infrastructure nodes; includes CEFR mapper and Indicazioni alignment | Reuse; do not copy. Indicazioni coverage needs grade-by-grade review before final publication |
| `knowledge/education/*` | IB, differentiation, RTI/assessment, multilingual observation, trauma-informed knowledge | Reuse as support, not LV source authority |
| `lenses/education/*` | Curriculum, assessment, parent voice, multilingual, observation, RTI, school leader lenses | Reuse as reasoning frames |
| `tests/golden_education_v1.yaml` | Education routing/privacy/decoy coverage | Reuse for LA confidence; not publication proof |
| `src/education/*` | Local/private student, Slack, report, document, assessment, teacher-guide tools | Keep in learning-architecture; do not copy runtime into LV |

## Recommended Wording Changes

| Replace | With |
|---|---|
| "unique globally" | "rare, to the author's knowledge" |
| "students achieve B1" | "designed to support progression toward B1" |
| "measurable outcomes" | "assessment structures intended to make progress visible" |
| "transferable" | "may be transferable after adaptation" |
| "publication" as commitment | "publication could be explored after review and rights clearance" |
| named institution/market details | generic multi-campus IB international school language unless authorized |

## Open Questions

- Which references can be redistributed publicly?
- Who besides the curriculum owner can approve public wording?
- Should `import_palette.py` be archived or removed later?
- What one-click download artifact format is actually needed?
- Which teacher-contributed materials can become shared curriculum source after anonymization and review?
- Is Indicazioni Ministeriali coverage sufficient for final publication?

## Phase 0 Conclusion

The package is not publication-ready now. Minimum changes before public release: downgrade overclaims, anonymize or approve institution-identifying language, verify reference rights, keep `.docx` authoritative until explicit promotion, use CEFR designed-to wording, and define owner/team/leadership/tool review gates.

Phase 1 structured YAML tracking is warranted after this audit because there are enough claims, references, and release gates to make manual review brittle. Phase 2 source migration may begin only as a non-authoritative source candidate. Phase 3 automation is justified only as a lightweight checker once structured claim/evidence files exist.
