# Real-Data Pipeline Audit — 2026-08-19

**Status: DIAGNOSTIC ONLY. Nothing here is fixed yet. This document is the ground-truth
state capture that the unified-fix agent builds on. Do not treat any listed behavior as
acceptable; do not treat any listed behavior as already handled.**

**Privacy: this document contains NO student names, NO individual student data. Test
inputs live locally at `~/Downloads/` (never committed). School name redacted per
publication-policy.md.**

## Scope

Two pipelines exercised against real IB school files on the dev machine (build under
test: desktop-v0.2.64, live):

1. **Lesson-content diversification** (Prepare → generate from coursework file)
   — tested with a real 2-page IB PYP "Learning experience" PDF
   (`~/Downloads/Lizard BrainWizard Brain - Instinct vs. Reason.pdf`, also on Drive).
2. **Student lens creation/editing** — tested with a real school file set
   (`~/Downloads/LV-lenses-test/`, 5 xlsx: class list drafts, two student-support
   sheets, 6-day-cycle calendar, kindergarten curriculum mapping). Goal scenario:
   create lenses ONLY for students in Claudia Canu's class, then enrich those lenses
   from the other files — while correctly IGNORING the files/rows that are irrelevant.

Environment note: `MC_AGENT=1` for every run; local ollama serving
`nemotron-3.5-lightning` (25 GB, thinking model — the hardware-aware auto-pick),
`qwen2.5:3b`, `qwen2.5:7b`, `qwen3:8b`, `gemma4:12b`, others.

---

## Pipeline 1 — Lesson content from a real coursework file

### What works (proven)

- **PDF extraction**: `docpipe.extract.extract_plain_text` pulled 2,385 clean chars
  from the real PDF (learning intentions, chameleon example, lizard/wizard brain
  description). Most of the doc fits the 1,500-char excerpt cap.
- **The pipeline itself is sound**: with `LV_REASON_MODEL=ollama/qwen2.5:3b`, full
  3-tier generation completed in **21.9s** and the output was genuinely grounded in
  the file — chameleon/predator sequence, stimulus→emotion→instinct chain, Italian
  journal work ("Il camaleonte si mimetizza"), tier-appropriate scaffolding.
  Diversification from real coursework is real when a suitable model answers.

### FINDING C1 (P0) — hardware-aware model auto-pick silently breaks generation

`config.detect_model()` prefers the hardware-recommended model when installed. On this
GPU that is `nemotron-3.5-lightning` (25 GB **thinking model**). Two compounding
failures:

- **C1a — thinking tokens eat the budget**: a single tier call returned in 35.3s with
  `error: <none>` and **empty visible content** — all 400 `max_tokens` consumed by
  reasoning tokens. LV's response parsing has no handling for thinking models
  (no reasoning-field strip, no empty-content-with-no-error failure signal).
- **C1b — 60s budget blown by serialization**: the three tier calls run in parallel
  via `asyncio.gather`, but ollama serializes them on one GPU. At ~35s each the
  overall `generate_lesson_materials` run hit exactly 60.1s (the
  `LV_REASON_TIMEOUT_SECONDS` default) on BOTH a cold and a warm model.

Net effect: empty/timed-out responses → `_has_placeholder_output` /
error branch → `_deterministic_material_fields` → **generic template text**.

### FINDING C2 (P0) — the fallback is silent to the teacher

`src/lingua_viva/lesson_materials.py` `_generate_tier_material` (~line 529): on
error, timeout, `model_used` starting with "none", or placeholder output, it swaps in
deterministic template fields with **no signal in the returned material, the API
response, or the UI** that the coursework file was ignored. The teacher sees
"Read the example about <topic>. Write three complete practice sentences." and has no
way to know AI generation never happened. Same silent-fallback failure class as the
YAML-alias→bundle-matrix trap fixed in the 08-19 build. `sync_status` exists for the
Drive leg; nothing equivalent exists for the generation leg.

### FINDING C3 (P1) — foundational-tier deterministic fallback is EMPTY

When the fallback fires, the foundational tier renders with **blank
`instructions_for_student`, blank `exercise_body`, `[]` scaffolding** — only a title
and teacher note. Reproduced twice. The weakest students' tier is the one that
degrades to nothing.

