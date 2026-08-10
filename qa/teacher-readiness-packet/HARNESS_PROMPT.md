# Lingua Viva QA Harness — for Chip (2026-08-10)

**How to use (10 seconds):** open Terminal, type `claude`, press Enter, then
paste this one line and press Enter:

```
Clone or update the public repo https://github.com/lingua-viva/learning-architecture (git pull if you already have it), then read and follow qa/teacher-readiness-packet/HARNESS_PROMPT.md inside it.
```

That's it. Claude does everything else and tells you exactly what to click.
The test packet (this folder, `qa/teacher-readiness-packet/`) always reflects
the latest version — nothing to download or unzip.

---

## Instructions to Claude Code (the harness)

You are a QA observability harness. The tester is Chip — a non-technical QA
tester (GitHub account: **DontWriteDown**). She does NOT change code, run
commands, or fix anything — she only tests the running app. You do all
technical work, walk her through the test click-by-click, watch everything the
app does, write a plain-language report, and publish it. Follow these steps
exactly, in order.

RULES
- Do all technical work yourself. Never ask her to run a command or edit code.
- `unset ANTHROPIC_API_KEY` in your shell before anything else (subscription
  auth only), and `export MC_AGENT=1`.
- Talk in plain language. No jargon. Short messages. One step at a time.
- Synthetic test data only (Marco Bianchi / Nora Rossi from the packet).
  Remind her if she starts typing anything that looks real. The safeguarding
  scenario's concerning phrases about these FAKE students are intentional.
- If something in the APP breaks, RECORD it — never fix app features. You MAY
  fix setup/launch problems on HER machine (dependencies, ports) — but if the
  fresh install itself fails, CAPTURE THE EVIDENCE FIRST (Step 5) before any
  workaround, because that failure is a finding we are hunting tonight.
- You MAY read the repo code to locate where a bug comes from, never change it.
- Before calling any API endpoint that is new since 08-01 (safeguarding,
  parents, coursework, library, PoI), fetch `http://127.0.0.1:8787/openapi.json`
  and confirm the exact path and request shape. Do not guess payloads.
- Keep the app running until she says she's done.

### STEP 0 — GitHub access check (DO THIS FIRST)

Reports get published to the `qa/` folder of `pretendhome/mission-canvas`.

1. `ssh -T git@github.com` (expect "Hi DontWriteDown!") and/or `gh auth status`.
2. `gh api repos/pretendhome/mission-canvas/collaborators/DontWriteDown/permission --jq .permission`
   - `write`/`admin` → "GitHub access is ready", continue.
   - otherwise → plain words: "You have a GitHub invitation waiting. Open
     https://github.com/pretendhome/mission-canvas/invitations logged in as
     **DontWriteDown** and click Accept." Re-check after she says done.
3. Still failing → continue testing anyway; hold the report locally at the end
   and tell her to send it to Mical. Never fork, never open public PRs.

### STEP 1 — What are we testing?

Ask: **"What are you testing today?"** Default = the full packet: read
`QA_TESTING_PLAN.md` in this folder (`qa/teacher-readiness-packet/`) — its "Note to the harness"
section is addressed to YOU. Tonight's run is the pre-rollout full pass:
56 checks, scenarios S then A→M. If she's short on time, priority order is:
**S, I (safeguarding), J (parent), C, D, H** — then the rest.

### STEP 2 — Fresh reference repos (you already have the first one)

Her local repos are ALWAYS out of date. Fresh clone or `git pull --rebase`:
- `lingua-viva/learning-architecture` (public) — you cloned/updated it to
  read this file. THE TEST PACKET IS `qa/teacher-readiness-packet/` INSIDE
  THIS CLONE — the plan, and the `documents/` files she uploads to Drive
  (open that folder in Finder for her when a scenario needs them). Also your
  reference for tracing bugs.
- `pretendhome/mission-canvas` — where the report gets pushed.
Record both HEAD hashes for the report. The app under test is NOT run from
the repo — only ever from the installed download.

### STEP 3 — Fresh app install (her standing workflow) — THIS IS A TEST, NOT JUST SETUP

1. Have her drag any existing Lingua Viva app to the Trash.
2. Have her download from **linguaviva.art** (the site button, NOT GitHub),
   install, open.
3. Record the exact version (About screen / health endpoint / logs).
   Expected: **desktop-v0.2.51 or newer** (a fix release may have landed
   tonight). Older than the latest release tag = P1 finding; keep testing.
4. **Context you must know**: today a Linux fresh-install of v0.2.50 failed
   with `ModuleNotFoundError: No module named 'fastapi'` — the packaged
   backend's dependency setup failed silently (finding D1-P0-001). Chip's Mac
   is the missing platform data point. Her machine has run LV before, so her
   Python user-site may already have the dependencies — meaning a PASS here
   does NOT fully clear the Mac fresh-install path. Note in the report
   whether `python3 -c "import fastapi"` already worked on her machine
   BEFORE the app's setup ran, so we know what her pass/fail actually proves.

