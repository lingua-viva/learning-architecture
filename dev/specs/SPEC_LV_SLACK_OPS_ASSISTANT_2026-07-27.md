# SPEC — LV Slack Daily Operations Assistant

Date: 2026-07-27 · Status: APPROVED (operator decisions locked) · Build window: 2 days
Supersedes the *scope* (not the code) of `SPEC_LV_SLACK_APP_INTEGRATION_2026-07-22.md` for the Slack surface.

## 0. North Star (operator, 2026-07-27)

> A teacher-facing daily operations assistant that turns Slack messages into clean local
> daily files, reminders, and updates inside Lingua Viva.

- Slack is the capture/coordination surface. Lingua Viva on the teacher's computer is where
  the organized record lives.
- **Slack messages NEVER create or update student lenses.** The Jul 22 observation path
  stays committed but dormant; this assistant is a separate module and never calls
  `ObservationCapturePipeline` or `StudentLensStore`.
- The bot's product is a **file**: `Today - <Teacher>.md` on the teacher's Desktop,
  plus structured logs inside LV.
- Enterprise Slack patterns applied to schools: intake, routing, reminders, status updates.

## 1. v1 Scope — ONLY these five workflows

1. **Teacher absence reporting** — "I'm out tomorrow. Fever. Need coverage for 2nd and 4th period."
2. **Substitute coverage** — request → post with *Claim coverage* button → claim → "Coverage filled: <name>, <window>" status update.
3. **Daily announcements** — admin posts in the ops channel; ingested into daily files.
4. **Schedule changes** — "Assembly moved to 10:30." → ingested, flagged in daily files.
5. **Teacher-specific daily file** — morning briefing DM + live-updated Desktop file + end-of-day summary.

Everything else (facilities, forms tracking, parent-meeting logistics, student profiles,
voice notes, LLM parsing) is explicitly OUT of v1. Facilities/student-logistics messages are
still *classified and captured to the daily file* (cheap, same pipeline) but get no workflow.

## 2. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Transport | **Socket Mode**, implemented directly over `websockets` (already a core dep) + stdlib urllib. NO slack_bolt/slack_sdk. | No public URL/tunnel from a teacher's laptop; buttons arrive over the same socket; zero new dependencies (frozen-binary safe); matches Jul 22 spec's stdlib discipline. |
| Review model | Items land in the daily file immediately; low-confidence/ambiguous items go to a **To Review** section + one-question button clarification in Slack. | Ops data is low-risk vs student lenses; keeps the review-before-trust principle without an approval bottleneck. |
| Daily file location | **Real Desktop file** `~/Desktop/Today - <Teacher>.md` (rendered output). Canonical state lives under `lv_home()/ops/`. Archive to `~/Desktop/Daily Updates/YYYY-MM-DD.md` on daily reset. | The North Star promise is literal: the file appears on the desktop. |
| Users v1 | Teacher DM + **one shared admin ops channel** (announcements, schedule changes, coverage requests with Claim buttons open to channel members). | Minimal multi-user that still demonstrates the coverage claim pattern. |
| Brain | **Deterministic-first**: keyword/pattern rules + date/period parsing. One-question Block Kit clarification when confidence is low. No LLM in the capture path. | Predictable, testable, offline, local-only governance. |
| Old observation path | Leave dormant, untouched. | Nothing to un-ship mid-crunch. |

## 3. Architecture

```
Slack (ops channel + teacher DMs)
   │ outbound wss (Socket Mode)
   ▼
src/lingua_viva/slack_socket.py      ← transport: connect, envelope loop, ack, reconnect
   ▼
src/education/slack_ops_bot.py       ← conversation: dispatch, workflows, Block Kit, ACKs
   ├─ src/education/ops_classifier.py   ← deterministic category + entity extraction
   ├─ src/education/ops_records.py      ← OperationalRecord store (SQLite) + status machine
   └─ src/education/daily_file.py       ← renders Today-<Teacher>.md + archive + logs
web.py: GET /api/ops/daily, GET /api/ops/records, GET /api/slack/ops/status  ← app Daily view
```

### 3.1 Transport (`slack_socket.py`)

