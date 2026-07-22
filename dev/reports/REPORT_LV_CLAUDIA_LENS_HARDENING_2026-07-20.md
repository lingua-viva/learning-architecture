# LV Claudia-Lens Hardening Pass - 2026-07-20

## Scope

15-iteration hardening pass following `REPORT_LV_CLAUDIA_LENS_REPASS_2026-07-20.md`.

This pass implemented low-risk copy/register fixes only. It did not change LV's privacy model, routing architecture, protection model, curriculum authority, or publication-safety rules.

## Iterations

| # | Target | Result |
|---|---|---|
| 1 | Parent draft register | Rewrote parent-report body around observed child competence and teacher review, preserving name stripping in `/api/parents/recommendation`. |
| 2 | Parent home-support sentence | Changed "may help your child begin tasks more independently" to an invitational family observation prompt. |
| 3 | Activity objectives | Replaced "Students will..." generated objectives with "Children..." competence-first objective language in generated packs. |
| 4 | Adapted activity objectives | Applied the same competence-first objective language to source-adapted packs. |
| 5 | Assessment band language | Replaced "Does not yet reach" and "Limited" with asset-based evidence language. |
| 6 | First-run setup | Added a teacher-purpose line: planning, observing, documenting, sharing learning with care. |
| 7 | Observation placeholder | Removed named demo-child placeholder from Observe. |
| 8 | Plan view | Reframed "Use this unit" as "Plan from this unit" and clarified that the source document stays untouched. |
| 9 | Students view | Changed roster and detail copy from RTI-first to trajectory/support-tier framing while keeping teacher-decision authority. |
| 10 | Home brief | Reframed first cards as teacher actions: observation to renew and decision to review. |
| 11 | Reflect view | Replaced generic placeholder with a three-question reflection prompt tied to children, environment, and next adjustment. |
| 12 | Settings sequencing | Split operational labels into Local model, Local app port, My week, and Curriculum folders. |
| 13 | Quick Capture UX | Added `timeout_seconds: 1` and changed toast copy to "Captured as local trace" so it no longer implies a saved observation. |
| 14 | PWA install surface | Replaced generic Research/Protect shortcuts with LV-native Capture Observation / Plan Lesson shortcuts. |
| 15 | Install/native launcher copy | Made installer and launcher copy more LV-specific and made port-conflict guidance more actionable. |

## Files Changed

- `src/education/parent_report.py`
- `src/education/content_differentiator.py`
- `src/education/assessment_generator.py`
- `src/web.py`
- `static/index.html`
- `static/manifest.json`
- `install.sh`
- `install.ps1`
- `contracts/UI_CONTRACT.yaml`
- `contracts/UI_CONTRACT.lock`
- `tests/test_content_differentiator.py`
- `tests/test_assessment_generator.py`
- `tests/test_pwa_manifest.py`
- `tests/test_teacher_api_phase2.py`
- `tests/test_quick_capture.py`
- `tests/test_ui_contract.py`
- `dev/INDEX.md`

## Verification

- `pytest -q tests/test_content_differentiator.py tests/test_assessment_generator.py tests/test_pwa_manifest.py tests/test_teacher_api_phase2.py tests/test_quick_capture.py tests/test_ui_contract.py` - 47 passed.
- `python3 -m pytest -q tests/test_parent_report.py tests/test_teacher_api_phase2.py` - 14 passed.
- `python3 -m pytest -q tests/test_install_hardening.py tests/test_install_launcher_scripts.py tests/test_project_metadata.py tests/test_privacy_log.py` - 26 passed.
- `PYTHONPATH=/home/mical/learning-architecture pytest -q tests/test_privacy_log.py` - 5 passed.
- `python3 -m py_compile src/education/content_differentiator.py src/education/assessment_generator.py src/education/parent_report.py src/web.py src/pwa.py` - pass.
- `python3 scripts/check_ui_contract.py --bump` - bumped and re-locked UI contract v8.
- `python3 scripts/check_ui_contract.py` - pass.
- `python3 -m src.lv_cli preflight` - 5/5.
- `python3 -m src.lv_cli health` - local model service reachable; provider=local.
- Fresh localhost server on port 8788 live-checked `/api/prepare/activity`, `/api/assess/rubric/g3-unit-1`, `/api/parents/recommendation`, `/manifest.json`, and root HTML snippets.
- `python3 -m pytest -q tests/` - 477 passed.

## Notes

- The first full-suite run found one real regression: `test_parent_report.py::test_draft_mentions_progress_when_cefr_improved` expected the word "progress." Fixed by keeping the warmer phrasing while restoring an explicit progress signal.
- One isolated `pytest` invocation of `tests/test_privacy_log.py` failed to import `src` when run with plain `pytest` in a mixed subset; `python3 -m pytest ...` and `PYTHONPATH=/home/mical/learning-architecture pytest ...` both pass. No code change made for that pre-existing import-path sensitivity.
- No commits were made.