### FINDING C4 (P1) — metadata auto-detect picks letterhead over title

`parse_lesson_metadata` on the real PDF returned:

- `title`: "[School name] School code: 049755" — the letterhead line, not
  "Lizard Brain/Wizard Brain - Instinct vs. Reason" (line 3 of the doc). Since
  Prepare's `topic` pre-fill = `curriculum.task or meta.title`, the teacher's Topic
  field pre-fills with the school letterhead.
- `grade`: **not detected**, despite "Author: Grade 3 Verdi Teachers" in the text.
- `document_type`: "unknown".
- `unit`: "Diversity and emotions" — **correct** (the one hit).

### FINDING C5 (P2) — excerpt cap vs. real docs

`_SOURCE_EXCERPT_CHARS = 1500` (deliberate C8 budget choice). This 2-page doc is
2,385 chars, so the excerpt loses the last ~40% (differentiation section, assessment
notes). Longer real coursework will be mostly unseen. Not a bug — a documented
trade-off the unified fix should revisit alongside C1 (a faster model buys headroom).

### Verified-good context for the fix agent

- Containment (`read_todays_lesson_text` refuses paths outside the course library)
  works.
- Generate-from-nothing guard (audit P0-2) works.
- `.pdf/.docx/.xlsx/.csv/.md/.txt` are the allowed import extensions
  (`_LOCAL_IMPORT_EXTENSIONS`, lesson_materials.py:674).
- Repro commands: see session transcript 2026-08-19; single-call probe requires
  `system_prompt=` (engine only calls the model when a system prompt is present —
  `reasoning.py:160`; a probe without it returns `model_used="none"` instantly, which
  is itself worth knowing).

---

## Pipeline 2 — Student lens creation from a real school file set

### The target scenario (what the teacher actually needs)

Create lenses ONLY for the students in Claudia's class, then enrich those lenses from
the other files, ignoring everything irrelevant. **Ground truth IS in the files:**

- **Class list** (`2026-2027 Class List Drafts`): one sheet per grade; classes are
  COLUMN PAIRS ("Grade 3 Verdi" | "Grade 3 Arancioni"); **row 2 names the teachers**
  — Grade 3 sheet, col A: "Claudia Canu-Fautre & Stella Rubinacci" → her class is
  Grade 3 Verdi; her roster is the ~39 names below that cell. Full first+last names.
- **`3V ES Student Support`**: single sheet "3rd", proper column headers (Student /
  class / Classroom Accommodations / Internal support / External Support / Student
  Support Plan / Notes). **6 students**, names abbreviated ("First L-W" style), class
  column "V"/"A" — only 3 of the 6 are hers.
- **`ES Student Support (K-5) 2025-2026`**: one sheet per class (KV, KA, 1A…3V…);
  category COLUMNS (Accommodations / Internal support / External Support / Learning
  Plan / **Medical needs** / Notes-social-dynamics / End-of-year notes). Names are
  first-name or "First L" style. NOTE: last school year — her current students'
  history is on the "2V" sheet, not "3V".
- **Curriculum mapping** (`Italiano_Kindergarten_Mappatura…`) and **6-day-cycle
  calendar**: contain ZERO students. Must be ignored.

### What the pipeline actually did (all runs on the real files, real code path)

| File | Real students | `students_detected` (deterministic) | Notes |
|---|---|---|---|
| Class list drafts | ~400 across school | **637 @ 0.99 flat** | includes class names ("Kindergarten Verdi") and TEACHERS as students |
| 3V ES Student Support | **6** (3 hers) | **0** | the single most relevant file produces nothing |
| ES Support K-5 | ~76 rows | 76 @ 0.99 | includes "Include Specialist" (a role) |
| Curriculum mapping | **0** | **144 @ 0.99** | Italian story/song titles as students ("Il Gruffalò", "La Befana") |
| 6-day-cycle calendar | **0** | **86 @ 0.99** | calendar events as students ("Buddy Readers", "Events Assemblea") |

### FINDING L1 (P0) — name detection is a capitalized-bigram heuristic with flat 0.99 confidence

