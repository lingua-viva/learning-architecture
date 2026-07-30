# SPEC: Golden Voice Loop + Gap→Eval Enrichment

**Date**: 2026-07-30
**Status**: DRAFT — operator review before build
**Lens**: architect (primary), precision (measurement discipline)
**Depends on**: `dev/SPEC_LV_GIR_VOICE_TONE_2026-07-29.md` **must land first** — this spec
reads `PipelineResult.grounding` and `PathRecord.voice_tone`, neither of which exist
until that build ships.
**Branch**: `feat/golden-voice-loop`
**Priority rationale**: item 5 of the LV gap analysis. Deliberately last in the
sequence — it measures the thing items 2-4 build, so it has nothing to measure until
they exist.

---

## What Already Exists (verified by reading, not assumed)

| Component | Status | Location |
|---|---|---|
| `golden_workflows` pattern (5 hermetic workflows) | Built | `src/lingua_viva/golden_workflows/runner.py`, `schema.py` |
| `GoldenWorkflowResult`/`WorkflowStep` schema | Built, extensible | `src/lingua_viva/golden_workflows/schema.py` |
| `mc golden-workflows` CLI equivalent (`lv golden-workflows`) | Built | `src/lingua_viva/cli.py:434-438, 511-516` |
| `WhisperLocalProvider` (local STT, no network at inference) | Built | `src/lingua_viva/voice_stt.py` |
| `improvement_audit.py` — ranks `gap_signals.ndjson` by signal family, distinct-session breadth | Built | `src/lingua_viva/improvement_audit.py` |
| `gap_signals.ndjson` record shape | Established, in production use | `memory/data/gap_signals.ndjson` — `{entry_node, domain, gap_signals: [...], timestamp, session_id}` |

## What's Missing

1. **No WAV fixture anywhere in the repo** (`find -iname "*.wav"` returns nothing). No
   golden voice loop can run without one.
2. **No 6th golden workflow exercising the voice path.** The existing 5
   (`GW-EDU-001..003`, `GW-DRIVE-004`, `GW-SLACK-005`) never touch STT, grounding→tone
   resolution, or TTS.
3. **No live instrument registry** (`improvement_audit.py` is analysis-only over static
   stores — confirmed no `INSTRUMENTS` dict, no `MEASURE`/`ANALYZE` functions anywhere
   in `src/` or `doctor/`). This is fine — see design decision below, we don't build one.
4. **No voice-specific failure classification.** `gap_signals.ndjson` has no signal
   family for STT mismatch, low-GIR, or tone-resolution failure — a golden voice loop
   failure today has nowhere established to report itself.

---

## Design

### Decision: don't port MC's `improvement_circuit.py`

MC's golden voice loop runs inside a live MEASURE/ANALYZE instrument registry.
LV has no such registry, and building one is a much larger, separate architectural
project than "add a voice check." Instead:

- The golden voice loop is **workflow #6** in the existing `golden_workflows` pattern
  — same `GoldenWorkflowResult`/`WorkflowStep` shape, same CLI, same hermetic-only
  default. This reuses machinery instead of inventing a parallel one.
- Failures are reported into **the existing `gap_signals.ndjson` store**, under a new
  signal family (`voice_loop_failure:<class>`), so `improvement_audit.py`'s existing
  breadth/ranking logic picks them up automatically. No new registry, no new ranking
  code — the "lighter-weight registration point" LV needs, per the original gap
  analysis.

### 1. Fixture

Add a small checked-in WAV file with a known, short, benign phrase — e.g. a 2-3 second
recording of "Show me the current project status." — at
`tests/fixtures/voice/golden_query.wav`. Store the expected transcript as a **keyword
set**, not an exact string (`{"current", "project", "status"}` or similar), and require
all expected keywords to be present rather than accepting a single hit — Whisper's `tiny` model output varies slightly
across environments/versions, and exact-match will be flaky. This mirrors the
substring/keyword-matching discipline already used elsewhere in this repo's eval code
(see `_count_claims()`'s marker-list approach in `grounding/build.py` for the same
pattern).

### 2. New golden workflow: `GW-VOICE-006`

`src/lingua_viva/golden_workflows/schema.py`: add `"GW-VOICE-006"` to `WORKFLOW_IDS`.

`src/lingua_viva/golden_workflows/runner.py`: add a dedicated `_run_voice_loop()`
function (don't cram this into `_run_one()` — the steps are different in kind, not
just parameters) and register it in `WORKFLOWS` / dispatch by `workflow_id`.

Steps (each a `WorkflowStep`):
1. **`stt_transcribe`** — `WhisperLocalProvider().transcribe()` on the fixture WAV.
   PASS if the transcript contains all expected keywords, FAIL otherwise.
2. **`pipeline_run`** — feed the transcript into `Pipeline.run()` (same path
   `run_teacher_query()` uses). PASS if it completes without exception.
