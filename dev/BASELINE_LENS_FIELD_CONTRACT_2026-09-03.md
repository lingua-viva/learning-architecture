# BASELINE — lens field contract, Rung 1 (nothing fixed)

**Date:** 2026-09-03 (measured 2026-09-03 21:00–22:00 PDT; sandbox timestamps read 2026-09-04Z)
**Seat:** PC-23, fresh window · **Operator:** Mical Neill (away)
**Spec:** `dev/SPEC_LENS_FIELD_CONTRACT_2026-09-03.md` · **Procedure:** `dev/PROMPT_LENS_FIELD_CONTRACT_4RUNG_2026-09-03.md`
**Branch:** `fix/cefr-write-and-unknown-field-refusal-2026-09-03` · **HEAD at measurement:** `a08f1c62efebd72bf7568f6e78812cfe0c29efea`

Every figure below was read from the tree or produced by a command run in this
window. Where a number in the spec differs, the tree wins and the difference is
noted. **No source file was changed in Rung 1.** Probe scripts live untracked
under `scratch/` (not gitignored — left untracked on purpose).

---

## RUNG 0 — gate

```
git status --porcelain            -> 0 lines (exit 0)
git rev-parse HEAD                -> a08f1c62efebd72bf7568f6e78812cfe0c29efea
git branch --show-current         -> fix/cefr-write-and-unknown-field-refusal-2026-09-03
git merge-base --is-ancestor d7e83aadd HEAD   -> exit 0   (the spec's base commit is in HEAD)
git merge-base --is-ancestor HEAD origin/main -> exit 1   (branch has NOT merged)
origin/main = 7037037d97c179ab1d4887f48bf3d8b4264cea22
   main has 2 commits HEAD lacks: 0c16607, 7037037 — both `chore(release): desktop-v0.2.84`,
   touching desktop/package.json and docs/index.html only. No source overlap.
   HEAD has 7 commits main lacks (the spec/prompt/start-here docs + the CEFR fix).
```

Base stays the fix branch (not merged). Rung 0 exit gate met. The operator's
real store was read once, **read-only** (`?mode=ro`), to prove it was not
touched: `~/.lingua-viva/runtime/student_lenses.db` mtime `2026-09-03 14:24:03`,
2 active rows (the two fixture students the briefing names), 0 observations —
identical before and after every measurement below.

---

## B1 — the lists, read from the tree

Command: the prompt's B1 snippet, plus `docpipe/lens.py::PROFILE_FIELDS`.

