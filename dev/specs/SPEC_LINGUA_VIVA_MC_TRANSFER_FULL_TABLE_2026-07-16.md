# Lingua Viva Mission Canvas Transfer Appendix

**Date**: 2026-07-16  
**Main spec**: `SPEC_LINGUA_VIVA_ACCOUNTABLE_CURRICULUM_SYSTEM_2026-07-16.md`

This appendix records the Mission Canvas action review. It is intentionally more mechanical than the main spec.

Column meanings:

- **Applicability**: `beneficial`, `adapt`, `not_needed`, `defer`
- **Disposition**: `include_in_lingua_viva_spec`, `exclude_as_bloat`, `reuse_existing_learning_architecture_surface`, `defer_for_operator_judgment`

## Coverage Summary

| Source group | Actions/rules reviewed | Included | Adapted | Reused existing | Excluded | Deferred |
|---|---:|---:|---:|---:|---:|---:|
| MC master layered table and layer specs | 130 | 11 | 16 | 13 | 85 | 5 |
| Patent readiness verified | 29 | 3 | 6 | 2 | 17 | 1 |
| Patent readiness addendum | 16 | 2 | 3 | 1 | 9 | 1 |
| Measurement integrity spec | 11 | 7 | 3 | 0 | 1 | 0 |
| Classify regression triage spec | 12 | 3 | 3 | 4 | 0 | 2 |
| **Total** | **198** | **26** | **31** | **20** | **112** | **9** |

The 14 individual layer specs were read and matched against the master 130-row table in `SPEC_CHANGES_BY_PIPELINE_LAYER_2026-07-15.md`; they do not add separate action IDs beyond the master rows.

## Master Layered Build Actions

