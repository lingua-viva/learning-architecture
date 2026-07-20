# Report: Stakeholder Hardening Sweep — 2026-07-20

**Scope**: Whole-system stakeholder-readiness pass across package metadata, runtime storage, coordinator/admin surfaces, runtime broker smoke tests, and final gates.

## Fixed

1. **Package metadata branding**
   - `pyproject.toml` now packages as `lingua-viva`, not `still-i-rise`.
   - `runtime/package.json` now packages as `lingua-viva-runtime`, not `mission-canvas-runtime`.
   - Added metadata regression tests so stale public manifest names do not return silently.

2. **Runtime data defaults**
   - `StudentLensStore()` now defaults to `~/.lingua-viva/runtime/student_lenses.db` through the `lv_home()` seam.
   - Document ingestion now defaults to `~/.lingua-viva/runtime/documents.db`.
   - Ingest scratch files now default to `~/.lingua-viva/runtime/ingest-tmp`.
   - Existing env/test overrides remain: `LV_STUDENT_DB_PATH`, `LV_DOCUMENT_STORE_PATH`, `LV_INGEST_TMP_DIR`.
   - UI contract bumped to v5 for the protected `src/web.py` change.

3. **Runtime broker smoke test**
   - Added `npm test` for `runtime/`.
   - Added `runtime/package-lock.json`.
   - Updated runtime broker labels/defaults to Lingua Viva while preserving `PALETTE_PEERS_*` env fallbacks.
   - Fixed the stale Node smoke test import and verified it against the current better-sqlite3 DB path.

4. **Coordinator/admin deferred views**
   - Replaced `{"status": "not_yet_implemented"}` with structured `deferred` responses carrying phase, reason, and prerequisites.
   - Updated the coordinator UI to show "planned after pilot evidence" with concrete prerequisites instead of "coordinator placeholder".
   - UI contract bumped to v6 for the protected `static/index.html` and `src/web.py` change.

## Reviewed and Left

- Doctor remains `WARN` because private/source `.docx` files are present and intentionally not read. This is the accepted privacy notice from the Doctor sweep, not a release defect.
- Auth/roles remain the largest true product risk before any multi-user deployment. This sweep did not add authentication because that is a larger product/security design, not a one-line hardening fix.
- Teacher decision-loop endpoints (`/rti`, `/grouping`, `/portfolio-entry`, `/assess/gaps`, `/help-artifact`) remain unbuilt and need a product decision: build or formally descope.
- Coordinator evidence/capacity/trends remain deferred, but are now explicitly messaged with prerequisites.

## Final Verification

- `python3 -m src.lingua_viva.cli preflight`: `5/5`.
- `python3 -m doctor.support_loop doctor`: `WARN` only for expected private-source exclusions.
- `python3 -m pytest tests/ -q`: `442 passed in 98.57s`.
- `python3 -m src.lingua_viva.cli health --full --json`: Doctor `WARN`; pytest, gauntlet, golden eval, and server 5xx all `PASS`.
- `npm test --prefix runtime`: `Runtime broker DB: ALL PASS`.
- `npm run build --prefix desktop`: TypeScript build passed.
