# Build Prompt - Still I Rise SlackBot Schedule Change Acknowledgements Phase 2B

You are building the next Still I Rise SlackBot workflow on top of Lingua Viva's Slack Daily Operations Assistant.

This is the selected next build because `dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30_2.md` ranks schedule-change acknowledgements as the highest-leverage remaining slice: absence/coverage and operational requests are now built or in-flight, while schedule changes still broadcast without acknowledgement tracking.

Read first:

```text
dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30_2.md
dev/SPEC_LV_SIR_SLACK_SCHEDULE_ACKS_2026-07-30.md
dev/PROPOSAL_STILL_I_RISE_SLACKBOT_WORKFLOWS_2026-07-30.md
dev/SPEC_LV_SIR_SLACK_ABSENCE_COVERAGE_MVP_2026-07-30.md
dev/SPEC_LV_SIR_SLACK_OPS_REQUEST_CENTER_2026-07-30.md
dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md
dev/reports/REPORT_SLACK_OPS_HARDENING_2026-07-27.md
```

## Hard Rules

1. **Do not commit.** Leave the working tree for the operator unless explicitly told otherwise.
2. **Do not add a calendar/timetable integration.** This is acknowledgement tracking only.
3. **Do not add broad Slack history scopes.** Use slash commands, modals, buttons, and current ops-channel/DM boundaries.
4. **Do not add AI.** This is deterministic operations routing.
5. **Do not write to student lenses.**
6. **Do not invent new DB tables or statuses unless there is no clean alternative.** Prefer `OpsRecord.extra` and existing `needs_review`.
7. **Preserve existing natural-language schedule-change capture.**

## Step 0: Orient And Baseline

Run:

```bash
git status --short --branch --untracked-files=all
pytest -q tests/test_sir_absence_coverage.py tests/test_sir_ops_request_center.py tests/test_slack_ops_bot.py tests/test_ops_records.py tests/test_ops_packs.py
python3 -m src.lingua_viva.cli preflight
```

The repo may already contain uncommitted work from the previous build. Identify inherited failures before editing and do not revert unrelated changes.

## Step 1: Add Constants And `/schedule-change`

In `src/education/slack_ops_bot.py`, add stable IDs:

```python
SIR_SCHEDULE_CHANGE_MODAL_CALLBACK_ID = "sir_schedule_change_modal"
SIR_SCHEDULE_ACK_WORKFLOW = "sir_schedule_ack"
```

Add slash-command handling:

- `/schedule-change` opens a modal
- `/absence` and `/ops-request` must keep working
- unknown slash commands remain no-op

Modal fields:

- campus
- affected scope
- affected staff, optional
- effective date
- changed item
- old time/location, optional
- new time/location
- short description
- acknowledgement required yes/no

## Step 2: Handle Modal Submission

Handle `view_submission` for `sir_schedule_change_modal`.

Implementation:

- Validate submitter is rostered unless the existing code has a clearer admin boundary.
- Resolve affected Slack IDs:
  - if explicit staff supplied, match Slack IDs and/or display-name fragments from `teacher_map`
  - if blank, use all `teacher_map` keys
- Create one `schedule_change` record.
- Store `workflow="sir_schedule_ack"` and structured schedule fields in `extra`.
- Store empty `acknowledgements`.
- Refresh daily files.
- Post an ops-channel summary card.
- If acknowledgement is required, DM each affected staff member a card with `Seen`, `Conflict`, and `Need clarification`.

Do not DM unknown staff identifiers; record skipped identifiers in `extra["unmatched_targets"]`.

## Step 3: Add Acknowledgement Actions

Add action IDs:

```text
ops_schedule_seen
ops_schedule_conflict
ops_schedule_clarify
```

On click:

- Load the record by button value.
- Require the Slack user to be in `extra["affected_slack_ids"]`.
- Write `extra["acknowledgements"][user_id]` with status, display name, and timestamp.
- For conflict/clarification, mark the record review-needed.
- Refresh daily files.
- Update the ops-channel summary card if `extra["card_ts"]` exists.
- Post or DM a short receipt.

Do not echo any private note or raw sensitive content into public channels.

## Step 4: Summary Rendering Helper

Add a helper that computes:

- target count
- seen count
- conflict count
- clarification count
- missing count

Use it for the ops card and for the API endpoint.

Keep the card concise, for example:

```text
Schedule change: Assembly -> 10:30, Nairobi.
Acknowledged: 1/3. Conflicts: 1. Needs clarification: 0.
```

## Step 5: Add Summary Endpoint

Add:

```text
GET /api/ops/schedule-ack-summary?date=YYYY-MM-DD
```

Compute only from `OpsRecordStore`.

Return:

- `date`
- `schedule_changes`
- `ack_required`
- `fully_acknowledged`
- `missing_acknowledgement`
- `conflicts`
- `needs_clarification`
- `changes`

Each `changes` row should include:

- `record_id`
- `campus`
- `changed_item`
- `target_count`
- `seen_count`
- `conflict_count`
- `clarification_count`
- `missing_count`

Update `contracts/ROUTE_REACHABILITY.yaml`. If no visible UI call is added, classify it as `intentionally_backend_only`.

If `src/web.py` changes, bump/relock `contracts/UI_CONTRACT.yaml` and `contracts/UI_CONTRACT.lock`, then update `tests/test_ui_contract.py`.

## Step 6: Tests

Add `tests/test_sir_schedule_acks.py`.

Cover:

- `/schedule-change` opens modal
- modal submit creates `schedule_change` record with `workflow="sir_schedule_ack"`
- blank affected staff targets all rostered teachers
- explicit affected staff targets only those users
- acknowledgement-required submission DMs target users
- `Seen` records status
- `Conflict` records status and marks review-needed
- `Need clarification` records status and marks review-needed
- unaffected/unrostered user cannot acknowledge
- ops summary card updates counts
- natural-language schedule change still lands in every daily file
- summary endpoint reports counts

Test hygiene:

- Use fake Slack clients.
- No network.
- Isolate `LV_OPS_DB_PATH`, `LV_OPS_DESKTOP_DIR`, `LV_OPS_STATE_PATH`, and privacy log paths.
- Pin `ops_packs.default_rule_set()` in bot/daily fixtures.

## Step 7: Verification

Run focused:

```bash
pytest -q tests/test_sir_schedule_acks.py tests/test_sir_absence_coverage.py tests/test_sir_ops_request_center.py tests/test_slack_ops_bot.py tests/test_ops_records.py tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

Then run:

```bash
pytest -q
```

If full suite fails from process-wide ops pack state, fix fixture isolation. Do not weaken the product behavior.

## Final Report

Report:

- files changed
- whether `/schedule-change` modal is built
- how affected staff are resolved
- acknowledgement button behavior
- summary endpoint route classification
- whether natural-language schedule capture still works
- focused test result
- preflight result
- full suite result

Do not claim live Slack production readiness unless a real Slack workspace was used end to end.
