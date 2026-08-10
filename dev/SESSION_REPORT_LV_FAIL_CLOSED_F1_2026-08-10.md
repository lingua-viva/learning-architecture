# Session Report — LV Fail-Closed Wave F1 (2026-08-10)

Scope: F1 only, per operator ruling 2026-08-10. F2/F3 were not touched. Exit
gate for this window was teacher-readiness 20/20 with C12 added, not 21/21.

## Built

- Added `tests/fixtures/safeguarding_corpus.yaml`.
  - `must_flag`: 36 entries.
  - `must_stay_green`: 12 entries.
  - Every entry carries `source` and `added` provenance.
  - The original fail-open phrase, `His dad hits him at home`, is present with
    `minimum_tier: RED`.
- Added shared corpus loader/evaluator:
  `src/lingua_viva/safeguarding_corpus.py`.
- Added corpus tests:
  `tests/test_safeguarding_corpus.py`.
- Added teacher-readiness C12:
  `Adversarial safeguarding corpus holds fail-closed classifier`.
- Added a harness-level C12 locking test in `tests/test_teacher_readiness.py`.
- Narrowly strengthened `src/lingua_viva/safeguarding.py` for F1 seed gaps:
  - secrecy paraphrase: `has/needs to stay a secret` -> RED.
  - persistent hunger paraphrase: `hungry every day` -> RED via ambiguous
    neglect round-up.
  - euphemistic home-context concerns: `gets in trouble at home` and
    household-adult anger -> AMBER.

## Baseline Before Build

```text
python3 -m src.lingua_viva.cli preflight --json
=> 6/6 passed

python3 -m src.lingua_viva.cli eval teacher-readiness --json
=> 19/19 passed, 0 failed, 0 stubbed
```

## Verification After Build

```text
python3 -m src.lingua_viva.cli preflight --json
=> 6/6 passed

python3 -m src.lingua_viva.cli eval teacher-readiness --json
=> 20/20 passed, 0 failed, 0 stubbed
```

C12 evidence:

```json
{
  "must_flag": 36,
  "must_stay_green": 12,
  "under_classified": [],
  "over_classified": []
}
```

Focused tests:

```text
pytest -q tests/test_safeguarding_corpus.py tests/test_safeguarding.py tests/test_teacher_readiness.py
=> 43 passed
```

Full suite:

```text
pytest -q tests/
=> 2229 passed, 13 skipped in 650.09s
```

## Weakening Demonstration

Temporary local weakening applied, then reverted:

```python
red_hits = [
    hit for hit in _scan(lowered, RED_INDICATORS)
    if hit["category"] != "physical_abuse"
]
```

Corpus test result under weakening:

```text
pytest -q tests/test_safeguarding_corpus.py
=> FAILED test_must_flag_phrases_meet_minimum_tier
=> phrase='His dad hits him at home' expected>=RED got=GREEN
=> rationale='normal teaching observation'
```

Teacher-readiness result under weakening:

```text
python3 -m src.lingua_viva.cli eval teacher-readiness --json
=> 19/20 passed, 1 failed, 0 stubbed
=> C12 FAIL P0
=> under_classified included:
   - His dad hits him at home: expected RED, got GREEN
   - His dad hit him at home last night: expected RED, got GREEN
   - His dad is hitting him at home: expected RED, got GREEN
   - He was hit by his dad after dinner: expected RED, got GREEN
   - He told me his dad hits him at home: expected RED, got GREEN
   - He told me that his father hurts him when he gets home: expected RED, got GREEN
   - She showed cigarette burn marks on her arm: expected RED, got GREEN
   - He flinches when I raise a hand to point at the board: expected RED, got GREEN
```

The weakening was reverted immediately. Final verification above was run after
the revert.

## Out-of-Scope Observation

User-provided screenshot
`/home/mical/Pictures/Screenshots/Screenshot from 2026-08-10 12-19-57.png`
shows desktop setup reporting `Lingua Viva Server did not start`, with a note
about missing components or port 8787. This window did not change desktop setup
because F1 safeguarding corpus was the explicit scope.
