# Lingua Viva — System → Thing → Outcome Taxonomy

**Date**: 2026-07-30  
**Purpose**: Map the Lingua Viva repo from systems to reusable things to the outputs and outcomes they produce. This is a heuristic product/architecture taxonomy, not a code registry. It answers: "What is this thing, where does it belong, what does it produce, and why does it exist?"

**Scope**: `/home/mical/learning-architecture` only. This file is the Lingua Viva equivalent of Mission Canvas `dev/MC_SYSTEM_THING_OUTCOME_TAXONOMY_2026-07-15.md`, but it does not import MC's rows. Where LV reuses MC-shaped machinery, the row is still named and scored by its LV implementation.

---

## 0. Vocabulary

| Term | Definition | Industry-adjacent name | LV use |
|---|---|---|---|
| System | Durable capability area with ownership, gates, and improvement loop | subsystem / platform capability | Teacher Runtime, Education Ontology, Evaluation System |
| Education Domain | Pedagogical classification area | domain taxonomy / curriculum strand | teacher, student, assessment, curriculum, parent |
| Ontology Node | Classified unit of education/support work with signals and dependencies | task taxonomy node / route | education teacher/student/admin nodes |
| Curriculum Artifact | Durable curriculum source or derivative | curriculum map / unit plan / scope-sequence | `Manuale_...docx`, `lingua_viva_matrix.yaml` |
| Student Lens | Accumulated learner profile from observations and approved evidence | learner profile / student support record | per-student lens JSON/view |
| Teacher Lens | Accumulated teacher/context profile | practitioner profile / instructional lens | local-teacher lens |
| Knowledge Entry | Evidence item linked to ontology and teaching work | knowledge-base entry / retrieval object | IB curriculum, differentiation, RTI, trauma-informed entries |
| Source Record | Local/Drive/Slack/material record entering the system | source ledger row / evidence packet | Drive imports, observation source records |
| Connector | Authenticated bridge to an outside system | integration / connector | Google Drive, Slack, Rime, local Whisper |
| Action | Governed executable operation | command / approval-gated action | action plan preview/approve/reject, filemap operations |
| Skill | Reusable education capability package | playbook / capability | adaptive learning, curriculum workspace, Claudia convergence |
| Workflow | Stateful multi-step product path | workflow / state machine | Observe→Lens, Drive import→review, Slack ops setup |
| Artifact | Durable output from work | deliverable / record / output object | parent draft, support bundle, audit receipt, daily file |
| Gate | Deterministic pass/fail check | guardrail / policy gate | preflight, doctor, route reachability, privacy boundary |
| Eval | Measurement surface | benchmark / test harness | golden education eval, layer 1-5 eval suite, app reality tests |
| Outcome | Human or system-level result | user value / educational result | safer teacher decision, better lesson prep, clearer family communication |
| Process | Repeatable sequence required for the app to reach or run for a real user | release pipeline / install process | binary release, desktop release, one-button update, install test |

---

## 0.5 Row Identifier Scheme

Every row gets a unique ID derived from its values. Format: `{PILLAR}-{CLASS}-{SEQ}`.

**PILLAR**:

| Code | System | # |
|---|---|---|
| RTE | Runtime Execution | S01 |
| EON | Education Ontology | S02 |
| CUR | Curriculum / Knowledge | S03 |
| OBS | Observation / Student Lens | S04 |
| EDU | Education Product Modules | S05 |
| PRV | Privacy / Governance | S06 |
| CON | Connectors / Sources | S07 |
| ACT | Action / Approval | S08 |
| EVA | Evaluation / Measurement | S09 |
| AGV | Artifact Governance | S10 |
| HTH | Health / Doctor / Readiness | S11 |
| SRF | Surfaces / Interfaces | S12 |
| AGT | Agents / Skills | S13 |
| MEM | Memory / Trace / Audit | S14 |
| VOC | Voice System | S15 |
| DLV | Delivery / Release Process | S16 |

**CLASS**:

| Code | Thing class |
|---|---|
| SYS | System pillar |
| DOM | Education/core domain |
| NOD | Ontology node group |
| KLE | Knowledge entry set |
| ART | Artifact |
| LNS | Lens |
| SRC | Source record |
| CON | Connector |
| ACT | Action |
| SKL | Skill |
| WFL | Workflow |
| GTE | Gate |
| EVL | Eval |
| FLW | Flow pattern |
| PRC | Process |

**SEQ**: 3-digit sequence within each PILLAR-CLASS group, starting at 001.

Examples:

- `RTE-SYS-001` = Lingua Viva runtime execution system.
- `EON-DOM-001` = Education ontology teacher domain.
- `OBS-ART-001` = Student lens artifact.
- `DLV-PRC-001` = CLI binary release process.

The ID is derived, never decorative: system + thing class + order of appearance.

---

## 0.6 Completeness Scoring Rubric

Every row is scored 0-100 across 10 dimensions. The scoring is deliberately harsh. Strong repo-local implementation still scores below 80 unless a real external classroom user has validated the value.

