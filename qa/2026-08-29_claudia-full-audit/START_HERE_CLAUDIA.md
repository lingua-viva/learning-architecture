# Claudia — Start Here (2026-08-29) — The Full Audit

## What you're doing

The **fullest audit of Lingua Viva yet** — every teacher-facing surface, in
real time, on your own computer, on the app exactly as any teacher would
download it. No special access, no developer build. If it doesn't work for
you tonight, it doesn't work for any teacher.

This covers everything from the 08-10 plan (56 checks) **plus** everything
shipped since: the lesson-plan creation loop, the document-to-lens student
import, the honesty surfaces (the app now tells you when an answer is
unverified, what route your question actually took, and what really happens
to a safeguarding note), and the UX pass built from your own feedback.

**~2 hours, with a natural break point halfway.** Claude Code walks you
through everything one step at a time. Reply "done" after each step, or
describe what looks wrong — in your own words, in whichever language comes
first.

## Before you start

1. **Update your repo** — open Terminal and run:
   ```
   cd ~/learning-architecture && git pull
   ```
2. **Trash** any old Lingua Viva app (drag to Trash, empty it).
3. **Download fresh** from **linguaviva.art** — click the macOS download
   button. This fresh download IS the first test.
4. Install and open. Note every macOS permission dialog you see — they count.
5. In Terminal, type `claude`, press Enter, and paste this:

   ```
   Read and follow ~/learning-architecture/qa/2026-08-29_claudia-full-audit/HARNESS_PROMPT.md
   ```

## Version gate

The app must say **desktop-v0.2.72 or newer** (version badge in the topbar,
or Settings). If it says v0.2.71 or older, STOP and tell Claude — that means
the release didn't ship and it's the first finding of the night.

## Rules

- **Fake data only.** Two test students: **Marco Bianchi** and **Nora Rossi**.
  Never type a real child's name, ever — not even to show that something's
  broken.
- If something breaks, don't fix it — describe what you see. That IS the job.
- If you're blocked for more than 2 minutes, say so and skip.
- Judge everything as a teacher at 8am on a Monday: would this help you,
  confuse you, or waste your time? Say which, out loud.

## What counts as a serious problem

- The app won't install, open, or reach its home screen
- Anything that shows a raw error, a traceback, or "Request failed: 404"
- An answer about a student that sounds confident but shows **no** sources
  and **no** "unverified" warning — the app is supposed to catch that itself
- A safeguarding note that claims someone was notified when nobody was
- A real-looking claim about what the app did that you can prove false
- Any screen where you genuinely don't know what to do next

## What's different about this audit

Claude will file your findings **as you say them** into a live report
(`REPORT.md` in this folder). You'll see the running count. Nothing gets
softened or summarized away — your words go in as findings, and every finding
gets an ID. When you're done, the report is the truth of the night.
