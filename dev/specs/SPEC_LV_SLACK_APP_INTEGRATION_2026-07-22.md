# Lingua Viva Slack App Integration

**Status:** Implemented MVP  
**Date:** 2026-07-22  
**Maturity:** Pilot-ready integration; live workspace validation still required

## 1. Objective

Expose Lingua Viva's existing classroom Slack observation system inside the
local teacher app. A teacher should be able to find Slack in the app, see
whether it is configured, understand the privacy boundary, and connect a
Slack Events API subscription to the app's real observation pipeline.

## 2. Investigation findings

The repository contains two Slack implementations:

1. `src/education/slack_bot.py` is the education-specific observation bot.
   It verifies Slack request signatures, rejects replayed requests, extracts
   typed text or completed audio-clip transcripts, routes only registered
   channels, requires an explicit student ID before establishing a short
   continuation context, deduplicates event IDs, writes through
   `ObservationCapturePipeline`, and emits fixed acknowledgements that never
   repeat student content.
2. `bridges/slack_bridge.py` is a generic Mission Canvas conversational
   bridge using Slack Bolt Socket Mode. It is suitable for governed chat but
   does not implement the education bot's student-routing and observation
   privacy contract.

The education bot is therefore the canonical integration. The generic bridge
remains available for future non-student conversational workflows and is not
started by this feature.

The prior build journal correctly identified the missing production seams:
an HTTP endpoint, app configuration/status, and live Slack registration.

## 3. User experience

- Add a `Slack` button to the utility navigation for teachers and
  coordinators.
- The Slack view reports `Ready` or `Setup required`.
- It shows individual, secret-free checks for signing secret, bot token, and
  teacher-channel routing.
- It gives the exact Events API path and environment variable names.
- It explains that Slack receives the original message under the school's
  workspace policy, while Lingua Viva stores observations locally and sends
  only fixed acknowledgements back.
- It links to Slack's app-management surface. No secret is entered into or
  returned to browser JavaScript.

## 4. Runtime architecture

```text
Slack message / audio transcript
        |
        v
POST /api/slack/events (raw signed body)
        |
        v
SlackObservationBot
  - HMAC + replay verification
  - event deduplication
  - registered-channel routing
  - explicit [student:<id>] context
        |
        v
ObservationCapturePipeline
  - local governance and sanitizer audit
  - local student_lenses.db write
        |
        v
Fixed acknowledgement -> Slack chat.postMessage
```

The web process owns one long-lived bot instance so event deduplication and
the ten-minute per-sender continuation window survive across requests.

## 5. Configuration contract

The local process reads:

- `LV_SLACK_SIGNING_SECRET`: Slack app signing secret.
- `LV_SLACK_BOT_TOKEN`: `xoxb-...` token with `chat:write`.
- `LV_SLACK_TEACHER_CHANNEL_MAP`: JSON object mapping Slack channel IDs to
  local teacher IDs, for example `{"C012345":"teacher-1"}`.

`GET /api/slack/status` returns booleans and counts only. It never returns
credential or channel values.

Slack must be configured with a publicly reachable HTTPS request URL ending
in `/api/slack/events`. A production school deployment must terminate TLS or
use an approved managed tunnel/reverse proxy; exposing the entire local app
directly to the public internet is not recommended.

## 6. API contract

### `GET /api/slack/status`

Returns readiness, mode, event path, secret-presence booleans, registered
channel count, voice-transcript support, and the local-only guarantee.

### `POST /api/slack/events`

- Reads the raw body before JSON parsing so signature verification is exact.
- Normalizes Slack signature headers.
- Returns `401` for an invalid or stale signature.
- Returns `503` if local Slack configuration is incomplete.
- Passes valid payloads to the existing observation bot, including Slack's
  URL-verification challenge.

## 7. Security and privacy invariants

- Never expose or log Slack secrets or tokens.
- Never echo raw observation text to Slack.
- Never send observation text to an external model.
- Never infer a student on cold start.
- Ignore unregistered channels silently.
- Preserve the existing five-minute replay limit and event-ID deduplication.
- Keep student records under Lingua Viva's local runtime database.

## 8. Acceptance criteria

- Slack appears as a real app navigation button.
- The Slack view renders configuration state from the backend.
- The status response contains no secret values.
- Slack URL verification works through the FastAPI route with a valid
  signature.
- Bad signatures return `401`.
- Missing configuration returns `503`.
- Existing Slack bot and end-to-end education tests continue to pass.

## 9. Known limits and next phase

- Live workspace registration and end-to-end delivery require operator-owned
  Slack credentials and a public HTTPS callback.
- Event IDs are held in process memory; a multi-process deployment needs a
  small persistent idempotency table.
- Slack audio transcription availability depends on the workspace and Slack
  plan/client behavior.
- Token rotation and an administrator-facing channel mapper should be added
  only with an encrypted local secret store; plain browser storage is
  prohibited.