`_detect_students` (`docpipe/extract.py:649`): any "Capitalized Capitalized" pair
(`_NAME_BIGRAM`, line 646) not in a **hardcoded English-only blocklist** becomes a
student at `VERBATIM_STUDENT_CONFIDENCE = 0.99` (line 40). Italian titles pass the
English blocklist wholesale — a curriculum doc with zero students yields 144
"students". Confidence is a constant, so `INGEST_CONFIDENCE_THRESHOLD = 0.7`
(web.py:2377) can never discriminate — the gate exists but is dead.

### FINDING L2 (P0) — bulk auto-create turns L1 into mass garbage-lens creation + Drive sync

`BULK_IMPORT_CONFIRMATION_THRESHOLD = 2` (web.py:2378): any import detecting >2
students auto-creates EVERY one (`_run_ingest_job`, web.py:2537-2550) and enqueues a
per-student Drive lens sync (web.py:2575-2585). Uploading the curriculum xlsx would
create **144 fake student lenses and sync them to Drive**. "Undo this import" exists
but is after-the-fact; there is no preview/dry-run.

### FINDING L3 (P0) — the most relevant file yields ZERO students; failure chain fully traced

`3V ES Student Support` (Claudia's class, categoried support data, 6 students):

1. Structured support parse (`_xlsx_support_extract`) requires **≥2 sheets whose
   TITLES map to lens fields** (`_SUPPORT_SHEET_MATCH_THRESHOLD = 2`, sheet-title map
   `_SHEET_FIELD_MAP` at extract.py:79). Real school files name sheets by CLASS
   ("3rd", "KV", "3V") and put categories in COLUMNS → 0 sheets match → structured
   path rejected. **Column-header→field mapping does not exist.**
2. Generic fallback flattens the whole workbook into **ONE span** (verified: span
   count = 1) — per-row grounding impossible.
3. `_NAME_BIGRAM` requires two full capitalized words; real support names are
   abbreviated ("West L-W", "Miles B") → 0 matches.
4. Model-enrichment rescue (tested with a working qwen2.5:3b): found **1 student**,
   as the partial/wrong name "West" @ 0.7. Not a rescue.

### FINDING L4 (P0 for the scenario) — no concept of class membership or "my class" exists

Extraction flattens all structure: detected students carry `student_id` /
`display_name` / `confidence` / `span_ids` — **no class, no grade, no teacher
attribution**, even though the class list encodes it (grade sheets, class columns,
teacher-name row) and the 3V file has a literal `class` column ("V"/"A"). There is no
ingest option to scope an import to a class/sheet/column. The 08-19 build's
`teacher_roster` table exists downstream but ingest never populates class membership
from file structure. Teachers themselves are ingested as students (the teacher row is
just another name bigram).

### FINDING L5 (P1) — category-routing machinery exists but cannot reach real files

The "right category" concept IS built: 10 `PROFILE_FIELDS` (docpipe/lens.py:14 —
learning_and_cognition, communication_and_language, executive_functioning,
social_skills, emotional_regulation, physical_sensory_needs,
attendance_and_engagement, strategies_trialed, academic_strengths,
personal_strengths), `field_hint` span routing, `FIELD_KEYWORDS` fallback. But the
only structured entry point is sheet-TITLE matching (L3.1), so on real files all
routing falls back to keyword sniffing over a single flattened span. Also: the K-5
file has a **"Medical needs (allergies …)" column and PROFILE_FIELDS has no
medical/health category** (physical_sensory_needs is the nearest neighbor) — medical
data has nowhere correct to land.

### FINDING L6 (P0) — model gate vs. model pick disagree on tag normalization; enrichment NEVER runs; warning misreports it

On this machine, ingest model enrichment is dead in a way invisible to the teacher:

- `LocalModelClient.complete` hard-codes `model=config.detect_model()` and
  `local_only=True` (docpipe/model.py:59-66). `LV_REASON_MODEL` cannot override it
  (the explicit `model=` param wins in `reason()`'s resolution chain).
- `detect_model()` picks `ollama/nemotron-3.5-lightning` (hardware pick, no tag).
- `is_provably_local_model` (model_gate.py:93) checks the name against the installed
  ollama set — which contains `nemotron-3.5-lightning:latest`. **model_gate does NOT
  normalize the `:latest` tag; config's installed-match does.** Two normalizers
  disagree → gate returns False for the very model the picker chose.
- `local_only=True` + no provably-local fallback → engine returns the
  "I need a local AI model…" refusal message with `model_used="none:local_only"`.
- The refusal prose then fails JSON parsing and the extraction warning says
  `model_enrichment_discarded:invalid JSON after retry` — **misreporting a privacy
  refusal as a model formatting problem**. Measured: 0.3s, no model call ever made.
- Even if the gate passed, C1a applies: nemotron returns empty visible content.

### FINDING L7 (P1) — model enrichment is additive-only; false positives are unfixable by design

`_model_enrich_students` (extract.py:692) can only ADD students the deterministic
pass missed (`if student_id in known_ids: continue`). It can never veto the 637/144/86
deterministic false positives. A perfect model still ships every fake student.

### FINDING L8 (P1) — no cross-file identity resolution

The same child appears as "First Last" (class list), "First L-W" (3V support),
first-name-only (K-5 sheets). `student_id = f"student-{slug(display_name)}"` — the
identity IS the spelling. Enriching lenses from the support files would create
duplicate/parallel students, not enrich existing ones. (Temporal dimension too: the
K-5 file is 2025-26 — current 3V students' history lives on the "2V" sheet.)

### FINDING L9 (P2) — generic xlsx normalization destroys row structure

The non-support xlsx path flattens a workbook into one span (3V file → 1 span for 6
student rows × 7 columns). Grounding checks, span citations, and field hints all
assume meaningful spans; on real spreadsheets there is only one giant one.

### FINDING L10 (P2) — "local model detector" can return a cloud model

`detect_model()`'s last resort is `ollama/{CLOUD_FALLBACK}` =
`ollama/kimi-k2.7-code:cloud` (config.py:29,468) — an ollama-CLOUD model returned by
the local-model detector when no preference-list model is installed. The student-data
gate correctly blocks `:cloud` (verified: `is_provably_local_model("ollama/kimi-k2.6:cloud")
→ False`), but lesson-content generation runs with `local_only=False` and would
silently use cloud on such a machine. Also `LOCAL_MODEL_PREFERENCE[0]` is
`nemotron-3.5-lightning` with a speed comment — nothing anywhere accounts for it
being a thinking model (see C1a).

### Verified-good (so the fix agent doesn't re-litigate)

- Privacy gate blocks `:cloud` models for student data (L10, first half).
- Mechanical grounding rule (every name token must appear in the cited span) works
  and did drop some false names (`grounding_dropped:*` warnings).
- Folder-vs-file Drive link routing at ingest is correct; class-folder path
  (`class_folder_ingest.py`) has conservative filename-match attribution + an
  unattributed-review queue (`/api/students/ingest/unattributed`, `/attribute`).
- Vault write-before-process (file safely stored even when extraction fails); honest
  failure copy on NotImplementedError/no-text.
- Undo-import (archive-all) exists.
- Drive-link ingest leg untestable until operator sets `LV_GOOGLE_OAUTH_CLIENT_ID/
  SECRET` (open dependency from the 08-19 ship).

---

## Scenario verdict — current state

**The target workflow is not achievable on today's build.** Importing all 5 files
as-is would create roughly **940+ student lenses, most fake, all synced toward
Drive** — while the 6 students with actual support data (and the ~39 real names of
Claudia's roster with class attribution available in the file) yield zero correctly
attributed, zero enriched lenses. Both pipelines fail through the SAME classes of
defect:

| Failure class | Content pipeline | Lens pipeline |
|---|---|---|
| Silent degradation, no teacher signal | C2 (template fallback) | L6 (enrichment refusal misreported) |
| Model auto-pick unfit / ungoverned | C1 (thinking model, timeout) | L6 (gate/picker disagree), L10 |
| Confidence that measures nothing | — | L1 (flat 0.99), gate dead |
| Real-world format vs. idealized format | C4 (letterhead as title) | L3/L5 (class-named sheets, column categories, abbreviated names) |
| Structure flattened at extraction | C5 (excerpt cap) | L4/L9 (class membership + rows lost) |
| No identity model | — | L8 |

The unified solution should treat these as six failure classes, not sixteen bugs.

*Diagnostics executed 2026-08-19 on the dev machine, `MC_AGENT=1`, read-only —
no lenses were created, no student store writes, no Drive calls. Repro code inline in
the session transcript (`a7005cb6`).*
