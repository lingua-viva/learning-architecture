# Build Prompt — Voice Student Detection v2 (Fuzzy + Context)

You are implementing `dev/SPEC_LV_VOICE_STUDENT_DETECTION_V2_2026-08-01.md`.

Read first:

```text
dev/SPEC_LV_VOICE_STUDENT_DETECTION_V2_2026-08-01.md
src/lingua_viva/voice_intent.py     (full — detect_student 81-99, classify_intent, thresholds)
src/web.py                          (the /api/voice/act handler, lines ~2599-2724 — every branch)
static/index.html                   (handleVoiceActResult, voiceActPending, VOICE_ACT_PENDING_MS — the clarification-memory pattern you will mirror)
tests/test_voice_intent.py          (full — extend, don't fork; note the _isolate pattern and the first-name-only privacy assertions)
src/lingua_viva/improvement_audit.py  (_gap_signals_path — the NDJSON log pattern for Step 4)
```

## Objective

Deterministic upgrades to student detection: difflib fuzzy matching for STT garbling,
frontend-held `last_mentioned_student` context for pronoun follow-ups, and transcript-free
detection-decision logging. **No LLM. No guessing. Every relaxation is threshold-gated and
spoken-confirmed by name.**

## Hard Rules

1. **Exact-match paths must be byte-identical** to current behavior — fuzzy runs only after
   exact fails.
2. **Ambiguity asks.** Two candidates within cutoff → needs_clarification listing both. Context
   resolution fires ONLY when a pronoun regex matches AND no roster name was detected.
3. **Every non-exact resolution names the student in the spoken confirmation** ("Got it —
   Marco. Saved." / "Still Marco — noted.") so a misresolution is audible immediately.
   First-name-only rule (web.py:~2665) applies to these strings too.
4. **stdlib only** — `difflib.get_close_matches`, `re`. No new dependencies.
5. **Additive response fields only** on /api/voice/act (`match_quality`, `candidates` on
   clarification). Existing fields frozen — the frontend voice wire and Chip's packet parse them.
6. **Detection log rows contain no transcript and no names** — ids, outcome enum, cutoff,
   timestamps only. Assert this in a test on serialized keys.
7. Hermetic tests, no commits, UI contract ceremony (changelog comment, `--bump` from repo
   root, EXPECTED_VERSION).

## Build Order

### Step 1 — Backend fuzzy matching
Rework `detect_student` per spec: possessive stripping, exact pass unchanged, fuzzy pass
(cutoff 0.8 as module constant `FUZZY_NAME_CUTOFF`), ≤3-char first names exact-only, unique-hit
rule, ambiguous → special return carrying both candidates. New return
`(student_id, display_name, match_quality)`; update the two call sites (classify_intent
internals + web.py handler) and every existing test's unpacking. `match_quality` enum:
`"exact" | "fuzzy" | "context" | None`.

### Step 2 — Context resolution
In the web.py observation branch: accept optional `context_student_id` from payload. Resolution
order: (1) roster name in transcript (exact→fuzzy) wins outright; (2) else pronoun regex
`\b(he|she|they)\b` (case-insensitive) + valid `context_student_id` → resolve with
`match_quality="context"`; (3) else needs_clarification (unchanged). Validate
context_student_id against the roster — unknown id is ignored, not an error.
Watch the trap in spec test 5: "he also helped Nora" — the pronoun is the subject; Nora
appearing as object must not steal attribution. Implement as: if a pronoun occurs BEFORE the
first detected roster name in the transcript, context wins; otherwise the named student wins.
Keep this rule as a small pure function with its own tests — it's the subtlest logic in the spec.

### Step 3 — Frontend memory
Mirror the voiceActPending pattern: `voiceLastStudent = {student_id, display_name, at}` set on
every response where an observation saved (or clarification resolved) with a student; cleared
on view switch and clarification-decline; expiry 120s reusing `VOICE_ACT_PENDING_MS`. Send
`context_student_id` in the voice/act payload when fresh. Show resolved-name echo in the
transcript toast for fuzzy/context resolutions (e.g., `"Marko helped…" → Marco`).

### Step 4 — Detection decision log
Small helper in web.py (or voice_intent.py — wherever imports stay clean): append NDJSON row
`{ts, decision: "student_detect", outcome: "exact"|"fuzzy"|"context"|"ambiguous"|"none",
student_id, cutoff_used, schema: "lv_route_mem_v1"}` to `LV_ROUTING_MEMORY_PATH` (env, default
`memory/data/routing_memory_v1.ndjson`). Fire-and-forget: log failure never affects the
response. This is Spec 5's ingestion source — get the schema field in from day one.

### Step 5 — Tests
Extend `tests/test_voice_intent.py` with the spec's 9-point plan. Non-negotiables:
- Byte-identical exact paths (run the existing detection tests unmodified — they must pass
  without edits beyond return-arity unpacking)
- The pronoun-subject-vs-named-object pair (both directions)
- Ambiguous roster [Marco, Marko]
- Privacy: fuzzy/context spoken strings contain first name only ("Bianchi" not in spoken)
- Log rows: key-set assertion (no `transcript`, no `display_name` keys)

### Step 6 — Verify
```bash
python3 -m pytest tests/test_voice_intent.py tests/test_ui_contract.py -q
python3 -m src.lingua_viva.cli preflight
python3 -m pytest -q tests/
```

## Definition of Done

- [ ] "Marko"/"Marco's" resolve to Marco with audible name echo
- [ ] Pronoun follow-ups attribute via context, window-bounded, never without a pronoun
- [ ] Ambiguity always asks with candidates; exact paths untouched
- [ ] Detection decisions logged transcript-free with versioned schema
- [ ] Full suite green, UI contract bumped
