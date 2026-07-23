# SPEC: Extract+Fill+Verify Engine (LV-DATA-IN-5)

**Date**: 2026-07-22
**Status**: APPROVED for design/build, WITH ONE GATE — see §4, do not skip it
**Author**: Claude (this session)
**Trigger**: Core "data in" capability — turns a teacher-confirmed file list
(Spec 2's output) into verified structured fields for a target schema
(`SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md`'s two schemas).
**Scope**: New module `src/lingua_viva/extraction_engine.py`, implements the
`extract()` stub in `src/lingua_viva/data_in_contracts.py`. New eval fixtures under
`tests/fixtures/data_in_eval/`.
**Risk level**: MEDIUM-HIGH for the student-lens path specifically — see §4.
LOW for the curriculum path (reuses an existing, already-approved document pipeline).
**Depends on**: `SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` (frozen contracts — import
`ExtractionResult`/`ExtractedField`/`SourceChunk`/the two field-name tuples from
`data_in_contracts.py`, do not redefine them). Its input is Spec 2's confirmed file
list — this spec does not scan directories itself.
**This is the one spec in the whole plan that needs an eval harness before it touches
a real file** — everything else in Tier 1/2 is deterministic wiring; this is the one
with a real chance of being wrong in a way that looks right.

---

## 1. What Already Exists — Reuse, Don't Rebuild

This spec's scope is **smaller than it first looked** — a second pass over the
backend (2026-07-22, same session) found that most of the pipeline this spec was
about to build already exists, just disconnected from the UI and, in one case,
broken by an unrelated import bug shared with the Ask feature. Read this section in
full before writing anything — the risk on this spec specifically is duplicating
real, working code.

`src/education/document_parser.py`'s `DocumentParser` is a genuinely good, already-
built chunker: PDF-only (pdfplumber), heading-based chunking, `ChunkRecord(chunk_id,
text, source_file, page_start, page_end, section, is_table, redactions,
needs_review)`, with a two-layer PII redaction pass reused from `src/lingua_viva/
privacy.py`. **Use this directly for PDF files in both extraction paths below** — do
not write a second PDF parser.

`src/lingua_viva/ingest.py::ingest_document(path, doc_type)` wraps `DocumentParser`
and persists chunks into `DocumentStore` (an embedding-indexed store, searchable via
`DocumentRetriever.retrieve(query, domain, k)`). `doc_type` is restricted to
`{"curriculum", "organizational"}` — `"student-records"` is a **documented, deliberate
refusal**: `document_parser.py`'s own module docstring says Layer 2's name-redaction
pattern requires a title prefix ("Dr. Smith") and does not catch bare given names
("Marco") — exactly the shape of real student-record text. This restriction exists
for a real reason. Read §4 before deciding how this spec relates to it.

**`src/education/content_differentiator.py::ContentDifferentiator.generate_from_documents()`
already does real-document content adaptation** — retrieves chunks via
`DocumentRetriever`, adapts them into 3-tier content (`_adapt_tier_from_source`),
falls back to template generation only if nothing is retrieved. **This spec does not
touch Prepare/Activity generation at all.** The actual remaining gap there is (a)
getting a teacher's real curriculum files through `ingest_document()` so the store
isn't empty (Spec 2 already produces the confirmed file list for this — the wiring
from Spec 2's output to an `ingest_document()` call is a small, separate follow-up,
not part of this spec), and (b) Plan/Prepare's route calling `generate_from_documents()`
instead of the template-only `generate()`. Neither needs a new extraction engine.

**`src/education/observation_capture.py::ObservationCapturePipeline`** is a complete,
well-designed classify → governance-check → sanitizer-audit → persist pipeline for
turning text into a lens observation. Its own docstring states an existing,
established build rule this spec must also follow: tags (`rti_tier`, `cefr_*`,
`sel_*`) are accepted as **explicit values, never inferred by an LLM** inside that
pipeline — "per the build rule against guessing CEFR/RTI classifications." This
spec's verification pass (§3) is not introducing new caution here; it's the reason
that rule can be honored at all when the source is a messy file instead of a
teacher's own typed/spoken words — this spec is what turns "unstructured file text"
into the "explicit value" `capture()` already expects to receive, never the reverse.

**Known blocker, shared with the Ask bug**: `observation_capture.py:39` does
`from ontology.engine import OntologyEngine, ClassificationResult` — the identical
missing-module failure as `src/pipeline.py:38` (see
`SPEC_LV_UI_WIRING_FIXES_2026-07-22.md` §1c). `ObservationCapturePipeline` is
therefore currently **unusable**, not just unused. Its own comments note
classification there is "advisory... not the PII gate" (the actual gate is
structural — anything entering `capture()` is treated as student data by
construction), so a minimal stub `OntologyEngine.classify()` (not the full semantic
engine — that's the 2-weeks-out work) may be enough to unblock it. **This spec does
NOT fix that import.** Spec 6 (student lens writer, not yet written) should call
`StudentLensStore.append_observation()` directly for now — it has no `ontology.engine`
dependency at all — and restoring the full `ObservationCapturePipeline` (governance
note + sanitizer audit logging) is a follow-up once `ontology.engine` has at least a
stub, tracked separately, not blocking this spec or Spec 6.

## 2. Two Extraction Paths — Different Shapes, Different Risk

### 2a. Curriculum Unit extraction (LOW risk — build this first)

**Scope check, given §1**: this is metadata extraction — "what units exist, and what
are they called/targeted at" (`CURRICULUM_UNIT_FIELDS`: grade, title, focus,
cefr_target, materials) — from a teacher's real curriculum files. It is NOT activity-
content generation (that's `ContentDifferentiator.generate_from_documents()`,
already built, out of scope here). The operator's own framing: "those unit documents
need to be stipulated, and then we need to use the local model to go through them and
create the units based on what we see... they will not be preloaded" — that's a real
gap `generate_from_documents()` doesn't cover, since it takes an already-known
`LessonInput`/unit as input rather than discovering what units exist at all.

Files here are curriculum/reference materials, already an **allowed** doc_type. Reuse
`ingest_document(path, doc_type="curriculum")`'s exact existing chunk+redact pipeline
— no new parsing/redaction logic needed. This spec adds, on top of those chunks:

1. An extraction pass: local model (via the existing `ReasoningEngine` — check
   `src/lingua_viva/reasoning.py` for the right call shape, do not invent a new model
   client), given the chunk text + `CURRICULUM_UNIT_FIELDS` + the `hint` (e.g. which
   grade this scan-confirmed folder was tagged for), proposes field values with a
   citation back to the specific chunk(s) that support each value.
2. A verification pass, run separately from extraction (§3 explains why these stay
   two passes internally even though they're one spec/one engine at the contract
   level): for each proposed `(field, value, cited_chunk_ids)`, check the cited
   chunks actually contain grounding for the value. Two checks, both must pass for
   `status="verified"`:
   - **Deterministic check** (cheap, catches blatant hallucination): does the cited
     chunk's text contain the claimed value or an obvious lexical variant (e.g. CEFR
     level "A2" appearing literally, a grade like "G3"/"Grade 3"/"terza")?
   - **LLM verification check** (catches subtler misreadings): a second, separately-
     prompted model call — NOT the same call that proposed the value — asked "does
     this specific chunk actually support this specific claimed value? yes/no/unsure."
     Treat "unsure" as `needs_confirmation`, not `verified`.