| # | Dimension | Points | What 0 Means | What 10 Means |
|---|---|---|---|---|
| 1 | **Specified** | 0-10 | No spec. Just an idea. | Full spec with acceptance criteria, edge cases, and non-goals. |
| 2 | **Implemented** | 0-10 | No code. | Working code, all intended paths present. |
| 3 | **Tested** | 0-10 | No tests. | Unit + integration + failure-mode tests. |
| 4 | **Gated** | 0-10 | No automated check. | Blocks regressions in preflight, doctor, CI, or evals. |
| 5 | **Wired** | 0-10 | Not accessible. | Reachable through intended CLI/API/UI/desktop surface. |
| 6 | **Documented** | 0-10 | No docs. | User/dev docs, examples, troubleshooting. |
| 7 | **Loop-measured** | 0-10 | No improvement/audit measurement. | Measured by LV audit/eval/doctor/reports. |
| 8 | **Loop-optimized** | 0-10 | Never improved by a loop. | Hardened or improved through documented iteration. |
| 9 | **User-validated** | 0-10 | No external teacher/student used it for real work. | External classroom use measured. |
| 10 | **Market/Outcome-proven** | 0-10 | No proof of outcome advantage. | Evidence that LV improves educational/admin outcomes vs alternative. |

Score bands:

- **0**: PROPOSED — nothing built.
- **1-20**: SPECIFIED — spec exists, maybe partial code.
- **21-40**: BUILT — code works, some tests, not fully wired.
- **41-60**: GATED — tests/gates exist and at least one user-facing route exists.
- **61-80**: IMPROVING — loop-measured, hardened, and documented.
- **81-100**: VALIDATED — external users and outcome evidence exist.

Current ceiling: ~70. LV has strong local tests and hardening reports, but external classroom validation and market/outcome proof remain mostly zero in the repo evidence.

---

## 0.7 Master Scored Inventory

### System Pillars

| ID | Instance | Spec | Impl | Test | Gate | Wire | Doc | Meas | Opt | User | Out | **Total** |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RTE-SYS-001 | Native local-first runtime | 8 | 8 | 8 | 8 | 7 | 4 | 5 | 4 | 0 | 0 | **52** |
| EON-SYS-001 | Education/core ontology | 9 | 8 | 8 | 8 | 6 | 4 | 5 | 3 | 0 | 0 | **51** |
| CUR-SYS-001 | Curriculum + knowledge evidence | 8 | 8 | 7 | 7 | 7 | 5 | 4 | 3 | 0 | 0 | **49** |
| OBS-SYS-001 | Observation + student lens loop | 9 | 8 | 8 | 8 | 8 | 4 | 6 | 4 | 0 | 0 | **55** |
| EDU-SYS-001 | Teacher/admin education product modules | 8 | 7 | 7 | 6 | 7 | 3 | 4 | 3 | 0 | 0 | **45** |
| PRV-SYS-001 | Privacy + governance | 9 | 8 | 8 | 8 | 8 | 4 | 5 | 4 | 0 | 0 | **54** |
| CON-SYS-001 | Connectors + source ingestion | 8 | 7 | 7 | 6 | 7 | 3 | 4 | 4 | 0 | 0 | **46** |
| ACT-SYS-001 | Action + approval system | 7 | 7 | 7 | 6 | 6 | 3 | 3 | 2 | 0 | 0 | **41** |
| EVA-SYS-001 | Eval + measurement system | 9 | 8 | 9 | 8 | 6 | 4 | 6 | 4 | 0 | 0 | **54** |
| AGV-SYS-001 | Artifact governance + publication safety | 8 | 7 | 7 | 7 | 6 | 5 | 5 | 4 | 0 | 0 | **49** |
| HTH-SYS-001 | Health, doctor, preflight, readiness | 9 | 8 | 8 | 9 | 8 | 4 | 6 | 5 | 0 | 0 | **57** |
| SRF-SYS-001 | Web/PWA/desktop/CLI surfaces | 8 | 8 | 8 | 7 | 8 | 4 | 4 | 4 | 0 | 0 | **51** |
| AGT-SYS-001 | Agents + skills | 7 | 6 | 5 | 4 | 5 | 4 | 2 | 2 | 0 | 0 | **35** |
| MEM-SYS-001 | Memory, traces, request/audit logs | 8 | 8 | 7 | 7 | 7 | 3 | 5 | 3 | 0 | 0 | **48** |
| VOC-SYS-001 | Voice STT/TTS/tone system | 8 | 7 | 7 | 6 | 7 | 3 | 4 | 3 | 0 | 0 | **45** |
| DLV-SYS-001 | Delivery/release/install process | 8 | 8 | 7 | 8 | 7 | 5 | 5 | 5 | 0 | 0 | **53** |

### High-Value Thing Inventory

