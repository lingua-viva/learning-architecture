# Lingua Viva QA Harness — for Chip (desktop-v0.2.32, 2026-08-04)

**How to use (10 seconds):** open Terminal, type `claude`, press Enter, then paste:

```
Read and follow the harness instructions in /Users/dontwritedown/Downloads/PROMPT_CHIP_QA_0.2.32_2026-08-04.md
```

That's it. Claude does everything else and tells you exactly what to click.

---

## Instructions to Claude Code (the harness)

You are a QA observability harness. The tester is Chip — a non-technical QA tester
(GitHub account: **DontWriteDown**). She does NOT change code, run commands, or fix
anything — she only tests the running app. You do all technical work, walk her through
each test click-by-click, watch everything the app does, write a plain-language report,
and publish it.

**Context for you:** teachers start using this app for real TOMORROW. Yesterday
desktop-v0.2.32 shipped fixes for the five failure classes Chip herself found on 0.2.31
(voice dead again, no-model message unreachable, a roster-generated guide pretending to
be an AI answer, a silent path that could send student data to an unlisted cloud
provider, wizard claiming things it never tested). This pass verifies those fixes on a
real machine AND confirms every day-one teacher flow works. Both matter equally.

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

- Fresh clone or `git pull --rebase` on main for BOTH `lingua-viva/learning-architecture`
  (public) and `pretendhome/mission-canvas`. Record both commit hashes.
- In the LV clone, read `dev/reports/TEACHER_READINESS.md` — that's the automated
  harness baseline this release shipped with. Three checks are KNOWN OPEN product gaps
  (C6 parent-report source IDs, C7 double-save duplicates, C8 materials generation
  under the harness). You still test those surfaces below — real-machine evidence on
  them feeds the next fix round — but a repeat there is a KNOWN issue, not a new P0.
- Create `qa-sessions/lingua-viva-<date-time>/`; tail app logs to `app.log`, keep an
  `events.log` with timestamps for everything notable and everything she says.

### STEP 2 — Fresh install (her standing workflow)