3. Anything failing either check → `status="unsupported"`, dropped from
   `verified_only()`, logged as an `unresolved_question` (e.g. "couldn't confirm a
   CEFR target for this unit — check `<file>` manually").

### 2b. Student Lens extraction (HIGHER risk — build second, after 2a's eval harness
is proven and you've re-read §4)

Input here is different in kind, not just degree: every file entering this path was
**already individually assigned to one specific, named student by a teacher**, via
Spec 2's manual assign-to-student action (never bulk, never auto-matched — Spec 2
explicitly refused to build automatic filename-to-student matching for this reason).

Given that:

1. Parse with `DocumentParser` directly (PDF) — **do not** call `ingest_document()`
   or touch `DocumentStore` for this path. Nothing from a student file should be
   persisted into an embedding index meant for later semantic search/retrieval — the
   only thing that should outlive this extraction call is the verified structured
   field VALUES written into that student's already-local-only `student_lenses.db`
   row. The raw chunk text is processed in memory and discarded.
2. For non-PDF files (plain `.txt`/`.md` — the realistic shape of "messy teacher
   notes"), add a minimal paragraph-window chunker in this spec's own module. Do
   **not** extend `DocumentParser` to non-PDF formats — its module docstring commits
   it to "PDF -> structured, PII-gated chunks" specifically; broadening its scope is
   a separate decision for a separate spec. `.docx` support is an explicit known gap
   — log `unresolved_questions` for any file type you can't parse, don't silently
   skip it.
3. Extraction + verification: same two-pass shape as §2a, targeting
   `STUDENT_LENS_FIELDS`. **`trauma_flag` is hard-coded to always resolve
   `needs_confirmation`, never `verified`, regardless of what the verification pass
   concludes** — this is stated in `data_in_contracts.py` already; do not let a
   confident-looking verification pass override it.

## 3. Why Extraction And Verification Are One Spec But Two Internal Passes

`SPEC_LV_DATA_IN_CONTRACTS_2026-07-22.md` §3 says extraction and verification must be
one engine, not two specs — that's still true at the contract level (`extract()` is
one function, `ExtractionResult` is one return value, no other spec touches the
intermediate state). Internally, though, the extraction call and the verification
call should be two separate model invocations, not one combined prompt — a model
grading its own answer in the same breath it gave the answer is a weak verifier.
Keep them as two clearly separated functions inside `extraction_engine.py` so the eval
harness (§5) can measure each stage's error rate independently, even though callers
outside this module only ever see the combined `extract()` result.

