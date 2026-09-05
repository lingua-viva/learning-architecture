# DRIVER PROMPT — Chip's first QA run of Lingua Viva desktop-v0.2.95 (Mac)

You are driving Chip's QA run of the Lingua Viva desktop app. Chip runs the CRM lane on this team; he is not a developer and not a teacher. He judges what he sees; you handle the technical side. Everything happens on **his Mac**, from the **live download** — never from source, never with a developer flag. Chip's verdicts land in two places: the interactive harness page https://claude.ai/code/artifact/2d6787bd-2802-46cb-b1a7-5eff2905c5ff (verdicts save into the page) and `dev/QA_CHIP_LV_2026-09-05_REPORT.md`, which you create at session start and fill as you go.

**Context for you:** v0.2.95 was cut 2026-09-05 06:19Z by an overnight builder. Its automated journeys (Assess from text / photo / scanned PDF / audio / in-app recording, Observe with retained audio, Prepare packets, approved parent notes, saved administrator queries, reinstall preservation) passed on synthetic data in an isolated workspace. **No teacher has run them. No human has run the Mac build.** Claudia's real report-card retry has not happened. Chip's run is the first human on this build and the first human on a Mac. The builder's own list: `dev/OVERNIGHT_VERIFIED_JOURNEYS_2026-09-05.md`. The bar for every check: what Chip sees on screen, in his words, PASS / FAIL / CANNOT-TELL. A CANNOT-TELL is a real answer.

**Rules:** one step at a time; wait for what he sees; record his words verbatim; never tell him what he should be seeing before he says it; no student names that are real (the demo folder is fictional); do not push anything — the operator pushes; if anything asks for an administrator password, stop and report it.

## Step 0 — the demo files

```
git clone https://github.com/lingua-viva/learning-architecture.git ~/lv-demo
open ~/lv-demo/demo-data
```
That folder holds `classe-3B.csv` (a roster of six), `pagella_abigail_chang.txt` (an Italian report card), `piano_lezione_poesia_3B.txt` (a lesson plan), and four short notes. Nothing else from the clone is used.

## Step 1 — install from the site (this is a check, not setup)

Open https://linguaviva.art/ and scroll to **Get Lingua Viva**. Also look at the **Still I Rise schools** section under it. Click **Download for Mac**. Note the file name and the tag in the address it downloaded from (it must be `desktop-v0.2.95`). Open the `.dmg`, drag the app to Applications, launch it.

Record: every dialog macOS shows, verbatim (Gatekeeper wording especially — the build is signed by team `XWT7RB624U`; if macOS says the developer cannot be verified, that is a FAIL row, not something to work around with right-click → Open before recording it).

### Check 1 — first launch, minute one
Start a timer at launch. What is on screen after one minute? The setup wizard may offer to install Ollama and a model; accept. Record every message.
- **PASS**: a usable window within the minute, or a wizard that says in plain words what it is doing and how long it takes.
- **FAIL**: a blank window, a traceback, an "Error" dialog, or a step with no explanation.

### Check 2 — the version badge and Doctor
Top bar: the version badge must read **v0.2.95**. Then **Governance → Doctor**.
- **PASS**: v0.2.95, and Doctor is green in plain words.
- **FAIL**: another version, or a WARN / BLOCKED (copy the check names verbatim).

### Check 3 — the navigation is the simplified one
Look at the left column as Teacher, then switch role (bottom of the column) to Coordinator.
- **PASS**: no Home, no Daily, no Plan, no Slack in either role. Teacher sees Prepare · Observe · Students · Assess · Ask · Summaries; Coordinator adds Programme … and **Lens queries**.
- **FAIL**: any of the four is visible, or the app opens on a blank view.

## Step 2 — the roster (U2)

### Check 4 — import
**Students → Import your roster → Choose File → `classe-3B.csv` → Import a local file.**
- **PASS**: six names in the preview, Lucà and Noëmi with their accents, no "low confidence" mark, the class picker shows 3B.
- **FAIL**: fewer names, a warning on a name, an accent lost, or the file picker defeats him (record what he tried).

### Check 5 — create, then re-import
Click **Create these 6 students**. Then import the same file again and create again.
- **PASS**: "6 students added"; each roster row shows `3B`; after the second import still six, nothing doubled.
- **FAIL**: duplicates, missing grade, or a message he cannot interpret.

## Step 3 — the report card (U3) — the check Claudia never finished

### Check 6 — extract
**Students → Update lenses from documents → Choose File → `pagella_abigail_chang.txt` → Upload and extract.**
- **PASS**: a list for **Chang Abigail** with plain labels (e.g. "CEFR listening — A2", "Communication & language · evidence"), four CEFR lines (listening A2, speaking A1+, reading A2, writing A1), some lines marked **needs your OK** with a tick box, and an "Include everything marked needs your OK" toggle.
- **FAIL**: raw paths like `support_profile.categories…`, no CEFR lines, no tick boxes.

### Check 7 — apply, confirm, look
Tick the toggle, click **Update all lenses**. Then click **Chang Abigail** in the roster.
- **PASS**: the message names Abigail and counts what was updated / waiting / refused; her page shows the four levels and the confirmed entries, each saying where it came from.
- **FAIL**: an id instead of a name, empty levels, entries with no source.

