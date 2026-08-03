# LV Build Runbook — Document Pipeline + Hotfixes + Ask (2026-08-04)

**Purpose:** run order, dependency graph, and file-ownership matrix for the parallel
spec/implementation prompt pairs in `dev/PROMPT_PAIR_*_2026-08-04.md`.
**Source rulings:** `dev/LV_BUILD_BRIEF_2026-08-04.md` (operator-ruled)
**Bug source:** `dev/QA_DEEP_DIVE_CHIP_0.2.32_2026-08-04.md`
**Decomposition credit:** operator-provided decomposition (local scratch file, adapted — not in repo)

## What must work by morning (the honest bar)

Teachers come online 2026-08-04. In priority order, this is the day-one bar —
everything else is refinement over the following days:

1. **Observe works**: mic in Observe → dictation → parse-on-save → editable
   record → saved to the lens. (Critical path: T0 → T2 → T4 → T5.)
2. **Lenses exist to observe into**: Students-from-file ingest creates lens
   scaffolds from real documents (T9, on T1/T2/T3/T4). If Drive slips, local-file
   ingest alone is acceptable for day one.
3. **Nothing lies and nothing leaks**: HF1 (fabrication warning, mic release,
   student placeholder) + HF2 (honest no-model messages) + T8's PII egress gate.
4. **Ask answers general questions by voice** (T8): Perplexity → spoken summary
   → full text lands in the Ask tab to read/track/copy-paste. No artifacts, no
   redirect — that's the whole feature for now.
5. **Drive write-back** (T6): wanted, but a local-only loop with manual sync is
   an acceptable day-one fallback. The loop must work with NO internet at all —
   offline is a supported state, not an error state.

"Working at all" beats polished. Wrong output is worse than missing output.

## Operator rulings 2026-08-03 (post-authoring — bind all tracks)

- **Ask scope**: questions → Perplexity → voice answer + text populated in the
  Ask tab for tracking/copy-paste. No artifact creation in Ask yet.
- **One student lens format only.** T4's bridge to the existing
  `StudentLensStore` is mandatory — no competing formats. (A separate *teacher*
  lens comes later; not in this build.)
- **By tomorrow: working at all.** Refinement comes after.
- **Offline-first confirmed**: everything except the Perplexity call and Drive
  sync must work with no internet.

## How to run a track

Works on ANY machine with a clone of `lingua-viva/learning-architecture`
(`git@lingua-viva:lingua-viva/learning-architecture.git`; `git pull` first —
these files live on `main`). Open a fresh Claude Code window at the repo root
and paste:

```
Read and execute dev/PROMPT_PAIR_<TRACK>_2026-08-04.md — Phase 1 (spec) first,
then Phase 2 (implementation) in the same session unless the file says otherwise.
```

## Dependency graph / waves

```
WAVE 1 (start NOW, 3 parallel windows — disjoint files):
  T0   Contract freeze                     ← BLOCKING for T1–T7 (~45 min)
  HF1  Frontend hotfixes  (F2, F1b, F5)    ← ship-blockers; owns static/index.html until done
  HF2  Backend hotfixes   (F4, F6)         ← reasoning.py + doctor/support_loop/paths.py

WAVE 2 (after T0 lands; HF1 must land before any index.html track starts):
  T1   Drive ingest connector      ┐
  T2   Vault store  (CRITICAL)     │  all parallel, build against T0 fixtures
  T3   Grounded extraction         │
  T4   Lens engine  (CRITICAL)     ┘
  T8   Ask = Perplexity voice-first   (independent of pipeline; needs HF1 done)

WAVE 3:
  T5   Observe capture path (CRITICAL — the demo)   needs T0 + HF1; fixtures until T4
  T6   Drive write-back                              needs T1
  T9   Ingest UI (Students-from-file, one tab only)  needs T1+T2+T3+T4

WAVE 4:
  T7   E2E integration + grounding audit — the release gate
```

**Critical path for a working demo: T0 → T2 → T4 → T5.** T1/T6 are the Drive
bookends — if they slip, the loop works local-only and syncs manually. Never let
them block T5.

## File-ownership matrix (parallel-session collision control)