| ID | Instance | Spec | Impl | Test | Gate | Wire | Doc | Meas | Opt | User | Out | **Total** |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EON-DOM-001 | Education ontology domains | 9 | 8 | 8 | 8 | 6 | 4 | 5 | 3 | 0 | 0 | **51** |
| CUR-ART-001 | Authoritative curriculum manual `.docx` | 8 | 6 | 5 | 6 | 4 | 6 | 4 | 3 | 0 | 0 | **42** |
| CUR-ART-002 | Structured curriculum matrix YAML | 8 | 8 | 7 | 7 | 7 | 5 | 4 | 3 | 0 | 0 | **49** |
| OBS-ART-001 | Student lens | 9 | 8 | 8 | 8 | 8 | 4 | 6 | 4 | 0 | 0 | **55** |
| OBS-WFL-001 | Observe capture -> classify -> lens update | 9 | 8 | 8 | 8 | 8 | 4 | 6 | 4 | 0 | 0 | **55** |
| EDU-WFL-001 | Teacher planning/preparation workflow | 8 | 7 | 7 | 6 | 7 | 3 | 4 | 3 | 0 | 0 | **45** |
| EDU-WFL-002 | RTI/tier proposal and decision workflow | 8 | 7 | 7 | 6 | 6 | 3 | 4 | 3 | 0 | 0 | **44** |
| CON-CON-001 | Google Drive connector/workspace | 8 | 7 | 7 | 6 | 7 | 4 | 4 | 4 | 0 | 0 | **47** |
| CON-CON-002 | Slack ops connector/workflow packs | 8 | 7 | 7 | 6 | 7 | 4 | 4 | 4 | 0 | 0 | **47** |
| VOC-CON-001 | Local Whisper STT | 8 | 7 | 7 | 6 | 7 | 3 | 4 | 3 | 0 | 0 | **45** |
| VOC-CON-002 | Rime TTS with privacy gate | 8 | 7 | 7 | 6 | 7 | 3 | 4 | 3 | 0 | 0 | **45** |
| EVA-EVL-001 | Layered education eval architecture | 9 | 8 | 9 | 8 | 6 | 4 | 6 | 4 | 0 | 0 | **54** |
| HTH-GTE-001 | `lv preflight` | 9 | 8 | 8 | 9 | 8 | 4 | 6 | 5 | 0 | 0 | **57** |
| HTH-GTE-002 | Doctor support loop | 9 | 8 | 8 | 8 | 8 | 5 | 6 | 5 | 0 | 0 | **57** |
| SRF-ART-001 | Web/PWA teacher app | 8 | 8 | 8 | 7 | 8 | 4 | 4 | 4 | 0 | 0 | **51** |
| SRF-ART-002 | Electron desktop shell/setup wizard | 8 | 8 | 7 | 8 | 8 | 4 | 4 | 5 | 0 | 0 | **52** |
| DLV-PRC-001 | CLI binary release process | 8 | 8 | 7 | 8 | 7 | 5 | 5 | 5 | 0 | 0 | **53** |
| DLV-PRC-002 | Desktop release process | 8 | 8 | 7 | 8 | 7 | 5 | 5 | 5 | 0 | 0 | **53** |

---

## 1. System Pillar Taxonomy

| # | System | Thing class | Core thing(s) | Where | Input | Mechanism | Output | Desired outcome | Proof / gate |
|---|---|---|---|---|---|---|---|---|---|
| S01 | Runtime Execution | System | local-first query/runtime kernel | `src/lingua_viva/`, `src/pipeline.py`, `src/provider_config.py` | teacher query/context | ontology/context/model routing + education execution | response + trace + local artifact | teacher gets useful help without unsafe external leakage | pytest, health, query tests |
| S02 | Education Ontology | System | 111 nodes / 25 domains, education domains | `ontology/` | query, observation, source | signal scoring, education domain routing | classified education work | know what teaching/admin work is being asked | ontology tests, golden eval |
| S03 | Curriculum / Knowledge | System | manual, structured matrix, KL entries | `Manuale_...docx`, `curriculum/`, `knowledge/` | curriculum question/source | retrieval, matrix lookup, evidence tiers | grounded curriculum context | curriculum stays coherent and citable | knowledge tests, publication audit |
| S04 | Observation / Student Lens | System | observation capture, student lens, RTI signals | `src/education/observation_capture.py`, `student_lens.py`, `src/lingua_viva/student_lens_writer.py` | teacher observation / evidence | capture, classify, approve, update lens | student lens + support signal | teachers see learner needs over time | observation/lens/eval tests |
| S05 | Education Product Modules | System | planning, differentiation, assessment, parent report, trend analysis | `src/education/` | teacher/admin task | module-specific deterministic logic | activity, guide, report, recommendation | daily teaching work gets lighter and safer | module tests |
| S06 | Privacy / Governance | System | privacy scan, injection guard, publication safety, trust | `src/lingua_viva/privacy.py`, `governance.py`, `injection_guard.py`, `governance/` | student/private content, output | local-first gates, redaction, trust checks | allowed/blocked/audited result | student data stays local and explainable | privacy/gov tests |
| S07 | Connectors / Sources | System | Drive, Slack, filemap, source records, local docs | `src/lingua_viva/google_drive_*`, `slack_*`, `filemap.py`, `src/web.py` | Drive folder, Slack ops text, local folder | import, classify, local copy, review | source record / daily file / extracted evidence | classroom materials enter LV with teacher control | connector/app tests |
| S08 | Action / Approval | System | action plans, approval/reject/history, governed export | `src/lingua_viva/actions.py`, `src/web.py` | proposed side effect | preview, teacher approval, audit | approved action / rejection / receipt | system proposes, teacher decides | action-plan tests |
| S09 | Evaluation / Measurement | System | goldens, layered evals, gauntlets, improvement audit | `tests/`, `tests/evals/`, `src/lingua_viva/*audit.py` | system behavior, synthetic fixtures | deterministic probes and scoring | pass/fail + gap signals | know if claims still hold | pytest, eval suite |
| S10 | Artifact Governance | System | inventory, evidence register, publication safety, source ledger | `artifacts/`, `claims/`, `governance/`, source ledgers | repo/public artifacts | status/risk checks, publication rules | findings + release constraints | public/internal artifacts do not overclaim | artifact gauntlet, publication tests |
| S11 | Health / Doctor / Readiness | System | preflight, doctor, support bundle, route reachability | `src/lingua_viva/cli.py`, `doctor/support_loop/`, `scripts/` | current repo/runtime | structural checks, privacy checks, app routes | OK/WARN/FIXABLE/BLOCKED | know if LV is safe to run/support now | `lv preflight`, doctor, CI |
| S12 | Surfaces / Interfaces | System | CLI, FastAPI, static app, PWA, desktop shell | `src/web.py`, `static/`, `desktop/`, `docs/` | teacher/user request | API routes + frontend + wrapper | teacher UI, PWA, desktop app, public site | usable local teacher product | UI contract, route reachability, smoke tests |
| S13 | Agents / Skills | System | intent agents, education skills, lenses | `agents/`, `skills/`, `lenses/` | classified intent/context | prompt/skill/lens activation | role-aware output | right education reasoning posture | skill/lens tests |
| S14 | Memory / Trace / Audit | System | traces, request log, privacy log, path records, activity | `memory/`, `src/lingua_viva/traces.py`, `request_log.py`, `privacy_log.py`, `activity.py` | run events/outcomes | append-only local persistence | trace/audit/activity records | every answer/action can be explained | trace/request/privacy tests |
| S15 | Voice System | System | STT, TTS, voice tone, voice companion, voice fixture | `src/lingua_viva/voice_stt.py`, `voice_tone.py`, `src/web.py`, `static/`, `tests/fixtures/voice/` | teacher speech / response text | local STT, Rime TTS, tone prefix, privacy gate | transcript / spoken response | teachers can operate hands-free without unsafe speech | voice tests, voice specs |
| S16 | Delivery / Release Process | Process system | installer, binary release, desktop release, GitHub Pages | `.github/workflows/`, `install.sh`, `install.ps1`, `desktop/`, `docs/` | commit/tag/user install | CI build, smoke, sign/notarize, install test | binary, desktop app, public site | stranger can install and run LV | release workflows, install-test |