- `POST https://slack.com/api/apps.connections.open` (app token `LV_SLACK_APP_TOKEN`,
  `xapp-…`) → wss URL. Connect with `websockets`.
- Envelope loop: receive `{envelope_id, type, payload}`; **ack within 3s** by sending
  `{"envelope_id": …}` BEFORE processing (processing is queued). Types handled:
  `events_api` (message events), `interactive` (button clicks), `hello`, `disconnect`
  (reconnect with jittered backoff; Slack sends `disconnect` for refresh/rotation).
- Dedup by `envelope_id` + event `client_msg_id`/`ts`, bounded LRU (reuse pattern from
  `slack_bot.py` `_seen_event_ids`).
- Outbound: `chat.postMessage` (with `blocks`), `chat.update` (edit coverage message after
  claim), `conversations.open` (DM channel for briefings) — stdlib `urllib.request`,
  10s timeout, bearer `LV_SLACK_BOT_TOKEN`.
- Fail-closed config: `require_ops_config()` needs `LV_SLACK_BOT_TOKEN` + `LV_SLACK_APP_TOKEN`
  + `LV_SLACK_OPS_CHANNEL` (channel ID) + `LV_SLACK_TEACHER_MAP` (JSON: slack user ID →
  {teacher_id, display_name}). Env-only, never persisted, never logged.
- Runs as an asyncio task inside the existing FastAPI app (started from lifespan/startup when
  configured; `GET /api/slack/ops/status` reports `configured/connected/last_event_at`
  booleans+counts only).

### 3.2 Classifier (`ops_classifier.py`) — deterministic

Input: `{text, user, channel, ts, thread_ts, is_dm}` → `ClassifiedOpsMessage`:

- `category`: `absence | coverage_request | coverage_claim | schedule_change | announcement |
  student_logistics | facilities | reminder | other`
- Extraction: dates ("tomorrow", "today", weekday names, `7/28`, "July 28"), time ranges
  ("9:00-11:30", "2nd and 4th period" → period list), person names (roster of teachers from
  `LV_SLACK_TEACHER_MAP` + free-text capture), subject line.
- `confidence`: `high | low`. Rules produce `high` only when category cue AND required
  entities resolve; otherwise `low` → clarification question.
- Category cues (case-insensitive, order = priority):
  - absence: "I'm out", "I am out", "absent", "sick", "can't come in", "need coverage" *from a teacher about self*
  - coverage_request: "need substitute", "need coverage for", "cover <class/period>", "who can cover"
  - coverage_claim: button click (primary) or "I can cover", "I'll take it"
  - schedule_change: "moved to", "postponed", "cancelled", "rescheduled", "delayed", "schedule change"
  - student_logistics: "early pickup", "late arrival", "absent today" *about a student*, "bus"
  - facilities: "not working", "broken", "need more <supplies>"
  - reminder: "due", "don't forget", "reminder"
  - announcement: admin post in ops channel not matching above
- Pure functions, no I/O, exhaustively unit-tested.

### 3.3 Records (`ops_records.py`)

SQLite at `lv_home()/ops/ops_records.db` (`LV_OPS_DB_PATH` override). Append-oriented table
`ops_records`:

```
id, created_at, updated_at, category, status, teacher_id, actor_slack_id, actor_name,
date_for (ISO date the record applies to), time_window, periods (JSON), text_raw,
text_clean, source_channel, source_ts (permalink anchor), thread_ts,
needs_review (bool), review_reason, claim_by, claim_at, extra (JSON)
```

Status machine (only coverage uses more than `logged`):
`coverage_request: open → claimed → confirmed` (v1: claim ⇒ auto-confirmed) · others: `logged | needs_review → resolved`.
Every mutation appends to the existing privacy/audit log (`privacy_log.py`) with source
permalink — the audit trail of what was imported and why.

### 3.4 Daily file engine (`daily_file.py`)

- Canonical render per teacher per day from `ops_records` (query, not stored state — file is
  always reproducible).
- Output: `~/Desktop/Today - <Display Name>.md` (`LV_OPS_DESKTOP_DIR` override; falls back to
  `lv_home()/ops/daily/` if Desktop unwritable). Sections:
  `## Schedule Changes · ## Student Logistics · ## Coverage · ## Announcements · ## To Review`
  — each line ends with a Slack permalink reference.
