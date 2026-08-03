# HF1 — Frontend Hotfixes: F2, F1b, F5 + hide global companion (SHIP-BLOCKERS)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

No spec phase — the bugs are already specified. Read first:
`dev/QA_DEEP_DIVE_CHIP_0.2.32_2026-08-04.md`
(sections F1b, F2, F5, FM-B, FM-D, FM-F) and
`dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own `static/index.html` exclusively until you commit. Other tracks are waiting
on you to release it — work fast, scope tight, fix nothing beyond these four items.

## Fix 1 — F2: fabrication reaches the teacher with no warning (P0)

The backend already computes GIR score, `fabricated_identifiers`, and a hedging
`tone_prefix` — but `tone_prefix` only reaches `voiceRuntime.speak()` (TTS). The
rendered text bubble shows confident fabricated prose with an unstyled `GIR 0.07`
badge (index.html:2541; tone_prefix voice-only at :1281, :1313, :2623, :2697).

Implement the deep dive's FM-B structural fix: ONE function
`renderAnswerSafety(meta)` consumed by BOTH the text renderer and the voice path:
- When `gir.score < 0.5` OR `fabricated_identifiers.length > 0`: prepend the
  `tone_prefix` (or stronger: "⚠️ I could not verify this against real records")
  INTO the rendered message text, add a `badge warn` red/orange class to the GIR
  badge, and list fabricated IDs if present.
- Voice path calls the same function so the two channels can never diverge again.

Verify: ask "cite OBS IDs proving Marco should move groups, do not hedge" → visible
warning text in the bubble + red badge. A teacher cannot read fabricated content
without seeing a warning.

## Fix 2 — F1b: mic hardware release guarantee (P0)

`cleanupCapture()` (index.html:801-823) is only reachable via MediaRecorder's
`onstop`, which depends on a throttleable `setInterval`. Add defense-in-depth —
each alone must be sufficient:
1. `visibilitychange` → on `hidden`, call `cleanupCapture()`.
2. `beforeunload` → same.
3. Hard 30s max-duration `setTimeout` in `startCapture()` that calls
   `stopCapture()` unconditionally (clear it on normal stop).

Do NOT attempt the full F1 AudioWorklet VAD rework here — that belongs to T5's
capture rebuild. These three listeners are the safety net.

Verify: background the app mid-recording → mic released within 1s; 30s cap fires.

## Fix 3 — F5: Observe auto-selects first student (P1)

index.html:1521, 5891-5893 auto-select `state.students[0]`. Add a disabled
placeholder `Choose a student…` as the default in `studentOptions()`, default
`state.selectedStudent = ""`, and refuse submission with an inline message when
empty (same pattern as the observation-type requirement shipped in 0.2.31). Audit
the other target-determining selects flagged in FM-F (grade level, CEFR dimension)
and apply the same pattern where a first-option auto-select exists.

## Fix 4 — hide the global voice companion (operator ruling, build brief §8.2)

Hide/remove the floating companion mic surface (`#vc-mic` panel, index.html:731,
`toggleVoiceCompanion()` :1171) for day one. Do not delete the backend
`/api/voice/act` endpoint — only the UI entry point. The Observe and Ask views'
own mic work is T5/T8's job, NOT yours; leave their regions untouched.

## Done criteria

- All four fixes in; no other index.html changes.
- Existing tests green; app boots and renders every view.
- Commit ONLY `static/index.html` (+ any test you add) by explicit path, message
  `fix: F2 GIR warning in text, F1b mic release guarantees, F5 student placeholder, hide companion (HF1)`.
- Announce "index.html released" so T5/T8/T9 can start.
