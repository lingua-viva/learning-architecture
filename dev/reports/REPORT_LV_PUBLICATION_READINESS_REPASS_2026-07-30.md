# Lingua Viva Publication Readiness Repass — 2026-07-30

**Status**: NOT PUBLICATION-READY FOR BROAD EXTERNAL LAUNCH  
**Scope**: Public/readiness copy and governance posture after the July 30 hardening run.  
**Selected from**: `dev/SPEC_LV_FINAL_GOVERNANCE_READINESS_PRODUCT_POLISH_SWEEP_2026-07-30.md` Priority 1.

## Executive Summary

The foundation-risk phase is substantially closed, but public launch still needs an owner review before broad external distribution.

The app can be described as a local-first teacher workbench with governed opt-in connectors. It should not be described as a system where no data ever leaves the computer, because Drive, Slack, Rime TTS, and external-provider paths exist behind explicit setup, role gates, and exit gates.

## Reviewed Surfaces

- `publication-policy.md`
- `dev/specs/LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md`
- `dev/SPEC_LV_FINAL_GOVERNANCE_READINESS_PRODUCT_POLISH_SWEEP_2026-07-30.md`
- `README.md`
- `docs/index.html`
- sampled public/static copy in `static/index.html`

## Copy Fixes Made

Changed `docs/index.html`:

- Replaced stale hardcoded test-count claim `570 tests` with `Regression suite`.
- Replaced `Saved locally - no third-party calls - teacher controlled` with `Saved locally by default - opt-in connectors are gated - teacher controlled`.
- Replaced `No data leaves your computer` with language stating student observations stay on-device by default and opt-in connectors require explicit setup and review.

These are narrow publication-honesty fixes. No product behavior changed.

## Current Go / No-Go

**Go**:

- Internal demos.
- Technical review with operators/developers.
- School-controlled pilot discussion that accurately describes local-first behavior and opt-in connectors.

**No-go until owner review**:

- Broad public launch claims that imply no external data paths exist.
- Parent/student public examples using real or realistic identifiers.
- Still I Rise or school-leadership package that implies policy/procedure assistant behavior without citation-gated retrieval.
- Any public claim that student outcomes are validated by Lingua Viva runtime data.

## Findings

### 1. Local-Only Copy Needed Precision

The public site had absolute language implying no third-party calls or no data leaving the computer. That is no longer accurate because the runtime has explicit, governed external surfaces.

Resolution: fixed the public site copy to say local by default and opt-in connectors are gated.

### 2. Hardcoded Test Count Was Stale

The public site claimed `570 tests`, while the current suite is much larger. Hardcoded test counts become stale quickly during hardening loops.

Resolution: replaced the number with `Regression suite`.

### 3. README Still Needs Owner-Level Claim Review

`README.md` is broadly improved compared with the July 16 audit, but it still contains public portfolio claims that should remain owner-reviewed before external launch:

- validated assessment improvement claims;
- transferability/value claims;
- personal/professional biographical detail;
- exact app capability scope.

No README edits were made in this pass because the claims are portfolio-level, not obvious one-line app-copy defects.

### 4. Parent Draft Surfaces Are Properly Framed Internally

Sampled `static/index.html` parent copy says drafts require review and are not sent automatically. This matches the current governance posture.

### 5. Public/Internal Boundary Remains Clear Enough for Pilot, Not Final Launch

The public site now better distinguishes local default behavior from opt-in connectors. A final launch should still include an explicit short privacy/connectors note near downloads or docs.

## Remaining Launch Readiness Checklist

- Verify reference redistribution rights before publishing curriculum/reference PDFs.
- Keep school/institution-identifying language generic unless explicitly approved.
- Use "designed to target" language for CEFR/progression claims unless outcome evidence is available.
- Keep parent/student examples anonymized and synthetic unless consent and review are documented.
- Add a concise public privacy/connectors explainer before broader external distribution.
- Run a fresh full suite and preflight immediately before any release/package handoff.

## Verification

Run after the copy/report changes:

```text
python3 -m src.lingua_viva.cli preflight
pytest -q tests/test_ui_contract.py tests/test_route_reachability.py
```

Full suite was not required for this report-only/public-doc copy slice because no runtime, contracts, routes, protected UI bundle, stores, gates, or shared modules changed.
