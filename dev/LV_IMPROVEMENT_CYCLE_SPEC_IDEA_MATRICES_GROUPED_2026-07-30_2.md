# Lingua Viva Improvement Cycle Spec Idea Matrices - Grouped By System And Artifact - Pass 2

Date: 2026-07-30

Derived from:

- `dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30.md`
- Current `learning-architecture` source, tests, reports, and new 2026-07-30 specs.

Purpose: second rolling audit pass for Lingua Viva improvement-cycle ideas. This file narrows the original grouped matrix to ideas that are still unimplemented, partial, deferred, or not yet proven across the real artifact boundary.

Verification boundary:

- This pass inspected source, tests, contracts, reports, and new specs. It did not run the full test suite.
- The worktree is active and contains uncommitted changes.
- `[x]` means source/test evidence found and removed from active remaining work.
- `[~]` means partially implemented or built but not fully proven across the intended artifact boundary.
- `[ ]` means not found implemented, explicitly deferred, or still needs a build/spec slice.

## Completed Or Mostly Closed Since The First Matrix

The following original LV matrix ideas now have enough evidence to stop carrying as active missing work:

- LV-A01 inline GIR/grounding at SYNTHESIZE, stored on `PathRecord` and returned through `/api/query`.
- LV-A05 through LV-A08 gap audit, candidate replay, distinct-session ranking, harness-burst detection, and OOV family drift audit.
- LV-A10 through LV-A12 curriculum authority separation, source status, and citation visibility.
- LV-A21 module-level app reality/live P0 style repeatability, now backed by route/UI contract and P0 reports.
- LV-A28, LV-A29, and LV-A31 Drive workspace, self-service sign-in/disconnect/status, and final hardening.
- LV-A33 through LV-A36 Slack ops injection/lifecycle/unmapped-user/idempotency hardening.
- LV-A38 and LV-A39 Sources/File Map convergence and local filemap autoscan/stale-root machinery.
- LV-A44 through LV-A49 audit/distill, proxy-to-live analytics, volume floors, informational signal separation, and Layer 1-5 eval backbone.
- LV-A50/LV-A76/LV-A77 golden voice workflow, synthetic fixture, voice-loop failure classification, and gap-signal write path.
- LV-A52 and LV-A53 artifact gauntlet and evidence register as release/accountability gates.
- LV-A56, LV-A57, LV-A60, LV-A61 route reachability, fast preflight, executable gates, and UI contract drift checks.
- LV-A66 through LV-A68 live-layer/lens contract checks and Claudia lens repass pattern.
- LV-A69 through LV-A71 raw-query-free traces, malformed NDJSON tolerance, and separate audit summaries.
- LV-A74 and LV-A75 GIR-governed voice tone plus `tone_prefix` safety-gated TTS route.
- LV-A78 Rime TTS privacy gate and student-name stripping.
- New 2026-07-30 voice streaming slice: `/api/query/stream`, SSE `answer_sentence`, and queued early sentence TTS are implemented.
- New 2026-07-30 SIR absence/coverage MVP is implemented with tests and staffing summary endpoint.
- New 2026-07-30 SIR operational request center is implemented with tests and request summary endpoint.

## Pass 2 Remaining Work Matrix

## RTE - Runtime Execution (`RTE-SYS-001`)

### Artifact: Local-first query/runtime kernel

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A04 | [~] | Finish sweeping import-time environment constants into call-time/lazy resolution. | Hermetic tests and desktop/source parity depend on config being read at the moment of use. | Add a small runtime hermeticity sweep over provider/config/sanitizer/helper modules. |
| LV-B01; LV-A25 | [ ] | Replace deferred LV exit/integrity no-ops before any external routing is enabled. | Local-first is safe because external routing is currently off. That stops being true the moment external calls become available. | `SPEC_LV_NATIVE_EXIT_INTEGRITY_GATES_2026-07-30.md` |
| New from `SPEC_LV_VOICE_STREAMING_2026-07-30` | [~] | True provider-token streaming remains unbuilt. | The SSE slice improves perceived voice flow, but first audio still waits for full `run_teacher_query()`. | Separate provider/reasoning streaming spec after voice SSE stabilizes. |

## EON - Education Ontology (`EON-SYS-001`)