| Track | Owns (exclusive while running) |
|---|---|
| T0 | `dev/CONTRACTS_V1_2026-08-04.md`, `src/lingua_viva/docpipe/` (stubs+schemas), `tests/fixtures/docpipe/` |
| HF1 | `static/index.html` (until it commits — then released to T5/T8/T9) |
| HF2 | `src/lingua_viva/reasoning.py`, `src/pipeline.py` (breaker only), `doctor/support_loop/paths.py` |
| T1 | `src/lingua_viva/docpipe/drive.py` + its tests |
| T2 | `src/lingua_viva/docpipe/vault.py` + its tests |
| T3 | `src/lingua_viva/docpipe/extract.py`, `jobs.py`, `grounding_docs.py` + tests |
| T4 | `src/lingua_viva/docpipe/lens.py` + its tests |
| T5 | `static/index.html` Observe region, `src/web.py` observe/voice endpoints |
| T6 | `src/lingua_viva/docpipe/sync.py`, `drive.push_file` + tests |
| T8 | `static/index.html` Ask region, `src/web.py` ask/perplexity endpoint |
| T9 | `static/index.html` Students region, one `src/web.py` ingest endpoint |
| T7 | `tests/e2e_docpipe/`, `scripts/` runner |

Rules: commit ONLY your owned files, by explicit path — never `git add -A`. If you
must touch a file another track owns, stop and coordinate via the operator.
T5/T8/T9 all touch `static/index.html`: they may run in parallel only if each stays
strictly inside its view region; otherwise serialize T5 → T8 → T9.

## Cross-cutting rules (every implementation prompt inherits these)

1. **Local models only.** All model calls go through the `ModelClient` protocol from
   T0; only `LocalModelClient` exists. Assert at import that no external endpoint is
   configured. (Exception: T8's Perplexity call, governed by its own PII gate.)
2. **No field without evidence.** Ungrounded output is a bug, not a degradation.
   Extends the invented-clinical-defaults defect class.
3. **Vault path is `~/.lingua-viva/vault/`** via `LV_STATE_HOME` — never
   bundle-relative (F6). The vault module is the ONLY writer of disk state.
4. **Packaging trap:** `desktop/package.json` `extraResources.filter` is an explicit
   allowlist. `docpipe/` lives INSIDE `src/lingua_viva/` so it ships automatically;
   do NOT create new top-level packages. If you must, add them to the filter and
   verify with `--appimage-extract` + import.
5. **Empty on install.** No seed data, no demo content, no placeholder brackets.
6. **Slow is fine, wrong is not.** Long-running work = background jobs with progress,
   never blocking the UI, surviving restart.
7. **Christi's 10 profile categories** are the lens's first-class fields: Learning
   and Cognition; Communication and Language; Executive Functioning; Social Skills;
   Emotional Regulation; Physical/Sensory Needs; Attendance and Engagement;
   Strategies trialed (with successful-or-not outcome); Academic Strengths; Personal
   Strengths. Align IDs with the existing `support_category` enum where it overlaps
   (`executive_functioning`, `communication_and_language`, …) — do not invent a
   parallel taxonomy.
8. **Regression floor:** existing tests green; `lv eval teacher-readiness` ≥ 16/19.
9. **Student resolution:** ambiguous → ask, NEVER guess. No invented students,
   CEFR values, or clinical defaults, ever.
10. Specs land in `dev/` with a same-day status line; never repo root. `docs/` is
    the live GitHub Pages site — nothing lands there except deliberate site changes.

## Adopted assumptions from build brief §8 (operator may veto)

- §8.1: keep edit-before-commit on Observe saves AND add Drive write-back (both).
- §8.2: global voice companion `#vc-mic` is hidden for day one (HF1 does this).
- §8.5: Observe gets STT (dictation); TTS belongs to T8/Ask.
- F3 (deep dive) is SUPERSEDED by the Ask=Perplexity ruling: Ask never reasons over
  student data. The fix is an egress gate (T8), not observation injection. F2's
  rendered warning (HF1) is the stopgap until T8 lands.
- Chip's QA prompt (`dev/PROMPT_CHIP_QA_0.2.32_2026-08-04.md`) tests flows this
  build removes — it must be re-issued after the build; not this runbook's job.

## Release gate

T7's grounding audit is the gate: if ANY vault field anywhere is populated without
valid `evidence[]`, the suite fails and the build does not ship. Ship mechanics
follow `AGENTS.md` 7-step push verification as always.
