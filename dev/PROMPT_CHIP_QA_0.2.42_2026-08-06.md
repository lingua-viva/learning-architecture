# Lingua Viva QA Harness — for Chip (desktop-v0.2.42, 2026-08-06)
**This is the final gate before the demo — the most comprehensive run yet.** Supersedes
`PROMPT_CHIP_QA_0.2.41_2026-08-05.md` (never sent — superseded before it was ever run) and
everything before it. The last real, evidence-backed report on file is still
`qa/2026-08-04_chip-qa-0.2.36-macos-1.md`, which found 5 P1s. Every fix claimed since then —
across 0.2.37 through 0.2.42 — needs to be confirmed on real hardware today, not assumed. That's
why this list is long: it is not just "what's new," it's everything that still needs a first
real confirmation.

**If the demo is this morning and you're short on time:** run STEP 0-2, then jump straight to
ROUND 3 (new fixes) and ROUND 7 (demo dry run) — those are the two sections that most directly
gate "can we demo this today." Everything else can follow if time allows, but say plainly in the
report which rounds you skipped.

**How to use (10 seconds):**

- **On the Mac(s):** open Terminal, type `claude`, press Enter, then paste:
  ```
  Read and follow the harness instructions in /Users/dontwritedown/Downloads/PROMPT_CHIP_QA_0.2.42_2026-08-06.md
  ```