### Artifact: Education ontology domains and candidate nodes

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A09 | [~] | Make learned weights load-bearing or formally demote them. | Inert self-tuning creates false confidence. If weights matter, health must prove it; if not, the product should stop implying adaptation there. | Add learned-weight usefulness audit and explicit demotion/activation decision. |
| LV-B02 | [ ] | Add lower-level taxonomy rows for every education ontology node. | Useful for future measurement precision once current domains stabilize. | Taxonomy refinement pass, not core loop blocker. |
| New from MC transfer / eval notes | [ ] | Add defect-source triage for curriculum vs checker vs ontology/source drift. | LV now has many measurement surfaces; failures need layer classification to avoid fixing the wrong part. | `SPEC_LV_DEFECT_SOURCE_TRIAGE_2026-07-30.md` |

## CUR - Curriculum / Knowledge (`CUR-SYS-001`)

### Artifact: Authoritative curriculum source and structured matrix

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A13 | [~] | Finish source freshness as an improvement signal, including Drive "New from Drive" metadata-only detection. | Filemap autoscan exists, but Drive/local freshness should land in daily/source status as ranked work. | Build metadata-only new-file detection and daily/source-surface reporting. |
| LV-B03 | [ ] | Let teachers propose curriculum adjustments as deferred candidates. | Teacher corrections should enter a governed queue without becoming authoritative by accident. | Add curriculum candidate records with owner-promotion gate. |
| Publication/source migration notes | [~] | Decide the future authority relationship between `.docx` and structured curriculum sources. | The `.docx` is still authoritative; indefinite dual-authority would create source drift. | Add a review-date/status field and migration-decision gate. |

## OBS - Observation / Student Lens (`OBS-SYS-001`)

### Artifact: Observe capture, classify, and lens update loop

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A14 | [~] | Finish the teacher decision half of the flywheel beyond RTI: portfolio entry, assess-gaps, help-artifact, and any missing visible action endpoints. | RTI confirm/defer and grouping now exist, but the full observe -> decide -> artifact loop is not proven for all intended teacher actions. | `SPEC_LV_TEACHER_DECISION_FLYWHEEL_COMPLETION_2026-07-30.md` |
| LV-A16 | [~] | Make gap-driven next-step proposals first-class teacher work. | Adaptive recommendations surface, but not every observed gap turns into a reviewable next-step/action artifact. | Connect gap clusters to teacher-visible recommendation/action queue. |
| LV-A18 | [~] | Portfolio write path still needs a clear build/proof or formal descope. | Portfolio is part of the stated student-learning loop; overclaiming it hides a real product boundary. | Prove route/UI/workflow or descope in `dev/INDEX.md`. |
| LV-B04 | [ ] | Student-facing surface remains deferred. | Valuable later, but not current teacher/admin improvement-loop foundation. | Revisit only after teacher/admin adoption signal. |

## EDU - Education Product Modules (`EDU-SYS-001`)

### Artifact: Teacher/admin product modules

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A19 | [~] | Admin evidence/capacity/trends are now realer than the original matrix, but still need pilot-data readiness boundaries. | These surfaces can mislead with small or synthetic data. | Add explicit data-sufficiency and consent-aware pilot gates. |
| LV-A22 | [~] | Daily file as convergence surface needs continued ownership boundaries as Slack, Drive, and local sources expand. | It is becoming the operational hub; without boundaries it can mix reminders, source freshness, student data, and ops records too freely. | Add daily-file section ownership and source-classification contract. |
| New from 2026-07-30 handoff | [ ] | Dedicated lesson planning per student cohort is weak or absent as a distinct capability. | It may be expected to emerge from Ask + student lenses + curriculum, but the repo does not show a clear dedicated workflow. | Decide whether to build a cohort lesson-planning workflow or document it as composed behavior. |

## PRV - Privacy / Governance (`PRV-SYS-001`)