### STEP 4 — Observability before testing

- Create `qa-sessions/lingua-viva-<date-time>/` in her home or Downloads.
- Find and tail the desktop app's logs → `app.log` in the session folder.
  Likely spots on Mac: `~/.lingua-viva/logs/`, `~/Library/Application
  Support/`, `~/Library/Logs/`, Console.app.
- Start `events.log`: timestamps for startup, errors, warnings, failed
  requests, health results, and everything she reports.
- Note launch method, URL (usually http://127.0.0.1:8787), versions.

### STEP 5 — Health check

Poll the app's health endpoint until it responds.
- Healthy → tell her "The app is running and healthy" + the URL.
- Won't come up → this is the D1-P0-001 hunt. BEFORE anything else:
  1. Save the full backend log (the traceback especially) into the session
     folder.
  2. Note the setup wizard's exact on-screen wording (or that it said
     nothing).
  3. Note whether Retry setup changes anything.
  4. Write and publish a SHORT P0 report immediately (Steps 8–9 format,
     abbreviated) — a Mac repro of the fresh-install failure is the most
     valuable possible outcome of the night.
  Then, and only then: you may check whether installing the missing Python
  packages on her machine gets the app up, so the rest of the packet can
  still run — record clearly in the report that the remaining checks ran on
  a hand-repaired environment, not a true fresh install.

### STEP 6 — Walk her through the packet, ONE STEP AT A TIME

Use `QA_TESTING_PLAN.md` (S, then A→M) as the script. For EACH step:
- Tell her exactly where to go and what to do ("Step 3 of 5: ...").
- Anything she must say or type goes on its own marked line:
      PASTE THIS:
      Marco helped a classmate find the right page during reading
- Tell her what pass looks like and what counts as wrong.
- STOP and wait for "done" or her description.
- Number steps so she knows how many are left.

Where the plan says the harness calls an API (E, G, K, and parts of I/J), run
the curl yourself (openapi.json first for new endpoints), save outputs as
files in the session folder, show her the content to judge. Feature clearly
absent → "NOT IN THIS BUILD (version X)", move on.

**Scenario I special handling**: after check 37 (the concerning phrase), you
verify the restricted routing yourself — confirm via API/log evidence that
the observation was flagged and routed, confirm the teacher-identity denial
on `/api/safeguarding/restricted` (check 41), and at the end grep every
generated artifact from the session for the concerning content (check 42).
Chip judges what she can SEE; you verify what she can't.

### STEP 7 — Watch while she tests

Keep checking health and logs quietly. Timestamp notable events. Only speak
up if something clearly broke — one plain sentence, then keep going. Write
down everything she reports, verbatim, with timestamps. Trace problems to
files in the clean clone and note locations in the report.

### STEP 8 — When she says "done"

Collect her manual feedback one question at a time (UX Feedback Template in
the plan — including the new question 5: would she hand this to Claudia's
teachers tomorrow?).

Then write `<date>_lingua-viva-teacher-readiness.md` combining:
1. Versions: app version, both repo HEADs, whether the install was a true
   fresh install or hand-repaired (Step 5), whether fastapi pre-existed
   (Step 3.4).
2. Plain-language summary + P0/P1 counts + a one-line "ready for teachers
   tomorrow: yes/no/with-fixes" verdict.
3. The S→M checklist: pass / fail / not-in-build / note per check (all 56
   accounted for).
4. "Manual QA feedback (Chip's notes)" — her answers, in her words.
5. Feature requests (separate from bugs).
6. Technical appendix: errors with timestamps, likely file/area per issue,
   key log excerpts, launch info, environment.

### STEP 9 — Publish to the QA repo

Publish to `pretendhome/mission-canvas` (clean clone from Step 2):
- `qa/<date>_lingua-viva-teacher-readiness.md` — the report
- `qa/traces/` — app.log, events.log, API outputs
- `qa/screenshots/` — any screenshots
- ONLY ever touch `qa/`. Stage explicit paths. NEVER `git add -A` / `git add .`.
- Commit: `qa: <date> lingua-viva teacher readiness`, push to main.
- Pre-push hook blocks anything outside `qa/` — if blocked, you touched too
  much; undo, keep only `qa/`, push again. Never bypass the hook.
- Push denied (Step 0 unresolved) → keep local, tell her where the file is.
- Success → "Report published" + the repo path.

Start now with STEP 0.

---

## If Claude ever gets stuck (for Chip)

- Technical question you don't understand? Reply: **"You decide — do what's most standard."**
- Stuck more than 2 minutes? Write down what happened and text Mical.
- Nothing here touches a real account or real student — you're always safe to
  close the terminal to stop everything.
