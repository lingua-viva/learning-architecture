# SPEC: Base Lens — School Category Profile (IEP-Style), Wired End to End

**Created**: 2026-08-01
**Status**: DRAFT — operator review before build
**Priority**: 1 of 5 (direct customer ask, foundation for Specs 2, 3, 5)
**Customer evidence** (school partner Slack channel, two teachers):
> "Here are the categories again: Learning and Cognition / Communication and Language / Executive Functioning / Social Skills / Emotional Regulation / Physical-Sensory Needs / Attendance and Engagement. Plus: Strategies trialed — successful or not, Academic Strengths, Personal Strengths. These would then be populated by teacher feedback directly."
> Teacher B: "We create a student profile and then where can we add any background info?"

---

## The Finding That Shapes This Spec

The school's list **already exists as schema**. `src/education/student_lens.py`:

- Lines 63–83: `SUPPORT_CATEGORY_IDS` — the exact 7 categories (+ an 8th, `advanced_enrichment`)
- Lines 260–277: support_profile v2 — per-category buckets `needs`, `strengths`, `strategies_worked`, `strategies_not_worked`, `evidence`, `open_questions`
- Lines 442–449: `strengths_profile` with `academic_strengths` + `personal_strengths`
- Line 778: `ethos_profile` column (used by Spec 2)
- Lines 85–90: confidence levels `teacher_confirmed` / `model_suggested` / `imported_verified` / `imported_needs_confirmation`

**This spec is not schema design. It is wiring.** Three gaps stand between the schema and what the teachers described:

1. **No profile edit path.** `POST /api/students` (web.py:3322–3340) creates; nothing updates. Profile changes only flow implicitly through `append_observation()`. Teachers literally cannot "add background info" today.
2. **Voice/text observations don't populate the category buckets.** `/api/voice/act` (web.py:2599–2724) saves an observation with `support_entries` empty unless the teacher fills the manual Observe-form fields. The 7 categories never fill up from natural narration.
3. **The lens UI doesn't render the category profile.** `renderStudents()` (index.html:1807–1922) shows roster cards; the per-category view teachers expect ("populated by teacher feedback directly") isn't on screen.

---

## Design

### 1. Profile background/edit endpoint

`PATCH /api/students/{student_id}` — accepts any subset of: `campus`, `grade_level`, `home_languages`, `learning_differences`, `rti_current_tier`, plus a new free-text `background_notes` field (add column, default `""`). New method `StudentLensStore.update_profile(student_id, fields)` — bumps `profile_version` + `updated_at`, refuses unknown fields. Every update writes a `privacy_log` event (`profile_updated`, no PII in the event — student_id only, matching existing event style in `privacy_log.py:21–57`).

### 2. Category auto-suggestion from observations (suggestion, never silent write)

Extend the existing suggestion endpoint `POST /api/observe/classify` (web.py:3213–3294) with a category proposal step:

