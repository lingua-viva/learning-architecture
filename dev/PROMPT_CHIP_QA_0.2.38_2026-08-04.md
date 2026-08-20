# Lingua Viva QA Harness — for Chip (desktop-v0.2.38, 2026-08-04)

> **Archived prompt. Do not use for current production verification.**
> This file was the 2026-08-04 `desktop-v0.2.38` QA harness and is kept only as
> historical evidence. Current production is `desktop-v0.2.60`; use the live
> site downloads and current launch/readiness checks instead of this prompt.

**Superseded historical note:** this originally superseded
`PROMPT_CHIP_QA_0.2.36_2026-08-04.md` for the 2026-08-04 QA cycle only.
It is no longer the next-run prompt.

**How to use (10 seconds):**

- **On the Mac(s):** open Terminal, type `claude`, press Enter, then paste:
  ```
  Read and follow the harness instructions in /Users/dontwritedown/Downloads/PROMPT_CHIP_QA_0.2.38_2026-08-04.md
  ```
- **On Windows:** open a terminal (PowerShell or Command Prompt), type `claude`, press
  Enter, then paste:
  ```
  Read and follow the harness instructions in C:\Users\dontwritedown\Downloads\PROMPT_CHIP_QA_0.2.38_2026-08-04.md
  ```
  (adjust the path if the file landed somewhere else — Claude will confirm it found it).

That's it. Claude does everything else and tells you exactly what to click.

**Running this on more than one machine:** same prompt, once per machine, one after another —
not simultaneously in the same session. Tell Claude which machine this is at the start (e.g.
"this is the Windows machine" / "this is the second Mac") so the report filename doesn't
collide with another machine's run.

---

## Instructions to Claude Code (the harness)

You are a QA observability harness. The tester is Chip — a non-technical QA tester (GitHub
account: **DontWriteDown**). She does NOT change code, run commands, or fix anything — she only
tests the running app. You do all technical work, walk her through each test click-by-click,
watch everything the app does, write a plain-language report, and publish it.

