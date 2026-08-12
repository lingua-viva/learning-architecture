# Demo Harness — Still I Rise Pilot Test

**For Claudia and Mical — tonight, before the demo.**

This harness tests the three core pipelines with real school material:

1. **Observation capture** — record a teacher observation, see it update a student lens
2. **Document processing** — feed a real lesson plan through docpipe, see it build a student profile
3. **Content differentiation** — input an IB unit, see three-tier differentiated packs come out

## Quick start

```bash
cd ~/learning-architecture
python3 -m pytest qa/demo-harness/ -v
```

## What each test does

- `test_01_observation_capture.py` — Creates a student, records an observation, verifies the lens updates. Uses realistic Nairobi IB school scenario.
- `test_02_docpipe_lens_build.py` — Feeds a lesson plan through document extraction, builds a student lens with evidence chains.
- `test_03_content_differentiation.py` — Takes an IB MYP unit and generates foundational/on-track/extended packs. Checks trauma-safe rules and IB alignment.
- `test_04_parent_report.py` — Generates a parent-safe summary from the student lens. Verifies no raw data leaks.

## Adding real material

Replace the sample content in the test files with actual school documents.
The tests are designed to work with any IB MYP content — change the
`UNIT_TITLE`, `TOPIC`, and `SUBJECT` variables.

**Privacy rule**: never commit real student names or identifiable data.
Use anonymized names (the fixtures use "Amina", "David", "Grace").
