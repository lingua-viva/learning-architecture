# SPEC — Voice Scope, Narrowed (Scope Ruling + One P0 Wiring Fix) — 2026-08-08

**Priority: P2 — DO NOT START before both P0 pairs ship**
(`SPEC_LV_STUDENT_LENS_FULL_CIRCLE_2026-08-08.md`,
`SPEC_LV_TIERED_MATERIALS_FULL_CIRCLE_2026-08-08.md`), **EXCEPT §1, which is P0 and may
ride with either P0 build.**

## Operator ruling (2026-08-08)

The long-term vision stands: ask-for-help anywhere, from any screen, Perplexity-backed.
We are far from it, and the last build round drifted toward full voice re-integration.
**Scope is frozen to exactly two surfaces:**

1. **Isolated mic for Observe** — voice capture exists only inside the observation flow
   (student lenses). Local Whisper (`voice_stt.py` `WhisperLocalProvider`), transcript
   editable, saved via the normal observation path. No ambient/global mic.
2. **ASK-anywhere with a persistent thread** — the Ask entry point is reachable from any
   screen, but it is a *portal to one thread*: every exchange lands in the single Ask
   panel thread. Asking from another screen does NOT navigate away — the answer appears
   in-place, and the full thread is there when the teacher clicks into the Ask panel.

Anything beyond these two surfaces — voice in planning, TTS on tier packets, global
wake/ambient listening, voice intent routing expansion — is out until the operator
re-opens scope. `SPEC_LV_VOICE_INTENT_ROUTER_2026-08-01` and
`SPEC_LV_FRONTEND_VOICE_WIRE_2026-08-01` remain reference material, not active mandates.

## §1 — P0: wire Ask's existing grounding to the surface (from QA, arc 0.2.36-0.2.42)

The backend already computes honesty; the surface discards it. QA showed Ask rendering
confident fabricated answers while the backend produced `gir: 0.0` and a `tone_prefix`.
The parent-report/student-summaries path proves the plumbing works
(`grounding/build.py`, `voice_tone.py` `resolve_voice_tone`); Ask's free-text
`run_teacher_query()` path (`src/lingua_viva/app.py`) is simply not wired to it.

Fix (wiring, not building):
- Ask responses carry their `GroundingResult` (or at minimum `gir` + tone tier) to the UI.
- UI renders the tone prefix and a visible grounding state on every Ask answer:
  plain (≥0.8) / "let's double-check" (0.4-0.8) / "no solid source — starting point, not
  a final answer" (<0.4), matching `resolve_voice_tone` thresholds exactly.
- If any Ask answer is spoken (TTS), the spoken text = prefixed text — never fabrication
  metadata, never unprefixed low-GIR content.
- Test: an Ask query with empty sources renders (and speaks, if spoken) the boundary
  prefix. This locks the class: **no surface may render an answer while dropping its
  grounding verdict.** (Claudia's own test — "what would Marco need" with no data — is
  the golden case: the app said "not enough data." Keep it true on every path.)
- Fix known Observe/Ask voice defects only if trivially adjacent: TTS locale (Italian
  voice on English text) is a one-line config class of fix — take it. Mic-release lag
  and stop-control are REAL but belong to the P2 build, not this fix.

## §2 — P2 build (deferred): the two surfaces, hardened

When the operator re-opens scope: Observe mic release <1s on app switch + visible
stop control; Ask-anywhere entry point on every screen; thread persistence across
sessions; nothing else. Full spec pass at that time — do not build from this paragraph.

## Acceptance for §1 only
1. Every Ask answer shows grounding state; low-GIR answers carry the boundary prefix in
   text and speech.
2. Class-locking test in place (no answer surface without its verdict).
3. No regression in Ask latency worth a teacher noticing; suite green; ships with
   whichever P0 release goes next.

## Carried-over pending items (parked here for the convergence brief, 2026-08-08)

Not voice work — parked in this file only because it's the next thing the operator opens.
None of these are scoped or built; do not start any of them from this note alone.

- **Confidential/CPS-flagged category + Drive-folder-routed permissions** — the
  folder-map plumbing (fail-closed "Personal" category, routing) ships inside Pair 1's
  G3 (`SPEC_LV_STUDENT_LENS_FULL_CIRCLE_2026-08-08.md`). What's still genuinely open:
  the CPS/abuse-sign classifier itself, blocked on Christianna's exhaustive category
  list — she committed to sending it, hasn't yet.
- **Rename parent-facing summary → "Student Summaries"** — ships inside Pair 1's G5,
  its own trivial commit. Listed here only to confirm it's covered, not orphaned.
- **Rubric-generator / assessment fields** — still fully unscoped. Explicit non-goal in
  both P0 pair specs. Waiting on the team's own answer to "let me know what you want
  assessed and how" from the 2026-08-06 sync — no build without that input.
- **Slack bot integration** — still fully unscoped. Explicit non-goal in both P0 pair
  specs. Waiting on one concrete Slack use-case from the team (Olga hadn't even read
  the proposal as of the 2026-08-06 sync) — no build without that input.
