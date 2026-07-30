# Build Prompt - Still I Rise SlackBot Operational Request Center Phase 2A

You are building the next Still I Rise SlackBot workflow on top of Lingua Viva's existing Slack Daily Operations Assistant.

Read first:

```text
dev/SPEC_LV_SIR_SLACK_OPS_REQUEST_CENTER_2026-07-30.md
dev/PROPOSAL_STILL_I_RISE_SLACKBOT_WORKFLOWS_2026-07-30.md
dev/SPEC_LV_SIR_SLACK_ABSENCE_COVERAGE_MVP_2026-07-30.md
dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md
dev/reports/REPORT_SLACK_OPS_HARDENING_2026-07-27.md
```

## Hard Rules

1. **Do not commit.** Leave the working tree for the operator unless explicitly told otherwise.
2. **Do not build a general workflow engine.** Reuse `SlackOpsBot`, `OpsRecordStore`, workflow packs, and daily files.
3. **Do not add open-ended AI.** This slice is deterministic school operations.
4. **Do not request broad Slack history scopes.** Use slash commands and interactive payloads.
5. **Do not add student-lens writes.** Slack ops remains separate from student evidence.
6. **Do not add database categories unless you prove they are necessary.** Store request subtype in `OpsRecord.extra`.
7. **Do not leak private details into public Slack cards.**

## Step 0: Orient And Baseline

Run:

```bash
git status --short --branch --untracked-files=all
pytest -q tests/test_sir_absence_coverage.py tests/test_slack_ops_bot.py tests/test_slack_socket.py tests/test_ops_records.py tests/test_ops_packs.py
python3 -m src.lingua_viva.cli preflight
```

If baseline fails, determine whether the failure is inherited before editing. Do not revert unrelated dirty work.

## Step 1: Add Stable Constants And Modal Builder

In `src/education/slack_ops_bot.py`, add stable IDs for the new workflow:

```python
SIR_OPS_REQUEST_MODAL_CALLBACK_ID = "sir_ops_request_modal"
SIR_OPS_REOPEN_MODAL_CALLBACK_ID = "sir_ops_request_reopen_modal"
```

Add `/ops-request` handling in the existing slash-command path.

The modal must include:

- request type: facilities / IT / supplies
- campus
- location
- severity
- description
- teaching blocked yes/no
- optional photo/link
- follow-up preference

Keep `/absence` behavior unchanged.

## Step 2: Handle Request Modal Submission

Handle `view_submission` for `sir_ops_request_modal`.

Implementation:

- Require the submitting Slack user to exist in `teacher_map`.
- Create an `OpsRecord` with `category="facilities"`.
- Store subtype and structured fields in `record.extra`.
- Include `workflow="sir_ops_request"`.
- Post a triage card to `ops_channel`.
- DM the requester a short receipt.
- Refresh daily files.

Suggested status:

- `needs_review` for `severity in {"teaching_blocked", "urgent"}`.
- `logged` for routine/same-day requests.

If the current store API makes `needs_review` records easier through `needs_review=True`, use that instead of manually forcing status.

## Step 3: Add Triage Card Actions

The public card should contain:

- request ID
- request type
- campus
- location
- severity
- short description
- owner/status line

Buttons:

- `Claim`
- `Resolve`
- `Need info` or `Still blocked` only if it fits the current code cleanly

Required action IDs:

```text
ops_request_claim
ops_request_resolve
ops_request_still_blocked
```

When a rostered user clicks `Claim`:

- write `owner_slack_id`, `owner_name`, `owner_claimed_at` into `extra`
- mark `needs_review -> logged` if appropriate
- update original card
- notify requester by DM if requester Slack ID is known

Unrostered claimers must receive the existing unknown-user message and must not become owner.

## Step 4: Resolve And Reopen

When owner or ops lead clicks `Resolve`:

- move `logged -> resolved`
- write `resolved_by`, `resolved_at`, and optional `resolution_note` in `extra`
- update original card
- DM requester that it was marked resolved

When requester says/clicks `Still blocked`:

- create a new `facilities` record with `needs_review=True`
- copy safe fields from the original
- set `extra["reopened_from"] = original_record_id`
- do not mutate the original resolved record back and forth unless the store already has a safe transition

Minimum acceptable path: a direct button creates the linked follow-up record with a generic "Still blocked" note.

## Step 5: Keep Natural-Language Facilities Capture Green

Existing deterministic messages must still classify and record:

```text
The projector in room 12 isn't working.
Photocopier is broken again.
Need more markers for the art room.
```

Do not break `config/ops_packs/facilities.yaml` parity. If you extend natural-language facilities to post triage cards, cover both the new behavior and the existing capture expectations in tests.

## Step 6: Add Request Summary Endpoint

Add:

```text
GET /api/ops/request-summary?date=YYYY-MM-DD
```

Compute from `OpsRecordStore` only. Count records where:

```python
record.category == "facilities"
record.extra.get("workflow") == "sir_ops_request"
```

Return:

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

Update `contracts/ROUTE_REACHABILITY.yaml`. If no visible UI call is added, classify this route as `intentionally_backend_only` with a clear reason.

If `src/web.py` changes, bump/relock the UI contract and update `tests/test_ui_contract.py`.

## Step 7: Tests

Add `tests/test_sir_ops_request_center.py`.

Cover:

- `/ops-request` opens modal
- modal submit creates a `facilities` record with structured `extra`
- public card does not leak private/student/HR details
- unrostered submitter rejected
- claim records owner metadata and updates card
- unrostered claimer rejected
- resolve moves to `resolved`
- still-blocked creates linked follow-up
- natural-language facilities capture still works
- request summary endpoint counts correctly

Important test hygiene:

- Pin `ops_packs.default_rule_set()` in fixtures for `SlackOpsBot` and `DailyFileEngine`.
- Use fake Slack clients; no network.
- Isolate `LV_OPS_DB_PATH`, `LV_OPS_DESKTOP_DIR`, `LV_OPS_STATE_PATH`, and privacy log paths.

## Step 8: Verification

Run focused:

```bash
pytest -q tests/test_sir_ops_request_center.py tests/test_sir_absence_coverage.py tests/test_slack_ops_bot.py tests/test_ops_records.py tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

Then run:

```bash
pytest -q
```

If full suite fails because another test mutated process-wide ops pack state, fix the fixture isolation rather than weakening the product behavior.

## Final Report

Report:

- files changed
- whether `/ops-request` modal is built
- whether claim/resolve/reopen are built
- whether natural-language facilities capture still works
- request-summary route classification
- focused test result
- preflight result
- full suite result

Do not claim live Slack production readiness unless a real Slack workspace was used end to end.
