# Lingua Viva Convergence Run Handoff - 2026-07-31

## Run Scope

Executed the manual Lingua Viva convergence sequence from
`dev/PROMPT_LV_FULL_SYSTEM_CONVERGENCE_RUN_2026-07-31.md`.

Repo: `/home/mical/learning-architecture`  
Branch: `main`  
Starting HEAD: `5d527ec` (`lv: publication readiness repass -- site copy fixes + go/no-go report`)

No commit, push, or release tag was made.

## Baseline

- Full suite before edits: `1692 passed, 13 skipped in 435.70s`
- `lv preflight`: `6/6`
- `lv doctor --json`: `WARN`
  - Expected private-source exclusion warning for `Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx` and `resume-cv/Claudia_CanuFautre_Resume.docx`
  - Worktree warning because the operator prompt file and `ontology/proposals/CAND-BDD09D9D.yaml` were already dirty before this run
- `lv audit --json`: exited `1` before a baseline because no audit summary baseline existed
- `lv eval golden`: `36/36 passed`
- `lv golden-workflows --hermetic`: `6/6 passed`

## Fixes Made

1. Wired `lv spec-status` into `src/lingua_viva/cli.py`.
   - Supports `--json`, `--markdown`, and `--strict`.
   - Added CLI dispatch coverage in `tests/test_lv_cli.py`.

2. Closed the 2026-07-30 build-spec index drift.
   - Added `dev/INDEX.md` rows for the Jul 30 `SPEC_LV_*` batch and their paired build prompts.
   - Updated shipped Jul 30 spec headers from draft/build-handoff language to shipped status with commit/test evidence.

3. Reduced false-positive spec-status drift.
   - `src/lingua_viva/spec_status.py` now treats common suffix variants (`_workflow`, `_loop`) as equivalent for spec/prompt topic matching.
   - Reworded the checker spec's placeholder-file example so it is not interpreted as a real shipped file claim.
   - Added regression coverage in `tests/test_spec_status.py`.

4. Closed one audit vocabulary drift.
   - `voice_loop_failure` is now a known signal family in `src/lingua_viva/gap_audit.py`.
   - This matches the shipped `GW-VOICE-006` failure emitter.
   - Added regression coverage in `tests/test_gap_audit.py`.

5. Established the first full audit baseline.
   - Ran `lv audit --journal-write --json`.
   - Follow-up `lv audit --json` exited `0` with no new drift.

## Convergence Findings Reviewed

- `distill`: highest-ranked clusters remain historical `CORE-PROTECT` burst signals from 2026-07-18, `CORE-RESEARCH` weak/low-confidence signals, and `GW-VOICE-006 voice_loop_failure:stt_mismatch`.
  - Disposition: no automatic ontology promotion. `voice_loop_failure` schema drift fixed; repeat counts remain visible for review.

- `candidates`: 39 active candidates listed.
  - Aging candidates in audit: `CAND-9A861241`, `CAND-B6FCE003`, `CAND-BDD09D9D`, `CAND-F734BAFA`.
  - Distill flagged possible resolution-by-routing for `CAND-67D0122B`, `CAND-AB1D05D6`, `CAND-B6FCE003`, `CAND-BDD09D9D`.
  - Disposition: deferred for operator/ontology review. The prompt explicitly says not to auto-promote candidates.

- `spec-status`: Jul 30 build-spec missing-index and prompt-pair drift is fixed.
  - Remaining findings are older repo-wide drift plus planning/backlog docs, not newly introduced Jul 30 build-spec drift.
  - `dev/SPEC_LV_FINAL_GOVERNANCE_READINESS_PRODUCT_POLISH_SWEEP_2026-07-30.md` still warns on backlog item paths that do not exist; disposition: left as backlog/planning truth rather than creating placeholder modules.

## Final Verification

- `python3 -m pytest tests/test_gap_audit.py tests/test_lv_cli.py tests/test_spec_status.py -q`: `43 passed`
- `python3 -m src.lingua_viva.cli preflight`: `6/6`
- `python3 -m src.lingua_viva.cli doctor --json`: `WARN`
  - Only worktree/private-source warnings; structural checks pass.
- `python3 -m src.lingua_viva.cli eval golden`: `36/36 passed`
- `python3 -m src.lingua_viva.cli golden-workflows --hermetic`: `6/6 passed`
- `python3 -m src.lingua_viva.cli audit --json`: exit `0`, no new drift after the baseline
- `python3 -m src.lingua_viva.cli audit --strict --json`: exit `1`
  - Strict absolute mode still reports historical repeat pairs and aging candidates.
- `python3 -m src.lingua_viva.cli spec-status --json`: exit `1`
  - Summary after this run: `90 warn`, `17 fail`.
  - Failures are pre-existing older spec/file claims; no new fail-severity finding was introduced for this run's touched build specs.
- Final full-suite rerun: `1694 passed, 13 skipped in 623.10s`

## Working Tree Notes

- Pre-existing dirty file: `ontology/proposals/CAND-BDD09D9D.yaml`.
  - This run's `distill`/candidate replay increased its diff against HEAD to `hit_count: 55 -> 58` and refreshed `updated_at`; review before commit.
- Pre-existing untracked prompt: `dev/PROMPT_LV_FULL_SYSTEM_CONVERGENCE_RUN_2026-07-31.md`.
- New runtime audit baseline under `memory/data/gap_audit_summaries.ndjson`; `memory/data/` is currently untracked and also contains existing runtime logs.

## Remaining Owner-Review Items

- Decide candidate dispositions for the aging ontology queue.
- Decide whether `audit --strict` should remain absolute-strict for historical drift or whether final gates should use delta semantics after the baseline.
- Decide whether to broaden the spec-status cleanup to older Jul 16-29 docs. This run intentionally fixed the Jul 30 build-spec drift requested by the prompt without rewriting historical specs.
