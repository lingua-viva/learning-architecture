# Lingua Viva Improvement Cycle Spec Idea Matrices - Grouped By System And Artifact

Date: 2026-07-30

Derived from:

- `dev/LV_SYSTEM_THING_OUTCOME_TAXONOMY_2026-07-30.md`
- `dev/HANDOFF_LINGUA_VIVA_2026-07-20.md`
- `dev/specs/SPEC_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`
- `dev/specs/SPEC_LV_GAP_SIGNAL_AUDIT_2026-07-26.md`
- `dev/specs/SPEC_LV_MEASUREMENT_DISTILLATION_2026-07-26.md`
- `dev/specs/SPEC_LV_EVAL_ARCHITECTURE_V1_2026-07-22.md`
- `dev/specs/SPEC_LV_DRIVE_WORKSPACE_2026-07-27.md`
- `dev/SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27.md`
- `dev/SPEC_LV_DRIVE_FINAL_HARDENING_2026-07-27.md`
- `dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md`
- `dev/SPEC_LV_GIR_VOICE_TONE_2026-07-29.md`
- `dev/SPEC_LV_GOLDEN_VOICE_LOOP_2026-07-30.md`
- `dev/SPEC_LV_VOICE_COMPANION_2026-07-29.md`
- `dev/BACKLOG_LV_FILEMAP_FOLLOWUPS_2026-07-27.md`
- `dev/REPORT_ARCHITECTURE_SWEEP_2026-07-18.md`
- `dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`
- `dev/reports/REPORT_SLACK_OPS_HARDENING_2026-07-27.md`
- `dev/INDEX.md`

This is the Lingua Viva equivalent of Mission Canvas `dev/IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30.md`. It groups useful spec ideas by the hard Lingua Viva system taxonomy and then by the artifact or thing each idea would improve.

Legend:

- `A` = directly useful to issue awareness, measurement, ranking, recursive improvement, or closing the observe→measure→fix loop.
- `B` = other unimplemented, partial, deferred, or review-worthy idea.
- Status is from local specs/reports and repo inspection, not a fresh full implementation audit.

## RTE - Runtime Execution (`RTE-SYS-001`)

### Artifact: Local-first query/runtime kernel

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A01 | A | Compute grounding/GIR inline at SYNTHESIZE and keep it on the permanent path record. | `PipelineResult`, `PathRecord`, `/api/query` response | `SPEC_LV_GIR_VOICE_TONE_2026-07-29.md` | Spec says post-hoc reconstruction existed; inline computation was the intended correction. |
| LV-A02 | A | Preserve the rule that runtime remains local-first and external calls default to zero. | query runtime / provider path | `MANIFEST.yaml`; `REPORT_ARCHITECTURE_SWEEP_2026-07-18.md` | Built as posture; any future external route needs explicit exit/integrity gates first. |
| LV-A03 | A | Keep eval/sweep modes non-mutating so tests do not train the product. | runtime eval mode / learned weights | `REPORT_ARCHITECTURE_SWEEP_2026-07-18.md` | Learned from Gate 3 sweep mutating weights/proposals. Needs to remain a gate invariant. |
| LV-A04 | A | Replace import-time environment constants with call-time/lazy resolution across runtime helpers. | config/provider/sanitizer/runtime path reads | `HANDOFF_LINGUA_VIVA_2026-07-20.md`; `REPORT_ARCHITECTURE_SWEEP_2026-07-18.md` | A real hermeticity bug was found/fixed once; remaining modules should be swept. |
| LV-B01 | B | Native LV pipeline replacement for deferred exit/integrity no-ops. | runtime pipeline boundary | `HANDOFF_LINGUA_VIVA_2026-07-20.md`; architecture sweep | Needed before any external routing; broader than immediate measurement loop. |

## EON - Education Ontology (`EON-SYS-001`)

