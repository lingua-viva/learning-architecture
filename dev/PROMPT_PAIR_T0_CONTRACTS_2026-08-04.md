# T0 — Contract Freeze (BLOCKING, run first)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Read first: `dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md` (cross-cutting rules),
`dev/LV_BUILD_BRIEF_2026-08-04.md` §3–§4.
You own: `dev/CONTRACTS_V1_2026-08-04.md`, `src/lingua_viva/docpipe/**`,
`tests/fixtures/docpipe/**`. Touch nothing else.

---

## Phase 1 — Spec prompt

You are freezing the data contracts for Lingua Viva's document pipeline. Produce
ONE file: `dev/CONTRACTS_V1_2026-08-04.md`. Write no implementation code in this
phase. Six other parallel sessions will build against this file — precision over
prose.

Define exactly four things:

1. **VAULT LAYOUT** — canonical local directory structure. Starting point (revise
   only if you find a defect, and say why):

   ```
   ~/.lingua-viva/vault/            (root from LV_STATE_HOME, same as config.py)
     manifest.json                  index of everything
     sources/<source_id>/
       original.<ext>               byte-identical copy of the source
       source.json                  provenance: origin (drive|local), drive_file_id,
                                    path, sha256, imported_at, mime, owner
     extracted/<source_id>.json     normalized text + structure + span index
     lenses/<student_id>/
       lens.json
       observations/OBS-<ulid>.json
     sync/queue.json                pending Drive writes
   ```

2. **EXTRACTION SCHEMA** — `extracted/<source_id>.json`. MUST include a `spans`
   array where every span has `{span_id, char_start, char_end, text}` and the full
   normalized text is addressable by char offset. Downstream grounding depends on
   this.

3. **LENS SCHEMA** — `lens.json`:
   - Christi's 10 profile categories as first-class fields (exact list + ID mapping
     rule in the runbook §7 — reuse the existing `support_category` enum IDs where
     they overlap; check `src/lingua_viva/` for the current enum before naming).
   - Every populated field carries `evidence[]`:
     `{source_ref, span_id | obs_id, confidence, added_at, added_by}`.
   - `source_ref` distinguishes DOCUMENT-derived from OBSERVATION-derived.
   - **No field may be non-empty with an empty `evidence[]`.**
   - Observations are separate files, referenced by id, never inlined.

4. **MODULE INTERFACES** — exact Python signatures each workstream implements, in
   `src/lingua_viva/docpipe/`:
   `drive.list_folder / drive.fetch_file / drive.push_file` ·
   `vault.put_source / get_source / put_extraction / get_extraction / get_lens /
   put_lens / manifest` · `extract.extract_document` ·
   `lens.create_from_extraction / lens.merge_observation` · `grounding.verify`

State the HARD RULES at the top of the file:
- All model calls are LOCAL. No external LLM. One seam only: a `ModelClient`
  protocol where an external client can be swapped in later (operator is building
  safe second-model access in MC separately — this seam is the handoff point).
- No field is written without evidence. Ungrounded output is a bug.
- The vault module is the ONLY writer of disk state.
- Vault root comes from `LV_STATE_HOME`/`~/.lingua-viva` — never bundle-relative.

## Phase 2 — Implementation prompt

Implement the T0 scaffold from `dev/CONTRACTS_V1_2026-08-04.md`. Deliver:

1. **JSON Schema files** for extraction, lens, observation, source, manifest in
   `src/lingua_viva/docpipe/schemas/` (inside src so desktop packaging picks them
   up — do NOT create a top-level dir).
2. **Stub modules** for every §4 interface — correct signatures and return types,
   `NotImplementedError` bodies.
3. **`ModelClient` protocol** with one implementation: `LocalModelClient` wrapping
   the existing local reasoning path (reuse `src/lingua_viva/reasoning.py` /
   config.detect_model — do not spawn a second Ollama client). Assert at import
   time that no external endpoint is configured.
4. **Fixtures** in `tests/fixtures/docpipe/`: two realistic source documents (one
   lesson plan, one student work sample — synthetic names only: Marco Bianchi,
   Nora Rossi), their expected extraction JSON, one partially-populated
   schema-valid lens.json, one observation JSON. Other sessions build against
   these instead of waiting for Drive. Realistic, not toy.
5. **Validator CLI**: `python -m src.lingua_viva.docpipe.validate <path>` checks
   any vault file against its schema, exits nonzero on failure.

Do NOT implement Drive, extraction, or lens logic. Stubs only. Run the existing
test suite for regressions in what you touched. Commit ONLY your owned paths
(explicit paths, never `git add -A`), message
`docpipe: freeze contracts v1 (T0)`, then report: "schemas frozen" + any
deviations you made from the starting layout and why.
