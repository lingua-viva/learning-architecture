# T2 Vault Store Spec
**Status:** FROZEN 2026-08-04 for implementation in `src/lingua_viva/docpipe/vault.py`.

## Purpose

The vault is the only writer of Lingua Viva document-pipeline disk state. Other modules may read through vault interfaces and may pass validated records to vault, but they do not create, update, or delete files directly under `${LV_STATE_HOME:-~/.lingua-viva}/vault/`.

## Root Resolution

Vault root is:

```text
${LV_STATE_HOME:-~/.lingua-viva}/vault/
```

Resolution order:

1. `LV_STATE_HOME`
2. `src.lingua_viva.config.lv_home()`
3. append `vault`

The vault is never resolved relative to the application bundle, current working directory, or repository root.

## First Run

`vault.init()` creates an empty vault:

```text
vault/
  manifest.json
  sources/
  extracted/
  lenses/
  sync/
    queue.json
```

There is no seed data, no demo content, and no placeholder student/source entries. `init()` is idempotent: calling it repeatedly must not rewrite valid existing content except to rebuild a missing manifest or missing empty sync queue.

## Manifest Design

`manifest.json` is an index, not the source of truth. It contains:

- `schema_version`
- stable `vault_id`
- `created_at`
- `updated_at`
- `sources`: records discovered under `sources/<source_id>/source.json`
- `extractions`: records discovered under `extracted/<source_id>.json`
- `lenses`: records discovered under `lenses/<student_id>/lens.json`
- `sync`: `queue_path` and `pending_count` from `sync/queue.json`

Consistency rule: after every successful vault write, rebuild and atomically replace `manifest.json` from the filesystem. If `manifest.json` is deleted or invalid, `manifest()` rebuilds it from the filesystem scan. The scan ignores incomplete temp files and invalid JSON payloads. Invalid canonical files fail loudly when read directly.

## Atomicity

Every JSON write is:

1. validate payload in memory against T0 schema;
2. write formatted JSON to a temp file in the destination directory;
3. `fsync` the temp file;
4. `os.replace(temp, destination)`;
5. best-effort `fsync` the parent directory;
6. rebuild manifest, also through temp-then-rename.

Every byte source write is:

1. write `original.<ext>.tmp-*` in the source directory;
2. `fsync`;
3. `os.replace`.

A crash between temp write and rename leaves the previous canonical file intact. Startup/rebuild ignores temp files.

## Concurrency

The vault uses an in-process re-entrant lock per root. File-level OS locks are deliberately deferred for day one:

- the desktop app is a single Python process for the P0 flows;
- background jobs and UI handlers share that process;
- per-root serialization is simpler and prevents manifest races;
- later multi-process sync workers can add advisory locks without changing public interfaces.

This is conservative: writes to different lenses serialize through the same root lock. That is acceptable for day one because writes are small and correctness matters more than parallel throughput.

## Schema Validation

Every canonical JSON write validates with the T0 validator before persistence:

- source -> `source.schema.json`
- extraction -> `extraction.schema.json`
- lens -> `lens.schema.json`
- manifest -> `manifest.schema.json`

Invalid payloads raise `ValueError` and do not touch the previous file. Reads also validate canonical files before returning records.

## Deletion and Orphans

T2 does not expose delete APIs. If a source file is manually removed:

- `manifest()` rebuild omits that source.
- Extractions with no source remain indexed because they may still be useful for audit, but downstream grounding must treat missing source provenance as an orphan.
- Lenses remain indexed even if their source documents are missing. Student evidence is never deleted merely because a source was removed.

Future delete/write-back work should add explicit tombstones rather than silent removal.

## Implemented Interfaces

The following T0 interfaces return real data:

- `init(root=None) -> ManifestRecord`
- `vault_root() -> Path`
- `put_source(source, content, root=None) -> SourceRecord`
- `get_source(source_id, root=None) -> SourceRecord`
- `put_extraction(extraction, root=None) -> ExtractionRecord`
- `get_extraction(source_id, root=None) -> ExtractionRecord`
- `put_lens(lens, root=None) -> LensRecord`
- `get_lens(student_id, root=None) -> LensRecord`
- `manifest(root=None) -> ManifestRecord`

Observation-file persistence remains owned by T5/T4 unless a later contract adds a vault API for it. The manifest scanner indexes observation IDs indirectly through lens metadata only.