### Artifact: Privacy, role, and export gates

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A23; LV-B06 | [ ] | Add server-side auth/role enforcement before any second real user. | Current role state is still not a real multi-user security boundary. | `SPEC_LV_SERVER_SIDE_AUTH_ROLE_GATE_2026-07-30.md` |
| LV-A24 | [ ] | Replace observe-once access with admin-grantable roster/co-teacher access. | A new co-teacher should not need to observe a child once before seeing assigned students. | `SPEC_LV_ROSTER_COTEACHER_ACCESS_MODEL_2026-07-30.md` |
| LV-A25 | [ ] | Build real exit/integrity gates before enabling external routing. | Student privacy and source integrity cannot rely on "external is off" forever. | Same gate slice as RTE. |
| LV-A27; LV-B11 | [~] | Publication-readiness Phase 1+ needs re-audit against current public/portfolio state. | Structured tracking and gauntlet exist, but the public-readiness question is still not fully closed for launch. | `SPEC_LV_PUBLICATION_READINESS_REPASS_2026-07-30.md` |

## CON - Connectors / Sources (`CON-SYS-001`)

### Artifact: Google Drive connector/workspace

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A30 | [ ] | Add metadata-only "New from Drive" detection without auto-importing content. | Teachers need awareness that source material changed without weakening the explicit-import privacy model. | Build status-only Drive delta lane into Sources/daily file. |
| LV-A32 | [~] | Use deliverables registry before expanding non-lens share-back. | Deliverable records now exist; the remaining work is applying them consistently to broader share/export actions. | Gate new share-back actions on `DeliverableRecord` + `AuditReceipt`. |
| LV-B07 | [ ] | Revisit `drive.file` + Google Picker as a narrower OAuth alternative. | Current broad Drive scope is honest but still high-trust. | Defer unless OAuth review demands narrower scope. |

### Artifact: Slack ops connector/workflow packs

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A37 | [ ] | Surface `/api/ops/records` as an audit/review UI, not backend-only forever. | Ops records are now central to SIR workflows; humans need inspectable history. | Add ops-records review surface or daily-file drilldown. |
| New `SPEC_LV_SIR_SLACK_SCHEDULE_ACKS_2026-07-30` | [ ] | Build schedule-change acknowledgements: `/schedule-change`, seen/conflict/clarify buttons, and summary endpoint. | Absence coverage and ops requests are closed-loop; schedule changes still broadcast without acknowledgement tracking. | Build Phase 2B schedule acknowledgement slice. |
| New SIR proposal | [ ] | Add AI policy retrieval with citations only after deterministic ops workflows are stable. | Policy answers need source/version citations and should not adjudicate staffing or safeguarding. | Separate retrieval-only policy workflow with citation gate. |
| LV-B08 | [ ] | Additional Slack ops packs beyond approved packs. | Product expansion; should follow corpus-gated pack governance. | Add only after existing SIR workflows are stable. |

### Artifact: Unified Sources surface / file map

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A40 | [~] | Prove bad parse, guard-trip, missing-file, and import-failure behavior in packaged bundle, not only source checkout. | Source failures must degrade correctly in the shipped app. | Add bundle-path source-read regression gate. |

## ACT - Action / Approval (`ACT-SYS-001`)

### Artifact: Action plans and teacher approval

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A41 | [~] | Make "system proposes, teacher confirms" common across all action surfaces. | Some flows now do this well; others still rely on view-only suggestions or backend-only action records. | Action-surface consistency audit. |
| LV-A42 | [~] | Expand action history/audit visibility for rejected and approved action plans. | Local records exist; teacher-facing audit review is still uneven. | Add action history panel or governance view section. |
| LV-A43 | [~] | Keep colleague snapshot warnings and privacy checks on every Drive/share/export action as share-back expands. | Share-back is where private student context can leak. | Add share-back gate tests for every new deliverable type. |
| LV-B09 | [~] | Broader executable education action layer remains partial. | Action plans exist, but not every workflow has a mature approval UX. | Keep behind approval/audit pattern. |

## EVA - Evaluation / Measurement (`EVA-SYS-001`)

### Artifact: Gap audit and measurement distillation

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A72 | [~] | Add stable origin/session tags for eval harness signal writes across all producers. | Distill detects likely harness bursts, but stable producer tags would make this mechanical. | Extend gap-signal schema with `origin`, `producer`, and stable `session_id` expectations. |
| LV-A73 | [~] | Make PASS/FIX/DEFER/WARN dispositions uniformly machine-readable in revision/audit logs. | Audit output becomes more useful when follow-up state is structured. | Add schema check over revision log decisions. |

