# SPEC: Multi-Teacher Triangulation via Shared Drive Workspace

**Created**: 2026-08-01
**Status**: BUILT 2026-08-01 — shipped in desktop 0.2.26 (UI contract v94; tests/test_triangulation.py, 22 tests). Spec 2 evidence records left as TODO in build_ledger_ndjson per build prompt.
**Addendum — teacher identity provisioning (P1, BUILT 2026-08-02)**: the original build treated attribution as solved ("Observations already carry teacher_id"), but every machine authored rows as the `"local-teacher"` default, so two machines exported the SAME ledger filename (silent overwrite in Drive) and skipped each other's ledger on pull as "own" — multi-machine triangulation was inert. Fix (UI contract v97, uncommitted — operator commit window): `own_teacher_id` in Tier 2 `school_profile.json` (`"local-teacher"` reserved, never a real identity) + Settings → Teacher identity panel; `configured_teacher_id()` seam inside `effective_teacher_id()` off-mode covers every `or "local-teacher"` fallback in web.py; `POST /api/school-profile` backfills prior rows via `StudentLensStore.rename_local_teacher` (surgical: origin='local' only, imported fan-out entries untouched); drive_sync never exports and never imports a sentinel-authored ledger (stale 0.2.26 artifacts skip cleanly); un-provisioned nudge in the lens triangulation section. tests/test_teacher_identity.py (21 tests). **Deployment precondition for Monday's multi-machine setup: each machine sets a distinct teacher ID in Settings (or ledgers simply stay local — safe either way).**
**Priority**: 3 of 5 — depends on Spec 1; benefits from Spec 2
**Customer evidence** (school partner Slack channel):
> "Is it possible for more than one teacher to talk about the same student so that data is triangulated or as the data stays local this is not feasible?"

This is the best question a customer has asked — it names the apparent contradiction (local-first vs shared insight) and the answer defines the product's architecture story: **triangulation without a server**. Intervention groups where "the teacher may not know the student well" (the first meeting's framing) are precisely the case where a colleague's observations matter most.

---

## Problem

- Observations already carry `teacher_id` (student_lens.py:645–684) — attribution exists in the schema
- Drive sync is **one-way push**: `sync_lens_to_drive()` (drive_sync.py:132–178) exports a rendered Markdown lens to the school's configured folder. Nothing imports a colleague's data back
- Two teachers running LV on two machines have two disjoint SQLite databases for the same student, and no view shows "what do my colleagues see that I don't"

## Design Principle

**The school's own shared Drive folder is the sync medium. No LV server, no third party.** Data moves only between teacher machines and the school's Google Drive — infrastructure the school already trusts with this exact data class. The answer to the teachers is: *yes, feasible, and the data still never touches us.*

## Design

### 1. Observation ledger export (per teacher, per student)

Alongside the existing Markdown lens export, `sync_lens_to_drive()` additionally uploads a machine-readable ledger:

- Filename: `{student_id}.{teacher_id}.ledger.ndjson` — IDs, not names (Drive filenames are the most-leaked surface: breadcrumbs, notifications, search)
- Content: one JSON row per observation (`Observation.to_row()`) + evidence records (Spec 2) authored by this teacher for this student
- Deterministic and idempotent: full-state re-upload each sync (files are small at classroom scale); `observation_id`/`evidence_id` UUIDs make merge trivially idempotent

### 2. Ledger pull + merge

New `pull_shared_ledgers(student_id=None)` in drive_sync.py:

- Lists `*.ledger.ndjson` in the configured folder, skips this teacher's own files
- Imports rows into local SQLite with **provenance intact**: `teacher_id` preserved, new column `origin: "local" | "imported"` on observations + evidence
- Merge rule: **append-only union by UUID**. Existing UUID → skip. Never overwrite, never conflict — two teachers' observations are two facts, not a conflict to resolve (this dissolves the classic sync problem; there is no "last writer wins" because there are no writes to the same row)
- Imported rows enter aggregates (CEFR trajectory, RTI history, category rollups) tagged `imported_verified`-tier, per the existing confidence-level vocabulary (student_lens.py:85–90)
- Trigger: manual "Pull colleague updates" button + on the existing sync cadence, always fire-and-forget failure handling like `_record_pending_sync()` (drive_sync.py:181–198)

### 3. Triangulation view

In the student detail view:

- Per-category (Spec 1's panel): entries badged by author — "you" vs teacher display initials
- **Convergence signals** (deterministic, no LLM): same category populated by 2+ teachers → "corroborated" badge; CEFR direction disagreement within 30 days (one says progressing, one regressing) → "divergent — worth a conversation" flag; a category only one teacher ever touches → shown as single-source
- A "Colleagues" strip: which teachers contribute to this student, last-seen dates

This is triangulation as the school means it: agreement strengthens evidence, disagreement is surfaced as a prompt for human conversation — never auto-resolved.

### 4. Privacy posture

- Ledger contains what the Markdown lens export already contains — same data class, same destination, same teacher-controlled folder. No new exposure category
- Every pull/import writes privacy-log events (`ledger_pulled`, `observations_imported` with counts + ids, no names)
- Imported data is deletable as a unit ("remove colleague data" per student) — origin column makes this a single DELETE
- Exit-gate rules unchanged: nothing in this feature sends data anywhere except the already-configured Drive folder

## Open Question — RULED 2026-08-01

`teacher_id` display: ledgers expose colleague teacher_ids to each other. **Operator ruling: (b) full display names.** Teacher-configured display name lives in Tier 2 config (`school_profile.json`), shown in full in the triangulation UI. Names never appear in ledger filenames or any Drive artifact — filenames stay ID-only.

## What NOT to Change

- One-way push semantics of the Markdown lens export (human-readable artifact stays as-is)
- `sync_status` handling on local observations
- No Drive scope expansion — same folder, same OAuth client ("Lingua Viva", configured 2026-07-27)

## Test Plan

1. Ledger export: valid NDJSON, ID-only filename, contains only this teacher's rows
2. Merge idempotence: import same ledger twice → row counts unchanged
3. Provenance: imported rows keep original teacher_id, get `origin=imported`; aggregates include them at imported tier
4. Never-overwrite: local row with same UUID (self-ledger accidentally imported) → skipped
5. Convergence: corroborated badge at 2+ authors; divergence flag on opposing CEFR directions within window; single-source rendering
6. Remove-colleague-data deletes exactly `origin=imported` rows for that teacher/student
7. Privacy events on pull/import; offline pull → graceful pending, UI unaffected
8. All hermetic (`_isolate` + faked Drive client — reuse whatever test double `tests/` already uses for drive_sync)

## Files

| File | Action |
|---|---|
| `src/lingua_viva/drive_sync.py` | MODIFY — ledger export, `pull_shared_ledgers()` |
| `src/education/student_lens.py` | MODIFY — `origin` column + migration, `import_observation_rows()`, remove-imported |
| `src/web.py` | MODIFY — pull endpoint, triangulation data in lens response |
| `static/index.html` | MODIFY — author badges, convergence signals, pull button, colleagues strip |
| `tests/test_triangulation.py` | CREATE |
| `contracts/ROUTE_REACHABILITY.yaml` | MODIFY |

## Definition of Done

- [ ] Two teachers, one shared folder → each sees the other's observations on the same student, attributed
- [ ] Corroboration and divergence surfaced, never auto-resolved
- [ ] Import is idempotent, append-only, and reversible per colleague
- [ ] Zero new egress surfaces; privacy events complete
- [ ] Full suite green, UI contract bumped
- [ ] Answer posted back to the school in Slack: "yes — through your own shared folder, and the data still never leaves school control" (operator sends)