| Source | ID | Layer | Summary | LV pipeline step | Applicability | Disposition | Priority | Proposed LV action / reason | Proof gate |
|---|---|---|---|---|---|---|---|---|---|
| SPEC_CHANGES + L01 | 1.1 | INGRESS | Pipecat voice transcription processor | ORIGIN | not_needed | exclude_as_bloat | P2 | LV already has Slack observation capture in learning-architecture; no telephony need in artifact package | none |
| SPEC_CHANGES + L01 | 1.2 | INGRESS | Retell voice backend | ORIGIN | not_needed | exclude_as_bloat | P2 | hosted voice transport is MC/runtime scope | none |
| SPEC_CHANGES + L01 | 1.3 | INGRESS | channel parameter in pipeline trace | ORIGIN/STORE | adapt | include_in_lingua_viva_spec | P1 | record artifact/request origin in revision log, not MC pipeline field | revision log has origin |
| SPEC_CHANGES + L01 | 1.4 | INGRESS | inbound webhooks | ORIGIN | not_needed | exclude_as_bloat | P2 | no LV webhook requirement | none |
| SPEC_CHANGES + L01 | 1.5 | INGRESS | parsed ticket adapter | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | support-ticket adapter is unrelated | none |
| SPEC_CHANGES + L01 | 1.6 | INGRESS | pipecat dependency | ORIGIN | not_needed | exclude_as_bloat | P2 | dependency bloat | none |
| SPEC_CHANGES + L01 | 1.7 | INGRESS | connector onboarding phase pattern | WORKTYPE CLASSIFY | defer | defer_for_operator_judgment | P2 | only revisit if LV app adds external integrations | integration decision |
| SPEC_CHANGES + L02 | 2.1 | SCAN | prompt-injection scan | PRIVACY/PUBLICATION SCAN | adapt | include_in_lingua_viva_spec | P1 | tiny publication/source scanner should flag injection-like source instructions in references | gauntlet fixture |
| SPEC_CHANGES + L02 | 2.2 | SCAN | LlamaGuard content safety | PRIVACY/PUBLICATION SCAN | not_needed | exclude_as_bloat | P2 | model safety service is too heavy for artifact package | none |
| SPEC_CHANGES + L02 | 2.3 | SCAN | shared entity detectors | PRIVACY/PUBLICATION SCAN | adapt | reuse_existing_learning_architecture_surface | P0 | reuse learning-architecture sanitizer/document parser patterns; do not fork | scanner references owner |
| SPEC_CHANGES + L02 | 2.4 | SCAN | sanitizer convergence health check | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | require checker-cross-check for privacy/publication rules | checker checks section |
| SPEC_CHANGES + L02 | 2.5 | SCAN | STT local routing | PRIVACY/PUBLICATION SCAN | reuse | reuse_existing_learning_architecture_surface | P1 | student observations already local/private in learning-architecture runtime | runtime boundary documented |
| SPEC_CHANGES + L02 | 2.6 | SCAN | direct injection-chain test | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | add source/publication hostile fixture if gauntlet is built | gauntlet fixture |
| SPEC_CHANGES + L02 | 2.7 | SCAN | injection in file content test | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | references and generated docs need file-content safety checks | gauntlet fixture |
| SPEC_CHANGES + L02 | 2.8 | SCAN | exit-gate multiturn injection | PRIVACY/PUBLICATION SCAN | not_needed | exclude_as_bloat | P2 | no chat/session service in package | none |
| SPEC_CHANGES + L02 | 2.9 | SCAN | dual-clearance bypass test | PRIVACY/PUBLICATION SCAN | adapt | include_in_lingua_viva_spec | P0 | publication gate must require privacy and evidence clearance | publication gate |
| SPEC_CHANGES + L02 | 2.10 | SCAN | sanitizer divergence exploit test | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | if two checkers exist, compare them | checker checks |
| SPEC_CHANGES + L02 | 2.11 | SCAN | LlamaGuard false-positive guards | INTEGRITY CHECK | not_needed | exclude_as_bloat | P2 | tied to LlamaGuard | none |
| SPEC_CHANGES + L02 | 2.12 | SCAN | voice PROTECT blocked externally | PRIVACY/PUBLICATION SCAN | reuse | reuse_existing_learning_architecture_surface | P0 | learning-architecture already treats student nodes as local/private | education tests |
| SPEC_CHANGES + L03 | 3.1 | CLASSIFY | cached GPU probe | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | MC model runtime issue | none |
| SPEC_CHANGES + L03 | 3.2 | CLASSIFY | confidence floor before LLM override | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P1 | education golden suite already guards classification; reference it | golden suite |
| SPEC_CHANGES + L03 | 3.3 | CLASSIFY | precomputed ClassificationResult | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | no LV pipeline runtime | none |
| SPEC_CHANGES + L03 | 3.4 | CLASSIFY | expose confidence_score | WORKTYPE CLASSIFY | adapt | include_in_lingua_viva_spec | P1 | worktype classification should record confidence only if checker built | revision log field |
| SPEC_CHANGES + L03 | 3.5 | CLASSIFY | warm/cold classification test | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P1 | use existing education classifier tests | golden suite |
| SPEC_CHANGES + L03 | 3.6 | CLASSIFY | deterministic match survives LLM disagreement | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P1 | learning-architecture routing tests cover decoys | education decoys |
| SPEC_CHANGES + L03 | 3.7 | CLASSIFY | verify MC golden IDs | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | MC golden IDs unrelated | none |
| SPEC_CHANGES + L03 | 3.8 | CLASSIFY | voice classifies once | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | no voice pipeline | none |
| SPEC_CHANGES + L03 | 3.9 | CLASSIFY | partial transcript not classified | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P1 | Slack bot handles incomplete transcription patterns | slack tests |
| SPEC_CHANGES + L03 | 3.10 | CLASSIFY | flag downstream override misclassified as signal collision | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | transfer as defect-source triage: curriculum vs checker vs source drift | defect class rule |
| SPEC_CHANGES + L04 | 4.1 | KNOWLEDGE | freshness reads per-entry interval | EVIDENCE RETRIEVE | adapt | include_in_lingua_viva_spec | P1 | evidence/register references need freshness/review cadence | evidence register |
| SPEC_CHANGES + L04 | 4.2 | KNOWLEDGE | freshness tie-break in retrieval | EVIDENCE RETRIEVE | adapt | include_in_lingua_viva_spec | P2 | only if LV adds retrieval; not Phase 0 | deferred |
| SPEC_CHANGES + L04 | 4.3 | KNOWLEDGE | rename namespace collision | EVIDENCE RETRIEVE | not_needed | exclude_as_bloat | P2 | MC repo cleanup only | none |
| SPEC_CHANGES + L04 | 4.4 | KNOWLEDGE | HR bias KL | EVIDENCE RETRIEVE | not_needed | exclude_as_bloat | P2 | HR unrelated | none |
| SPEC_CHANGES + L04 | 4.5 | KNOWLEDGE | marketing brand voice KL | EVIDENCE RETRIEVE | not_needed | exclude_as_bloat | P2 | marketing executor unrelated | none |
| SPEC_CHANGES + L04 | 4.6 | KNOWLEDGE | sales CRM schema KL | EVIDENCE RETRIEVE | not_needed | exclude_as_bloat | P2 | CRM unrelated | none |
| SPEC_CHANGES + L04 | 4.7 | KNOWLEDGE | freshness curve test | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P2 | reference freshness gate should be tested if implemented | gauntlet |
| SPEC_CHANGES | 5.x | CONTEXT | no master actions | CONTEXT BUILD | not_needed | exclude_as_bloat | P2 | no MC context changes to transfer | none |
| SPEC_CHANGES | 6.x | REASON | no master actions | DRAFT/REASON | not_needed | exclude_as_bloat | P2 | no MC reason changes to transfer | none |
| SPEC_CHANGES + L07 | 7.1 | EGRESS | LlamaGuard exit layer | PRIVACY/PUBLICATION SCAN | not_needed | exclude_as_bloat | P2 | too heavy; use tiny publication gate | none |
| SPEC_CHANGES + L07 | 7.2 | EGRESS | voice vendor allowlist | OPTIONAL RESEARCH | not_needed | exclude_as_bloat | P2 | no voice vendors | none |
| SPEC_CHANGES + L07 | 7.3 | EGRESS | PSA/RMM allowlist | OPTIONAL RESEARCH | not_needed | exclude_as_bloat | P2 | support connectors unrelated | none |
| SPEC_CHANGES + L07 | 7.4 | EGRESS | CRM allowlist | OPTIONAL RESEARCH | not_needed | exclude_as_bloat | P2 | CRM unrelated | none |
| SPEC_CHANGES + L07 | 7.5 | EGRESS | async connector egress wall | OPTIONAL RESEARCH | not_needed | exclude_as_bloat | P2 | no connector framework | none |
| SPEC_CHANGES + L07 | 7.6 | EGRESS | Teams signature verification | ORIGIN | not_needed | exclude_as_bloat | P2 | no Teams bridge in LV package | none |
| SPEC_CHANGES + L07 | 7.7 | EGRESS | WeasyPrint local asset fetcher | SYNTHESIZE/EXPORT | adapt | defer_for_operator_judgment | P1 | only needed if LV generates PDFs with WeasyPrint | render decision |
| SPEC_CHANGES + L07 | 7.8 | EGRESS | Teams unsigned payload test | ORIGIN | not_needed | exclude_as_bloat | P2 | no Teams bridge | none |
| SPEC_CHANGES + L08 | 8.1 | INTEGRITY | citation grounding validation | INTEGRITY CHECK | beneficial | include_in_lingua_viva_spec | P0 | claim/reference grounding is core | evidence gate |
| SPEC_CHANGES + L08 | 8.2 | INTEGRITY | reject mismatched quote offset | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | source quote/excerpt checks should fail closed | gauntlet |
| SPEC_CHANGES + L08 | 8.3 | INTEGRITY | accept exact offset match | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | source quote/excerpt positive fixture | gauntlet |
| SPEC_CHANGES | 9.x | SYNTHESIZE | no master actions | SYNTHESIZE/EXPORT | not_needed | exclude_as_bloat | P2 | no MC synth changes | none |
| SPEC_CHANGES + L10A | 10.1-10.6 | EXECUTE | action registry/domain whitelist fixes | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | MC action registry should not enter LV | none |
| SPEC_CHANGES + L10A | 10.7-10.14 | EXECUTE | support/sales/marketing/finance/hr/ops/RE/doc action YAML | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | domain actions unrelated; document action may be revisited only after source decision | none |
| SPEC_CHANGES + L10A | 10.15 | EXECUTE | connector executor | SYNTHESIZE/EXPORT | not_needed | exclude_as_bloat | P2 | connector bloat | none |
| SPEC_CHANGES + L10A | 10.16 | EXECUTE | render as governed action | SYNTHESIZE/EXPORT | adapt | defer_for_operator_judgment | P2 | useful only if LV adds generated exports | export contract |
| SPEC_CHANGES + L10D | 10.17-10.27 | EXECUTE | connector registry/vault/OAuth/resilience/PSA/CRM | ORIGIN/OPTIONAL RESEARCH | not_needed | exclude_as_bloat | P2 | explicit non-goal | none |
| SPEC_CHANGES + L10E | 10.28-10.33 | EXECUTE | business executors | DRAFT/REASON | not_needed | exclude_as_bloat | P2 | unrelated business logic | none |
| SPEC_CHANGES + L10F | 10.34 | EXECUTE | document rendering package | SYNTHESIZE/EXPORT | defer | defer_for_operator_judgment | P2 | maybe useful later; not Phase 0 | source/export decision |
| SPEC_CHANGES + L10F | 10.35 | EXECUTE | document templates tree | SYNTHESIZE/EXPORT | defer | defer_for_operator_judgment | P2 | only after manual generation source exists | source/export decision |
| SPEC_CHANGES + L10F | 10.36 | EXECUTE | jinja2 dependency | SYNTHESIZE/EXPORT | not_needed | exclude_as_bloat | P2 | defer dependency until generation need | none |
| SPEC_CHANGES + L10F | 10.37 | EXECUTE | weasyprint dependency | SYNTHESIZE/EXPORT | not_needed | exclude_as_bloat | P2 | defer dependency | none |
| SPEC_CHANGES + L10F | 10.38 | EXECUTE | docxtpl dependency | SYNTHESIZE/EXPORT | defer | defer_for_operator_judgment | P2 | relevant only if `.docx` generation becomes required | source/export decision |
| SPEC_CHANGES + L10F | 10.39 | EXECUTE | pypdf/pdfplumber inbound extraction | EVIDENCE RETRIEVE | reuse | reuse_existing_learning_architecture_surface | P1 | learning-architecture document parser already owns this pattern | parser tests |
| SPEC_CHANGES + L10G | 10.40-10.47 | EXECUTE | executable canvas manifests and workflow schema | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | MC canvas runtime only | none |
| SPEC_CHANGES + L10I | 10.48-10.68 | EXECUTE | action/connector/business/canvas tests | INTEGRITY CHECK | not_needed | exclude_as_bloat | P2 | tests are for excluded machinery | none |
| SPEC_CHANGES + L10I | 10.69-10.75 | EXECUTE | document rendering/ingest/watermark/adversarial tests | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | adapt as tiny artifact gauntlet, not full renderer tests | gauntlet |
| SPEC_CHANGES + L11 | 11.1 | STORE | knowledge gap logging | STORE/LOG | beneficial | include_in_lingua_viva_spec | P1 | `dev/lv_deferred_candidates.yaml` for unsupported claims/gaps | deferred file |
| SPEC_CHANGES + L11 | 11.2 | STORE | deal score history | STORE/LOG | not_needed | exclude_as_bloat | P2 | revenue artifact unrelated | none |
| SPEC_CHANGES + L11 | 11.3 | STORE | structured trace observations | STORE/LOG | adapt | include_in_lingua_viva_spec | P1 | revision log should record origin/defect/proof, not full MC trace | revision log |
| SPEC_CHANGES + L11 | 11.4 | STORE | trace observations omit sanitized query text | STORE/LOG | beneficial | include_in_lingua_viva_spec | P0 | do not store raw student/private text in LV logs | privacy gate |
| SPEC_CHANGES + L11 | 11.5 | STORE | flat fields stay populated transition test | STORE/LOG | not_needed | exclude_as_bloat | P2 | MC schema migration only | none |
| SPEC_CHANGES + L12 | 12.1 | DELIVER | TTS model ID | SYNTHESIZE/EXPORT | not_needed | exclude_as_bloat | P2 | voice output unrelated | none |
| SPEC_CHANGES + L12 | 12.2 | DELIVER | knowledge stale CLI | EVIDENCE RETRIEVE | adapt | include_in_lingua_viva_spec | P2 | optional tiny stale-reference report if checker built | gauntlet |
| SPEC_CHANGES + L12 | 12.3 | DELIVER | knowledge gaps CLI | STORE/LOG | adapt | include_in_lingua_viva_spec | P2 | optional local view of deferred candidates | gauntlet |

