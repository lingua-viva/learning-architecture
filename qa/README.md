# QA — Lingua Viva

This folder is where all Lingua Viva QA test packets, session reports, and
evidence live. **If you ran a test session, your report belongs here.**

## Where reports go

```
qa/
  README.md                          — this file
  YYYY-MM-DD_<description>.md        — session reports (one file per session)
  packets/                           — test packets (the scripts you follow)
  traces/                            — app.log, events.log, API outputs per session
  screenshots/                       — UI evidence, descriptive filenames
```

Example report filename: `2026-08-03_teacher-readiness-claudia.md`

## Conventions

- One report file per QA session, at the top level of `qa/`.
- Every report includes: app version tested, repo commit hash, what passed,
  what failed, steps to reproduce failures, and the tester's own feedback in
  their own words.
- Traces for a session go in `traces/<session-name>/`.
- When committing, stage **only** files under `qa/` with explicit paths
  (`git add qa/...`). Never `git add -A`. Never commit anything outside `qa/`.
- Commit message: `qa: YYYY-MM-DD <short description>`

## Privacy — the one hard rule

**Synthetic data only.** The test students are **Marco Bianchi** and
**Nora Rossi** — invented children. No real student name, record, photo, or
detail may ever appear in a test session, report, trace, or screenshot. This
repo is public. If real data slips in, stop and remove it before committing.

## Current packet

- `packets/teacher-readiness-2026-08-03/` — Claudia's teacher-readiness run
  (start at `START_HERE_CLAUDIA.md`)