| list | file:line | len |
|---|---|---|
| `STUDENT_LENS_FIELDS` | `src/lingua_viva/data_in_contracts.py:114` | **58** |
| `SUPPORT_CATEGORY_IDS` | `src/education/student_lens.py:63` | **9** |
| `_LENS_FIELD_IDS` | `src/lingua_viva/docpipe/lens_extract.py:274` | **10** |
| `StudentLensStore.UPDATABLE_PROFILE_FIELDS` | `src/education/student_lens.py:1192` | **5** |
| `PROFILE_FIELDS` (docpipe.lens.v1) | `src/lingua_viva/docpipe/lens.py:15` | **10** |
| `SUPPORT_PROFILE_CATEGORIES` (feeds list 1) | `src/lingua_viva/data_in_contracts.py:92` | 8 |
| `CATEGORY_SIGNALS` keys (Observe's router) | `src/education/observation_capture.py` | 9 (== SUPPORT_CATEGORY_IDS) |

```
only in SUPPORT_CATEGORY_IDS : ['advanced_enrichment', 'personal_context']
only in _LENS_FIELD_IDS      : ['academic_strengths', 'personal_strengths', 'strategies_trialed']
_LENS_FIELD_IDS == PROFILE_FIELDS : True      (the docpipe world agrees with itself)
ethos_profile declared in STUDENT_LENS_FIELDS : False
strengths_profile / sel_summary / background_notes / avoid_pairing_with in STUDENT_LENS_FIELDS : False
SUPPORT_PROFILE_CATEGORIES vs SUPPORT_CATEGORY_IDS : personal_context missing from the former
```

Matches spec §1.1 exactly (the numbers had not moved). Correction to the spec's
framing: it is **five** lists, not four — `PROFILE_FIELDS` is the fifth and
§2.7.4 already acknowledges it.

---

## B2 — emittable field paths, enumerated from source

Every `field_path=` site in `src/` (grep), each read; the variable ones expanded
from the constant they draw on. Script: `scratch/b2_b3_count.py`.

| emitter | site | paths |
|---|---|---|
| `_extract_cefr` | `lens_extract.py:109` | `cefr_snapshot.{reading,writing,speaking,listening}` (4) |
| grade-scale / learner-profile / ATL / attendance heuristics | `lens_extract.py:126,145,164,184` | `support_profile.categories.learning_and_cognition.{evidence,strengths}`, `…attendance_and_engagement.evidence` (3) |
| `_route_to_support_category` | `lens_extract.py:204` | `support_profile.categories.{9 CATEGORY_SIGNALS}.evidence` (9) |
| `_route_to_ethos` | `lens_extract.py:225` | `ethos_profile.traits.{9 ethos.yaml traits}.evidence` (9) |
| classify-batch failure | `lens_extract.py:628` | `unclassified` at status `classify_failed` (1) |
| sentence classify (batch LLM / keyword / single LLM) | `lens_extract.py:734, 763, 821, 1017` | `support_profile.categories.{8 of _LENS_FIELD_IDS}.evidence` **incl. `strategies_trialed`**, plus bare `academic_strengths`, `personal_strengths` (10) |
| whole-doc LLM | `lens_extract.py:1264` | anything in `STUDENT_LENS_FIELDS` (58; filtered by that list) |
| `extraction_engine.extract` | `extraction_engine.py:440` | anything in `STUDENT_LENS_FIELDS` (58); callers `web.py:4467, 4522, 6167` |

**B2 = 72 distinct emittable paths.**

---

## B3 — writer-implemented paths

Measured by probing `write_student_lens` with one well-formed field (status
`verified`, one chunk id, valid value) per B2 path on a throwaway DB.

**B3 = 55 of 72 land in `written_fields`.**

The writer's de-facto accepted set, read off its `if/elif` chain
(`student_lens_writer.py:121-277`), is **61**: `campus`, `grade_level`,
`trauma_flag` (confirm-only), 4 × `cefr_snapshot.*`, and
9 categories × 6 buckets of `support_profile.categories.*`. Six of those 61 are
accepted but emitted by nothing: the five non-evidence buckets of
`personal_context`, and `trauma_flag` which lands in review by design.

---

## B4 — emitted but not written (B2 − B3 = 17), with WHERE each lands

| landing | paths |
|---|---|
| **ABSENT FROM ALL THREE LISTS (silent drop, live today)** | `support_profile.categories.strategies_trialed.evidence` |
| refused by name | `ethos_profile.traits.{9}.evidence` (9) |
| refused by name — **store has an operation for it** | `academic_strengths`, `personal_strengths` (`add_profile_strength`, `student_lens.py:2411`); `home_languages`, `learning_differences` (`update_profile`, `:1200`) |
| refused by name, after being consumed | `display_name` — used at `:74-81` to create the lens, then hits the unknown-path refusal at `:293` |
| refused, content-free by design (P0-3) | `unclassified` |
| review_required by design | `trauma_flag` |

### B4a — the writer's remaining silent-drop shapes (`scratch/b3_b4_probe.py`)

The 2026-09-03 refusal rule closed the end of the loop, but the
`support_profile.categories.` branch has its own end (`student_lens_writer.py:174-199`):
a path that enters that branch and does not satisfy `cat_id in SUPPORT_CATEGORY_IDS`
falls out of it with a bare `continue` — **not written, not reviewed, not refused.**

```
support_profile.categories.strategies_trialed.evidence      verified -> ABSENT FROM ALL THREE   <- EMITTED at lens_extract.py:734
support_profile.categories.academic_strengths.evidence      verified -> ABSENT FROM ALL THREE
support_profile.categories.not_a_category.evidence          verified -> ABSENT FROM ALL THREE
support_profile.categories.learning_and_cognition           verified -> ABSENT FROM ALL THREE   (3 segments)
support_profile.categories.learning_and_cognition.not_a_bucket        -> EXCEPTION ValueError   <- uncaught: voids the whole import (glass-box violation)
```

`strategies_trialed` is the CEFR defect, alive, one field over: the batch
classifier is *told* to route sentences to `strategies_trialed`
(`_FIELD_DESCRIPTIONS`, `lens_extract.py:295`), builds
`support_profile.categories.strategies_trialed.evidence` (`:734`), and the writer
discards it without a word. It did not show in B5 only because this machine
has no model to run the classifier.

Also measured: every heuristic extractor emits `supporting_chunk_ids=[]`
(`lens_extract.py:113,130,149,168,188,208,229`); fed directly, CEFR and
support entries are refused for missing source references. In the real pipeline
they arrive with chunk ids (B5: 51/51 had them), so a later step backfills
them — **CANNOT-TELL where** without reading past the briefing's stop line.

---

## B5 — the report-card round trip, end to end over HTTP, sandboxed

```
SB=/c/Users/spide/AppData/Local/Temp/claude/lv_rung1   (fresh; rm -rf first)
LV_CONFIG_HOME=$SB LV_STATE_HOME=$SB PYTHONPATH=. python src/web.py 8821
/api/health -> routers_loaded 5 / routers_expected 5
isolation check: $SB/runtime/student_lenses.db EXISTS after the roster step   (held)
extraction log landed at $SB/imports/20260904T041437Z_synthetic_report_card_abigail.txt.ndjson   (sandbox, not ~)
```

Driver `scratch/b5_roundtrip.py`, artifacts `$SB/b5_*.json`. Chain as the
prompt lists it. Roster: `ingest` → `preview` → `approve` (returns
`creating`, creates nothing) → `done` with 1 `needs_confirmation` → `confirm`
→ `student-abigail-chang` created. Note: the roster CSV carried `Grade: G3`
and the lens's `grade_level` is empty afterwards — roster ingest does not set it.

**Import preview (51 fields, 14 distinct paths):**

```
verified            8   cefr×4, learning_and_cognition.{evidence,strengths},
                        attendance_and_engagement.evidence, advanced_enrichment.evidence
needs_confirmation  5   ethos.{emotional_intelligence,self_discipline,social_intelligence}.evidence,
                        communication_and_language.evidence, executive_functioning.evidence
classify_failed    38   unclassified   <- no local model on PC-23 (server.log: local_only_no_model)
```

**Apply (HTTP response):**

```
keys returned      ['fields_written', 'review_required', 'student_id', 'written_count']
fields_written      8     review_required 5     written_count 8
unresolved_questions in payload:  FALSE
```

**The writer's own result (replayed from the saved log on a COPY of the sandbox DB):**

```
written_fields 8 · review_required 5 · unresolved_questions 38   -> 8+5+38 = 51 = every field that entered
```

So the writer accounts for every field **by count**; the 38 refusals are
content-free and do not name `unclassified` (by design, P0-3). But
**`routers/document_import.py:221-228` drops `unresolved_questions` from the
HTTP response.** Over the wire the teacher saw 8 written, 5 to review, and
nothing at all about 38 sentences. The glass-box invariant holds in the
function and is broken at the boundary the teacher actually uses.

**Lens after apply:** `cefr_snapshot = {reading A2, writing A1, speaking A1, listening A2}` — correct.

**Idempotency (same import applied twice):**

```
support_profile.learning_and_cognition   strengths 2, evidence 2
support_profile.attendance_and_engagement evidence 2
support_profile.advanced_enrichment      evidence 2
observations: cefr × 4 dimensions × 2 = 8      profile_version 17
duplicate texts inside buckets: 4
```

**Re-import double-writes everything.** The docpipe bridge (B8) dedupes by
evidence key; the writer has no such notion.

Also: `evidence_records` count is 0 after import — the report-card path never
touches the unified evidence ledger.

---

## B6 — bounded test baseline

Command (redirected whole, not piped; exit code appended bare):

```
PYTHONPATH=. python -m pytest tests/ -q -p no:randomly -rf \
  -k "lens or extract or writer or docpipe or observation or student or contract" \
  --ignore=tests/test_daily_file.py --ignore=tests/test_document_intelligence.py \
  > scratch/baseline_20260903.txt 2>&1
```

```
13 failed, 790 passed, 4 skipped, 2170 deselected, 32 xfailed, 1 warning in 585.27s
pytest_exit=1
```

Full failure list preserved in `scratch/before.txt` (13 ids) and reproduced
here so the Rung 4 diff has a committed anchor:

| test id | first error line | class |
|---|---|---|
| `tests/evals/layer2_retrieval/test_document_classification.py::test_L2_CLASS_005_student_records_blocked` | `ModuleNotFoundError: No module named 'sqlite_vec'` | missing package on PC-23 |
| `tests/evals/layer5_gauntlets/test_gauntlet_wrong_input_rejection.py::test_gauntlet_student_records_blocked_at_ingest` | same | same |
| `tests/test_document_ingest_endpoint.py::test_ingest_endpoint_rejects_student_records_type` | same | same |
| `tests/test_brief_endpoint.py::test_brief_returns_recent_observation_count` | `FileNotFoundError: [WinError 2]` | subprocess binary not on PATH here (`python3`-class) |
| `tests/test_brief_endpoint.py::test_brief_returns_unobserved_students` | same | same |
| `tests/test_support_bundle.py::test_bundle_excludes_student_data_patterns` | same | same |
| `tests/test_docpipe_extract.py::test_extraction_is_schema_valid` | `ValueError: source sha256 does not match original content` | CRLF hash drift class (fixture bytes rewritten on checkout) |
| `tests/test_docpipe_extract.py::test_model_veto_flags_never_deletes` | same | same |
| `tests/test_docpipe_extract.py::test_job_runs_to_done_and_writes_extraction` | same | same |
| `tests/test_docpipe_extract.py::test_crashed_job_resumes_to_done_without_partials` | same | same |
| `tests/test_docpipe_vault.py::test_put_and_get_source_extraction_lens_rebuilds_manifest` | same | same |
| `tests/test_ui_contract.py::test_ui_contract_check_passes` | `locked 990e4239… actual b86e20a7…` | the known false CRLF failure — **`--bump` NOT run** |
| `tests/test_ui_contract.py::test_ui_contract_lock_matches_live_files` | same | same |

**All 13 are PC-23 platform artifacts** (three classes: a package not
installed here, a subprocess binary not on PATH here, CRLF checkout changing
bytes that are hashed). None exercises the lens writer, the extractor, or the
store. `tests/test_lens_writer_field_coverage.py`,
`tests/test_ingestion_extraction_mapping_v2.py` and
`tests/test_batch_classify_provenance.py` all passed. The classes are stated
as read from the first error line of each block; **CANNOT-TELL** whether the
five sha256 failures are CRLF specifically without normalising and re-hashing
each fixture, which is Rung 4's job if they move.

---

## B7 — every `students` column classified

Read from `_init_schema` (`student_lens.py:889-912`), the write paths, and the
reconstruction law in `get_lens_as_of` (`:2208`), which rebuilds **only**
`cefr_snapshot` and `rti_current_tier` from the logs.

| column | origin | declared shape / writer | note |
|---|---|---|---|
| `student_id` | authored | `create_lens` | identity |
| `display_name` | authored | `create_lens`; **no update path** (writer refuses it) | |
| `campus` | authored | `create_lens`, `update_profile`, writer raw SQL `:270` | |
| `grade_level` | authored | same as campus, writer raw SQL `:261` | |
| `home_languages` | authored | `create_lens`, `update_profile` — list[str] | writer refuses it |
| `learning_differences` | authored | same | writer refuses it |
| `trauma_flag` | authored, **restricted** | `create_lens`; writer raw SQL `:123` only on teacher confirmation | never auto-written |
| `avoid_pairing_with` | authored | `set_avoid_pairing_with` — list[student_id] | full replace by design |
| `rti_current_tier` | **derived** | from `rti_tier_history` via `update_rti_tier` / observation `rti_tier_changed_this_obs` | law: `:1187-1191` |
| `rti_tier_history` | **derived** (append-only log) | `[{tier, from, to, trigger}]` | |
| `cefr_snapshot` | **derived** | `{reading,writing,speaking,listening: level\|null}` from `observations` | law: `set_initial_cefr` docstring `:1136` |
| `cefr_trajectory_30d` | derived | enum `insufficient_data` ∪ `VALID_CEFR_DIRECTIONS`, `_compute_cefr_trajectory` | not reconstructed as-of |
| `sel_summary` | derived | `{recent_concerns, recent_positives, dominant_domain, last_urgency_flag}` from observations | not reconstructed as-of |
| `support_profile` | authored (append-only through store ops) | `{schema_version: 2, categories: {9 ids: {needs, strengths, strategies_worked, strategies_not_worked, evidence, open_questions}}, last_reviewed_at, last_reviewed_by}`; entry `{id, text, created_at, created_by, source_observation_id, source_ref_ids, confidence, active…}` | observations feed it through the SAME ops (`_fan_out_support` `:2051`); not reconstructed as-of |
| `strengths_profile` | authored (append-only) | `{schema_version: 1, academic_strengths[], personal_strengths[], last_reviewed_at, last_reviewed_by}` via `add_profile_strength` | in none of the five lists |
| `ethos_profile` | authored (append-only) + derived rollups | `{traits: {trait_id: {evidence[], …rollups}}}` via `add_ethos_evidence`; rollups from `evidence_records` (`_recompute_ethos_rollup` `:3038`) | in none of the five lists |
| `background_notes` | authored | free text ≤10k, `update_profile` | |
| `profile_version` | derived | counter, bumped by every write | |
| `created_at` / `updated_at` | system | | |
| `deleted` / `deleted_at` | authored | `delete_lens` tombstone | |

**UNCLASSIFIED: 0** — but one classification deserves the operator's eye
rather than my confidence: `support_profile` is *authored* by the store's
laws today (direct append, no as-of reconstruction), while the report-card
writer appends to it with **no observation record behind the entry**. If the
operator's intent is "everything about a child derives from an append-only
record", then `support_profile` entries written by import are the exception,
and that is a K7-class ruling, not a builder's call. Recorded, not decided.

---

## B8 — what the docpipe → store bridge carries and drops

`docpipe/lens.py::_sync_to_student_store` (`:340`) → `_bridge_one_field` (`:372`).
Live in production on two paths: roster ingest
(`routers/students.py:141-161`, `_create_lens_for_detected`) and class-folder
ingest (`class_folder_ingest.py:157`).

| docpipe field (PROFILE_FIELDS) | store operation | carried as |
|---|---|---|
| 7 × `SUPPORT_CATEGORY_FIELDS` (`PROFILE_FIELDS[:7]`) | `add_support_evidence(category_id=field_id)` | `support_profile.categories.{id}.evidence` — **evidence bucket only**, never needs/strengths |
| `academic_strengths` | `add_profile_strength(kind="academic")` | `strengths_profile.academic_strengths[]` |
| `personal_strengths` | `add_profile_strength(kind="personal")` | `strengths_profile.personal_strengths[]` |
| `strategies_trialed` | `add_support_entry(category_id="learning_and_cognition", bucket=worked/not_worked/open_questions)` | **RENAMED and RE-HOMED**: the docpipe field has no category; the bridge hardcodes `learning_and_cognition` (`:434-446`) |

Per evidence item, docpipe carries `{source_ref{type, source_id|obs_id, path},
span_id, confidence: float, added_at, added_by}` (`lens.py:88-96, 150-160`).
The bridge forwards `source_id` (as `source_ref_ids=[source_id]`),
`obs_id` (as `source_observation_id`), `added_by`; it **drops `span_id`, the
numeric `confidence` (coarsened to `imported_verified` / `teacher_confirmed`),
`added_at`, and `path`.**

Cannot cross at all (no docpipe representation): `advanced_enrichment`,
`personal_context`, `cefr_snapshot.*`, `trauma_flag`, `home_languages`,
`learning_differences`, `background_notes`, `avoid_pairing_with`, every
`ethos_profile` trait. The bridge is one-directional and idempotent
(`synced_evidence_keys`, `:347-357`) — the one property the writer lacks.

### K8 verdict

**K8 FIRES.** The bridge renames one field (`strategies_trialed` → a bucket
under an invented category) and drops per-evidence provenance (`span_id`,
numeric confidence). Per spec §2.7.4 and §9, reconciling the two lens
structures is the operator's ruling. See the report for the question, the
options, and the recommendation.

---

## B9 — every OUT consumer, its entry point, and the fields it actually reads

Read from the code (grep of `lens.get("…")` / `lens["…"]` per module, each
hit read in context), not inferred from names.

| consumer | entry point(s) | lens fields actually read |
|---|---|---|
| `education/parent_report.py` | `get_lens` `:164, :288` | `display_name`, `grade_level`, `home_languages` (+ observations via its own queries) |
| `education/content_differentiator.py` | `get_lens` (caller passes the dict) `:600-606` | `rti_current_tier`, `cefr_snapshot` |
| `education/help_artifacts.py` | `export_lens` `:262, :305` | `observations`, `cefr_snapshot`, `support_profile`, `rti_current_tier` |
| `education/cohort_planning.py` | `export_lens` `:107, :267` + roster dicts | `support_profile.categories`, `cefr_snapshot`, `student_id`, `display_name`, `rti_current_tier`, `observations` |
| `education/trend_analysis.py` | `get_lens` + `export_lens` `:128-129, :189` | `observations[].cefr_dimension/cefr_level_observed/recorded_at`, `display_name`, `rti_current_tier`, `cefr_trajectory_30d`, `student_id` |
| `education/access_control.py` | `get_lens` `:78`, `export_lens` `:104` | `student_id`, `display_name`, `observations[].teacher_id` — **the perspective class, already real** |
| `education/pipeline_execute.py` | `get_lens` `:268` | `display_name`, `cefr_snapshot`, `rti_tier_history` |
| `lingua_viva/drive_sync.py` | `export_lens` `:559`, `get_lens` `:693` | `display_name`, `grade_level`, `cefr_trajectory_30d`, `rti_current_tier`, `strengths_profile`, `support_profile`, `ethos_profile`, `observations` — the widest reader |
| `lingua_viva/governance.py` | `export_ethos_report` `:220, :547` | ethos report (derived view) |
| `lingua_viva/activity.py` | `export_ethos_report` `:139` | ethos report, `student_id` |
| `pipeline.py` | `export_lens` `:681` | `student_id`, `display_name`, `observations`, `cefr_snapshot` |
| `routers/students.py` | all four + `get_lens_as_of` `:712, 781, 1131, 1166, 1475, 1759, 1828, 1873, 1932, 1959` | returns whole dicts to the UI (the UI is the reader; not walked) |
| `web.py` | `export_lens` `:3437, :5641, :6231` | whole dicts into brief / parent report / markdown export |
| `docpipe/sync.py` | `vault.get_lens` `:197` | the docpipe structure, not the store |

**13 modules, 4 store entry points (+ `get_lens_as_of`), no declared contract**
— matches spec §2.8. `cefr_snapshot` and `rti_current_tier` are the most-read
fields (7 and 7 consumers); `background_notes`, `learning_differences`,
`avoid_pairing_with`, `sel_summary` are read by **no** consumer in `src/`
outside the store and routers.

---

## Delta from the spec's figures (read the tree, never quote the spec)

| figure | spec said | tree says |
|---|---|---|
| lists | 4 | 5 (`PROFILE_FIELDS`; spec §2.7.4 already knew) |
| emitted-but-unwritable | "at least the ethos namespace" | 17 paths; **1 still silently dropped**, 9 ethos + 5 store-supported refused by name |
| silent drops | "closed 2026-09-03" | closed at the loop's end; **open inside the support_profile branch** (B4a) |
| refusal reaches the teacher | assumed | **no** — dropped at `document_import.py:221` |
| re-import idempotent | acceptance for Rung 2 | **red today** (B5) |

## CANNOT-TELL (Rung 1)

- No local model on PC-23: 38/51 sentences `classify_failed`. The LLM-classified
  paths — including the live silent drop — were exercised only in-process, never
  over HTTP here.
- Where the pipeline backfills `supporting_chunk_ids` for heuristic fields (B4a note).
- Whether the UI renders the import *preview's* `unresolved_questions` (step 1
  does return them) or offers a confirm affordance for `review_required`. No UI walk.
- `extraction_engine.extract` (`web.py:4467/4522/6167`): which UX reaches it was not traced.