### Artifact: Education ontology domains and candidate nodes

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A05 | A | Use gap-signal clusters to reveal recurring weak ontology nodes. | education ontology domains / `gap_signals.ndjson` | `SPEC_LV_GAP_SIGNAL_AUDIT_2026-07-26.md`; `SPEC_LV_MEASUREMENT_DISTILLATION_2026-07-26.md` | Built/read-side instruments exist; keep signals loop-visible. |
| LV-A06 | A | Replay open ontology candidates through today's engine to flag `possibly_resolved` candidates. | `ontology/proposals/CAND-*.yaml` | `SPEC_LV_MEASUREMENT_DISTILLATION_2026-07-26.md` | Human review only; never auto-discard. |
| LV-A07 | A | Rank ontology gaps by distinct sessions, not raw row counts, and annotate suspected harness bursts. | ontology gap ranking | `SPEC_LV_MEASUREMENT_DISTILLATION_2026-07-26.md` build correction | Protects ranking from machine-cadence false breadth. |
| LV-A08 | A | Treat OOV gap-signal family names as vocabulary drift. | gap-signal family set | `SPEC_LV_GAP_SIGNAL_AUDIT_2026-07-26.md` | Exact known-family matching; read-side only for now. |
| LV-A09 | A | Make learned weights load-bearing or formally demote them. | `ontology/learned_weights.yaml` | `HANDOFF_LINGUA_VIVA_2026-07-20.md`; architecture sweep | Current evidence says self-tuning is inert or low-value. |
| LV-B02 | B | Add lower-level taxonomy rows for every education ontology node. | LV taxonomy doc / ontology inventory | `LV_SYSTEM_THING_OUTCOME_TAXONOMY_2026-07-30.md` | Refinement work, useful after domains stabilize. |

## CUR - Curriculum / Knowledge (`CUR-SYS-001`)

### Artifact: Authoritative curriculum source and structured matrix

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A10 | A | Keep `.docx` authority separate from structured derivative YAML until owner promotion. | `Manuale_...docx`, `curriculum/lingua_viva_matrix.yaml` | artifact inventory; complete build spec | Core governance rule; prevents accidental source-of-truth drift. |
| LV-A11 | A | Surface curriculum source status and derivative freshness in the app. | curriculum/source status | `SPEC_LINGUA_VIVA_APP_COMPLETE_BUILD_2026-07-16.md`; source specs | Helps teachers know whether an answer is from authority or derivative. |
| LV-A12 | A | Add source citation visibility to generated activities and curriculum outputs. | activity/prepare outputs | complete build spec; P0 reports | Important for grounded teacher trust. |
| LV-A13 | A | Use filemap/source freshness checks to reveal stale local curriculum materials. | file map / local curriculum sources | `BACKLOG_LV_FILEMAP_FOLLOWUPS_2026-07-27.md` | Follow-up queued; source drift should feed improvement list. |
| LV-B03 | B | Let teachers propose curriculum adjustments as deferred candidates. | curriculum candidate queue | complete build spec | Product feature; keep governed and non-authoritative by default. |

## OBS - Observation / Student Lens (`OBS-SYS-001`)

### Artifact: Observe capture, classify, and lens update loop

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A14 | A | Close the teacher decision half of the flywheel: RTI confirm/defer, grouping, portfolio writes, gap detection, and help artifact endpoints. | observe→lens→act workflow | `HANDOFF_LINGUA_VIVA_2026-07-20.md`; P0 specs | Handoff says observe/propose is strong, action side is thin/partial. |
| LV-A15 | A | Ensure extraction/imported evidence updates a student lens only after teacher review and approval. | extraction review/write path | Drive workspace spec; extraction specs | Core trust rule; keep as invariant across Drive/local/Slack sources. |
| LV-A16 | A | Add gap-driven next-step proposals from observation patterns. | student lens / weekly recommendations | handoff; education module specs | Turns observed student data into ranked teacher work. |
| LV-A17 | A | Keep RTI tier changes as teacher-owned decisions with recorded disposition. | RTI decision record | UI wiring fixes; handoff | Built/partial; needs end-to-end confidence before multi-teacher use. |
| LV-A18 | A | Add portfolio write path or formally descope it to stop shipped-status overclaiming. | portfolio artifact / student record | handoff | Explicit open product decision. |
| LV-B04 | B | Student-facing surface to close observe→differentiate→re-observe from the learner side. | student-facing product surface | handoff | Important but explicitly sequenced after teacher/admin adoption signal. |

## EDU - Education Product Modules (`EDU-SYS-001`)

### Artifact: Teacher/admin product modules

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A19 | A | Convert admin deferred states into real evidence, capacity, and trend analytics once data prerequisites exist. | admin/coordinator modules | handoff; architecture sweep | Currently mostly explicit deferred state. |
| LV-A20 | A | Keep parent drafts behind safety gates and improve warmth/voice through Claudia/education lens hardening. | parent report draft | Claudia lens reports; parent safety tests | Built/hardened pattern; keep measured. |
| LV-A21 | A | Add module-level app-reality checks for each teacher P0 experience. | teacher module surface | P0 improvement cycle report | Live-run P0 method found real gaps; should remain repeatable. |
| LV-A22 | A | Treat daily file as a convergence surface for Slack ops, Drive new-file metadata, and local source changes. | daily file / daily brief | Drive self-service auth spec; Slack ops specs | Approved pattern; touches multiple lanes and needs ownership boundaries. |
| LV-B05 | B | Coordinator-facing Evidence/Capacity/Trends as full product features. | admin tier | P0 prompt; handoff | Deferred until accumulated consent-aware teacher data exists. |

