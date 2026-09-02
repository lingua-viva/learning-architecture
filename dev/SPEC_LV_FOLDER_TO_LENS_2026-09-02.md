# SPEC: Lingua Viva — Folder-to-Lens Pipeline Contract

**Date**: 2026-09-02
**Status**: ACTIVE — acceptance tested against v0.2.81 (fdbe0de + split refusal fix)
**Upstream**: `SPEC_ENTITY_LENS_DOCPIPE_RECIPE_2026-09-01.md` (cross-repo recipe)
**Demo**: Thu Sep 4

## What This Is

The folder-to-lens pipeline takes classroom documents (PDF report cards, CSV
rosters, DOCX teacher notes) and produces per-student lenses — structured,
grounded, human-confirmable profiles that drive everything downstream:
lesson differentiation, observation context, parent report drafting.

LV is the **reference implementation** for the cross-repo recipe. Trop AI and
Mission Canvas port from LV, not the other way. This spec freezes what "working"
means so the demo has a contract and the ports have a target.

## Pipeline Stages (5, each frozen-record → frozen-record)

| # | Stage | Code | Deterministic? |
|---|---|---|---|
| 1 | **Parse + normalize** — file → text + stable char offsets + spans | `docpipe/extract.py` | always |
| 2 | **Entity detection** — structural (CSV headers, 0.99) + text (bigram, 0.99) + optional model (0.7) | `docpipe/extract.py` | core yes; model optional |
| 3 | **Identity resolution** — 5-tier name match → verdict: exact/queue/new | `docpipe/identity.py` | always |
| 4 | **Section + classify** — `fold_text` split → deterministic extractors first → one batched LLM call for remainder | `docpipe/lens_extract.py` | section yes; ~46% classify deterministic |
| 5 | **Lens merge** — evidence-grounded fields, `_assert_grounded`, SHA256 dedup | `docpipe/lens.py` + `student_lens_writer.py` | always |

## Governance Invariants (7, non-negotiable)

These come from the recipe spec §3 and Claudia's QA:

1. **Model routes, never authors.** LLM output is a pointer into source text. Phrase must be exact words from the sentence — if not, replaced by the sentence itself.
2. **No data beats fake data.** Every degradation path returns less, never invented.
3. **Ambiguity is a question, not a guess.** Two matches → queue, never silent pick.
4. **Provenance is threaded end-to-end.** Claim → span_id → char offsets → source file.
5. **Import ≠ truth.** Everything lands `needs_confirmation`. Human flips to verified.
6. **Name comparison only via sanctioned comparators.** `normalize_name`, `fold_text`, `_levenshtein`. Raw `.lower()`/`==` is the closed failure class.
7. **Refuse to split rather than mis-split.** Multi-student, zero name positions → empty sections, not full-text duplication. (Fixed 2026-09-02, locking test: `test_section_split_no_positions_refuses_rather_than_duplicates`.)

## P0 Fixes — ALL CLOSED in v0.2.81

| P0 | Issue | Fix (fdbe0de) | Locking test |
|---|---|---|---|
| P0-1 | Silent truncation at sentence 41 | Paged 40×N batches, visible overflow | `test_batch_classify_provenance.py` |
| P0-2 | Lost chunk provenance in batched path | sentence→chunk mapping threaded | `test_batch_classify_provenance.py` |
| P0-3 | Batch failure → 0 results silently | Per-sentence `classify_failed`, guarded out of lens/dedup/synthesis | `test_batch_classify_provenance.py` |

## Split Refusal Fix — CLOSED 2026-09-02

| Issue | Fix | Locking test |
|---|---|---|
| Multi-student, no name positions → full text for every student (cross-contamination) | Return empty sections; caller surfaces "No content found" as unresolved question | `test_section_split_no_positions_refuses_rather_than_duplicates` in `test_lens_from_report_cards.py` |

## 10 Lens Profile Fields

1. `learning_and_cognition`
2. `communication_and_language`
3. `executive_functioning`
4. `social_skills`
5. `emotional_regulation`
6. `physical_sensory_needs`
7. `attendance_and_engagement`
8. `strategies_trialed`
9. `academic_strengths`
10. `personal_strengths`

## Acceptance Criteria

For the demo and for any port to claim "working":

1. **Multi-student document** → correct per-student section isolation, zero cross-contamination.
2. **Single-student document** → full text assigned to that student.
3. **Accented / reversed names** → `fold_text` finds positions correctly (Noëmi, Lucà Rossi, surname-first).
4. **No name positions found (multi-student)** → empty sections, not duplicated full text.
5. **>40 sentences** → paged batches, all sentences classified or visible warning, zero silent loss.
6. **Batch failure mid-run** → affected sentences get `classify_failed`, other batches unaffected.
7. **Every batched field** → non-empty `supporting_chunk_ids` resolving to real chunks.
8. **Every imported field** → `needs_confirmation` status, not auto-verified.
9. **Deterministic extractors run first** — CEFR, IB profile, ATL, attendance detected without model.
10. **LLM phrase extraction** → substring-verified against source sentence.
11. **Dedup** → SHA256 evidence key, no duplicate lens entries from repeated import.
12. **Preview before apply** → teacher sees proposed changes before lens write.

## Known Demo Steer-Arounds (not fixed, won't break the pipeline)

- **BUG-T1.1**: Accented first name dropped from CSV roster detection (6th surface — extract.py roster path). Steer: use pre-imported roster, don't live-import accented CSV.
- **BUG-T5.2**: Sibling ambiguity bypassed when student pre-selected in Observe UI. Steer: avoid two-sibling voice observations.
- **Parent summary fabrication**: Generic prose when not enough data. Steer: don't demo parent summary for data-poor student.

## Files (absolute paths)

| Component | Path |
|---|---|
| Parse + normalize | `src/lingua_viva/docpipe/extract.py` |
| Identity resolution | `src/lingua_viva/docpipe/identity.py` |
| Section split + classify | `src/lingua_viva/docpipe/lens_extract.py` |
| Lens merge + grounding | `src/lingua_viva/docpipe/lens.py` |
| Lens writer | `src/lingua_viva/student_lens_writer.py` |
| Batch classify tests | `tests/test_batch_classify_provenance.py` |
| Section split tests | `tests/test_lens_from_report_cards.py` |
| Name match tests | `tests/test_name_match_fold.py` |
| Golden doc tests | `tests/golden/test_golden_document_to_lens.py` |

## Test Commands

```bash
# Split + provenance + golden (the contract tests)
python3 -m pytest tests/test_lens_from_report_cards.py tests/test_name_match_fold.py \
  tests/test_batch_classify_provenance.py tests/golden/test_golden_document_to_lens.py -v

# Full suite (must stay green)
python3 -m pytest tests/ -q
```
