# Claudia — Start Here (2026-08-12)

## What you're doing

Testing **Lingua Viva v0.2.56** — the build that fixes the bug Chip found
tonight. She discovered that selecting a student in Observe and then switching
to Students causes errors. We fixed it and need you to verify it's gone, then
walk through the core teaching workflows to make sure nothing broke.

**~45 minutes.** Claude Code walks you through everything step by step.
Reply "done" after each step, or describe what looks wrong.

## Before you start

1. **Trash** any old Lingua Viva app.
2. **Download fresh** from **linguaviva.art** — click the download button for
   your platform.
3. Install and open.
4. Open Terminal, type `claude`, press Enter, and paste this:

   ```
   Read and follow ~/learning-architecture/qa/2026-08-12_claudia-state-leak-verification/HARNESS_PROMPT.md
   ```

## Rules

- **Fake data only.** Two test students: **Marco Bianchi** and **Nora Rossi**.
  Never type a real child's name.
- If something breaks, don't fix it — describe what you see. That IS the job.
- If you're blocked for more than 2 minutes, skip it and tell Claude.

## What counts as a serious problem

- The app won't install or open
- Student data from one tab "follows" you to another tab (that's the bug
  we're checking is fixed)
- An error message that takes over the whole page
- "Request failed: 404" appearing anywhere on screen
- A real child's name appearing in generated materials