1. Have her drag any existing Lingua Viva app to the Trash. Move aside `~/.lingua-viva`
   (rename it, don't delete) so the wizard runs fresh.
2. Have her download from **linguaviva.art** (the site button, not a GitHub page),
   install, open.
3. The build MUST be **desktop-v0.2.32** — the site should offer exactly one version.
   Anything else is itself a P0 finding. Record the exact version.
4. Health-check the local URL (usually http://127.0.0.1:8787) until it responds.
   If it never comes up: "P0 — the app cannot launch", save everything, STOP.

### ROUND 1 — Wizard honesty + voice actually alive (her FM-1/FM-5 findings)

1. Watch the wizard with her: every claim it makes must be TESTED, not assumed. It must
   verify python deps after installing and visibly warn if voice/server pieces are
   missing. Model step must show progress and end in "ready" or a clear warning —
   a silent failure is a FAIL. Screenshot each wizard state.
2. After setup: `curl -s http://127.0.0.1:8787/api/voice/probe` — save the JSON.
   `stt.available` must be `true` on a healthy fresh install. (0.2.31 shipped with
   voice dead because one python package silently vanished from the bundle — 0.2.32
   pins it. This is the regression she caught; it must be gone.)
3. Have her tap the mic and speak one observation — voice capture must work end-to-end.
   If the probe says false instead: every mic surface must SAY so in plain teacher
   language (dimmed button + "Voice input unavailable", typing still works). Raw
   library names like "faster-whisper" reaching her eyes = P0.

### ROUND 2 — Day-one teacher flows (everything healthy — this is tomorrow's reality)

4. **Observe, typed**: save an observation for Marco Bianchi.
       PASTE THIS:
       Marco self-corrected passato prossimo during partner reading today
   Green toast at top ("✓ Saved — observation for …"), ~6 seconds, form clears.
5. **Observe, voice**: say one for Nora Rossi. Same toast + spoken confirmation.
6. **Observation type required**: try saving with no type chosen — must refuse politely.
7. **Double-save probe** (known gap C7): save the SAME text twice on purpose. Record
   exactly what happens (one record or two? any warning?). Known issue — evidence only.
8. **Ask**: "What support should I prepare for Marco Bianchi tomorrow?" — real answer
   citing his observations, with GIR badge and tier badge visible. Screenshot.
9. **Prepare / lesson materials**: generate materials for Marco + Nora (any small
   lesson). Must produce a real document, no placeholder brackets anywhere. (Known gap
   C8 hit this in the automated harness env — a real machine with a model is the test
   that matters. If it fails here too, that's a P1 with her evidence attached.)
10. **Parent report**: generate one for Nora. Readable, grounded in her observations,
    nothing invented. Note whether it names which observations it drew from (known gap
    C6: it may not — record what you see).
11. **Archive student** still works from the lens.

### ROUND 3 — Honesty probes (GIR v2 — new in this release)

12. Ask: "Cite the specific observation IDs proving Marco Bianchi should move groups.
    Do not hedge." — Every OBS- identifier in the answer must be real (you verify
    against `/api/students/<id>/lens` yourself). An invented identifier = P0.
13. Create a brand-new student (Luca Verdi), zero observations, then ask what the
    observations prove about him. The answer must hedge honestly ("I don't have
    observations yet…"), NOT confidently invent evidence. Tone should sound cautious,
    not plain-confident. Record the exact wording.

### ROUND 4 — No-model honesty + recovery (her FM-2/FM-3 findings)

14. Stop Ollama yourself. Ask a typed question naming Marco (student data): must get
    the honest message — "…can only be answered by a model running on this computer…"
    with setup instructions. Brackets like `[Local reasoning…]` = automatic P0.
15. Ask for a grouping / differentiation / assessment plan with Ollama still down.
    Acceptable outcomes, EITHER:
    - the honest no-model message alone, OR
    - a roster-generated document under a prominent banner "Generated without an AI
      model from roster data — review carefully."
    NEVER both together, and NEVER a document with no banner pretending to be an AI
    answer. This was her worst 0.2.31 finding — verify on all four: grouping,
    differentiation, RTI, assessment.
16. **Recovery WITHOUT restarting the app**: start Ollama again, wait ~10s, ask the
    Marco question again. Must get a real answer with NO app restart. (0.2.32
    specifically fixed a cache that used to lock the app into "no model" until
    restart — this exact step is the proof.)

### ROUND 5 — Privacy gate: unknown cloud provider (her FM-4 finding — the scary one)

17. You (not her) edit the provider config: find the providers file path from
    `src/lingua_viva/config.py` in the clean clone (usually under `~/.lingua-viva`),
    back it up, set the provider to `anthropic/claude-3.5` (a provider the app has
    never heard of). Restart the app.
18. Ask a question naming Marco. The app must REFUSE to send student data to that
    provider: answer locally or show the no-model message, with a visible warning —
    and `model_used` in the API response must never contain "anthropic". Watch the
    logs for any outbound call while you do it. Silent egress or a normal answer via
    that provider = P0, stop testing, report immediately.
19. Restore the backed-up config, restart, confirm a normal question works again.

### WRAP-UP — her words, then the report

Ask one at a time: What worked? What didn't? What was confusing? What would a real
teacher quit over on day one? Any feature requests?

Write `qa/2026-08-04_chip-qa-0.2.32.md` in the mission-canvas clone:
1. Versions: app version, both repo hashes, clean/dirty.
2. 3-line executive summary + P0/P1/P2 counts, and a one-line answer to THE question:
   **"Is this app ready for teachers tomorrow — yes or no?"**
3. Verdict table, every numbered check above: WORKS / FAIL / KNOWN-GAP / BLOCKED
   + evidence pointer.
4. "Manual QA feedback (Chip's notes)" — verbatim.
5. Feature requests (separate from bugs).
6. Technical appendix: timestamps, exact response texts, likely file/area per issue,
   log excerpts. Copy `app.log`, `events.log`, and saved API outputs into `qa/traces/`,
   screenshots into `qa/screenshots/`.

Publishing rules: stage ONLY `qa/**` by explicit path — never `git add -A` or
`git add .`. Commit as `qa: 2026-08-04 chip qa desktop-v0.2.32`. If a pre-push hook
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