## PRV - Privacy / Governance (`PRV-SYS-001`)

### Artifact: Privacy, role, and export gates

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A23 | A | Add server-side auth/role enforcement before any second real user. | roles/access boundary | `HANDOFF_LINGUA_VIVA_2026-07-20.md` | Current role is client-side bootstrap; hard blocker for multi-user deployment. |
| LV-A24 | A | Replace observe-once access control with an admin-grantable roster/co-teacher model. | `src/education/access_control.py` | handoff | Current access model is single-teacher bootstrap. |
| LV-A25 | A | Build real exit/integrity gates before enabling any external routing. | exit/integrity governance | handoff; architecture sweep | Safe today only because external routing is disabled. |
| LV-A26 | A | Keep broad Drive permission copy honest and visible when OAuth scope cannot be narrow. | Drive OAuth trust copy | Drive self-service auth spec | Required because Google may show broad Drive permission. |
| LV-A27 | A | Treat publication-readiness Phase 1 as a governance improvement item. | publication safety / public artifacts | handoff; publication audit specs | Phase 0 audit exists; follow-through remains open. |
| LV-B06 | B | Full multi-user authentication and admin account system. | app auth system | handoff | Product/platform work; required before multi-teacher pilot. |

## CON - Connectors / Sources (`CON-SYS-001`)

### Artifact: Google Drive connector/workspace

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A28 | A | Move Drive connection from Settings into the daily Sources/Drive surface. | Drive workspace UI | `SPEC_LV_DRIVE_WORKSPACE_2026-07-27.md` | Built as Phase 1 per spec; keep as IA rule. |
| LV-A29 | A | Add self-service Google sign-in, status polling, disconnect, and stored-token death path. | Drive OAuth flow | `SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27.md` | Spec approved for current window; important for non-operator use. |
| LV-A30 | A | Add metadata-only "New from Drive" detection without auto-importing content. | Drive new-file signal / daily file | Drive self-service auth spec; Drive workspace spec | Approved as privacy-preserving Phase 2. |
| LV-A31 | A | Add Drive export/import retention policy and file size cap. | `drive_exports/`, `drive_imports/` | `SPEC_LV_DRIVE_FINAL_HARDENING_2026-07-27.md` | Hardening item to prevent unbounded local accumulation and bad imports. |
| LV-A32 | A | Build deliverables registry before share-back of non-lens artifacts. | Drive share-back / deliverables | Drive workspace spec | Explicitly not in Phase 1; needed before expanding share-back. |
| LV-B07 | B | Revisit `drive.file` + Google Picker as narrower-scope OAuth alternative. | Drive connector | Drive self-service auth spec | Follow-up; not needed for current privacy posture. |

### Artifact: Slack ops connector/workflow packs

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A33 | A | Preserve injection-safe rendering for Slack event fields in daily files. | Slack daily file renderer | `REPORT_SLACK_OPS_HARDENING_2026-07-27.md` | Fixed; should remain a regression check. |
| LV-A34 | A | Keep Slack lifecycle failures non-fatal and visible. | Slack scheduler/lifecycle | Slack hardening report | Fixed one failure that killed scheduling; preserve as health signal. |
| LV-A35 | A | Make unmapped Slack users honest: no fabricated teacher IDs, no junk daily files. | Slack teacher map / daily files | Slack hardening report | Fixed; important for multi-teacher readiness. |
| LV-A36 | A | Add idempotency/replay protections and daily rotation re-render checks. | Slack ops records / daily file | Slack hardening report | Fixed; should remain part of ops regression suite. |
| LV-A37 | A | Treat `/api/ops/records` as an audit surface, not backend-only forever. | ops records audit UI | Slack hardening report | Report notes backend-only; good candidate for visible issue awareness. |
| LV-B08 | B | Additional Slack ops workflow packs beyond current approved packs. | `config/ops_packs/` | Slack ops V2 specs | Product expansion after current packs prove stable. |