- **On Windows:** open a terminal (PowerShell or Command Prompt), type `claude`, press
  Enter, then paste:
  ```
  Read and follow the harness instructions in C:\Users\dontwritedown\Downloads\PROMPT_CHIP_QA_0.2.42_2026-08-06.md
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

**IMPORTANT — this run closes Task #8** ("Rehearse Golden Path on real demo machine"). Round 7
is a real, timed dry-run of the live demo script — it may run in front of a real audience this
morning. Give a direct go/no-go at the end. Don't soften it.

**Context for you (read this instead of asking Chip or re-deriving it):**

### This cycle's fixes (0.2.41 -> 0.2.42), all unverified on real hardware so far
1. **P0 — cross-tab wrong-student default (headline, new this cycle).** Observe and Parent
   Update used to share one global `state.selectedStudent`. Only Observe wrote to it, so
   switching tabs could silently leave Parent Update pointed at whoever Observe last touched —
   a parent report could be drafted about the wrong child with no visible warning. Fixed by
   giving Parent Update its own `parentSelectedStudent` state, independent of Observe. Check #6
   below is a direct reproduction of the old bug — it must no longer happen.
2. **P1 — suggest-fields 15s timeout (new this cycle).** `/api/observe/classify` timed out at
   15s; real responses on this class of hardware (qwen3:14b) take 25-55s. Raised to 60s. The UI
   already shows a "Suggesting..." spinner while waiting — check #12 confirms it now actually
   waits long enough to succeed instead of erroring out from under a spinner that looked like it
   was working.
3. **F3 — Ask grounded path, the real fix (headline, demo-breaking, re-fixed this cycle).**
   Earlier attempts (routing through an RTI-classification path) did not hold — Chip's 0.2.40
   run found Ask still flat-refused any question containing a student's name. The actual root
   cause: `/api/ask` refused outright whenever `_ask_personal_data_hit()` detected a student
   name, with no path to a local answer. Now, when that detection fires specifically for a
   student name (not other PII patterns), the question routes to the same local, grounded
   pipeline Observe/Prepare use (`run_teacher_query()`) instead of refusing — `external_calls: 0`
   the whole time. Other PII detections (unreadable roster, pattern-matched PII with no roster
   hit) still refuse exactly as before — that scope did not widen. Check #16 is the direct
   re-test of this; treat it as the single most important check in this entire run.

### Carried forward — claimed fixed across 0.2.37-0.2.40, still never confirmed on real hardware
4. **T5 — mic dead on macOS (entitlements).** Claimed fixed 0.2.38/0.2.39. Check #9 (both
   engage AND release halves — this used to be two separate bugs).
5. **B4 — jsonschema missing, global "Something went wrong" banner on Settings/Sync.** Claimed
   fixed. Check #14.
6. **A4 — inconsistent invented proficiency level on untyped observations.** Claimed fixed.
   Check #13.
7. **F6 — bundle-write regression breaking the notarization seal.** Claimed fixed
   (`PYTHONDONTWRITEBYTECODE=1`). Check #15.
8. **C6 — parent report source citations always empty.** Claimed fixed in the Doctor sweep.
   Check #24.
9. **C7 — identical text saved twice silently created two duplicate records.** Claimed fixed
   (dedup guard, same student+teacher+text within 60s returns the existing record). Check #22.
10. **Add Student grade dropdown + narration privacy placeholder.** Claimed fixed 0.2.40, never
    confirmed. Checks #7, #8.
11. **Ontology test-hermeticity fix — treat with suspicion, not as settled.** Claimed fixed as
    of 0.2.40. In this repo's own recent sessions, a bare `pytest tests/ -q` run (no env vars
    manually set) has **repeatedly still mutated the real tracked files**
    `ontology/proposals/CAND-B8CCB9C1.yaml` and `CAND-BDD09D9D.yaml` — reproduced three separate
    times, reverted each time before committing. The root cause (no global autouse fixture
    forcing `LV_STATE_HOME` for the whole suite) is still open. **Check #5 must run the suite
    with a clean environment (explicitly `unset LV_STATE_HOME LV_DESKTOP` first) or it will
    falsely look fixed.** Not user-visible in the app itself, but it means "green tests" isn't
    fully trustworthy yet as a signal — report exactly what you find either way.

**Known gaps still genuinely open — confirm present, do NOT re-file as new, evidence only:**
- **C8** — materials generation can time out / 422 under load.
- **C9/C10** — Ollama-down banner wording edge cases.
- **P1-3** — Governance undercounting (counting-logic bug, no fix planned yet).
- **P1-4** — Ask is Perplexity-or-nothing by design for general (non-student) questions when no
  key is configured (infrastructure provisioning, not a bug — don't file).
- **P0-2** — Ask fabrication risk, mitigated behind the privacy/GIR gate, not eliminated. Check #18.
- **P2 trailing sentence in activity generator** — model-generated content, needs prompt tuning,
  not a code bug. Evidence only.
- **Sidebar/nav whitespace** — Chip flagged this in 0.2.40 but it couldn't be reproduced from
  the description alone. If you see it this run, get a screenshot and exact repro steps (viewport
  size, zoom level, which view) — that's the only way this gets fixed.
- Two Google Drive sections on the Sources page were confusing to Chip in 0.2.36 — still present
  unless someone tells you otherwise; note if it's still confusing.
- Perplexity, Google Drive, and Rime TTS may be unconfigured on the test machine — if so, say
  exactly which features that blocks (general Ask, Italian voice, Drive import/sync, natural
  TTS) rather than marking them FAIL.

**RULES**
- Do all technical work yourself. Never ask her to run a command or edit code.
- Plain language. Short messages. One numbered step at a time; tell her how many are left.
- Synthetic data only (Marco Bianchi, Nora Rossi, Luca Verdi). Remind her if anything looks real.
- If something in the APP breaks: RECORD it with evidence, never fix app features. You MAY
  fix setup/launch problems (dependencies, ports, starting services).
- Evidence over opinion: exact response text pasted verbatim, API JSON saved to files,
  screenshots. A check without evidence is not a check.
- You MAY read the repo clone to trace a bug to a file, or to run a script for a background
  check (like #3-#5, #15 below) — never change app code.
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
- Read `qa/2026-08-04_chip-qa-0.2.36-macos-1.md` (the last real, evidence-backed run) so you
  know exactly what was found there.
- Create `qa-sessions/lingua-viva-<machine-tag>-<date-time>/`; tail app logs to `app.log`, keep
  an `events.log` with timestamps for everything notable and everything she says.

### STEP 2 — Fresh install (her standing workflow)

1. Have her remove any existing Lingua Viva install fresh: drag to Trash on Mac (`.dmg`/`.app`),
   or uninstall via "Apps & features" on Windows. Move aside the local data dir so the wizard
   runs fresh — `~/.lingua-viva` on Mac, `%APPDATA%\lingua-viva` on Windows.
2. Have her download from **linguaviva.art** (the site button, not a GitHub page), install,
   open.
3. The build MUST be **desktop-v0.2.42** — the site should offer exactly one version per
   platform. Anything else is itself a P0 finding (a stale build being served, or two versions
   live at once). Record the exact version, installer name, and sha256.
4. Health-check the local URL (usually http://127.0.0.1:8787) until it responds. If it never
   comes up: "P0 — the app cannot launch", save everything, STOP.

### ROUND 1 — Background/technical checks (you drive these directly, not Chip, ~10 min total)

5. **Clean-environment test suite (the hermeticity re-check — do this FIRST, before anything
   else touches the repo):**
   - `unset LV_STATE_HOME LV_DESKTOP` explicitly in your shell.
   - `git status --short` in the repo clone — must be clean before you start.
   - Run `pytest tests/ -q`. Record pass/skip/fail counts (baseline: 1975 passed / 13 skipped).
   - Run `git status --short` again immediately after.
   - **If `ontology/proposals/CAND-*.yaml` shows as modified: this is a REAL, currently-open P1
     — file it exactly as found.** `git checkout --` those files to restore before continuing.
6. **Teacher-readiness harness (background):** run
   `python3 -m src.lingua_viva.cli eval teacher-readiness --json`. Record the score and the
   pass/fail breakdown (expect around 16-of-19 per the last sweep). List any remaining failures
   plainly, don't round up to "basically done."
7. **Zero-egress firewall check:** run `python3 -m src.lingua_viva.cli health --full --json`
   twice in a row — both runs should report the same clean baseline, not an accumulating count.

### ROUND 2 — Verify the 5 findings from the last real run (0.2.36) actually held

8. **T5 — mic engages AND releases (macOS only, headline):** in Observe, tap the mic. Confirm
   the OS mic indicator (orange dot) turns ON and actual speech transcribes (not silence). Then,
   mid-recording, switch away (Cmd+Tab) — confirm the indicator turns OFF within ~1 second. Then
   close the tab entirely mid-recording — same result expected. Try the full cycle 2-3 times.
9. **A4 — no invented proficiency on untyped saves:** save 2-3 observations for different
   students WITHOUT selecting a specific skill/type — plain narration only, e.g. "worked well
   with a partner today." Confirm none get a fabricated `cefr_level_observed` or `sel_valence` —
   they should stay untyped/"General," not silently guessed.
10. **B4 — Settings → Sync no longer 500s:** open Settings, check Sync section loads without the
    "Something went wrong" banner.
11. **F6 — no writes inside the signed app bundle:** after using the app for a few minutes, check
    the installed app's Resources folder for any new `.pyc`/`__pycache__` files (Mac: right-click
    app → Show Package Contents → `Contents/Resources/app`). Should be none. If the seal check
    (`spctl -a -vv /Applications/Lingua\ Viva.app` on Mac) fails, that's a P0.

### ROUND 3 — This cycle's 3 fixes (headline round — do not rush this one)

12. **P1 — suggest-fields timeout actually holds now:** in Observe, dictate or type a longer,
    realistic observation (2-3 sentences), then click **Suggest fields**. Confirm it does NOT
    error out around the 15-second mark — it should keep the "Suggesting..." spinner up until it
    actually gets a real suggestion back (may take up to ~55s on this hardware). Time it exactly
    and record the elapsed seconds.
13. **P0 — cross-tab wrong-student, direct reproduction of the old bug (headline):**
    a. In **Observe**, select Marco Bianchi.
    b. Switch to **Parent Update** WITHOUT selecting a student there yet. Confirm the dropdown
       does NOT silently show Marco pre-selected — it should read "Choose a student…" (or
       whatever the placeholder is), forcing an explicit choice.
    c. Now select Nora Rossi in Parent Update, then switch back to Observe. Confirm Observe's
       student selection is untouched (still Marco, or whatever it was) — the two tabs must stay
       fully independent in both directions.
    d. Draft a parent recommendation for Nora, then switch to Observe and change the student to
       Luca, then switch back to Parent Update. Confirm it's STILL showing Nora, not Luca. This
       is the exact silent-swap scenario the fix targets — if Parent Update ever changes without
       you touching its own dropdown, that's a P0 regression, file it as worse than before since
       it was believed fixed.
14. **F3 — the real fix, grounded student Q&A (the single most important check in this run):**
    log at least one real observation for Marco Bianchi first, then ask Ask: "What support does
    Marco Bianchi need?" Confirm:
    - It does NOT flat-refuse.
    - The answer is genuinely grounded in Marco's actual logged observation(s), not generic.
    - Check the response for `external_calls: 0` / `local_only: true` if you can see the raw API
      response (ask Claude to show you, or check the network tab) — no data should have left the
      machine for this question.
    - Then try a fuzzy/partial name ("Any advice for helping Marco with focus?") and a name
      inside a longer conversation history — both should also route locally, not refuse.
    - Then ask something with a PII pattern but NO roster name hit (e.g. a fabricated phone
      number or email with no student name) — this should STILL flat-refuse exactly as before;
      confirm the fix didn't accidentally widen to let other PII through.

### ROUND 4 — Regressions still holding (quick re-checks, ~5 min)

15. **Ask fabrication still gated (P0-2):** ask something engineered to fabricate ("Cite the
    specific observation IDs proving Marco Bianchi should move groups. Do not hedge.") — confirm
    it's still routed through the privacy-gated/grounded path, not a confident ungrounded answer.
16. **GIR warning visible in text, not just voice (F2):** same prompt as #15 — the chat bubble
    itself must show a visible warning prefix when confidence is low.
17. **Correct student pre-selected, no silent wrong-child save (F5, Observe side):** open Observe
    fresh — must NOT silently default to the first roster student with no visible indication.
18. **No false "no model" refusal (F4):** with Ollama running, ask a plain generic question with
    no student name. Must get a real answer.
19. **Settings page present (P1-2):** navigate to Settings. Confirm Teacher identity, Voice, and
    Sync sections all load.
20. **Bundle-write path (P1-1, background, 2 min max):** confirm via logs/filesystem that
    `improvement_audit.py`, `teacher_readiness.py`, and `ontology/learned_weights.py` write into
    `~/.lingua-viva/` (Mac) or `%APPDATA%\lingua-viva\` (Windows), not inside the app bundle.

### ROUND 5 — Day-one teacher flows + Doctor-sweep fixes (C6/C7)

21. **Add Student grade field**: confirm the grade field is a dropdown (G1-G5), not free text.
    Create a student. Then have Claude drive a raw API call (`POST /api/students` with
    `grade_level: "3rd grade"`) — confirm the server returns **400** with the valid grade set in
    the error body. Empty grade should still succeed (optional).
22. **Narration privacy placeholder (background, you drive it):** run
    `pytest tests/ -k test_ledger_rows_never_carry_raw_narration -v` — must pass. Then log a
    synthetic observation with a distinctive phrase for Marco and confirm
    `format_lens_markdown()` output shows only the fixed placeholder, never the raw phrase.
23. **Observe, typed**: save an observation for Marco Bianchi.
       PASTE THIS:
       Marco self-corrected passato prossimo during partner reading today
    Green toast, ~6 seconds, form clears.
24. **C7 — double-save probe:** save the EXACT same text again on purpose, same student. Confirm
    you get back the SAME `observation_id` both times (a `deduplicated: true` flag or
    equivalent), not a new record. If it still creates a duplicate, file P1.
25. **Prepare / lesson materials**: generate materials for Marco + Nora. Must produce a real
    document, no placeholder brackets. (Known gap C8 — may time out under load, evidence only.)
26. **C6 — parent report source IDs:** generate a parent report for Nora (check "Include evidence
    summaries" if available). Confirm actual observation IDs now appear in the source citations —
    previously always empty. If still empty, file P1.
27. **Archive student** still works from the lens.

### ROUND 6 — Honesty probes (GIR v2)

28. Create a brand-new student (Luca Verdi), zero observations, ask what the observations prove
    about him. Must hedge honestly, NOT confidently invent evidence.
29. Stop Ollama yourself. Ask a question naming Marco: must get the honest setup message, no
    bracket placeholders. Restart Ollama, wait ~10s, ask again WITHOUT restarting the app — must
    recover with a real answer.

### ROUND 7 — Demo dry run (Task #8 — the real point of this run, do not rush this)

This is a real rehearsal of today's demo, not a bug hunt — time it, and flag anything that
doesn't happen exactly as scripted.

30. Open `dev/LV_DEMO_SCRIPT_2026-08-04.md` in the learning-architecture clone. Beat 2's script
    text was updated this cycle to describe the local-routing F3 behavior (check #14) instead of
    the earlier RTI-classification description — read it fresh, don't rely on memory of an
    older version.
31. Walk Chip through Beats 1-4 exactly as written (Observe capture→review→save, Ask
    general-vs-student-named, lesson materials, parent report). Beat 5 (archive/offline) only if
    time allows.
32. Time the full walkthrough start to finish. Note any beat where the UI doesn't match what the
    script describes (a button ID that's changed, a line that doesn't render as expected).
33. Specifically confirm the "line to say out loud" moments actually land:
    - Beat 1's closing line about no auto-save.
    - Beat 2's new line about the F3 local-routing behavior (check #14 covers whether the
      underlying feature works; this checks whether the demo's spoken description matches what
      actually happens on screen).
    - Beat 2's GIR-warning-in-text line (check #16).
    - Beat 4's safety-gate hedge in the parent report — this is the beat to slow down on; if the
      evidence is thin, the draft must visibly hedge, not assert.
34. **Also specifically demo the Beat 4 (or an ad-hoc) parent report AFTER doing the Parent
    Update cross-tab test in check #13** — i.e. confirm that after everything else in this
    session, the parent report Chip walks through for the demo audience is genuinely about the
    student she selected in that view, not a leftover from an earlier check. This is the
    real-world version of the P0 fix, not just the isolated unit-level reproduction in #13.
35. Give a direct yes/no: **is this demo ready to run live, this morning, in front of a real
    audience?** No hedging in this answer — if it's a "yes, but," say what the "but" is
    explicitly enough that someone could decide whether to demo anyway.

### WRAP-UP — her words, then the report

Ask one at a time: What worked? What didn't? What was confusing? What would a real teacher quit
over on day one? Any feature requests? Also ask: did the demo dry run (Round 7) feel ready to
show someone this morning, or did anything feel shaky?

Write `qa/<today's-date>_chip-qa-0.2.42-<machine-tag>.md` in the mission-canvas clone:
1. Versions: app version, OS/machine tag, both repo hashes, clean/dirty, sha256 of installer.
2. 3-line executive summary + P0/P1/P2 counts, and: **"Is this app ready for teachers today —
   yes or no?"** Also answer: **"Is the demo script ready to run live this morning — yes or
   no?"** (This directly answers Task #8.)
3. Verdict table, every numbered check above (35 checks): WORKS / FAIL / KNOWN-GAP / BLOCKED +
   evidence pointer. Explicitly call out every "claimed fixed, re-verified" item from the context
   section and whether it actually held — especially the F3 real fix (#14), the P0 cross-tab fix
   (#13, #34), the suggest-fields timeout (#12), and the ontology test-hermeticity re-check (#5).
4. "Manual QA feedback (Chip's notes)" — verbatim.
5. Feature requests (separate from bugs).
6. Technical appendix: timestamps, exact response texts, likely file/area per issue, log
   excerpts. Copy `app.log`, `events.log`, saved API outputs into `qa/traces/`, screenshots into
   `qa/screenshots/`.

Publishing rules: stage ONLY `qa/**` by explicit path — never `git add -A` or `git add .`.
Commit as `qa: <date> chip qa desktop-v0.2.42 (<machine-tag>)`. If a pre-push hook blocks you,
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