## Step 4 — Assess (U5 / U6) — new in v0.2.95; Chip is the first human on it

### Check 8 — typed sample
**Assess → Review language work.** Choose Abigail, language Italian or English. Paste a deliberately flawed paragraph (Chip writes five sentences with two grammar mistakes and one repeated word). Click **Analyse corrected text** (correct the text first if the box asks).
- **PASS**: four findings (fluency, syntax, grammar, vocabulary), each with a quote from his own text; no grade; no CEFR change offered automatically; the two mistakes are among the quotes.
- **FAIL**: a grade, a level, an invented quote, or findings with no evidence.

### Check 9 — confirm to lens, print, undo
Edit one finding's wording, click **Confirm and save to lens**, then **Print diagnostic**, then go to **Students → Abigail** and look; then back in Assess click **Remove from active lens**.
- **PASS**: the diagnostic appears on Abigail's page and in **Sources** as saved work with Open / Download / Print; after Remove it leaves the active lens but stays in Sources as history.
- **FAIL**: nothing in the lens, nothing in Sources, or Remove deletes the history.

### Check 10 — a photo
Print (or handwrite) one paragraph on paper, photograph it with the phone, AirDrop the photo to the Mac. **Assess → Recording, photo or document → the photo → Read file.**
- **PASS**: the recognised text appears in **Corrected text** for him to fix before analysis, with a note that correction is required; a typeset page reads mostly right; handwriting may read badly — record the recognised text verbatim either way.
- **FAIL**: no text, a crash, or analysis running without the correction step.

### Check 11 — a recording
**Record oral sample.** Chip reads the same paragraph aloud for 30 seconds in English, then stops.
- **PASS**: a transcript appears in Corrected text within a couple of minutes, mostly right; the Whisper step says what it is doing while it runs.
- **FAIL**: no transcript, wrong language, or a silent wait with no progress.
Then repeat with a 20-second Italian read (any Italian sentence; accent does not matter) and record how much of it came through.

## Step 5 — Observe (U4)

### Check 12 — dictate, correct, save, reopen
**Observe → choose Abigail → dictate** "Abigail finished early again and could benefit from extension activities." Correct the words if needed, save.
- **PASS**: "Saved" with the line "What this note did to the lens: 1 lens field updated" and a *not this — remove* button; **Sources** shows the observation with a **Download saved version** of the original audio.
- **FAIL**: no lens line, no audio in Sources.

### Check 13 — the safeguarding sentence
**Observe → Abigail → type** `Qualcuno a casa gli fa paura.` **→ save.**
- **PASS**: **Restricted record — not yet routed to a person.**; Abigail's page and Sources show nothing of it; as Coordinator, **Governance** shows "1 safeguarding item is waiting…" with no name and no words.
- **FAIL**: "Saved locally", or the sentence visible anywhere normal.

## Step 6 — Prepare (U9)

### Check 14 — packet
**Prepare → upload `piano_lezione_poesia_3B.txt` → confirm the topic → Generate Activity → review the three tiers → Preview Printable Packet → Save Packet.**
- **PASS**: three tiers that visibly use the poem lesson (quote one line from each tier that comes from the upload); the app says whether a model was used; the packet reopens in Sources with Print.
- **FAIL**: generic tiers that ignore the upload, or no statement about the model.

## Step 7 — Summaries (U10)

### Check 15 — draft, approve, reopen
**Summaries → Abigail → Draft Summary → tick the three checklist boxes → add one sentence → Approve → Print.** Then **Sources → the note → Open.**
- **PASS**: no "Not enough evidence" box (Abigail has evidence now); "Approved — N piece(s) of evidence…, signed <name> (Class Teacher)"; the printed page has no student name, no ids, no AI wording; Sources reopens the approved version.
- **FAIL**: approval with nothing behind it, a name on the print, or nothing in Sources.
Then pick a student with nothing recorded (e.g. Giuseppe Esposito) → Draft Summary: **PASS** = the red "Not enough evidence to send" box and Approve stays disabled.

## Step 8 — Coordinator (U18)

### Check 16 — a saved answer
Switch to Coordinator → **Lens queries** → choose a question → fill its parameters → **Run and save answer** → **Download CSV** → **Sources**.
- **PASS**: an answer in words with its counts; a CSV file lands in Downloads; the answer is listed in Sources.
- **FAIL**: an error, an empty CSV, or nothing saved.

## Step 9 — durability (C8) — the last check, on purpose

### Check 17 — reinstall over
Quit the app. Download the Mac build again from the site and replace the app in Applications. Launch.
- **PASS**: the six students, Abigail's levels, the diagnostic, the notes and the saved work are all still there.
- **FAIL**: anything missing (name it).

### Check 18 — closing verdict
Best thing about this build? Worst thing? Would you hand it to a teacher tomorrow? Record his words verbatim.

## Reporting

Create `dev/QA_CHIP_LV_2026-09-05_REPORT.md` at session start: build tag, Mac model and macOS version, then one row per check — PASS / FAIL / CANNOT-TELL and Chip's exact words — and the closing verdict. Every FAIL needs the wording on screen or a screenshot name. Total pass/fail at the end. Do not push; the operator pushes, and the rows go into `dev/WITNESS_LOG_UX_2026-09.md` as the first Mac witness.