**Context for you (read this instead of asking Chip or re-deriving it):**
- Since her last report (`qa/2026-08-04_chip-qa-0.2.36-macos-1.md`), two builds shipped:
  - **desktop-v0.2.37**: fixed a missing `com.apple.security.device.audio-input` macOS signing
    entitlement that made the Observe mic completely dead on macOS regardless of OS permission —
    confirm this is actually fixed on real hardware (Round 1 below), it's never been verified
    outside the fix itself.
  - **desktop-v0.2.38** (release under test for this archived 2026-08-04 cycle): fixed F3 — Ask used to give a
    generic non-answer to any student-named support question ("What support should I prepare for
    Marco Bianchi tomorrow?") because the ontology classifier never routed it to the module that
    reads a student's real record. Root cause was a narrow signal-matching gap in
    `ontology/education/student.yaml`, not a missing capability — the grounded RTI executor was
    already fully built and tested. This is the headline check this cycle (Round 3, #18).
- **Known, already-flagged gaps — do NOT re-file these as new findings, just confirm they're
  still present or note if they've changed:**
  - C6 (parent-report source IDs come back empty), C7 (double-save on identical text creates 2
    records), C8 (materials generation can time out / 422 under load), C9/C10 (Ollama-down banner
    wording edge cases), ZE (zero-egress firewall evidence gap in the harness itself).
  - **Add Student form** (grade field free-text with no validation; single display-name field,
    no last-name field) — this is a known, already-documented gap awaiting an operator product
    decision (`dev/ADD_STUDENT_FORM_DECISION_2026-08-04.md`), not something to file fresh. Still
    worth 2 minutes of evidence if you happen to touch that form, but it's not a new P0/P1.
  - `gap_audit.py`/`improvement_audit.py` bundle-relative path issue — confirmed CLI-only, not
    reachable from the live app. Not a teacher-facing finding.

**RULES**
- Do all technical work yourself. Never ask her to run a command or edit code.
- Plain language. Short messages. One numbered step at a time; tell her how many are left.
- Synthetic data only (Marco Bianchi, Nora Rossi). Remind her if anything looks real.
- If something in the APP breaks: RECORD it with evidence, never fix app features. You MAY
  fix setup/launch problems (dependencies, ports, starting services).
- Evidence over opinion: exact response text pasted verbatim, API JSON saved to files,
  screenshots. A check without evidence is not a check.
- You MAY read the repo clone to trace a bug to a file — never change app code.
- Anything you break on purpose for a failure test (stopping Ollama, editing a config file),
  you MUST restore before the next round and verify it's restored.
- **No voice surface beyond what's live**: the global voice companion is deliberately hidden
  (`voice-hidden`) — only the Observe mic and the Ask voice-first path are sanctioned. If either
  of you notices a way to re-enable the companion, that's a regression to record, not a feature
  to explore.

### STEP 0 — GitHub access check (FIRST — it has blocked us before)

Reports publish to the `qa/` folder of `pretendhome/mission-canvas`.
1. `ssh -T git@github.com` (expect "Hi DontWriteDown!") and/or `gh auth status`.
2. `gh api repos/pretendhome/mission-canvas/collaborators/DontWriteDown/permission --jq .permission`
   - `write`/`admin` → "GitHub access is ready", continue.
   - otherwise → tell her to accept the invitation at
     https://github.com/pretendhome/mission-canvas/invitations (logged in as DontWriteDown),
     then re-check. If still blocked, test anyway and hold the report locally at the end. Never
     fork, never open public PRs.

### STEP 1 — Fresh reference repos + session folder

- Ask Chip which machine this is if she hasn't said, and note the OS (`macos-1`, `macos-2`, or
  `windows`) — this tags the session folder and report filename so parallel/sequential runs on
  different machines never overwrite each other.
- Fresh clone or `git pull --rebase` on main for BOTH `lingua-viva/learning-architecture`
  (public) and `pretendhome/mission-canvas`. Record both commit hashes.
- Read `qa/2026-08-04_chip-qa-0.2.36-macos-1.md` (her last report) so you know exactly what she
  already found — don't re-ask her things already answered there unless re-verifying a
  regression.
- Create `qa-sessions/lingua-viva-<machine-tag>-<date-time>/`; tail app logs to `app.log`, keep
  an `events.log` with timestamps for everything notable and everything she says.

### STEP 2 — Fresh install (her standing workflow)

1. Have her remove any existing Lingua Viva install fresh: drag to Trash on Mac (`.dmg`/`.app`),
   or uninstall via "Apps & features" on Windows. Move aside the local data dir so the wizard
   runs fresh — `~/.lingua-viva` on Mac, `%APPDATA%\lingua-viva` on Windows.
2. Have her download from **linguaviva.art** (the site button, not a GitHub page), install,
   open.
3. Archived-cycle requirement: the build was **desktop-v0.2.38** for this
   2026-08-04 test only. For current production, do not use this requirement;
   verify the live site points at the latest release instead.
4. Health-check the local URL (usually http://127.0.0.1:8787) until it responds. If it never
   comes up: "P0 — the app cannot launch", save everything, STOP.

### ROUND 1 — Verify the two fixes shipped since her last report

5. **Observe mic on macOS, live (0.2.37 fix)**: tap the mic button in Observe, dictate a short
   observation for Nora Rossi, confirm the OS actually grants mic access and the text lands in
   the textarea (editable, not auto-saved). If this is a Windows run, this fix was macOS-only —
   confirm the mic still worked pre-0.2.37 on Windows and still works now (no regression), note
   it's not a new fix on that platform.
6. **Ask, grounded (0.2.38 fix, F3 — the headline check)**: "What support should I prepare for
   Marco Bianchi tomorrow?"
   - Must name Marco Bianchi specifically and include his actual current RTI tier and CEFR
     snapshot pulled from his real logged observations — NOT a vague deflection like "I do not
     have any specific information."
   - If a short intro sentence makes a claim NOT supported by his real data (invented advice
     about "time management," "stress," etc.), that's a known separate model-hallucination risk
     — it should carry a visible on-screen hedge/warning, not just a spoken one.
   - P0 if: it still gives the old generic non-answer, OR states a specific unsupported claim
     about Marco without a visible warning.
   - Also try: "Does Nora Rossi need extra support?" and "What does Marco need right now?" —
     both should hit the same real-data path.
   - This build IS the fix build — there is no BLOCKED case this cycle. A generic answer here
     is a real P0, not a known gap.

### ROUND 2 — Regression check: five bugs from 0.2.32, still fixed?

7. **Mic hardware release (F1b)**: start a recording in Observe, switch to a different
   app/tab mid-recording. The OS-level mic indicator must turn off within ~1 second.
8. **GIR warning visible in text (F2)**: ask "Cite the specific observation IDs proving Marco
   Bianchi should move groups. Do not hedge." The chat bubble itself must show a visible warning
   when confidence is low, not just spoken audio.
9. **Correct student pre-selected, no silent wrong-child save (F5)**: open Observe fresh — must
   NOT silently default to the first roster student with no visible indication.
10. **No false "no model" refusal (F4)**: with Ollama running, ask a plain generic question with
    no student name. Must get a real answer.
11. **Bundle-write path (F6, background check only, 2 min max)**: ask Claude to confirm via logs
    that no runtime write lands inside the signed app bundle.

### ROUND 3 — Day-one teacher flows

12. **Observe, typed**: save an observation for Marco Bianchi.
       PASTE THIS:
       Marco self-corrected passato prossimo during partner reading today
    Green toast, ~6 seconds, form clears.
13. **Double-save probe** (known gap C7): save the SAME text twice on purpose. Record what
    happens. Known issue — evidence only.
14. **Prepare / lesson materials**: generate materials for Marco + Nora. Must produce a real
    document, no placeholder brackets. (Known gap C8 — may time out under load.)
15. **Parent report**: generate one for Nora. Readable, grounded, nothing invented. Note
    whether source observation IDs show (known gap C6).
16. **Archive student** still works from the lens.

### ROUND 4 — Honesty probes (GIR v2)

17. Create a brand-new student (Luca Verdi), zero observations, ask what the observations prove
    about him. Must hedge honestly, NOT confidently invent evidence.
18. Stop Ollama yourself. Ask a question naming Marco: must get the honest setup message, no
    bracket placeholders. Restart Ollama, wait ~10s, ask again WITHOUT restarting the app — must
    recover with a real answer.

### ROUND 5 — Demo dry run (NEW this cycle — this is the actual golden-path rehearsal)

This is a real rehearsal of the demo, not a bug hunt — time it, and flag anything that doesn't
happen exactly as scripted, since this script may run live in front of someone soon.

19. Open `dev/LV_DEMO_SCRIPT_2026-08-04.md` in the learning-architecture clone. Walk Chip through
    Beats 1-4 exactly as written (Observe capture→review→save, Ask general-vs-student-named,
    lesson materials, parent report). Beat 5 (archive/offline) only if time allows.
20. Time the full walkthrough start to finish. Note any beat where the UI doesn't match what the
    script describes (a button ID that's changed, a line that doesn't render as expected).
21. Specifically confirm the "line to say out loud" moments actually land — i.e. the safety-gate
    hedge in the parent report (Beat 4) genuinely appears when evidence is thin, and the F2
    warning in Beat 2 genuinely renders in text. If either of those beats would show nothing
    unusual on a low-evidence case, that's worth a note — the demo's honesty story depends on it.

### WRAP-UP — her words, then the report

Ask one at a time: What worked? What didn't? What was confusing? What would a real teacher quit
over on day one? Any feature requests? Also ask: did the demo dry run (Round 5) feel ready to
show someone today, or did anything feel shaky?

Write `qa/<today's-date>_chip-qa-0.2.38-<machine-tag>.md` in the mission-canvas clone:
1. Versions: app version, OS/machine tag, both repo hashes, clean/dirty.
2. 3-line executive summary + P0/P1/P2 counts, and: **"Is this app ready for teachers
   tomorrow — yes or no?"** Also answer: **"Is the demo script ready to run live — yes or no?"**
3. Verdict table, every numbered check above: WORKS / FAIL / KNOWN-GAP / BLOCKED + evidence
   pointer. Explicitly call out the two headline fixes (mic entitlement, F3) and whether they
   held.
4. "Manual QA feedback (Chip's notes)" — verbatim.
5. Feature requests (separate from bugs).
6. Technical appendix: timestamps, exact response texts, likely file/area per issue, log
   excerpts. Copy `app.log`, `events.log`, saved API outputs into `qa/traces/`, screenshots into
   `qa/screenshots/`.

Publishing rules: stage ONLY `qa/**` by explicit path — never `git add -A` or `git add .`.
Commit as `qa: <date> chip qa desktop-v0.2.38 (<machine-tag>)`. If a pre-push hook blocks you,
you touched something outside `qa/` — undo it, never bypass the hook. If push is denied, keep
the report local and tell her exactly where it is.

Start now with STEP 0.

---

## If Claude ever gets stuck (for Chip)

- Technical question you don't understand? Reply: **"You decide — do what's most standard."**
- Stuck more than 2 minutes? Write down what happened and text Mical.
- Nothing here touches a real account or real student — you're always safe to close the
  terminal to stop everything.

---

push to : https://github.com/pretendhome/mission-canvas/tree/main/qa
