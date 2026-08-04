# Chip QA Pass — desktop-v0.2.31 Regression + Fix Verification

Paste everything below this line into Claude Code on the test machine.

---

You are running a QA pass on Lingua Viva desktop-v0.2.31 in `~/learning-architecture`
(pull latest from `main` first). Yesterday's release shipped four failure-CLASS fixes
from Claudia's teacher-readiness QA (`dev/FIX_BRIEF_CLAUDIA_QA_2026-08-03.md`). Your
job: verify each class is actually closed on a real install, plus a quick regression
of the prior blast-radius fixes.

**Ground rules**
- Test the REAL app: download fresh from https://linguaviva.art (should offer only
  desktop-v0.2.31 — anything else is itself a P0 finding). Do not test from source.
- Use fake student data only. Never real names.
- Evidence over opinion: paste exact response text, screenshots to `qa/screenshots/`,
  API responses verbatim. A check without evidence is not a check.
- Write your report to `qa/2026-08-04_chip-regression-0.2.31.md` (same shape as the
  2026-08-03 report: verdict table with P0/P1/P2, evidence log with timestamps).
- When done: commit ONLY `qa/**` files by explicit path and push. qa/ paths do not
  trigger a release — never `git add -A`.

## Round 1 — Setup wizard honesty (P0-1 + P1-1 fix)

1. Fresh install (move aside `~/.lingua-viva` or equivalent app data first).
2. Watch the wizard: it must now VERIFY python deps after install and show a visible
   warning if voice or server components are missing — silence is a failure.
3. Model step: wizard must show "Preparing the local AI model..." and then either
   "Local AI model ready." or a clear warning / system notification when the download
   finishes after the wizard closes. A model pull that fails with no message = FAIL.
4. Evidence: screenshot of each wizard state you see.

## Round 2 — Mic surfaces react to reality (P0-1 fix)

5. `curl -s http://127.0.0.1:8787/api/voice/probe` — record the JSON.
6. If `stt.available: true`: mic button normal, voice capture works end-to-end in
   companion, Ask, and Observe.
7. If `stt.available: false` (or force it: temporarily rename the bundled `av`
   package dir, restart): EVERY mic surface must show it — companion button dimmed
   with "Voice input unavailable" tooltip, `#vc-state` reads "Voice unavailable —
   type instead", Observe's mic badge explains typing still works. Tapping the mic
   must give a plain-language message. The string "faster-whisper is not installed"
   must never appear anywhere a teacher can see. Check ALL surfaces, not just one.

## Round 3 — No-model messages (P1-2 fix)

8. Stop Ollama (or remove all models). Ask a typed question in Ask.
   - Must get: "I need a local AI model to answer questions about your students.
     To set this up: install Ollama from ollama.com... ollama pull qwen2.5:3b..."
   - Must NEVER get: `[Local reasoning for ... - no model available]` — brackets
     reaching a teacher is an automatic P0.
9. Ask a voice question (if voice works): the SPOKEN answer must be the same
   actionable message, not bracket noise.
10. Ask a question naming a fake student: must get the student-data variant
    ("...can only be answered by a model running on this computer...").
11. Prepare → generate lesson materials with no model: the error shown must contain
    the same setup instructions, not "Start Ollama and retry."
12. Recovery: start Ollama with qwen2.5:3b pulled, ask again WITHOUT restarting the
    app — must get a real answer.

## Round 4 — Save confirmation (P2-1 fix)

13. Save an observation: a green toast must appear at the TOP of the window —
    "✓ Saved — observation for <name> · <time>" — and stay ~6 seconds. The form
    clears, but the toast makes the save unmistakable. Time it.
14. Try to double-save the way Claudia did: save, watch the form clear, ask yourself
    honestly whether anything tempts you to save again. Note your gut reaction.
15. Voice-act save (say an observation to the mic): same toast must appear alongside
    the spoken confirmation.

## Round 5 — Regression spot-check (prior fixes must still hold)

16. Observation save works at all (sanitizer bundled — the 0.2.29 P0).
17. Observation type is still required — no save without choosing one.
18. Ask chat still shows the GIR badge and tier badge on answers.
19. Archive student still works from the lens.

## Verdicts

Per check: WORKS / FAIL / BLOCKED (+ evidence). Anything a teacher would hit on
day one is P0. Finish with a 3-line executive summary at the top of the report.
