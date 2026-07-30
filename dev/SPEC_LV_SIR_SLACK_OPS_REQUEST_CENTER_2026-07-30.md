# SPEC: Still I Rise SlackBot - Operational Request Center Phase 2A

**Date**: 2026-07-30
**Status**: DRAFT - build handoff
**Proposal source**: `dev/PROPOSAL_STILL_I_RISE_SLACKBOT_WORKFLOWS_2026-07-30.md`
**Previous slice**: `dev/SPEC_LV_SIR_SLACK_ABSENCE_COVERAGE_MVP_2026-07-30.md`
**Primary surface**: Lingua Viva Slack Daily Operations Assistant

---

## Goal

Extend the Still I Rise SlackBot from staffing coordination into a small operational request center for:

- facilities problems
- IT problems
- supplies/materials requests

This is still not a general chatbot. It is a deterministic operations workflow:

```text
Request -> Triage -> Assign owner -> Act -> Requester confirms -> Resolve
```

The build should reuse the current Slack ops primitives and add the minimum structure needed for a usable school-operations router.

## Existing Repo Capabilities To Reuse

| Capability | Existing implementation | Use in this build |
|---|---|---|
| Slack Socket Mode | `src/lingua_viva/slack_socket.py` | Reuse envelope dispatch, `views.open`, messages, updates, DMs. |
| Slash commands | `SlackOpsBot.on_envelope(..., "slash_commands")` | Add `/ops-request`; keep `/absence`. |
| Interactive payloads | `SlackOpsBot._handle_block_actions()` and view submissions | Add request modal, owner claim, requester confirm, close actions. |
| Ops records | `src/education/ops_records.py` | Store operational requests in existing records. |
| Facilities pack | `config/ops_packs/facilities.yaml` | Keep natural-language facilities capture working. |
| Daily file | `src/education/daily_file.py` | Surface pending operational requests in daily files. |
| Ops audit route | `GET /api/ops/records` | Reuse for local inspection. |
| Route contracts | `contracts/ROUTE_REACHABILITY.yaml` | Classify any new route. |

## Current Gaps This Spec Closes

1. Facilities messages are captured but not assigned or resolved as a workflow.
2. IT and supplies requests have no structured Slack intake.
3. Requesters do not get a closed-loop status path.
4. Ops leads do not get a simple daily request summary.
5. There is no deterministic "owner claimed this problem" state for non-coverage operations.

## Design Constraint: No New Database Categories Unless Necessary

Use the existing `facilities` category for Phase 2A records and store subtype in `OpsRecord.extra`.

Recommended `extra` shape:

```json
{
  "workflow": "sir_ops_request",
  "request_type": "facilities",
  "campus": "Nairobi",
  "location": "Room 12",
  "severity": "teaching_blocked",
  "teaching_blocked": true,
  "photo_url": "",
  "owner_slack_id": "U222",
  "owner_name": "Ben Ali",
  "requester_slack_id": "U111",
  "requester_name": "Ana Ruiz",
  "requester_confirmation_required": true,
  "resolution_note": ""
}
```

Allowed `request_type` values:

- `facilities`
- `it`
- `supplies`

Allowed `severity` values:

- `routine`
- `same_day`
- `teaching_blocked`
- `urgent`

Do not add a full asset-management or ticketing schema in this slice.

## Build Scope

### Slice 1: `/ops-request` Command Opens A Structured Modal

When Slack sends a slash command envelope with `command: "/ops-request"`, the bot opens a modal.

Modal fields:

- request type: facilities / IT / supplies
- campus
- room/location
- severity
- short description
- teaching currently blocked: yes/no
- photo/link, optional
- preferred follow-up channel: thread / DM

Privacy rule:

- The modal must not ask for student details.
- Public cards should contain operational facts only: campus, location, severity, and short description.
- Do not post private notes or sensitive HR/student details.

### Slice 2: Modal Submission Creates A Request Record

Handle Slack interactive `view_submission` payloads for the operational request modal.

Expected behavior:

- Validate submitter against `teacher_map`.
- Create an `OpsRecord` with category `facilities`.
- Store structured request fields in `extra`.
- Use `status="needs_review"` for urgent/teaching-blocked requests if the current status machine requires review before assignment.
- Use `status="logged"` for routine requests that can be assigned directly.
- Post a triage card to the ops channel.
- DM the requester a receipt.
- Refresh daily files.

The record text should be concise and non-sensitive, for example:

```text
Facilities request: Nairobi, Room 12, teaching blocked - Projector not working.
```

### Slice 3: Claim / Assign Owner

Add a button on the ops-channel triage card:

- `Claim`

When a rostered staff member clicks `Claim`:

- Store owner metadata in `record.extra`.
- Keep the request visible in daily files.
- Update the original card to show owner and status.
- DM the requester that someone has taken ownership.

Do not use `coverage_request` statuses for non-coverage records. For the existing default status machine:

- `needs_review -> logged` can represent owner assignment after triage.
- `logged -> resolved` remains the close path.
- owner metadata in `extra` carries the assignment details.

### Slice 4: Resolve And Requester Confirmation

Add two deterministic close paths:

1. Owner marks "Ready for requester confirmation".
2. Requester clicks "Confirmed fixed" or "Still blocked".

Minimum acceptable first build:

- Owner `Resolve` button writes `resolution_note` and moves `logged -> resolved`.
- Requester receives a DM with the final message.
- If requester clicks "Still blocked", create a new `needs_review` follow-up record linked to the original via `extra["reopened_from"]`.

Do not silently close high-severity or teaching-blocked requests without leaving an audit trail.

### Slice 5: Natural-Language Facilities Capture Still Works

Existing DM/ops-channel facilities classification must continue to capture messages like:

- "The projector in room 12 isn't working."
- "Photocopier is broken again."
- "Need more markers for the art room."

For Phase 2A, natural-language facilities capture may remain capture-only, but if the implementation can safely post the same triage card for high-confidence facilities messages, that is acceptable. Pin the chosen behavior in tests.

### Slice 6: Daily Operational Request Summary Endpoint

Add a read-only endpoint:

```text
GET /api/ops/request-summary?date=YYYY-MM-DD
```

Compute from `OpsRecordStore` only.

Response fields:

- `date`
- `total_requests`
- `by_type`
- `routine`
- `same_day`
- `teaching_blocked`
- `urgent`
- `unassigned`
- `assigned_open`
- `resolved`
- `reopened`

Do not call Slack or external services from this endpoint.

Classify this route as `intentionally_backend_only` unless a visible UI call is added in the same build.

## Out Of Scope

- No AI classification beyond the existing deterministic ops classifier.
- No broad Slack channel history reading.
- No Slack App Home command center.
- No cross-campus dashboard.
- No photo upload download/storage pipeline; a URL/reference string is enough.
- No HR, procurement, or ITSM integration.
- No calendar/timetable updates.
- No emergency/safeguarding workflow.
- No SMS/phone fallback.
- No production live Slack verification unless the operator provides a real workspace.

## Privacy / Permission Rules

The build must preserve the current Slack ops boundary:

- Act only on slash commands, DMs, interactive payloads, and configured ops channels.
- Do not treat group DMs as private DMs.
- Do not read broad channel histories.
- Do not write to student lenses.
- Do not include student names or private HR/medical details in operational request cards.
- Keep Slack tokens secret; never log token values.

Recommended Slack scopes remain:

- `commands`
- `chat:write`
- `users:read`
- `channels:read`

Do not add `channels:history`, `groups:history`, or `mpim:history` for this slice.

## Tests

Add focused tests, preferably in a new `tests/test_sir_ops_request_center.py`:

1. `/ops-request` opens a modal.
2. Unknown slash commands remain ignored.
3. Modal submission from a rostered user creates one `facilities` record with `extra["workflow"] == "sir_ops_request"`.
4. Request type, campus, location, severity, teaching-blocked, and photo/link fields are stored in `extra`.
5. Public triage card does not contain forbidden private/student/HR terms from an optional note.
6. Unrostered submitter gets a rejection and creates no record.
7. Claim button records owner metadata and updates the original card.
8. Unrostered claimer is rejected and does not become owner.
9. Resolve button moves the record to `resolved` and notifies requester.
10. "Still blocked" creates a linked follow-up record with `extra["reopened_from"]`.
11. Existing natural-language facilities capture still works.
12. `GET /api/ops/request-summary` reports correct counts.
13. Route reachability passes.

Run:

```bash
pytest -q tests/test_sir_ops_request_center.py tests/test_slack_ops_bot.py tests/test_ops_records.py tests/test_route_reachability.py
python3 -m src.lingua_viva.cli preflight
pytest -q
```

## Acceptance Criteria

- `/ops-request` produces a structured Slack modal.
- Modal submission creates a local ops record and posts a triage card.
- Requests can be claimed by a rostered owner.
- Requests can be resolved with requester notification.
- Reopened requests are linked to the original record.
- Summary endpoint reports counts from local records.
- Existing absence/coverage and natural-language facilities flows remain green.
- Full suite and preflight pass.

## Implementation Notes

- Add stable callback/action IDs near the existing Still I Rise Slack constants.
- Prefer helper methods in `SlackOpsBot`: modal builder, modal value extractor, request-card renderer, owner assignment, resolve/reopen.
- Keep new fields in `OpsRecord.extra`; avoid schema migrations.
- If `src/web.py` changes, update `contracts/ROUTE_REACHABILITY.yaml` and UI contract lock/version/log as required.
- If tests rely on ops packs, pin `ops_packs.default_rule_set()` in fixtures to avoid global rule-set pollution.
- Leave working tree uncommitted.
