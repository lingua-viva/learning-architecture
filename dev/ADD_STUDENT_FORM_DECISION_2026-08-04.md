# Add Student Form — Two Open Product Decisions
**For:** operator ruling. Not guessed — grounded in `static/index.html:2169-2202`,
`src/web.py:4121-4139`, `curriculum/lingua_viva_matrix.yaml:19-33`.

**RESOLVED 2026-08-04 (per recommendation, no objection raised):**
- **Decision 1 shipped**: Grade field is now a dropdown (`static/index.html`,
  `#new-student-grade`) populated from `overview.grade_bands` (G1-G5), matching the
  Prepare-view pattern. Server-side defense-in-depth added in `src/web.py:create_student` —
  rejects any `grade_level` that doesn't normalize to a known grade band (400, with the valid
  set in the error message), so any other caller of `/api/students` gets the same protection.
  Verified end-to-end: `G3` → 200, `3` → 200 (normalizes), `3rd grade` → 400 (the exact
  silent-failure case this closes), empty → 200 (still optional). 268 tests passing across
  every file that exercises `/api/students` or grade_level. `test_ethos.py`'s `MYP5` fixture
  is unaffected — it calls `store.create_lens()` directly, bypassing the HTTP validation, which
  is correct: MYP grades are a real, intentionally-unmodeled case (see `LV-STU-007` note above),
  not a case this validation should block at the store layer.
- **Decision 2 not actioned**: no downstream consumer found that needs a structured last name;
  treated as closed, no code change.

## Decision 1 — Grade field format
**Current state:** `#new-student-grade` is a free-text input, placeholder "e.g. G3", zero
validation client or server side. Curriculum `grade_bands` (and the Prepare-view grade dropdown)
require the exact canonical string `G1`/`G2`/`G3`/`G4`/`G5`. A mismatched entry ("3rd grade",
"Grade 3", "3") creates a student who will silently never match a grade-band — differentiation
and materials generation just find nothing, no error surfaced.

**Options:**
1. **Dropdown, canonical values only** (`G1`-`G5`, whatever the school's actual band range is).
   Zero silent-mismatch risk. Loses free text for any grade outside the modeled bands (e.g. a
   G6 MYP transition student — see `LV-STU-007`).
2. **Free text + server-side normalize/validate** (accept "3", "Grade 3", "grade3" → coerce to
   `G3`; reject anything that doesn't resolve). Keeps typing speed, closes the silent-mismatch
   gap, small amount of new normalization code + tests.
3. **Leave free text, add a visible warning** when the value doesn't match a known grade band
   ("This grade isn't in the curriculum — differentiation may not find matching materials").
   Cheapest, but still lets it happen if the teacher ignores the warning.

**Recommendation if asked:** Option 1 for grades that exist in `grade_bands` today (G1-G5), since
that's a closed, small, known set for this school — lowest risk, matches the Prepare view's
existing dropdown pattern exactly.

## Decision 2 — Last name field
**Current state:** one `display_name` free-text field. No `last_name` column exists anywhere in
the schema. Two call sites (`web.py:3350`, `slack_ops_bot.py:1596`) do
`display_name.split()[0]` to get a first name for greetings — breaks only if a teacher enters a
single-word name.

**Options:**
1. **Do nothing.** No known consumer actually needs a structured last name today — no roster CSV
   import splits first/last, no parent-report template addresses "Dear Mr./Ms. [Last]." If that's
   true, this isn't a real gap, just an assumption that was never verified. **This is the cheapest
   option and may be the right one — worth 2 minutes confirming there's no parent-report or
   report-card template downstream that expects a surname before ruling this closed.**
2. **Add a last-name field**, concatenate to `display_name` on save (or store separately and
   render as needed). Only worth doing if something downstream actually needs the split — no
   such consumer was found in this pass.

**Recommendation if asked:** rule Decision 1 now (it has a real, demonstrated silent-failure
path); treat Decision 2 as "no action unless you know of a specific downstream need I didn't
find" rather than a real open gap.
