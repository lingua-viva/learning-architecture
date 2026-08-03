# T9 — Ingest UI: Students-from-file, ONE tab end-to-end (Wave 3)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Prereqs: T1 (drive ingest), T2 (vault), T3 (extraction), T4 (lens engine) all
committed; HF1 released index.html; coordinate with T5/T8 on index.html regions.
Read first: `dev/CONTRACTS_V1_2026-08-04.md`, the T1–T4 specs,
`dev/LV_BUILD_BRIEF_2026-08-04.md` §3 + §11,
`dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: the Students region of `static/index.html`, one ingest endpoint (+ job
status endpoint) in `src/web.py`, + tests. Nothing else.

**Scope ruling (brief §11):** one tab, genuinely end-to-end, beats eight
half-wired tabs. This track wires **Students-from-file** only — it is the tab
Observe depends on (lens scaffolds must exist before teachers can update them by
voice). The other tabs' ingestion (Daily/Plan/Prepare/Assess/Parents) copies this
pattern LATER — do not build them tonight.

## Phase 1 — Spec prompt

Spec the Students ingest surface. Output `dev/SPEC_T9_INGEST_UI_2026-08-04.md`,
no code. Cover:

- **Entry point** in the Students view: "Import students from a file or Drive
  folder". Two paths: local file picker, and Drive folder (via T1). No manual
  field entry anywhere — the teacher points at a source; the pipeline does the
  rest.
- **The chain it triggers**: `drive.fetch_file`/local copy → `vault.put_source`
  → `extract.extract_document` (T3 background job) → student identification from
  the extraction (roster docs, class lists, background docs) →
  `lens.create_from_extraction` per student → students + lens scaffolds appear
  in the UI.
- **Student identification rules**: which extracted fields establish a student
  (name at minimum); ambiguity → surface for teacher confirmation, NEVER
  auto-create on a guess; duplicates (same name re-imported) merge into the
  existing lens per T4's merge rules, never fork.
- **Progress UX for long jobs**: extraction on a local model may take minutes.
  Job status visible in the Students view (queued / extracting / n students
  found / done / failed with reason), driven by T3's job runner events. UI never
  blocks; teacher can navigate away and come back.
- **Honest empty/failure states**: nothing extractable → say so plainly; never
  seed demo students. Partial success (3 of 5 students identified) → show what
  was found and what was skipped, with source-document names.
- **Provenance visible**: each created student/lens shows which document it came
  from (evidence[] surfaced minimally — full provenance UI is later).

## Phase 2 — Implementation prompt

Implement your spec. Acceptance (brief §9 A1–A4, A6):

- A teacher can select a Drive folder or local file and the app ingests it with
  zero manual field entry.
- Ingestion produces real student profiles + lens scaffolds rendered in-app;
  every populated field traces to source-document content (evidence[] enforced
  by T4 — verify with the docpipe validator on the resulting vault).
- No invented content: a student with no extractable evidence for a category
  shows that category empty.
- Processing runs as a background job with visible progress; UI never blocks.
- Fresh install: Students tab renders empty, import affordance visible.
- Existing tests green; add an endpoint test driving the full chain against the
  T0 fixture documents.

Commit ONLY owned files by explicit path, message
`students: file/drive ingest → extraction → lens scaffolds, one tab e2e (T9)`.
