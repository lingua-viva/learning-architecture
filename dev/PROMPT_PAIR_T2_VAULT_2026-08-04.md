# T2 — Vault Store (Wave 2, after T0 — CRITICAL PATH)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Read first: `dev/CONTRACTS_V1_2026-08-04.md` (frozen),
`dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: `src/lingua_viva/docpipe/vault.py` + its tests. Nothing else.
Other sessions are blocked on real vault reads — this track ships before T4 needs
it. Announce loudly when vault reads return real data.

## Phase 1 — Spec prompt

Spec the vault store — the single source of truth for local disk state. Output
`dev/SPEC_T2_VAULT_2026-08-04.md`, no code. Cover:

- Manifest design: what it indexes, how it stays consistent with the filesystem,
  how it rebuilds if deleted.
- Atomicity: every write is write-temp-then-rename. A crash mid-write must never
  leave a partial JSON file that fails schema validation.
- Concurrency: background extraction jobs and the UI both write. Specify the
  locking model — file-level locks are probably enough; argue for or against.
- Schema validation on every write (use the T0 schemas + validator). A write
  producing an invalid file fails loudly rather than persisting.
- First-run: `vault.init()` creates an EMPTY vault. No seed data, no demo content.
  All app tabs render empty until real files are ingested.
- Deletion and orphan handling: what happens to a lens whose source document was
  removed.
- Root resolution: `LV_STATE_HOME` → `~/.lingua-viva/vault/`. Never
  bundle-relative (the F6 lesson).

## Phase 2 — Implementation prompt

Implement your spec. Requirements:

- All `vault.*` interfaces from the contracts fully implemented.
- Atomic writes, schema validation on write, manifest kept consistent.
- `vault.init()` idempotent, empty.
- Manifest rebuild from filesystem scan.
- Tests covering: crash mid-write leaves prior state intact (kill between temp
  write and rename); invalid payload rejected; concurrent writes to different
  lenses succeed; concurrent writes to the same lens serialize.

Commit ONLY owned files by explicit path, message `docpipe: vault store (T2)`.
Then announce: "vault live — drop the fixtures" to T1/T3/T4.
