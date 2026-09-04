# DIAGNOSTIC — does every line of `src/` serve a UX? A reachability census

**Date:** 2026-09-03 (night) · **Seat:** PC-23 · **Operator:** Mical Neill
**Ask:** *"full diagnostic to check each and every line of code to make sure it serves a specific UX — we have trash-collection.py in MC for reference."*
**Instrument:** `scripts/trash-collector.py` (ported from mission-canvas, spec `mc:dev/SPEC_TRASH_COLLECTOR_2026-09-01.md`) + `config/reachability_roots.yaml` (13 declared roots) + `scratch/ux_census.py` (per-module, per-line, mapped to `dev/UX_MATRIX_AND_ACTION_LIST_2026-09-03.md` §2).
**Authority:** ADVISORY. Nothing was deleted. A finding is a testing defect or a wiring gap, not a deletion order. Three dispositions, never two: **MOUNT · DELETE · PENDING**.

---

## 1. Method, and what it can and cannot see

Roots are **declared, never inferred** (`config/reachability_roots.yaml`): the FastAPI app module body, the five routers (mounted by `importlib` string, invisible to a static graph, so declared directly), the two CLIs, and five hand-run scripts. Every `__main__` block under `src/` is accounted for (8/8); undeclared entry points: 0.

Two edges were added to the MC analyser for LV, both in the safe direction (they mark *more* code live, so the tool under-reports):

1. a FastAPI/Starlette registration decorator (`@app.get`, `@router.post`, `on_event`, `middleware`, `exception_handler`, `websocket`) reaches the decorated handler — without it every route read as unreached (product-reached went 1527 → 1830);
2. a function nested in a function is live when its parent is — LV passes closures to `_with_student_store(do_x)` on nearly every route (1830 → 1930).

**Blind spots, stated:** the graph covers `src/` only; `doctor/`, `ontology/`, `governance/`, `deliverables/` are reached as libraries and not analysed. Method calls resolve to every method of that name (over-approximation). `getattr(store, "add_to_roster")`-style dynamic lookups are invisible, so two of the findings below are known false positives and are marked.

## 2. The numbers (tree at `6841c99`)

```
lines in src/                57,183
  inside REACHED defs        43,375   75.9%   reached from a product or script root
  inside UNREACHED defs       1,769    3.1%   the subject of this report
  module-level statements    12,640   22.1%   imports/constants; run on import — every module
                                              is imported from a root except 3 (§4.1)
symbols (functions/methods)   2,077
  reached from product        1,930   92.9%
  reached from a script only      7
  tested but never reached       61   2.9%    <- FINDINGS (§4)
  referenced by nothing          79   3.8%    <- plain dead code, a different class (§5)
```

Read plainly: **97% of the lines that do anything are on a path a teacher, admin, or operator can reach.** The 3% that are not is 61 tested-but-unreached symbols and 79 unreferenced ones, listed below with what each one was for.

## 3. Per UX — which UX each module serves, and how much of it is reached

A module serving several UXs counts under each. `mod-lvl` lines run on import. Full per-module table: `scratch/ux_census.txt` (and `--json`).

| UX | what | modules | lines | reached | unreached | tested-unreached | unreferenced |
|---|---|---|---|---|---|---|---|
| U1 | Install & first run | 10 | 3,782 | 2,990 | 87 | 6 | 1 |
| U2 | Roster → lenses | 21 | 11,851 | 9,390 | 645 | 19 | 28 |
| U3 | Report card → lens | 24 | 11,739 | 8,361 | 685 | 21 | 32 |
| U4 | Observe → lens | 13 | 6,982 | 4,874 | 263 | 10 | 12 |
| U5 / U6 | Assess (oral / written) | 1 | 217 | 68 | 0 | 0 | 0 |
| U7 | View a lens | 3 | 5,886 | 5,311 | 187 | 6 | 8 |
| U8 | Edit a lens by hand | 2 | 5,514 | 5,044 | 158 | 4 | 8 |
| U9 | Prepare | 16 | 7,363 | 5,075 | 252 | 9 | 12 |
| U10 | Summaries / parent report | 7 | 1,608 | 969 | 83 | 4 | 2 |
| U11 | Ask | 20 | 5,654 | 3,801 | 253 | 4 | 17 |
| U12 | Sources / file map | 31 | 11,148 | 8,012 | 516 | 16 | 23 |
| U13 | Governance / Privacy / Health | 21 | 4,907 | 3,242 | 75 | 6 | 3 |
| U14 | Profile / Settings | 3 | 930 | 569 | 69 | 3 | 0 |
| U15 | Home / Daily / Plan (hidden for SIR) | 6 | 1,284 | 806 | 3 | 0 | 1 |
| U16 | Slack (hidden for SIR) | 12 | 5,650 | 4,077 | 79 | 6 | 5 |
| U17 | Reflect | 8 | 2,239 | 1,431 | 153 | 2 | 5 |
| U18 | Admin: query across lenses | 6 | 7,242 | 6,185 | 181 | 5 | 10 |
| U19 | Admin: teacher lenses | 4 | 1,027 | 658 | 31 | 2 | 1 |
| U20 | Admin: onboard a teacher | 1 | 277 | 182 | 0 | 0 | 0 |
| ALL | web.py + web_helpers | 2 | 7,249 | 7,691 | 3 | 0 | 1 |

