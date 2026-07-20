# dev/ Index

The one place spec statuses live (MC-lessons §10, 2026-07-19). MC's own
`dev/INDEX.md` prevents status claims from scattering into individual spec
files and going stale — LV's sweep already had to correct spec statuses
once before this existed. Update this table in the same commit as any spec
status change.

## Specs (`dev/specs/`)

| Spec | Date | Status | Evidence |
|---|---|---|---|
| [SPEC_DOWNLOAD_BUTTONS](specs/SPEC_DOWNLOAD_BUTTONS_2026-07-20.md) | 2026-07-20 | SHIPPED (partial) | Phases 1-2 shipped: `60faae5`, `797a52c`, `c86fb76`; live release `v1.0.3` publishes `lv-darwin-arm64`, `lv-linux-x86_64`, `lv-windows-x86_64.exe`; Release Binary run `29764711261` passed; Linux Install Test runs `29764711037` and `29764709197` passed. Mac/Windows installer paths remain manually unverified per G-5. Phases 3-4 still pending: desktop installer CI and landing-page button wiring |
| [SPEC_APP_IMPROVEMENT_MC_LESSONS](specs/SPEC_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md) | 2026-07-19 | SHIPPED | This sweep — §1-§10 applied, HB1/HB2 green, see REPORT_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md |
| [SPEC_FULL_ARCHITECTURE_SWEEP](specs/SPEC_FULL_ARCHITECTURE_SWEEP_2026-07-18.md) | 2026-07-18 | SHIPPED | REPORT_ARCHITECTURE_SWEEP_2026-07-18.md |
| [SPEC_PHASE6_TRUST_UI](specs/SPEC_PHASE6_TRUST_UI_2026-07-18.md) | 2026-07-18 | SHIPPED | Trust/Why views live in static/index.html |
| [SPEC_PHASE5_FILE_MAP](specs/SPEC_PHASE5_FILE_MAP_2026-07-17.md) | 2026-07-17 | SHIPPED | src/lingua_viva/filemap.py + /api/filemap/* |
| [SPEC_PHASE4_ONBOARDING_UX](specs/SPEC_PHASE4_ONBOARDING_UX_2026-07-17.md) | 2026-07-17 | SHIPPED | Onboarding flow in static/index.html |
| [SPEC_MC_BACKEND_MIGRATION](specs/SPEC_MC_BACKEND_MIGRATION_2026-07-16.md) | 2026-07-16 | SHIPPED (partial) | Phases 1-3 complete; legacy pipeline replacement deferred, see spec body |
| [SPEC_LINGUA_VIVA_APP_COMPLETE_BUILD](specs/SPEC_LINGUA_VIVA_APP_COMPLETE_BUILD_2026-07-16.md) | 2026-07-16 | SHIPPED | v1.0.0 release, github.com/lingua-viva/learning-architecture releases |
| [ADDENDUM_THREE_TIER_SIDEBAR](specs/ADDENDUM_THREE_TIER_SIDEBAR_2026-07-16.md) | 2026-07-16 | SHIPPED | Amends APP_COMPLETE_BUILD §Phase 2 — folded into the same ship |
| [LV_PHASE_1_3_HARDENING_REPORT](specs/LV_PHASE_1_3_HARDENING_REPORT_2026-07-16.md) | 2026-07-16 | SHIPPED | Self-reported: Passed |
| [LV_SUPPORT_LOOP_MVP_HARDENING_REPORT](specs/LV_SUPPORT_LOOP_MVP_HARDENING_REPORT_2026-07-16.md) | 2026-07-16 | SHIPPED | Self-reported: Passed |
| [SPEC_LINGUA_VIVA_LOCAL_SUPPORT_LOOP](specs/SPEC_LINGUA_VIVA_LOCAL_SUPPORT_LOOP_2026-07-16.md) | 2026-07-16 | DRAFT | Proposed build spec — superseded/scoped down by LV_SUPPORT_LOOP_MVP_HARDENING_REPORT |
| [SPEC_LINGUA_VIVA_DOCTOR_PHASE_B_SUPPORT_BUNDLE](specs/SPEC_LINGUA_VIVA_DOCTOR_PHASE_B_SUPPORT_BUNDLE_2026-07-16.md) | 2026-07-16 | DRAFT | Proposed build spec, Phase B not confirmed shipped |
| [SPEC_LINGUA_VIVA_APP_UNIFIED_BUILD](specs/SPEC_LINGUA_VIVA_APP_UNIFIED_BUILD_2026-07-16.md) | 2026-07-16 | DRAFT | Proposed unified build spec |
| [SPEC_LINGUA_VIVA_ACCOUNTABLE_CURRICULUM_SYSTEM](specs/SPEC_LINGUA_VIVA_ACCOUNTABLE_CURRICULUM_SYSTEM_2026-07-16.md) | 2026-07-16 | DRAFT | Proposed spec only; no implementation in this change |
| [LV_PUBLICATION_READINESS_AUDIT](specs/LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md) | 2026-07-16 | TRIAGE | Phase 0 human audit complete; package not publication-ready yet |
| [SPEC_LINGUA_VIVA_MC_TRANSFER_APPENDIX](specs/SPEC_LINGUA_VIVA_MC_TRANSFER_APPENDIX_2026-07-16.md) | 2026-07-16 | DRAFT | Reference/mapping doc, not a build spec |
| [SPEC_LINGUA_VIVA_MC_TRANSFER_FULL_TABLE](specs/SPEC_LINGUA_VIVA_MC_TRANSFER_FULL_TABLE_2026-07-16.md) | 2026-07-16 | DRAFT | Reference/mapping doc, not a build spec |

## Handoffs (`dev/`)

| Handoff | Date | Purpose |
|---|---|---|
| [HANDOFF_LINGUA_VIVA_2026-07-20](HANDOFF_LINGUA_VIVA_2026-07-20.md) | 2026-07-20 | Cross-session orientation: full spec inventory, three-tier (student/teacher/admin) build status, ranked weaknesses, recommended focus order |

## Reports (`dev/`)

| Report | Date | Evidence |
|---|---|---|
| [REPORT_APP_IMPROVEMENT_MC_LESSONS_2026-07-19](REPORT_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md) | 2026-07-19 | This sweep's final report |
| [REPORT_STAKEHOLDER_HARDENING_SWEEP_2026-07-20](REPORT_STAKEHOLDER_HARDENING_SWEEP_2026-07-20.md) | 2026-07-20 | Stakeholder-readiness hardening: metadata, runtime storage, admin deferred UX, runtime broker test |
| [REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20](REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20.md) | 2026-07-20 | Landing site build/hardening plus download-button Phase 0-2 release pipeline work; live CLI release v1.0.3 |
| [REPORT_DOCTOR_SWEEP_2026-07-20](REPORT_DOCTOR_SWEEP_2026-07-20.md) | 2026-07-20 | Doctor branch gate updated for main; privacy WARN reviewed/deferred |
| [REPORT_ARCHITECTURE_SWEEP_2026-07-18](REPORT_ARCHITECTURE_SWEEP_2026-07-18.md) | 2026-07-18 | Full architecture sweep close-out |
| [REPORT_FINAL_POLISH_2026-07-18](REPORT_FINAL_POLISH_2026-07-18.md) | 2026-07-18 | Final polish close-out |
