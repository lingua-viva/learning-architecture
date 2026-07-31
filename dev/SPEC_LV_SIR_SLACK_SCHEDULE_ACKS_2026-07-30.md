# SPEC: Still I Rise SlackBot - Schedule Change Acknowledgements Phase 2B

**Date**: 2026-07-30
**Status**: SHIPPED - committed `2fa5cd9`, tested
**Proposal source**: `dev/PROPOSAL_STILL_I_RISE_SLACKBOT_WORKFLOWS_2026-07-30.md`
**Previous slices**:

- `dev/SPEC_LV_SIR_SLACK_ABSENCE_COVERAGE_MVP_2026-07-30.md`
- `dev/SPEC_LV_SIR_SLACK_OPS_REQUEST_CENTER_2026-07-30.md`

**Primary surface**: Lingua Viva Slack Daily Operations Assistant
**Selection rationale**: `dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30_2.md` ranks this as the highest-leverage next slice after absence/coverage and operational requests. It completes the third Still I Rise Slack workflow family while reusing existing ops records, workflow packs, buttons, DMs, and daily files.

---

## Goal

Turn schedule and timetable changes into acknowledged operational updates.

The current Slack ops assistant already captures schedule changes from the configured ops channel and broadcasts them into every teacher's daily file. This slice adds a deterministic acknowledgement loop:

```text
Schedule change -> targeted notification -> Seen / Conflict / Need clarification -> coordinator summary
```

This is not calendar integration and not a timetable optimizer. It is a low-risk workflow that proves staff saw an operational change and gives coordinators a list of conflicts and non-responders.

## Existing Repo Capabilities To Reuse

| Capability | Existing implementation | Use in this build |
|---|---|---|
| Schedule-change pack | `config/ops_packs/schedule_changes.yaml` | Keep natural-language schedule capture working. |
| Broadcast daily files | `schedule_change` is a broadcast category | Continue writing schedule changes into all mapped teachers' daily files. |
| Slack Socket Mode | `src/lingua_viva/slack_socket.py` | Reuse posts, updates, DMs, interactive buttons, slash commands. |
| Slash commands/modals | `/absence` and `/ops-request` patterns | Add `/schedule-change` structured intake. |
| Ops records | `src/education/ops_records.py` | Store the schedule change and acknowledgement state in `extra`. |
| Bot setup packs | `ops_packs`, `ops_bot_spec` | Do not rewrite pack configuration. |
| Route contracts | `contracts/ROUTE_REACHABILITY.yaml` | Classify any new endpoint. |

## Current Gaps This Spec Closes

1. Schedule changes are captured, but staff acknowledgement is not tracked.
2. Coordinators cannot see who has not seen a change.
3. Staff cannot mark "conflict" or "need clarification" from the Slack card.
4. There is no summary endpoint for acknowledged vs. unresolved changes.

## Data Model

Do not add a new database table unless absolutely necessary. Store acknowledgement state in `OpsRecord.extra` on a `schedule_change` record.

Recommended `extra` shape:

```json
{
  "workflow": "sir_schedule_ack",
  "campus": "Nairobi",
  "affected_scope": "grade_7",
  "affected_slack_ids": ["U111", "U222"],
  "changed_item": "Assembly",
  "new_time": "10:30",
  "effective_date": "2026-07-31",
  "acknowledgements": {
    "U111": {
      "status": "seen",
      "display_name": "Ana Ruiz",
      "at": "2026-07-30T19:00:00Z"
    },
    "U222": {
      "status": "conflict",
      "display_name": "Ben Ali",
      "at": "2026-07-30T19:05:00Z",
      "note": "I have coverage period 2."
    }
  }
}
```

Allowed acknowledgement statuses:

- `seen`
- `conflict`
- `need_clarification`

The record status can remain `logged` until every targeted staff member has acknowledged with `seen`. If any staff member reports `conflict` or `need_clarification`, keep the record unresolved and mark `needs_review=True`.

## Build Scope

### Slice 1: `/schedule-change` Command Opens A Structured Modal

When Slack sends `slash_commands` with `command: "/schedule-change"`, open a modal.

Modal fields:

- campus
- affected scope: whole campus / grade / department / named staff
- affected staff Slack IDs or comma-separated display names, optional
- effective date
- changed item
- old time/location, optional
- new time/location
- short description
- acknowledgement required: yes/no

If no affected staff are specified, target all teachers in `teacher_map` for this first build.

### Slice 2: Modal Submission Creates Schedule Record + Notification Card

Handle `view_submission` for the schedule-change modal.

Expected behavior:

- Require submitting Slack user to be rostered or otherwise allow only configured ops channel users if the current bot has no role directory.
- Create one `schedule_change` record.
- Store structured fields and empty `acknowledgements` in `extra`.
- Refresh daily files.
- Post an ops-channel summary card.
- If acknowledgement is required, DM each affected rostered user a card with buttons:
  - `Seen`
  - `Conflict`
  - `Need clarification`

