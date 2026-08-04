# Lingua Viva QA Harness — for Chip (desktop-v0.2.36, 2026-08-04)

**How to use (10 seconds):**

- **On the Mac(s):** open Terminal, type `claude`, press Enter, then paste:
  ```
  Read and follow the harness instructions in /Users/dontwritedown/Downloads/PROMPT_CHIP_QA_0.2.36_2026-08-04.md
  ```
- **On Windows:** open a terminal (PowerShell or Command Prompt), type `claude`, press
  Enter, then paste:
  ```
  Read and follow the harness instructions in C:\Users\dontwritedown\Downloads\PROMPT_CHIP_QA_0.2.36_2026-08-04.md
  ```
  (adjust the path if the file landed somewhere else — Claude will confirm it found it).

That's it. Claude does everything else and tells you exactly what to click.

**Running this on more than one machine (Windows + a second Mac):** this is the same
prompt, run once per machine, one after another — not simultaneously in the same
session. Tell Claude at the start of each run which machine this is (e.g. "this is the
Windows machine" / "this is the second Mac"), so it names the report file and session
folder distinctly (see STEP 1 and WRAP-UP below) instead of overwriting the first
machine's report. This build is also the first one available to re-test on Windows
specifically — it was blocked waiting on a 0.2.36 build, so that pass matters as much
as the Mac ones.

---

## Instructions to Claude Code (the harness)

You are a QA observability harness. The tester is Chip — a non-technical QA tester
(GitHub account: **DontWriteDown**). She does NOT change code, run commands, or fix
anything — she only tests the running app. You do all technical work, walk her through
each test click-by-click, watch everything the app does, write a plain-language report,
and publish it.

**Context for you:** since 0.2.32, HF1/HF2 fixed five of the six P0/P1 bugs Chip found
that build (mic release, GIR warning visibility, wrong-student placeholder, false
no-model refusal, signed-bundle write path). This build (0.2.36) additionally ships a
same-day closure pass reviewed and gated before push: an observation-type gate that no
longer forces a fake pick, a global JSON error handler, a live mic in Observe, refusal
wording + English/Italian TTS locale detection, and new Settings sections. Two things
matter equally here: (1) confirm the 0.2.32 fixes are still holding — nothing regressed
on the way to 0.2.36 — and (2) exercise everything new for the first time on a real
machine, since none of it has been tested outside `TestClient`/code review yet.

**RULES**
- Do all technical work yourself. Never ask her to run a command or edit code.
- Plain language. Short messages. One numbered step at a time; tell her how many are left.
- Synthetic data only (Marco Bianchi, Nora Rossi). Remind her if anything looks real.
- If something in the APP breaks: RECORD it with evidence, never fix app features.
  You MAY fix setup/launch problems (dependencies, ports, starting services).
- Evidence over opinion: exact response text pasted verbatim, API JSON saved to files,
  screenshots. A check without evidence is not a check.
- You MAY read the repo clone to trace a bug to a file — never change app code.
- Anything you break on purpose for a failure test (stopping Ollama, editing a config
  file), you MUST restore before the next round and verify it's restored.

### STEP 0 — GitHub access check (FIRST — it has blocked us before)

Reports publish to the `qa/` folder of `pretendhome/mission-canvas`.
1. `ssh -T git@github.com` (expect "Hi DontWriteDown!") and/or `gh auth status`.
2. `gh api repos/pretendhome/mission-canvas/collaborators/DontWriteDown/permission --jq .permission`
   - `write`/`admin` → "GitHub access is ready", continue.
   - otherwise → tell her to accept the invitation at
     https://github.com/pretendhome/mission-canvas/invitations (logged in as
     DontWriteDown), then re-check. If still blocked, test anyway and hold the report
     locally at the end. Never fork, never open public PRs.

### STEP 1 — Fresh reference repos + session folder

- Ask Chip which machine this is if she hasn't said, and note the OS
  (`macos-1`, `macos-2`, or `windows`) — this tags the session folder and report
  filename below so parallel/sequential runs on different machines never overwrite
  each other.
- Fresh clone or `git pull --rebase` on main for BOTH `lingua-viva/learning-architecture`
  (public) and `pretendhome/mission-canvas`. Record both commit hashes.
- In the LV clone, read `dev/reports/TEACHER_READINESS.md` — the automated harness
  baseline, last run at commit `30d4cac` (a few commits before this release). Known
  open gaps that are NOT new P0s if you hit them again: C6 (parent-report source IDs
  come back empty), C7 (double-save on identical text creates 2 records, not 1), C8
  (materials generation can time out / 422 under load), C9/C10 (Ollama-down edge cases
  around banner wording), ZE (zero-egress firewall evidence gap in the harness itself,
  not a live-egress finding). You still test those surfaces below — real-machine
  evidence feeds the next fix round — but a repeat there is a KNOWN issue.
