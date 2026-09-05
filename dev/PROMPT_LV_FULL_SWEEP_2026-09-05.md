# PROMPT — LINGUA VIVA FULL SWEEP: every UX, made to work, to a very high bar

**Written:** 2026-09-05 04:10Z by the PC-23 seat, at the end of the 2026-09-04 lane day (cycles 0–7, desktop-v0.2.85 → v0.2.92) and the first live session with a real teacher (Claudia, PC-23). **Operator:** Mical Neill. **Teachers:** Claudia (La Scuola, Italian immersion K-5 PYP), Olga (Still I Rise). **Mandate:** *"go over each and every UX and simply make it work … a full mandate to make it work to a very high bar."*

**Read first, in this order:** `AGENTS.md` (the definition of *pushed*, the release window, the merge doctrine) · `dev/PATH_TO_UX_READINESS_2026-09-04.md` (levels 0–5, the five properties, the hard list) · `dev/WITNESS_LOG_UX_2026-09.md` (what a real person has seen, verbatim) · `dev/HARNESS_LIVE_TEST_2026-09-04.md` · the 2026-09-03 Still I Rise meeting recap (this prompt carries its rulings in §1) · `dev/ASSESS_CHANGES_NEEDED_2026-09-03.md` · `dev/UX_MATRIX_AND_ACTION_LIST_2026-09-03.md`.

---

## 0. The one shape behind every UX: multi-in → lens → multi-out

The student lens (`src/education/student_lens.py`, SQLite `~/.lingua-viva/runtime/student_lenses.db`) is the only record. Everything a teacher gives the app — a roster, a report card, a progress report, a document from the state about the child's family, a typed note, a voice note, an oral-exam recording, a photo of written work, a past test — is an **input that resolves into declared lens fields** through one contract (`src/lingua_viva/lens_field_contract.py`: `FieldSpec` registry, `resolve()` the only way in, the accounting invariant *every field lands in exactly one of written / review_required / unresolved*, `read_for(output_id)` the only way out). Everything the app produces — a lens view, a parent note, differentiated materials, an oral diagnostic, an admin query, a printed page — is an **output that reads the lens through `read_for`** and says which fields it used and which it lacked.

So "make a UX work" means, for every UX below: **(a)** the input reaches the lens with every sentence accounted for, nothing invented, refusals named; **(b)** the teacher can see what happened and undo it in two seconds; **(c)** the output cites the lens entries it used; **(d)** a real teacher has done it on the live download and written down what she saw. That is level 4 in the readiness path. Level 3 (fixture end to end) is where most of the list sits tonight; level 4 is the bar.

**The five properties (readiness path §1) are the acceptance test of every UX:** named failures · nothing fabricated · reversible · private by construction · measured.

---

## 1. Rulings you must honour (each with its source)

| ruling | source |
|---|---|
| Still I Rise profile: hide Home / Daily / Plan / Slack, open on Students; code kept | Olga, 2026-09-03 meeting; shipped v0.2.88 + Settings control v0.2.90 |
| Oral assessment goes **under Assess**, 3–4 minute recordings, Italian and English, **not graded** — surface the problems (fluency, syntax, grammar, vocabulary) as an assessment-oriented output | Olga + Mical, meeting 19:08–21:57 |
| **One assessment logic** for a document and for an oral recording: same fields, same output | Mical, meeting 21:20, Olga "that sounds good" |
| Observe routing automated as far as possible; the manual controls (choose student, choose section) stay for the teacher who wants them | Mical, meeting 21:59 |
| PDFs must work; images "should work — untested" was said to a customer: make it true or make the app say it cannot yet | Mical to Olga, 17:33–17:56 |
| Lenses are saved locally and never overwritten by a reinstall (C8) | Mical to Olga, 25:51; locked by `tests/test_c8_install_over_install.py` |
| Sticky remove: a dismissed lens entry stays dismissed when the same source is re-applied | Mical, 2026-09-04 |
| Minimum-evidence gate on the parent note: threshold 1 evidence-backed sentence (`PARENT_NOTE_MIN_EVIDENCE`) | built 2026-09-04; the number is Mical's |
| No API key in any tree; no real child data in any test — `demo-data/` and `tests/fixtures/` only; the teacher's real roster only in her own app | standing |
| Never `check_ui_contract.py --bump` from a CRLF checkout; never push into an open release window; never `git add -A` | standing, `AGENTS.md` |
| The teacher is the authority on teaching; the tool bends to her use case, never the reverse | Mical, meeting 24:56; `CLAUDE.md` |