---

## 2. Education Ontology Things

| System | Thing class | Instance | Where | What it is for | Output | Desired outcome | Cross-domain? |
|---|---|---|---|---|---|---|---|
| Education Ontology | Domain | teacher | `ontology/education/teacher.yaml` | teacher planning/observation support | teacher route | classroom work classified correctly | yes |
| Education Ontology | Domain | student | `ontology/education/student.yaml` | learner profile and support needs | student route | observations become learner understanding | yes |
| Education Ontology | Domain | assessment | `ontology/education/assessment.yaml` | formative/summative/RTI decisions | assessment route | assessment support is pedagogically grounded | yes |
| Education Ontology | Domain | curriculum | `ontology/education/curriculum.yaml` | curriculum design and unit planning | curriculum route | IB/Reggio/language work stays coherent | yes |
| Education Ontology | Domain | parent | `ontology/education/parent.yaml` | family communication | parent route | drafts are safe and useful | yes |
| Education Ontology | Domain | planning | `ontology/education/planning.yaml` | lesson/activity planning | planning route | teacher prep becomes structured | yes |
| Education Ontology | Domain | admin | `ontology/education/admin.yaml` | coordinator/admin work | admin route | operational work classified separately from teaching | partly |
| Education Ontology | Domain | infrastructure | `ontology/education/infrastructure.yaml` | school/system support | infrastructure route | system/admin needs stay visible | partly |
| Education Ontology | Domain | learner | `ontology/education/learner.yaml` | learner-facing/learner model work | learner route | eventual student-facing work has a place | partly |
| Education Ontology | Core domains | intents/data/governance/work/deployment/legal | `ontology/core/` | shared non-education routing | core route | generic tasks remain governed | yes |
| Education Ontology | Proposals | candidate nodes | `ontology/proposals/` | proposed ontology additions | candidate YAML | gaps enter governed review | yes |
| Education Ontology | Learned weights | signal weights | `ontology/learned_weights.yaml` | adapt routing from outcomes | adjusted signal weights | classifier can improve from use | yes |

---

## 3. Curriculum / Knowledge Things

| System | Thing class | Instance | Where | Input | Mechanism | Output | Desired outcome | Proof / gate |
|---|---|---|---|---|---|---|---|---|
| Curriculum / Knowledge | Curriculum artifact | authoritative manual draft | `Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` | curriculum owner draft | human-authored source | authoritative current draft | curriculum source remains controlled | artifact inventory |
| Curriculum / Knowledge | Curriculum artifact | structured matrix | `curriculum/lingua_viva_matrix.yaml` | extracted curriculum structure | YAML matrix | grade/unit/strand data | app can navigate curriculum | curriculum tests |
| Curriculum / Knowledge | Knowledge entry set | IB curriculum | `knowledge/education/curriculum_ib.yaml` | curriculum route | evidence-tiered entries | curriculum context | IB-aware planning | knowledge tests |
| Curriculum / Knowledge | Knowledge entry set | differentiation | `knowledge/education/differentiation.yaml` | learner needs | evidence-tiered entries | differentiation context | better adaptation | knowledge tests |
| Curriculum / Knowledge | Knowledge entry set | multilingual observation | `knowledge/education/multilingual_observation.yaml` | observation work | evidence-tiered entries | language-observation context | better multilingual interpretation | knowledge tests |
| Curriculum / Knowledge | Knowledge entry set | RTI assessment | `knowledge/education/rti_assessment.yaml` | support-tier work | evidence-tiered entries | RTI context | safer tier recommendations | RTI/eval tests |
| Curriculum / Knowledge | Knowledge entry set | trauma-informed | `knowledge/education/trauma_informed.yaml` | sensitive support work | evidence-tiered entries | caution context | avoid harmful framing | safety tests |
| Curriculum / Knowledge | Source reference | CEFR and Italian standards refs | `references/` | external standards | local reference files | standard context | curriculum stays aligned | publication review |

