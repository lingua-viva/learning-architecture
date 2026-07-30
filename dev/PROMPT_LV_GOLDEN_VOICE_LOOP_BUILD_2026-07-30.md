# Build Prompt — Golden Voice Loop + Gap→Eval Enrichment

You are adding a 6th golden workflow that exercises Lingua Viva's voice path end to
end, and wiring its failures into the existing gap-signal store. Read the spec first:

```
dev/SPEC_LV_GOLDEN_VOICE_LOOP_2026-07-30.md
```

## Hard Prerequisite — check this before writing any code

This spec reads `PipelineResult.grounding` and `PathRecord.voice_tone`. Those fields
only exist after `dev/SPEC_LV_GIR_VOICE_TONE_2026-07-29.md` has been built and merged.

**First step, no exceptions**: run
```
grep -n "gir_score\|voice_tone" memory/schema/path.py
```
If that returns nothing, the prerequisite spec has not landed yet. **Stop and tell the
operator**, don't try to build around the gap or stub it out yourself.

## Why This Matters

LV's voice loop currently has zero automated regression coverage — a change that
breaks STT, breaks grounding, or silently reverts tone resolution would only be caught
by hand. This closes that gap the same way the existing 5 golden workflows already
cover the source→grounding→action→deliverable→receipt chain: one more hermetic,
CI-safe workflow, reusing the same schema and CLI.

## Critical Rules

1. **Don't build a new instrument registry.** `improvement_audit.py` already ranks
   `gap_signals.ndjson` by signal family. This workflow just needs to write into that
   same file with a new signal family (`voice_loop_failure:*`). If you find yourself
   writing a new registry class or a `MEASURE`/`ANALYZE` function pair, stop — that's
   explicitly out of scope (see spec's "Design" section).
2. **Never call the real Rime API or a real network endpoint from this workflow.**
   Every existing golden workflow in `hermetic` mode is network-free; this one must be
   too. The TTS step only exercises the prefix-construction logic, not the HTTP route.
3. **Keyword matching for the STT transcript, not exact string equality.** Whisper's
   `tiny` model output isn't byte-identical across environments. Exact match will make
   this workflow flaky and someone will end up disabling it — do it right the first
   time.
4. **Model-load failure is a SKIP, not a FAIL.** If `WhisperLocalProvider` can't load
   its model (no cache, no network in CI), mark the `stt_transcribe` step `SKIP` and
   don't fail the whole workflow for an environment problem. Look at how this repo
   already guards `ollama_reachable()` in its test suite for the pattern to mirror.
5. **Use `_gap_signals_path()`'s existing resolution logic** (or an equivalent
   env-overridable lazy path lookup) — do not hardcode
   `memory/data/gap_signals.ndjson` as a module constant. This repo's own docstring in
   `improvement_audit.py` explains why: module-constant paths have broken test
   hermeticity here before (`sanitizer/client.py`, 2026-07-20).

## Build Steps (do in order, run tests after each)

### Step 1: Confirm the prerequisite (see above) — do not skip this check.

### Step 2: Record/obtain the fixture

Create `tests/fixtures/voice/golden_query.wav` — a short (2-3 second), clean recording
of a benign phrase such as "Show me the current project status." If you cannot
record audio directly, check whether a text-to-speech tool is available in this
environment to synthesize the fixture, or ask the operator to supply one. Define the
expected keyword set in the test/workflow code (e.g. `{"current", "project", "status"}`
— case-insensitive substring match against the lowercased transcript, requiring all
expected keywords).

### Step 3: Extend the workflow schema

In `src/lingua_viva/golden_workflows/schema.py`, add `"GW-VOICE-006"` to
`WORKFLOW_IDS`. Nothing else in this file should need to change — `GoldenWorkflowResult`
and `WorkflowStep` are already general enough to reuse.

### Step 4: Write `_run_voice_loop()`

In `src/lingua_viva/golden_workflows/runner.py`, add a new function alongside
`_run_one()` (don't overload `_run_one()` — the steps are structurally different).
Implement the 5 steps from the spec in order: `stt_transcribe`, `pipeline_run`,
`grounding_result`, `tone_resolved`, `tts_hermetic`. Each step becomes one
`WorkflowStep` in the result, exactly like the existing workflows do.

Wire it into `run_workflows()`'s dispatch (or the `WORKFLOWS` list / `only` filter) so
`lv golden-workflows --only GW-VOICE-006` runs just this one, matching how the other 5
already work.

### Step 5: Failure → gap signal

On any step FAIL, append one record to `gap_signals.ndjson` in the exact shape shown
in the spec (`entry_node: "GW-VOICE-006"`, `domain: "voice"`, `gap_signals:
["voice_loop_failure:<class>"]`, `timestamp`, `session_id`). Use the five failure
classes from the spec (`stt_mismatch`, `pipeline_error`, `gir_out_of_range`,
`tone_mismatch`, `tts_prefix_wrong`) — don't invent new ones without flagging it in
your summary.

### Step 6: Verify audit pickup — don't assume it

Temporarily point the gap-signals path at a scratch file (via whatever env var
`improvement_audit.py` already honors), deliberately break the fixture or a step to
force a `voice_loop_failure:*` record, then run the audit's ranking function against
that scratch file and confirm the new signal family shows up correctly ranked. **If it
doesn't surface**, that's a real bug in the audit's existing family-detection logic —
fix it and note it in your summary, don't paper over it.

### Step 7: Tests

Add a test that runs `GW-VOICE-006` in hermetic mode against the good fixture and
asserts PASS on all 5 steps. Add a second test that forces a failure (bad fixture path,
or monkeypatched transcribe returning garbage) and asserts the correct
`voice_loop_failure:*` record lands in a scratch `gap_signals.ndjson`.

## Verification

1. `python3 -m src.lingua_viva.cli golden-workflows` shows `GW-VOICE-006` PASS,
   5/5 steps, alongside the existing 5 workflows still passing.
2. Forced-failure test confirms the gap-signal write.
3. Audit pickup confirmed per Step 6.
4. `pytest -q tests/` green.
5. `python3 -m src.lingua_viva.cli health` (or equivalent Doctor check) passes.

## What NOT To Build

- No live instrument registry / `MEASURE`/`ANALYZE` loop.
- No real network calls anywhere in this workflow's hermetic path.
- No transcription-quality benchmarking beyond this one smoke-test fixture.
- No dashboard or UI surfacing — ranking via the existing audit tooling is sufficient
  for this pass.

If the prerequisite check in Step 1 fails, or if `improvement_audit.py`'s
family-detection needs a real fix in Step 6, stop and report back rather than
expanding scope to cover it yourself without flagging it first.
