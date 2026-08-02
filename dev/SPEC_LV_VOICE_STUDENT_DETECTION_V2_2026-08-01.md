# SPEC: Voice Student Detection v2 — Fuzzy Names + Conversational Context

**Created**: 2026-08-01
**Status**: DRAFT — operator review before build
**Priority**: 4 of 5 — independent of Specs 1–3; directly improves Chip's C10–17 checks and Monday classroom use
**Origin**: Kiro's from-scratch review, item 4 ("semantic, not string-match") — scoped down to what's deterministic and shippable

---

## Problem

`detect_student()` (voice_intent.py:81–99) is exact substring/word match on display name or first name. Real classroom failure modes:

1. **STT garbling**: Whisper hears "Marko" or "Marco's" or Italian-inflected renderings; exact match returns `(None, None)` → teacher gets asked "which student?" about a student they just named
2. **Follow-up references**: "Marco struggled with the reading" … *20 seconds later* … "he also asked for help with writing" → second observation is unattributable, teacher must re-say the name every sentence
3. The existing clarification memory (frontend `voiceActPending`, 120s window) holds a *pending transcript* awaiting a name — it does not remember *who was just successfully mentioned*

The fix is two deterministic mechanisms. Explicitly **not** an LLM call and **not** guessing: every relaxation is threshold-gated, and everything below threshold still asks. The existing safety rule ("If no student detected for observation, NEVER guess — ask", frontend voice wire spec) stays the law.

## Design

### 1. Fuzzy name matching (backend)

Extend `detect_student(transcript, roster)`:

- Tokenize transcript; strip possessives (`marco's` → `marco`)
- Exact match first (current behavior, unchanged fast path)
- Fuzzy pass: `difflib.get_close_matches(token, first_names, n=2, cutoff=0.8)` per token (stdlib only, no new dependency)
  - Unique fuzzy hit ≥ 0.8 → match, and the response carries `match_quality: "fuzzy"` + `matched_token` so the spoken confirmation can echo the resolved name ("Got it — Marco. Saved.") letting the teacher catch a wrong resolution instantly
  - Two roster names both within cutoff of the same token (Marco/Marko in the same class) → **no match**, needs_clarification with both candidates in the spoken prompt: "Did you mean Marco or Marko?"
- First names ≤ 3 chars: exact-only (fuzzy on "Al"/"Bo" is noise)
- Return type grows to `(student_id, display_name, match_quality)` — internal callers only (web.py:2624 region + tests); no external contract change

### 2. Conversational context — `last_mentioned_student`

**Frontend-held session memory** (consistent with the ruled clarification-memory pattern — ruling 2(b) on the voice wire spec):

- After any voice/act response that resolved a student (observation saved, or clarification resolved), frontend stores `{student_id, display_name, at}` as `voiceLastStudent`
- Window: 120s (same constant as `VOICE_ACT_PENDING_MS`); any resolved mention refreshes it
- Next voice/act call sends `context_student_id` in the payload
- Backend: if intent=observation and `detect_student` finds no name **and** the transcript opens with or contains a third-person reference (`\b(he|she|they)\b` — deterministic regex), resolve to `context_student_id`, with `match_quality: "context"`, spoken confirmation **always names the student**: "Still Marco — noted." If no pronoun and no name → clarify as today (a nameless, pronounless observation shouldn't silently attach to the last student)
- View changes and clarification-declines clear `voiceLastStudent`

### 3. Routing-memory hooks (feeds Spec 5)

Every detection outcome is a decision worth remembering. Emit one NDJSON record per voice/act call to the routing-memory log (Spec 5's `LV_ROUTING_MEMORY_PATH`; if Spec 5 unbuilt, write to `memory/data/gap_signals.ndjson` in its existing shape): `{decision: "student_detect", outcome: exact|fuzzy|context|ambiguous|none, cutoff_used, corrected_later: null}`. **IDs and match metadata only — never the transcript, never names** (the log may leave the machine in a debug bundle someday; assume it will).

## What NOT to Change

- The never-guess rule: ambiguity always asks; context resolution requires an explicit pronoun
- `/api/voice/act` response contract — additive fields only (`match_quality`, candidate list on clarification)
- The 120s constant semantics for pending clarification (this adds a sibling memory, doesn't touch it)
- WRITE_INTENT_THRESHOLD and the intent classification itself

## Test Plan

1. Exact still wins: full name + first name paths byte-identical to today
2. Fuzzy: "Marko helped today" with roster [Marco Bianchi] → Marco, `fuzzy`; "Marco's essay improved" possessive → Marco
3. Ambiguous fuzzy: roster [Marco, Marko] → needs_clarification, both names in spoken prompt
4. Short names: roster [Al] + transcript "All done with the group work" → no match (guard works)
5. Context: prior resolved Marco + "he also helped Nora" → **Marco** (pronoun subject), spoken names Marco — and Nora being named must NOT steal attribution when a pronoun opens the utterance; conversely "Nora struggled today" (name, no pronoun) → Nora, context ignored
6. No pronoun, no name → clarify even with fresh context
7. Expired context (>120s) → clarify
8. Spoken confirmations remain first-name-only (existing privacy assertion pattern)
9. Routing records: correct outcome per case, no transcript/name fields present — assert on serialized record keys

## Files

| File | Action |
|---|---|
| `src/lingua_viva/voice_intent.py` | MODIFY — fuzzy pass, pronoun check, match_quality |
| `src/web.py` | MODIFY — context_student_id handling, additive response fields, routing record emit |
| `static/index.html` | MODIFY — voiceLastStudent memory, payload field, confirmation display |
| `tests/test_voice_intent.py` | MODIFY — extend with cases above |

## Definition of Done

- [ ] Garbled and possessive names resolve; ambiguity asks with candidates
- [ ] "He also…" follow-ups attribute correctly within the window, always spoken-confirmed by name
- [ ] Zero regressions on exact-match paths and the never-guess rule
- [ ] Detection decisions logged transcript-free for Spec 5
- [ ] Full suite green, UI contract bumped
