# Lingua Viva Slack Integration — 15-Pass Hardening Report

**Date:** 2026-07-22  
**Scope:** Slack app view, Events API route, configuration boundary, education
observation bot, outbound acknowledgements  
**Maturity:** Pilot-ready; live-workspace validation remains operator-owned

## Outcome

The loop found and fixed ten concrete defects or resilience gaps. The
education-specific Events API bot remains the canonical integration. No
student observation text is sent to an external model or echoed back to
Slack.

## Pass record

| Pass | Failure class | Investigation | Result |
|---:|---|---|---|
| 1 | Architecture drift | Compared `SlackObservationBot` with the generic Socket Mode bridge and app runtime boundaries. | Kept Events API observation bot canonical; no duplicate bot stack. |
| 2 | Configuration isolation | Injected an empty environment while machine variables were populated. | Fixed `environ or os.environ` fallback; explicit empty mappings now stay empty. |
| 3 | Secret disclosure | Inspected status JSON and error shapes for token, signing-secret, and channel leakage. | Status remains boolean/count-only; regression test proves no values leak. |
| 4 | Authentication edge cases | Tested empty secrets, stale timestamps, `NaN`, and infinite clocks. | Empty secret and non-finite times now fail closed. |
| 5 | Handshake sequencing | Tested Slack URL verification before bot installation/channel mapping. | Valid signed challenge now needs only the signing secret. |
| 6 | Payload abuse | Exercised oversized bodies, invalid UTF-8, invalid JSON, and non-object JSON. | Added 1 MB request cap and explicit `413`/`400` boundaries. |
| 7 | Routing integrity | Tested callbacks without `event_id` and unregistered channels. | Missing IDs are rejected from processing; unregistered channels remain silent. |
| 8 | Replay-memory pressure | Simulated more receipts than the event cache limit. | Added ordered 10,000-event cap with deterministic eviction. |
| 9 | Observation-content bounds | Tested tag-only and 20,001-character observations. | Empty and oversized notes are not stored; fixed privacy-safe guidance is returned. |
| 10 | Continuation safety | Simulated clock rollback inside the ten-minute student continuation window. | Negative elapsed time no longer reuses student context. |
| 11 | Outbound transport | Inspected bearer header, JSON body, timeout, malformed API responses, and Web API outage. | Transport is bounded; malformed replies fail clearly; failed acknowledgements cannot replay or erase the local write. |
| 12 | Scope correctness | Rechecked Slack public/private channel event subscriptions and OAuth scopes. | UI now distinguishes `message.channels`/`channels:history` from `message.groups`/`groups:history`. |
| 13 | Network exposure | Traced the consequence of tunneling the local FastAPI server. | UI now directs operators to expose only `/api/slack/events`, never the full teacher app. |
| 14 | UI contract | Re-ran navigation handler/count checks and protected-bundle hashing. | Utility count updated; Slack change recorded at v12. Concurrent protected app work continued during convergence; the shared surface ultimately stabilized at v15 without reverting it. |
| 15 | Regression convergence | Ran Slack unit, app-route, end-to-end education, home, and UI-contract suites plus compile/diff checks. | Focused suite green; syntax and contract checks green. |

## Added invariants

- Explicit empty configuration cannot inherit ambient machine configuration.
- A signing secret must be non-empty.
- Replay timestamps and local comparison clocks must be finite.
- URL verification can complete before full bot configuration.
- Request bodies over 1 MB never enter JSON or ontology processing.
- An Events API callback without `event_id` cannot write an observation.
- Receipt memory is bounded to 10,000 IDs.
- Tag-only and oversized observations cannot reach local storage.
- Clock rollback cannot extend student continuation context.
- A failed Slack acknowledgement cannot cause a second local observation write.
- Setup guidance does not encourage publishing the local app.

## Verification

- Slack/app/end-to-end focused tests: passed.
- Protected UI contract: v15, passed.
- Python compile check: passed.
- `git diff --check`: passed.
- Full repository suite: attempted during the parent build and exceeded the
  two-minute command window; no failure result was produced. This report does
  not claim a complete all-tests pass.

## Remaining operator validation

1. Register a real Slack app and confirm URL verification over an approved
   path-only HTTPS proxy.
2. Validate one public or private teacher channel with the matching event and
   history scope.
3. Send a typed note and a supported voice clip.
4. Confirm one local student-lens write and one fixed acknowledgement.
5. Rotate the test credentials after validation.

Multi-process deployment remains out of scope: event receipts are bounded but
process-local. A multi-worker server requires a persistent idempotency table.
