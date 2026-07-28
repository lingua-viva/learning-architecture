# Slack Daily Operations Assistant — 15-Pass Hardening Loop (2026-07-27)

Scope: the full ops-assistant surface built earlier today —
`src/lingua_viva/slack_socket.py`, `src/education/ops_classifier.py`,
`src/education/ops_records.py`, `src/education/daily_file.py`,
`src/education/slack_ops_bot.py`, the three `src/web.py` ops routes, and the
Daily view. Spec: `dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md`.
UX baseline: `dev/UX_REVIEW_SLACK_OPS_2026-07-27.md`.

Method: 15 adversarial passes, one angle each. Real findings fixed with a
regression test in the same pass; clean passes recorded as verified.
House pattern per `dev/reports/REPORT_LV_SLACK_15_PASS_HARDENING_2026-07-22.md`.

## Verdict

**8 real defects fixed** (2 of them silent-data-loss class), **7 passes
verified clean**. Ops suites 164/164; UI contract re-sealed at v42.

## Pass-by-pass

| # | Angle | Result |
|---|---|---|
| 1 | Injection via untrusted event fields | **FIXED** — `daily_file._COMMENT_SAFE` charset gate on the trailing HTML source-anchor comment: an event-supplied channel/ts containing `>` could terminate the comment early and inject visible content into the Desktop file. Unsafe refs now drop the anchor entirely. Also verified hostile message text cannot inject headings (whitespace collapse keeps it on its bullet line). |
| 2 | Secrets hygiene | Clean — tokens repr-redacted, log lines carry exception type names only, status/daily/records routes asserted secret-free in tests. |
| 3 | Transport resilience | Clean — ack-before-dispatch, bounded dedup (`MAX_SEEN_KEYS` deque trim), capped jittered backoff, handler exceptions confined to the dispatch worker. Note: dispatch queue is unbounded — acceptable at school scale. |
| 4 | Concurrency | Clean — envelopes dispatched serially by one worker; web read-routes open per-request stores inside their `to_thread` closure (created/used/closed on one thread); file writes atomic (`mkstemp` + `os.replace`). |
| 5 | Time/date correctness | **FIXED (data-loss class)** — `refresh_for_record` rendered `record.date_for`, so "I'm out tomorrow" overwrote today's Desktop file with tomorrow's (mostly empty) render AND advanced the day marker past today, silently killing the next morning's rotation. The Today-file now always renders the bot's (injectable) today; future records surface on their own day via the rotation re-render (pass 13). |
| 6 | Status-machine edges | **FIXED** — `Ignore` on a flagged coverage request that a colleague confirmed mid-review hit the illegal `confirmed→resolved` transition (ValueError swallowed by the worker; teacher got silence). Now falls back to clearing the review flag. Stale/unknown record ids on `Log it` / `Ignore` / `Use emergency plan` also degrade gracefully instead of raising. |
| 7 | Rendering edges | Clean — empty text falls back to "(no detail)", bad `source_ts` falls back to `created_at` then `--:--`, whitespace collapsed, filenames sanitized (no hidden files, never empty). |
| 8 | Teacher-map consistency | **FIXED** — an unmapped Slack user was given a fabricated identity (teacher_id = display_name = raw Slack id), which created junk `Today - U0XXX.md` files on the operator's Desktop. Now: unmapped **DM** senders get an honest "ask your admin to add you" reply and no record; unmapped **ops-channel** senders are capture-only (broadcasts behave normally; per-teacher categories stored unattributed — visible in the web records audit, never fabricated into a daily file). |
| 9 | Web-route hardening | Clean — malformed/hostile query params (nonsense dates, script tags) return 200-empty, never 500. Regression test added. |
| 10 | Lifecycle | **FIXED** — one Slack failure inside `send_all_briefings` killed the `run_schedules` task forever (no briefings until restart, no signal). The loop now logs and survives; `fired` is marked before sending so there is no hot-retry. `_shutdown_slack_ops` also awaits the cancelled scheduler task (contract v42). |
| 11 | Classifier adversarial | **FIXED** — "I'm out of paper for the copier" classified as a teacher absence. `_ABSENCE_RE` now excludes "out of <thing>" while keeping "out of town / out of (the) office / out of school / out of the building" as absences. |
| 12 | Button abuse/replay | **FIXED** — an unmapped user tapping `Claim coverage` would have written a raw Slack id as the claimer into the card and the requester's daily file. Claims now require roster membership (honest threaded reply otherwise). Double-claim, replayed ids, and junk values were already covered. Note: repeated `Remind me later` taps each schedule a resend — bounded nuisance, left as-is. |
| 13 | Idempotency / day rollover | **FIXED** — rotation archived yesterday's files but left the Desktop empty until the day's first event: records logged in advance for today stayed invisible and the morning briefing's "Open daily file" could point at a missing file. `archive_if_new_day` now re-renders every mapped teacher's Today-file after rotating. Idempotency preserved (marker check unchanged). |
| 14 | Privacy re-verify | **FIXED (boundary tightened)** — group DMs (`mpim`) were treated as private DMs; receipts and absence detail would have been visible to every member. Now strictly 1:1 (`im` / D-channels). Re-verified: other channels ignored, audit log identifiers-only, no student-lens imports anywhere in ops modules. |
| 15 | Docs + final seal | This report; UI contract bumped v41→v42 (web.py shutdown await; v41's concurrent-lane lock had silently sealed the in-flight edit); full suite run below. |

## Known limits (unchanged from UX review, plus one new note)

1. Offline = missed messages (Socket Mode; documented in setup guide).
2. Briefing/EOD times are injectable defaults, no env knob.
3. Claim auto-confirms (status machine already supports claimed→confirmed).
4. Name matching is a first-name heuristic — fine at Claudia-scale.
5. `/api/ops/records` is backend-only (audit surface).
6. **New:** event dedup is in-memory — a bot restart can re-process events
   Slack redelivers, creating duplicate records for the same message.
   Low-frequency at school scale; roadmap alongside the relay/queue item.

## Test evidence

- Ops suites (`test_slack_socket`, `test_ops_classifier`, `test_ops_records`,
  `test_daily_file`, `test_slack_ops_bot`, `test_ops_app_integration`):
  **164 passed** (150 pre-loop across lanes A–E; net +14 adversarial
  regression tests, with a few existing tests rewritten to pin the
  corrected semantics).
- Full repo suite: see final run at the bottom of the working session
  (operator commit window — everything remains uncommitted).