## Patent Readiness Verified Actions

| Source | ID | Layer | Summary | LV pipeline step | Applicability | Disposition | Priority | Proposed LV action / reason | Proof gate |
|---|---|---|---|---|---|---|---|---|---|
| PATENT_VERIFIED | P3.1 | CLASSIFY | eval checks `blocks_external` | PRIVACY/PUBLICATION SCAN | beneficial | include_in_lingua_viva_spec | P0 | privacy/publication gate must test sensitive artifacts | privacy fixture |
| PATENT_VERIFIED | P3.2 | CLASSIFY | add governance golden queries | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P1 | reuse education golden suite; add LV artifact cases only if needed | golden suite |
| PATENT_VERIFIED | P3.3-P3.6 | CLASSIFY | bypass resistance tests | PRIVACY/PUBLICATION SCAN | adapt | include_in_lingua_viva_spec | P1 | hostile publication/source fixtures | gauntlet |
| PATENT_VERIFIED | P5.1 | CONTEXT | integration test asserts context assembly | CONTEXT BUILD | adapt | include_in_lingua_viva_spec | P1 | source-grounded context must show framework/evidence inputs | matrix/evidence check |
| PATENT_VERIFIED | P6.1 | REASON | governance-only flag | INTEGRITY CHECK | not_needed | exclude_as_bloat | P2 | MC runtime mode not needed | none |
| PATENT_VERIFIED | P7.1 | EXIT | skip research in governance-only mode | OPTIONAL RESEARCH | adapt | include_in_lingua_viva_spec | P0 | external research never runs with private/student content | publication gate |
| PATENT_VERIFIED | P9.1 | SYNTHESIZE | structured governance report | SYNTHESIZE/EXPORT | adapt | include_in_lingua_viva_spec | P1 | produce publication review report if gauntlet fails | gauntlet report |
| PATENT_VERIFIED | P11.1-P11.6 | STORE | consensus in improvement circuit | STORE/LOG | not_needed | exclude_as_bloat | P2 | service-level circuit too heavy; human review status in register is enough | none |
| PATENT_VERIFIED | P11.7-P11.8 | STORE | boundary accuracy in improvement circuit | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | transfer as defect-class triage | defect class |
| PATENT_VERIFIED | P11.9-P11.14 | STORE | taxonomy as executable data structure | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P1 | education ontology already exists | ontology reference |
| PATENT_VERIFIED | P11.15 | STORE | patent evidence report from path records | CLAIM/EVIDENCE | adapt | include_in_lingua_viva_spec | P1 | convert to publication/IP readiness register, not patent report | evidence register |
| PATENT_VERIFIED | P12.1 | DELIVER | patent-evidence CLI | SYNTHESIZE/EXPORT | not_needed | exclude_as_bloat | P2 | patent CLI not needed | none |
| PATENT_VERIFIED | P12.2 | DELIVER | governance-only CLI flag | INTEGRITY CHECK | not_needed | exclude_as_bloat | P2 | MC runtime only | none |
| PATENT_VERIFIED | PC.1 | CROSS | full patent claim integration test | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | adapt as artifact gauntlet across inventory/evidence/privacy/freshness | gauntlet |
| PATENT_VERIFIED | PNA.1 | NONCODE | prior art matrix | CLAIM/EVIDENCE | defer | defer_for_operator_judgment | P2 | maybe useful for publication/IP positioning, not Phase 0 | operator decision |

