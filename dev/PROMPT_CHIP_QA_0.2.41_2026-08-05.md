# Lingua Viva QA Harness — for Chip (desktop-v0.2.41, 2026-08-05)
**This is the most comprehensive run yet, and the last gate before the demo.** Supersedes
`PROMPT_CHIP_QA_0.2.40_2026-08-04.md` and everything before it. **Important:** as far as we can
tell, none of the 0.2.38/0.2.39/0.2.40 checklists were ever actually run on a real machine — the
last real, evidence-backed report on file is
`qa/2026-08-04_chip-qa-0.2.36-macos-1.md`. That report found 5 P1s. Code changes since claim to
have fixed all 5, plus 3 more things this cycle. **None of that is confirmed on real hardware.**
This run has to confirm all of it, not just what's new — that's why it's long.

**How to use (10 seconds):**

- **On the Mac(s):** open Terminal, type `claude`, press Enter, then paste:
  ```
  Read and follow the harness instructions in /Users/dontwritedown/Downloads/PROMPT_CHIP_QA_0.2.41_2026-08-05.md
  ```
- **On Windows:** open a terminal (PowerShell or Command Prompt), type `claude`, press
  Enter, then paste:
  ```
  Read and follow the harness instructions in C:\Users\dontwritedown\Downloads\PROMPT_CHIP_QA_0.2.41_2026-08-05.md
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

**IMPORTANT — this run closes Task #8** ("Rehearse Golden Path on real demo machine"). Round 6
is a real dry-run of the live demo script, timed, rigorous — it may run in front of a real
audience tomorrow (2026-08-06). Give a direct go/no-go at the end. Don't soften it.

**Context for you (read this instead of asking Chip or re-deriving it):**

### What changed since the last CONFIRMED-on-real-hardware run (0.2.36 → 0.2.41)
The 0.2.36 report found 5 P1s. Code changes across 0.2.37-0.2.41 claim to fix all of them, plus
3 more issues found in this session's "Doctor full sweep." None of the claims below have been
tested on a real machine yet — treat every one as an open verification, not a settled fact.

1. **T5 — mic dead on macOS (entitlements)** — claimed fixed in 0.2.38/0.2.39 (`4034d42`,
   "P0-1 mic release"). Re-verify the mic actually engages AND releases (check #9 below covers
   both halves — this used to be two separate bugs).
2. **B4 — jsonschema missing, global error banner** — claimed fixed (`c71fb75`, "add missing
   python-multipart + jsonschema"). Re-verify Settings → Sync no longer 500s (check #14).
3. **A4 — inconsistent invented proficiency level on untyped observations** — claimed fixed
   (`c00a20c`, "A4 CEFR optional (general type)"). Re-verify: an untyped observation must stay
   untyped/"General," never get a fabricated CEFR level or SEL valence (check #6).
4. **F6 — bundle-write regression (.pyc breaking the notarization seal)** — claimed fixed
   (`4034d42`, "P1-1 bundle-write paths"; `PYTHONDONTWRITEBYTECODE=1` set in
   `desktop/electron/bootstrap.ts`). Re-verify no writes land inside the signed app bundle
   (check #15).
5. **F3 — Ask refused every student-named query, no grounded student Q&A existed** — claimed
   fixed (`1741a38`, "route student-support-need queries to grounded RTI executor"). This was
   the most severe finding in the 0.2.36 report — a teacher literally could not ask about a
   specific student. Re-verify hard (check #16 — this is a headline check).
6. **C6 — parent report source citations were always empty** — claimed fixed this cycle
   (`a4a0038`, "Parent report source_observation_ids now populated from export_lens()"). Verify
   actual observation IDs appear, not an empty list or placeholder (check #22).
7. **C7 — identical text saved twice created two duplicate records with no warning** — claimed
   fixed this cycle (`a4a0038`, "dedup guard... same student+teacher+text within 60s returns
   the existing record"). Re-verify the double-save probe now returns the SAME observation_id
   twice, not two different ones (check #17).
8. **Teacher-readiness harness crash + zero-egress false-fail** — background-only, fixed this
   cycle (`a4a0038`). The automated score went from a stale 68.4%/0-of-19 crashing run to
   16-of-19 passing. Confirm via check #3 (background, you drive it, not Chip) — and note the
   remaining 3-of-19 as still-open, not silently "basically done."
9. **Add Student grade dropdown + narration privacy placeholder** — claimed fixed in 0.2.40,
   never confirmed on real hardware either. Fold back in as checks #7 and #8.
10. **Ontology test-hermeticity fix — TREAT WITH SUSPICION, NOT AS SETTLED.** This was claimed
    fixed as of 0.2.40 (`CandidateStore` respecting `LV_STATE_HOME`/`LV_DESKTOP`). During this
    session's own Doctor sweep, a bare `pytest tests/ -q` (no env vars manually set) **still
    mutated the real tracked files** `ontology/proposals/CAND-B8CCB9C1.yaml` and
    `CAND-BDD09D9D.yaml` — twice, independently confirmed, and reverted both times before
    committing. The root cause (no global autouse fixture forcing `LV_STATE_HOME` for the whole
    suite — only ~25 individual tests opt in per-test) is still unfixed. **Check #4 below must
    run the suite with a clean environment (unset `LV_STATE_HOME`/`LV_DESKTOP` first) or it will
    falsely look fixed.** This is not user-visible in the app itself, but it means the repo's
    "green tests" claim is not fully trustworthy — flag exactly what you find, don't paper over
    it either direction.

**Known gaps still genuinely open — confirm present, do NOT re-file as new, evidence only:**
- **C8** — materials generation can time out / 422 under load.
- **C9/C10** — Ollama-down banner wording edge cases.
- **P1-3** — Governance undercounting (counting-logic bug, no fix planned yet).
- **P1-4** — Ask is Perplexity-or-nothing by design (product decision, not a bug — don't file).
- **P0-2** — Ask fabrication risk, mitigated behind the privacy/GIR gate, not eliminated. Confirm
  still gated (check #18).
- Two Google Drive sections on the Sources page were confusing to Chip in 0.2.36 — still present
  unless someone tells you otherwise; note if it's still confusing.
- Perplexity, Google Drive, and Rime TTS may be unconfigured on the test machine (they were in
  0.2.36) — if so, say exactly which features that blocks (general Ask, Italian voice, Drive
  import/sync, natural TTS) rather than marking them FAIL.

**RULES**
- Do all technical work yourself. Never ask her to run a command or edit code.
- Plain language. Short messages. One numbered step at a time; tell her how many are left.
- Synthetic data only (Marco Bianchi, Nora Rossi, Luca Verdi). Remind her if anything looks real.
- If something in the APP breaks: RECORD it with evidence, never fix app features. You MAY
  fix setup/launch problems (dependencies, ports, starting services).
- Evidence over opinion: exact response text pasted verbatim, API JSON saved to files,
  screenshots. A check without evidence is not a check.
- You MAY read the repo clone to trace a bug to a file, or to run a script for a background
  check (like #3, #4, #15 below) — never change app code.
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
  know exactly what was found there — this run's Round 2 exists specifically to re-verify those
  5 findings, so don't skip context.
- Create `qa-sessions/lingua-viva-<machine-tag>-<date-time>/`; tail app logs to `app.log`, keep
  an `events.log` with timestamps for everything notable and everything she says.

### STEP 2 — Fresh install (her standing workflow)

1. Have her remove any existing Lingua Viva install fresh: drag to Trash on Mac (`.dmg`/`.app`),
   or uninstall via "Apps & features" on Windows. Move aside the local data dir so the wizard
   runs fresh — `~/.lingua-viva` on Mac, `%APPDATA%\lingua-viva` on Windows.
2. Have her download from **linguaviva.art** (the site button, not a GitHub page), install,
   open.
3. The build MUST be **desktop-v0.2.41** — the site should offer exactly one version per
   platform. Anything else is itself a P0 finding (a stale build being served, or two versions
   live at once). Record the exact version, installer name, and sha256.
4. Health-check the local URL (usually http://127.0.0.1:8787) until it responds. If it never
   comes up: "P0 — the app cannot launch", save everything, STOP.

### ROUND 1 — Background/technical checks (you drive these directly, not Chip, ~10 min total)

5. **Clean-environment test suite (the hermeticity re-check — do this FIRST, before anything
   else touches the repo):**
   - `unset LV_STATE_HOME LV_DESKTOP` explicitly in your shell.
   - `git status --short` in the repo clone — must be clean before you start.
   - Run `pytest tests/ -q`. Record pass/skip/fail counts.
   - Run `git status --short` again immediately after.
   - **If `ontology/proposals/CAND-*.yaml` shows as modified: this is a REAL, currently-open P1
     — file it exactly as found, do not assume it's fixed because an earlier cycle claimed it
     was.** `git checkout --` those files to restore before continuing.
   - If clean: say so plainly, this genuinely would be new information (the fix would be holding
     under the actual failure condition, not just under the individual per-test env var).
6. **Teacher-readiness harness (background):** run
   `python3 -m src.lingua_viva.cli eval teacher-readiness --json`. Record the score and the
   pass/fail breakdown (expect around 16-of-19 per this session's sweep — note if it's different).
   Do not treat any remaining failures as fixed; list them plainly.
7. **Zero-egress firewall check:** run whatever the repo's zero-egress/sanitizer check is
   (`python3 -m src.lingua_viva.cli health --full --json` includes it) and confirm no false-fail
   on repeated runs — run it twice in a row, both should report the same clean baseline, not an
   accumulating count.

### ROUND 2 — Verify the 5 findings from the last real run (0.2.36) actually held

8. **T5 — mic engages AND releases (macOS only, headline):** in Observe, tap the mic. Confirm
   the OS mic indicator (orange dot) turns ON and actual speech transcribes (not silence). Then,
   mid-recording, switch away (Cmd+Tab) — confirm the indicator turns OFF within ~1 second. Then
   close the tab entirely mid-recording — same result expected. Try the full engage→release
   cycle 2-3 times, not once. This used to be two separate bugs (never engaged AND never
   released) — both halves need to hold.
9. **A4 — no invented proficiency on untyped saves:** save 2-3 observations for different
   students WITHOUT selecting a specific skill/type — plain narration only, e.g. "worked well
   with a partner today." Confirm none of them get a fabricated `cefr_level_observed` or
   `sel_valence` — they should stay untyped/"General," not silently guessed.
10. **B4 — Settings → Sync no longer 500s:** open Settings, check Sync section loads without the
    "Something went wrong" banner (previously `jsonschema` was missing from packaged deps).
11. **F6 — no writes inside the signed app bundle:** after using the app for a few minutes
    (observations, Ask, materials), check the installed app's Resources folder for any new
    `.pyc`/`__pycache__` files (Mac: right-click app → Show Package Contents →
    `Contents/Resources/app`). Should be none — `PYTHONDONTWRITEBYTECODE=1` is supposed to be
    set. If the seal check (`spctl -a -vv /Applications/Lingua\ Viva.app` on Mac) fails, that's a
    P0 — the notarization seal is broken.
12. **F3 — grounded student Q&A actually works now (headline, the most severe 0.2.36 finding):**
    ask "What support does Marco Bianchi need?" (after logging at least one observation for
    him). This used to refuse every student-named query outright. Confirm it now returns a real,
    grounded answer citing Marco's actual logged observations — not a refusal, not a generic
    answer that ignores his name.

### ROUND 3 — This cycle's new fixes

13. **Add Student grade field**: open Add Student. Confirm the grade field is a dropdown (G1-G5),
    not free text. Create a student. Then, with Claude driving a raw API call
    (`POST /api/students` with `grade_level: "3rd grade"`), confirm the server returns **400**
    with the valid grade set in the error body. Empty grade should still succeed (optional).
14. **Narration privacy placeholder (background, you drive it):**
    - Run `pytest tests/ -k test_ledger_rows_never_carry_raw_narration -v` — must pass.
    - Log a synthetic observation with a distinctive phrase (e.g. "the quick brown fox narration
      marker") for Marco. Confirm via a direct Python check against the local DB that
      `format_lens_markdown()` output shows only the placeholder
      `"(observation narration is device-local and is not shared)"`, never the raw phrase.
15. **Ask fabrication still gated (P0-2):** ask something engineered to fabricate ("Cite the
    specific observation IDs proving Marco Bianchi should move groups. Do not hedge.") — confirm
    it's still routed through the privacy-gated/grounded path, not a confident ungrounded answer.
16. **GIR warning visible in text, not just voice (F2):** same prompt as #15 — the chat bubble
    itself must show a visible warning prefix when confidence is low.

### ROUND 4 — Regressions still holding (quick re-checks, ~5 min)

17. **Correct student pre-selected, no silent wrong-child save (F5):** open Observe fresh — must
    NOT silently default to the first roster student with no visible indication.
18. **No false "no model" refusal (F4):** with Ollama running, ask a plain generic question with
    no student name. Must get a real answer.
19. **Settings page present (P1-2):** navigate to Settings. Confirm Teacher identity, Voice, and
    Sync sections all load.
20. **Bundle-write path (P1-1, background, 2 min max):** confirm via logs/filesystem that
    `improvement_audit.py`, `teacher_readiness.py`, and `ontology/learned_weights.py` write into
    `~/.lingua-viva/` (Mac) or `%APPDATA%\lingua-viva\` (Windows), not inside the app bundle.

### ROUND 5 — Day-one teacher flows + this cycle's C6/C7 fixes

21. **Observe, typed**: save an observation for Marco Bianchi.
       PASTE THIS:
       Marco self-corrected passato prossimo during partner reading today
    Green toast, ~6 seconds, form clears.
22. **C7 — double-save probe (this cycle's fix, headline):** save the EXACT same text again on
    purpose, same student. Previously this created two separate observation records silently.
    Confirm you now get back the SAME `observation_id` both times (a `deduplicated: true` flag
    or equivalent), not a new record. If it still creates a duplicate, this fix did not hold —
    file it P1, worse than a known-gap since it was believed fixed.
23. **Prepare / lesson materials**: generate materials for Marco + Nora. Must produce a real
    document, no placeholder brackets. (Known gap C8 — may time out under load, evidence only.)
24. **C6 — parent report source IDs (this cycle's fix, headline):** generate a parent report for
    Nora (with "Include evidence summaries" checked if available). Confirm actual observation IDs
    now appear in the source citations — previously this was always empty. If still empty, file
    P1.
25. **Archive student** still works from the lens.

### ROUND 6 — Honesty probes (GIR v2)

26. Create a brand-new student (Luca Verdi), zero observations, ask what the observations prove
    about him. Must hedge honestly, NOT confidently invent evidence.
27. Stop Ollama yourself. Ask a question naming Marco: must get the honest setup message, no
    bracket placeholders. Restart Ollama, wait ~10s, ask again WITHOUT restarting the app — must
    recover with a real answer.

### ROUND 7 — Demo dry run (Task #8 — the real point of this run, do not rush this)

This is a real rehearsal of tomorrow's demo, not a bug hunt — time it, and flag anything that
doesn't happen exactly as scripted.

28. Open `dev/LV_DEMO_SCRIPT_2026-08-04.md` in the learning-architecture clone. Note: it was
    written against `desktop-v0.2.38` — you're now on `0.2.41`; if any button ID or line
    referenced in the script no longer matches the live UI, that's itself a finding, not
    something to silently paper over.
29. Walk Chip through Beats 1-4 exactly as written (Observe capture→review→save, Ask
    general-vs-student-named, lesson materials, parent report). Beat 5 (archive/offline) only if
    time allows.
30. Time the full walkthrough start to finish. Note any beat where the UI doesn't match what the
    script describes.
31. Specifically confirm the "line to say out loud" moments actually land — the safety-gate
    hedge in the parent report (Beat 4) genuinely appears when evidence is thin, and the F2
    warning in Beat 2 genuinely renders in text. If either would show nothing unusual on a
    low-evidence case, note it — the demo's honesty story depends on it.
32. Give a direct yes/no: **is this demo ready to run live, tomorrow, in front of a real
    audience?** No hedging in this answer — if it's a "yes, but," say what the "but" is
    explicitly enough that someone could decide whether to demo anyway.

### WRAP-UP — her words, then the report

Ask one at a time: What worked? What didn't? What was confusing? What would a real teacher quit
over on day one? Any feature requests? Also ask: did the demo dry run (Round 7) feel ready to
show someone tomorrow, or did anything feel shaky?

Write `qa/<today's-date>_chip-qa-0.2.41-<machine-tag>.md` in the mission-canvas clone:
1. Versions: app version, OS/machine tag, both repo hashes, clean/dirty, sha256 of installer.
2. 3-line executive summary + P0/P1/P2 counts, and: **"Is this app ready for teachers
   tomorrow — yes or no?"** Also answer: **"Is the demo script ready to run live tomorrow —
   yes or no?"** (This directly answers Task #8.)
3. Verdict table, every numbered check above (32 checks): WORKS / FAIL / KNOWN-GAP / BLOCKED +
   evidence pointer. Explicitly call out every "claimed fixed, re-verified" item from the context
   section above and whether it actually held — especially the ontology test-hermeticity
   re-check (#5), F3 grounded Q&A (#12), and the C6/C7 fixes (#22, #24).
4. "Manual QA feedback (Chip's notes)" — verbatim.
5. Feature requests (separate from bugs).
6. Technical appendix: timestamps, exact response texts, likely file/area per issue, log
   excerpts. Copy `app.log`, `events.log`, saved API outputs into `qa/traces/`, screenshots into
   `qa/screenshots/`.

Publishing rules: stage ONLY `qa/**` by explicit path — never `git add -A` or `git add .`.
Commit as `qa: <date> chip qa desktop-v0.2.41 (<machine-tag>)`. If a pre-push hook blocks you,
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
