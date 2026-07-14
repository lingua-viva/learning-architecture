# Bridge Wiring Record — IO-20260714-ead72c

**Purpose**: Generic capture-only bot for archiving.
**Pattern**: CAPTURE
**Platform**: slack
**Channels**: (none specified)
**Output destination**: local_store
**Governance**: blocks_external=True, requires_local=True
**Rationale**: No external routing needed for this integration.

## Wiring steps (Governed Capture pattern)

1. Base contract: `src/education/slack_bot.py` (Events API webhook receiver, signed-request verification).
2. Extract and tag-parse the transcript per the existing `extract_transcript` / tag-parsing pattern — never guess an identity from absence.
3. Deduplicate by `event_id` before any side effect.
4. Write only to the local store named in `scope.output_destination` above — never echo content back, never call an external model.
5. This pattern defaults `blocks_external: true` — if governance widened it, re-confirm that's actually intended for a capture-only integration.