---

## 2. Every tool at your disposal (use all of them; each one exists because a class of failure needed it)

### 2.1 Proving before shipping
- **Red-first tests.** Every fix starts with a test that fails on the current tree and names the witnessed failure in its docstring (date, build, wording). `tests/test_u2_roster_honesty.py`, `test_u3_review_confirm.py`, `test_u8_editable_lens.py`, `test_u10_approve_print.py`, `test_u13_safeguarding_through_the_routes.py`, `test_c8_install_over_install.py`, `test_desktop_ollama_spawn.py`, `test_cefr_italian_labels.py` are the pattern.
- **Sabotage scripts.** A guard is not a guard until you watched it fail: `scratch/c8_sabotage.py` (four mutations, each must turn its test red, then revert with `git checkout --`). Do this for every new guard.
- **The Linux/3.11 CI replica in WSL** (PC-23): `~/lv-ci` (LF clone) and `~/lv-ci-full` (full-suite clone), venv `~/lv-venv` (uv, Python 3.11.16). `git fetch /mnt/c/Users/spide/lv-work <branch>` then `pytest -q tests/`; 1m45s for 3,100 tests. **The Windows baseline of 34 failures hides real Linux failures** (cycle 0 died on the UI-contract lock this way). Five environment-only Linux rows are known (`test_ask_grounding_surface` ×3, `test_closing` dir name, `test_reconcile` root); anything else is yours.
- **UI contract lock** (`contracts/UI_CONTRACT.yaml` + `.lock`, `tests/test_ui_contract.py`): `src/web.py`, `static/index.html`, `static/sw.js` are hash-locked. Any change: bump-log line + `EXPECTED_VERSION` + `--bump` **on the Linux LF checkout** (`scratch/wsl_bump_generic.sh <branch> "<name>" "<email>" <msgfile> <ref>`), verify every hash equals the git blob's sha256. v187 is current.
- **Route reachability manifest** (`contracts/ROUTE_REACHABILITY.yaml`, `scripts/check_route_reachability.py`): every route classified once; a route the UI calls is `reachable_from_ui` with its literal call-site string; the rest `intentionally_backend_only` with a reason. 35 rows are `deferred_undecided` — each is a UX not yet mounted.
- **Trash collector** (`scripts/trash-collector.py`, `config/reachability_roots.yaml`): which code serves which UX; run it before claiming a function is reached.
- **Doctor** (`doctor/support_loop/doctor.py`, `lv health`, `/api/health`): the app's own self-check; must be green on Windows and Mac in the packaged build (`_desktop_mode()` branch).
- **`lv lens-query L1..L12`** (`src/lingua_viva/lens_query.py`, `/api/admin/lens-query/*`): twelve deterministic questions over the store — use L11 (search) to prove a RED sentence is absent, L1/L2 for census/coverage after an import.
- **Desktop TypeScript type-check** on PC-23: `cd desktop && npm ci --ignore-scripts && npx tsc --noEmit` (node 24). Do it before any `desktop/**` push; a build failure costs a release cycle.

### 2.2 Shipping and verifying "pushed"
- **Release window check** before every main push: `actions/workflows/auto-release.yml/runs` via the public API (`gh` is not logged in on PC-23; on PC-0 use `gh run list`). 0 in flight or wait.
- **Trigger paths:** `desktop/**`, `src/**`, `static/**`, `docs/index.html`, `pyproject.toml`, `uv.lock`. A contracts/tests-only push does **not** release. `pin-site` pushes `chore(release): pin` to main after each release — **fetch before every push**.
- **"Pushed" means:** the tag's commit descends from your sha (`git merge-base --is-ancestor <sha> desktop-vX.Y.Z^{commit}`), `https://linguaviva.art/` pins the tag, and Setup.exe / .dmg / .AppImage answer HTTP 302. Only then say "vX ready — test U-n".
- **Publish the conflict map before any rebase** (`git diff --name-only <base> origin/main` ∩ yours); backup tags; verify by blob.