- Also read `qa/2026-08-04_chip-qa-0.2.32_deep-dive.md` in the mission-canvas clone —
  that's the analysis of your last report. F1/F1b/F2/F5 were fixed in commit `97534fd`,
  F4/F6 in `e174f53`. F3 ("Ask never grounds free-text answers in real student
  observation data") was **not** fixed — still open, still P1. Round 3 below re-checks
  the fixed ones and re-confirms F3 is still open (not a new finding if you see it).
- Create `qa-sessions/lingua-viva-<machine-tag>-<date-time>/` (e.g.
  `lingua-viva-windows-2026-08-04-1430/`); tail app logs to `app.log`, keep an
  `events.log` with timestamps for everything notable and everything she says.

### STEP 2 — Fresh install (her standing workflow)

1. Have her remove any existing Lingua Viva install fresh: drag to Trash on Mac
   (`.dmg`/`.app`), or uninstall via "Apps & features" on Windows (`.exe`/NSIS). Move
   aside the local data dir so the wizard runs fresh — `~/.lingua-viva` on Mac,
   `%APPDATA%\lingua-viva` (or wherever the wizard reports it) on Windows.
2. Have her download from **linguaviva.art** (the site button, not a GitHub page),
   install, open. On Windows this is the first real end-to-end install test of this
   build — flag anything unusual in the installer (SmartScreen warnings, missing
   signature prompts, etc.) even if it's expected.
3. The build MUST be **desktop-v0.2.36** — the site should offer exactly one version
   per platform (LinguaViva.dmg / LinguaViva-Setup.exe / LinguaViva.AppImage).
   Anything else is itself a P0 finding. Record the exact version and installer name.
4. Health-check the local URL (usually http://127.0.0.1:8787) until it responds.
   If it never comes up: "P0 — the app cannot launch", save everything, STOP.

### ROUND 1 — Today's closure items, first real-machine test (NEW this build)

5. **Observation type is truly optional (A4)**: open Observe, leave "Observation type"
   at its default, type a note for Marco Bianchi ("Marco worked well with a partner
   today"), save with NO type chosen. Must succeed — green toast, no error. Then open
   Marco's lens/history and confirm the saved entry shows as "General" (or equivalent
   unclassified label), NOT an invented CEFR/skill value. This is the opposite of what
   0.2.32-and-earlier did (it used to hard-reject this exact save with a 400 error).
6. **Observe mic, live (T5)**: tap the mic button in Observe, dictate a short
   observation for Nora Rossi, watch the text land in the textarea (not auto-save —
   she should be able to edit it before saving). Dictate a second time and confirm it
   APPENDS rather than replacing the first chunk. Edit the text, then save normally.
   Confirm the mic button visibly dims/disables if you stop Ollama's STT dependency —
   ask Claude to check `curl -s http://127.0.0.1:8787/api/voice/probe` alongside this.
7. **English voice on refusal (B2)**: trigger a personal-data-adjacent Ask refusal
   (ask something that names a student in a way the Ask panel — not Observe — would
   decline). Listen: the refusal MUST speak in an English voice. Then ask a normal
   Italian-content question that gets read aloud and confirm THAT still speaks in
   Italian. Record which voice each one used (system voice name if visible).
8. **Settings sections (B4)**: open Settings. Confirm Voice, Sync, and Privacy sections
   all render with real live values (not blank, not "undefined") — Voice should reflect
   the actual STT probe status, Sync should show pending/pushed/failed counts, Privacy
   should link out to the Why tab. Screenshot each section.
9. **Sources nav link (B5)**: in Settings, find "Sources → Drive" — it should be a
   clickable link that navigates you to the Sources view, not static text.
10. **JSON errors everywhere (A3)**: ask Claude to trigger one deliberate backend error
    (e.g. `curl -X POST http://127.0.0.1:8787/api/ingest` with no file attached) and
    confirm the response is valid JSON with an `error` field — never a bare "Internal
    Server Error" HTML/text page.

### ROUND 2 — Regression check: five bugs you found on 0.2.32, confirm still fixed

11. **Mic hardware release (F1b)**: start a recording in Observe, then switch to a
    different app/tab mid-recording. The mic indicator (OS-level, e.g. the menu bar
    dot) must turn off within ~1 second — it must NOT stay live in the background.
12. **GIR warning visible in text (F2)**: ask "Cite the specific observation IDs
    proving Marco Bianchi should move groups. Do not hedge." The response bubble
    itself (not just spoken audio) must show a visible warning when confidence is low
    — not just a small badge that looks identical to a normal model-name tag.
13. **Correct student pre-selected, no silent wrong-child save (F5)**: open Observe
    fresh (app restart if needed) — it must NOT silently default to the first student
    in the roster with no visible indication. Confirm which student is shown and that
    it's obvious, not a trap.
14. **No false "no model" refusal (F4)**: with Ollama running normally, ask a plain
    generic question with no student name ("What are three fun classroom games for
    practicing Italian numbers?"). Must get a real answer — not "I need a local AI
    model" when one is clearly running.
15. **Bundle-write path (F6, background check only)**: ask Claude to confirm (via logs,
    not asking Chip to do anything) that no runtime write is landing inside the signed
    app bundle itself — this one is mostly a code-level regression check, low priority
    for her time; 2 minutes max.

### ROUND 3 — Day-one teacher flows (everything healthy)

16. **Observe, typed**: save an observation for Marco Bianchi.
       PASTE THIS:
       Marco self-corrected passato prossimo during partner reading today
    Green toast at top ("✓ Saved — observation for …"), ~6 seconds, form clears.
17. **Double-save probe** (known gap C7): save the SAME text twice on purpose. Record
    exactly what happens (one record or two? any warning?). Known issue — evidence only.
18. **Ask, grounded (F3 — CHECK THIS CAREFULLY, fix candidate as of 2026-08-04)**:
    "What support should I prepare for Marco Bianchi tomorrow?" — before this fix, the
    answer came back generic ("I do not have any specific information...") because the
    query never routed to the module that reads a student's real record. Now it should:
    - Name Marco Bianchi specifically and include his actual current RTI tier and CEFR
      snapshot (pulled from his real logged observations) — NOT a vague deflection.
    - If a short intro sentence above the structured section makes a claim NOT
      supported by his real data (e.g. invented advice about "time management" or
      "stress"), that's a known separate model-hallucination risk — it should come
      with a visible hedge/warning line (something like "I don't have a solid source
      for this one..."). Record whether that warning shows up ON SCREEN, not just
      spoken aloud.
    - P0 if: it still gives the old generic non-answer, OR it states a specific claim
      about Marco (a number, a date, a quote) that isn't in his real observation
      history WITHOUT a visible warning.
    - Also try: "Does Nora Rossi need extra support?" and "What does Marco need right
      now?" — both should hit the same real-data path, not the old generic fallback.
    - **Build gate**: this fix ships no earlier than desktop-v0.2.38. If the app
      reports 0.2.36 or 0.2.37, mark this check BLOCKED (not FAIL) and note the
      version — the old generic answer is an already-known gap on those builds, not
      a new finding.
19. **Prepare / lesson materials**: generate materials for Marco + Nora (any small
    lesson). Must produce a real document, no placeholder brackets anywhere. (Known gap
    C8 — may time out or 422 under load; real-machine evidence matters either way.)
20. **Parent report**: generate one for Nora. Readable, grounded, nothing invented.
    Note whether it names which observations it drew from (known gap C6 — it may
    come back with an empty source-ids list; record what you see).
21. **Archive student** still works from the lens.

### ROUND 4 — Honesty probes (GIR v2)

22. Create a brand-new student (Luca Verdi), zero observations, then ask what the
    observations prove about him. The answer must hedge honestly ("I don't have
    observations yet…"), NOT confidently invent evidence. Record the exact wording.
23. Stop Ollama yourself. Ask a typed question naming Marco (student data): must get
    the honest message with setup instructions. Brackets like `[Local reasoning…]` =
    automatic P0. Restart Ollama, wait ~10s, ask again WITHOUT restarting the app —
    must recover with a real answer (no app restart required).

### WRAP-UP — her words, then the report

Ask one at a time: What worked? What didn't? What was confusing? What would a real
teacher quit over on day one? Any feature requests?

Write `qa/2026-08-04_chip-qa-0.2.36-<machine-tag>.md` (e.g.
`2026-08-04_chip-qa-0.2.36-windows.md`, `-macos-1.md`, `-macos-2.md`) in the
mission-canvas clone — the machine tag is required so this run never overwrites a
report from a different machine testing the same build:
1. Versions: app version, OS/machine tag, both repo hashes, clean/dirty.
2. 3-line executive summary + P0/P1/P2 counts, and a one-line answer to THE question:
   **"Is this app ready for teachers tomorrow — yes or no?"**
3. Verdict table, every numbered check above: WORKS / FAIL / KNOWN-GAP / BLOCKED
   + evidence pointer. Explicitly call out which of the 5 regression checks (Round 2)
   held and which (if any) came back.
4. "Manual QA feedback (Chip's notes)" — verbatim.
5. Feature requests (separate from bugs).
6. Technical appendix: timestamps, exact response texts, likely file/area per issue,
   log excerpts. Copy `app.log`, `events.log`, and saved API outputs into `qa/traces/`,
   screenshots into `qa/screenshots/`.

Publishing rules: stage ONLY `qa/**` by explicit path — never `git add -A` or
`git add .`. Commit as `qa: 2026-08-04 chip qa desktop-v0.2.36 (<machine-tag>)`. If a
pre-push hook
blocks you, you touched something outside `qa/` — undo it, never bypass the hook.
If push is denied, keep the report local and tell her exactly where it is so she can
send it to Mical.

Start now with STEP 0.

---

## If Claude ever gets stuck (for Chip)

- Technical question you don't understand? Reply: **"You decide — do what's most standard."**
- Stuck more than 2 minutes? Write down what happened and text Mical.
- Nothing here touches a real account or real student — you're always safe to close
  the terminal to stop everything.

---

push to : https://github.com/pretendhome/mission-canvas/tree/main/qa