### Artifact: Unified Sources surface / file map

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A38 | A | Unify Drive, Slack, local, and curriculum folders into a Sources primary-nav model. | Sources IA / filemap | Drive workspace spec; filemap backlog | Directional Phase 3; useful because source awareness is central to improvement. |
| LV-A39 | A | Add stat-only filemap stale checks like "New from Drive" for local folders. | filemap freshness signal | `BACKLOG_LV_FILEMAP_FOLLOWUPS_2026-07-27.md` | Queued follow-up; should feed daily file/source status. |
| LV-A40 | A | Keep bad parse, guard trip, import failure, and missing-file paths landing on shipped bundle behavior. | live-layer/source read path | live-layer read path prompt | Prevents source failures from only being caught in source checkout. |

## ACT - Action / Approval (`ACT-SYS-001`)

### Artifact: Action plans and teacher approval

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A41 | A | Keep "system proposes, teacher confirms" as the common action pattern. | action plan preview/approve/reject | handoff; complete build spec | Strong product invariant; still incomplete in some teacher flows. |
| LV-A42 | A | Add action history/audit visibility for rejected and approved action plans. | action history / audit receipts | action tests; web routes | Helps teachers and support understand side-effect decisions. |
| LV-A43 | A | Ensure Drive/share/export actions include colleague-snapshot warnings and privacy checks. | share-back action | Drive workspace spec | Built for student lens share; extend only with deliverables registry. |
| LV-B09 | B | Broader executable action layer for education workflows. | action registry | complete build / action specs | Useful later; should follow approval and audit pattern. |

## EVA - Evaluation / Measurement (`EVA-SYS-001`)

### Artifact: Gap audit and measurement distillation

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A44 | A | Keep `lv audit` delta-first so historical WARNs do not become permanent noise. | `src/lingua_viva/gap_audit.py` | `SPEC_LV_GAP_SIGNAL_AUDIT_2026-07-26.md` | Built; baseline semantics are the key idea. |
| LV-A45 | A | Keep `lv distill` as the ranked human-review instrument over gap signals, candidates, and revision logs. | `src/lingua_viva/improvement_audit.py` | `SPEC_LV_MEASUREMENT_DISTILLATION_2026-07-26.md` | Built; read-only by default. |
| LV-A46 | A | Track proxy→live transitions by defect class. | revision log analytics | measurement distillation spec | Shows whether app reality is replacing proxy checks. |
| LV-A47 | A | Detect revision-log defect-class concentration/fragmentation only above volume floors. | revision log analytics | measurement distillation spec | Avoids fake structure in low-n data. |
| LV-A48 | A | Keep informational signal families separate from real walls in rankings. | gap ranking | measurement distillation correction | Prevents correct `skipped_research:self_sufficient` from outranking true failures. |

### Artifact: Layered eval architecture / golden workflows

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A49 | A | Maintain Layer 1-5 education evals: schema, retrieval, isolation, pedagogy goldens, and gauntlets. | `tests/evals/` | `SPEC_LV_EVAL_ARCHITECTURE_V1_2026-07-22.md`; taxonomy | Built in repo; should stay the backbone of improvement. |
| LV-A50 | A | Add golden voice loop into golden workflows and failure ranking. | golden workflow runner / voice fixture | `SPEC_LV_GOLDEN_VOICE_LOOP_2026-07-30.md` | Spec says failures should become same ranking stream as other golden failures. |
| LV-A51 | A | Repeat the live P0 experience sweep as a regression instrument. | P0 experience eval | P0 improvement cycle report | Live-run method found real gaps; should be preserved. |
| LV-B10 | B | UI/dashboard surfacing of voice-loop failures. | eval dashboard | golden voice loop spec | Explicitly out of scope in voice loop spec; later surfacing item. |

## AGV - Artifact Governance (`AGV-SYS-001`)

### Artifact: Artifact inventory, publication safety, and evidence register

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A52 | A | Keep artifact gauntlet and publication safety as release gates, not proof of educational efficacy. | `artifacts/inventory.yaml`, `doctor/lv_artifact_gauntlet.py` | artifact inventory; complete build spec | Prevents public/internal artifact overclaiming. |
| LV-A53 | A | Keep evidence register synchronized with public claims. | `claims/evidence_register.yaml` | complete build spec; publication audit | Important for public site and portfolio claims. |
| LV-A54 | A | Add status-drift checks so specs marked shipped cannot stay inconsistent with code. | `dev/INDEX.md`, specs/reports | handoff; built-to-shipped sync report | Repeated issue: specs say shipped while routes/features are partial. |
| LV-A55 | A | Keep dev INDEX complete and current as the spec corpus grows. | `dev/INDEX.md` | measurement distillation spec; INDEX | Missing specs were flagged; index drift hides work. |
| LV-B11 | B | Publication-readiness Phase 1 copy/content cleanup. | public portfolio/site artifacts | handoff; publication audit | Governance/product work; high priority if public launch is near. |