3. **`grounding_result`** — read `PipelineResult.grounding` (from the
   GIR-voice-tone build). PASS if `gir.score` is present and within `[0, 1]`.
4. **`tone_resolved`** — read `PipelineResult.path_record.voice_tone`. PASS if it's
   one of `plain`/`clarify`/`name_boundary` and matches what
   `resolve_voice_tone(gir_score)` would independently compute — this step is a
   **consistency check**, catching drift between the stored value and the resolver
   function, not a re-test of the resolver's own thresholds (those are unit-tested in
   `test_voice_tone.py` from the prior spec).
5. **`tts_hermetic`** — do **not** call the real `/api/voice/tts` route or hit Rime.
   Call the tone-prefix construction logic directly (the same prepend step the route
   performs) and assert the prefix is present/absent as expected for the fixture's
   known GIR bucket. Keeps this workflow network-free, consistent with every other
   hermetic golden workflow in this file.

### 3. Failure → gap signal

If any step FAILs, `_run_voice_loop()` appends one record to `gap_signals.ndjson`
(reuse `src/lingua_viva/improvement_audit.py`'s `_gap_signals_path()` resolver, don't
hardcode the path — the module already documents why: env-override hermeticity) in the
existing shape:

```python
{
    "entry_node": "GW-VOICE-006",
    "domain": "voice",
    "gap_signals": [f"voice_loop_failure:{failure_class}"],
    "timestamp": time.time(),
    "session_id": session_id,  # the fixture's session_id, e.g. "SESSION-GW-VOICE-006"
}
```

`failure_class` is one of: `stt_mismatch`, `pipeline_error`, `gir_out_of_range`,
`tone_mismatch`, `tts_prefix_wrong`. This is the "classify by failure kind" idea from
the gap analysis (S08 A04-A06), scoped down to five concrete, checkable classes instead
of MC's fuller taxonomy — start small, expand only if real failures show a class this
list doesn't cover.

### 4. `improvement_audit.py` picks it up automatically — verify, don't rebuild

Because this reuses the existing `gap_signals.ndjson` store and existing ranking logic
(breadth-by-distinct-session, structural floors), no changes to `improvement_audit.py`
should be needed. **Verify this is actually true** by running the golden voice loop
against a broken fixture on purpose, then running the audit command and confirming the
new `voice_loop_failure:*` signal family appears in its ranked output. If it doesn't
surface correctly, that's a real gap in the audit's family-detection logic worth fixing
— don't assume it "just works" without checking.

---

## Open Risks

- **Model download in CI.** `WhisperLocalProvider(model_size="tiny")` downloads model
  weights on first use if not cached. If CI has no cached model and no network, this
  step will fail for reasons unrelated to the actual check. Mirror the existing
  `ollama_reachable()` skip-guard pattern in this repo's test suite — skip
  `stt_transcribe` (mark `SKIP`, not `FAIL`) if the model can't be loaded, rather than
  failing the whole workflow.
- **Whisper output non-determinism.** Keyword matching (not exact string) mitigates
  this but doesn't eliminate it — a genuinely bad transcription could still contain the
  keywords by coincidence on a short fixture. Acceptable for a first pass; revisit if
  it proves noisy.
- **Fixture voice/accent bias.** One WAV, recorded once, is not a representative test
  of STT quality — this is a smoke test that the wiring works end to end, not a
  transcription-quality benchmark. Don't oversell it as more than that.

## Files Touched

| Action | File |
|---|---|
| NEW | `tests/fixtures/voice/golden_query.wav` |
| MODIFY | `src/lingua_viva/golden_workflows/schema.py` (`WORKFLOW_IDS`) |
| MODIFY | `src/lingua_viva/golden_workflows/runner.py` (`_run_voice_loop()`, dispatch) |
| MODIFY | `tests/` — new test asserting the workflow runs and, on a deliberately broken
  fixture, writes the expected `gap_signals.ndjson` record |

## Verification

1. `python3 -m src.lingua_viva.cli golden-workflows` (or the LV equivalent flag) shows
   `GW-VOICE-006` with 5 steps, PASS on the checked-in good fixture.
2. Temporarily point `LV_GAP_SIGNALS_PATH` at a scratch file, force a failure (e.g.
   corrupt the fixture path), confirm a `voice_loop_failure:*` record is written in the
   correct shape.
3. Run `improvement_audit.py`'s ranking against that scratch file, confirm the new
   signal family surfaces in ranked output.
4. `pytest -q tests/` green.

## What This Does NOT Cover

- No live MEASURE/ANALYZE instrument registry (explicitly rejected above — out of
  scope, disproportionate to the need).
- No real Rime network call in the hermetic path — TTS is checked at the
  prefix-construction level only.
- No transcription-quality benchmarking beyond the single smoke-test fixture.
- No UI/dashboard surfacing of voice-loop failures — they land in the same
  `gap_signals.ndjson` ranking teachers/operators already have via existing tooling.