---

## 4. Observation / Student Lens Things

| System | Thing class | Instance | Where | Input | Mechanism | Output | Desired outcome | Proof / gate |
|---|---|---|---|---|---|---|---|---|
| Observation / Student Lens | Artifact | student lens | `src/education/student_lens.py`, `src/lingua_viva/student_lens_writer.py` | observations/evidence | aggregation + guarded write | learner profile | teacher sees patterns over time | student lens tests |
| Observation / Student Lens | Workflow | observe capture | `src/education/observation_capture.py`, `/api/observe/capture` | quick teacher note | capture + classify + store | observation record | low-friction classroom capture | observation tests |
| Observation / Student Lens | Workflow | observe classify | `/api/observe/classify` | observation text/categories | classification guidance | structured proposal | observations become actionable | observe classify tests |
| Observation / Student Lens | Artifact | RTI decision record | `/api/students/{id}/rti/decision`, `/api/students/{id}/rti` | teacher decision | confirm/defer/update | tier decision/update | system proposes, teacher decides | RTI tests |
| Observation / Student Lens | Artifact | student roster | `/api/students`, local store | student metadata | local store | roster/list | teacher can attach evidence to students | student tests |
| Observation / Student Lens | Artifact | support summary | `/api/students/support-summary` | lens data | summarization | support summary | support needs visible | support tests |
| Observation / Student Lens | Workflow | extraction review/write path | `src/lingua_viva/extraction_engine.py`, `/api/extraction/*` | source document | extract -> review -> approve | proposed/writeable observations | evidence enters lens only after review | extraction tests |

---

## 5. Education Product Module Things

| System | Thing class | Instance | Where | Input | Mechanism | Output | Desired outcome | Proof / gate |
|---|---|---|---|---|---|---|---|---|
| Education Product Modules | Module | assessment generator | `src/education/assessment_generator.py` | curriculum/skill target | generator logic | assessment artifact | faster assessment prep | tests |
| Education Product Modules | Module | content differentiator | `src/education/content_differentiator.py` | lesson/student needs | adaptation logic | differentiated content | learner-appropriate tasks | tests |
| Education Product Modules | Module | teacher guide | `src/education/teacher_guide.py` | lesson/unit | guide builder | teaching guide | prep support | tests |
| Education Product Modules | Module | parent report | `src/education/parent_report.py` | lens/observation data | guarded drafting | parent-facing draft | safer family communication | parent report safety gate |
| Education Product Modules | Module | morning/daily brief | `src/education/morning_brief.py`, `daily_file.py` | schedule/source records | summarization | daily file/brief | day starts with relevant context | daily tests |
| Education Product Modules | Module | weekly recommendation | `src/education/weekly_recommendation.py` | student/lens trends | recommendation logic | weekly next step | intervention loop continues | tests |
| Education Product Modules | Module | trend analysis | `src/education/trend_analysis.py` | observations over time | trend extraction | trend report | patterns become visible | tests |
| Education Product Modules | Module | school ethos | `src/education/ethos.py`, `lenses/education/school-ethos.yaml` | school values | ethos lens/context | ethos-aware output | product voice fits school | ethos tests |
| Education Product Modules | Module | admin metrics | `src/lingua_viva/admin_metrics.py` | aggregate app/student data | metrics computation | admin view data | coordinator sees system state | admin tests |

---

## 6. Privacy / Governance Things

| System | Thing class | Instance | Where | Input | Mechanism | Output | Desired outcome | Proof / gate |
|---|---|---|---|---|---|---|---|---|
| Privacy / Governance | Gate | student data local boundary | `src/lingua_viva/privacy.py`, tests | student/private data | local-first rules | allowed/blocked/redacted | student data stays local | `test_student_data_stays_local.py` |
| Privacy / Governance | Gate | injection guard | `src/lingua_viva/injection_guard.py` | imported/user text | prompt-injection checks | blocked/sanitized text | source content cannot hijack system | injection tests |
| Privacy / Governance | Gate | publication safety | `governance/publication_safety.yaml`, `src/lingua_viva/publication.py` | public/draft content | safety rules | publish allowed/blocked | public claims stay controlled | publication tests |
| Privacy / Governance | Artifact | privacy event log | `src/lingua_viva/privacy_log.py`, `~/.lingua-viva/privacy_events.ndjson` | privacy event | append-only event log | privacy events | teacher can inspect privacy behavior | privacy log tests |
| Privacy / Governance | Artifact | governance trust view | `/api/governance/trust` | current trust state | trust summary | trust payload | safety is visible in app | trust API tests |
| Privacy / Governance | Workflow | observation export gate | `/api/governance/observation-export` | export request | policy/gate check | export decision | export only after governance check | governance tests |

---

## 7. Connectors / Source Things

