# Claudia — Start Here (2026-08-03)

## The one rule that matters most

**Never type or speak a real child's name during testing. Not once.**
The two test students are **Marco Bianchi** and **Nora Rossi** — invented for
this packet. Everything you save during testing goes into logs and a public
report. Your real students stay completely out of this. If you catch yourself
starting to type a real name, stop — Claude will help you scrub it.

## What you're doing

Testing **Lingua Viva** end-to-end on your own computer, the way you'll use it
in class. 39 checks across 7 rounds, ordered so the most important things come
first. Claude Code does everything technical and walks you through each click.

Total time: roughly 1–2 hours. It's completely fine to stop partway — just
tell Claude **"I'm done"** and it will write up whatever you finished.

## The workflow (4 moves)

1. **Trash** any old Lingua Viva app on your Mac.
2. **Download fresh** from **linguaviva.art** (the site's download button, not
   a GitHub page), install, open.
3. Open Terminal and get the repo (first time only — later sessions just need
   the `git pull`):

   ```
   git clone git@github.com:lingua-viva/learning-architecture.git ~/learning-architecture
   cd ~/learning-architecture && git pull
   ```

4. Still in Terminal, type `claude`, press Enter, and paste this line:

   ```
   Read and follow the harness instructions in ~/learning-architecture/qa/packets/teacher-readiness-2026-08-03/HARNESS_PROMPT.md
   ```

   Then **follow Claude's steps one at a time.** Reply "done" after each, or
   describe what looked wrong. When you finish (or run out of time), say
   **"I'm done"** — Claude collects your feedback, writes the report, and
   publishes it to the repo automatically.

## What to try, in order

1. **First — the core loop**: create the two test students and save typed
   observations. If this works, everything else has a foundation.
2. **Second — voice observations**: speak observations, watch it pick the
   right student, refuse to guess, and never invent a language level.
3. **Third — voice questions**: ask about your (test) students out loud.
4. **Fourth — worksheet generation**: three-tier materials, and the hard
   privacy gate — no student name may ever appear in a worksheet.
5. **Fifth — Google Drive**: connect, import documents, extraction into a
   student lens, auto-sync, and the offline test.
6. **Sixth — cohort lesson planning**: the tiered lesson guide.
7. **Seventh — general health**: every tab, settings, Doctor page, and the
   new archive-student button.

Claude leads you through all of this — you don't need to memorize it. The full
script is in `QA_TESTING_PLAN.md` in this folder.

## Rules

- **Fake data only** (see the top of this page — it's rule zero).
- If something breaks, don't fix it — **describe it**. That IS the job.
- If something is missing that you wish existed, that's a **feature request**,
  not a bug — keep a list. You can ask Claude to draft a spec for any of them.
- Blocked more than 2 minutes? Note it, skip it, keep moving. Message Mical if
  the whole thing is stuck.

## What counts as a serious problem (tell Claude immediately)

- You can't install or open the app
- A save, connect, import, or voice action fails with no way forward
- A student's full name is spoken aloud or printed in generated worksheets
- The app records a language level (like "A2") you never said or typed
- Anything that looks like real private data where it shouldn't be

## Your feedback is the point

Chip tested whether the buttons work. You're the only person who can tell us
whether the app fits how a teacher actually observes, plans, and teaches. When
Claude asks the feedback questions at the end, the pedagogy answers — "this
field doesn't match how I think about my students" — are worth more than any
bug report.
