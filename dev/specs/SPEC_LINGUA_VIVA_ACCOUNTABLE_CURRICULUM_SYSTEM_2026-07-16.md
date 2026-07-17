# Lingua Viva Accountable Curriculum Spec

**Status**: proposed spec only; no implementation in this change  
**Date**: 2026-07-16  
**Author/context**: Codex review of Lingua Viva after Mission Canvas transfer analysis  
**Decision appendix**: `SPEC_LINGUA_VIVA_MC_TRANSFER_APPENDIX_2026-07-16.md`  
**Archived transfer table**: `archive/SPEC_LINGUA_VIVA_MC_TRANSFER_FULL_TABLE_2026-07-16.md`

## Problem

Lingua Viva has a strong curriculum vision, but the current package does not yet prove what it claims. The README makes public/professional claims before evidence, maturity, and publication-safe wording are tracked; the `.docx` manual draft has no explicit provenance or source-of-truth status; reference files are present but not classified by public/private/licensing risk; and teacher/student contribution boundaries are not defined. Before adding more tooling, Lingua Viva needs a small accountability layer: what is source, what is derivative, what is public-safe, what is private, and which claims can be defended.

## North Star

Lingua Viva should be curriculum a school can answer for:

1. The manual has a clear source of truth.
2. Student, teacher, colleague, and institution-private material stay private.
3. Public claims are supported, maturity-labeled, and not inflated.
4. Assessment changes do not pretend to be learning improvements.
5. Teacher collaboration is preserved without leaking identifiable classroom evidence.

## Immediate Source-Of-Truth Decision

**Decision**: `Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` is the current authoritative curriculum/manual draft for this package.

Rationale: the repo does not yet contain a structured Markdown/YAML source that can replace it. Therefore, until a future migration is explicitly approved:

| Artifact | Status |
|---|---|
| `.docx` manual | authoritative current manual draft |
| `README.md` | public/professional narrative derived from the manual and project intent |
| future curriculum matrix | derivative/extracted map until promoted |
| future generated downloads | derivative outputs |
| references | source/reference material, not the manual itself |

Consequences:

- Freshness means derivative files match the `.docx` and references.
- Publication safety must review the `.docx` content as well as README/download surfaces.
- A future Markdown/YAML source migration must include a one-time reconciliation proving the structured source preserves the manual's curriculum substance.
- Any direct edit to the `.docx` after structured derivative files exist must create a review note or revision-log entry with `defect_class: source_artifact_drift` unless the edit is only formatting. The matrix remains `draft/extracted` until the operator explicitly promotes it to authoritative. If that promotion happens, the relationship inverts: structured source becomes authoritative and the `.docx` becomes generated/derivative output.

## Operator And Review Roles

In this spec, **operator** means the accountable Lingua Viva curriculum owner: Claudia Canu Fautre unless she explicitly delegates review authority.

Other roles:

| Role | Authority |
|---|---|
| Curriculum owner/operator | approves public wording, source-of-truth changes, publication release, and claim maturity |
| Teaching team contributor | contributes activities, observations, rubric feedback, classroom implementation notes, and revision suggestions |
| Reviewer | checks claim support, privacy, references, and assessment integrity before publication |
| Runtime/tool owner | owns app, Slack bot, one-click download, and local student-data tooling in learning-architecture or a future app repo |

Teacher contributions are source material only after review. Identifiable teacher comments, classroom observations, student work, and campus-specific implementation notes are private by default. Public surfaces may describe patterns and methods, not identifiable teacher/student evidence.

## Stakeholder And Adoption Plan

Phase 0 should include a lightweight coalition path, not only artifact review.

| Stakeholder | Needed input |
|---|---|
| Curriculum owner/operator | approve source-of-truth decision, public wording, and claim maturity |
| Teaching team representatives | confirm whether the manual structure matches classroom reality and where collaboration notes can safely enter |
| School leadership or authorized delegate | approve any institution-identifying public language, publication direction, and `.docx` to structured-source migration |
| Runtime/tool owner | confirm whether one-click download, Slack bot, or app surfaces are in scope for a given release |

Adoption strategy:

- Share the Phase 0 audit as a review document, not a finished mandate.
- Ask teachers to validate the workflow in terms of classroom usefulness: what helps planning, assessment, and portfolio work; what feels like extra compliance.
- Treat the `.docx` to structured-source migration as a later coalition decision. Target review window: after the Phase 0 audit and before any public/downloadable release that depends on a curriculum matrix.

## Current System Model

### Lingua Viva Package

Owner: `/home/mical/fde/implementations/education/lingua-viva`

