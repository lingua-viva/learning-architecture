# Lingua Viva — Demo Script: The Trust Story
**Date written:** 2026-08-04. **Target build:** `desktop-v0.2.38` (live, signed, verified — see
`dev/LV_STATUS_AND_VOICE_WALKBACK_2026-08-04.md`). **Runtime:** ~6-8 minutes.

No new draft existed for this — `dev/EXECUTION_PROMPT_LV_DEMO_READINESS_2026-07-22_KIRO.md` is a
different, past demo (2026-07-23, Linux machine, lesson-differentiation focus). This is a fresh
script for today's build and today's story.

## The story, in one line
**Lingua Viva doesn't pretend to know things it doesn't.** Every beat below either shows the app
producing a grounded answer from real evidence, or honestly refusing when the evidence isn't
there — and both are the feature, not the disclaimer.

## Discipline check before you touch the laptop (Task #11)
- Global voice companion stays hidden (`voice-hidden`). Do not re-enable it for "wow factor."
- Only two sanctioned mics exist in this build: the Observe dictation mic (`#obs-mic`) and the Ask
  voice-first Perplexity path. Don't demo anything else that has a mic icon.
- If a mic fails live (OS permission dialog, flaky audio), **fall back to typing immediately** —
  that fallback is rehearsed below, not improvised.
- No Prepare mic, no student-profile mic, no skip-review-at-high-confidence. If someone asks "can
  it just save automatically," the honest answer is "not yet, by design — a teacher always
  reviews before anything is saved."

---

## Beat 1 — Observe: capture is fast, save is never automatic
1. Open **Observe**. Pick a real (or seeded demo) student from `#obs-student`.
2. Tap `#obs-mic` and say something like: *"She self-corrected passato prossimo and used essere
   correctly in context."* Watch it transcribe into `#obs-text`.
   - **If the mic doesn't fire** (permission dialog, silence): don't fight it on camera. Say "and
     the typed path is identical" and type the same sentence into `#obs-text`. This is the
     rehearsed fallback, not a recovery — say so.
3. Click **Suggest fields** (`#suggest-observation`). Point at the status line: *"Nothing is saved
   until you review and press Save."* Walk through the suggested tags (CEFR skill, observed
   level, direction) — these are proposals, editable, not committed.
4. Click **Save Observation** (`#save-observation`). Point at `#obs-result`: *"Student data stays
   on this machine."*

**The line to say out loud:** "Notice there's no 'auto-save while listening.' Every voice capture
still ends at a human review card. That's a deliberate walkback from an earlier version that
saved straight from speech — we ripped it out."

## Beat 2 — Ask: grounded when there's evidence, honest when there isn't
1. Switch to **Ask**. Ask a *general* pedagogy question first (something with no student name) —
   e.g. "What's a good scaffolding strategy for passato prossimo?" Let it answer normally.
2. Now ask a **student-named support question** — e.g. "What support does [the student from Beat
   1] need?" This is the RTI path (`LV-STU-003`), fixed this session (F3): it now classifies
   correctly and returns a grounded answer built from that student's actual observations and
   RTI-tier evidence, not a generic answer.
   - **Say explicitly:** "This used to flat-refuse any question containing a student's name.
     Now it routes locally through the lens and returns a grounded answer — no data leaves
     this machine. The privacy gate still blocks the question from going to Perplexity, but
     it answers from local observations instead of refusing."
3. Optionally, ask something with **no grounding available at all** (a student with zero
   observations, or a fabricated-sounding claim). Let the safety gate fire — a visible warning
   prefix should appear in the chat bubble itself, not just in speech.
   - **The line to say out loud:** "That warning renders in the text, not just in the voice
     output — earlier this version only warned you if you were listening, not reading. Now both
     paths get the same warning from the same signal."

## Beat 3 — Lesson materials: privacy-clean generation, nothing invented
1. Generate lesson materials for the CEFR level surfaced in Beat 1/2.
2. **The line to say out loud:** "This only uses what's actually in the curriculum store — it
   won't invent activities or reading passages that aren't grounded in ingested material. If it
   doesn't have something, it says so instead of guessing."

## Beat 4 — Parent report: the safety gate on camera, the actual differentiator
1. Go to the parent-communication view. Pick the student, set a home-support focus
   (`#parent-focus`), optionally check "Include evidence summaries" (`#parent-include-evidence`).
2. Click **Draft Recommendation** (`#draft-parent`). Watch `#parent-output`.
3. **This is the beat to slow down on.** If the safety gate fires (low GIR, or a claim without
   two-point evidence), the draft will visibly hedge or refuse a specific claim rather than
   asserting it to a parent. Read that hedge out loud.
   - **The line to say out loud:** "This is the moment that matters. A parent report is the
     highest-stakes text this app produces — it goes to a family. If the evidence isn't there,
     it says so in the draft itself, before a teacher ever sends it. That's not a limitation,
     that's the product."

## Beat 5 — Archive and the offline story (only if time allows)
1. Show a student can be archived (`#archive-student`) without deleting their observation history.
2. If Ollama is genuinely down for the demo, don't hide it — let the honest
   "model unreachable" message surface and narrate it: "It tells you plainly when the local model
   isn't running, and recovers automatically when it comes back. It never silently falls back to
   a cloud model behind your back."

---

## Closing line
"Every one of these beats is either a grounded answer built from real evidence, or an honest
'I don't know yet.' There's no third option where it guesses and hopes."

## What NOT to do live
- Don't open dev tools to "show the JSON" unless specifically asked — keep it teacher-facing.
- The Add Student grade field is now a dropdown (G1-G5) with server-side validation — safe to
  demo directly if asked, no longer an open decision. The single-name field (no separate last
  name) is still a deliberate choice, not a bug — if asked, say "one display name field is enough
  for what the app needs today."
- Don't improvise a new voice surface, even if the audience asks "can it just listen all the
  time?" Answer honestly: "that's the exact thing we tried and walked back — here's why," and
  point to Beat 1's closing line.
