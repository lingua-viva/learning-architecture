# BUILD PROMPT — LV Demo-Eve Fix Wave (v2) — 2026-08-19 night

You are the fix agent for tonight's wave in `~/learning-architecture`. The live demo is
TOMORROW MORNING (2026-08-20). Everything ships as one wave with ONE push tonight. If
you already ran the window-prep instructions, your prep findings stand — proceed. If
not, do the prep steps embedded below as you go.

## What happened since the last build
desktop-v0.2.65 (the v1 real-data fix wave) went through a full independent test with
the REAL teacher on screen and a conductor capturing backend state. The verdict is the
best kind of MIXED: **zero contradictions between screen and backend** — the five lying
patterns are dead; the app now tells the truth about itself — but **three capability
defects block the demo**:

1. **Importing her class fabricates children (18 → 35).** The sheets carry stacked
   group tables (Music / STEAM) below the roster; each group-table column holds a WHOLE
   name, and the roster's surname+firstname join rule fuses two real children into one
   non-existent student. No per-entry remedy in the preview.
2. **Ask invents progress from zero data.** Observations 0, evidence 0, CEFR all null —
   and it still said the child was "making good progress", aloud. Hedged as
   "weak source" when the truth is "no data".
3. **The printable packet silently RE-GENERATES.** Three fresh model calls on preview;
   what prints is not what the teacher reviewed. Her review is meaningless, and the
   (intermittent) broken Italian she rejected can reappear at print time.

The teacher's own words: "I would not hand these 3 cards to my students." That sentence
is what tonight removes.

## Read, in order
1. `~/Downloads/BASELINE_REPORT_v0.2.65_2026-08-19.md` — the test report. Do NOT
   commit it. Findings 1–8, the verified-fixed table, and the empty Contradictions
   section are your map of what to fix and what to not break.
2. `dev/SPEC_LV_DEMO_EVE_FIX_2026-08-19.md` — THE binding spec for tonight: F1–F6 in
   order, §1 ground-truth procedure, §4 constraints, §5 gates.
3. `dev/SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.md` — the v1 spec, for architecture
   context (preview path, corpus/scorer, locks). Its expected-count numbers are
   SUPERSEDED by tonight's spec §1.
4. `AGENTS.md` — PUSH definition + 7-step verification.

## The one rule that overrides every document
**No expected student-count from ANY document is trusted.** Our docs have been wrong
twice (~39, then 20/41). The teacher counts 18 in her class. Counts are established
only by: fixed extractor prints the roster names per class column → human confirms →
label sealed. Your fix is STRUCTURAL (roster block only, one column-pair, join rule
scoped to the roster block); the number falls out of correct structure.

## Build order (spec §2)
F1 (roster-block segmentation — the fabrication killer) → F1b (per-entry exclude in
preview, if evening allows) → F2 (zero-data refusal gate in Ask) → F3 (packet renders
the STORED reviewed artifact, zero model calls on print path, explicit Regenerate) →
F4 (surface version in UI) → F5 (fix the lying import copy + xlsx guidance) →
F6 items only if time truly permits.

F1, F2, F3 are each demo-blocking. Do not gold-plate F1 at the cost of F2/F3.

## Hard constraints — violating any ends the run
- The four uncommitted .deb WIP files appear in ZERO commits: both workflow files,
  `desktop/electron/deb-after-install.sh`, and the deb hunks of `desktop/package.json`.
  Hunk-isolate. F4 may legitimately touch `desktop/` — stage only your own hunks.
- ONE push, at the very end, after every §5 gate. Auto-release fires per push.
- Privacy: no real student/colleague/school names committed anywhere. Real-file runs
  and extracted name lists stay local. Committed fixtures use synthetic names but the
  REAL structure (two class column-pairs + three stacked tables per sheet).
- `MC_AGENT=1` on every run.
- No name blocklists — positive structural conditions only.
- Locks stay green: preview-never-writes; enrichment/support imports never grow the
  student count; curriculum/calendar yield zero.
- Do not break what the report verified fixed (its "genuinely fixed" table is a
  regression list: preview-no-write, cancel-no-trace, teachers-not-students,
  no-template-filler, route=local on student questions, packet excludes support
  content, non-blank foundational, real-title metadata).

## Verification and shipping (spec §5)
Suite green → new class-lock tests green (F1 fixture / F2 refusal / F3
zero-calls-on-print) → scorer on relabeled corpus → real-file local run with human
count confirmation (expected 18; STOP and ask the operator to confirm the printed
list) → `lv preflight` → UI contract bump → Claudia-lens audit → ONE push → AGENTS.md
7-step verification (run green, release assets 200, pin advanced, cache-busted site
check). Then write `dev/REPORT_LV_DEMO_EVE_FIX_2026-08-19.md` (per-fix evidence,
confirmed count, known-open list: Finding 3 model-bound Italian quality, Finding 5
extraction depth, spec §3 items) and update `dev/INDEX.md` in the same commit.

If any gate is red at push time, stop and report — a truthful "not shipped" beats a
hollow release on demo eve.
