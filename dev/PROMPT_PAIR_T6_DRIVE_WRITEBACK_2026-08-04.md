# T6 — Drive Write-Back (Wave 3, after T1)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Read first: `dev/CONTRACTS_V1_2026-08-04.md`, `dev/SPEC_T1_DRIVE_2026-08-04.md`,
`dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: `src/lingua_viva/docpipe/sync.py`, `drive.push_file` in
`src/lingua_viva/docpipe/drive.py` (coordinate the handoff with T1 — take the
file only after T1 commits), + tests. Nothing else.

The requirement (operator, brief §8.1): when a lens is saved locally it propagates
to Google Drive where other teachers can see it. A local save that never reaches
Drive is a failed save.

**Privacy note:** lens content is student PII going to the teacher's OWN Google
Drive — that is the intended shared-visibility channel, teacher-authorized via
their Drive auth. It never touches an LLM provider. Keep those two egress classes
visibly distinct in code and logs.

## Phase 1 — Spec prompt

Spec Drive write-back. Output `dev/SPEC_T6_SYNC_2026-08-04.md`, no code. Cover:

- **Rendering**: lenses go to Drive as something a teacher can actually read —
  a Google Doc or formatted export, not raw JSON. Specify the format and how
  evidence/provenance appear in it.
- **The sync queue**: every local lens write enqueues (T5 enqueues; you drain).
  Worker model, retry, backoff, and what the teacher sees when sync is behind.
- **Conflict handling**: two teachers edit the same student's lens. Propose a
  policy — last-write-wins is probably wrong for shared student records. Argue
  for what you choose (evidence[] is additive by design — lean on that).
- **Offline**: queue persists across restarts (`sync/queue.json` per contracts)
  and drains when connectivity returns. Nothing is lost.
- **Sync status in the UI**: synced / pending / failed, per lens — specify the
  minimal surface (you may expose a status API; the UI badge itself can be
  T9-or-later if index.html contention bites).

## Phase 2 — Implementation prompt

Implement your spec. Requirements:

- `drive.push_file` implemented (INGEST stays T1's untouched code).
- Persistent sync queue draining in the background; retry/backoff per spec.
- Human-readable lens rendering on the Drive side.
- Sync status queryable per lens.
- Offline-safe: kill the process mid-queue, restart, queue drains — test this.

Test: save a lens offline, restore connectivity, confirm it appears in Drive with
correct content and no duplicates. Commit ONLY owned files by explicit path,
message `docpipe: drive write-back + sync queue (T6)`.
