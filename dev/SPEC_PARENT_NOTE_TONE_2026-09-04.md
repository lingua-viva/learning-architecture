# SPEC — The parent note reads like a person wrote it: report-card codes become words, the voice lens is applied, nothing is invented

**Date:** 2026-09-04 · **Author:** PC-23 seat · **Operator:** Mical Neill
**Origin:** Claudia's audit 2026-08-29 FRICTION-16 (*"The tone is ok, not particularly warm."*), the same audit's BUG-6 (parent summary fabricates ungrounded recommendations), and the 2026-09-04 chain run in which the note said *"At school, your child shows strength in ATL: thinking, social, communication, self-management, research."* (`dev/NIGHT_SUMMARY_2026-09-03.md` §3, `dev/PATH_TO_UX_READINESS_2026-09-04.md` U10).
**Status:** spec. Companion prompt: `dev/PROMPT_SAFEGUARDING_P0_AND_PARENT_TONE_2026-09-04.md`.

---

## 0. WILL IMPROVE WHAT · HOW MUCH · HOW VERIFIED

| | |
|---|---|
| **WHAT** | The parent note (`src/education/parent_report.py`) is built deterministically from templates and, since 2026-09-04, from the lens's strengths. It is honest and it is cold: lens text arrives verbatim, so report-card shorthand ("ATL: thinking, social…", "grade descriptor: developing", "inquirers, communicators") reaches a parent as jargon, and the sentence frames are the same for every child. `lenses/VOICE-EDU-001_malaguzzi_inspired.md` exists and **no code reads it** (`grep -rn VOICE-EDU-001 src/` → 0). |
| **HOW MUCH** | Measured on the chain fixture (Abigail) and on Claudia's 08-29 note: **0 report-card codes** (`ATL:`, `grade descriptor:`, IB attribute lists, CEFR codes) in a rendered note; **every sentence still traceable** to an observation id or lens entry id (the 09-04 `source_entry_ids` / `source_observation_ids` contract, unchanged); note length within the current bounds; **no new sentence that is not backed by a lens field** (BUG-6 stays closed). Then one real note read by Claudia: warm / not warm, in her words. |
| **VERIFIED** | The code-free assertion is a test that is red on the current tree (the Abigail note contains `ATL:` today). Traceability tests from 09-04 must stay green unchanged. The warmth verdict is a person's, logged as PASS / FAIL / CANNOT-TELL in the walkthrough, never asserted by code. |

## 1. The tree today

- `generate_draft` (`parent_report.py:164-300`): intro sentence → CEFR trend sentence → SEL sentence → **lens strengths (09-04)** → home activity. Every sentence is a fixed frame with the child's name substituted. Strengths come from `support_profile…strengths`, `strategies_worked`, `strengths_profile.*` (family audience, report-grade only) and are inserted **verbatim** after `"At school, {name} shows strength in "`.
- What sits in those lens fields comes from the report-card extractor: `lens_extract.py:135-171` writes `"ATL: thinking, social"`, `"inquirers, communicators"` (IB learner profile attributes), and `"grade descriptor: developing"` into `learning_and_cognition.strengths` / `.evidence` — shorthand meant for the teacher's lens, never for a parent.
- The voice lens `lenses/VOICE-EDU-001_malaguzzi_inspired.md` is a prose guide (Malaguzzi: image-rich, relational, "the hundred languages"). It is documentation, not data. Nothing consumes it.
- `_check_trauma_safety` (`content_differentiator.py:123`) and the endpoint's `_strip_parent_output` + `check_publication_safety` gate every sentence. They must keep gating every sentence this spec adds.
- There is **no model call** in the note and this spec does not add one (offline-first; BUG-5/6 class). Warmth has to come from better deterministic phrasing and from what the lens actually holds.

## 2. The contract

