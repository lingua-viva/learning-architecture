# Build Prompt — Base Lens: School Category Profile Wired End to End

You are implementing `dev/SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES_2026-08-01.md`.

Read first:

```text
dev/SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES_2026-08-01.md
src/education/student_lens.py          (lines 49-100 category IDs + confidence levels; 260-290 support_profile v2; 440-460 strengths_profile; 729-950 StudentLensStore, schema, create_lens)
src/education/observation_capture.py   (full — ObservationCapturePipeline.capture)
src/lingua_viva/voice_intent.py        (signal-list pattern you will mirror; parse_observation_context)
src/web.py                             (grep: /api/students, /api/observe/classify, /api/voice/act)
src/lingua_viva/config.py              (read_provider_config — the Tier 2 config pattern)
src/lingua_viva/privacy_log.py         (event style)
static/index.html                      (renderStudents ~1807, renderObserve ~1545)
tests/test_voice_intent.py             (the _isolate(monkeypatch, tmp_path) hermetic pattern — reuse it)
```

## Objective

The school's IEP-style categories already exist as schema. Wire them: (1) profile edit
endpoint with `background_notes`, (2) category auto-suggestion from observation transcripts,
(3) strategies-trialed outcome parsing, (4) Category Profile panel in the student lens UI,
(5) Tier 2 school-configurable labels.

## Hard Rules

1. **Do not rename or remove any `SUPPORT_CATEGORY_IDS` value.** Existing SQLite lenses
   depend on them. Labels are configurable; IDs are frozen.
2. **Suggestions never auto-write into category buckets.** Below `CATEGORY_SUGGESTION_THRESHOLD`
   (define it as a module constant, start at 0.5 matching `WRITE_INTENT_THRESHOLD`), the entry
   goes to `open_questions` with `confidence_level: "model_suggested"`. No guessing — same
   principle as detect_student returning (None, None).
3. **Additive API changes only.** `/api/voice/act` and `/api/observe/classify` existing response
   fields must not change shape — the frontend voice wire and Chip's QA packet depend on them.
4. **Hermetic tests.** Every test uses the `_isolate` env pattern (LV_STUDENT_DB_PATH,
   LV_STATE_HOME, LV_PRIVACY_LOG_PATH, LV_REVISION_LOG_PATH → tmp_path). Never read the
   machine's real `~/.lingua-viva`.
5. **Do not commit.** Leave all changes for the operator's commit window.
6. **UI contract ceremony**: add changelog comment WITHOUT touching `version:`, run
   `python3 scripts/check_ui_contract.py --bump` FROM REPO ROOT, update `EXPECTED_VERSION`
   in `tests/test_ui_contract.py`.

## Build Order

### Step 1 — Schema + profile edit (backend only)
- Add `background_notes TEXT DEFAULT ''` to the students table with a startup migration
  (follow whatever migration pattern `StudentLensStore.__init__`/schema-setup already uses —
  ALTER TABLE guarded by a PRAGMA table_info check).
- `StudentLensStore.update_profile(student_id, fields: dict)`: whitelist
  `{campus, grade_level, home_languages, learning_differences, rti_current_tier, background_notes}`;
  unknown key → ValueError; bump `profile_version`, `updated_at`.
- `PATCH /api/students/{student_id}` in web.py: 404 unknown student, 400 unknown field,
  privacy_log event `profile_updated` (student_id only, no name).

### Step 2 — Category suggestion engine
- `suggest_support_categories(transcript)` in observation_capture.py. Signal lists as
  module-level dicts mapping category_id → list of regex/keyword signals (mirror the
  OBSERVATION_SIGNALS structure in voice_intent.py:25–45). Return list of
  `{"category_id", "confidence", "matched_signals"}` sorted by confidence.
- Wire into `POST /api/observe/classify` response as `category_suggestions` and into the
  `/api/voice/act` observation branch response (additive field).
- `parse_strategy_outcome(transcript)` in voice_intent.py: returns
  `{"strategy_statement", "outcome": "worked"|"not_worked"|None}`. Patterns: "tried X and it
  (worked|helped|clicked)" vs "tried X but ...", "didn't help", "still struggled". When outcome
  is non-None and a category suggestion clears threshold, capture() places the entry in
  `strategies_worked`/`strategies_not_worked` as `model_suggested`.

### Step 3 — Tier 2 config
- `read_school_profile()` in config.py: loads `~/.lingua-viva/config/school_profile.json`
  (respect LV_CONFIG_HOME). Returns `{category_labels: {...}, hidden_categories: [...]}` with
  shipped defaults on missing/invalid file. Never raises.
- Expose via existing settings/status endpoint or a small `GET /api/school-profile` (your
  call — check what the frontend can already reach; prefer reusing an existing settings fetch).

### Step 4 — Frontend Category Profile panel
- In the student detail view: 7 category sections (respect `hidden_categories`), each rendering
  needs / strengths / strategies ✓|✗ / evidence count / open questions from the lens export.
- Academic Strengths + Personal Strengths blocks from `strengths_profile`.
- Confidence badges: solid for `teacher_confirmed`, outlined "suggested" for `model_suggested`
  with a tap-to-confirm that POSTs the confirmation (reuse the existing observe/capture
  confirmation mechanics — find how `teacher_confirmed` flows today before inventing a new
  endpoint).
- Background section with inline edit → PATCH.

### Step 5 — Tests (`tests/test_school_categories.py`)
Cover, minimum:
1. update_profile happy path + unknown-field rejection + profile_version bump
2. PATCH endpoint 200/400/404 + privacy event written
3. Category suggestion: executive_functioning transcript → suggested; empty/vague transcript →
   nothing above threshold; below-threshold routes to open_questions not a bucket
4. Strategy outcomes: worked / not_worked / neither
5. voice/act response: `category_suggestions` present; existing fields unchanged; spoken
   confirmation still first-name-only (assert "Bianchi" not in spoken — copy the existing
   privacy assertion style)
6. read_school_profile: custom labels, missing file → defaults, corrupt JSON → defaults

### Step 6 — Verify
```bash
python3 -m pytest tests/test_school_categories.py tests/test_voice_intent.py tests/test_ui_contract.py -q
python3 -m src.lingua_viva.cli preflight
python3 -m pytest -q tests/    # full suite; 3 Drive OAuth failures are known-environmental on the operator machine
```

## Definition of Done

- [ ] PATCH profile endpoint live with background_notes
- [ ] Category suggestions from transcript, threshold-gated, never silent
- [ ] Strategies trialed split worked / not-worked
- [ ] Category Profile panel renders the school's list with confidence badges
- [ ] Tier 2 labels config with immutable IDs
- [ ] New tests + full suite green, UI contract bumped, ROUTE_REACHABILITY updated
