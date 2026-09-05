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

## Operator's subsequent scope ruling

Working journeys only: question/input through a usable saved deliverable. Slack
is out; Daily and Home removed from both schools' navigation; Plan stays hidden
until its interactive research/material workflow works. Preserve all prior work.

## Built and measured in the isolated branch (not yet released)

- Approved parent notes are immutable saved JSON revisions, reopened/downloaded/
  printed in Sources. Disk failure refuses a successful save. Actual headless
  Edge + real API: draft, review, approve, reload, reopen, download PASS.
- That browser run caught a late Students response overwriting Sources. Guard
  added and same run passed. Retired navigation absent in the actual DOM.
- Desktop window bounds clamp to a connected display's usable area. TypeScript
  build and actual compiled-function tests pass (unplugged monitor, small screen,
  negative display coordinates, invalid numeric saved bounds).
- Document safeguarding previously claimed restricted routing without calling it.
  English/Italian synthetic family reports now enter the restricted ledger and
  local coordinator queue once; sensitive chunks never reach normal extraction
  logs or the model fallback. 42 related tests passed after two red cases.
- Assess now has text, document, file audio and in-app recording controls, a
  mandatory corrected-text step, four editable diagnostic dimensions with quotes,
  confirmation through the field contract, a printable saved result, and undo.
  Records are append-only in the existing student SQLite store; assessment_profile
  is a projection, not another writable student blob. No grades or automatic CEFR.
  Drafts are saved and can resume from Sources. Active findings appear in the lens,
  L11 search and (for explicit reviewed support decisions) parent summaries.
- Actual Edge/API text diagnostic -> review -> lens -> saved output -> undo PASS.
  English/Italian API journey tests also prove summary inclusion and withdrawal.
- qwen3:8b was present when checked. Actual local model runs on deliberately flawed
  English/Italian samples returned findings with exact evidence quotes. Category
  assignments were imperfect: these are suggestions, not semantic verification.
  The fluency dimension keeps measured data/review instructions because a text
  model cannot hear pauses. Both runs used local_only=True.
- Whisper small, actual synthetic eSpeak recordings: English 25.5s, WER 0.000;
  Italian 27.9s, WER 0.065. Timed segments retained. This proves synthetic-speech
  plumbing, not accuracy for a child's voice, accent or classroom noise.
- Local OCR uses rapidocr-onnxruntime 1.4.4, whose wheel includes models; source
  inspected after installation. Synthetic English/Italian image test with socket
  connections blocked passed. Every OCR result requires correction; scores are
  recognition estimates, not accuracy guarantees. Real handwriting pending.
  Reference: https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/
- Latest focused regression: 72 passed. Browser and TypeScript passed. Linux full
  suite at 072a6f2 had 3114 passed / 6 failed: four documented baseline failures plus
  two now-obsolete Home-default assertions, updated for the operator's ruling.
  The Assess/OCR slice still requires its Linux full run and UI re-lock.

Remaining before any completion claim: all-source browser path, Linux validation,
installer/dependency smoke, release-window check, live release verification and
install-over-install measurement. Teacher witness and clean Mac are still pending.

### Follow-through checks

Actual Edge + real API, using installer-pinned faster-whisper 1.1.1 and
opencv-python 5.0.0.93: synthetic photo, scanned PDF, English WAV, Italian WAV,
and the in-app MediaRecorder control (synthetic microphone device) each reached
text correction, diagnostic review, lens and saved output. The same run passed
the administrator query -> saved CSV journey. No JavaScript errors.

Linux OCR's first failure was real: the bundled angle classifier flipped an
upright DejaVu Italian line. Disabling the angle classifier after EXIF orientation
made that exact image pass, including OpenCV 5.0.0.93. Correction remains mandatory.

Sources now resumes both text-correction and diagnostic-review checkpoints and
downloads their original files. Classroom packets join the same saved-work view.
Two red tests exposed same-second packet filename reuse and absent reopen controls;
packet filenames now include a revision suffix and PDF/Markdown saves are atomic.

The baseline test defects are corrected: add the missing pytest import to the
grounding tests; simulate PermissionError directly in the reconciliation test so
it tests the same failure on Windows and root Linux. The missing-field expectation
now includes the declared assessment_profile. These changes do not remove checks.
The new Linux full-suite result will be recorded after the UI lock is updated.
