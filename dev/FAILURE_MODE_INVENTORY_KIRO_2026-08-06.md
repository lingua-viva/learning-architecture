# Failure Mode Inventory — Kiro Audit 2026-08-06

**Source commits audited:**
- `303b7cc feat: build Still I Rise phase 1 fixes`
- `f164359 feat: add SIR traits and absence signal`

**Plus two code fixes applied this session (not yet committed):**
- `src/education/parent_report.py` — personal_context exclusion from evidence summaries
- `src/web.py` — voice-act dedup guard (60s window)

**Test suite status after fixes: 2005 passed, 13 skipped, 0 failed.**

---

## Part 1 — What the commits got right (verified by code + test inspection)

| Item | Status | Evidence |
|------|--------|----------|
| `.xlsx`/`.docx` extraction | ✅ SOLID | `_xlsx_text`, `_docx_text` in extract.py; library import guards with clear errors; `test_xlsx_roster_extracts_cell_text`, `test_docx_roster_extracts_paragraph_and_table_text` |
| Unsupported format fails honestly | ✅ SOLID | ValueError with supported format list; `test_real_unsupported_upload_fails_honestly` |
| Bulk roster confirmation gate (>2 students) | ✅ SOLID | `BULK_IMPORT_CONFIRMATION_THRESHOLD = 2`; all detected names route to `needs_confirmation`; `test_bulk_roster_requires_confirmation_before_creating_students` |
| Single/dual detection auto-creates (regression check) | ✅ SOLID | `test_full_chain_creates_grounded_lenses` — 2-student doc auto-creates |
| Bulk undo by job_id | ✅ SOLID | `DELETE /api/students/ingest/{job_id}`; archives exactly that job's students; `test_bulk_undo_archives_only_students_from_that_import`, `test_bulk_undo_does_not_touch_students_from_another_import` |
| Job persistence across restart | ✅ SOLID | `_save_ingest_job` writes JSON to disk; `_ingest_job` reads from disk when not in memory; `test_ingest_job_status_survives_memory_reset` |
| G1-G12 canonical grade list | ✅ SOLID | `STUDENT_GRADE_LEVELS = tuple(f"G{grade}" for grade in range(1, 13))`; `create_student` validates against this; curriculum content is irrelevant |
| Perplexity/Rime key persistence | ✅ SOLID | `service_api_key()` + `save_service_api_keys()` in config.py; `POST /api/settings/keys`; never echoes plaintext back; env var fallback preserved |
| Still I Rise ethos seed (2 values + 7 attributes) | ✅ SOLID | `ethos_seed()` returns schema_version 1 with self_worth, self_discipline + 7 learner attributes; `validate_ethos` structural validation; keyword matching with word-boundary anchoring |
| `personal_context` support category | ✅ SOLID | In `SUPPORT_CATEGORY_IDS`, `SUPPORT_CATEGORY_LABELS`, signal patterns, and API /api/categories response |
| Observation dedup (observe/capture) | ✅ SOLID | Same student+teacher+transcript within 60s returns existing ID with `deduplicated: True` |
| General observation no-invention | ✅ SOLID | `template_type == "general"` nulls cefr_*, sel_* at web.py L3921-3927; pipeline.capture() passes only what's given |
| Local grounded student Q&A (F3 fix) | ✅ SOLID | `hit == "student_name_detected"` routes to `run_teacher_query` locally; no Perplexity egress; honest degradation on model unavailable |
| `@absence` vocabulary + classifier | ✅ SOLID | Regex in absence_coverage.yaml; classifier routes correctly; "I'm out of paper" does NOT trigger |
| Absence Slack retries idempotent | ✅ SOLID | `_is_duplicate` checks envelope_id, client_msg_id, channel+ts; bounded set with FIFO eviction |
| Staffing-summary absence rows in API | ✅ SOLID | Compact row objects with record_id, reported_by, date_for, time_window, periods, status, coverage_requested, needs_review |
| Daily Absences panel in UI | ✅ SOLID | Renders staffing.absences with structured metadata only (no raw Slack text) |
| Parents → Summaries nav rename | ✅ SOLID | Nav tuple `["parents", "Summaries", "👨👩👧"]`; title "Student Summaries" |
| Ethos traits visible on student profile | ✅ SOLID | `renderEthosRollups(lens)` shows badge per trait with evidence count |
| Dependencies in bootstrap.ts | ✅ SOLID | `openpyxl>=3.1,<4`, `python-docx>=1.1,<2` listed alongside existing deps |
| Dependencies in pyproject.toml | ✅ SOLID | Both listed in `[project] dependencies` |
| Confirm UI (bulk checkboxes + confirm subset) | ✅ SOLID | `data-ingest-confirm-check`, `display_names: names` in frontend; `test_bulk_confirm_subset_creates_only_selected_students` |

---

## Part 2 — Failure modes I found and fixed this session

### FIX 1: Personal Context evidence leaked into parent summaries (PRIVACY)