## Patent Addendum Actions

| Source | ID | Layer | Summary | LV pipeline step | Applicability | Disposition | Priority | Proposed LV action / reason | Proof gate |
|---|---|---|---|---|---|---|---|---|---|
| PATENT_ADDENDUM | BUG-1 | STORE | KPI gates wired into MEASURE | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | artifact gates must actually run in gauntlet | gauntlet command |
| PATENT_ADDENDUM | BUG-2 | STORE | monotonicity guard bypass | STORE/LOG | adapt | include_in_lingua_viva_spec | P1 | append-only revision log should not silently rewrite history | append-only check |
| PATENT_ADDENDUM | ADD-1 | DELIVER | complete explain_trace | STORE/LOG | adapt | include_in_lingua_viva_spec | P1 | revision log entries need explainable decision/proof fields | revision schema |
| PATENT_ADDENDUM | ADD-2 | INTEGRITY | governance compliance quality eval | INTEGRITY CHECK | beneficial | include_in_lingua_viva_spec | P0 | publication safety and evidence compliance are P0 | gauntlet |
| PATENT_ADDENDUM | ADD-3 | DELIVER | surface unused trace fields | STORE/LOG | not_needed | exclude_as_bloat | P2 | MC trace report fields not needed | none |
| PATENT_ADDENDUM | ADD-4 | DELIVER | confidence lift report | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | classifier metric not central to LV package | none |
| PATENT_ADDENDUM | ADD-5 | STORE | latency in MEASURE | INTEGRITY CHECK | not_needed | exclude_as_bloat | P2 | performance metric not needed for artifact spec | none |
| PATENT_ADDENDUM | ADD-6 | STORE | journal provenance chain | STORE/LOG | beneficial | include_in_lingua_viva_spec | P1 | revision log should link source, defect, proof, and reviewer | revision schema |
| PATENT_ADDENDUM | ADD-7 | STORE | golden failure root-cause analysis | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | map failures to unsupported claim/source drift/privacy/measurement | defect class |
| PATENT_ADDENDUM | ADD-8 | STORE | golden checkpoint log | STORE/LOG | adapt | include_in_lingua_viva_spec | P2 | optional gauntlet run log | gauntlet log |
| PATENT_ADDENDUM | ADD-9 | CLASSIFY | deterministic reproducibility test | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P1 | education decoys/goldens already cover routing | golden suite |
| PATENT_ADDENDUM | ADD-10 | CLASSIFY | classification latency benchmark | WORKTYPE CLASSIFY | not_needed | exclude_as_bloat | P2 | runtime benchmark unnecessary | none |
| PATENT_ADDENDUM | ADD-11 | EXIT | one-way escalation invariant | PRIVACY/PUBLICATION SCAN | adapt | include_in_lingua_viva_spec | P0 | private/public decisions require human review | publication gate |
| PATENT_ADDENDUM | ADD-12 | CONTEXT | credential isolation test | PRIVACY/PUBLICATION SCAN | not_needed | exclude_as_bloat | P2 | no credentials in LV package | none |
| PATENT_ADDENDUM | ADD-13 | STORE | append-only trace integrity | STORE/LOG | beneficial | include_in_lingua_viva_spec | P1 | revision log append-only | append-only check |
| PATENT_ADDENDUM | ADD-14 | CLASSIFY | domain extensibility without retraining | WORKTYPE CLASSIFY | defer | defer_for_operator_judgment | P2 | only relevant if LV adds new worktypes | operator decision |

