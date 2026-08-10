# HANDOFF — Kiro Session 2026-08-03/04/06 → Next Window

**Written by:** kiro.design
**Date:** 2026-08-06
**Repo:** `~/learning-architecture` (lingua-viva/learning-architecture)
**HEAD:** `a8300bb` (pin desktop-v0.2.43)
**Latest release:** desktop-v0.2.43

---

## What happened this session (3-day marathon)

### Night 1 (2026-08-03): The build wave + closure

The v0.2.35 build wave landed T0/HF1/HF2/T2/T4/T6/T8/T9 but T1/T3/T5 never reached
origin from the other machine (postmortem: push credentials silently revoked). I was
brought in as closer. Built:

- **T5 (Observe mic)** — mounted mic button, wired to `captureLocalStt` with
  conversational accumulation, form-gated save
- **A3** — global JSON exception handler (no more bare 500 text strings)
- **A4** — observation type defaults to "general" (not forced); CEFR/SEL nulled on general
- **B1-B5** — refusal wording, TTS locale detection, Settings panels (Voice/Sync/Privacy),
  Sources navigation link, `/api/sync/status` endpoint

T3 (extraction) was built by Codex and landed separately (`58695ee`).

### Night 2 (2026-08-04): QA reports → fix cycles

Three QA reports came in (Windows operator, Chip macOS×2). Fixed:
- P0-A: OpenMP DLL collision (KMP_DUPLICATE_LIB_OK=TRUE)
- P0-B: Windows orphan backend + port cleanup + log-to-file
- P1-1: macOS mic entitlement (com.apple.security.device.audio-input)
- P1-2: jsonschema missing from deps
- P1-3: Invented CEFR levels on general type
- P1-4: F4 regression (external ontology default_model skipped when unreachable)
- P1-5: PYTHONDONTWRITEBYTECODE=1
- P1-9: routing_memory.py bundle-relative path

Then v0.2.38 QA report arrived — fixed:
- P0-1: Mic release on background (MediaRecorder.stop() in cleanupCapture)
- P1-1: F6 bundle-write in 6+ files (improvement_audit, teacher_readiness,
  learned_weights all redirected to state_home)

### Day 3 (2026-08-06): Review pass + plan

Reviewed and committed Claude's Add Student grade validation + Lens Primitive DOES
boundary (narration never leaves machine). Fixed test hermeticity (CandidateStore
writing to tracked files during pytest). Current build plan for the next two weeks
is in `dev/BUILD_PLAN_TWO_WEEK_2026-08-06.md`.

---

## Current state

### What works (confirmed by QA across Mac + Windows)
- Typed observations → saved to lens with Christi's 10 categories
- Voice dictation in Observe (mic → transcript → edit → save)
- File import → extraction → grounded lenses (T3+T9)
- Ask with Perplexity (PII gate refuses student-named queries, honest)
- Offline-first (everything except Perplexity works with no network)
- Empty on install, no seed data, no invented content
- Honest degradation everywhere (no model → honest message, not a lie)
- Narration stays local (DOES boundary at export)

### What's broken / known open
- **F2 fabrication** in `/api/query` pipeline — GIR warning computed but not surfaced
  in rendered text. Currently hidden from teachers by Ask privacy gate (refuses first).
  The pipeline bug is live but unreachable through normal UI.
- **Governance/trust page undercounts** observations and student-named questions
- **Settings page may be missing** in some builds (dead references in Home/Sources)
- **Sidebar scrolls with content** (should be position-fixed)
- **Perplexity + Rime keys** have no persistent Settings UI — only env vars work

---

## What to build next (priority order from dev/BUILD_PLAN_TWO_WEEK_2026-08-06.md)

1. **Fix class-list upload** — accept .xlsx/.docx (Olga is blocked TODAY)
2. **Require confirmation before roster-import creates students** (prevents bulk auto-create)
3. **Bulk delete/undo-by-import** (Olga needs cleanup)
4. **Grades 1-12** (decouple from curriculum content coverage)
5. **Perplexity + Rime key persistence** (Settings section that actually writes to config)

Gated on external input (don't start without it):
6. Confidential/CPS category (waiting on Christianna's abuse-signs list)
7. Manifesto 9 traits on student profile
8. Trait mapping (observation → trait key)

---

## Files to know

| File | Role |
|------|------|
| `dev/BUILD_PLAN_TWO_WEEK_2026-08-06.md` | The active plan — read this first |
| `dev/CLOSURE_WORKLIST_2026-08-04.md` | Original gate structure (mostly closed) |
| `dev/SPEC_LENS_PRIMITIVE_2026-08-04.md` | Privacy architecture (DOES boundary) |
| `dev/ADD_STUDENT_FORM_DECISION_2026-08-04.md` | Grade validation decision |
| `dev/CONTRACTS_V1_2026-08-04.md` | Docpipe schemas (frozen, T0) |
| `dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md` | Original wave plan (historical) |
| `qa/2026-08-04_chip-qa-0.2.36-macos-1.md` | Chip's detailed QA (29 evidence files) |
| `qa/2026-08-04_teacher-readiness-claudia.md` | Claudia's live teacher QA |

---

## Uncommitted files on disk

```
?? dev/BUILD_PLAN_TWO_WEEK_2026-08-06.md
?? dev/PROMPT_CHIP_QA_0.2.42_2026-08-06.md
?? dev/PROMPT_CLAUDIA_DEMO_REHEARSAL_2026-08-06.md
?? dev/PROMPT_LV_TWO_WEEK_PHASE1_BUILD_2026-08-06.md
```

These are ready to commit — they're plan/prompt docs, no code changes.

---

## Standing rules (from palette-core + this project)

1. **Wrong output is worse than missing output.** Never invent data.
2. **No field without evidence.** Ungrounded output is a bug.
3. **Vault is the only writer of disk state** (docpipe path).
4. **Local models only** in the document pipeline (ModelClient protocol).
5. **Commit only owned files by explicit path.** Never `git add -A`.
6. **"Pushed" means downloadable from the site button.** Nothing else.
7. **Empty on install.** No seed data, no demo content.

---

## Slack context

The team (Federica, Christi, Olga, Claudia) is actively using the app as of this week.
Next sync call: Thu 2026-08-20. Olga has questions in `#ai-lingua-viva` that need
answers (file upload broken, accidental student creation, setup guidance, grades 1-12).
Commitment on the call: "I'll see you in two weeks with all that stuff built."