**Severity:** HIGH — safeguarding/family data reaching parent output  
**Root cause:** `parent_report.py`'s `include_evidence_summaries` loop called `store.list_evidence(student_id)` with no category filter — personal_context evidence (even if teacher_confirmed) would appear in the report body.  
**Fix:** Added `if item.get("target_id") == "personal_context": continue` inside the evidence loop.  
**Test:** `test_personal_context_evidence_excluded_from_parent_summaries` — creates personal_context evidence, generates report with `include_evidence_summaries=True`, asserts no sensitive text appears.  
**QA source:** Prompt failure-mode list: "Summary includes Personal Context or safeguarding data."

### FIX 2: Voice-act observation writes lacked dedup guard (DATA INTEGRITY)

**Severity:** MEDIUM — duplicate observation records from network retries  
**Root cause:** `/api/observe/capture` had a 60s dedup check (v116), but `/api/voice/act`'s observation write path called `pipeline.capture()` directly without the same guard.  
**Fix:** Added identical dedup logic (same student+teacher+transcript within 60s) to the voice-act `capture(store)` closure.  
**Test:** `test_observe_capture_dedup_within_60s` + `test_voice_act_dedup_within_60s` — both confirm dedup works.  
**QA source:** Prompt failure-mode list: "Duplicate observations are accepted with no warning."

---

## Part 3 — Failure modes verified as NOT present (I checked, they don't exist)

| Claimed failure mode | Verdict | Why |
|---------------------|---------|-----|
| Voice action writes inferred CEFR/SEL not explicitly present | NOT PRESENT | voice-act's parse_observation_context only picks cefr_dimension/level when evidence is in the transcript (BUG-5 fix); template defaults to "literacy" without clinical fields |
| `@absence` from unmapped Slack user fabricates identity | NOT PRESENT | SlackOpsBot's `_resolve_teacher(user_id)` returns None for unmapped users → bot responds with a non-acknowledgement, no record created |
| Slack bot touches student lenses | NOT PRESENT | `slack_ops_bot.py` imports only from `ops_records`, `ops_classifier`, `ops_packs` — never from `student_lens` or `observation_capture`; no `append_observation` call exists |
| Ask sends student data externally | NOT PRESENT | PII gate (`_ask_personal_data_hit`) runs BEFORE key check; student-named → local route or refuse; roster-unreadable → fail closed |
| Import creates support/ethos claims without teacher confirmation | NOT PRESENT | Ingest pipeline creates student lenses with profile fields from the extraction but support entries require explicit `pipeline.capture()` or `add_support_entry()` calls from teacher action |
| Category signals fire on vague behavior for personal_context | NOT PRESENT | Signal keywords require "safeguarding", "child protection", "abuse", "domestic violence", etc. — tested with 7 vague/explicit sentences, all correct |

---

## Part 4 — Failure modes that remain open (not fixable in code alone)

| Failure mode | Why it's still open | What would fix it |
|---|---|---|
| Voice STT dependency packaging (macOS signed app) | `com.apple.security.device.audio-input` entitlement requires re-sign + re-notarize — can't do locally | Next desktop build must verify entitlements; test added at P1-1 in Chip QA |
| Ask from Prepare/Plan workflow context | No UI path exists to invoke Ask from within Prepare/Plan yet | Feature flag or button addition in static/index.html |
| Drive CPS/Personal Context folder routing | Gated on Christianna's input (Items 6-11 in build plan) | Wait for input per plan |
| Observation dedup at voice-act also surfacing in the UI | The voice-act response returns `deduplicated: True` but the frontend doesn't explicitly show "already saved" feedback on dedup | UI copy change in static/index.html |
| Publication safety gate fires after content shown | Parent report shows draft THEN runs safety check — pedagogically correct (teacher must see to fix) but the prompt questions this order | Architectural decision: flag-not-block is deliberate (v59 design) |

---

## Part 5 — Files changed this session

| File | Change |
|------|--------|
| `src/education/parent_report.py` | personal_context evidence exclusion |
| `src/web.py` | voice-act dedup guard |
| `contracts/UI_CONTRACT.yaml` | v122 bump log |
| `contracts/UI_CONTRACT.lock` | Re-locked hashes |
| `tests/test_ui_contract.py` | EXPECTED_VERSION → 122 |
| `tests/test_parent_report.py` | personal_context exclusion test |
| `tests/test_observation_dedup.py` | NEW — dedup tests for observe/capture + voice-act |

---

## Summary

The two 2026-08-06 commits are structurally sound. Items 1-5 from the build plan are implemented correctly with proper test coverage. The Still I Rise traits, absence signal, and personal_context category are in place.

I found and fixed **2 real failure modes** that would have affected the 2026-08-20 demo:
1. Personal context data leaking into parent summaries (privacy-critical)
2. Voice-act observations duplicating on retry (data integrity)

The system is ready for the next build window (Items 6-11, gated on school input) and for QA packaging verification (mic entitlements, first-run UX).
