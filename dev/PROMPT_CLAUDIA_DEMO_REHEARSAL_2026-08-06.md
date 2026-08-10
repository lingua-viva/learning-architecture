# Claudia — Demo Rehearsal, 1 Hour Before Showtime (2026-08-06)

**Build:** `desktop-v0.2.43` — pushed, signed, live at linguaviva.art, verified minutes ago
(full 7-step check passed: CI green, macOS signature `XWT7RB624U`, download links resolve).
This is the exact build you'll be running. If your app auto-updates, let it — you're on the
newest, most-tested version we have.

**Script you're rehearsing:** `dev/LV_DEMO_SCRIPT_2026-08-04.md` (below, with one live risk
flagged and a decision you need to make before you walk in).

---

## The one decision you need to make right now: Beat 2

Chip QA-tested this build last night. Everything else in the script is confirmed solid. **Beat
2's second half — asking Ask a student-named question — fabricated 3 out of 5 times in her
dry run**, using the exact question the script tells you to ask. It's not random flakiness: the
app's own internal signal correctly flags these answers as ungrounded (`gir: 0.0`), but that
warning currently doesn't show up clearly enough in the moment for an audience to read it as
"the app caught itself" rather than "the app just made something up."

**Pick one before you rehearse, don't decide live:**

- **Option A (safest):** Skip the student-named half of Beat 2. Do the general pedagogy
  question only, then move to Beat 3. Still shows Ask works; removes the coin-flip.
- **Option B (still shows the RTI path, safe):** Ask about a **zero-observation student**
  instead of one with real history — Chip verified this hedges honestly every time, no
  fabrication risk. Use a student with no observations yet, or create one fresh
  (`+ Add Student`) right before the demo and don't observe them first. Ask: *"What support
  does [name] need?"* It will correctly say it doesn't have enough information yet — that IS
  the trust story, just as honest, zero risk.
- **Option C (bold, only if you're comfortable):** Ask the real question on a student with
  real observations anyway, and if it fabricates, say out loud: *"This is exactly the gap
  we're still closing — it should have caught this and it didn't yet."* This is still honest
  to the demo's own thesis, but it's a harder line to land live and only works if you're calm
  improvising in front of the room.

**My recommendation: Option B.** It keeps the exact beat, the exact button, the exact RTI
language from the script — you're just choosing a student for whom the honest answer is
guaranteed rather than a coin flip.

Whichever you pick, **say it out loud once right now** before you start the clock below, so the
words are already in your mouth when you get there live.

---

## Rehearse it for real, once, start to finish (6-8 min target)

Don't just read the script — open the app and click through every beat below, out loud, at
demo pace. Time yourself.

### Discipline check first
- Voice companion should be hidden — don't turn it on for "wow factor."
- Only two mics exist in this build: Observe's dictation mic, and Ask's voice path. Don't touch
  any other mic icon.
- **If a mic fails live** (permission dialog, silence): don't fight it on camera. Say "and the
  typed path is identical" and type the sentence instead. Rehearse this fallback now, not just
  read about it — actually deny the mic permission once and practice recovering from it.

### Beat 1 — Observe
1. Open Observe, pick a real student.
2. Mic: *"She self-corrected passato prossimo and used essere correctly in context."*
   Watch it transcribe.
3. Click Suggest Fields. Point at the status line: nothing is saved until you review.
4. Click Save Observation.
- **Line to say:** "Notice there's no auto-save while listening. Every voice capture still
  ends at a human review card."

### Beat 2 — Ask (with your Option A/B/C choice already made)
1. General question first, no student name: *"What's a good scaffolding strategy for passato
   prossimo?"* Let it answer normally.
2. Student-named question — using whichever option you picked above.
3. **Line to say (routing):** "This used to flat-refuse any question with a student's name.
   Now it routes locally through the lens — no data leaves this machine."
4. If you want the honest-refusal moment too (Option B naturally gives you this): let the
   safety warning render in the chat text itself, not just speech, and read it: *"That warning
   renders in the text now, not just voice — earlier this version only warned you if you were
   listening."*

### Beat 3 — Lesson materials
1. Generate materials for the CEFR level from Beat 1/2.
- **Line to say:** "This only uses what's actually in the curriculum store. If it doesn't have
  something, it says so instead of guessing."

### Beat 4 — Parent report (this is your strongest beat — confirmed rock-solid by QA)
1. Parent-communication view, pick the student, set a home-support focus.
2. Click Draft Recommendation. **Slow down here.**
3. Read any hedge/refusal out loud if it appears — this is the moment that matters.
- **Line to say:** "A parent report is the highest-stakes text this app produces. If the
  evidence isn't there, it says so in the draft itself, before a teacher ever sends it."

### Beat 5 — only if time allows
Archive a student without deleting history. If Ollama is down, narrate the honest "model
unreachable" message instead of hiding it.

### Closing line
"Every one of these beats is either a grounded answer built from real evidence, or an honest
'I don't know yet.' There's no third option where it guesses and hopes."

---

## What NOT to do live
- Don't open dev tools / show raw JSON unless someone specifically asks.
- Don't improvise a new voice surface even if asked "can it just listen all the time?" — answer
  honestly: "that's the exact thing we tried and walked back," point back to Beat 1.
- Add Student's grade field is a dropdown now (G1-G5, validated) — safe to demo directly.
- One display-name field (no separate last name) is a deliberate choice, not a bug, if asked.

## If something breaks that isn't in this doc
Say what you see, don't paper over it. "It's telling me X" is always a safe sentence in this
demo — the entire story is that honest failure is the feature. You can't break the thesis by
having something visibly not work; you can only break it by pretending it did work when it
didn't.

**Go time-box this to 15 minutes: pick your Beat 2 option (2 min), run the full script once at
pace (8 min), fix anything that felt shaky (5 min). You have the room.**
