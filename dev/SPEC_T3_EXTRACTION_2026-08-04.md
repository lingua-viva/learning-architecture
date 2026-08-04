# SPEC T3 — Grounded Document Extraction + Job Runner (2026-08-04)

**Status: implemented same-day (2026-08-04, recovery session after the wave
convergence failure — see dev/POSTMORTEM_WAVE_CONVERGENCE_FAILURE_2026-08-04.md).**

Sources: `dev/PROMPT_PAIR_T3_EXTRACTION_2026-08-04.md`,
`dev/CONTRACTS_V1_2026-08-04.md` (frozen), T0 fixtures
(`tests/fixtures/docpipe/expected_extraction_*.json` — the target shape).
Owned files: `src/lingua_viva/docpipe/extract.py`, `jobs.py`,
`grounding_docs.py` + tests. (`grounding.py`'s lens-level verify stays T7's.)

## 0. Architecture: deterministic core, model enrichment, mechanical verify

Offline is a supported state (runbook) and Ollama is optional (installer copy),
so extraction CANNOT depend on a model to function. Two layers:

1. **Deterministic layer (always runs, offline-safe):** normalization → spans →
   title/type/sections/curriculum → student detection. This alone feeds T9→T4
   (lens creation consumes `students_detected` + spans; lens.py maps span text
   to profile fields). Wrong-output risk ≈ 0: everything is copied, never
   generated.
2. **Model enrichment layer (optional, `LocalModelClient` only):** span-cited
   student candidates the heuristic missed. Every model claim is mechanically
   verified against its cited span BEFORE inclusion; failures are **DROPPED,
   never demoted** (prompt rule), each drop logged in `warnings[]`. Model
   absent/erroring → deterministic result + `model_enrichment_unavailable`
   warning. `model.py`'s import-time assert already fails hard on an external
   default (hard rule 1).

## 1. Normalization (stable offsets)

- **text/markdown, text/plain, csv:** UTF-8 decode (`errors="replace"`),
  `\r\n`/`\r` → `\n`, tabs → single space, strip trailing spaces per line,
  collapse 3+ blank lines to one blank line, ensure trailing `\n\n` (fixture
  convention). All downstream offsets refer to THIS string — computed once,
  never re-derived.
- **pdf:** `pdfplumber` page text joined with blank lines, then the same text
  normalization. Import/parse failure → honest `ValueError` (job fails with a
  teacher-readable reason; nothing invented).
- **Other mimes (docx, images…):** `ValueError("unsupported format …")` —
  a clear failure beats an empty "success". (docx is a named fast-follow.)

## 2. Spans

Paragraph-level: split `normalized_text` on blank-line boundaries; each
non-empty block = one span `SPN-%04d` with `char_start`/`char_end` measured in
the canonical string and `text == normalized_text[start:end]` **by
construction** (slices, not re-assembly). Matches both T0 fixtures exactly.
Spans are the only citable units — chunking for the model (§4) sends whole
spans, so chunk boundaries can never split an offset.

## 3. Structure (deterministic)

- `title`: first `#`-heading (stripped) or first line if heading-like; else null.
- `document_type`: keyword heuristic in priority order — roster (roster/class
  list + ≥3 detected names), lesson_plan (learning goal/warm-up/unit/
  differentiation), student_work_sample (work sample/task:+student prose),
  rubric (criterion/band/descriptor), report (progress report/term), else
  unknown. Honest default: unknown, never a guess presented as certainty.
- `sections`: labeled-paragraph mapping (`Task:`, `Teacher note:`,
  meta lines, differentiation heading, lesson-flow rest) mirroring the fixture
  section vocabulary; generic fallback = one section per heading.
- `curriculum`: labeled fields when present (`Class:`, `Unit:`, `Task:`,
  grade tokens like MYP5/G3). Absent → omitted, never invented.
- `language`: tiny stopword-count heuristic (en/it), default en + warning.

## 4. Student detection

- Deterministic pass: capitalized First-Last bigrams (accent-tolerant, common
  sentence-start words excluded) → full-name candidates, confidence 0.99 when
  the full name appears verbatim (fixture convention); every span containing
  the full name OR the first name as a whole word joins `span_ids`.
  `student_id = "student-" + slug(display_name)` (fixture convention —
  T9/T4 merge on it deterministically across re-imports).
