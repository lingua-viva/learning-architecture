# EXECUTION PROMPT — Slack Ops v2: Build SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27 (spec v2)

Copy everything below the line into a fresh agent window in `~/learning-architecture`.

**Operator: spec §10 has 3 remaining open questions (multi-school horizon,
Slack half of the teach loop, facilities default). The agent proceeds with the
spec's stated defaults unless you edit this prompt to say otherwise.**

---

You are building `dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md`
(**spec v2** — it was rewritten after a code audit of the v1 runtime; if the
spec you find contradicts this prompt, the spec wins). Read FIRST, in full,
in this order:

1. `dev/specs/SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md` — what you're
   building. §3 ("Architecture reality check") is the heart: it already did
   the audit of what is data vs code vs core. Do not re-litigate it.
2. `dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md` — the v1 you're
   refactoring.
3. `dev/reports/REPORT_SLACK_OPS_HARDENING_2026-07-27.md` — 8 hardening fixes
   you must not regress; several live inside the rules you are moving to data.
4. `dev/UX_REVIEW_SLACK_OPS_2026-07-27.md` — the behavior contract.
5. The runtime, closely: `src/education/ops_classifier.py` (9 categories,
   priority order at the dispatch chain, module-level compiled regexes —
   the thing you are refactoring), `ops_records.py` (BROADCAST_CATEGORIES,
   status machines), `daily_file.py` (`_CATEGORY_SECTIONS`, SECTION_ORDER,
   rotation), `slack_ops_bot.py` (flows, `run_schedules` — note
   `briefing_hhmm`/`eod_hhmm` already injectable), `src/web.py`
   `_startup_slack_ops`/`_shutdown_slack_ops`.

## Context you need

- v1 is LIVE for a real teacher (Claudia) since Mon 2026-07-28. Spec §3.3 is
  law: **no bot-spec file + env configured ⇒ exact v1 behavior**, and the
  go-live gate applies only when a bot-spec exists. The 168-test ops suite is
  your golden regression — it must pass **unmodified** wherever possible; any
  test you must touch, justify line-by-line in the report.
- **Flows stay code** (spec §3(b)). You are NOT building a workflow engine.
  Packs enable/parameterize code-backed capabilities and contribute
  vocabulary/sections/samples. If you find yourself designing YAML that
  describes buttons, state transitions, or message sequences — stop, re-read
  spec §3.
- Trust line (verbatim in any UI copy): *"The live bot does not guess with
  AI. It follows approved school rules."*
- Teacher standard: **"The teacher should never experience 'bot setup'."**
  Zero new friction on the teacher DM path.

## Hard rules (violating any of these is a failed build)

1. **NEVER commit or push.** Operator holds the single commit window. No
   `git stash`, no `git checkout --`, no reverting anything you didn't write.
   Run `git status` at start — the tree carries uncommitted work from parallel
   lanes (Slack ops v1+hardening, Drive, one-button-update, Sources, ethos).
   Touch none of it; your diff must be hunk-isolatable.
2. **NO LLM anywhere.** Live capture stays 100% deterministic; even
   design-time LLM assist is a separate future lane.
3. **Slack never touches student lenses.** Ops store stays separate; no
   imports from lens/observation modules into ops modules.
4. **Privacy per `CLAUDE.md`**: no student data, no institution names, audit
   log gets identifiers only, tokens never on disk/logs/UI. The bot-spec file
   must never contain secrets (spec §3.2) — assert it in a test.
5. **App never writes into `LV_ROOT`.** Bot-spec and all mutable state under
   `lv_home()` (`src/lingua_viva/config.py`) or existing `LV_OPS_*` seams;
   add `LV_OPS_BOT_SPEC_PATH` for hermetic tests. Shipped packs at
   `config/ops_packs/*.yaml` are read-only data.
6. **UI contract ceremony** for `static/index.html` / `static/sw.js` /
   `src/web.py`: `python3 scripts/check_ui_contract.py --bump`, bump-log line
   BEFORE `version:`, sync `EXPECTED_VERSION` in `tests/test_ui_contract.py`.
   Contract was **≥v44** on 2026-07-27 and concurrent lanes move it — check
   current first; note any pin-sync race in your bump-log line (house
   convention: last sealer syncs pins).
