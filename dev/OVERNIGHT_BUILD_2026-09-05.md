# Overnight build — durable teacher workspace

Operator ruling, this conversation: the installed application and its processing
logic may change; the teacher's data, saved work and the tasks performed with them
must remain on disk and accessible across updates. Files should have repository-like
preservation and revision history. This does not require Git or a remote repository.

Implementation interpretation: preserve originals and historical results; changes
create explicit revisions; cached projections may be rebuilt, but must not replace
the evidence or approved artifact from a previous processing run. Keep the existing
SQLite student store authoritative rather than creating a competing lens store.

Base: `443dd32`. Isolated branch: `build/overnight-durable-workspace-20260905`.
The operator's existing checkout, installed app and private workspace are not test
targets. Use isolated synthetic state for all automated checks.

First evidence: four persistence tests failed on the old implementation (same-second
overwrite, chunks lost on reload, no retained-original operation, no fsync/atomic
publication); two additional route tests failed before wiring. After the fix,
Windows targeted run: 43 passed / 1 failed. The failure is the existing vault
fixture SHA mismatch under CRLF; Linux verification follows. No protected UI file
changed in this slice.

Current slice (U3 / C8): same-filename imports in one second currently overwrite an
NDJSON log; the document-import path drops the uploaded bytes and persisted chunk
details. Lock those failures with tests, retain originals in the existing vault,
and preserve each processing run atomically. Legacy logs must still load.

Then return to the handoff's order: U3 corpus/chain, U1 startup, Assess shared
oral/document data model, remaining UXs. Teacher-witness and clean-Mac rows remain
pending until performed. Latest operator correction: Claudia's pagella redo has
not started, despite the older handoff's wording.

Checks required before any release: focused red/green tests, Linux replica, route
reachability, protected-file hash lock when applicable, release window, tag ancestry,
live download verification. Never convert an automated pass into a teacher witness.

Second reproduced defect: PDF/Word text was decoded for matching but their binary
bytes were then decoded as UTF-8 for lens extraction. Synthetic PDF and Word tests
failed before the fix; both now retain originals and extract the decoded evidence.
Broken documents and images no longer enter extraction as binary garbage. OCR is
still pending and these imports return an explicit retained-original error.
Windows focused verification: 35 passed.

Linux full suite at first commit `1302feb`: 3108 passed, 4 failed, 34 skipped,
32 xfailed. The failures match the documented baseline (three missing `pytest`
imports in grounding tests and one root-permission reconciliation test); this is
not a fully green run. Linux focused verification at `2c6f638`: all 35 tests
passed, matching Windows. These commits remain local; no release has been made.

Test isolation incident: three synthetic binary fixtures reached the local vault
because the new source helper ignored LV_STATE_HOME. Their exact files were
verified by name and digest, quarantined outside the vault, and its manifest
rebuilt with the one pre-existing source retained. No student lens rows changed.
The helper and import log now honor LV_STATE_HOME; a regression test checks that
LV_CONFIG_HOME remains untouched when a separate workspace is configured.