## HTH - Health / Doctor / Readiness (`HTH-SYS-001`)

### Artifact: Preflight, doctor, full health, support bundle

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A56 | A | Keep `lv preflight` under a strict fast budget and reserve slow instruments for health/audit. | preflight command | gap audit/distill specs; CLI | Prevents local developer/teacher startup checks from becoming too slow. |
| LV-A57 | A | Add route reachability and UI contract drift to preflight/readiness. | route/UI contracts | CLI preflight; built-to-shipped sync | Built; closes "built but not mounted" class. |
| LV-A58 | A | Keep doctor privacy WARNs explicit and non-blocking where source exclusions are intentional. | doctor support loop | handoff; doctor sweep | Fixed branch gate; privacy WARN remains reviewed/deferred. |
| LV-A59 | A | Add support bundle privacy scrub and manifest/git status into support outputs. | support bundle | complete build spec; doctor specs | Helps support without leaking private classroom data. |
| LV-A60 | A | Make every release gate executable, not only documented. | doctor/preflight/scripts | architecture sweep | LV lesson for itself and MC; keep named scripts for gates. |

## SRF - Surfaces / Interfaces (`SRF-SYS-001`)

### Artifact: Web/PWA/desktop/CLI surfaces

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A61 | A | Preserve route-reachability as a hard guard against backend-only shipped features. | API/UI surface contract | built-to-shipped sync; CLI preflight | Repeatedly useful for finding "built not mounted." |
| LV-A62 | A | Keep public UI states honest for deferred admin features. | admin surface | handoff; architecture sweep | Deferred with reasons is better than fake placeholders. |
| LV-A63 | A | Add direct tests for previously untested endpoints and keep endpoint smoke coverage current. | FastAPI route surface | architecture sweep | Direct tests were missing for several routes in earlier sweep. |
| LV-A64 | A | Make Drive/Sources daily surfaces use teacher language, not implementation language. | Sources/Drive UI | Drive workspace spec | Improves usability and reduces source confusion. |
| LV-A65 | A | Keep app startup behavior identical in source checkout and desktop bundle. | web/desktop surface | live-layer read path; desktop release reports | Prevents fixes that pass locally but fail packaged. |
| LV-B12 | B | Student-facing UI. | future student surface | handoff | Defer until teacher/admin adoption justifies it. |

## AGT - Agents / Skills (`AGT-SYS-001`)

### Artifact: Education lenses, Claudia lens, and skill packages

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A66 | A | Keep live-layer lens overrides readable from source and desktop bundle with deterministic precedence. | lens engine / live layer | live-layer read path prompt | Prevents bundle/source divergence. |
| LV-A67 | A | Continue Claudia lens repasses as a product-quality instrument for warmth, deficit language, and teacher fit. | Claudia/education lenses | Claudia lens reports | Proven useful in hardening teacher-facing copy. |
| LV-A68 | A | Add lens API/UI contract checks so lens promises do not drift. | lens UI/API contract | `SPEC_LV_LENS_UI_API_CONTRACT_2026-07-23.md` | Existing tests/specs; keep as improvement surface. |
| LV-B13 | B | Hot-reload, lens enable/disable, and template-editor UI. | lens management surface | live-layer read path prompt | Explicitly out of scope; later authoring UX. |

## MEM - Memory / Trace / Audit (`MEM-SYS-001`)

### Artifact: Trace, request log, revision log, gap-signal stores

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A69 | A | Keep raw query text out of trace storage; store hashes/metadata only. | trace storage | `MANIFEST.yaml`; privacy tests | Core local-first privacy invariant. |
| LV-A70 | A | Treat malformed NDJSON as counted/skipped, never audit-crashing. | gap/revision/audit stores | gap audit and distill specs | Important for append-only local logs. |
| LV-A71 | A | Append audit summaries separately from signal streams. | `gap_audit_summaries.ndjson`, `audit_summary.ndjson` | gap audit/distill specs | Prevents measured stream from being polluted by summaries. |
| LV-A72 | A | Add stable origin/session tags for eval harness signal writes. | gap signal records | measurement distillation correction | Not built in shared pipeline; would prevent harness-minted breadth. |
| LV-A73 | A | Record dispositions while auditing: PASS/FIX/DEFER/WARN. | revision log / reports | architecture sweep | Makes sweep outcomes machine-readable later. |