## 4. GATE — Read This Before Writing Any Student-Lens Extraction Code

This spec's §2b path deliberately does not route student files through
`ingest_document()`'s `BLOCKED_DOC_TYPES` refusal. The reasoning: that refusal exists
because bare-name redaction is unreliable for a **general-purpose, persist-and-index-
for-later-search** pipeline processing **unassigned, untyped documents**. This spec's
input is structurally different — every file is already bound to one specific,
teacher-named student before extraction ever runs, and nothing gets persisted or made
searchable beyond the verified field values written to that student's own local row.
The redaction gap `document_parser.py` documents (missing NER for bare given names)
is about *whose name is in the text*, which stops mattering once a human has already
told the system whose file this is.

That reasoning may be right. It has not been confirmed by the operator, and it
touches a documented, deliberate safety boundary protecting real children's data at a
school serving a vulnerable population. **Do not write or run any code that reads a
real (non-synthetic) student's file under this path until the operator has explicitly
read this section and confirmed the distinction above.** Building and testing against
the synthetic eval fixtures in §5 requires no such confirmation — that work can
proceed immediately. Only the "point this at Marco's real file" moment needs the
explicit go-ahead.

## 5. Eval Harness — Build And Run This Before Touching Any Real File

Matches the operator's stated methodology: build a small golden set with known ground
truth, run the engine, measure, iterate, repeat until it converges — same shape as
the MC eval loop, applied here for the first time on Lingua Viva.

1. `tests/fixtures/data_in_eval/curriculum/` — 3-5 synthetic short text files
   (invented Italian-curriculum-style content, NOT real school material) with a
   hand-written `expected.yaml` per file stating the exact `CURRICULUM_UNIT_FIELDS`
   values a correct extraction should produce.
2. `tests/fixtures/data_in_eval/student_lens/` — 3-5 synthetic "teacher notes" text
   files about invented students (never real names, never real schools) with a
   hand-written `expected.yaml` per file stating expected `STUDENT_LENS_FIELDS`
   values, INCLUDING at least one fixture where the correct answer is
   `needs_confirmation` (genuinely ambiguous grade/level) and one where a field
   should end up `unsupported` (the file doesn't actually say what a naive read might
   assume) — the harness must be able to tell "confidently correct" apart from
   "confidently wrong," which is the entire point of the verification pass.
