# Build Prompt - GIR + Voice Real-App Hardening Loop

You are running the first product-reality hardening pass after the GIR, golden voice loop, and
voice streaming builds. Read the spec first:

```text
dev/SPEC_LV_GIR_VOICE_HARDENING_LOOP_2026-07-30.md
```

## Hard Rules

1. **Do not commit or push.** The operator owns the commit window.
2. **Use synthetic data only.** Do not use real student names, real family data, or private school
   records. If a name might match the demo roster, use `Student Alpha`, `Student Beta`, etc.
3. **Use the real app path.** Prefer a running local app and HTTP calls to `/api/query/stream`,
   `/api/query`, and `/api/voice/tts`. Do not reduce this to unit tests of `resolve_voice_tone()`.
4. **Do not send student-data text to external TTS.** `/api/voice/tts` must keep refusing or
   falling back locally when text mentions synthetic student data that matches the safety gate.
5. **Do not fake the 15 passes.** If a pass cannot run, record it as blocked with the exact
   reason and system evidence.
6. **Fix scoped P0/P1 defects only.** Bigger product gaps become report findings and follow-up
   specs, not surprise architecture builds.

## Step 0: Verify Prerequisites

Run and read:

```bash
git status --short --branch
grep -n "Step 6.25: GROUND" src/pipeline.py
grep -n "gir_score\\|voice_tone" memory/schema/path.py
grep -n "query/stream\\|answer_sentence" src/web.py static/index.html
grep -n "GW-VOICE-006" src/lingua_viva/golden_workflows/schema.py src/lingua_viva/golden_workflows/runner.py
python3 -m pytest -q
python3 -m src.lingua_viva.cli preflight
```

If tests fail before you touch anything, identify whether the failure is inherited from the
previous build and report it before continuing.

## Step 1: Decide Manual vs Harness

If the app is easy to run and inspect manually, run the 15 scenarios by hand while capturing
HTTP evidence.

If repetition is slowing you down, add:

```text
scripts/run_lv_voice_gir_hardening.py
```

The harness should:

- call a running app at `LV_APP_URL` or `http://127.0.0.1:8787`
- post each synthetic question to `/api/query/stream`
- parse SSE events
- capture first `answer_sentence` timing and final `result`
- post the first sentence plus `tone_prefix` to `/api/voice/tts`
- record fallback/refusal/audio status without requiring Rime credentials
- write JSONL evidence to `dev/reports/artifacts/`

Keep the harness small. It is an observability tool, not a new product subsystem.

## Step 2: Run the 15 Iterations

Use the scenario mix in the spec:

- 3 strong local curriculum coverage
- 3 thin/no local source coverage
- 3 synthetic student-support/lens-style
- 2 admin/operations
- 2 follow-up/context
- 2 streaming/voice stress

For each iteration, record:

- question
- bucket
- route used
- SSE events seen
- final answer summary
- `classification.node`
- `gir_score`, `gir_method`, `voice_tone`, `tone_prefix`
- `grounding.tier_used`
- `route`, `model_used`, `external_calls`
- TTS result: audio / local fallback / privacy refusal / unavailable
- human verdict
- defect ID if any

## Step 3: Fix Real Defects

When a defect appears:

1. classify severity P0/P1/P2/P3 using the spec
2. log it before fixing
3. fix only if it is tightly scoped to GIR/voice/streaming
4. add or update a regression test
5. rerun the exact failed scenario

Do not silently tune GIR thresholds unless the report calls out the before/after evidence.

## Step 4: Write the Report

Create:

```text
dev/reports/REPORT_LV_GIR_VOICE_HARDENING_2026-07-30.md
```

Use this structure:

```markdown
# Lingua Viva GIR + Voice Hardening Report - 2026-07-30

## Verdict
- Run status:
- Highest severity:
- Release gate:

## Environment
- App URL:
- Model/provider state:
- Rime state:
- Worktree note:

## Scenario Results
| # | Bucket | Question | Route | GIR | Tone | TTS | Verdict |
|---|---|---|---|---:|---|---|---|

## Findings
| ID | Severity | User symptom | System evidence | Fix status | Retest |
|---|---|---|---|---|---|

## Open Risks

## Follow-Up Specs Needed
```

## Step 5: Final Verification

Run:

```bash
python3 -m pytest -q
python3 -m src.lingua_viva.cli preflight
git status --short --branch
```

Report the exact pass/fail counts. Mention explicitly that this loop validates real-app
sentence/SSE streaming and GIR/tone behavior, not true provider-token streaming.