| Surface | Current role | Required decision |
|---|---|---|
| `README.md` | public/professional narrative | audit claims and adjust wording |
| `Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` | authoritative current manual draft | classify as source of truth for now |
| `references/CEFR_Young_Learners.pdf` | reference | classify public/licensed/private status |
| `references/CEFR_can_do_lists.pdf` | reference | classify public/licensed/private status |
| `references/Criteri_Fondanti_Curricolo_Italiano_K-5*.pdf/pages` | reference/source candidate | review licensing and publication safety |
| `references/D.M.211-2025-GU-26012026-Nuove-Indicazioni-nazionali.pdf` | standards reference | verify title/date before public citation |
| `palette_imported.yaml` | legacy Palette/MC knowledge import | reference-only; not LV source |
| `import_palette.py` | legacy import utility | out of LV runtime scope |

### Learning-Architecture Reuse Boundary

Learning-architecture already owns the broader education engine. Reuse it; do not copy it into the Lingua Viva package.

Verified existing surfaces:

| Surface | Verified role | LV stance |
|---|---|---|
| `ontology/education/curriculum.yaml` | IB unit planning, CEFR mapping, Indicazioni alignment, Reggio multimodal exploration, vertical coherence | reuse, but review Indicazioni coverage before relying on it for final publication |
| `ontology/education/assessment.yaml` | assessment/rubric, standards tracker, portfolio and CEFR evidence nodes | reuse |
| `ontology/education/teacher.yaml`, `student.yaml`, `parent.yaml`, `planning.yaml`, `learner.yaml`, `admin.yaml`, `infrastructure.yaml` | teacher workflow, student privacy, parent reports, planning, learner prompts, admin/accreditation, Toddle/cross-campus constraints | reuse |
| `knowledge/education/*` | evidence-tiered education knowledge including multilingual observation, curriculum IB, RTI/assessment, differentiation, trauma-informed practice | reuse |
| `lenses/education/*` | curriculum designer, assessment specialist, parent voice, multilingual learner, observation coach, RTI monitor, school leader, trauma-informed lenses | reuse |
| `tests/golden_education_v1.yaml` | education routing and decoy tests | reuse |
| `src/education/slack_bot.py` | Slack observation capture input surface | runtime-private; do not duplicate |
| `src/education/student_lens.py`, `access_control.py`, `observation_capture.py` | local student data and permissions | runtime-private; do not duplicate |
| `src/education/document_parser.py`, `document_store.py`, `document_retrieval.py` | document ingestion and retrieval | reuse if source processing is later automated |
| `src/education/parent_report.py` | parent-safe teacher-voice output, no AI attribution | reuse as rule precedent |
| `src/education/content_differentiator.py`, `assessment_generator.py`, `teacher_guide.py` | deterministic classroom artifact helpers | reuse as tool layer |

## Public Claim Audit

This is the first useful action. It should be completed before new YAML schemas or automation.

| Claim in current README/manual | Current support | Classification | Required action |
|---|---|---|---|
| Lingua Viva integrates Indicazioni Ministeriali, CEFR A1-B1, IB PYP, and Reggio-inspired multimodality | README, `.docx`, and references support intent; coherence has not been independently reviewed | supported as designed, not validated | wording should say "designed to integrate" until reviewed |
| The integration methodology is transferable | plausible design argument; no implementation outside one school | aspirational | label as potential transferability, not proven |
| "Unique globally among IB PYP schools with Italian immersion" / equivalent uniqueness claims | no market scan or publisher/IB evidence in repo | unsupported high-risk claim | downgrade to "rare" or "to the author's knowledge" pending evidence |
| Potential editorial publication | no publisher contact or publication proposal in repo | aspirational | keep as future possibility, not plan/proof |
| Measurable outcomes through CEFR, Toddle portfolios, Prove MT, Kahoot | tools named; no LV-specific measurement data in package | partially supported as design intent | distinguish assessment design from measured outcome |
| 3-year timeline for design/pilot/finalization/publication | README/manual state plan | supported as project plan | keep as plan, not commitment |
| 50% standardized / 50% flexible model | stated design principle | supported as design principle | keep but do not claim validated efficacy |
| School-serving app/tool surfaces such as one-click download or Slack bot | learning-architecture has related runtime surfaces; LV package does not own them | external dependency | reference as tool ecosystem only after boundary is explicit |

Output of Phase 0 should be a short Markdown audit report that updates this table with final wording decisions.