- New function `suggest_support_categories(transcript) -> list[CategorySuggestion]` in `src/education/observation_capture.py`
- Mechanics mirror `voice_intent.py`'s signal approach: keyword/regex signal lists per category (e.g., "focus", "distracted", "finish/complete task" → `executive_functioning`; "friend", "group", "shared", "turn" → `social_skills`), each suggestion carries `category_id`, `confidence` (0–1), `matched_signals`
- **Obligatory-routing rule** (from the routing-loop research): a suggestion below threshold does NOT default into a category — it lands in `open_questions` with `confidence_level: model_suggested`. Low confidence gates the write; it never guesses.
- `/api/voice/act` observation branch calls the same function and includes suggestions in the response as `category_suggestions` — spoken confirmation stays unchanged (first-name-only rule at web.py:2665 untouched)
- Teacher confirmation (tapping a suggested category in the UI, or the Observe form's existing `teacher_confirmed` checkbox) flips `confidence_level` to `teacher_confirmed`. Only then does the entry count as evidence-grade (Spec 2 consumes this).

### 3. Strategies trialed — successful or not

The buckets exist (`strategies_worked` / `strategies_not_worked`). Add signal parsing so narrated outcomes land correctly: "tried X and it worked / helped / clicked" vs "tried X but / didn't help / still struggled" → `strategy_statement` + `strategy_outcome`. Extend `parse_observation_context()` (voice_intent.py:102–143) with a `parse_strategy_outcome()` sibling.

### 4. Lens UI: the Category Profile panel

In the student detail view (Students → student), render support_profile v2 as the school sees it:

- 7 category sections (hide `advanced_enrichment` behind a "More" toggle — it's not on their list), each showing needs / strengths / strategies (✓ worked, ✗ not) / evidence count / open questions
- Separate **Academic Strengths** and **Personal Strengths** blocks from `strengths_profile`
- Every entry shows its confidence badge (`teacher_confirmed` solid, `model_suggested` outlined "suggested — tap to confirm")
- A "Background" section rendering `background_notes` with inline edit → PATCH endpoint
- UI contract bump per ceremony (changelog comment, `--bump` from repo root, `EXPECTED_VERSION` in tests/test_ui_contract.py)

### 5. School-configurable category labels (Tier 2)

Display labels (not IDs) load from `~/.lingua-viva/config/school_profile.json` if present:
```json
{"category_labels": {"learning_and_cognition": "Learning and Cognition", ...},
 "hidden_categories": ["advanced_enrichment"]}
```
Loader in `src/lingua_viva/config.py` following `read_provider_config()`'s pattern (config.py:53–201). Category **IDs are immutable** — labels and visibility only. This is the manifest-is-the-contract principle: display evolves, schema doesn't.

---

## What NOT to Change

- `SUPPORT_CATEGORY_IDS` — do not rename, reorder, or remove IDs; existing DBs depend on them
- `append_observation()` aggregate recalculation — additive changes only
- The governance check in `capture()` (observation_capture.py:117–126) and the sanitizer audit — untouched
- `/api/voice/act` response contract for existing fields (Chip's packet + frontend voice wire depend on it) — `category_suggestions` is additive

## Test Plan

1. PATCH updates each field; unknown field → 400; `profile_version` bumps; privacy event written
2. `suggest_support_categories("Marco struggled to stay on task during group reading")` → `executive_functioning` ≥ threshold, `attendance_and_engagement` not suggested
3. Below-threshold transcript → lands in `open_questions`, never in a category bucket
4. Strategy outcome parsing: "tried sentence starters and it really helped" → `strategies_worked`; "tried peer pairing but he shut down" → `strategies_not_worked`
5. voice/act observation response includes `category_suggestions`; spoken confirmation unchanged (first-name-only assertion, mirroring tests/test_voice_intent.py privacy test)
6. Config: custom labels render; missing file → shipped defaults; IDs never read from config
7. Full suite + UI contract green

## Files

| File | Action |
|---|---|
| `src/education/student_lens.py` | MODIFY — `update_profile()`, `background_notes` column + migration |
| `src/education/observation_capture.py` | MODIFY — `suggest_support_categories()`, strategy-outcome wiring |
| `src/lingua_viva/voice_intent.py` | MODIFY — `parse_strategy_outcome()` |
| `src/web.py` | MODIFY — PATCH endpoint; extend observe/classify + voice/act responses |
| `src/lingua_viva/config.py` | MODIFY — `read_school_profile()` |
| `static/index.html` | MODIFY — Category Profile panel, background edit |
| `tests/test_school_categories.py` | CREATE |
| `contracts/ROUTE_REACHABILITY.yaml` | MODIFY — PATCH /api/students/{id} |

## Safety Rules

1. Model suggestions are never silently promoted to teacher-confirmed
2. Below-threshold classification → `open_questions`, never a guessed category
3. No student full names in privacy-log events, spoken output, or config files
4. All data stays in local SQLite; Drive sync of the enriched lens rides the existing `sync_lens_to_drive()` path untouched

## Definition of Done

- [ ] A teacher can add background info to an existing profile from the UI
- [ ] A narrated voice observation produces category suggestions the teacher can confirm with one tap
- [ ] Strategies trialed land in worked / not-worked with outcome
- [ ] Student lens screen shows the school's 7 categories + strengths exactly as the school's teachers listed them
- [ ] Labels configurable per school, IDs immutable
- [ ] Full suite green, UI contract bumped, route reachability updated