Do not include student details. Do not DM non-rostered Slack IDs.

### Slice 3: Acknowledgement Buttons

Add interactive action IDs:

- `ops_schedule_seen`
- `ops_schedule_conflict`
- `ops_schedule_clarify`

When clicked:

- Validate the Slack user is in the affected audience.
- Update `record.extra["acknowledgements"][user_id]`.
- Update or post a concise acknowledgement receipt.
- Refresh daily files.
- Update the ops-channel summary card if its `card_ts` is known.

Conflict and clarification can use a minimum first-build path:

- Button click records the status and posts "Coordinator will follow up."
- Optional note modal is acceptable but not required for Phase 2B.

### Slice 4: Missing-Acknowledgement Summary

Add a read-only endpoint:

```text
GET /api/ops/schedule-ack-summary?date=YYYY-MM-DD
```

Compute from `OpsRecordStore` only.

Response fields:

- `date`
- `schedule_changes`
- `ack_required`
- `fully_acknowledged`
- `missing_acknowledgement`
- `conflicts`
- `needs_clarification`
- `changes`: array with record id, changed item, campus, target count, seen count, conflict count, clarification count, missing count

Classify this route as `intentionally_backend_only` unless the build also adds a visible UI call.

### Slice 5: Natural-Language Schedule Capture Remains Green

Existing ops-channel messages must still work:

- "Assembly moved to 10:30 today."
- "Tomorrow's fire drill is postponed."
- "Lunch is now at 12:15 for the whole school."

Natural-language schedule capture may remain capture-only with daily-file broadcast. Do not force acknowledgement tracking onto every informal schedule message unless the implementation can do so without false positives.

## Out Of Scope

- No Google Calendar or timetable source-of-truth integration.
- No automatic affected-staff inference from real timetable data.
- No broad Slack history reading.
- No Slack App Home dashboard.
- No SMS/phone fallback.
- No emergency/safeguarding workflow.
- No student-lens writes.
- No AI summarization or conflict adjudication.
- No production live Slack verification unless the operator provides a real workspace.

## Privacy / Permission Rules

- Act only on slash commands, interactive payloads, DMs, and configured ops channel events.
- Do not treat group DMs as private DMs.
- Do not add `channels:history`, `groups:history`, or `mpim:history`.
- Do not include student names in schedule-change cards.
- Do not log Slack tokens or raw private notes.
- Store acknowledgement state locally in ops records.

Recommended Slack scopes remain:

- `commands`
- `chat:write`
- `users:read`
- `channels:read`

## Tests

Add focused tests, preferably in `tests/test_sir_schedule_acks.py`:

1. `/schedule-change` opens a modal.
2. Unknown slash commands still no-op.
3. Modal submit creates a `schedule_change` record with `extra["workflow"] == "sir_schedule_ack"`.
4. Empty affected-staff input targets all rostered teachers.
5. Acknowledgement-required submission DMs every affected teacher.
6. `Seen` button records `status="seen"` for that user.
7. `Conflict` button records `status="conflict"` and marks the record review-needed.
8. `Need clarification` records `status="need_clarification"` and marks the record review-needed.
9. Unaffected/unrostered user cannot acknowledge the change.
10. Ops-channel summary card updates counts after acknowledgements.
11. Natural-language schedule capture still broadcasts to every daily file.
12. `GET /api/ops/schedule-ack-summary` reports missing, seen, conflict, and clarification counts.
13. Route reachability passes.

Run:

```bash
pytest -q tests/test_sir_schedule_acks.py tests/test_slack_ops_bot.py tests/test_ops_records.py tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
pytest -q
```

## Acceptance Criteria

- `/schedule-change` structured intake works through Slack modal payloads.
- Schedule changes are recorded locally and still appear in daily files.
- Affected staff receive acknowledgement buttons.
- Seen/conflict/clarification states are stored in `OpsRecord.extra`.
- Coordinators can retrieve a local summary of missing acknowledgements.
- Existing schedule-change pack behavior stays green.
- Existing absence/coverage and ops-request tests remain green.
- Full suite and preflight pass.

## Implementation Notes

- Add stable callback/action IDs beside existing Still I Rise constants in `SlackOpsBot`.
- Prefer small helpers: build modal, extract modal values, render schedule card, update acknowledgement, summarize acknowledgement state.
- Keep status-machine changes minimal. Use `needs_review` plus `extra` instead of adding new statuses.
- If tests instantiate `SlackOpsBot`, pin `ops_packs.default_rule_set()` in the fixture to avoid process-wide rule-set pollution.
- If `src/web.py` changes, update route reachability and UI contract version/lock/test pin.
- Leave working tree uncommitted.