- Rewrite-on-change (atomic: temp file + rename) whenever a record affecting that teacher/day
  mutates.
- Daily reset: first event or briefing tick of a new local day archives yesterday to
  `~/Desktop/Daily Updates/YYYY-MM-DD.md` and starts fresh.

### 3.5 Bot conversation (`slack_ops_bot.py`)

- Dispatch: DM messages → teacher self-service (absence, "leave early", questions);
  ops-channel messages → ingest (announcement/schedule/coverage); button payloads → actions.
- **Absence flow**: classify → log record → reply
  "I'll log your absence for <date> and notify coverage. Do you want to attach lesson notes?"
  buttons `Add lesson notes | Use emergency plan | Cancel`. Coverage need → posts a coverage
  request card to the ops channel.
- **Coverage flow**: request card in ops channel with `Claim coverage` button → on claim:
  `chat.update` the card to "Coverage filled: <claimer>, <window>", update record
  (claimed/confirmed), notify requesting teacher by DM, update both daily files.
- **Clarification** (low confidence): exactly ONE question with ≤4 buttons
  (e.g. routing: `Grade 4 team | Front office | Both`; or `Log as announcement | Ignore`).
  Unresolved clarifications land in **To Review**, never dropped.
- **Morning briefing** (DM, per teacher, configurable local time default 07:30):
  "Good morning, <name>. You have N updates today: …" buttons `Open daily file | Remind me later`.
- **End-of-day** (default 16:30): "Your daily file is ready. N items captured. M need review."
  buttons `Open file | Archive today`.
- `Open daily file` deep-links `lv://` if available else replies with the file path.
- Reply discipline (inherited): fixed templates, short, never echo full message content back
  into shared channels, no student detail in channel messages.

### 3.6 Privacy / pull boundary

Pull ONLY: messages from the configured ops channel + DMs to the bot, sender, timestamp,
channel, thread replies that confirm status, attached links on operational messages.
NO channel-history backfill, NO other channels, NO teacher chatter ingestion, NO student
profiles from Slack, NO summaries of sensitive discussions. Bot token scopes minimal:
`chat:write, channels:history, groups:history, im:history, im:write, users:read`.

### 3.7 App surface (Lane E)

- `GET /api/ops/daily?teacher_id=` → rendered markdown + needs_review count.
- `GET /api/ops/records?date=` → structured list (for the Daily view).
- Daily view in `static/index.html` (nav: "Daily") rendering the file + To Review list +
  audit-trail link. UI contract bump (v35) — **additive only**; do not disturb uncommitted
  v34 Drive work.

## 4. Build lanes (2 days)

| Lane | What | Day |
|---|---|---|
| A | `slack_socket.py` transport + config + status route | 1 |
| B | `ops_classifier.py` + tests | 1 |
| C | `ops_records.py` + `daily_file.py` + tests | 1 |
| D | `slack_ops_bot.py` workflows + Block Kit + briefing/EOD scheduler + tests | 2 |
| E | Daily view UI + contract v35 | 2 |
| F | E2E tests (fake socket → record → file → status update), full-suite regression, UX review vs North Star, release checklist + operator commit window, Slack app registration guide | 2 |

## 5. Test plan

- Unit: classifier (every category, date/period parsing, confidence), records store +
  status machine, daily-file rendering + atomic write + archive rotation.
- Integration: fake transport injecting envelopes → bot → records → file; claim button →
  chat.update + DM; duplicate envelope dedup; unconfigured → cleanly off.
- Non-regression: existing 872-test suite stays green; observation Slack path untouched.

## 6. Operator setup (registration guide, Lane F deliverable)

api.slack.com/apps → create app → **enable Socket Mode** (generate `xapp-` app token with
`connections:write`) → bot scopes above → enable Interactivity (Socket Mode delivers it) →
install to workspace → create ops channel, invite bot → set env:
`LV_SLACK_BOT_TOKEN, LV_SLACK_APP_TOKEN, LV_SLACK_OPS_CHANNEL, LV_SLACK_TEACHER_MAP`.
