# Build Prompt - Still I Rise SlackBot Absence + Coverage MVP

You are building the first Still I Rise SlackBot workflow on top of Lingua Viva's existing Slack ops assistant.

Read first:

```text
dev/SPEC_LV_SIR_SLACK_ABSENCE_COVERAGE_MVP_2026-07-30.md
dev/PROPOSAL_STILL_I_RISE_SLACKBOT_WORKFLOWS_2026-07-30.md
dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md
dev/reports/REPORT_SLACK_OPS_HARDENING_2026-07-27.md
```

## Hard Rules

1. **Do not commit.** Leave the working tree for the operator.
2. **Do not build a general workflow engine.** Reuse the current ops records, Slack bot, workflow packs, and daily-file machinery.
3. **Do not add open-ended AI.** This is deterministic school operations.
4. **Do not request broad Slack history scopes.** `/absence` should work through commands/interactivity, not surveillance.
5. **Do not leak private absence details.** Public coverage cards must not include medical/private notes.
6. **Do not let Slack ops touch student lenses.** Keep the existing boundary.

## Step 0: Orient And Baseline

Run:

```bash
git status --short --branch
pytest -q tests/test_slack_socket.py tests/test_slack_ops_bot.py tests/test_ops_records.py tests/test_ops_app_integration.py tests/test_ops_packs.py tests/test_ops_corpus.py
python3 -m src.lingua_viva.cli preflight
```

If baseline fails, identify whether it is inherited before editing.

## Step 1: Add Slack `views.open` Helper If Needed

In `src/lingua_viva/slack_socket.py`, add an injectable method like:

```python
async def open_view(self, trigger_id: str, view: dict) -> bool:
    ...
```

Use Slack Web API `views.open`. Follow existing `post_message`, `update_message`, and `open_dm` error posture.

Tests:

- success returns true
- Slack API error returns false
- payload does not log/expose tokens

## Step 2: Add `/absence` Command Handling

In `src/education/slack_ops_bot.py`:

- Extend `on_envelope()` for `slash_commands`.
- If command is `/absence`, build and open the absence modal.
- Unknown slash commands remain no-op.

Keep modal block/action IDs stable. Suggested IDs:

- `sir_absence_modal`
- `campus`
- `date_for`
- `periods`
- `grade_class`
- `subject`
- `absence_type`
- `coverage_needed`
- `handover_link`
- `emergency_plan`
- `contact_teacher`
- `private_note`

## Step 3: Handle Absence Modal Submission

Handle interactive payloads with `type: view_submission` and `callback_id: sir_absence_modal`.

Implementation:

- Extract values defensively.
- Require rostered Slack user.
- Create `absence` record.
- Store structured fields in `extra`.
- If coverage is needed, create `coverage_request` and post coverage card.
- DM receipt to requester.
- Refresh daily files.

No public message may include private note text.

## Step 4: Coordinator Confirmation

Modify coverage claim behavior carefully.

Target behavior when coordinator confirmation is enabled:

- Claim button changes record `open -> claimed`.
- Original card updates to "Coverage claimed: <claimer>. Awaiting coordinator confirmation."
- Confirmation controls are sent to the configured coordinator/ops channel.
- Confirm button changes `claimed -> confirmed`.
- Final card says coverage filled.
- Requester gets a DM.

Do not add new store statuses unless truly necessary. Prefer `extra` metadata for coordinator fields.

Backward compatibility:

- If no coordinator confirmation setting exists, preserve current auto-confirm behavior or explicitly choose a safe default and pin it in tests.

## Step 5: Partial Coverage Minimal Path

Add `Claim part` as a visible option.

Minimum acceptable behavior:

- opens a modal or records a partial-claim marker
- does not mark request confirmed
- sets `needs_review=True` if full coverage cannot be proven

Do not overbuild period coverage optimization in this slice.

## Step 6: Staffing Summary Endpoint

Add:

```text
GET /api/ops/staffing-summary?date=YYYY-MM-DD
```

Compute from `OpsRecordStore`:

- reported_absences
- coverage_requests
- fully_covered
- awaiting_coverage
- claimed_awaiting_confirmation
- substitute_periods_assigned
- critical_unfilled

If you touch `src/web.py`, update:

- route reachability manifest
- UI contract lock if protected files require it

## Step 7: Tests

Add or update tests for:

- `/absence` opens modal
- modal submission creates records
- private note is not in public Slack card
- unrostered submitter creates no record
- claim stays `claimed` until coordinator confirms
- confirm action moves to `confirmed`
- partial claim stays review-needed
- staffing summary counts correctly
- existing DM absence flow still works

Run focused tests:

```bash
pytest -q tests/test_slack_socket.py tests/test_slack_ops_bot.py tests/test_ops_records.py tests/test_ops_app_integration.py tests/test_route_reachability.py
```

Then run:

```bash
pytest -q
python3 -m src.lingua_viva.cli preflight
```

## Final Report

In your final response, report:

- files changed
- whether `/absence` modal path is built
- whether coordinator confirmation is built
- what remains out of scope
- focused test result
- full test result
- preflight result

Do not claim production Slack readiness unless a real Slack workspace was used end-to-end. Hermetic tests prove implementation wiring, not live Slack configuration.
