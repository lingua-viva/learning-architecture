# T4 — Lens Engine (Wave 2, after T0 — CRITICAL PATH)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Read first: `dev/CONTRACTS_V1_2026-08-04.md` (frozen),
`dev/SPEC_T3_EXTRACTION_2026-08-04.md` once available,
`dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: `src/lingua_viva/docpipe/lens.py` + its tests. Nothing else.

Why this matters: **Observe is not a blank-page tool.** The app creates lens
scaffolds from ingested documents FIRST; teachers then update them by voice (T5).
A mic pointed at an empty lens is not the product (build brief §4.3).

## Phase 1 — Spec prompt

Spec the lens engine. Output `dev/SPEC_T4_LENS_2026-08-04.md`, no code.
Two operations:

1. `lens.create_from_extraction(student_id, extraction)` — the app builds the
   lens scaffold ITSELF from ingested documents. Specify:
   - how extraction fields map to Christi's 10 categories (runbook §7; align with
     the existing `support_category` enum — read it before naming anything);
   - what happens when a category has no supporting evidence: it stays EMPTY —
     never invent;
   - how multiple source documents merge into one lens.

2. `lens.merge_observation(lens, observation)` — fold a teacher observation into
   an existing lens. Specify:
   - conflict policy when an observation contradicts document-derived content.
     Recommended: retain BOTH with provenance; the teacher resolves in the UI.
     Argue if you disagree.
   - `evidence[]` accumulation — merging never destroys prior evidence;
   - what makes a merge reversible.

Also specify the provenance rule: DOCUMENT-derived and OBSERVATION-derived content
must be distinguishable in the UI at all times, and teacher-authored evidence
outranks model-derived evidence.

Relationship to existing state: LV already has a student lens surface
(`/api/students/<id>/lens`, `StudentLensStore`). Specify how the vault lens.json
relates to it — the vault is the document-pipeline source of truth; state
explicitly how/when the existing lens store is populated from it (adapter, not a
fork — do NOT create two competing lens formats without a declared bridge).

## Phase 2 — Implementation prompt

Implement your spec. Requirements:

- Both operations implemented, writing through `vault.put_lens` only.
- No lens field ever populated without `evidence[]` — assert this in code.
- Merges are additive and reversible.
- Document- vs observation-derived provenance preserved on every field.
- The bridge to the existing `StudentLensStore` implemented per your spec, so the
  current UI renders vault-derived lenses without a second format war.
- Build against T0 fixtures until T2/T3 land, then switch to real data.

Tests: create a lens from a fixture extraction; merge three observations in
sequence; assert evidence accumulates, nothing is lost, and no ungrounded field
appears. Commit ONLY owned files by explicit path, message
`docpipe: lens engine (T4)`.
