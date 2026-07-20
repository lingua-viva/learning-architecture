# Lingua Viva Final Polish Report

Date: 2026-07-18

## Baseline

The first baseline run exposed one stale runtime artifact from a previous ingest test:

- `python3 -m pytest tests/ -q`: `1 failed, 399 passed`
- Failure: `tests/test_document_ingest_endpoint.py::test_ingest_endpoint_never_leaves_a_temp_file_behind`
- Cause: stale `case-studies/04-still-i-rise/data/ingest-tmp/tmp*.pdf`

After making ingest temp cleanup deterministic, the baseline was re-run:

- `python3 -m pytest tests/ -q`: `400 passed`
- `python3 -m src.lingua_viva.cli health --full --json`: `doctor=WARN`, `pytest=PASS`, `gauntlet=PASS`, `golden_eval=PASS`
- `scripts/gate3_sweep.sh 15`: `15/15 passed`
- `python3 -m src.lingua_viva.cli eval golden tests/golden_education_v1.yaml`: `36/36 passed`
- `npm run build --prefix desktop`: passed

## Item 1: Stub Closure

Disposition: FIX

ExitGate and IntegrityGate remain legacy pipeline no-ops, but they are no longer silent. Each now carries an explicit `# DEFERRED` comment with reason, date, and owner. Admin placeholder endpoints are also explicitly deferred in `src/web.py`.

Regression coverage added:

- `tests/test_stub_audit_sweep.py::test_exit_gate_deferred_noop_contract`
- `tests/test_stub_audit_sweep.py::test_integrity_gate_deferred_noop_contract`
- `tests/test_stub_audit_sweep.py::test_admin_deferred_endpoints_are_explicit_placeholders`

## Item 2: Installer Naming

Disposition: FIX

The install/build surface was renamed to Lingua Viva:

- Binary name: `lv`
- Install home: `~/.lingua-viva/`
- Launcher: `lv-launch`
- Port: `8787`
- PyInstaller spec: `mc.spec` renamed to `lv.spec`
- PyInstaller entry point: `src/lv_cli.py`
- CLI now includes `lv serve [port]`
- Docker environment names use `LV_` prefixes

Validation:

- `sh -n install.sh`: passed
- `python3 -m pytest tests/test_lv_cli.py -q`: passed
- Naming grep over `install.sh`, `lv.spec`, and `docker-compose.yml`: no SIR/MC-era hits

## Item 3: Learned Weights Provenance

Disposition: FIX

Golden evaluation was run before and after removing learned weights. The score stayed unchanged:

- Before: `36/36 passed`
- After zeroing `ontology/learned_weights.yaml`: `36/36 passed`

Conclusion: learned weights are not load-bearing for the current golden set, so they were reset to an empty map.

## Item 4: Missing Endpoint Tests

Disposition: FIX

Smoke coverage was added for endpoints previously identified as untested:

- `GET /api/curriculum/unit/{unit_id}`
- `GET /api/admin/evidence`
- `GET /api/admin/capacity`
- `GET /api/stats`
- `GET /api/session`

Test file: `tests/test_endpoint_smoke_polish.py`

These tests assert status code and response shape only; they are intended to prevent accidental 500s, not to replace deeper product tests.

## Item 5: Ollama Circuit Breaker

Disposition: FIX

`src/lingua_viva/reasoning.py` now tracks consecutive local Ollama failures. After three failures, local reasoning fails fast for 30 seconds with:

`Ollama appears to be down - check if it's running, then try again.`

The breaker resets after a successful local call.

Regression coverage added:

- `tests/test_lingua_viva_reasoning.py::test_ollama_circuit_breaker_opens_after_three_timeouts`

## Item 6: Service Worker PII Parity

Disposition: FIX

The service worker privacy guard now covers the high-value PII types expected from the server-side privacy layer:

- SSN
- Email
- US and international phone numbers
- Credit card-like numbers
- Date of birth
- Passport-like identifiers
- Medical record numbers
- Street addresses

Regression coverage added:

- `tests/test_pwa_assets.py::test_service_worker_covers_high_value_pii_patterns`

## Final Validation

- `python3 -m pytest tests/ -q`: `411 passed`
- `python3 -m pytest doctor/support_loop/tests/ -q`: `15 passed`
- `python3 -m src.lingua_viva.cli health --full --json`: `doctor=WARN`, `pytest=PASS`, `pytest_summary="411 passed in 25.37s"`, `gauntlet=PASS`, `golden_eval=PASS`
- `scripts/gate3_sweep.sh 15`: `15/15 passed`
- `python3 -m src.lingua_viva.cli eval golden tests/golden_education_v1.yaml`: `36/36 passed`
- `npm run build --prefix desktop`: passed
- `python3 doctor/lv_artifact_gauntlet.py`: `PASS`, checked 15 files and 7 gates
- `python3 -m doctor.support_loop doctor`: `WARN`, not critical
- Forbidden branding grep over `static/ src/lingua_viva/ tests/`: no hits
- `.docx` status check: empty
- Port 8787 after Gate 3: free

Doctor WARN details are accepted for this working tree:

- Local changes are present and should be reviewed before update.
- Expected private-source exclusions are present and were not read.

## Accepted State

Lingua Viva is closed for this pass. The remaining stubs are explicit and tested, installer and build names are Lingua Viva-native, learned weights are no longer carrying unverifiable behavior, previously untested endpoints have smoke coverage, local reasoning has a bounded failure mode when Ollama is down, and the service worker privacy layer now covers the top PII categories. Final validation is green: 411 application tests, 15 Doctor tests, Gate 3 at 15/15, golden eval 36/36, desktop build passed, artifact gauntlet passed, no forbidden branding in active surfaces, and the authoritative `.docx` remains untouched.