| System | Thing class | Instance | Where | Input | Mechanism | Output | Desired outcome | Proof / gate |
|---|---|---|---|---|---|---|---|---|
| Connectors / Sources | Connector | Google Drive | `src/lingua_viva/google_drive_integration.py`, `google_drive_oauth.py` | Drive folder/file | OAuth/local import/share-back | local copy/source record/export | shared classroom materials enter LV safely | Drive tests |
| Connectors / Sources | Connector | Slack app / events | `src/lingua_viva/slack_integration.py`, `slack_socket.py`, `src/education/slack_bot.py` | Slack events/messages | Slack bot/event bridge | observation/ops record | daily signals captured from Slack | Slack tests |
| Connectors / Sources | Connector | Slack ops packs | `config/ops_packs/`, `src/education/ops_*` | school ops messages | pack classifier/rules | daily ops file/reclassifications | logistics are structured and reviewable | ops tests |
| Connectors / Sources | Source ledger | source records | `/api/sources/status`, `/api/sources/records`, `/api/sources/observations` | local/Drive/Slack sources | registry/read path | source status/records | sources stay inspectable | source ledger tests |
| Connectors / Sources | Artifact | file map | `src/lingua_viva/filemap.py`, `/api/filemap*` | local folder/files | scan, confirm, assign, exclude | curriculum file map | local materials become navigable | filemap tests |
| Connectors / Sources | Connector | local document ingestion | `src/education/document_*`, `src/lingua_viva/ingest.py` | PDF/doc/local content | parse/retrieve/store | document record/content | classroom docs become usable | document tests |

---

## 8. Action / Approval Things

| System | Thing class | Instance | Where | Input | Mechanism | Output | Desired outcome | Proof / gate |
|---|---|---|---|---|---|---|---|---|
| Action / Approval | Action | action plan preview | `/api/action-plans/preview`, `src/lingua_viva/actions.py` | proposed change/action | risk/preview builder | action plan preview | teacher sees effects before approval | action tests |
| Action / Approval | Action | action plan approve | `/api/action-plans/approve` | preview id/decision | approval write path | approved action result | side effects require consent | action tests |
| Action / Approval | Action | action plan reject | `/api/action-plans/reject` | preview id/reason | rejection record | rejected plan | unsafe/unwanted changes are recorded | action tests |
| Action / Approval | Artifact | action history | `/api/actions/history`, `/api/action-plans/history` | past actions | history query | action log | work remains auditable | history tests |
| Action / Approval | Action | filemap operations | `/api/filemap/scan`, `/confirm`, `/assign`, `/exclude`, `/clear` | file/folder intent | local filemap mutation | filemap update | source organization stays teacher-controlled | filemap tests |

---

## 9. Eval / Gate Things

| System | Thing class | Instance | Where / command | Measures | Output | Desired outcome |
|---|---|---|---|---|---|---|
| Evaluation / Measurement | Eval | golden education suite | `python3 -m src.lingua_viva.cli eval golden`, `tests/golden_education_v1.yaml` | 36 education classifications | accuracy report | base education routing stays correct |
| Evaluation / Measurement | Eval | layer 1 schema evals | `tests/evals/layer1_schema/` | schema conformance | pass/fail | education records stay valid |
| Evaluation / Measurement | Eval | layer 2 retrieval evals | `tests/evals/layer2_retrieval/` | document classification, grade fencing, retrieval determinism, teacher-lens extraction | pass/fail | retrieved context is correct and bounded |
| Evaluation / Measurement | Eval | layer 3 isolation evals | `tests/evals/layer3_isolation/` | privacy, student isolation, teacher isolation, temporal integrity | pass/fail | boundaries hold under classroom data |
| Evaluation / Measurement | Eval | layer 4 golden evals | `tests/evals/layer4_golden/` | bilingual balance, Bloom, CEFR, holdout, tier logic | pass/fail | pedagogy-specific correctness holds |
| Evaluation / Measurement | Eval | layer 5 gauntlets | `tests/evals/layer5_gauntlets/` | contamination, lesson prep, new student, RTI change, wrong input rejection | pass/fail | realistic failure modes stay caught |
| Evaluation / Measurement | Eval | improvement audit | `src/lingua_viva/improvement_audit.py` | gap/failure signals | ranked improvement summary | system knows what to improve next |
| Evaluation / Measurement | Eval | gap audit | `src/lingua_viva/gap_audit.py` | missing coverage/signals | gap report | uncovered issues become visible |
| Health / Doctor / Readiness | Gate | preflight | `python3 -m src.lingua_viva.cli preflight` | imports, contracts, routes, project metadata | pass/fail | fast structural readiness |
| Health / Doctor / Readiness | Gate | full health | `python3 -m src.lingua_viva.cli health --full --json` | doctor, pytest, gauntlet, golden eval, 5xx check | health JSON | know if local repo can operate |
| Health / Doctor / Readiness | Gate | doctor | `python3 -m doctor.support_loop doctor` | local diagnostics/privacy/support readiness | OK/WARN/FIXABLE/BLOCKED | supportable local install |
| Surfaces / Interfaces | Gate | UI contract | `contracts/UI_CONTRACT.yaml`, `scripts/check_ui_contract.py` | UI route/element promises | pass/fail | shipped UI does not drift silently |
| Surfaces / Interfaces | Gate | route reachability | `contracts/ROUTE_REACHABILITY.yaml`, `scripts/check_route_reachability.py` | backend route reachability from UI | pass/fail | built routes are not orphaned |
| Artifact Governance | Gate | artifact gauntlet | `doctor/lv_artifact_gauntlet.py`, `artifacts/inventory.yaml` | publication/accountability artifacts | pass/fail/report | artifacts stay honest |

---

## 10. Surfaces / Interface Things

