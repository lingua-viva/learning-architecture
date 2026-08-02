# Build Prompt — Evidence Attachment + Ethos Traits

You are implementing `dev/SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01.md`.
**Precondition**: Spec 1 (`SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES_2026-08-01.md`) is built —
`read_school_profile()` and the Category Profile panel exist. If they don't, stop and report.

Read first:

```text
dev/SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01.md
src/education/student_lens.py        (schema + append/recompute patterns; ethos_profile column ~778; soft-delete pattern)
src/education/parent_report.py       (full — generate_draft, approve, trauma-safety, attribution lock)
src/lingua_viva/governance.py        (check_publication_safety, lines ~374-430)
src/web.py                           (grep: /api/sources/records, /api/parents/recommendation, _strip_parent_output, /api/voice/act)
src/lingua_viva/google_drive_integration.py  (import_dir, list_connected_folders)
src/lingua_viva/config.py            (read_school_profile from Spec 1)
static/index.html                    (Sources view render fn; student detail view from Spec 1)
```

## Objective

An append-only `evidence_records` table; attach documents from Sources and direct teacher
feedback to students against support categories / ethos traits / strengths; school-configurable
ethos trait list; evidence summaries flowing into parent report drafts **behind the existing
safety gates**.

## Hard Rules

1. **Append-only evidence.** No UPDATE endpoint, no hard DELETE — soft-delete flag only,
   mirroring the students table `deleted`/`deleted_at` pattern.
2. **Provenance pointers, not file copies.** `source_ref` stores the sources record id/type.
   Never ingest file bytes into the lens DB.
3. **Gate order is sacred.** Evidence summaries are assembled INTO the draft BEFORE
   `_strip_parent_output()` and `check_publication_safety()` run. Do not add any parent-facing
   path that skips them. Do not touch the `attribution_visible_to_parent=False` hard-lock.
4. **Ethos UI hidden when no traits configured.** Empty `ethos_traits` → no panel, no endpoints
   erroring, everything degrades to current behavior.
5. **Additive only** on `/api/voice/act` (`ethos_suggestions` field) — existing response shape
   frozen.
6. **Hermetic tests** via the `_isolate` env pattern. **Do not commit.** UI contract ceremony:
   changelog comment, `--bump` from repo root, `EXPECTED_VERSION` update.

## Build Order

### Step 1 — Schema + store methods
`evidence_records` table per spec (evidence_id UUID PK, student_id FK, teacher_id, created_at,
kind, target_type, target_id, summary, source_ref JSON, confidence_level, deleted, deleted_at).
Startup migration guarded by table-exists check. Methods:
- `append_evidence(record) -> evidence_id` — validates kind/target_type enums, target_id against
  SUPPORT_CATEGORY_IDS / configured trait ids / {"academic","personal"} / None for background
- `list_evidence(student_id, target_type=None, target_id=None, include_deleted=False)`
- `soft_delete_evidence(evidence_id)`
- `_recompute_ethos_rollup(student_id)` — per-trait `{evidence_count, last_evidence_at}` into
  `ethos_profile`; call from append/soft-delete (same pattern as the CEFR/RTI recompute in
  `append_observation`)

### Step 2 — Endpoints
- `POST /api/students/{id}/evidence` — 404 unknown student; for kind=document resolve
  `source_ref` against the sources records backend (find the function `/api/sources/records`
  calls and reuse it — do not shell out through your own HTTP call); bogus ref → 400.
  Privacy-log event `evidence_recorded` (ids only).
- `GET /api/students/{id}/evidence` with target filters, grouped response
  `{by_target: {...}, total}`.
- `DELETE /api/students/{id}/evidence/{evidence_id}` → soft-delete.
- Register all three in `contracts/ROUTE_REACHABILITY.yaml`.

### Step 3 — Ethos config + suggestions
- Extend `read_school_profile()`: `ethos_traits` list, each `{id, label, description}`;
  validate ids `^[a-z_]+$`, drop invalid entries with a logged warning, never raise.
- In the `/api/voice/act` observation branch and `POST /api/observe/classify`: match transcript
  tokens against trait labels/descriptions (case-insensitive word match — keep it deterministic,
  no LLM); include `ethos_suggestions: [{trait_id, matched_term}]`. One-tap confirm in the UI
  POSTs a `teacher_feedback` evidence record.

### Step 4 — Report integration
In `ParentReportGenerator.generate_draft()`: optional `include_evidence_summaries` (default
False for now — the endpoint passes True only when the teacher checks "include evidence" in the
Parents view). Pull teacher_confirmed evidence summaries per trait/category, cap at ~3 per
target, append to the draft body sections. Confirm by reading the code that the assembled body
then flows through the trauma-safety check, `_strip_parent_output()`, and
`check_publication_safety()` — write the regression test BEFORE wiring, watch it fail on a
gate-bypassing implementation, then implement correctly.

### Step 5 — Frontend
- Sources view: "Add as evidence" on each record → student picker + target picker → POST.
- Student detail: "Evidence" tab (grouped list, soft-delete with confirm) + ethos panel
  (per-trait rollups, quick feedback line + trait picker).
- Parents view: "Include evidence summaries" checkbox.

### Step 6 — Tests (`tests/test_student_evidence.py`)
1. Append/list/soft-delete; enum + target validation; bogus source_ref → 400
2. Ethos rollup recompute correctness
3. Empty trait config → no suggestions, panel hidden flag in response
4. voice/act: ethos_suggestions additive, existing fields byte-identical for a no-trait config
5. **Gate regression**: evidence summary containing a student's full name → draft flags
   `review_required=True` with the name violation from `check_publication_safety`
6. Privacy events written; all hermetic

### Step 7 — Verify
```bash
python3 -m pytest tests/test_student_evidence.py tests/test_ui_contract.py -q
python3 -m src.lingua_viva.cli preflight
python3 -m pytest -q tests/
```

## Definition of Done

- [ ] Documents and teacher feedback attach as append-only evidence with provenance
- [ ] Ethos traits configurable; feedback lands per-trait; rollups on the lens
- [ ] Evidence summaries reach report drafts strictly behind existing gates (regression test proves it)
- [ ] Route reachability + UI contract updated, full suite green
