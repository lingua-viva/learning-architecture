# Lingua Viva — Status + Voice UX Regression Walkback
**Date:** 2026-08-04. Covers the voice walkback executed 2026-08-03 (evening) and where
the app stands as of today's push.

---

## 1. Where LV stands right now

- **Live build:** `desktop-v0.2.37`, on `origin/main` at `056a93b`. Signed
  (`✓ Signed by team: XWT7RB624U`, verified from the CI log, not just a green run).
  `docs/index.html` pinned to it; only that version is listed on the GitHub Releases page
  (older `desktop-v0.2.36`/`0.2.35` releases deleted so there's no ambiguity about which
  build a teacher gets).
- **Tests:** full suite 1973 passed / 13 skipped / 0 failed.
- **What works day-one:** typed Observe capture, lesson-materials generation
  (privacy-clean, no invented content), parent reports (safety gate fires, honestly
  hedged), archive, honest Ollama-down/recovery messaging, JSON errors everywhere.
- **Known open gaps (not fixed, flagged deliberately, not silently dropped):**
  - Add Student form has no last-name field and no grade-format validation — needs a
    product decision on what "grade" should accept, not a guessed patch.
  - Ask still refuses every student-named query (F3) — there is no working surface today
    for "what does Marco need?" grounded in his real observations. This is the same gap
    the voice walkback below is downstream of (see §2).
  - `src/lingua_viva/gap_audit.py` / `improvement_audit.py` still compute a bundle-relative
    state path (the same anti-pattern that caused the F6 regression elsewhere) — confirmed
    reachable only from the `lv` CLI, not the live app, so it's latent, not teacher-facing.

---

## 2. The voice regression — what went wrong

**Built Jul 28-29** (`faa79a3`, integration-loop sprint): a single **global voice
companion** — one persistent mic (`#vc-mic`) that classified intent from speech and
dispatched to Observe/Ask/generate. Per-surface mics (a dedicated Observe mic, a dedicated
Ask mic) were drawn in the UI but their handlers were never mounted — dead buttons.

**Diagnosed 2026-08-03**, two independent passes converged on the same root cause:

- **Chip's QA deep-dive on 0.2.32** (`mission-canvas/qa/2026-08-04_chip-qa-0.2.32_deep-dive.md`)
  found, among other P0s:
  - **F1** — silence detection (`setInterval` polling every 150ms) gets throttled by the
    browser to 1s+ in a backgrounded tab, so recordings either never stop or cut off too
    early; Whisper hallucinates filler words on the resulting sub-1s clips.
  - **F1b** — no guaranteed mic hardware release; the mic could stay physically live
    indefinitely (privacy + trust problem, not just a bug).
  - **F2** — GIR/fabrication safety signals (`tone_prefix`, `gir.score`,
    `fabricated_identifiers`) were computed correctly server-side but **only wired to the
    speech (TTS) path** — the rendered chat bubble showed an unstyled badge with no
    warning, so a teacher reading (not listening to) a fabricated answer saw nothing.
    Named as a systemic pattern: *"the client was built voice-first — all
    signal→action mappings target the speech path; text rendering was never updated to
    consume the same signals."*
  - **F5** — Observe auto-selected the first student in the roster by default, so a
    voice/text save with no explicit student choice could land on the wrong child.
- **Convergence brief** (`dev/CONVERGENCE_BRIEF_LV_VOICE_EXPERIENCE_2026-08-03.md`),
  written same evening from 4 independent lenses (operator framing, design take, Claudia
  Canu's lens, a UX-designer lens) plus a direct code audit, landed on one diagnosis
  verbatim across all of them (**D5**): *"the old two mics weren't wrong in shape, they
  were under-built... The universal companion then made voice carry intent that the view
  already carried."* One mic tried to be everywhere, so a teacher could never predict what
  tapping it would do — and worse, voice-initiated observations saved **immediately, with
  no review step** (`/api/voice/act` → direct `ObservationCapturePipeline` write), while a
  parallel propose-confirm system already existed (`/api/observe/classify`,
  `teacher_confirmation_required:true`) but was only reachable from the typed form's
  "Suggest fields" button — never from voice.

## 3. What we did to walk it back (2026-08-03, evening)

The convergence brief's own design fix (D1-D5: per-surface mic contracts, always-review,
retire speak-and-commit) was **accepted as correct**, but the operator re-ordered
priorities in a follow-up **build brief** (`dev/LV_BUILD_BRIEF_2026-08-04.md`, status:
RULED): voice stopped being the MVP for day one. Document ingestion and artifact
generation became P0; voice became secondary. Ruling §8.2, combined with the
Observe-only/Ask-only scoping in Q3, was explicit: **hide the global companion entirely
for day one — only per-surface mics (Observe + Ask) are the sanctioned path going
forward, no global dispatcher.**

That ruling was executed the same night in commit `97534fd`
(`fix: F2 GIR warning in text, F1b mic release guarantees, F5 student placeholder, hide
companion (HF1)`), against `dev/PROMPT_PAIR_HF1_FRONTEND_HOTFIX_2026-08-04.md`:

- **Companion hidden** — `<body class="voice-hidden">` in `static/index.html`; CSS rule
  collapses the companion panel and its layout gutter to nothing. The backend
  `/api/voice/act` endpoint was left untouched (removing the UI entry point, not the
  capability) — a one-line class removal restores it if ever needed.
- **F2 fixed structurally, not with a bandaid**: `renderAnswerSafety(meta)` is now the
  single safety gate consumed by *both* the chat bubble and every `speak()`/`speakQueue()`
  call — GIR < 0.5 or fabricated identifiers now prepend a visible warning into the
  rendered text, not just the spoken audio.
- **F1b fixed**: `visibilitychange` (tab hidden) and `beforeunload` both force
  `cleanupCapture()`; a 30s hard cap on `captureLocalStt` guarantees release even if a
  hidden tab throttles the normal stop path. Belt-and-suspenders, either alone is
  sufficient.
- **F5 fixed**: `ensureStudents()` no longer auto-selects the first roster entry;
  `studentOptions()` starts on a disabled "Choose a student…" placeholder; save/suggest/
  parent-draft all refuse with an inline message when no student is chosen.
- UI contract bumped to v101 to cover the `static/index.html` change; 10 new regression
  assertions added (`tests/test_hf1_frontend_hotfixes.py`) to lock the walkback in.

## 4. Where voice stands today, post-walkback

- **Global companion:** off by design (`voice-hidden`), not a bug. Copy that used to say
  "use the voice companion mic" now says "type below" on Observe.
- **Observe per-surface mic:** exists as the sanctioned flagship path (capture → structured
  extraction → review card → explicit Save), but today's `desktop-v0.2.36` QA
  (`qa/2026-08-04_chip-qa-0.2.36-macos-1.md`) found it **completely dead on macOS** — a
  missing `com.apple.security.device.audio-input` signing entitlement blocked the mic at
  the OS level regardless of user permission. Fixed and shipped live in `desktop-v0.2.37`
  today (§1).
- **Ask voice-first Perplexity path:** built separately (`f8bf166`, "ask: voice-first
  perplexity with PII egress gate, no redirect") as the brief's P1 item.
- **Explicitly still deferred**, per the build brief, no ETA: Prepare mic, student-profile
  mic, a real Command-voice grammar, and skip-review-at-high-confidence. These are staged
  as "own specs later," not forgotten.