| System | Thing class | Instance | Where | Input | Mechanism | Output | Desired outcome | Proof / gate |
|---|---|---|---|---|---|---|---|---|
| Surfaces / Interfaces | Surface | FastAPI backend | `src/web.py` | API/browser requests | route handlers | JSON/HTML/audio | local teacher app works | route/API tests |
| Surfaces / Interfaces | Surface | static teacher app/PWA | `static/index.html`, `static/sw.js`, `static/manifest.json` | teacher interaction | browser UI + service worker | teacher workspace | usable planning/observe/source/trust views | UI/PWA tests |
| Surfaces / Interfaces | Surface | CLI | `src/lingua_viva/cli.py`, `src/lv_cli.py` | terminal command | argparse commands | health/eval/filemap/serve/audit output | operator can run and diagnose LV | CLI tests |
| Surfaces / Interfaces | Surface | Electron desktop | `desktop/electron/` | desktop launch/setup | shell + bootstrap | desktop app | non-terminal teacher entry point | desktop tests/release CI |
| Surfaces / Interfaces | Surface | public site | `docs/` | visitor/download | GitHub Pages static site | landing/download page | people can understand and install LV | site/release checks |
| Surfaces / Interfaces | Surface | profile/privacy/why views | `/api/profile`, `/api/privacy`, `/api/why` | teacher inspection | local logs/profile export | trust explanation | teacher can inspect and clear data | trust/profile tests |
| Surfaces / Interfaces | Surface | voice companion | `static/index.html`, voice routes | mic/text response | STT -> query -> TTS | spoken/typed exchange | lower-friction teacher use | voice tests |

---

## 11. Agents / Skills / Lenses

| System | Thing class | Instance | Where | Input | Mechanism | Output | Desired outcome | Cross-domain? |
|---|---|---|---|---|---|---|---|---|
| Agents / Skills | Agent | protect | `agents/protect/` | sensitive query | protect prompt/logic | protect response | privacy-first handling | yes |
| Agents / Skills | Agent | research | `agents/research/` | research query | research prompt/logic | research response | evidence-aware reasoning | yes |
| Agents / Skills | Agent | decide | `agents/decide/` | decision request | decide prompt/logic | decision support | better tradeoffs | yes |
| Agents / Skills | Agent | create | `agents/create/` | creation request | create prompt/logic | artifact draft | faster teacher/admin creation | yes |
| Agents / Skills | Agent | diagnose | `agents/diagnose/` | problem/failure | diagnose prompt/logic | diagnosis | root causes visible | yes |
| Agents / Skills | Agent | reflect | `agents/reflect/` | review/learning | reflect prompt/logic | reflection | system/human learning | yes |
| Agents / Skills | Agent | orchestrator | `agents/orchestrator/` | classified intent | convergence/orchestration | selected agent/path | right reasoning mode | yes |
| Agents / Skills | Lens | education lenses | `lenses/education/` | education query/context | lens activation | pedagogy-specific posture | outputs respect teaching context | yes |
| Agents / Skills | Lens | Claudia person lens | `lenses/LENS-PERSON-002_claudia_canu.yaml` | practitioner context | person lens | Claudia-specific posture | product matches operator | no |
| Agents / Skills | Lens | Malaguzzi voice guide | `lenses/VOICE-EDU-001_malaguzzi_inspired.md` | writing task | voice guide | Reggio-inspired copy | product voice fits ethos | partly |
| Agents / Skills | Skill | adaptive learning framework | `skills/education/adaptive-learning-framework.md` | learner support need | framework | adaptive plan | differentiated learning | yes |
| Agents / Skills | Skill | adaptive learning command | `skills/education/adaptive-learning-command.md` | command/use case | skill instructions | support output | reusable teacher capability | yes |
| Agents / Skills | Skill | curriculum operating workspace | `skills/education/claudia-curriculum-operating-workspace.md` | curriculum work | workspace pattern | curriculum artifact | curriculum as data structure | no |
| Agents / Skills | Skill | skill builder | `skills/meta/skill-builder.yaml` | new capability need | builder schema | skill proposal | skills can expand coherently | yes |

---

## 12. Flow Patterns

| Flow | System chain | Thing chain | Output | Desired outcome |
|---|---|---|---|---|
| Ask education question | Surface -> Runtime -> Ontology -> Knowledge -> Privacy -> Trace | Ask UI/API -> query runtime -> education node -> KL/context -> local-first gate -> trace | grounded answer + trace | teacher gets useful, inspectable help |
| Observe student | Surface -> Observation -> Ontology -> Student Lens -> Memory | Observe UI/STT -> capture -> classify -> lens update -> trace/log | observation + lens update | quick classroom signal becomes durable learner understanding |
| Import Drive material | Surface -> Connector -> Source Ledger -> Extraction -> Observation/Lens | Drive view -> OAuth/import -> source record -> extract/review -> approved write | local copy + source/evidence record | shared material enters local LV with teacher control |
| Slack ops daily file | Connector -> Ops Packs -> Education Module -> Surface | Slack event -> ops classifier/packs -> daily file -> Ops UI | structured daily ops summary | operational noise becomes reviewable school context |
| Generate parent draft | Education Module -> Privacy -> Surface -> Artifact Governance | parent report -> safety gate -> UI preview -> record/export | parent draft | family communication is useful and safe |
| RTI decision | Student Lens -> Education Module -> Action Approval -> Trace | lens signals -> tier proposal -> teacher confirm/defer -> decision record | RTI decision/update | tier changes remain teacher-owned |
| Filemap source setup | Surface -> Connector/Sources -> Curriculum/Knowledge | filemap UI/CLI -> scan/assign/exclude -> source map | filemap | local teaching materials become navigable |
| Voice query | Voice -> Surface -> Runtime -> Voice -> Privacy | STT -> `/api/query` -> response/GIR/tone -> TTS gate | transcript + spoken answer | teacher can use LV hands-free with safety controls |
| Support bundle | Health -> Artifact Governance -> Privacy -> Surface | doctor/support loop -> bundle build -> privacy scrub -> export | support bundle | support can debug without leaking private data |
| Release install | Delivery -> Health -> Surface | tag/workflow -> binary/desktop build -> install test -> public site | installable app | stranger can install and run LV |