CEFR wording rule: "curriculum designed to target CEFR A1-B1" can be supported by curriculum mapping to CEFR descriptors. "Students achieve CEFR A1-B1" is an outcome claim and requires validated external assessment evidence. Designed/proposed maturity must use designed-to wording, never achievement wording.

## Minimal Workflow

Lingua Viva does not need a 12-step runtime pipeline. Use this human workflow:

1. **Draft or revise**: update the `.docx`, README, manual section, curriculum note, app/download copy, or teacher-contribution summary.
2. **Check privacy**: confirm no student names, individual assessment records, identifiable colleague comments, confidential institution material, or unpublished internal documents are exposed.
3. **Check evidence and maturity**: confirm claims are supported by the `.docx`, references, learning-architecture evidence, or a documented review; downgrade unsupported claims.
4. **Publish or hold**: release only public-safe material; keep private/internal material local; log any ambiguous item for later review.

This workflow can later become structured files or checks if the package grows. It should not become a service.

If automated drafting/reasoning is later added through learning-architecture or another tool, it must assemble context from approved source material, evidence notes, and publication-safety constraints. It must not introduce new public claims that are absent from the audit/register, and it must not send student/private content or unpublished curriculum structures to external research or model services.

## Governance Rules

| Area | Rule |
|---|---|
| Student data | No raw student work, names, IEPs, progress reports, individual scores, or identifiable observations in the Lingua Viva package or public surfaces. |
| Teacher contributions | Private by default. Public outputs may use anonymized patterns or collaboratively approved activities, not identifiable classroom notes. |
| Institution data | Use generic institution descriptions unless the curriculum owner explicitly approves naming or identifying detail. |
| Colleague data | Do not name or identify colleagues in public/professional surfaces without explicit approval. |
| References | Classify each reference as public, licensed, private, generated, source, or review-needed before public redistribution. |
| AI attribution | No public Lingua Viva artifact may attribute curriculum decisions, assessment decisions, or parent-facing communication to AI. AI may assist drafting; humans own the published result. |
| Claims | Public claims require evidence, maturity label, and safe wording. Unsupported claims are downgraded or held. |
| Assessment | Assessment/rubric changes must not be reported as student learning gains without independent evidence. |
| External research | Do not send student/private content, unpublished internal documents, or unpublished proprietary curriculum structure to external research tools. Research general standards or public landscape questions without exposing the manual's non-public architecture. |

## Assessment And Measurement Integrity

Every meaningful revision should be labeled with one defect class:

| Defect class | Meaning | Usual fix |
|---|---|---|
| `curriculum_content` | content, sequence, framework mapping, or activity is wrong/incomplete | revise manual/source content |
| `assessment_instrument` | rubric, CEFR threshold, benchmark, or scoring instrument changed | revise instrument and require independent cross-check |
| `evidence_interpretation` | evidence is read too strongly or against the wrong baseline | revise interpretation and maturity label |
| `publication_wording` | public/professional wording overclaims | downgrade wording or add evidence |
| `source_artifact_drift` | README/matrix/download differs from `.docx` or references | refresh derivative or mark stale |
| `privacy_exposure` | public/internal boundary violated | block publication and redact/reclassify |
| `ambiguous` | source cannot be determined | hold and create review note |

Concrete Lingua Viva example:

If the CEFR rubric changes the A1-to-A2 threshold from Grade 2 to Grade 3 and more students "pass," that does not prove better teaching. It may only prove the goalpost moved. The revision must be logged as `assessment_instrument`, not `curriculum_content`, and any learning-improvement claim requires an independent anchor such as unchanged student work samples, human calibration, or an external benchmark.

If structured tracking is added later, revision-log entries should use this schema:

```yaml
timestamp: 2026-07-16T14:30:00Z
revision_id: lv-rev-003
artifact_id: lv-artifact-readme
artifact_path: README.md
defect_class: publication_wording
origin: human_review
instrument_that_found_it: phase0_claim_audit
instrument_touched: false
independent_cross_check: unchanged_docx_excerpt
decision: "Downgrade unsupported uniqueness claim."
proof: "README claimed global uniqueness; repo contains no market scan."
reviewer: operator
teacher_contribution_involved: false
privacy_review: passed
```

Append-only logs should not be created empty. Start them only when there are real revisions to record.

## Implementation Phases

### Phase 0 - Human Audit First

No YAML. No Python checker. No new runtime.

Deliver one Markdown report, for example `LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md`, containing:

- current artifact inventory
- source-of-truth decision: `.docx` authoritative current draft
- README/manual claim audit with supported, aspirational, unsupported, and private classifications
- publication/privacy issues found
- revised safe wording recommendations
- teacher-contribution boundary notes
- stakeholder signoff needs and adoption notes
- open questions for the curriculum owner

