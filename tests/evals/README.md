# Lingua Viva Eval Suite

## What This Is

A 5-layer property-based eval architecture that tests the system's **promises**, not its mechanisms.

All tests are currently `pytest.mark.skip` — they define what "correct" means. The implementation team builds to these specs.

## Running

```bash
# Collect all eval tests (verify they're discoverable)
pytest tests/evals/ --co

# Run all (all skip cleanly — no crashes on import)
pytest tests/evals/ -v

# Run a single layer
pytest tests/evals/layer1_schema/ -v
pytest tests/evals/layer2_retrieval/ -v
pytest tests/evals/layer3_isolation/ -v
pytest tests/evals/layer4_golden/ -v
pytest tests/evals/layer5_gauntlets/ -v

# Confirm existing tests still pass
pytest tests/ -q --ignore=tests/evals/ --tb=no
```

## The Five Layers

| Layer | What It Tests | Test Count | Runtime Target |
|-------|--------------|-----------|----------------|
| 1. Schema & Contract | Output structure validity | 15 | <1s |
| 2. Adaptive Retrieval | Grade fencing, document classification, teacher lens extraction | 20 | <30s |
| 3. Isolation | Student/teacher/temporal/privacy boundaries | 15 | <5s |
| 4. Golden Artifacts | Tier logic, CEFR, Bloom's, holdout prediction, bilingual | 20 | <60s |
| 5. Gauntlets | End-to-end workflow correctness | 5 gauntlets (~25 assertions) | <120s |

## Key Files

- `CONTRACTS.md` — Interface specs the implementation team must satisfy
- `fixtures/synthetic_students.yaml` — Test roster with expected tiers
- `fixtures/synthetic_observations.yaml` — 55 observations with canary values
- `fixtures/synthetic_teacher_history/` — 5 historical teaching artifacts
- `layer4_golden/tier_assignment_truth_table.yaml` — Complete RTI×CEFR → tier mapping

## Design Principles

1. **No overlap** — each property is owned by exactly one layer
2. **Lower layer wins** — if a test fits two layers, it goes in the lower one
3. **Dependencies flow up** — Layer N requires Layers 1..(N-1) to pass first
4. **Holdout, not human validation** — teacher's own past work IS the ground truth
5. **Forward-looking** — all tests are skipped until implementation exists

## Spec

Full specification: `dev/specs/SPEC_LV_EVAL_ARCHITECTURE_V1_2026-07-22.md`
