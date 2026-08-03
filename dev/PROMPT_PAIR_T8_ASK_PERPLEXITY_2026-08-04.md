# T8 — Ask = Voice-First Perplexity (Wave 2, after HF1 releases index.html)

**Deadline context:** real teachers start using this app on 2026-08-04 — tomorrow
morning. Ship the smallest honest version of this track that genuinely works;
refinement comes over the following days. Wrong output is worse than missing
output. See the runbook's "What must work by morning" list before scoping down.

Independent of the document pipeline. Read first:
`dev/LV_BUILD_BRIEF_2026-08-04.md` §5,
`dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md`.
You own: the Ask region of `static/index.html`, the ask/perplexity endpoint in
`src/web.py`, + tests. Stay out of Observe/Students regions (T5/T9 own them).
Reference screenshot for text rendering:
`dev/assets/ask-render-reference-2026-08-03.png`.

**The ruling:** Ask is EXTERNAL information retrieval only. It does not reason
over student evidence, does not generate materials, and **no personal data ever
leaves the machine on any Ask call**. This supersedes deep-dive F3 ("inject
observations into Ask") — student questions are not Ask's job anymore.

## Phase 1 — Spec prompt

Spec voice-first Ask. Output `dev/SPEC_T8_ASK_2026-08-04.md`, no code.

**Before speccing, locate the existing plumbing** (reuse, don't duplicate):
Perplexity routing/client (LV inherited external routing + sanitizer from MC —
find the existing egress path and allowlist), the student-name detection step
(`src/pipeline.py` ~:297-341, currently a local_only privacy gate), TTS via
`voiceRuntime.speak()`, and HF1's `renderAnswerSafety()`.

Cover:
- **UI**: button labeled **"ASK"** (not "Mic") with a few example questions
  displayed underneath ("What are strategies for a student with ADD in a language
  immersion classroom?" etc. — brief §5.1). Mic input dictates into the question
  box via `captureLocalStt`; typed input works identically.
- **Backend**: Perplexity only. Whatever Perplexity returns is what the teacher
  gets — no post-processing layer. Response length capped to a one-paragraph
  summary via the API call parameters, then *"Would you like to hear more?"*;
  "more" fetches/plays the continuation.
- **The PII egress gate (the hard requirement)**: before ANY payload leaves the
  machine, run student-name detection against the live roster + the existing
  sanitizer. If a student name (or other personal identifier) is detected:
  REFUSE the external call with an honest message — "Ask answers general teaching
  questions from the web. Information about your students lives in their lens —
  nothing personal is ever sent off this machine." Log the block to the privacy
  log. No silent stripping-and-sending for names: student questions get the
  refusal, not a sanitized query.
- **Voice-first output**: spoken TTS of the summary in real time; playback
  stoppable by clicking ASK again or saying "stop".
- **Text output**: full answer prints in the Ask tab conversation view with
  source citations as Perplexity returns them.
- **No redirect, ever**: the teacher is never moved to the Ask tab automatically.
  Remove the `switchView("ask")` auto-switch (index.html:1309 path) if HF1's
  companion-hide didn't already orphan it.
- **Offline/unconfigured honesty**: no Perplexity key or no network → plain
  message, no fake answers.

## Phase 2 — Implementation prompt

Implement your spec. Acceptance (brief §9 A12–A16):

- ASK button labeled "Ask" with example questions visible.
- Answers from Perplexity only; **no personal data in any request payload** —
  add a test that a roster-name query never produces an outbound call (assert at
  the egress/firewall layer, not just the UI).
- Spoken one-paragraph summary with "hear more" continuation; stoppable by
  button or "stop".
- Text + citations print in the Ask tab; the view never auto-switches.
- Student-name queries get the honest refusal; block logged to privacy log.
- Existing tests green; `lv eval teacher-readiness` ≥ 16/19 (the no-model honesty
  checks C9/C10 must not regress — Ask's refusal message is a NEW message class;
  route it through `src/lingua_viva/messages.py`).

Commit ONLY owned files by explicit path, message
`ask: voice-first perplexity with PII egress gate, no redirect (T8)`.