## Measurement Integrity Transfer

| Source | ID | Layer | Summary | LV pipeline step | Applicability | Disposition | Priority | Proposed LV action / reason | Proof gate |
|---|---|---|---|---|---|---|---|---|---|
| MEASUREMENT_INTEGRITY | MI-1 | INTEGRITY | distinguish system defect from measurement defect | INTEGRITY CHECK | beneficial | include_in_lingua_viva_spec | P0 | core checker-checks rule | defect class |
| MEASUREMENT_INTEGRITY | MI-2 | STORE | record instrument_that_found_it | STORE/LOG | beneficial | include_in_lingua_viva_spec | P1 | revision log field | revision schema |
| MEASUREMENT_INTEGRITY | MI-3 | STORE | record instrument_touched | STORE/LOG | beneficial | include_in_lingua_viva_spec | P1 | prevents self-validating checker changes | revision schema |
| MEASUREMENT_INTEGRITY | MI-4 | INTEGRITY | require independent_cross_check | INTEGRITY CHECK | beneficial | include_in_lingua_viva_spec | P0 | applies to rubrics/checkers/source parsers | proof gate |
| MEASUREMENT_INTEGRITY | MI-5 | INTEGRITY | system_defect rule | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | translate to curriculum_content/source defect | defect class |
| MEASUREMENT_INTEGRITY | MI-6 | INTEGRITY | measurement_defect rule | INTEGRITY CHECK | beneficial | include_in_lingua_viva_spec | P0 | assessment instrument defects cannot prove learning improvement | proof gate |
| MEASUREMENT_INTEGRITY | MI-7 | INTEGRITY | ambiguous rule | STORE/LOG | beneficial | include_in_lingua_viva_spec | P1 | ambiguous goes to deferred candidates | deferred file |
| MEASUREMENT_INTEGRITY | MI-8 | INTEGRITY | independent cross-check examples | INTEGRITY CHECK | beneficial | include_in_lingua_viva_spec | P0 | unchanged source/sample/human anchor | proof gate |
| MEASUREMENT_INTEGRITY | MI-9 | INTEGRITY | lean fixture worlds | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | tiny public/private/claim/source fixtures if checker built | gauntlet |
| MEASUREMENT_INTEGRITY | MI-10 | STORE | proposed code boundary | STORE/LOG | adapt | include_in_lingua_viva_spec | P1 | YAML/NDJSON and tiny checker only | file list |
| MEASUREMENT_INTEGRITY | MI-11 | SCOPE | out-of-scope auto reverts/heavy machinery | ALL | not_needed | exclude_as_bloat | P2 | reinforces minimum-code principle | non-goals |

