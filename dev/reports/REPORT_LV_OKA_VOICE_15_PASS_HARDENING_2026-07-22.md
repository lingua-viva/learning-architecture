# Report: Oka Voice Infrastructure — 15-Pass Hardening

**Date**: 2026-07-22  
**Status**: BUILT (uncommitted)  
**Scope**: Observe live capture + Ask voice interaction only

## Iterations

1. **Local-only classification** — pinned Observe classification to an Ollama model even when an external provider is configured.
2. **Input bounds** — rejected observation transcripts over 4,000 characters before model work.
3. **Bounded model wait** — wrapped classification in a 15-second timeout with all-null manual fallback.
4. **Strict output parsing** — parse only the first JSON object and discard invalid enum values.
5. **Text normalization** — collapse whitespace and cap free-text `sel_domain` output at 80 characters.
6. **Truthful degradation** — breaker/no-model/zero-confidence replies now return `model_used="none"` and `suggestions_available=false`.
7. **No unsafe defaults** — Observe begins with unselected type/CEFR fields instead of silently implying speaking/A1.
8. **Explicit review gates** — CEFR observations require a skill and level; urgency remains unchecked until the teacher affirms it.
9. **Observe Oka lifecycle** — upgraded Observe to interim transcript, tap-to-stop, 2.5-second pause completion, listening state, and start/error recovery.
10. **Permission-error safety** — a failed Ask microphone attempt cannot submit text that was already in the input.
11. **Navigation safety** — speech callbacks tolerate their input, button, or status elements disappearing after view navigation.
12. **Turn concurrency** — Ask prevents overlapping model turns and disables its microphone while reasoning is active.
13. **Spoken-error boundary** — technical/network errors remain visible but are not read aloud as if they were a valid answer.
14. **Accessible state** — voice buttons expose `aria-pressed`; listening, suggestion, and save statuses use polite live regions.
15. **Integrated recovery/regression** — Observe keeps text after save failure, prevents duplicate saves, refreshes the live lens after success, and the protected UI bundle was re-locked at contract v19.

## Evidence

- `tests/test_observe_classify.py`: valid proposal, empty input, oversize input, invalid output, multiple-object output, SEL normalization, breaker state, exception/no-model degradation.
- `tests/test_oka_voice_hardening.py`: shared Oka runtime, error non-submission, navigation tolerance, concurrency, human review, manual fallback, accessibility.
- Targeted hardening + teacher API/UI + contract run: 25 passed.
- Full repository suite: 512 passed, 20 failed. All 20 remaining failures are outside this feature and reproduce as unavailable Ollama embeddings or Windows/POSIX permission/tooling assumptions.
- Inline JavaScript compiled successfully with Node.
- UI contract: v19, all protected hashes locked.
- Live isolated flow from the preceding build pass: classifier made zero writes; manual Save appended one observation; the learner lens refreshed to reading A2.

## Remaining environment-wide failures

The repository-wide suite still contains Windows/POSIX permission assertions and Ollama embedding-model availability failures outside this feature. No hardening test in this report depends on those services.
