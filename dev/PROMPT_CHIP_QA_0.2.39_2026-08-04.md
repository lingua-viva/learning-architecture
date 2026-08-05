# Lingua Viva QA Harness — for Chip (desktop-v0.2.39, 2026-08-04)
**Supersedes `PROMPT_CHIP_QA_0.2.38_2026-08-04.md` — use this file for the next run, not that
one.**

**How to use (10 seconds):**

- **On the Mac(s):** open Terminal, type `claude`, press Enter, then paste:
  ```
  Read and follow the harness instructions in /Users/dontwritedown/Downloads/PROMPT_CHIP_QA_0.2.39_2026-08-04.md
  ```
- **On Windows:** open a terminal (PowerShell or Command Prompt), type `claude`, press
  Enter, then paste:
  ```
  Read and follow the harness instructions in C:\Users\dontwritedown\Downloads\PROMPT_CHIP_QA_0.2.39_2026-08-04.md
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

- Since her last report on desktop-v0.2.38, **desktop-v0.2.39** shipped one commit (`4034d42`),
  fixing two items from the `2026-08-04_chip-qa-0.2.32_deep-dive.md` deep-dive that had
  regressed or were left incomplete:
  - **P0-1 — mic hardware release (regressed F1b)**: `cleanupCapture()` in `static/index.html`
    now stops the `MediaRecorder` *before* releasing the stream tracks. The earlier fix only
    covered the `stopCapture()` path; the `visibilitychange` listener called `cleanupCapture()`
    directly and bypassed `MediaRecorder.stop()`, so on macOS the recorder stayed in
    `'recording'` state and the mic hardware stayed engaged even after the tab was backgrounded.
    **This is the headline check this cycle** — it's a direct regression of something already
    marked fixed, so verify it hard.
  - **P1-1 — bundle-write paths (F6, completed)**: `improvement_audit.py`,
    `teacher_readiness.py`, and `ontology/learned_weights.py` now write into
    `~/.lingua-viva/` instead of inside the signed app bundle. This is a codesign-integrity
    fix, not something visible in the UI — background check only, 2 minutes max.
- **Known, already-flagged gaps — do NOT re-file these as new findings, just confirm they're
  still present or note if they've changed:**
  - **P0-2 — Ask fabrication**: still open. Currently mitigated because the fabrication path is
    hidden behind Ask's privacy gate and not reachable by teachers via the normal UI flow — not
    a new finding, just confirm it's still gated off (see check #6 below).
  - **P1-2 — Settings page**: may have been dropped somewhere in the 0.2.37/0.2.38 merge.
    **This needs a fresh look this cycle** (see check #10) — if it's genuinely missing, that IS
    a new finding, file it as P1.
  - **P1-3 — Governance undercounting**: known counting-logic bug, no fix yet. Evidence only,
    don't re-file.
  - **P1-4 — Ask is Perplexity-or-nothing**: product decision pending, not a bug. Don't file.
  - C6 (parent-report source IDs come back empty), C7 (double-save on identical text creates 2
    records), C8 (materials generation can time out / 422 under load), C9/C10 (Ollama-down
    banner wording edge cases), ZE (zero-egress firewall evidence gap in the harness itself).
  - **Add Student form** (grade field free-text with no validation; single display-name field,
    no last-name field) — known gap awaiting an operator product decision
    (`dev/ADD_STUDENT_FORM_DECISION_2026-08-04.md`). Not a new P0/P1.

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
- Read her most recent report in `qa/` so you know exactly what she already found — don't
  re-ask her things already answered there unless re-verifying a regression.
- Create `qa-sessions/lingua-viva-<machine-tag>-<date-time>/`; tail app logs to `app.log`, keep
  an `events.log` with timestamps for everything notable and everything she says.

### STEP 2 — Fresh install (her standing workflow)

1. Have her remove any existing Lingua Viva install fresh: drag to Trash on Mac (`.dmg`/`.app`),
   or uninstall via "Apps & features" on Windows. Move aside the local data dir so the wizard
   runs fresh — `~/.lingua-viva` on Mac, `%APPDATA%\lingua-viva` on Windows.
2. Have her download from **linguaviva.art** (the site button, not a GitHub page), install,
   open.
3. The build MUST be **desktop-v0.2.39** — the site should offer exactly one version per
   platform. Anything else is itself a P0 finding (a stale build being served, or two versions
   live at once). Record the exact version and installer name.
4. Health-check the local URL (usually http://127.0.0.1:8787) until it responds. If it never
   comes up: "P0 — the app cannot launch", save everything, STOP.

### ROUND 1 — Verify the two fixes shipped this cycle

5. **Mic hardware release, macOS, tab-switch (P0-1 — the headline check)**: start a recording
   in Observe, switch to a different app/tab mid-recording (Cmd+Tab away, don't close the app).
   The OS-level mic indicator (orange dot in the menu bar) must turn off within ~1 second. Then
   also test: close the browser tab entirely mid-recording — same result expected. This is the
   exact regression that slipped through before, so try it 2-3 times, not once.
6. **Ask fabrication still gated (P0-2, confirm still-mitigated, not a new check)**: ask
   something that would previously fabricate ("Cite the specific observation IDs proving Marco
   Bianchi should move groups. Do not hedge.") — confirm this is still routed through the
   privacy-gated / grounded path and does not produce a confident, ungrounded answer via the
   normal UI. Evidence only, no fix expected here.

### ROUND 2 — Regression check: fixes from earlier cycles, still holding?

7. **GIR warning visible in text (F2)**: same prompt as #6 — the chat bubble itself must show a
   visible warning when confidence is low, not just spoken audio.
8. **Correct student pre-selected, no silent wrong-child save (F5)**: open Observe fresh — must
   NOT silently default to the first roster student with no visible indication.
9. **No false "no model" refusal (F4)**: with Ollama running, ask a plain generic question with
   no student name. Must get a real answer.
10. **Settings page present (P1-2 — needs a fresh look, may be a new finding)**: navigate to
    Settings from the main nav. Confirm the page loads and shows provider configuration
    (Ollama/local model, any cloud provider fields). If it's missing, blank, or unreachable,
    file this as a new P1 with exact repro steps and a screenshot — this may have been dropped
    in a recent merge.
11. **Bundle-write path (P1-1, background check only, 2 min max)**: ask Claude to confirm via
    logs/filesystem that `improvement_audit.py`, `teacher_readiness.py`, and
    `ontology/learned_weights.py` are writing into `~/.lingua-viva/` (Mac) or
    `%APPDATA%\lingua-viva\` (Windows), not inside the installed app bundle.

### ROUND 3 — Day-one teacher flows

12. **Ask, grounded (F3)**: "What support should I prepare for Marco Bianchi tomorrow?" — must
    name Marco Bianchi specifically with his real logged observations, not a vague deflection.
13. **Observe, typed**: save an observation for Marco Bianchi.
       PASTE THIS:
       Marco self-corrected passato prossimo during partner reading today
    Green toast, ~6 seconds, form clears.
14. **Double-save probe** (known gap C7): save the SAME text twice on purpose. Record what
    happens. Known issue — evidence only.
15. **Prepare / lesson materials**: generate materials for Marco + Nora. Must produce a real
    document, no placeholder brackets. (Known gap C8 — may time out under load.)
16. **Parent report**: generate one for Nora. Readable, grounded, nothing invented. Note
    whether source observation IDs show (known gap C6).
17. **Archive student** still works from the lens.

### ROUND 4 — Honesty probes (GIR v2)

18. Create a brand-new student (Luca Verdi), zero observations, ask what the observations prove
    about him. Must hedge honestly, NOT confidently invent evidence.
19. Stop Ollama yourself. Ask a question naming Marco: must get the honest setup message, no
    bracket placeholders. Restart Ollama, wait ~10s, ask again WITHOUT restarting the app — must
    recover with a real answer.

### ROUND 5 — Demo dry run (this is the actual golden-path rehearsal)

This is a real rehearsal of the demo, not a bug hunt — time it, and flag anything that doesn't
happen exactly as scripted, since this script may run live in front of someone soon.

20. Open `dev/LV_DEMO_SCRIPT_2026-08-04.md` in the learning-architecture clone. Walk Chip through
    Beats 1-4 exactly as written (Observe capture→review→save, Ask general-vs-student-named,
    lesson materials, parent report). Beat 5 (archive/offline) only if time allows.
21. Time the full walkthrough start to finish. Note any beat where the UI doesn't match what the
    script describes (a button ID that's changed, a line that doesn't render as expected).
22. Specifically confirm the "line to say out loud" moments actually land — i.e. the safety-gate
    hedge in the parent report (Beat 4) genuinely appears when evidence is thin, and the F2
    warning in Beat 2 genuinely renders in text. If either of those beats would show nothing
    unusual on a low-evidence case, that's worth a note — the demo's honesty story depends on it.

### WRAP-UP — her words, then the report

Ask one at a time: What worked? What didn't? What was confusing? What would a real teacher quit
over on day one? Any feature requests? Also ask: did the demo dry run (Round 5) feel ready to
show someone today, or did anything feel shaky?

Write `qa/<today's-date>_chip-qa-0.2.39-<machine-tag>.md` in the mission-canvas clone:
1. Versions: app version, OS/machine tag, both repo hashes, clean/dirty.
2. 3-line executive summary + P0/P1/P2 counts, and: **"Is this app ready for teachers
   tomorrow — yes or no?"** Also answer: **"Is the demo script ready to run live — yes or no?"**
3. Verdict table, every numbered check above: WORKS / FAIL / KNOWN-GAP / BLOCKED + evidence
   pointer. Explicitly call out the headline fix (mic hardware release on tab-switch) and
   whether it held.
4. "Manual QA feedback (Chip's notes)" — verbatim.
5. Feature requests (separate from bugs).
6. Technical appendix: timestamps, exact response texts, likely file/area per issue, log
   excerpts. Copy `app.log`, `events.log`, saved API outputs into `qa/traces/`, screenshots into
   `qa/screenshots/`.

Publishing rules: stage ONLY `qa/**` by explicit path — never `git add -A` or `git add .`.
Commit as `qa: <date> chip qa desktop-v0.2.39 (<machine-tag>)`. If a pre-push hook blocks you,
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