7. **Route-reachability gate**: every new `src/web.py` route needs a verified
   UI call site or a classified entry in `contracts/ROUTE_REACHABILITY.yaml`.
8. **Roster boundary stands** (v1 hardening pass 8/12): unmapped users get the
   honest decline / capture-only treatment; setup and teach loop must not
   create any path that fabricates teacher identities. Roster source of truth
   stays `LV_SLACK_TEACHER_MAP` env — setup panel shows it read-only.
9. **YAML loading is `yaml.safe_load` with size caps.** This repo already ate
   a YAML alias-bomb startup hang in another lane (one-button-update
   hardening). Cap pack + bot-spec file sizes, fail-closed on malformed input
   per spec §3.2.

## Build order

Phases 1+2 are the risky refactor and are **independently shippable** (spec
§9). If quality would suffer, stop cleanly after Phase 2 with everything
green rather than delivering a half-built Phase 3+ — state the boundary in
the report. Stop-points between phases; verify each before the next.

### Phase 1 — Category registry + packs as data (the load-bearing refactor)
- New module (suggested `src/education/ops_packs.py`): pack loader + category
  registry + `CompiledRuleSet`. Registry entry: category id, priority,
  section, broadcast flag, review-required default, capability id (or none),
  `channel_default` flag (announcement is positional, NOT keyword-triggered —
  spec §3.1 table).
- Write the 5 launch pack files per spec §5: `absence_coverage.yaml`,
  `announcements.yaml`, `schedule_changes.yaml`, `student_logistics.yaml`,
  `facilities.yaml`. Pack schema documented in a commented header in each
  file. **There is no substitute-notes pack** — lesson notes are part of the
  absence capability.
- Refactor `ops_classifier.py` from module-level regex constants + module
  function to classification against an injected `CompiledRuleSet` (keep a
  default-compiled module-level instance so v1 call sites and tests work
  unchanged). Entity extraction (dates/times/periods/names) stays core —
  packs never duplicate it. The `_OUT` lookahead ("out of paper" ≠ absence)
  moves into the absence pack's vocabulary with its regression tests intact.
- Replace the scattered category literals: `daily_file._CATEGORY_SECTIONS`
  and `SECTION_ORDER` derive from the registry; `ops_records`
  `BROADCAST_CATEGORIES` and `slack_ops_bot._flow_capture`'s broadcast tuple
  read from it; bot dispatch keys on capability ids.
- **Parity proof**: 168 ops tests green untouched, PLUS a new test asserting
  the default compile's category set, priority order, section mapping, and
  broadcast set equal v1's hardcoded values exactly.
- **Disabled-pack tests** (spec §3.4): with absence_coverage disabled,
  "I'm out tomorrow" → core `other` → To Review (never dropped); section
  list shrinks; Coverage always-renders rule off. One such test per launch
  pack.

### Phase 2 — Bot-spec (compile + swap)
- `src/education/ops_bot_spec.py`: `load_compiled_spec()` → immutable
  `CompiledBotSpec` (registry + rule set + settings: channels, times, period
  aliases, claim rights, review-required categories, approved learned rules,
  corpus results). Atomic writes, `schema_version`, generated
  do-not-hand-edit header, fail-closed to v1-parity compile + health WARN on
  malformed spec.
- **Atomic in-process swap** (spec §3.2 ruling): setup/teach routes rebuild
  and swap one reference; no file watchers. Design the seam so
  classifier/daily/bot read through the current compile.
- Wire times: `_startup_slack_ops` passes bot-spec
  `briefing_hhmm`/`eod_hhmm` into `run_schedules` (params already exist —
  this is a one-line wire plus tests). Closes v1 known-limit #2.
- Period-naming aliases: settings feed extra alias patterns into core period
  extraction (`extract_periods`) — "P2", "Block B" per spec §2.2/§3(c).
- Compat tests: env-only + no bot-spec = v1 behavior byte-for-byte on a
  rendered daily file; bot-spec present + `live: false` = bot does not start;
  creating a bot-spec never stops an env-configured running bot.

