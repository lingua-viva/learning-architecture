# Slack Ops Assistant — Workspace Setup Guide (Operator)

Spec: `dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md` · Transport: Socket Mode (no public URL, no tunnel).

## 1. Create the Slack app

1. Go to https://api.slack.com/apps → **Create New App** → *From scratch*.
   Name: `Lingua Viva` · Workspace: the school workspace.
2. **Socket Mode** (left nav) → toggle ON.
   - It will prompt you to create an **app-level token**: name it `lv-socket`, add scope
     `connections:write`, generate. Copy the `xapp-…` token → this is `LV_SLACK_APP_TOKEN`.
3. **OAuth & Permissions** → *Bot Token Scopes* — add exactly these:
   - `chat:write` — send/edit bot messages
   - `channels:history`, `groups:history` — read the ops channel (public or private)
   - `im:history`, `im:write` — teacher DMs + morning briefing
   - `users:read` — resolve display names
4. **Event Subscriptions** → toggle ON (no Request URL needed — Socket Mode delivers).
   Subscribe to bot events: `message.channels`, `message.groups`, `message.im`.
5. **Interactivity & Shortcuts** → toggle ON (again, no URL — Socket Mode delivers buttons).
6. **App Home** → enable *Messages Tab* + "Allow users to send Slash commands and messages
   from the messages tab" (so teachers can DM the bot).
7. **Install App** (left nav) → *Install to Workspace* → authorize.
   Copy the **Bot User OAuth Token** (`xoxb-…`) → this is `LV_SLACK_BOT_TOKEN`.

## 2. Create the ops channel

1. Create one channel, e.g. `#school-ops` (private is fine — scopes cover both).
2. Invite the bot: `/invite @Lingua Viva`.
3. Get the channel ID: channel name → *View channel details* → bottom of the About tab
   (starts with `C` for public, `G`/`C` for private) → this is `LV_SLACK_OPS_CHANNEL`.

## 3. Map teachers

Each teacher who will use DMs/briefings needs a map entry. Get Slack member IDs
(profile → ⋮ → *Copy member ID*, starts with `U`).

```json
{"U0AAAAAAA": {"teacher_id": "claudia", "display_name": "Claudia Canu"}}
```

## 4. Set environment (on the teacher/ops machine running LV)

```bash
export LV_SLACK_BOT_TOKEN="xoxb-..."
export LV_SLACK_APP_TOKEN="xapp-..."
export LV_SLACK_OPS_CHANNEL="C0XXXXXXX"
export LV_SLACK_TEACHER_MAP='{"U0AAAAAAA":{"teacher_id":"claudia","display_name":"Claudia Canu"}}'
```

Env-only by design: never written to disk, never logged, never shown in the UI.
Optional overrides: `LV_OPS_DB_PATH` (records DB), `LV_OPS_DESKTOP_DIR` (daily-file location).

The teacher map is the roster: a Slack user who is not in it gets a polite
"ask your admin to add you" reply when DMing the bot, and cannot claim
coverage. Ops-channel messages from unmapped users are still captured
(announcements/schedule changes broadcast normally; anything per-teacher is
stored unattributed for the records audit).

## 5. Verify

1. Start LV. `GET /api/slack/ops/status` (or the Settings → Slack panel) should show
   `configured: true`, `connected: true` within a few seconds.
2. DM the bot: `I'm out tomorrow. Need coverage for 2nd period.` → expect the absence
   confirmation with buttons, a coverage card in `#school-ops`, and
   `Today - <Name>.md` updated on the Desktop.

## Privacy boundary (what the bot reads)

Only: messages in the configured ops channel, DMs sent to the bot, sender, timestamp,
thread replies that confirm status. It does not backfill history, read other channels,
ingest teacher chatter, or create student profiles from Slack.

## Limitation to know

Socket Mode requires the LV app to be running to receive messages. If the laptop is
asleep/off, Slack retries briefly and then drops the event — messages sent while LV is
offline will not appear in the daily file. (Roadmap: relay/queue option if this bites.)