### Artifact: Layered eval architecture / golden workflows

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A50; LV-A76 | [~] | Keep golden voice failures feeding ranking, and add any missing UI/dashboard surfacing later. | Gap signals are written; human-facing review of voice loop failures is still minimal. | After stability, add eval dashboard row for voice-loop failures. |
| LV-A51 | [~] | Repeat the live P0 experience sweep as a scheduled regression instrument. | The live P0 pass found real gaps; it should not remain an occasional manual ritual. | Add repeatable P0 sweep command/report. |
| LV-B10 | [ ] | UI/dashboard surfacing of voice-loop failures. | Explicitly out of scope for initial golden voice loop, but useful for operator review. | Defer until voice loop is consistently green. |

## AGV - Artifact Governance (`AGV-SYS-001`)

### Artifact: Artifact inventory, publication safety, and evidence register

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A54 | [~] | Add mechanical status-drift checks so specs marked shipped cannot disagree with code/contracts. | The new 2026-07-30 specs already show how quickly INDEX/spec status can fall behind active builds. | `SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md` |
| LV-A55 | [~] | Keep `dev/INDEX.md` complete and current as the corpus grows. | New specs from today should be indexed or explicitly marked draft/built. | Add index-completeness check over `dev/*SPEC*.md` and `dev/specs/*SPEC*.md`. |
| LV-B11 | [~] | Publication copy/content cleanup before public launch. | Product governance, not proof of educational efficacy. | Same publication-readiness repass as PRV. |

## HTH - Health / Doctor / Readiness (`HTH-SYS-001`)

### Artifact: Preflight, doctor, full health, support bundle

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A58 | [~] | Keep doctor privacy WARNs explicit and revalidated as source exclusions evolve. | Expected private `.docx` exclusions should remain visible but not block teacher use. | Periodic doctor privacy warning repass. |
| LV-A59 | [~] | Keep support bundle privacy scrub current as new ledgers/routes are added. | Source ledger, ops records, and voice traces add new local data surfaces. | Extend support-bundle exclusion/redaction tests for new stores. |
| LV-B16 | [~] | Full signing/notarization/release maturity across platforms remains incomplete. | Release trust work matters before broad installs. | Separate release-readiness pass. |

## SRF - Surfaces / Interfaces (`SRF-SYS-001`)

### Artifact: Web/PWA/desktop/CLI surfaces

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A62 | [~] | Keep public UI states honest as previously deferred admin features become real. | Admin pages moved from deferred to partial/real; copy must not overstate confidence. | Admin copy/data sufficiency pass. |
| LV-A63 | [~] | Keep endpoint smoke coverage current for newly added routes. | New SIR and stream endpoints add surface area. | Add smoke rows for all 2026-07-30 routes. |
| LV-A65 | [~] | Keep startup behavior identical in source checkout and desktop bundle. | Source-ledger, live-layer, voice, and Sources paths are all path-sensitive. | Bundle/source parity smoke for new routes and stores. |
| LV-B12 | [ ] | Student-facing UI remains deferred. | Strategic later surface, not current improvement loop. | Revisit after teacher/admin adoption. |

## AGT - Agents / Skills (`AGT-SYS-001`)

### Artifact: Education lenses, Claudia lens, and skill packages

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-B13 | [ ] | Hot-reload, lens enable/disable, and template-editor UI remain deferred. | Useful authoring UX, but outside current hardening loop. | Defer unless live-layer authoring becomes the main workflow. |

## MEM - Memory / Trace / Audit (`MEM-SYS-001`)

### Artifact: Trace, request log, revision log, gap-signal stores

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A72 | [~] | Stable producer/origin/session tags for eval-harness signals. | Prevents harness-minted breadth from being inferred indirectly. | Same schema slice as EVA. |
| LV-A73 | [~] | Structured dispositions in all audit/revision entries. | Makes follow-up pass/fix/defer state machine-readable. | Revision-log schema validation pass. |

## VOC - Voice System (`VOC-SYS-001`)