Two readings the operator asked for, answered:

- **Every module now has a UX mapping** (0 unmapped; the map is hand-declared in `scratch/ux_census.py`, so it is a claim, not a measurement — the measurement is the reach column).
- **U5/U6 (Assess) has 217 lines and they are the MYP criteria generator**, not the SIR oral/written diagnostic. Assess for Still I Rise is not built; see `dev/ASSESS_CHANGES_NEEDED_2026-09-03.md`.

## 4. The 61 findings — tested, and never reached from a root

### 4.1 Unwired modules (no symbol reached)

| module | what | disposition |
|---|---|---|
| `src/lingua_viva/docpipe/grounding.py` (13 lines, `verify`) | docpipe grounding check | **PENDING** — tiny; either the docpipe path calls it or it goes with the docpipe→producer ruling |
| `src/lingua_viva/observe_to_lens.py` | was unwired at first run tonight | **MOUNTED** — now called from `/api/query` observe path (`web.py`), commit `6841c99` |

### 4.2 The ones that matter to a UX — MOUNT candidates

Each verified by grep: **no production reference anywhere in `src/`**.

| symbol | UX | why it matters | disposition |
|---|---|---|---|
| `injection_guard.detect_injection` | U11 U13 | **CORRECTED 2026-09-04:** the guard IS armed — its redaction half (`redact_injection`) runs at three seams: `document_parser.py:111` (parse time), `extraction_engine.py:107` (file text), `pipeline.py:210` (external egress). Only the detect-only twin is unreached, and the module's docstring rules that the teacher's own Ask queries are trusted input in a local-only app. First draft called this "an unarmed guard, complete-mediation failure" — wrong; the mechanism is in force. | **DELETE** `detect_injection` (retarget its tests at `redact_injection`'s list) or declare it a test seam. Do NOT arm it on the teacher's question. Open: verify the knowledge-library ingest path also parses through `document_parser` (CANNOT-TELL). |
| `safeguarding.pending_notifications`, `docpipe/sync.drain`/`loop`, `slack_socket.drain` | U13 U4 | queued safeguarding notifications and docpipe sync have drains that **nothing in product starts** (only the Drive drain is registered at startup, `web.py:1647-1681`). If a RED observation queues a notification, who delivers it? | **MOUNT** or state where they run — CANNOT-TELL tonight whether the desktop wrapper or a CLI starts them |
| `pdf_generator.render_parent_report_pdf` | U10 | the parent-report PDF renderer is never called; the differentiated-materials PDF is | **MOUNT** behind the parent-report approve flow, or DELETE if print-HTML is the product |
| `parent_report.approve`, `to_print_html`, `to_printable_text` | U10 | the approve/print half of Summaries is not on any route (`students.py:1886/1945` closures do something else) | **MOUNT** — U10 is on the SIR list |
| `content_differentiator.generate_with_teacher_lens`, `assign_packs_for_roster` | U9 U19 | teacher-lens-aware differentiation exists and Prepare does not use it | **PENDING U19** (teacher lenses not built) |
| `access_control.list_shared_students`, `get_colleague_observations` | U13 U19 | the *perspective* lens class (who may see what) is implemented and unreached | **PENDING U19/U20** |
| `student_lens.set_avoid_pairing_with`, `replace_support_profile` | U8 | editable-lens store operations with **no endpoint** | **MOUNT under U8** (hard-list item 5) |
| `observation_capture.confirm_ethos_suggestion` | U4 U13 | ethos suggestion confirm unreachable | **PENDING** the ethos ruling (report §6.1) |
| `poi_progression.register_unit`, `list_units`, `seed_default_units`, `default_units_for_year` | U9 | Programme-of-Inquiry unit seeding never runs | **PENDING** curriculum seeding decision |
| `ethos.save_ethos`, `teacher_lens_builder.ingest` | U19 | admin-side authoring, not built | **PENDING U19** |
| `config.connect_provider`, `verify_key`, `ollama_embedding_reachable` | U14 | provider-connect flow: `provider_config.py` wraps some of these; CANNOT-TELL which door the UI uses without reading it | **check** |
| `filemap.scan_directory` (public) | U12 | production calls `_scan_directory`; the public wrapper is test-only | **DELETE** the wrapper or retarget the 3 tests |

### 4.3 Superseded or duplicated paths — DELETE candidates (after a look)

| symbol | evidence |
|---|---|
| `docpipe/jobs.py` — `run_extraction_job`, `resume_pending`, `job_status`, `_new_job`, `_write_job` (1 of 11 reached) | roster ingest runs its own job loop in `routers/students.py:_run_ingest_job`; `jobs.py` looks superseded. Tests hold it up. |
| `docpipe/lens.merge_observation`, `sync_to_student_lens_store` (public) | the docpipe-side Observe merge; ruling A makes docpipe a producer and nothing calls this door. `_sync_to_student_store` (private) IS live via `create_from_extraction`. |
| `data_in_contracts.write_student_lens` | a re-export wrapper; production imports `student_lens_writer` directly; 3 tests import the wrapper |
| `docpipe/contracts.obs_id` property | only reachable through `merge_observation` above |

### 4.4 Declared seams and operator tooling — allowlist by docstring, not silently

`lens_field_contract.writable_paths` (used by tests and `scratch/b2_b3_count.py`), `model_gate.clear_model_gate_cache`, `defect_triage.triage_*`, `improve_surface.format_report`, `improvement_audit.format_report`, `reconcile.pending_count`, `runtime_paths.memory_data_dir`, `pipeline._provider_config_path`, `slack_credentials.field_source`, `vault.get_source`/`init`/`manifest`. Convention (from MC): a seam that exists for tests **says so in its docstring** and the allowlist counts it. None of these say so yet → they stay findings until they do.

### 4.5 Known false positives (dynamic lookups the graph cannot see)

`student_lens.add_to_roster` (called via `getattr(student_store, "add_to_roster")` in `docpipe/lens.py:_register_roster`), `student_lens.support_profile_default` (aliased through a staticmethod). Two of 61.

### 4.6 Not adjudicated tonight — PENDING triage

`observation_capture.assert_never_external`, `pending_sync_count`; `ops_bot_spec.approved_rules`/`candidate_rules`/`current_spec` and `slack_ops_bot._claim_coverage_with_confirmation` (U16, hidden for SIR); `ethos.format_traits_for_prompt`; `lens_extract._classify_sentence_to_field`; `lesson_materials.assign_tier_groups`; `voice_intent.detect_student`; `google_drive_oauth._decode_id_token_email`; `google_drive_integration.clean`. Each is a test pitched at a helper; each needs a reader, not a verdict from a graph.

## 5. The 79 unreferenced symbols

Reached by nothing, tested by nothing. This is plain dead code — a different class from §4 and the one that IS safe to delete once someone reads the module. Concentrated in: `pipeline_execute.py` (8 of 12 symbols, 176 lines — U11's action loop is mostly unreached), `docpipe/sync.py` (6), `docpipe/jobs.py` (5), `student_lens.py` (8), `routers/students.py` (18 — helpers left behind by the web.py → router move), `web.py` (18). The collector's `--json` does not list them individually yet; the census script counts them per module (`scratch/ux_census.txt`, column `unref`).

## 6. Also run tonight — the repo's own gates

| gate | result |
|---|---|
| `scripts/check_route_reachability.py` | OK — 196 routes classified (149 reachable, 47 backend-only, 34 `deferred_undecided` awaiting an operator decision) |
| `scripts/check_app_reality.py` | 24 pre-existing MEDIUM findings, all "template value rendered without escapeHtml" in `static/index.html` — not touched |
| `scripts/check_ui_contract.py` | fails falsely on this box (CRLF vs LF-locked digest). `--bump` NOT run. |
| `python -m doctor.support_loop doctor` | **crashed** (hardcoded `python3`, `WinError 2`) → fixed in `3eaa943`; now runs: 15 files, 7 gates, gauntlet PASS; overall BLOCKED only because branch ≠ main and worktree dirty (its policy) |

## 7. What to do with this

1. ~~Arm `detect_injection`~~ — corrected 2026-09-04: the redaction guard is armed at three seams; delete the detect-only twin or mark it a test seam (§4.2). The open question is whether every retrieved-text path into Ask goes through `document_parser`.
2. Answer who drains safeguarding notifications. If nothing does, RED observations are being queued and never delivered.
3. U8's two store ops need endpoints; U10's approve/print half needs a route. Both are on the SIR list.
4. Re-run `python scripts/trash-collector.py` after every wiring change; the delta is the proof.

## 8. CANNOT-TELL

- Whether the desktop (Electron) wrapper or an `lv` CLI command starts the sync/notification drains — outside `src/`.
- Whether `provider_config.py`'s wrappers are the live provider-connect door (not read).
- The individual list of the 79 unreferenced symbols (counted, not listed).
- Whether `pipeline_execute.py`'s 176 unreached lines are the operator's "actions" (`actions.py` is 100% reached; `pipeline_execute` is the loop that runs them — CANNOT-TELL if the UI reaches that loop at all).
