# UX Review — Slack Daily Operations Assistant vs. North Star (2026-07-27)

Spec: `dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md` · Setup: `dev/SLACK_OPS_SETUP_GUIDE.md`
Method: walk the North Star's "perfect day" flow message-by-message against the built behavior.

## The perfect day, as built

| North Star moment | Built behavior | Verdict |
|---|---|---|
| **07:30 morning briefing DM** | Wall-clock poller fires once/day; "Good morning, Ana. You have 2 updates today: …" + `Open daily file` / `Remind me later` (later = +1h resend). No updates → honest "No updates for today yet." | ✅ |
| **Daily file on the Desktop** | `Today - <Name>.md`, atomic writes, sections Schedule Changes / Student Logistics / Coverage / Announcements / To Review. Coverage ALWAYS renders (empty = "No coverage assigned to you today.") so absence of info is never ambiguous. Each line ends "(Slack HH:MM)". | ✅ |
| **Teacher DMs "I'm out tomorrow. Need coverage for 2nd period."** | Absence logged for the right date; coverage card posted to ops channel; DM receipt with `Add lesson notes` / `Use emergency plan` / `Cancel`. One message in, everything routed. | ✅ |
| **Lesson notes** | Button opens a 10-minute window; the teacher's next DM is attached verbatim to the absence record and the file refreshes. Window expiry falls back to normal classification — nothing is lost. | ✅ |
| **Colleague taps `Claim coverage`** | Card rewrites in place to "Coverage filled: Ben Ali, period 2." — no channel clutter, no stale card. Requester gets a DM. Claiming survives bot restarts (record id in the button, card ts persisted). Double-tap → threaded "already covered." | ✅ |
| **Text claim ("I'll cover it")** | Works when exactly one request is open; otherwise asks to use the button so the *right* request is updated. Honest about ambiguity instead of guessing. | ✅ |
| **Admin posts announcement / schedule change in ops channel** | Captured silently — the daily file is the acknowledgement (restrained voice §3.5). Broadcasts to every teacher's file. | ✅ |
| **Unclear message** | One question, at most two buttons (`Log it` / `Ignore`). Unresolved items land in To Review — never dropped, never silently guessed. | ✅ |
| **16:30 end-of-day summary** | "Your daily file is ready. 4 items captured today. 1 still needs review." + `Open file` / `Archive today`. | ✅ |
| **New day** | First event of the day rotates yesterday's files into `Daily Updates/<date> - <Name>.md`. Idempotent. | ✅ |
| **In-app mirror** | New "Daily" view renders the same markdown from the same records, with a plain-language connection checklist and privacy-boundary panel. | ✅ |

## Voice check (restrained, conversational)

- Fixed short templates everywhere; the bot never echoes a teacher's message text back into a shared channel.
- Ops-channel speech is limited to: coverage cards, claim confirmations, one-question clarifications (threaded).
- DMs always give a receipt ("Saved to your daily file.") — a teacher talking to the bot deserves an answer.
- No student detail ever appears in bot-authored channel messages (cards carry teacher name + window only).

## Privacy boundary (§3.6) — verified in tests

- Only the configured ops channel + DMs are read; all other channels ignored (`test_other_channels_are_ignored`).
- No student-lens import exists anywhere in the ops modules (separate store, separate bot).
- Audit log receives identifiers only, never message text.
- Status/daily/records routes are secret-free (token strings asserted absent in responses).

## Known v1 limits (deliberate, documented)

1. **Offline = missed messages.** Socket Mode needs LV running; Slack drops events after brief retries. Documented in the setup guide; roadmap: relay/queue.
2. **Briefing times are defaults** (07:30 / 16:30) — injectable in code, no env knob yet.
3. **Claim auto-confirms.** v1 has no "requester approves the claimer" step; the status machine already supports claimed→confirmed if that's ever wanted.
4. **Name matching is first-name heuristic** ("Need a sub for Ana") against the teacher map; ambiguity falls back to the sender's own identity. Fine at Claudia-scale, revisit for larger staff.
5. **`/api/ops/records` is backend-only** (audit via curl/tests); the teacher surface is the Daily view + Desktop file.

## Verdict

The build matches the redefined North Star: the product is the file, the bot is quiet, every unclear thing lands in To Review, and nothing from Slack ever touches a student record.

## Post-review hardening

A 15-pass adversarial loop ran the same evening — 8 defects fixed (future-dated
absence clobbering today's file + rotation marker, day-rollover leaving no fresh
file, unmapped-user junk Desktop files, "I'm out of paper" false absences,
scheduler death on one Slack failure, mpim treated as private DM, comment-anchor
injection, status-machine ValueErrors on stale buttons). Details:
`dev/reports/REPORT_SLACK_OPS_HARDENING_2026-07-27.md`.

## Post-review first-contact fix (operator ruling, same evening)

Teacher-experience step 2 from the v2 design ruling was pulled into v1 before
Monday go-live: a DM greeting or "help" now gets *"Hi <Name> — I can help with
absences, coverage, schedule changes, and daily updates…"* instead of the
classifier's "Should I log this as an announcement?" non-answer; a voice-clip
or file-only DM gets an honest "I can't listen to voice clips yet — type it as
a message" (silently ignored in the ops channel — no junk review items).
Ops suites 168/168. The rest of the ruling is specced for v2:
`dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md`.
