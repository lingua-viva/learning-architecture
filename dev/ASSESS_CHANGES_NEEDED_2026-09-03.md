# ASSESS (U5 oral · U6 written) — changes needed, logged

**Date:** 2026-09-03 (night) · **Seat:** PC-23 · **Operator:** Mical Neill
**Sources:** `dev/PLAN_SIR_SPLIT_AND_ONE_LOGIC_2026-09-03.md` §3 and §7 (C1–C3, C5, C7), `dev/UX_MATRIX_AND_ACTION_LIST_2026-09-03.md` items 9–12 and §5, the lens field contract (`src/lingua_viva/lens_field_contract.py`), and the reachability census (`dev/DIAGNOSTIC_UX_CENSUS_2026-09-03.md` §3).
**Status:** nothing built. This is the change log the build will be checked against. Every line is either read from the tree tonight or is an operator/customer ruling with its source named.

---

## 0. What exists today, measured

| | |
|---|---|
| `src/education/assessment_generator.py` | 217 lines, **MYP criterion-referenced assessment generator** (four criteria, levels 0–8). Reached from product via `pipeline_execute.py:49`. It is the *La Scuola* shape, not the Still I Rise diagnostic. |
| Whisper | **In the tree and reached:** `src/lingua_viva/voice_stt.py::WhisperLocalProvider` — local `faster-whisper` via PyAV, audio stays on the machine; `grep -rli whisper src/` → 7 files (voice_stt, voice_intent, web, cli, teacher_readiness, golden_workflows, defect_triage). (First draft of this row said "not in this tree" — wrong; corrected before commit, see §5.) |
| Observe mic surface | `voice_stt.py` (84 lines) + `/api/voice/*` routes exist and are reached; R3 says Assess oral reuses this surface. |
| Lens fields for a diagnostic | **none declared.** The contract has no path for fluency / syntax / grammar / vocabulary. |
| Grade | **no field, and by ruling there must be none** (C1). |

## 1. Rulings the build must honour (each with its source)

| # | ruling | source |
|---|---|---|
| A1 | **Assess produces a diagnostic, not a mark.** "automatically not graded … all of the problems to just kind of come out" — "Correct." | customer sync 2026-09-03, C1 |
| A2 | The oral output has a **named shape: fluency/flow · syntax · grammar · vocabulary**, each "is this the problem area / does this need support" | C2 |
| A3 | Oral input: **record in-app first**, file import later, on Observe's mic surface; gate refuses by name — too short, too quiet, **too long (3 minutes max)** | R3, C3 |
| A4 | Whisper, multilingual; Italian in scope and weaker than English → **Italian/English parity discipline from day one** (the safeguarding-detector lesson) | C5 |
| A5 | Per-dimension **indicators (e.g. literacy 8/10) MAY exist as calibration evidence with a source**; the moment an indicator can become a grade without a teacher touching it, the product has built the thing the customer declined | UX_MATRIX §5 |
| A6 | **The lens holds everything; the assessment document is a render from the lens**, not a second store | plan §3.3 (the non-grade half survives C1) |
| A7 | Written/photo input is the item most likely to miss; **schedule last**; low-OCR-confidence shows the teacher what it read before anything touches the lens | plan §3.2, C7 |
| A8 | Everything Assess writes goes through the lens field contract: resolved paths, named refusals, the accounting invariant, `source_kind` provenance | this build (Rungs 2–4) |

## 2. The contract changes — what Assess needs declared

Assess is a **producer** (spec §2.8.2c). It needs a declared place for every value it can produce. Proposed registry entries (not added tonight; K7-class — the shape of a child's record is the operator's):

```
assessment.oral.{dimension}.indicator     dimension ∈ {fluency, syntax, grammar, vocabulary}
    kind: assessment · origin: authored · status: declared_not_implemented (until built)
    value: {"needs_support": bool, "indicator": 0..10 | null, "note": str}
    requires_sources: True   (the recording id / transcript span)
    sensitivity: normal
    validator: needs_support is bool; indicator, if present, is 0..10; NO "grade" key accepted
assessment.oral.transcript_ref            the recording/transcript id, never the audio bytes
assessment.written.{dimension}.indicator  same shape; dimension set TBD by the operator (A7 last)
```

Storage question for the operator (K7): a new `students` column / blob (`assessment_profile`), or entries under `support_profile.categories.communication_and_language.evidence` with a structured `text`? The first is honest (a diagnostic is not a support entry); the second needs no migration (spec §2.5 says no schema migration *for the contract build*, which this is not). **Recommendation: a new `assessment_profile` blob, declared in `LENS_SHAPES`, derived-never-punched from an append-only `assessments` record** — the same law that keeps `cefr_snapshot` honest.

The OUT side: `requires("assessment_document")` declares the four dimensions as **essential** — a diagnostic document that is missing a dimension must say so, not render a confident sheet with a hole in it (spec §2.8.2).

## 3. The build, in the order the dependencies allow

| step | what | serves | depends on | size (plan's estimate) |
|---|---|---|---|---|
| S1 | Operator rulings: storage shape (§2), written-dimension set, indicator scale | — | — | a conversation |
| S2 | Registry entries + `LENS_SHAPES["assessment_profile"]` + `requires("assessment_document")`; `declared_not_implemented` until S5 | A8 | S1 | 0.5d |
| S3 | Oral capture on Observe's mic: record-in-app, duration/level gate refusing by name (< N s, silent, > 180 s) | A3 | — | 1d (item 9) |
| S4 | Transcription through the existing `WhisperLocalProvider` (voice_stt.py), Italian + English, with a parity test per language (same transcript shape both ways) | A4 | S3 | 0.5d |
| S5 | Diagnostic extractor: transcript → four dimensions (needs_support / indicator / note), each with a source span; writes through `write_student_lens(source_kind="assessment")` | A2, A5, A8 | S2, S4 | 2d (item 10) |
| S6 | Assessment document rendered FROM the lens via `read_for("assessment_document")`; refuses to render when a dimension is missing | A6 | S5 | 1d (item 12) |
| S7 | Written/photo: PDF text path first (already solved), OCR-with-confirmation for photos, dimension set per S1 | A7 | S2 | ?? (item 15, expected to slip) |

Model note: S5 runs on **qwen3:8b** (R2). Nemotron stays opt-in until Assess ships.

## 4. What must NOT happen (the kill list for this build)

- A `grade` field, key, or column anywhere. Not "hidden", not "optional".
- An indicator that reaches any teacher-facing summary without a source span behind it.
- A dimension that is silently absent from the rendered document.
- An Assess path that writes to the lens without going through `resolve()` — the census will show it (`trash-collector.py`), and the producer parity test will fail.
- Italian transcripts tested less than English ones.

## 5. CANNOT-TELL tonight, and one correction

- **Correction:** the first draft of §0 claimed Whisper was not in the tree. It is (`voice_stt.py`, `WhisperLocalProvider`). I wrote the claim before running the grep; the grep ran, the row was fixed. Recorded because that is exactly the "figure quoted instead of read" defect this whole night was about.
- Whether `faster-whisper` and PyAV are actually installed on a customer machine (the provider raises a named error if not) — not measured here.
- Whether the existing `/api/voice/stt` route is the one Assess should extend or a sibling is cleaner — not read.
- The written-dimension set (the customer named the four for *oral*).
