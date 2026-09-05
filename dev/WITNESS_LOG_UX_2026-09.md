# WITNESS LOG — LV UX lane, September 2026

Append-only. One entry per live test. PASS / FAIL / CANNOT-TELL per step, exact wording seen, the release tag tested. A row on the tracker moves only with an entry here.
Rule (plan §0): a Mical PASS = "ready for teacher witness", not green. Green needs Claudia or Olga.

---

## Cycle 0 — 2026-09-04 — main `30f5e03` → auto-release run 33908229547

**What is in it:** the 29 commits of `fix/cefr-write-and-unknown-field-refusal-2026-09-03` (lens field contract; report card → lens with every field accounted for and idempotent re-apply; Observe → lens, typed and voice; Prepare and the parent note reading the lens; CEFR plus levels; Doctor `python3` fix; `lv lens-query`; the readiness path, the UX set, three specs, one prompt). Full suite on PC-23: 2,987 passed / 34 failed, all 34 identical on untouched main.

**Outcome of run 33908229547 (`30f5e03`): FAILED at "Test gate"** — Health, Backend smoke, desktop-release and pin-site skipped; nothing shipped; v0.2.84 stayed live.
**Cause, proven on Linux/Python 3.11 (WSL clone at `30f5e03`, LF bytes):** `src/web.py` is a contract-protected file (`contracts/UI_CONTRACT.yaml`, v180) and cycle 0 changed it without a bump — `test_ui_contract_check_passes` and `test_ui_contract_lock_matches_live_files` fail (`locked f9d50f5c… / actual 2dc3cb74…`). On PC-23 those two tests already fail for CRLF reasons (Windows baseline rows 32–33), which is why the Windows "0 new failures" could not see it. Class: **a Windows-baselined test can mask a real Linux failure** — the CI replica in WSL now exists so this class is measurable here.
**Fix:** `fix/ui-contract-v181-lens-routes` = `604a823` (bump-log v181, `EXPECTED_VERSION = 181`) + `f22e7a6` (lock re-taken by `check_ui_contract.py --bump` on the Linux LF checkout; every hash equals the git blob's sha256; contract tests 8 passed / 1 skipped on Linux).
**Re-push:** `f22e7a6` -> `main` at 2026-09-04 after a second window check (0 in flight). Full suite on Linux/3.11 in WSL at `f22e7a6`: **3,035 passed / 5 failed / 34 skipped / 32 xfailed in 1m45s**; the same 5 fail identically at `71b069d` (the last green CI commit) in that environment — repo dir name (`lv-ci-full` != `learning-architecture`), root user (read-only file test), and a `pytest` NameError in `test_ask_grounding_surface.py` — so 0 new failures on Linux against the last green commit.

**Release tag:** `desktop-v0.2.85` — auto-release run 33910405182 on `7fa7c9a` (main = `f22e7a6` + the U1 Rung 1 docs + the C8 durability test), every job success, published 2026-09-04T19:27:04Z; `https://linguaviva.art/` pins `desktop-v0.2.85`; Setup.exe / .dmg / .AppImage all HTTP 302.
**Live download contains `30f5e03`:** YES — the tag's commit `ee6805c` descends from `7fa7c9a` → `f22e7a6` → `30f5e03` (`git merge-base --is-ancestor`, PC-23, 2026-09-04).

**→ v0.2.85 ready — test U-1** (the click path below, plus the chain A–E). Note for step 4: the Doctor fix (`sys.executable`) is in this build.

### Mical — U1 click path (prompt §6) on the live download

| step | expected | verdict | wording seen |
|---|---|---|---|
| 1 download button → tag served | desktop-v0.2.85 | | |
| 2 installer dialogs | none unexpected | | |
| 3 first launch, minute one | app usable, no traceback | | |
| 4 Governance → Doctor | green, plain words | | |
| 5 Students → classe-3B.csv → approve → confirm | 6 lenses, accents intact | | |
| 6 quit, relaunch | 6 students still there | | |
| 7 network off, relaunch | works or names what is unavailable | | |

### Mical — the chain that is level 3 on a fixture (cheat-sheet beats 3, 5, 6, 7)

| step | expected on v0.2.85 | verdict | wording seen |
|---|---|---|---|
| A upload `pagella_abigail_chang.txt` → Update lenses | CEFR reading A2 / writing A1 / speaking **A1+** / listening A2; the apply result lists what was written, what needs confirmation, and **names every field it refused** | | |
| B apply the same report card again | nothing doubles (same counts on the lens) | | |
| C Observe (typed): `Abigail finished early again and could benefit from extension activities. Listening: A2+.` | saved; the lens gains an Advanced/Enrichment entry marked as a teacher note; listening moves to A2+ | | |
| D Students → Abigail → lens | report entries and the note both visible, with where each came from | | |
| E Student Summary → Draft | the note mentions the listening progress AND a strength from the report card; nothing invented | | |

_(FAIL → verbatim error back to PC-23. PASS → tracker row to "Mical-passed, awaiting teacher witness".)_

---

## Cycle 1 — 2026-09-04 — main ← `ux/u13-safeguarding` (= v0.2.85 + U2 + U13 + UI contract v182)

**What is in it:** U2 roster honesty (`90d9c88`: a CSV roster is read as a table — names carry column evidence and are never flagged "low confidence", the Classe column becomes the lens's grade, nothing invented when the column is absent, a re-import never overwrites a teacher-set grade; 6 tests, 4 red first). U13 safeguarding P0 through the routes (`bac8112`: the three RED rows of the 2 September retest and the five innocent rows posted to `/api/observe/capture`; RED responses no longer carry the matched indicator regexes; every normal surface read back empty; `GET /api/safeguarding/pending`; the coordinator's Safeguarding panel in Governance; 15 tests, 6 red first). Lock v182 (`0f6f792`, taken on Linux). Full suite on Linux/3.11 (WSL) at `0f6f792`: **3,064 passed / 5 failed / 34 skipped / 32 xfailed in 1m46s** — the same 5 environment-only rows as at `71b069d` (last green CI) and at every head today; Windows targeted suites 139 passed.

**Release tag:** `desktop-v0.2.86` — auto-release run 33911993275 on `eacc3c5` (= `0f6f792` rebased onto the v0.2.85 site pin), every job success, published 2026-09-04T19:44:06Z; `https://linguaviva.art/` pins `desktop-v0.2.86`; Setup.exe / .dmg / .AppImage all HTTP 302.
**Live download contains `0f6f792` / `eacc3c5`:** YES — the tag commit `0b3ac28` descends from `eacc3c5` (`git merge-base --is-ancestor`, PC-23, 2026-09-04).

**→ v0.2.86 ready — test U-2 and U-13** (click paths below). It also contains everything v0.2.85 had, so U-1 can be run on this build instead.

### Mical — U2 click path on the live download

| step | expected | verdict | wording seen |
|---|---|---|---|
| 1 Students → import `demo-data/classe-3B.csv` | preview lists 6 names, accents intact; **no** "low confidence" mark on any of them; the class picker shows `3B` | | |
| 2 approve | "6 students added from classe-3B.csv."; no "Check these names" warning | | |
| 3 Roster rows | each row shows `3B` after the support tier | | |
| 4 import the same file again | still 6 students; nothing doubled; a grade you edited by hand is untouched | | |

### Mical — U13 click path on the live download (two roles)

| step | expected | verdict | wording seen |
|---|---|---|---|
| 1 as coordinator: Governance | a **Safeguarding** panel at the top: "No safeguarding items are waiting." badge `0` | | |
| 2 as teacher: Observe, pick a student, type `Qualcuno a casa gli fa paura.` and save | badge **Restricted record — not yet routed to a person.**; NOT "Saved locally" | | |
| 3 Students → that student → observations / lens | the sentence is nowhere; no observation was added | | |
| 4 Student Summary → Draft for that student | no word of it | | |
| 5 as teacher: Observe, type `Ha paura del buio durante la lettura` and save | an ordinary saved note (no restricted badge) | | |
| 6 as coordinator: Governance | "1 safeguarding item is waiting. No notification channel is configured — set one in Settings, or review them here." badge `1`; no student name, no words of the sentence anywhere on that panel | | |
| 7 as teacher: Governance | no Safeguarding panel at all | | |

_(FAIL → verbatim error back to PC-23. PASS → tracker rows U2 / U13 to "Mical-passed, awaiting teacher witness". Claudia typing step 2 in her own app is level 4 for U13 — the spec's R4.)_

---

## Cycle 2 — 2026-09-04 — main ← `ux/u8-editable-lens` (= v0.2.86 + U8 + UI contract v183)

**What is in it:** U8 edit a lens by hand (`2f82915`: `POST /api/students/{id}/support-entry/dismiss` deactivates one entry — never deletes — and every reader drops it; the writer returns `written_entries` with ids; the Students view carries a *remove* control on every support entry and hides dismissed ones; the Observe result shows "What this note did to the lens" with a *not this — remove* undo per written entry; 5 tests, all red first). Lock v183 (`9be3888`, taken on Linux). Full suite on Linux/3.11 (WSL) at `9be3888`: run 1 **3,068 passed / 6 failed** — the five environment rows plus `test_teacher_identity::test_sync_never_exports_unprovisioned_ledger` (Drive sync returned False); run 2 **3,069 passed / 5 failed** (the five rows only). That test passes alone, as its whole file (×3), and with each new test file run ahead of it — an order/timing flake in the full run, not a U8 regression; recorded here, not baselined. Windows: U8 + contract + Observe + parent-report + reachability + U13 suites 74 passed.

**Release tag:** `desktop-v0.2.87` — auto-release run 33913640279 on `648c9ea`, every job success, published 2026-09-04T20:03:26Z; `https://linguaviva.art/` pins `desktop-v0.2.87`; Setup.exe / .dmg / .AppImage all HTTP 302.
**Live download contains `9be3888` / `648c9ea`:** YES — the tag commit `aea93a7` descends from `648c9ea` (`git merge-base --is-ancestor`, PC-23, 2026-09-04).

**→ v0.2.87 ready — test U-8** (click path below). It contains v0.2.85 and v0.2.86, so U-1 / U-2 / U-13 can all be run on this build.

### Mical — U8 click path on the live download (plan #5 "Done means": mis-route a note on purpose, see what it did, correct it in two clicks)

| step | expected | verdict | wording seen |
|---|---|---|---|
| 1 Observe, pick a student, type `Finished early again and could benefit from extension activities.` save | "Saved" + a line **What this note did to the lens: 1 lens field updated.** and one row `advanced enrichment · evidence` with the sentence and a *not this — remove* button | | |
| 2 click *not this — remove* | button turns to **removed**; no error | | |
| 3 Students → that student → lens | the enrichment entry is not shown | | |
| 4 Students → any student with support entries → click *remove* on one | toast "Removed from the lens. The note it came from is kept."; the entry disappears; the observation it came from is still in the history | | |
| 5 Student Summary → Draft for that student | the removed entry's text is not in the note | | |

_(FAIL → verbatim error back to PC-23. PASS → tracker row U8 to "Mical-passed, awaiting teacher witness". Known edge, recorded in the commit: re-applying the same source after a remove brings the entry back as a fresh suggestion — a sticky remove is your ruling.)_

---

## Cycle 3 — 2026-09-04 — main ← `ux/sir-profile` (= cycle 2 + plan #6 SIR profile + UI contract v184)

**What is in it:** the SIR deployment profile (`7a09884`: `deployment_profile` in the school profile, `la_scuola` default or `sir`; `LV_DEPLOYMENT_PROFILE` env wins for an install; under `sir` the nav hides Home / Daily / Plan / Slack and teachers boot to Students; the shell paints only after the profile is known; unknown values are a named 400; a malformed file boots with the default; 6 tests, all red first). Lock v184 (`0302414`, taken on Linux). Full suite on Linux/3.11 (WSL) at `0302414`: **3,073 passed / 7 failed** — the five environment rows plus two `test_home_view.py` pins on the literal default-view strings the profile replaced; fixed in `8e37fd9` (the intent is asserted against `defaultViewFor()`), and home-view + SIR + contract + school-profile suites 53 passed / 1 skipped on Linux at that head.

**Release tag:** `desktop-v0.2.88` — auto-release run 33914464568 on `dd89712`, every job success, published 2026-09-04T20:13:46Z; `https://linguaviva.art/` pins `desktop-v0.2.88`; Setup.exe / .dmg / .AppImage all HTTP 302.
**Live download contains `0302414` / `dd89712`:** YES — the tag commit `938f82c` descends from `dd89712` (`git merge-base --is-ancestor`, PC-23, 2026-09-04).

**→ v0.2.88 ready — test the SIR profile** (click path below). This build contains every cycle of the day (U1 install foundation + C8, U2, U13, U8, SIR), so all five click paths can be run on it.

**Lane state at 20:15Z:** plan #1–#6 built and shipped; the plan's STOP line applies — U10 is not started until Mical says so. Open verdicts: every row above. Open decisions for Mical: sticky remove (U8), a Settings control for the deployment profile, `gh auth login` on PC-23.

**Rulings received 20:30Z:** *"Sticky remove yes -- go ahead with U10."*

---

## Cycle 4 — 2026-09-04 — main ← `ux/u10-approve-print` (= cycle 3 + sticky remove + U10 + UI contract v185)

**What is in it:** sticky remove (`e3e2adb`: a dismissed entry counts as present for the writer's dedupe, so re-applying the same note or report card never brings it back; the ledger says "0 entries written, 1 already present"; 1 test, red first). U10 approve/print (`POST /api/parents/approve` behind a minimum-evidence gate of 1 evidence-backed sentence; trauma-safety re-check on the teacher's edit; name strip on full name **and** name tokens — the full-name-only gate let "amina's" through, found and fixed; publication gate; signed artifact with `print_html` / `printable_text` and the evidence ids; content-free `parent_report_approved` log line; the UI shows "Not enough evidence to send", approves through the route, prints the returned artifact; 8 tests, all red first). Lock v185 (`c281172`, taken on Linux). Full suite on Linux/3.11 (WSL) at `c281172`: **3,083 passed / 6 failed** — the five environment rows plus one `test_parent_summary_finish` pin on the old client-built print doc, updated in `feeac60` (Print now hands the approved artifact to the same exit surface); those files 27 passed / 1 skipped on Linux at `feeac60`. Windows: the day's twelve suites 125 passed.

**Release tag:** `desktop-v0.2.89` — auto-release run 33919984498 on `382beb6`, every job success, published 2026-09-04T21:21:48Z; `https://linguaviva.art/` pins `desktop-v0.2.89`; Setup.exe / .dmg / .AppImage all HTTP 302.
**Live download contains the U10 head (`382beb6`):** YES — the tag commit `65d9c4a` descends from it (`git merge-base --is-ancestor`, PC-23, 2026-09-04).

**→ v0.2.89 ready — test U-10 and the sticky remove** (click paths above). Every earlier cycle is in it.

---

## Cycle 5 — 2026-09-04 — main ← `ux/sir-download-surface` (= cycle 4 + School profile in Settings + Still I Rise download section + UI contract v186)

**What is in it:** the operator's 21:00Z ask ("push all the way to app/prod in the app store under Still I Rise"): there is no app store in this tree, so the live download surface got a **Still I Rise schools** section on linguaviva.art (same three installers, tracked by pin-site, plus the one-click instruction) and Settings got a **School profile** select + Apply that POSTs the deployment profile and repaints the shell at once (`e14a18d`; 2 tests, red first). Lock v186 (`446dd51`, taken on Linux). The live test harness: `dev/HARNESS_LIVE_TEST_2026-09-04.md` and the interactive page https://claude.ai/code/artifact/4acfefa3-151d-4f15-822c-639b2dedfeef. Full suite on Linux/3.11 (WSL) at `446dd51`: **3,086 passed / 5 failed** — the five environment rows only.

**Release tag:** `desktop-v0.2.90` — auto-release run 33920915583 on `36c38a0`, every job success, published 2026-09-04T21:32:33Z; `https://linguaviva.art/` pins `desktop-v0.2.90` and carries the **Still I Rise schools** section (three installers, all HTTP 302).
**Live download contains the cycle 5 head (`36c38a0`):** YES — the tag commit `a3a09df` descends from it (`git merge-base --is-ancestor`, PC-23, 2026-09-04).

**→ v0.2.90 ready — this is the build for the whole harness** (`dev/HARNESS_LIVE_TEST_2026-09-04.md`; interactive: https://claude.ai/code/artifact/4acfefa3-151d-4f15-822c-639b2dedfeef). It contains every cycle of the day: U1 foundation + C8, U2, U13, U8 + sticky remove, SIR profile with the Settings control, U10.

**Lane state at 21:35Z:** plan #1–#6 and U10 built and live. Open: every verdict; a preset Still I Rise installer (a desktop/ bootstrap marker + second channel — a ruling); the PDF renderer left unmounted; `gh auth login` on PC-23.

---

## Live install on PC-23 — 2026-09-04 21:45Z — desktop-v0.2.90, operator's word "launch the app" (witness: the PC-23 seat, not Mical)

| step | expected | verdict | wording seen |
|---|---|---|---|
| U1-1 download from linguaviva.art | tag served | PASS | `desktop-v0.2.90/LinguaViva-Setup.exe`, 81,762,592 bytes, sha256 `27a04f8d…` |
| U1-2 installer dialogs | none unexpected | PASS | silent NSIS per-user install to `%LOCALAPPDATA%\Programs\lingua-viva-desktop`; no dialog; the app launched itself |
| U1-3 first launch, minute one | usable, no traceback | **FAIL** | the wizard's consent-click Ollama install ran (Ollama's own "Welcome to Ollama!" window appeared; `ollama app.exe` + `ollama.exe` running, models `[]`), then a modal titled **Error**: *"A JavaScript error occurred in the main process — Uncaught Exception: Error: spawn ollama ENOENT at ChildProcess._handle.onexit (node:internal/child_process:286:19)"*. No `~/.lingua-viva/logs/` was written. Backend never started. |
| recovery | — | PASS | quit the four `Lingua Viva.exe` processes, relaunched from the install dir: window **"Still I Rise — Setup"**, no Error; `setup.log` shows the dependency install completing; backend listening on 8787 after ~3 min |

---

## Claudia's live session on PC-23 — 2026-09-05 from 03:00Z — desktop-v0.2.91 → v0.2.92 (first real teacher on the lane's builds)

| step | expected | verdict | wording / what happened |
|---|---|---|---|
| U2-1 Students → Import your roster → `classe-3B.csv` → Import a local file | 6 names, accents, no low-confidence mark, class 3B | **PASS** (03:05Z) | preview: 6 names, `low_confidence: False` on all, class `3B`. Friction: the app window had opened squeezed to the right edge and the import box was off-screen — she could not see it; the seat resized the window. Friction: the file picker — she could not find the folder; copies were put in Documents and Downloads and an Explorer window opened. Noted, not shown to her: the job carried an internal warning line (`grounding_dropped:model_veto:Nome Classe Note:…`) — the roster UI does not render `job.warnings`, so it stayed in the job file. |
| U2-2 Create these 6 students | 6 created, grade 3B | **PASS** (03:06Z) | store: 6 students, all `3B`, `Lucà Rossi` / `Noëmi Villa` intact — **U2 at level 4** (witnessed by a teacher who is not the developer). |
| U3-A Update lenses from documents → `pagella_abigail_chang.txt` → Upload and extract → Update all lenses | CEFR reading A2 / writing A1 / speaking A1+ / listening A2; written / needs-confirmation / refused named | **FAIL** (03:08Z) | Abigail's snapshot stayed empty: the CEFR reader knew only the English words; the pagella says *Ascolto / Parlato / Lettura / Scrittura*. Last night's chain ran on the English fixture. And the six fields held for her confirmation were invisible: the app showed *"student-chang-abigail — 1 field(s) updated"* and nothing else; the route could not take a per-field confirmation at all. |
| fix | — | shipped as cycle 7 = **`desktop-v0.2.92`** (run 33941685826 on `cac732b`, success, site pinned) | `e74bf3b` Italian labels + two-pass reader (direct "label: level" wins over the 25-char proximity rule); `d587890` review step: tick boxes on held fields, plain labels, `confirmed_fields` through the route, the result names the student and counts written / waiting / refused; lock v187. Linux/3.11: 3,100 passed / 5 env rows. |
| C8 live | install v0.2.92 over v0.2.91 keeps every lens | **PASS** (03:40Z) | store before 6, after 6; backend healthy; the served page carries the review step. |
| U3-A retest on v0.2.92 | the four levels + the held items confirmable | _(Claudia, in progress)_ | |

**Cause (read in `desktop/electron/bootstrap.ts`):** after the silent Ollama installer exits 0, `installOllamaWindows()` spawned `ollama serve` by bare name — the new install is on the *user* PATH only, which the already-running Electron process never re-reads — and the detached child had no `error` listener, so Node turned the async ENOENT into an uncaught exception. This is Olga's 3 September class ("another error popped up"): a first-run failure path with a traceback instead of a named message.
**Fix:** `fix/u1-ollama-spawn-enoent` — one resolver `ollamaCommand()` (PATH, then `%LOCALAPPDATA%\Programs\Ollama`, `/opt/homebrew/bin`, `/usr/local/bin`), `addOllamaDirToPath()` after a successful install, the serve spawn carries an `error` handler that writes a named line to `setup.log` and never throws; `tests/test_desktop_ollama_spawn.py` (4, red first). Shipped as **cycle 6 = `desktop-v0.2.91`** (run on `05e1c91`, every job success, site pinned, installers 302, tag commit descends from the fix). The install on PC-23 is v0.2.90 and was recovered by relaunch; the first clean witness of the fixed first run is the next fresh install (U1-3 in the harness).

_(The SIR click path in cycle 3 now starts from Settings → School profile; the harness has the updated steps.)_

### Mical — U10 click path on the live download

| step | expected | verdict | wording seen |
|---|---|---|---|
| 1 Summaries → pick a student who has **no** observations and no report card → Draft Summary | draft appears with a red box **Not enough evidence to send** and its reason; the Approve button stays disabled even after ticking the checklist; status "Not enough evidence to send — nothing here can be approved." | | |
| 2 pick Abigail (report card applied earlier) → Draft Summary | no red box; a sentence with a strength from the report card; checklist → tick all three → **Approve** enabled | | |
| 3 edit the textarea (add one warm sentence) → Approve | toast "summary approved"; status "Approved — N piece(s) of evidence behind this note, signed <you> (Class Teacher)."; **Copy final text** and **Print** appear | | |
| 4 Print | the printed page has the subject, your edited text, "A few things you could try at home", the signature line "— <you> (Class Teacher)"; no student name, no ids, no AI wording | | |
| 5 edit the textarea to include the child's first name → Approve | refused: "The child's name or a private detail is still in the note. Replace it with 'your child' and approve again." | | |
| 6 edit to include "refugee student" → Approve | refused with the unsafe label named | | |

### Mical — sticky remove (U8 ruling) on the live download

| step | expected | verdict | wording seen |
|---|---|---|---|
| 1 Observe → the extension-activities note → *not this — remove* | removed | | |
| 2 Observe → the **same** note again → save | "What this note did to the lens: 0 lens fields updated" or the field named with "already present"; **no** new remove row; Students → lens shows no such entry | | |

_(FAIL → verbatim error back to PC-23. PASS → tracker row U10 to "Mical-passed, awaiting teacher witness" — Claudia sending one real note is level 4.)_

### Mical — SIR profile click path on the live download

| step | expected | verdict | wording seen |
|---|---|---|---|
| 1 fresh launch (La Scuola default) | teacher nav shows Home · Daily · Plan · Prepare · Observe · Students · Assess · Ask · Summaries; utility nav shows Slack | | |
| 2 `curl -X POST localhost:8787/api/school-profile -H "Content-Type: application/json" -d '{"deployment_profile":"sir"}'` (or set `LV_DEPLOYMENT_PROFILE=sir` before launch) | `200`; `GET /api/school-profile` shows `"deployment_profile": "sir"` | | |
| 3 reload as teacher | nav shows Prepare · Observe · Students · Assess · Ask · Summaries only; no Slack; the app opens on **Students** | | |
| 4 brand/home click | goes to Students, not Home | | |
| 5 as coordinator | Programme view as before; Governance still there | | |
| 6 POST `{"deployment_profile":"hogwarts"}` | `400` naming the choices; nothing changes | | |
| 7 back to `la_scuola` | Home returns | | |

_(Plan #6 "Done means": SIR profile boots to Students with the four surfaces hidden; test green — the test half is done, the boot half is this table. No Settings control yet; the flag is POST or env.)_