## VOC - Voice System (`VOC-SYS-001`)

### Artifact: STT, TTS, tone, voice companion, golden voice loop

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A74 | A | Use GIR to govern voice tone so ungrounded answers do not sound equally confident. | `voice_tone.py`, TTS payload | `SPEC_LV_GIR_VOICE_TONE_2026-07-29.md` | Highest-safety voice idea; LV uses smaller resolver than MC VoiceBridge. |
| LV-A75 | A | Add `tone_prefix` to `/api/voice/tts` before publication-safety and length checks. | TTS route / Rime request | GIR voice tone spec | Ensures spoken uncertainty is itself safety-checked. |
| LV-A76 | A | Golden voice loop should classify failures and feed them into the same improvement ranking stream. | golden voice loop / improvement audit | `SPEC_LV_GOLDEN_VOICE_LOOP_2026-07-30.md` | Spec direction; no separate voice silo. |
| LV-A77 | A | Keep synthetic pinned voice fixture as stable regression input. | `tests/fixtures/voice/golden_query.wav` | golden voice loop spec | Avoids privacy risk and nondeterministic real-user fixture drift. |
| LV-A78 | A | Keep Rime TTS behind publication/privacy safety gate, including student-name stripping. | TTS privacy gate | voice companion spec; voice tests | Built/tested; critical because audio can leak. |
| LV-B14 | B | Persistent voice companion sidebar and unified voice flow. | voice companion UI | `SPEC_LV_VOICE_COMPANION_2026-07-29.md` | Product completeness; useful but less core than voice measurement/tone. |
| LV-B15 | B | Advanced voice UX: reading-position highlighting and multi-turn voice. | voice UX | voice companion spec | Explicitly out of scope. |

## DLV - Delivery / Release Process (`DLV-SYS-001`)

### Artifact: Release, install, desktop, one-button update

| ID | Type | Idea | Artifact improved | Source(s) | Current status / note |
|---|---|---|---|---|---|
| LV-A79 | A | Keep desktop backend smoke using the exact installer dependency set. | desktop release workflow | desktop release workflow/report | Prevents source-env green, packaged app broken. |
| LV-A80 | A | Keep curl install test as an end-to-end public install gate. | `install.sh`, binary release | install-test workflow | Ensures stranger install path works. |
| LV-A81 | A | Pin live site/download buttons to verified release assets. | public site/download process | download button specs; built-to-shipped sync | Prevents site pointing at nonexistent assets. |
| LV-A82 | A | Keep signing/notarization secret diagnostics value-free but explicit. | signing workflow | check-signing-secrets workflow | Reduces contradictory manual secret checks. |
| LV-A83 | A | Keep one-button update conflict surface visible. | update process / desktop surface | one-button update specs/tests | Prevents silent failed updates. |
| LV-B16 | B | Full release notarization/signing maturity across all platforms. | desktop release process | release specs | Release trust work; important but not issue-awareness core. |

## Highest-Leverage Clusters After Grouping

| Priority | System / artifact cluster | Why it rises after grouping |
|---:|---|---|
| 1 | OBS + ACT + EDU: observe→lens→teacher decision | The product observes well, but the teacher action half is the main incomplete improvement flywheel. |
| 2 | EVA + MEM + EON: gap audit, distill, candidates, learned weights | LV already records useful signals; improvement depends on keeping them ranked, delta-aware, and free of harness noise. |
| 3 | CON + CUR + SRF: Sources/Drive/Slack/filemap convergence | Classroom reality enters LV through sources; source freshness and source UI are central to issue awareness. |
| 4 | PRV + HTH + DLV: multi-user/readiness/release gates | A second real user changes the risk model; auth, roster, exit gates, and install gates become blockers. |
| 5 | VOC + EVA + RTE: grounded voice and golden voice loop | Spoken output needs grounding-aware tone and voice failures need to become normal improvement evidence. |

## Coverage Notes

This grouped artifact is not a code audit and does not claim every item is still unimplemented. It is a spec-idea matrix: rows are ideas found in LV specs/reports that either directly help the improvement cycle (`A`) or remain useful for review (`B`). Items marked fixed are included when the idea should stay as a regression invariant or measurement surface.

