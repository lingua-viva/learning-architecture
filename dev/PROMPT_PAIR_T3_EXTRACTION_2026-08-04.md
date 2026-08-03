# T3 — Grounded Extraction (Wave 2, after T0 — the "100% grounded" make-or-break)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Read first: `dev/CONTRACTS_V1_2026-08-04.md` (frozen),
`dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: `src/lingua_viva/docpipe/extract.py`, `jobs.py`, `grounding_docs.py`
+ tests. Nothing else.

This track decides whether "100% grounded in real data" is a mechanical property
or a hope. The mechanism is **span anchoring**: the model must cite character
offsets, and the code verifies the citation mechanically rather than trusting it.

## Phase 1 — Spec prompt

Spec grounded document extraction. Output `dev/SPEC_T3_EXTRACTION_2026-08-04.md`,
no code. Cover:

- Normalization: how PDF/DOCX/text become one canonical text string with STABLE
  character offsets. Offsets anchor everything downstream.
- Chunking for a local model with a small context window. Chunk boundaries must
  not break the offset mapping.
- The extraction prompt contract: the model returns `{field, value, span_id}` —
  never a bare value. Specify the exact JSON the model must emit and the retry
  policy when it emits something else (LV already has hardened JSON-parse
  patterns in the observe/classify route — reuse the lessons: first-object-only,
  fenced-JSON stripping, discard-on-invalid).
- `grounding.verify()`: given an extraction and the source text, confirm every
  value is supported by its cited span. Define "supported" concretely — exact
  substring is too strict, semantic similarity is too loose. Propose a rule
  (e.g., normalized token-overlap threshold against the span) and defend it.
- Rejection path: a field that fails verification is **DROPPED, not lowered in
  confidence**. Say so explicitly.
- Long-running jobs: extraction may take minutes on a local model. Specify the
  job model — queued, resumable, progress-reportable, survives app restart.
  Slow is acceptable; blocking the UI is not.

## Phase 2 — Implementation prompt

Implement your spec. Requirements:

- `extract.extract_document(source_id) -> extraction JSON`, schema-valid.
- `grounding.verify()` implemented and called on EVERY extraction before write.
- Fields failing verification are dropped and logged with the reason.
- Background job runner: queued, resumable, progress events, survives restart.
- `LocalModelClient` only (T0's protocol). Fail hard if an external endpoint is
  configured.
- Tests: build a fixture where the model is forced to hallucinate a field
  (mock a ModelClient that returns a value with a span that doesn't support it)
  and assert the field is DROPPED. **This test is the point of the workstream.**

Build against T0 fixtures until T2 announces real vault reads. Commit ONLY owned
files by explicit path, message `docpipe: grounded extraction + job runner (T3)`.
Report the grounding pass rate on the T0 fixtures.
