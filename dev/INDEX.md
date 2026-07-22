# dev/ Index

The one place spec statuses live (MC-lessons §10, 2026-07-19). MC's own
`dev/INDEX.md` prevents status claims from scattering into individual spec
files and going stale — LV's sweep already had to correct spec statuses
once before this existed. Update this table in the same commit as any spec
status change.

## Specs (`dev/specs/`)

| Spec | Date | Status | Evidence |
|---|---|---|---|
| [SPEC_LV_FULL_ARTIFACT_HARDENING](specs/SPEC_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md) | 2026-07-20 | SHIPPED (uncommitted) | Full artifact hardening pass complete. Setup wizard built (Part 1), all teacher/coordinator/trust experiences live-walked (Part 2). 479/479 tests passing. `linguaviva.art` ESCALATED (unreachable). See `dev/reports/REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md`. |
| [SPEC_DESKTOP_SETUP_WIZARD](specs/SPEC_DESKTOP_SETUP_WIZARD_2026-07-20.md) | 2026-07-20 | SHIPPED (uncommitted) | Guided setup wizard built: `desktop/electron/setup-wizard.html`, multi-candidate Python detection, Ollama install/skip, early-exit detection. Desktop build compiles. Windows live-test pending (structural verification complete). |
| [SPEC_LV_SIDEBAR_DESIGN](specs/SPEC_LV_SIDEBAR_DESIGN_2026-07-20.md) | 2026-07-20 | DRAFT | Next-iteration spec, unbuilt. Selectively adapts MC's `SIDEBAR_APP_DESIGN_DOC_2026-07.md` (Canvas-Tile-Rail, 24 canvases, voice-command contract, gravity/recede) down to LV's actual scale (17-button flat role-swapped nav, no voice, single domain). Confirmed against `static/index.html` and `ADDENDUM_THREE_TIER_SIDEBAR_2026-07-16.md` — no contradiction with prior sidebar decisions. Keeps: nav-item contract, state-transition doc, a11y pass (aria-current/focus-visible/aria-label — the sharpest gap), 3-token naming pass, acceptance criteria, 2-phase build order. Drops: Canvas/Experience nesting, voice runtime, gravity/recede, domain-accent theming, canvas-seeding onboarding — all N/A to LV, named explicitly so as not to be silently re-proposed later. Companion prompt: `dev/EXECUTION_PROMPT_LV_SIDEBAR_DESIGN_2026-07-20_CODEX.md`. |
| [SPEC_LV_CLAUDIA_LENS_REPASS](specs/SPEC_LV_CLAUDIA_LENS_REPASS_2026-07-20.md) | 2026-07-20 | DRAFT | Next-iteration spec, unbuilt. Mirrors MC's `SPEC_P0_FOUNDER_LENS_REPASS` pattern — reviews LV's built experiences (9 P0 + 9 named non-P0) through Claudia Canu Fautré's person lens (`lenses/LENS-PERSON-002_claudia_canu.yaml`) and Malaguzzi voice guide (`lenses/VOICE-EDU-001_malaguzzi_inspired.md`), not pure technical correctness (already covered by the P0 pass). Companion prompt: `dev/EXECUTION_PROMPT_LV_CLAUDIA_LENS_REPASS_2026-07-20.md`. |
| [SPEC_LV_P0_IMPROVEMENT_CYCLE](specs/SPEC_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md) | 2026-07-20 | SHIPPED (uncommitted) | All 9 P0 experiences live-run against the real app. EXP09's named bug (PRIVATE_RISK/WARN sharing a CSS class) fixed. Two more real gaps found and fixed during live-verification: EXP04 (`external_calls` was a hardcoded 0, not a real counter — now logs/counts real `external_call_made` events) and EXP08 (the "only enforced" 25s timeout wasn't actually cancellable below ~20s because a blocking call had no `await` point — now runs via `asyncio.to_thread`). EXP01/02/03/05/06/07 confirmed matching happy-state exactly, no gap. UI contract bumped v6→v7. 476/476 tests passing, `lv health` clean (WARN explained/pre-existing). Changes staged but **not committed** — operator holds the sole commit window in this repo. See `dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`. |
| [SPEC_INSTALL_RELEASE_PIPELINE_HARDENING](specs/SPEC_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md) | 2026-07-20 | SHIPPED | F-1 and F-2 reproduced live and fixed; L-1 through L-4 fixed with regression coverage, L-5 resolved as a named decision (no Windows CI runner added — recommendation only, left for operator). 18 new tests (12 in test_install_hardening.py, 6 in test_install_launcher_scripts.py); suite 443→461 passing; `lv health` clean. PowerShell-side coverage (F-2, L-3, lv-launch.ps1) remains structural/simulated only — no pwsh/powershell runtime on this machine. See REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md |
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
| [REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20](reports/REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md) | 2026-07-20 | Desktop setup wizard shipped + full artifact hardening gauntlet: 479/479 tests, all teacher/coordinator/trust experiences live-walked, `linguaviva.art` escalated (unreachable), GitHub release v1.0.3 verified |
| [REPORT_LV_CLAUDIA_LENS_HARDENING_2026-07-20](reports/REPORT_LV_CLAUDIA_LENS_HARDENING_2026-07-20.md) | 2026-07-20 | 15-iteration Claudia-lens hardening pass shipped uncommitted: parent draft warmth, asset-based activity/assessment copy, Quick Capture trace UX, LV-native PWA shortcuts, UI contract v8; full suite 477/477 |
| [REPORT_LV_CLAUDIA_LENS_REPASS_2026-07-20](reports/REPORT_LV_CLAUDIA_LENS_REPASS_2026-07-20.md) | 2026-07-20 | Claudia-lens review pass complete: 18 built experiences live-checked against localhost app/nav/routes; top findings are parent-draft warmth, behaviorist/deficit-adjacent activity/assessment language, and Quick Capture deterministic UX mismatch |
| [REPORT_APP_IMPROVEMENT_MC_LESSONS_2026-07-19](REPORT_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md) | 2026-07-19 | This sweep's final report |
| [REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20](reports/REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md) | 2026-07-20 | Install/release pipeline hardening sweep close-out — F-1/F-2 fixed, L-1 through L-5 resolved, 461/461 tests passing |
| [REPORT_STAKEHOLDER_HARDENING_SWEEP_2026-07-20](REPORT_STAKEHOLDER_HARDENING_SWEEP_2026-07-20.md) | 2026-07-20 | Stakeholder-readiness hardening: metadata, runtime storage, admin deferred UX, runtime broker test |
| [REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20](REPORT_LINGUA_VIVA_SITE_RELEASE_2026-07-20.md) | 2026-07-20 | Landing site build/hardening plus download-button Phase 0-2 release pipeline work; live CLI release v1.0.3 |
| [REPORT_DOCTOR_SWEEP_2026-07-20](REPORT_DOCTOR_SWEEP_2026-07-20.md) | 2026-07-20 | Doctor branch gate updated for main; privacy WARN reviewed/deferred |
| [REPORT_ARCHITECTURE_SWEEP_2026-07-18](REPORT_ARCHITECTURE_SWEEP_2026-07-18.md) | 2026-07-18 | Full architecture sweep close-out |
| [REPORT_FINAL_POLISH_2026-07-18](REPORT_FINAL_POLISH_2026-07-18.md) | 2026-07-18 | Final polish close-out |