---

## 13. Process Taxonomy — Commit To Teacher Machine

These processes are not product features. They are repeatable sequences that must complete correctly for a teacher or reviewer to receive a working Lingua Viva app.

| ID | Process | Failure it prevents | Where | Proof / gate | Status |
|---|---|---|---|---|---|
| DLV-PRC-001 | CLI binary release: tag -> PyInstaller build -> smoke -> GitHub release | released binary cannot run `health` | `.github/workflows/release.yml`, `lv.spec` | binary smoke under C/locale constraints | built/gated |
| DLV-PRC-002 | Desktop release: desktop tag -> backend smoke -> Electron build -> prerelease assets | desktop app ships with import-time backend crash | `.github/workflows/desktop-release.yml` | backend `/api/health` smoke before builds | built/gated |
| DLV-PRC-003 | Auto desktop release on main changes | code changes do not produce updated desktop artifacts | `.github/workflows/auto-release.yml` | pytest, health, backend smoke | built/gated |
| DLV-PRC-004 | Linux curl install test | install script points to missing/broken binary | `.github/workflows/install-test.yml`, `install.sh` | assert installed binary and live web UI | built/gated |
| DLV-PRC-005 | Signing-secret diagnostic | contradictory manual signing-secret status | `.github/workflows/check-signing-secrets.yml` | secret presence report without values | diagnostic |
| DLV-PRC-006 | Desktop setup wizard bootstrap | teacher cannot satisfy Python/Ollama/runtime prerequisites | `desktop/electron/bootstrap.ts`, `setup-wizard.html` | desktop/setup tests | built/gated |
| DLV-PRC-007 | One-button update | teacher stuck on old build or conflict | update specs/tests | update conflict surface tests | partial/built |
| DLV-PRC-008 | Route/UI contract drift check | backend route ships with no UI trigger or UI promises drift | `contracts/`, `scripts/check_*` | preflight route/UI checks | built/gated |

---

## 14. Key Taxonomy Decisions

1. **Lingua Viva is not Mission Canvas with a school skin.** It has MC-shaped components, but its durable systems are teacher runtime, education ontology, observation/student lens, source ingestion, privacy, evals, and delivery.
2. **The strongest live product loop is Observe -> Student Lens -> Teacher Action.** The taxonomy treats this as its own system, not just an education module.
3. **Curriculum source authority is separate from structured runtime data.** The `.docx` remains an authoritative draft until the curriculum owner promotes a structured source.
4. **Sources are a first-class system.** Drive, Slack, local files, source records, and extraction are not settings; they are how classroom reality enters LV.
5. **Voice is a system, but not the product center.** Voice improves teacher flow and safety, while the product's core loop remains observation, lens, curriculum, and decision support.
6. **Release/install is part of the product.** LV is a local-first app; if a teacher cannot install and boot it, the teacher-facing system does not exist in practice.
7. **External validation is not assumed.** Scores keep User and Outcome at zero unless the repo contains concrete classroom-use evidence.

---

## 15. Gap Summary

### What exists today

- Native local-first runtime with CLI, FastAPI, static app/PWA, and Electron desktop shell.
- 111-node ontology across 25 domains, including 9 education domain files.
- Evidence-tiered knowledge library with education entries and citations.
- Teacher-facing modules for observation, student lenses, assessment, differentiation, parent drafts, guides, trends, daily files, and ops.
- Google Drive, Slack ops, local filemap, voice STT/TTS, and source-ledger surfaces.
- Privacy, injection, publication, trust, request, trace, and profile/export infrastructure.
- Layered eval architecture, golden education eval, doctor, preflight, route/UI gates, and release/install CI.

### What is partial or still weaker

- External teacher/classroom validation and measured educational outcome proof are not present as repo evidence.
- Student-facing surface remains absent or intentionally minimal; students mostly appear as data captured by teachers.
- Learned weights exist but are not clearly load-bearing.
- Some downstream teacher decision paths are still thinner than observe/lens capture.
- Drive/Slack/source convergence is moving toward a unified Sources model but is not fully settled.
- Voice gap-to-eval and voice-loop measurement are emerging, not yet mature as a permanent loop.

### Highest-leverage next taxonomy refinements

1. Add a lower-level row set for every education ontology node once the education-domain YAMLs are stable.
2. Split source ingestion into Local, Drive, Slack, and Future Source rows once the unified Sources IA is finalized.
3. Add per-route surface coverage scores from `ROUTE_REACHABILITY.yaml`.
4. Add per-eval baselines from the layered eval suite.
5. Re-score User and Outcome only after documented external classroom use exists.