- Model enrichment (optional): prompt over spans returns STRICT JSON
  `{"students":[{"display_name","span_id"}]}` — never a bare value. Parse with
  the hardened pattern from the observe/classify route (fenced-JSON strip,
  first-object-only, discard-on-invalid, ONE retry with a "JSON only" nudge,
  then give up with a warning). Each candidate must pass §5 verification
  against its cited span or it is dropped. Verified model finds get
  confidence 0.7 (below the fixture's 0.99 verbatim tier, above T9's
  needs-confirmation threshold boundary — model-found students with exact
  span support auto-create; anything shakier already fails verification).

## 5. `grounding_docs.verify()` — the mechanical grounding gate

`verify_extraction(extraction) -> DocGroundingReport` runs on EVERY extraction
before `vault.put_extraction` (jobs.py enforces the ordering):
1. **Span integrity:** unique ids; `0 <= start < end <= len(normalized_text)`;
   `text == normalized_text[start:end]` byte-for-byte.
2. **Reference integrity:** every `span_id` cited by sections and
   students_detected exists.
3. **Support rule** for every students_detected entry: tokenize the
   display_name (accent-folded, lowercase, tokens >2 chars); EVERY name token
   must appear somewhere in the union of its cited spans, and EACH cited span
   must contain ≥1 name token. Rationale: exact-substring is too strict
   (spans cite "Nora" without the surname — fixture SPN-0003), semantic
   similarity requires a model (circular — the model would grade itself).
   Whole-token overlap is mechanical, deterministic, and explainable in one
   sentence to an auditor.
4. Violations → the offending entry is **DROPPED from the extraction** and the
   drop is recorded as `warnings: ["grounding_dropped:<what>:<reason>"]`.
   Never a lowered confidence — a claim that failed verification is not
   "less likely true", it is unsupported, and unsupported does not ship.

Model-claim verification (§4) reuses rule 3 verbatim: value tokens vs cited
span tokens, threshold = ALL name tokens for student claims.

## 6. Job runner — `jobs.py`

Persistent, restart-safe, UI never blocks:
- State: `<vault>/jobs/<job_id>.json` (atomic temp+replace, same pattern as
  sync.py) — `{job_id, source_id, status: queued|running|done|failed,
  progress: {stage, detail}, error, created_at, updated_at, attempts}`.
- `run_extraction_job(source_id, *, root=None, model_client=None) -> dict`:
  loads source + original bytes from the vault, stamps `running`, runs
  `extract_document`, runs `verify_extraction` (drops + warnings applied),
  `vault.put_extraction`, stamps `done` (or `failed` with the honest reason).
  Idempotent: re-running a done job re-extracts from the same bytes and
  overwrites the same extraction path (deterministic core → same output).
- `resume_pending(*, root=None)`: any job found `queued`/`running` on disk
  (i.e. the app died mid-job) is re-run — extraction is a pure function of
  vault bytes, so resume == rerun; a lens is never half-written because lens
  creation happens downstream of a `done` extraction only.
- `job_status(job_id)` / `list_jobs()` for the web layer. The existing
  in-memory T9 registry keeps serving the UI; wiring web.py's ingest onto
  jobs.py is a separate T9-owned commit in this session.
- Slow is fine: progress stages (`normalizing`, `detecting_students`,
  `model_enrichment`, `verifying`, `writing`) update the record as they run.

## 7. Tests (tests/test_docpipe_extract.py) — report grounding pass rate

1. **Fixture parity:** extracting `lesson_plan_marco_nora.md` /
   `student_work_nora_rossi` sources reproduces the frozen expected
   extractions (normalized_text, spans incl. exact offsets, title, type,
   sections, students_detected ids/names/span_ids). Grounding pass rate on
   both fixtures: must be 100%, reported in the commit message.
2. **THE hallucination test (the point of the workstream):** a mock
   ModelClient returns a student claim citing a span that does not contain
   the name → the claim is DROPPED, the extraction carries a
   `grounding_dropped:` warning, and students_detected contains only
   verified entries. Also: mock returns malformed JSON → one retry → give-up
   warning, deterministic result intact.
3. Span integrity property: every span slices back exactly; corrupted span
   (tampered offsets) → verify_extraction drops/fails it.
4. Offline: `model_client=None` → full deterministic extraction + warning.
5. Unsupported mime → honest ValueError; pdf path smoke (skip if pdfplumber
   missing).
6. Job runner: run → done + extraction in vault; kill-simulation (job file
   left `running`, fresh `resume_pending`) → re-run to done, single
   extraction file, no partial writes; failure path stamps honest error.
7. E2E with T9: upload via `/api/students/ingest` with the REAL extract
   (no mock) → students created with grounded lenses (this flips tonight's
   installed-app behavior from honest-failure to working).

---
**Status 2026-08-04:** implemented in this session; commit
`docpipe: grounded extraction + job runner (T3)`.