### 2.3 Watching a real person use it (PC-23)
- The installed app: `%LOCALAPPDATA%\Programs\lingua-viva-desktop\Lingua Viva.exe`; state `~/.lingua-viva`; logs `~/.lingua-viva/logs/{setup,backend}.log`; **the app's own request log** `~/.lingua-viva/request_events.ndjson` — tail it with a Monitor filtered to `POST|PUT|DELETE|4xx|5xx` and you see every action the teacher takes, as she takes it.
- Screenshots: PowerShell `System.Drawing` `CopyFromScreen`; a dialog's text: `System.Windows.Automation` (that is how "spawn ollama ENOENT" was read off a modal). Window placement: `SetWindowPos` (the app opened squeezed off-screen for Claudia; a first-launch window-state bug to fix — `desktop/electron/main.ts` `window-state.json`).
- Reinstall = install-over-install (C8 live): quit the app, run the new `LinguaViva-Setup.exe` silently, wait for 8787, compare `select count(*) from students` before/after.
- Fixtures on the box: `C:\Users\spide\Desktop\Lingua Viva demo\` (also Documents and Downloads). Ollama is installed on PC-23 with **no model**; `qwen3:8b` is the quality floor (`src/lingua_viva/config.py`) — pull it before testing anything model-backed.
- **The witness log** `dev/WITNESS_LOG_UX_2026-09.md`: append-only, PASS / FAIL / CANNOT-TELL, exact wording, the tag tested. **The interactive harness** https://claude.ai/code/artifact/4acfefa3-151d-4f15-822c-639b2dedfeef (verdicts save into the page; read them back with the Artifact tool).

### 2.4 The loop that moved the needle tonight (repeat it for every UX)
1. Prompt the teacher with **one** action in plain words (exact button labels — read them from `static/index.html` first).
2. Watch the request log; read the store (`sqlite3`), the job file (`~/.lingua-viva/ingest-jobs/`), the extraction log (`~/.lingua-viva/imports/*.ndjson`), the vault (`~/.lingua-viva/vault/`).
3. When it fails: reproduce offline on the same input in a sandbox (`LV_STATE_HOME` + `LV_CONFIG_HOME`), write the red test, fix the **class**, run the suites here and in WSL, bump the lock if needed, push, watch the chain, verify live, reinstall, ask her to do it again.
4. Record the row. Move to the next action only when the row says PASS by her.

Tonight's yield of that loop: U2 PASS at level 4 (her); the Italian CEFR labels (`Ascolto / Parlato / Lettura / Scrittura`) were unknown to the reader — the English fixture had hidden it; the six report-card fields held for her confirmation were invisible and unconfirmable; the app window opened off-screen; the file picker lost her. Four defects, two hours, all from one teacher and one report card. **Assume every UX below hides the same density until a teacher has done it.**

---

## 3. The UXs — one section each: bar, tools, build, witness

Format per UX: **Level now** (readiness path, corrected by tonight) · **Bar** (what level 4 means here) · **Build** (what to do, in dependency order) · **Witness** (the click path a teacher runs). Do them in the order given unless a witnessed failure re-ranks them; the order is by what blocks the most teachers.

### U1 — Install and first run (level 2 → 4)
**Bar:** clean Windows and clean Mac, no traceback ever; every first-run failure path is a named message with the next step; Doctor green in the packaged build; Ollama and the model download explained in the wizard in plain words; the window opens visible.
**Build:** (1) first-launch window state — never restore a position off-screen (`main.ts` `window-state.json`; clamp to the current display). (2) `desktop/electron/bootstrap.ts`: every `spawn`/`execFile` has an `error` listener (the ENOENT class, fixed for Ollama in v0.2.91; audit Python, pip, the backend spawn the same way). (3) Model download: progress and ETA in the wizard, "you only do this once", resumable. (4) Sabotage S1–S8 of `dev/PROMPT_LV_U1_INSTALL_TO_GREEN_2026-09-04.md` (no Ollama, no network, non-admin, non-ASCII path, OneDrive home, install-over-install, kill mid-first-run, Doctor on each) — automate what can be, transcript the rest. (5) A fresh-box run on both platforms recorded step by step.
**Witness:** harness section 1 (7 steps) by Mical on a clean box, then Olga on her laptop (her 3 September errors are the target).

### U2 — Roster → lenses (level 4 by Claudia, 2026-09-05 03:06Z)
**Bar held.** Keep it: CSV (`,` and `;`), xlsx, docx, Google Sheet export; accents; class column → grade; re-import idempotent; "only my class" scope. **Open:** the file picker (a teacher could not find the folder — add "recent folders" / drag-and-drop hint in the import box; test drag-and-drop); `job.warnings` are never shown (decide: show teacher-readable ones, keep internal ones in the job file — never a raw `grounding_dropped:` string on screen).

### U3 — Any document about a student → the lens (level 3, witnessed FAIL then fixed in v0.2.92; re-witness pending)
This is the hardest and most valuable UX. The inputs are **not known in advance**: report cards from other schools, progress reports, IEPs, a report from the state about the family, a teacher's letter, a PDF scan, a phone photo. Multi-in.
**Bar:** any of those, in Italian or English, matched to the right student (surname-first and given-name-first both), every sentence resolved into a declared field or named as refused / unresolved; verified fields written; held fields confirmable in two clicks with plain labels; nothing invented; RED safeguarding content routed to the restricted ledger and absent from the lens (the state-family report is exactly where this fires); re-apply idempotent; the teacher sees what happened by student name.
**Build:** (1) **A document corpus, not a fixture:** `tests/fixtures/docpipe/synthetic-corpus/` exists — extend it with one synthetic example of each expected type (Italian pagella, English report card from another school, IB progress report, an IEP-style support plan, a social-services family report with RED content, a teacher's letter, a scanned-PDF text layer, a photo), each with an `expected_extraction_*.json`; a golden test per type through `import-document` + `apply-extractions`. (2) **Field coverage:** measure with the accounting ledger — what share of sentences per document type is written / held / refused; refusals must name a reason a teacher understands; the `learning_and_cognition/evidence` catch-all is not a destination for everything. (3) **Model path:** with `qwen3:8b` present, the `ReasoningEngine` classifies ambiguous sentences — measure precision on the corpus against the deterministic path; the deterministic path is the floor and must never get worse. (4) **PDF:** `pdfplumber` text; a scanned PDF has no text layer — detect it and say so (U6 handles OCR). (5) **Images:** see U6. (6) **Matching:** `lens_match.match_document_to_students` — tokens in either order, accents folded, a document that names two students splits sections (`_split_into_student_sections`); an unmatched document goes to the unattributed queue with a plain reason. (7) **Provenance on the lens view:** every entry shows "from report card X, 2026-09-05" or "teacher note" (already on the wire as `source_ref_ids`; render it). (8) Safeguarding through this route: `capture_with_safeguarding` guards Observe; **prove the document route has the same gate** (`_is_red_safeguarding` in `lens_extract`) with the family-report fixture and `lv lens-query L11`.
**Witness:** harness section 2 (the chain) — Claudia's redo of the pagella on v0.2.92 first, then a second document type she brings.

### U4 — Observe → the right section (level 3 → 4)
**Bar:** typed and voice notes land in the right category and bucket without the teacher choosing them; the note's effect is shown at once ("What this note did to the lens", v0.2.87) with the undo; CEFR mentions move the snapshot; the student is resolved from the text when not chosen (`voice_intent.detect_student`, "Which student?" chooser); Italian notes route as well as English ones.
**Build:** (1) Italian routing vocabulary for `_route_to_support_category` (the CEFR-label class again — audit every keyword table for Italian pairs; `tests/test_safeguarding_parity.py` is the discipline: every English row has an Italian row). (2) Voice: `/api/voice/stt` with `faster-whisper` `tiny` — measure WER on a 30-second Italian sample; `small` is likely the floor for Italian (Mical: "English is much better trained"); make the model size a setting with a size/quality note. (3) Observe result renders `review_required` with confirm controls (same component as U3's tick boxes). (4) The observation confirm path (`observe_comment_to_lens` with `confirmed_fields`) exercised by a test on a comment, not only a report.
**Witness:** harness section 5 steps 1–3 and chain step 3 by Claudia; an Italian voice note by Olga.

### U5 — Assess: oral exam → diagnostic → lens (level 0 → 4; **promised to Olga within two weeks of 2026-09-03**)
**Bar (Olga's words):** a 3–4 minute recording, Italian or English; a transcript; the problems surfaced — fluency, syntax, grammar, vocabulary — "not graded"; the same output shape as a document-based assessment; the result lands in the lens (declared fields) with the teacher's confirmation; the recording never leaves the machine.
**Build (follow `dev/ASSESS_CHANGES_NEEDED_2026-09-03.md` §2–§3; S1 storage-shape ruling first):** (1) Contract: declare the assessment fields (`assessments[]` with `kind: oral|written|document`, `transcript_ref`, `dimensions: {fluency, syntax, grammar, vocabulary}` each with evidence spans and a level/observation, `cefr_estimate` per dimension as *suggested*, never written to `cefr_snapshot` without confirmation). (2) Pipeline: upload audio (`.m4a/.mp3/.wav/.webm`) → `voice_stt` (`small`, language auto or chosen) → transcript with timestamps → deterministic analysers first (speech rate, pauses, filler ratio for fluency; sentence length / fragment ratio for syntax; a grammar checker for Italian and English if one is local; vocabulary range by type-token ratio and CEFR word lists) → model-backed explanation only when `qwen3:8b` is present, always citing transcript spans → `review_required` for every judgement → apply through the writer. (3) One logic: the document-based assessment (a past test, an essay) goes through the same analysers on text. (4) UI under **Assess**: upload / record, progress ("transcribing 3:40 of audio, ~2 minutes"), the transcript with highlighted spans per dimension, the diagnostic in plain words, "add to lens" with tick boxes, print. (5) Tests: a 30-second Italian and English fixture recording (synthetic, no child), golden transcript, analyser outputs pinned; sabotage: a recording that mentions a family risk must route RED.
**Witness:** Olga records a 3-minute mock oral (herself, no student); she reads the diagnostic and says whether it names the problems she would name.

### U6 — Assess: written work and photos (level 0 → 3, schedule after U5)
**Bar:** a photo of handwritten work or a scanned test becomes text the teacher can correct before anything is written; the same assessment logic as U5; the app says clearly when OCR confidence is low.
**Build:** OCR local-only (Tesseract with Italian + English traineddata bundled by the installer, or a local vision model through Ollama); confidence per line; "correct the text" step is mandatory before analysis; image inputs accepted by `import-document` with the same route; a photo fixture in the corpus.
**Witness:** Olga photographs one page with her phone.

### U7 — View a lens (level 2 → 4)
**Bar:** a teacher opens a student and understands in ten seconds what is known, from where, since when, and what is waiting for her; "insufficient data" is never uniform noise; provenance per entry; RED content never visible.
**Build:** provenance rendering (U3.7); a "what changed since you last looked" strip (`profile_version`, `updated_at`); the pending-confirmation panel unified across report / observe / assess; BUG-4 closed with the route test (done in `test_u13`) and shown in the UI test.
**Witness:** Claudia opens Abigail after the redo and narrates.

### U8 — Edit a lens by hand (level 3 → 4)
**Bar held in v0.2.87–89** (remove in two seconds, sticky). **Open:** edit the text of an entry in place; move an entry to another bucket; set CEFR by hand as an observation (`set_initial_cefr` law: derived from observations, never a direct write); undo a remove.
**Witness:** harness section 5 by Claudia.

### U9 — Prepare: differentiated materials (level 2–3 → 4)
**Bar:** upload a lesson plan → three tiers that visibly use the uploaded content (BUG-1: ignored it), assignment of students to tiers from the lens (`assign_tier_with_provenance`, `read_for("prepare")`) with the reason shown, PDF print that a teacher would hand out, and the app says plainly when no model was available (today it returns template cards **and does not say so**).
**Build:** generation_status honest on the wire and on screen; the uploaded document's spans quoted in each tier; tier assignment reasons ("foundational: RTI tier 2, reading A1"); Italian output when the lesson is Italian.
**Witness:** Claudia uploads `piano_lezione_poesia_3B.txt` and reads the three tiers aloud.

### U10 — Summaries: the parent note (level 3 → 4)
**Bar held in v0.2.89** (evidence gate, approve, print, name tokens). **Open:** tone (`dev/SPEC_PARENT_NOTE_TONE_2026-09-04.md`: no report-card codes in a note, warm in the teacher's voice); Italian notes for Italian-speaking families (home_languages drives the language); one real note sent by Claudia.
**Witness:** harness section 7.

### U11 — Ask (level 2 → 3)
**Bar:** never fabricates (BUG-5); refuses by name on a cold start; every claim about a child cites a lens entry; with no model, says so.
**Build:** minimum-evidence refusal reusing `PARENT_NOTE_MIN_EVIDENCE`'s shape; GIR-style citation check on the answer against the lens; a cold-start test.
**Witness:** Claudia asks "what does Abigail need this week?".

### U12 — Sources / file map / knowledge library (level 2–3)
**Bar:** every ingested file visible with what it produced; the knowledge library parsed through `document_parser` (guard). **Witness:** Sources view after the day's uploads.

### U13 — Safeguarding, Governance, Why, Privacy, Health (level 3 → 4)
**Bar held in v0.2.86** (routes, surfaces, pending count, coordinator panel). **Open:** a notification channel other than Slack for a school without one (email? a coordinator's local inbox?) — a ruling; the drain stays a button; Italian indicator review with a native speaker (spec R4).
**Witness:** harness section 4 by Claudia (teacher) and Mical (coordinator).

### U14 — Profile / Settings (level 2 → 3)
**Bar:** teacher identity, colleague names, school profile (v0.2.90), model choice with size/quality words, Whisper size, provider connect/disconnect — each with a named failure. **Witness:** Claudia sets her teacher ID and the Still I Rise profile off/on.

### U15 / U16 — Home, Daily, Plan, Slack (hidden under SIR; kept for La Scuola)
**Bar:** under La Scuola they must not lie: Daily says what it needs configured; Plan says when no model is present. Low priority; do after U1–U11.

### U17 — Reflect (level 2)
**Bar:** witnessed once; a reflection that cites the day's observations. Low priority.

### U18 — Admin: query across lenses (level 1 → 3)
**Bar:** an admin panel on `adminNav` that runs L1–L12 with the ARON codes explained in words; exports a CSV without student names by default. **Build:** the panel (route exists); the manifest rows move from `deferred_undecided` to `reachable_from_ui`. **Witness:** Mical as coordinator.

### U19 / U20 — Teacher lenses; onboard a teacher (level 1 / 0)
**Bar:** an admin creates a teacher, the teacher's first launch is pre-provisioned (teacher ID, school profile, roster scope). **Build after** U1–U11 and only with a ruling on the provisioning channel.

### C8 — Durability (live PASS 2026-09-05: v0.2.91 → v0.2.92 kept six lenses)
Keep the test; add a Mac run; add a "backup lenses to a file / restore" control in Settings (one-way-door safety before any migration).

---

## 4. The order, and what "done" means for the sweep

1. **U3 re-witness with Claudia on v0.2.92** (the pagella; then a second document type). Fix what she hits. Then the chain (U3 → U4 → U7 → U10) end to end by her.
2. **U1 on a clean Windows and a clean Mac**, with the window-state and spawn audits landed first.
3. **U5 oral assessment** — Olga's two-week promise; S1 ruling from Mical first.
4. **U4 Italian routing + voice**, U8 edits, U9 Prepare honesty.
5. **U6 photos**, U11 Ask refusal, U18 admin panel.
6. U12–U17, U19–U20.

For every UX, done means: the witness log row says **PASS by a teacher** on a live download whose tag commit descends from your sha; the tests that locked it were red first and are green on the Linux replica; the harness page has the section; the readiness table's level column is updated in the same commit. Say "vX ready — test U-n" only after the live verification; say CANNOT-TELL when it is; never call a fixture pass a teacher pass.

## 5. Kill criteria for the sweep
- **K1** any output that names a child from data the lens does not hold.
- **K2** any RED content reaching a normal surface — test with `lv lens-query L11` after every ingest path you touch.
- **K3** any push that skips the Linux replica, the window check, or the live verification.
- **K4** any "should work" said to a teacher without a witnessed row behind it.
- **K5** a model-backed path that gets a different answer than the deterministic floor without saying so on the wire.

## 6. Where things are (2026-09-05 04:10Z)
- `main` = `7618a9b` (v0.2.92 pinned; witness log through Claudia's session). Branches on origin: `ux/u1-install`, `ux/u2-roster`, `ux/u13-safeguarding`, `ux/u8-editable-lens`, `ux/sir-profile`, `ux/u10-approve-print`, `ux/sir-download-surface`, `fix/u1-ollama-spawn-enoent`, `fix/cefr-italian-labels`, `fix/ui-contract-v181-lens-routes`.
- PC-23: app v0.2.92 installed and running, six demo students in the store, Ollama present with no model, `gh` not logged in, WSL replica ready.
- Open rulings for Mical: Assess storage shape (S1); a notification channel without Slack; a preset Still I Rise installer; the unmounted PDF renderer; Whisper model size; the OCR engine.
- Open for Claudia: the pagella redo on v0.2.92 (started 03:33Z).