1. **A phrase map, keyed to the extractor's own vocabulary, translates codes into words a parent knows.** One table, in `parent_report.py`, keyed to the constants the extractor uses so the two cannot drift (`lens_extract.IB_LEARNER_PROFILE`, `ATL_SKILLS`, `GRADE_SCALE`, `VALID_CEFR_LEVELS`). Examples — the wording is the builder's first draft and Claudia's to change:
   - `ATL: thinking, social` → *"the way they think things through and work alongside others"*
   - `inquirers, communicators` → *"asking good questions and sharing ideas clearly"*
   - `grade descriptor: developing` → not rendered as a strength at all (it is a level, not a strength; it goes to `growth_areas` phrasing or is omitted)
   - a CEFR code (`A2`) never appears in a parent note; the existing trend sentence already avoids it.
   An entry the map does not know is rendered as-is **and counted** in the draft's `unmapped_terms` so the gap is visible, never silently ugly.
2. **The voice lens becomes data the generator reads.** A small YAML sidecar `lenses/VOICE-EDU-001_malaguzzi_inspired.yaml` (the `.md` stays as the human guide) declares: an opening frame per template (`progress`, `concern`, `activity_ideas`), a closing frame, sentence connectors, and **forbidden registers** (deficit, clinical, ranking — reuse `TRAUMA_UNSAFE_LABELS` plus `tier`, `intervention`, `behind`, `struggles`). `generate_draft` reads it through the lens store like any lens; **absent file = today's frames, byte-identical** (the zero-lens law from MC applies here too). Only the school's configured voice lens is read; no per-teacher prompt text.
3. **Variety without invention.** Two or three frames per slot, chosen deterministically by `hash(student_id + reporting_period)` so the same child gets the same note twice and two children do not get identical notes. Never a model. Never a sentence without a lens field or observation behind it — `source_entry_ids` / `source_observation_ids` remain complete; a frame with no backing source is not emitted.
4. **Honesty stays visible.** `fields_used`, `fields_enriching_missing` (09-04) unchanged. A note built from one lens field still says so in `fields_enriching_missing`, and the body says *"We are still collecting…"* exactly as today when there is nothing to say.
5. **Italian.** The note body is English today and `language` is a routing field (module docstring). This spec does not translate. It does require every phrase-map entry and every frame to have an `it` slot **declared**, even if empty, so the parity discipline is in place before translation lands. Empty `it` renders English and counts in `unmapped_terms["it"]`.

## 3. Rungs

**R0** sandbox. **R1** baseline: render the Abigail chain note and a note from Claudia's 08-29 fixture shape; list every code-like token; count sentences per source; save the bytes. Commit `dev/BASELINE_PARENT_NOTE_TONE_2026-09-04.md`. **R2** build the map, the sidecar reader, the frames; iterate on the two fixtures until zero codes and identical traceability; the no-sidecar render is byte-identical to R1. **R3** sabotage: delete the sidecar → frames revert (test green, bytes identical); remove a map entry → `unmapped_terms` counts it and the code test goes red; add a frame without a source → the traceability test goes red; put "struggles with" in a frame → the register test goes red. **R4** Claudia reads one real note in her app and says warm / not warm. That verdict, not this spec, closes FRICTION-16.

## 4. Kill criteria

- **K1** any sentence in a note cannot be traced to a lens entry id or an observation id.
- **K2** a model call appears anywhere in the note path.
- **K3** a code (`ATL:`, `grade descriptor:`, a CEFR level, a raw IB attribute list) reaches a rendered note after the map is in place.
- **K4** the no-sidecar render differs by one byte from the R1 baseline.
- **K5** a phrase-map entry or frame is added without its `it` slot declared.
- **K6** `personal_context` or a `needs` bucket entry reaches a note (the 09-04 family-audience rule).

## 5. Fences

No push to `main`. `lenses/` in LV is not a release trigger, but the sidecar is a new file beside a teacher's lens — path-scoped add, named in the commit. No student data in fixtures beyond the repo's fictional ones. `check_ui_contract.py --bump` never from PC-23 (the note's print template is in `templates/`, not `static/index.html`, so this build should not touch the lock; if it must, stop and say so).

## 6. CANNOT-TELL

What Claudia means by warm, until she reads one. Whether the Malaguzzi register survives a deterministic frame at all — the voice guide is built on image and rhythm, and a template can carry only a little of that; if R4 says "still cold", the honest next step is a *teacher-authored* frame set per school, not a model.