### Phase 1 - Structured Tracking Only If Needed

If Phase 0 finds enough claims/revisions to make manual review brittle, add structured files:

- `artifacts/inventory.yaml`
- `claims/evidence_register.yaml`
- `governance/publication_safety.yaml`
- `dev/lv_revision_log.ndjson`
- `dev/lv_deferred_candidates.yaml`

These files should be populated from the Phase 0 audit, not created empty.

### Phase 2 - Source Migration

Only after the `.docx` has been audited:

- decide whether to keep `.docx` authoritative through Year 1 or migrate to Markdown/YAML
- if migrating, create `curriculum/lingua_viva_matrix.yaml` as the new source candidate
- reconcile matrix rows against the `.docx` and references
- promote structured source only after review
- set a target promotion review date when the migration starts; do not leave both `.docx` and matrix in indefinite dual-authority.

### Phase 3 - Automation Threshold

Do not build `dev/lv_artifact_gauntlet.py` now. A human checklist is sufficient while the package is small.

Automation becomes justified when one of these is true:

- the package grows beyond roughly 30 maintained artifacts
- multiple generated outputs exist
- public release cadence makes manual review unreliable
- structured claim/evidence files are already populated
- the one-click app/download pipeline needs repeatable release gates

The first automated checker, if built, is a bootstrap exception: it is validated by human review of its fixtures against the Phase 0 audit files. After that initial validation, any change to the checker, fixture set, rubric logic, parser, or freshness rule requires an independent cross-check under the measurement-integrity rule.

If claim tracking becomes structured, add optional `scope`, `scoped_by`, or `conflicts_with` fields only when overlapping claims start creating ambiguity. Example: "CEFR A1-A2 focus for K-3" can be compatible with "A1-B1 progression for K-5" if the grade span is explicit.

## Publication Checklist

Before any public README/manual/app/download release:

- `.docx` source status is clear.
- Claims are classified as supported, aspirational, unsupported, or private.
- Uniqueness claims are downgraded unless externally evidenced.
- Student/colleague/institution-private content is absent.
- Teacher contributions are anonymized or approved.
- AI is not credited as the decision-maker or assessor.
- Assessment changes are not described as learning gains without independent evidence.
- Any derivative matrix/download/README is fresh relative to the `.docx`.
- External research did not expose unpublished curriculum structure.

## Explicit Non-Goals

Do not transfer or build:

- Mission Canvas action registry
- connector framework, OAuth vault, or circuit breakers
- CRM/PSA/support/sales/marketing/finance/HR/real-estate workflows
- voice backend/STT/TTS vendor stack
- executable canvas manifests
- patent evidence CLI/reporting
- recursive improvement service
- generalized document rendering system
- Python gauntlet before the human audit proves it is necessary
- keeping `import_palette.py` active as a normal LV tool; archive or remove it after the Phase 0 inventory confirms it is not needed

## Acceptance Criteria

- The spec stands alone as a Lingua Viva curriculum/accountability spec.
- The `.docx` is identified as current authoritative manual draft.
- The README claim audit is present and actionable.
- Operator and teaching-team roles are defined.
- The workflow is human-scale, not a hidden runtime.
- Publication safety includes explicit AI-attribution and teacher-contribution rules.
- Measurement integrity includes a concrete CEFR threshold example.
- Stakeholder/adoption review is included in Phase 0.
- Future structured tracking has a revision-log schema and `.docx` drift rule.
- MC transfer details are summarized in the appendix and archived separately.

## Risks

| Risk | Mitigation |
|---|---|
| Overbuilding governance for a small package | Phase 0 is one Markdown audit; structured files only after need is proven |
| Leaving claims inflated | audit README/manual claims immediately and downgrade unsupported language |
| Treating `.docx` as generated | mark it authoritative until a migration is approved |
| Losing teacher collaboration | define teacher contributions as private-by-default source material |
| Misreporting assessment changes as learning gains | require defect class and independent cross-check |
| Duplicating learning-architecture runtime | reuse existing education engine surfaces by boundary |
| Sharing the manual's non-public architecture through research | research only general public standards/landscape questions unless operator approves disclosure |

## Deferred Questions

- Should a future structured source replace the `.docx`, and when?
- Which references can be redistributed publicly?
- Who besides the curriculum owner can approve public wording?
- What one-click download artifact format is actually needed?
- Which teacher-contributed materials can become shared curriculum source after anonymization and review?
- Should `import_palette.py` be moved to `archive/` or removed after inventory?