### Artifact: STT, TTS, tone, voice companion, golden voice loop

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A74 | [~] | GIR calibration remains an ongoing product truth check, not just a unit-test fact. | The hardening report found/closed an inflation bug; real-query calibration should continue. | Run periodic voice/GIR hardening scenarios and write defects into gap signals. |
| LV-B14 | [~] | Persistent voice companion sidebar and unified voice flow remain product-polish work. | Voice now has core mechanics; the companion surface still needs real UX validation. | App-reality pass for voice companion. |
| LV-B15 | [ ] | Advanced voice UX: reading-position highlighting and multi-turn voice. | Explicitly out of scope for current loop. | Defer. |
| Rime live verification | [~] | Rime audio quality/path cannot be fully verified without `RIME_API_KEY`. | Route-level privacy and prefix behavior pass, but live external audio is still environment-gated. | Run Rime integration scenarios once key is available. |

## DLV - Delivery / Release Process (`DLV-SYS-001`)

### Artifact: Release, install, desktop, one-button update

| Source ID(s) | Status | Remaining idea | Why still matters | Next spec / action |
|---|---|---|---|---|
| LV-A79 | [~] | Keep desktop backend smoke pinned to exact installer dependency set as dependencies move. | A source environment pass is not enough. | Add dependency-set smoke to release checklist. |
| LV-A80 | [~] | Keep curl install test as a public install gate. | Stranger install path must remain executable. | Repeat on release candidates. |
| LV-A81 | [~] | Keep live site/download buttons pinned to verified release assets. | Prevents public links from pointing at stale or missing artifacts. | Keep `mc_push`/site-pin verification in release pass. |
| LV-A82 | [~] | Keep signing/notarization secret diagnostics value-free but explicit. | Release failures should be explainable without leaking secrets. | Continue release workflow hardening. |
| LV-A83 | [~] | Keep one-button update conflict surface visible. | Silent failed updates destroy trust. | Re-run update conflict surface tests after release changes. |
| LV-B16 | [~] | Full cross-platform notarization/signing maturity. | Important before broad distribution. | Dedicated release-readiness pass. |

## Newly Found Unimplemented Ideas From 2026-07-30 Specs

| New ID | System | Status | Idea | Evidence / note | Next action |
|---|---|---|---|---|---|
| LV-N01 | CON / EDU | [ ] | Schedule-change acknowledgement loop: `/schedule-change`, targeted DM cards, seen/conflict/clarify state, and summary endpoint. | Spec exists; no matching `tests/test_sir_schedule_acks.py`, route, or action IDs found. | Build `SPEC_LV_SIR_SLACK_SCHEDULE_ACKS_2026-07-30.md`. |
| LV-N02 | EDU / OBS | [ ] | Dedicated cohort lesson-planning workflow. | 2026-07-30 handoff says source search found no clearly dedicated module. | Decide build vs composed behavior. |
| LV-N03 | CON / CUR | [ ] | AI policy retrieval with citations for SIR. | Proposal includes policy retrieval/citation checklist; not in built absence/request-center slices. | Separate retrieval-only, source-cited policy workflow. |
| LV-N04 | RTE / VOC | [ ] | True token streaming from the reasoning provider. | `/api/query/stream` is SSE over completed pipeline result; provider stream is explicitly out of scope. | Future provider adapter spec. |
| LV-N05 | AGV | [~] | Index/status update for new 2026-07-30 specs and build reports. | New specs/prompts exist; index drift has historically hidden shipped/partial state. | Run index-completeness/status-drift checker or update manually. |

## Highest-Leverage Next Slices

1. `SPEC_LV_SIR_SLACK_SCHEDULE_ACKS_2026-07-30.md` - completes the third SIR Slack workflow family after absence coverage and ops requests.
2. `SPEC_LV_SERVER_SIDE_AUTH_ROLE_GATE_2026-07-30.md` - hard blocker before any second real user.
3. `SPEC_LV_ROSTER_COTEACHER_ACCESS_MODEL_2026-07-30.md` - replaces observe-once access with real school assignment.
4. `SPEC_LV_TEACHER_DECISION_FLYWHEEL_COMPLETION_2026-07-30.md` - closes portfolio/help/gap/action endpoints around the observe -> decide loop.
5. `SPEC_LV_SPEC_STATUS_DRIFT_CHECKER_2026-07-30.md` - prevents the matrix/spec/index drift this pass had to correct manually.
6. `SPEC_LV_NATIVE_EXIT_INTEGRITY_GATES_2026-07-30.md` - required before external routing can safely exist in LV.
