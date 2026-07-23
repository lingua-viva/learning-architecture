# Claude Execution Prompt: LV Extract+Fill+Verify Engine

Copy everything below into a fresh Claude Code session. Working directory:
`~/learning-architecture` (or wherever your local clone of
`lingua-viva/learning-architecture` lives).

This one is recommended for Claude specifically, not Codex/Kiro: it's judgment-heavy
(prompt design for extraction/verification, eval-harness iteration, a real
architecture decision gated behind operator sign-off) rather than a fully-decided
mechanical build. It benefits from being run interactively — pause and think out loud
with the operator at the gate in §4, rather than executing straight through.

---

```markdown
You're working in the Lingua Viva repo, building the one piece of the "data in"
pipeline that's genuinely new: turning raw, messy file content into verified
structured field values. Everything downstream of this (content generation,
observation persistence) already exists — do not rebuild it. Read the spec's §1
before anything else; a prior pass this session already found and reused several
existing modules, and duplicating them is the main risk on this spec specifically.

The product bar: given a teacher-confirmed file (from the file-map verification
step), propose values for a target schema's fields, each backed by a specific citable
chunk of source text, with a genuine chance of being marked "unsupported" if the text
doesn't actually say what a naive read might assume. A confident wrong answer is
worse than an admitted gap — build and prove that with the eval harness before
touching any real file.

The output is not a chat summary. The output is a working `extract()` implementation,
a passing eval harness with a hard check against confidently-wrong answers, and a
short report.

## Execution Contract

Work in this order:

1. Read the required files, in order. Do not skip `document_parser.py`,
   `content_differentiator.py`, or `observation_capture.py` — the spec's §1 exists
   because those were found mid-session and change this spec's real scope.
2. Read `dev/specs/SPEC_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md` in full. This is
   your spec.
3. Build the eval harness scaffold (§5) BEFORE any real extraction logic — you need a
   measurable target from the start, not something bolted on at the end.
4. Build §2a (curriculum unit metadata extraction), iterate against the eval harness
   until it passes cleanly on all curriculum fixtures.
5. **STOP at the gate in spec §4.** Re-read it. Do not write or run any §2b
   (student-lens) code against a real file — synthetic fixtures are fine — until the
   operator has explicitly confirmed the reasoning in that section. If this is a
   background/non-interactive run and you cannot get that confirmation live, STOP
   after step 4, report clearly that you're gated, and do not proceed to step 6.
6. (Only after explicit confirmation) Build §2b (student-lens field extraction),
   iterate against the eval harness until it passes cleanly, including the
   ambiguous-grade and unsupported-field fixtures.
7. Run the full verification checklist.
8. Update `dev/INDEX.md`.
9. Give the final response under 150 words.

## Required Reading (in order)

1. `CLAUDE.md` — repo architecture, privacy rules
2. `dev/INDEX.md` — current spec status (several sibling specs may be mid-flight in
   other windows — check their status before assuming anything about the app's
   current state)
3. `dev/specs/SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` — the frozen contracts you
   implement against. Import `ExtractionResult`/`ExtractedField`/`SourceChunk`/
   `STUDENT_LENS_FIELDS`/`CURRICULUM_UNIT_FIELDS` from
   `src/lingua_viva/data_in_contracts.py` — do not redefine these locally.
4. `dev/specs/SPEC_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md` — YOUR SPEC, full
   detail, including §1's "already exists, don't rebuild" list and §4's gate
5. `src/education/document_parser.py` — the chunker you reuse directly (read the full
   module docstring — the PII-redaction scope restriction it documents is why §4
   exists)
6. `src/lingua_viva/ingest.py` — `ingest_document()`, and specifically
   `BLOCKED_DOC_TYPES` — understand exactly what it refuses and why before deciding
   how your student-lens path differs from it
7. `src/education/content_differentiator.py` — `generate_from_documents()` (out of
   scope for you, but read it so you don't accidentally re-derive a worse version of
   it) and `assign_tier_for_student()` (shows the existing codebase pattern for
   consuming a `student_lens` dict — match this style)
8. `src/education/observation_capture.py` — `ObservationCapturePipeline.capture()`.
   Note the explicit build rule in its docstring: tags are explicit values, never
   LLM-inferred, inside that pipeline. Note also line 39's `ontology.engine` import —
   confirm for yourself this is broken (do not fix it, just confirm the failure mode,
   same as `SPEC_LV_UI_WIRING_FIXES_2026-07-22.md` already documented for the Ask bug)
9. `src/education/student_lens.py` — `Observation` dataclass and
   `StudentLensStore.append_observation()` — this is what Spec 6 (not you, a
   follow-up spec) will call directly with your verified output; you don't call it
   yourself in this spec, but your field names must match what it expects
10. `src/lingua_viva/reasoning.py` — `ReasoningEngine` — use this for your model
    calls, do not invent a new model-calling path

## What To Build

Full detail in the spec (§2a/§2b/§3/§5) — do not re-derive it here, read the spec.
Summary:

1. Eval harness first: `tests/fixtures/data_in_eval/{curriculum,student_lens}/` with
   synthetic files + `expected.yaml` per file, `tests/test_extraction_engine_eval.py`
   measuring precision/recall AND a hard zero-tolerance check for confidently-wrong
   `verified` fields.
2. `src/lingua_viva/extraction_engine.py`: `extract()` implementing the
   `data_in_contracts.py` stub. Two-pass internally (extraction call, then a
   SEPARATE verification call — not the same prompt grading itself) for both target
   schemas. Deterministic grounding check + LLM verification check, both must pass
   for `status="verified"`.
3. `trauma_flag` hard-coded to never resolve `verified`, regardless of verification
   pass output — write an explicit test asserting this.

## Hard Rules

- Do not modify `document_parser.py`, `ingest_document()`, `DocumentStore`,
  `ContentDifferentiator`, or `ObservationCapturePipeline` — this spec is additive
  only, reusing what exists via import, never editing it.
- Do not fix the `ontology.engine` import — out of scope, tracked separately.
- Student-lens path (§2b): never call `ingest_document()` or write to
  `DocumentStore` — parse in memory, discard raw chunks after extraction, only
  verified field values may persist anywhere (and this spec doesn't even do the
  persisting — that's Spec 6).
- **Do not write or run any student-lens extraction code against a real
  (non-synthetic) file before the operator explicitly confirms spec §4.** This is
  the one rule in this whole multi-spec plan that gates on a live human decision, not
  a technical check — do not talk yourself past it because the reasoning in §4
  "seems obviously right." It touches real children's data at a school serving a
  vulnerable population. Get the explicit confirmation.
- Do not commit — leave everything staged for operator.
- No real student data, institution names, or private school documents anywhere,
  including in eval fixtures — invented names/content only.

## Verification Before Closing

```bash
python3 -m pytest -q tests/
python3 -m pytest -q tests/test_extraction_engine_eval.py -v   # eval harness, explicitly
python3 -m py_compile src/lingua_viva/extraction_engine.py
```

The eval harness passing is the real bar here, not just `pytest` exiting 0 — report
its precision/recall numbers explicitly, and confirm zero confidently-wrong
`verified` fields across every fixture.

## Deliverables

1. `src/lingua_viva/extraction_engine.py`
2. Eval fixtures + `tests/test_extraction_engine_eval.py`
3. `dev/reports/REPORT_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md` — cover eval
   results for both schemas (or just curriculum, if gated at §4), any prompt-tuning
   iterations that mattered, and explicit confirmation status of the §4 gate
4. `dev/INDEX.md` updated

## Final Response

Under 150 words. Include only:
- eval harness results (precision/recall, confidently-wrong-answer count — must be 0)
- §4 gate status: confirmed-and-built, or stopped-and-waiting
- report path
- test result

Do not restate the whole task.
```