### Phase 3 — Admin setup panel
- JSON routes: catalog get, bot-spec get/put (selections + settings), roster
  read-only. Panel flow per spec §6: pick packs (launch set pre-checked) →
  channel/roster confirm → times → corpus test (Phase 5's runner — build the
  runner before the panel's test step if you reorder) → go live. Never a
  blank page.
- Review-required gate: settings-listed categories land in To Review even at
  high confidence — applied in the capture flows, tested.
- Respect rules 6+7. Setup routes secret-free (assert no `xoxb`/`xapp`
  substrings in any response).

### Phase 4 — Teach loop
- New store API `ops_records.reclassify_record(record_id, category)` —
  audit-log entry (identifiers only), needs_review cleared, daily file
  re-rendered. Guard the coverage status machine: reclassifying INTO
  coverage_request creates a proper open record state; reclassifying OUT of
  an open coverage request resolves its card gracefully (reuse the stale-
  button degradation patterns from hardening pass 6).
- Candidate rules per spec §4: conservative exact-keyphrase, provenance,
  lifecycle candidate → corpus re-test → approved/rejected/expired.
  **Precedence**: learned rules OR into their category's vocabulary at that
  category's existing priority slot; never reorder priorities; never target
  `other`. Candidates never affect live classification — test it.
- Desktop-only surface for reclassify/approve in this build; the Slack
  Approve/Ignore DM is spec §10 open question 2 — skip unless the operator
  edited this prompt to include it.

### Phase 5 — Test-corpus gate
- Pack samples with **relative-date expectations** ("+1d", "+0d", weekday
  offsets) resolved against an injected reference `today` (spec §7) — no
  absolute dates that rot.
- Runner over the compiled rule set; actual-vs-expected table via route +
  panel section; admin sentences stored in bot-spec; go-live requires a
  passing run recorded (timestamp + result hash). Same runner gates
  candidates (Phase 4).

### Phase 6 — STRETCH: shadow suggester + backlog packs
- Only if Phases 1–5 are fully green: add `bus_transport.yaml` +
  `dismissal_changes.yaml` (vocabulary/section-only — the proof a pack needs
  no flow code) and the weekly would-have-matched counter + panel suggestion
  (spec §8). Skip cleanly if the bar isn't met; do not stub.

## Verification bar (all of it, before you write the report)

- Full suite green, zero regressions (baseline 2026-07-27: 1121 passed / 13
  skipped full-suite; 168 ops-suite — concurrent lanes move these, check and
  record current numbers first).
- Parity + disabled-pack + compat tests from Phases 1–2 all present.
- Hermetic tests for: bot-spec load/compile/fallback/malformed-fail-closed/
  size-cap, atomic swap under a concurrent request, candidate lifecycle,
  reclassify_record (incl. coverage-machine edges), corpus runner
  pass/fail/relative dates, times knob moves the scheduler, secret-free
  routes, no-secrets-in-bot-spec.
- `lv preflight` passes; UI contract sealed at your version, pins synced.
- Live manual proof: start served app env-only (v1 behavior, bot on) →
  create bot-spec via the panel (pick packs, run corpus, go live) → DM an
  absence → daily file renders → change briefing time via panel → show the
  scheduler picked it up. Paste the transcript in the report.

## Deliverables

1. Code + tests + pack files, **uncommitted**.
2. `dev/reports/REPORT_SLACK_OPS_V2_PACKS_2026-07-27.md` — per-phase record,
   pack schema documentation, any touched golden tests justified
   line-by-line, test counts before/after, live-proof transcript, deferred
   items with reasons, "Found, not fixed" list for adjacent pre-existing
   bugs (this repo's audits usually find some — fix nothing out of scope).
3. `dev/INDEX.md`: update the SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS row
   (DRAFT → BUILT (uncommitted) or PARTIAL with the exact phase boundary —
   "through Phase 2" is a legitimate, valuable outcome). Statuses live ONLY
   in INDEX.
4. Append a short "v2 built" note to `dev/UX_REVIEW_SLACK_OPS_2026-07-27.md`
   only if teacher-visible behavior changed (by design it must NOT — say so).

## What is explicitly OUT of scope

- Any workflow engine / flows-in-YAML (spec §3(b) — capabilities stay code).
- LLM anywhere, including design-time assist.
- Slack-thread admin setup; roster import (CSV/member-pull); multi-school
  packaging; non-English vocabulary packs.
- Offline relay/queue for Socket Mode (v1 limit #1); restart-durable event
  dedup (v1 limit #6).
- Mission Canvas (`~/fde/mission-canvas`) — LV validates first.
- Releases/tags — operator cuts them.
