# Phase 1 Feedback — Claude (Audit + Gemini Integration)
## For: Kiro | Before starting Phase 1: Sanitizer Unification
## Date: 2026-06-14

---

## Phase 0 Verdict: PASS

73 Python tests, 2 Node.js suites, 94% health. Clean baseline. Proceed.

---

## Phase 1 Requirements (Combining My Audit + Gemini's Feedback)

Gemini's three points are all correct. Here's my synthesis with implementation specifics:

### Requirement 1: Fail-Closed (Gemini's Point)

**MANDATORY.** If the sanitizer service is unreachable, every external call MUST be blocked. Never fail-open.

```python
# In the calling code (hub or pipeline):
try:
    result = await call_sanitizer(text, context)
except (ConnectionError, Timeout, HTTPError):
    # Sanitizer unreachable = treat as blocked
    return {"ok": False, "blocked": True, "text": "", "reason": "sanitizer_unavailable"}
```

**Test for this**: Kill the sanitizer service. Send a query to the hub. Verify the external model is NOT called. This is the most important test in Phase 1.

---

### Requirement 2: Tiered Sanitization (Gemini's Point, Extended)

Gemini is right that NER is expensive. But let me add nuance from what I saw in the code:

**Current Python sanitizer** (`src/gateway/sanitizer.py`) does:
1. Regex patterns (fast)
2. Ollama-based entity detection (the "NER" — actually an LLM call, not spaCy)
3. Ontology block signals

The Ollama call is what's slow (~500ms+). The regex layer alone takes <5ms.

**My recommendation**: The unified service should expose TWO endpoints:

```
POST /sanitize/fast    → Regex only. <5ms. Use for all real-time calls.
POST /sanitize/deep    → Regex + LLM entity detection. 500ms+. Use for high-stakes or async.
```

**Default all surfaces to /fast.** Only use /deep when:
- The entry gate flags something as `sensitivity: high` but regex didn't catch specific PII
- A client deployment is configured for `deep_sanitization: true` (HIPAA mode for Komodo)
- Async processing (stored path records can be deep-scanned after the fact)

This gives us Gemini's tiered model without overcomplicating the API.

---

### Requirement 3: Context-Aware Sanitization (Gemini's Point, Critical)

This is the most important design decision in Phase 1.

**The problem**: "SKU-415-555-1212" is a product code at Tropical IT but looks like a phone number to a regex. Recursive sanitization will destroy legitimate structured data.

**The solution**: The `POST /sanitize` payload accepts a `context` field that tunes sensitivity:

```json
POST /sanitize/fast
{
  "text": "Ship SKU-415-555-1212 to Colombia for order TI-4521",
  "context": "logistics",
  "boundary": "no-pricing"
}
```

Context-specific behavior:

| Context | Suppressed Patterns | Why |
|---------|--------------------|----|
| `logistics` | phone_us (inside SKU prefix), case_number | SKUs and order IDs look like phone numbers and case numbers |
| `medical` | NONE suppressed, ALL patterns active | PHI is never acceptable to leak |
| `education` | NONE suppressed for child data patterns | COPPA compliance, strictest mode |
| `general` | Default behavior, all patterns active | Safe default |

**Implementation**: The context → pattern suppression map should be a simple dict in the service config, not hardcoded. New clients add their context without code changes.

---

### Additional Requirement 4: The Service Must Be Optional for Development

**Do NOT require Docker or the sanitizer service running for local dev/testing.** 

The current state (sanitizer imported directly in Python, called inline in JS) means a developer can just `./mc start` and everything works. If Phase 1 makes the sanitizer a separate service that must be running, the dev experience degrades.

**Solution**: Fallback import. If the service is unreachable AND we're in dev mode:

```python
# In pipeline.py:
if DEV_MODE and sanitizer_service_unavailable:
    # Fall back to direct import (same code, just not via HTTP)
    from sanitizer.core import sanitize
else:
    # Production: call the service
    result = await http_post("localhost:6100/sanitize/fast", payload)
```

This means:
- **Dev**: `./mc start` works without starting the sanitizer service separately
- **Production (Docker)**: sanitizer is its own container, always available, fail-closed if down
- **Tests**: can test both paths

---

### Additional Requirement 5: Firewall Log Unification

Currently both `server.mjs` and `peers/hub/server.mjs` write their own `firewall_log.ndjson`. The unified sanitizer should own ONE log.

```
sanitizer/data/firewall_log.ndjson  ← single append-only log
```

All surfaces call the sanitizer. The sanitizer logs every decision. One audit trail. This is actually simpler than the current state (two log files in two locations).

---

## Summary for Kiro: Phase 1 Acceptance Criteria

| # | Criterion | Test |
|---|-----------|------|
| 1 | Single sanitizer service at localhost:6100 | `curl localhost:6100/health` returns 200 |
| 2 | `POST /sanitize/fast` — regex only, <10ms p99 | Benchmark 1000 requests |
| 3 | `POST /sanitize/deep` — regex + LLM, <1000ms | Benchmark 10 requests |
| 4 | Fail-closed on service unavailable | Kill service → verify hub blocks all external calls |
| 5 | Context parameter tunes sensitivity | `context: logistics` → SKU-like patterns not redacted |
| 6 | Hub calls sanitizer before every external fetch | Grep for raw `fetch()` to external APIs — should be zero without sanitizer |
| 7 | Pipeline calls sanitizer (or direct import in dev) | `DEV_MODE=1 ./mc start` works without service running |
| 8 | One firewall log location | Only `sanitizer/data/firewall_log.ndjson` exists |
| 9 | Existing tests pass | 73 Python + 2 Node.js suites |
| 10 | Existing sanitizer tests ALSO pass against new service | Port `test_external_sanitizer.mjs` assertions to hit the HTTP endpoint |

---

## Build Order Within Phase 1

1. Build the FastAPI service (`sanitizer/app.py`) with `/health`, `/sanitize/fast`, `/sanitize/deep`
2. Port all regex patterns from the 3 existing implementations into one canonical list
3. Add context-aware suppression logic
4. Add fail-closed wrapper in hub (`server.mjs`) — try service, catch → block
5. Add fail-closed wrapper in pipeline (`pipeline.py`) — try service, catch → block (with dev fallback)
6. Wire firewall logging into the service (not the callers)
7. Remove old sanitizer functions from `data_boundary.mjs` and `external_sanitizer.mjs` (keep the files for backwards compat but mark deprecated, or delete if confident)
8. Run all tests
9. Benchmark latency

---

## One Risk to Name

**The biggest risk in Phase 1 is not the implementation — it's the migration.** The current system WORKS. Every external call is sanitized. The risk is that during the migration from "3 implementations that work" to "1 service that works," there's a window where something is unwired and the governance gap reopens.

**Mitigation**: Don't delete the old implementations until the new service is verified end-to-end. Wire the new service ALONGSIDE the old code first (call both, compare results, log discrepancies). Only remove the old code after the new service has been running without discrepancies for a full test cycle.

This is a TWO-WAY DOOR only if you keep the old code until the new is proven.

---

*Feedback from claude.analysis. Incorporating gemini safety review. Ready for Kiro to proceed.*
