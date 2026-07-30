# SPEC: Still I Rise SlackBot - Absence + Coverage MVP

**Date**: 2026-07-30
**Status**: DRAFT - build handoff
**Proposal source**: `dev/PROPOSAL_STILL_I_RISE_SLACKBOT_WORKFLOWS_2026-07-30.md`
**Primary surface**: Lingua Viva Slack Daily Operations Assistant
**Priority rationale**: staff absence and substitute coverage is the highest-leverage Still I Rise SlackBot workflow because it is urgent, frequent, auditable, and already close to the existing Lingua Viva Slack ops architecture.

---

## Goal

Add a structured absence-intake and coordinator-approved coverage flow on top of the current Lingua Viva Slack ops assistant.

This is **not** a broad AI assistant. It is a deterministic school-operations workflow:

```text
Report absence -> create records -> route coverage request -> claim -> coordinator confirm -> notify -> daily summary
```

## Existing Repo Capabilities To Reuse

| Capability | Existing implementation | Use in this build |
|---|---|---|
| Socket Mode transport | `src/lingua_viva/slack_socket.py` | Reuse envelope dispatch, ack-before-processing, post/update/open_dm methods. |
| Slash command envelope dispatch | `DISPATCHED_ENVELOPE_TYPES` includes `slash_commands`; tests already cover dispatch. | Add `/absence` handling in `SlackOpsBot`. |
| Interactive buttons | `SlackOpsBot._handle_block_actions()` | Add coordinator confirmation actions and optional modal submission handling. |
| Ops records | `src/education/ops_records.py` | Store absence and coverage records; extend `extra` for structured fields. |
| Coverage status machine | `open -> claimed -> confirmed` | Change Still I Rise path to `open -> claimed -> confirmed`, but require coordinator confirmation between claim and final `confirmed`. |
| Daily file | `src/education/daily_file.py` | Continue rendering coverage/absence status. |
| Workflow packs | `config/ops_packs/absence_coverage.yaml` | Keep pack semantics; no new general workflow engine. |
| Bot Setup/corpus gate | `ops_bot_spec.py`, `ops_corpus.py`, setup UI | Do not rewrite; add only settings seams needed for this MVP if necessary. |

## Current Gaps This Spec Closes

1. No structured `/absence` command or Slack modal intake.
2. Coverage claims auto-confirm today; Still I Rise needs coordinator approval before final assignment.
3. Staff directory is too thin for production routing, but the first build can store and expose the shape without requiring a full HR integration.
4. Daily staffing summary does not yet report coverage counts as a campus command view.

---

## Build Scope

### Slice 1: `/absence` Command Opens A Structured Modal

When Slack sends a `slash_commands` envelope with `command: "/absence"`, the bot should open a modal.

Add a Slack Web API helper if needed:

```python
SlackSocketClient.open_view(trigger_id: str, view: dict) -> bool
```

Implementation details:

- Use `views.open`.
- Never log token values or modal payload contents.
- Return `False` on Slack API errors, same posture as `open_dm()`.
- Tests use injected urlopen/fake client; no network.

Modal fields:

- campus
- date
- full day or periods
- grade/class
- subject/responsibility
- absence type: planned leave / illness / emergency / late arrival
- coverage needed: yes/no
- handover or lesson-plan link
- emergency plan available: yes/no
- coordinator should contact teacher: yes/no
- optional private note

Privacy rule:

- Do not post absence type/private note/medical explanation into public channels.
- Store sensitive/private details only in the local ops record `extra` field.

### Slice 2: Modal Submission Creates Absence + Coverage Records

Handle Slack interactive `view_submission` payloads for the absence modal.

Expected behavior:

- Validate the submitting Slack user is in `teacher_map`.
- Create an `absence` record with structured fields in `extra`.
- If coverage is needed, create a `coverage_request` record.
- Post a coverage card to the configured ops channel.
- DM the absent teacher a receipt.
- Refresh daily files.

Record `extra` should include structured values, for example:

```json
{
  "campus": "Nairobi",
  "grade_class": "Grade 7",
  "subject": "Mathematics",
  "absence_type": "illness",
  "handover_link": "https://...",
  "emergency_plan": true,
  "contact_teacher": false,
  "private_note_present": true
}
```

Do not put raw private note text in public Slack messages.

### Slice 3: Coordinator-Confirmed Coverage

Today `_claim_coverage()` immediately transitions `open -> claimed -> confirmed`.

For Still I Rise coverage requests, change behavior to:

1. Claim button transitions `open -> claimed`.
2. Coverage card updates to tentative text:

```text
Coverage claimed: <claimer>. Awaiting coordinator confirmation.
```

3. Coordinator receives a DM or ops-channel threaded message with buttons:

- Confirm assignment
- Choose another person

4. Confirm button transitions `claimed -> confirmed`.
5. Final message updates original coverage card and notifies requester.

Implementation guidance:

- Preserve backward compatibility if no coordinator is configured: either keep current auto-confirm behavior or use ops-channel confirmation. Document the chosen behavior in code/tests.
- Store `claim_by`, `claim_at`, and `coordinator_confirmed_by` / `coordinator_confirmed_at` in record fields or `extra`.
- Do not add new status strings unless necessary. The existing store supports `claimed` and `confirmed`; use those.

### Slice 4: Partial Coverage Form

Add a second button on coverage cards:

- Claim all
- Claim part

`Claim part` should open a small modal asking which periods/time window the claimer can cover.

Minimum acceptable first build:

- If modal support is too broad for this slice, store partial coverage as `extra["partial_claim"]` from a simplified button payload and mark the record `needs_review=True`.
- Do not pretend partial coverage is fully resolved unless all requested periods are covered.

### Slice 5: Daily Staffing Summary Endpoint

Add a read-only endpoint that summarizes coverage status for a date:

```text
GET /api/ops/staffing-summary?date=YYYY-MM-DD
```

Response fields:

- date
- reported_absences
- coverage_requests
- fully_covered
- awaiting_coverage
- claimed_awaiting_confirmation
- substitute_periods_assigned
- critical_unfilled

Use `OpsRecordStore` only. Do not call Slack or external services.

Add a small section in the Daily view if appropriate, but do not expand UI scope if backend/reporting is the safer first slice.

---

## Out Of Scope

- No general AI assistant.
- No unrestricted Slack history reading.
- No HR-system integration.
- No timetable/calendar integration.
- No cross-country central dashboard.
- No SMS/phone fallback.
- No safeguarding workflow.
- No production-grade availability optimizer.
- No full Slack App Home command center.

## Privacy / Permission Rules

The build must preserve the current Slack ops boundary:

- Only DMs, slash commands, interactive payloads, and configured ops/coverage channels are acted on.
- Other channels are ignored.
- Group DMs are not treated as private DMs.
- Slack messages never update student lenses.
- Audit logs carry structural identifiers, not message text.
- Broad history scopes are not required for the `/absence` MVP.

Recommended Slack scopes for this build:

- `commands`
- `chat:write`
- `users:read`
- `channels:read`
- `im:history` only if DM intake remains enabled

Avoid `channels:history`, `groups:history`, and `mpim:history` unless a future spec explicitly requires message surveillance in designated channels.

## Tests

Add focused tests in existing Slack suites:

1. `/absence` slash command opens the absence modal.
2. Unknown slash command is ignored gracefully.
3. Absence modal submission from rostered teacher creates absence record.
4. Modal submission with coverage needed creates coverage request and posts a coverage card.
5. Private note / absence type does not appear in public coverage card text.
6. Unrostered modal submitter gets an honest failure and creates no record.
7. Claim all moves coverage from `open` to `claimed`, not directly to `confirmed`, when coordinator confirmation is enabled.
8. Confirm assignment moves `claimed` to `confirmed` and updates the original card.
9. Double-claim / stale confirm buttons degrade gracefully.
10. `GET /api/ops/staffing-summary` reports correct counts from hermetic records.

Run:

```bash
pytest -q tests/test_slack_socket.py tests/test_slack_ops_bot.py tests/test_ops_records.py tests/test_ops_app_integration.py tests/test_route_reachability.py
pytest -q
python3 -m src.lingua_viva.cli preflight
```

## Acceptance Criteria

- `/absence` works through Slack slash command payloads.
- Structured modal submissions create local records without relying on AI.
- Coverage claim no longer silently becomes final when coordinator confirmation is configured.
- Public Slack messages contain operational coverage facts, not private absence explanations.
- Daily staffing summary is generated from records.
- Existing natural-language absence DM flow still works.
- Existing ops suites remain green.
- Full suite and preflight pass.

## Implementation Notes

- Prefer small helper functions in `SlackOpsBot` for modal construction and payload extraction.
- Keep modal block IDs/action IDs stable and testable.
- Keep all new Slack client methods injectable/offline-testable.
- Store structured fields in `OpsRecord.extra` first; do not migrate the SQLite schema unless a field must be queried often.
- If a new route is added, update `contracts/ROUTE_REACHABILITY.yaml`.
- If `src/web.py` or `static/index.html` changes, update the UI contract lock and bump log.