3. `tests/test_extraction_engine_eval.py` — runs `extract()` against every fixture,
   compares `verified_only()` fields against `expected.yaml`, reports precision
   (of fields marked verified, how many matched truth) and recall (of truth fields,
   how many were found and correctly verified) plus a hard check: **zero fixtures
   should ever produce a `verified` field that contradicts `expected.yaml`** — a
   wrong-but-confident field is worse than a missed one, and the eval must fail loudly
   on that case specifically, not just report a lower recall number.
4. Do not consider this spec done until the eval harness passes on all fixtures. If a
   fixture consistently fails, that's real signal to tighten the extraction/
   verification prompts — iterate the recursive-loop way, not by weakening the
   fixture's expected answer to match whatever the engine currently produces.

## 6. What Does NOT Change

- `document_parser.py` / `ingest_document()` / `DocumentStore` — untouched. This spec
  imports `DocumentParser` directly for chunking; it does not modify the existing
  curriculum/organizational ingestion path in any way.
- The `BLOCKED_DOC_TYPES` refusal in `ingest.py` — untouched, still in force for that
  code path. This spec's student-lens path is a separate function, not a bypass flag
  on the existing one.
- Nothing writes to any store yet — Spec 6 (student lens writer) and Spec 7
  (curriculum unit writer) consume this engine's output; this spec only produces
  `ExtractionResult`, it does not call `create_lens`/`append_observation`/write
  anything to `curriculum_units`.
- `ContentDifferentiator` / `generate_from_documents()` — untouched, out of scope
  entirely (see §1).
- `ObservationCapturePipeline` / `ontology.engine` — untouched. This spec does not
  attempt the import fix; Spec 6 calls `append_observation()` directly instead of
  going through the currently-broken pipeline wrapper.

## 7. Build Order

1. Read `data_in_contracts.py` and `document_parser.py` fully (30 min)
2. §5 eval fixtures + harness scaffold (expected.yaml format, test runner shell) —
   before any real extraction logic exists, so you're building toward a measurable
   target from the start (45 min)
3. §2a curriculum extraction pass (extraction call) (45 min)
4. §2a verification pass (deterministic + LLM check) (45 min)
5. Run eval harness against curriculum fixtures, iterate until it passes cleanly (time
   varies — this is the real work, don't shortcut it)
6. **Stop. Re-read §4. Get operator confirmation before continuing to step 7.**
7. §2b student-lens extraction + verification (mirrors 3-4, plus the non-PDF chunker
   and the hard-coded `trauma_flag` rule)
8. Run eval harness against student-lens fixtures, iterate until it passes cleanly,
   including the "must not produce a confident wrong answer" hard check

## 8. Definition of Done

- [ ] `extract()` implemented for `target_schema_id="curriculum_unit"`, passing all
      curriculum eval fixtures
- [ ] Eval harness reports zero confidently-wrong `verified` fields across all
      fixtures (both schemas)
- [ ] Operator has explicitly confirmed §4's reasoning in writing (a chat message,
      commit note, or comment in this spec's status row in `dev/INDEX.md` — some
      durable record) before any §2b code ran against a real file
- [ ] `extract()` implemented for `target_schema_id="student_lens"`, passing all
      student-lens eval fixtures, including the ambiguous-grade and unsupported-field
      fixtures
- [ ] `trauma_flag` never appears as `status="verified"` in any test run, confirmed by
      an explicit test asserting this
- [ ] Nothing in the student-lens path calls `ingest_document()` or writes to
      `DocumentStore` — confirmed by grep
- [ ] `python3 -m pytest -q tests/` passes, including the new eval test file

## 9. Provenance

- `document_parser.py` and `ingest.py` read in full this session — the
  `BLOCKED_DOC_TYPES` restriction and its documented reasoning are load-bearing to
  this spec's design, not incidental.
- Operator's stated methodology: "get a set of evals that I can build to, then run a
  recursive loop until I get there" — same model as Mission Canvas's eval-driven
  hardening, applied here for the first time.
- Operator's own capability language: "extract data... verify against hallucination"
  — §2-3's two-pass-inside-one-engine design is the concrete shape of that.
