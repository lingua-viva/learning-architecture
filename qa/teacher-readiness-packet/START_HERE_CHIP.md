# Chip — Start Here (2026-08-10)

## What you're doing tonight

Testing **Lingua Viva** end-to-end before it goes to real teachers tomorrow.
**56 checks across 14 areas** — everything from the last packet (Drive,
documents, voice, worksheets, sync, planning, app health) **plus the new
stuff built this week**: safeguarding routing, parent reports, coursework
packs, library search, and student progression panels.

You test by hand. Claude Code does everything technical and walks you through
each click. Full pass is roughly 2 hours; it's fine to stop partway — just
tell Claude "I'm done" and it reports on whatever you finished. If you're
short on time, Claude knows which areas matter most and will prioritize.

## One thing that's different tonight

**The install itself is a test.** Earlier today we found that a brand-new
install can fail to start on some machines. If the app won't open or hangs on
setup — **that's not you doing something wrong, that's exactly what we're
hunting.** Tell Claude immediately; it will collect the evidence and that
alone is a hugely valuable result.

## Before anything else — GitHub access (2 minutes)

1. Open: **https://github.com/pretendhome/mission-canvas/invitations**
2. Make sure you're logged in as **DontWriteDown**.
3. Click **Accept invitation** (if it says "no pending invitations", you
   already accepted — fine, Claude verifies either way).

## The whole workflow (same 4 moves as always)

1. **Trash** any old Lingua Viva app on your Mac.
2. **Download fresh** from **linguaviva.art** (the site's download button —
   not a GitHub page), install, open.
3. Open Terminal, type `claude`, press Enter, and paste this ONE line:

   ```
   Clone or update the public repo https://github.com/lingua-viva/learning-architecture (git pull if you already have it), then read and follow qa/teacher-readiness-packet/HARNESS_PROMPT.md inside it.
   ```

   That's it — no downloading or unzipping test files anymore. The test
   packet lives in the repo and Claude always fetches the latest version.

4. **Follow Claude's steps one at a time.** Reply "done" after each, or
   describe what looked wrong. When you finish (or run out of time), say
   **"I'm done"** — Claude collects your feedback, writes the report, and
   publishes it for Mical automatically.

## Rules

- **Fake data only.** The two test students are **Marco Bianchi** and
  **Nora Rossi** — invented. Never type a real child's name.
- One test area (safeguarding) has you type some upsetting-sounding sentences
  about Marco. **They're invented, about a fake child, on purpose** — we're
  testing that the app locks that kind of note away properly. Type them
  exactly as Claude gives them to you.
- If something breaks, don't fix it — describe it. That IS the job.
- Something missing you wish existed? That's a **feature request**, not a
  bug — keep a list; Claude can draft a spec for it.
- Blocked more than 2 minutes? Note it, skip it, keep moving. Text Mical if
  the whole thing is stuck.

## What's in the packet (Claude fetches it for you)

- `QA_TESTING_PLAN.md` — the full 56-check script (Claude reads this and
  leads you — no need to memorize)
- `HARNESS_PROMPT.md` — the harness instructions (the one line above points
  Claude at it)
- `documents/` — synthetic files you'll upload to Google Drive (Claude will
  open the folder for you when it's time):
  - `G3_family_relationships_unit.pdf` — fake curriculum unit
  - `student_record_marco_bianchi.md` — fake student record
  - `student_record_nora_rossi.md` — fake student record

## What counts as a serious problem (tell Claude immediately)

- You can't install or open the app (**most valuable finding tonight**)
- A save, connect, import, or voice action fails with no way forward
- A student's full name spoken aloud or printed in generated worksheets
- The upsetting test sentence from the safeguarding area showing up anywhere
  it shouldn't — the student's normal record, a worksheet, a parent report
- Anything that looks like real private data where it shouldn't be