## Classify Regression Source Triage Transfer

| Source | ID | Layer | Summary | LV pipeline step | Applicability | Disposition | Priority | Proposed LV action / reason | Proof gate |
|---|---|---|---|---|---|---|---|---|---|
| CLASSIFY_TRIAGE | CT-1 | TRIAGE | ontology_signal_defect -> fix_signal_collision | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P1 | education ontology owned by learning-architecture | ontology reference |
| CLASSIFY_TRIAGE | CT-2 | TRIAGE | downstream_classification_override -> fix_classification_override | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P1 | runtime classification owned by learning-architecture/MC | boundary doc |
| CLASSIFY_TRIAGE | CT-3 | TRIAGE | stale_or_incomplete_eval_artifact -> refresh_eval_artifact | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P1 | generated/manual/source drift should refresh artifact or mark stale | freshness gate |
| CLASSIFY_TRIAGE | CT-4 | TRIAGE | ambiguous -> diagnostic_spec | STORE/LOG | beneficial | include_in_lingua_viva_spec | P1 | ambiguous LV findings go to deferred candidates | deferred file |
| CLASSIFY_TRIAGE | CT-5 | TRIAGE | fix-class vocabulary | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P0 | translate to LV defect classes | defect class |
| CLASSIFY_TRIAGE | T1 | TEST | ontology defect fixture | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P2 | existing education tests owner | tests |
| CLASSIFY_TRIAGE | T2 | TEST | downstream override fixture | WORKTYPE CLASSIFY | reuse | reuse_existing_learning_architecture_surface | P2 | runtime owner | tests |
| CLASSIFY_TRIAGE | T3 | TEST | incomplete golden artifact fixture | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P2 | stale manual/source fixture | gauntlet |
| CLASSIFY_TRIAGE | T4 | TEST | mixed sources fixture | STORE/LOG | beneficial | include_in_lingua_viva_spec | P2 | ambiguous goes to deferred spec | deferred file |
| CLASSIFY_TRIAGE | T5 | TEST | analyze no longer hardcodes source | INTEGRITY CHECK | adapt | include_in_lingua_viva_spec | P2 | LV checker must not assume every failure is curriculum content | checker test |
| CLASSIFY_TRIAGE | CT-OOS-1 | SCOPE | avoid broad new eval suites | ALL | beneficial | include_in_lingua_viva_spec | P1 | keep tiny gates | non-goals |
| CLASSIFY_TRIAGE | CT-CLOSE | STORE | update deferred candidate/report | STORE/LOG | defer | defer_for_operator_judgment | P2 | choose file/report convention during implementation | operator decision |

## Optional Read Files

| Source | Finding | LV effect |
|---|---|---|
| PRE_CHANGE_ARCHITECTURE_BRIEF_2026-07-16.md | MC has 12-layer pipeline, routing authority, memory/ontology, eval and kaizen maps | confirms LV should have its own smaller pipeline |
| LAYERED_BUILD_LEDGER_2026-07-16.md | layered build fixed many MC-specific integration defects and logged proof gates | transfer the ledger habit as revision log, not the implementation details |
| FINAL_LAYERED_BUILD_REPORT_2026-07-16.md | final MC readiness emphasizes hardening, deferred candidates, proof gates | transfer deferred-candidate discipline and proof gates |
| deferred_spec_candidates.yaml | append-only deferred spec list | transfer as `dev/lv_deferred_candidates.yaml` |
