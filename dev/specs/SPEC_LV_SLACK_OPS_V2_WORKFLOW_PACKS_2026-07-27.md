# SPEC — Slack Ops Assistant v2: Workflow Packs + Setup Interview + Teachable Corrections

Date: 2026-07-27 · Status: **DRAFT v2 — approved direction, unbuilt** (operator ruling
2026-07-27 eve; v2 of this spec incorporates a same-night code audit of the v1 runtime —
see §3 "Architecture reality check")
Builds on: `dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md` (v1, shipped + hardened same day)
Related: `dev/UX_REVIEW_SLACK_OPS_2026-07-27.md`, `dev/reports/REPORT_SLACK_OPS_HARDENING_2026-07-27.md`
Prompt: `dev/EXECUTION_PROMPT_LV_SLACK_OPS_V2_PACKS_2026-07-27.md`

## 0. The problem v2 solves

v1 is one hardcoded bot: 9 categories, fixed briefing times, fixed daily-file
sections, English-only regex rules. It fits Claudia's school. It cannot fit the
next school without code changes — and "we cannot possibly understand all the
different ways they will need to create Slack bots" (operator). v2 makes the
bot's *configurable surface* data, gathered through a short structured
interview and refined through corrections — while the live capture path stays
100% deterministic and the interaction flows stay code (§3).

**Trust line (verbatim, use in all UI/marketing copy):**
> The live bot does not guess with AI. It follows approved school rules.

## 1. Operator ruling — design ranking

1. **Workflow Packs** (primary) — schools pick from a catalog of pre-built
   workflow definitions; never a blank page.
2. **Teachable Bot** — corrections in the To Review queue become candidate
   rules behind an approval ceremony.
3. **Short Workup Interview** — admin setup asks only school-specific details
   the packs can't know.
4. **Shadow Mode** — demoted to a *post-install suggestion engine* ("I found 18
   transport-related updates this week. Add a Bus/Transport section?"), NOT a
   primary onboarding path.
5. **LLM at design time** — optional, privacy-bounded, only ever in
   setup/suggestion tooling. **Never in the live capture path.**
6. **Bot-as-config-UI** — quick choices OK as Slack buttons; durable
   configuration lives in the LV desktop app, not chat.

## 2. Experience standards

### 2.1 Teacher standard

**"The teacher should never experience 'bot setup'."** Lifecycle:

1. Admin installs; teacher gets one DM: *"I can help with absences, coverage,
   schedule changes, and daily updates."* (Shipped into v1 as the
   help/first-contact reply, 2026-07-27.)
2. Teacher types naturally — no commands, no forms.
3. Bot gives a receipt; the daily file updates.
4. When unsure, the bot asks **one** simple question with at most two buttons.

Nothing in v2 may add friction to this path. Configuration is invisible to
teachers.

### 2.2 Admin standard

Setup ≈ 10 minutes, never a blank page:

1. Pick 4–6 packs from the catalog (launch packs pre-checked).
2. Connect channels.
3. Confirm the teacher roster.
4. Choose briefing/EOD times.
5. Test with sample sentences (§7).
6. Go live.

Only *school-specific* questions are asked: channels, briefing time, who may
claim coverage, period naming ("2nd period" vs "P2" vs "Block B"), what the
daily file contains, which categories require review before filing.

## 3. Architecture reality check (v1 code audit, 2026-07-27)

The naive reading of "packs as data" — each pack a YAML file of trigger rules,
routing, and buttons — does not survive the v1 code. Three different kinds of
behavior live in the runtime, and only one of them is honestly data:

**(a) Vocabulary & routing — data.** Category cue regexes
(`ops_classifier.py` `_ABSENCE_RE` … `_REMINDER_RE`), category→section mapping
(`daily_file._CATEGORY_SECTIONS`), broadcast membership
(`ops_records.BROADCAST_CATEGORIES`), review-required flags, sample sentences.
These become pack data.

**(b) Interaction flows — code, forever (in v2).** The absence flow
(receipt + Add-lesson-notes 10-min pending window + emergency plan + cancel),
the coverage state machine (card post → Claim button → chat.update in place →
requester DM → restart-survivable via record id in button value + persisted
card ts), the text-claim single-open heuristic, briefings, the roster
boundary. Making these YAML means building a workflow engine — explicitly out
of scope. A pack may only **enable/disable and parameterize** a code-backed
capability, keyed by a stable `capability` id.

**(c) Shared infrastructure — core, not per-pack.** Entity extraction
(dates/times/periods/names in `ops_classifier.py`), the binary-confidence
policy, clarification/To-Review machinery, daily-file mechanics (atomic
writes, rotation, day marker), the `other` fallback category. Always on;
packs never own or duplicate it. Period-naming aliases (§2.2) are a
*settings-fed extension point* of core period extraction — not pack regex.

### 3.1 Category registry (the real refactor)

v1 has **9 categories** whose names are string literals scattered across four
modules (`ops_classifier` constants, `daily_file._CATEGORY_SECTIONS`,
`ops_records.BROADCAST_CATEGORIES`, `slack_ops_bot` dispatch +
`_flow_capture`'s broadcast tuple). v2 centralizes them in one registry,
populated from compiled pack data. Full accounting — every v1 category must
land somewhere:

| v1 category | v2 home | Notes |
|---|---|---|
| absence | Absence & Coverage pack | capability: absence flow (notes window, emergency, cancel) |
| coverage_request | Absence & Coverage pack | capability: coverage card + claim machine |
| coverage_claim | Absence & Coverage pack | capability: text-claim heuristic |
| schedule_change | Schedule Changes pack | broadcast |
| announcement | Announcements pack | **positional, not lexical** — the ops-channel high-trust default bucket (`ops_classifier.py:350`); pack schema expresses this as `channel_default: true`, not trigger rules |
| reminder | Announcements pack | broadcast; keyword-triggered |
| student_logistics | Student Logistics pack | subject-name confidence rule stays code |
| facilities | Facilities pack (catalog, off by default at new schools; ON in the v1-parity default set since v1 captures it) | capture-only in v2, same as v1 |
| other | **core** — not a pack | fallback + clarification + To Review; cannot be disabled |

**Priority order is load-bearing** (absence beats claim beats request beats
schedule…, earlier wins — `ops_classifier.py:35`). The registry carries an
explicit priority per category; the compiled order with the default pack set
MUST equal v1's order. Hardening fixes that live inside rules (the
"out of paper" vs "out of town" `_OUT` lookahead, pass 11) move into pack data
with their regression tests intact.

**Correction to spec v1 of this document:** "Substitute Notes" is NOT a
category or pack — lesson notes are a sub-flow of the absence capability. The
launch pack list in §5 reflects this.

### 3.2 Compiled bot-spec (single source of truth)

ONE YAML file per school is the compiled configuration: selected packs +
interview answers (channels, times, period aliases, claim-rights,
review-required categories) + approved learned rules + corpus results. The
admin **never hand-edits it** (generated header says so); it is produced by
setup and the teach loop and reviewed read-only in the desktop app.

- Location: `lv_home()/ops/bot_spec.yaml` (env override `LV_OPS_BOT_SPEC_PATH`
  for tests). Shipped packs are read-only repo/bundle data at
  `config/ops_packs/*.yaml`. The app never writes into `LV_ROOT`.
- Loading: `load_compiled_spec()` → immutable `CompiledBotSpec` (category
  registry, compiled rule set, section order, broadcast set, settings)
  consumed by classifier + daily engine + bot. Because v1's rules are
  module-level compiled regex constants, this forces the classifier from
  module functions to an injected rule-set object — that is the Phase 1
  refactor.
- Reload semantics (ruled): **atomic in-process swap** — setup/teach-loop
  routes rebuild the CompiledBotSpec and swap the reference; no file
  watchers, no hot partial reload, no app restart required.
- Fail-closed: malformed/unreadable bot-spec → fall back to the v1-parity
  default compile + health WARN. Never crash the bot, never half-apply.
- Atomic writes (mkstemp+replace), `schema_version` field from day one.
- Secrets stay in env exactly as v1 (`LV_SLACK_*`). The bot-spec never
  contains tokens.

### 3.3 Backward compatibility (Claudia is live)

v1 went live for a real teacher on 2026-07-28. Therefore:

- **No bot-spec file present + env configured ⇒ exact v1 behavior** (the
  v1-parity default compile: 5 launch packs + facilities enabled, 07:30/16:30,
  v1 sections, live immediately). The existing 168 ops tests are the golden
  regression and must pass unmodified wherever possible.
- The go-live gate (§7) applies **only when a bot-spec exists**. Creating one
  must never silently stop a running env-configured bot.
- A pack-parity test proves the default compile's category set, priority
  order, section mapping, broadcast set, and regex behavior equal v1's.

### 3.4 Disabled-pack semantics (ruled)

A message whose only matching category belongs to a disabled pack falls
through to core `other` → one-question clarification / To Review. **Never
dropped, never a dead code path.** Consequences derive from the compile:
daily-file section list, broadcast set, and the classifier priority chain all
come from *enabled* packs only. The "Coverage always renders, even empty"
rule (v1 hardening) applies only while the Absence & Coverage pack is
enabled. Each launch pack gets a disabled-fallback test.

## 4. Teach loop (candidate rules)

- To Review item → admin reclassifies (desktop Review surface; optionally a
  one-question Slack DM with Approve/Ignore buttons — quick choice in Slack,
  durable state in the bot-spec, per ranking #6).
- Reclassification does two things: (1) fixes the *record* — new store API
  `reclassify_record(record_id, category)` (does not exist in v1
  `ops_records`; must be added with audit-log entry, needs_review cleared,
  daily file re-rendered); (2) offers to generalize: *"Treat future messages
  like this as coverage?"* → **candidate rule**.
- Candidate rule = conservative exact-keyphrase (normalized: lowercase,
  collapsed whitespace, the distinctive phrase the admin confirms — not the
  whole sentence). No automatic generalization beyond that.
- **Precedence (ruled):** learned rules OR into their target category's
  vocabulary and are evaluated at that category's *existing* priority slot.
  Learned rules can never reorder category priorities and can never target
  core (`other`).
- Lifecycle: `candidate` → corpus re-test (§7 runner; zero previously-passing
  samples may change routing) → `approved` (compiled in on next atomic swap)
  | `rejected` | expired. Candidates NEVER affect live classification.
  Provenance stored: source record id, admin action, timestamp.

## 5. Workflow Pack catalog

Pack file = capability switches + vocabulary + section mapping + samples +
pack-level settings schema. Launch set (v1 parity) then backlog:

| Pack | Contents | Status |
|---|---|---|
| 1. Absence & Coverage | absence + coverage_request + coverage_claim; capabilities: absence flow, coverage machine, text-claim | launch (v1) |
| 2. Announcements | announcement (`channel_default`) + reminder | launch (v1) |
| 3. Schedule Changes | schedule_change | launch (v1) |
| 4. Student Logistics | student_logistics | launch (v1) |
| 5. Facilities | facilities (capture-only) | launch (v1; off by default for new schools) |
| 6. Bus / Transport | new vocabulary + section | backlog |
| 7. Dismissal Changes | new vocabulary + section | backlog |
| 8. Event Volunteers | new vocabulary + section | backlog |
| 9. Cafeteria Counts | new vocabulary + section | backlog |

Backlog packs are vocabulary/section-only (no new capabilities) — the first
proof that a pack can be added without touching flow code. English-only
vocabulary in v2; packs-as-data is deliberately the future seam for
other-language packs (out of scope now).

## 6. Admin setup (interview)

LV desktop app "Bot Setup" panel (reachable from the Daily view), backed by
JSON routes: catalog get, bot-spec selections/settings get+put, roster
read-only view (roster source of truth stays `LV_SLACK_TEACHER_MAP` env,
unchanged from v1 — no member pull, no CSV, this build). Flow: pick packs
(launch set pre-checked) → confirm channel/roster → choose times → corpus
test (§7) → go live (writes bot-spec, swaps compile). Review-required
categories from the interview become a settings gate applied in the capture
flows: records in those categories land in To Review even at high confidence.
Briefing/EOD times finally get their knob here — `run_schedules` already
accepts `briefing_hhmm`/`eod_hhmm` (`slack_ops_bot.py:703`); web startup just
passes bot-spec values (closes v1 known-limit #2).

## 7. Test-corpus gate

- Each pack ships 3–6 sample sentences with expected routing. **Expectations
  use relative dates** ("date_for: +1d") resolved against an injected
  reference `today` — the classifier already takes `today` as a parameter, so
  corpus runs are deterministic and never rot.
- Corpus runner: feed samples (pack samples + admin-added sentences, stored
  in the bot-spec) through the compiled rule set; per-sentence
  actual-vs-expected table in the setup panel.
- Go-live toggle requires a passing corpus run recorded in the bot-spec
  (timestamp + result hash). A school never goes live on untested rules.
- The same runner is the candidate-rule regression gate (§4).

## 8. Shadow suggester (stretch)

Weekly count of `other`/unmatched ops-channel traffic against *disabled*
packs' vocabularies; ≥N would-have-matched → panel suggestion ("I found 18
transport-related updates this week. Add a Bus/Transport section?").
Suggestion only; admin approves. Builds only if Bus/Transport +
Dismissal Changes backlog packs exist to suggest.

## 9. V2 minimum slice (build order — cleanly stoppable after item 2)

1. **Packs as data** — category registry + `CompiledRuleSet` classifier
   refactor + 5 launch pack files; v1-parity default compile proven by the
   untouched golden suite + parity test. *(The risky refactor.)*
2. **Bot-spec** — load/validate/compile/atomic-swap, fail-closed fallback,
   times knob wired. *(Items 1+2 alone are shippable and valuable.)*
3. **Admin setup panel** — routes + UI, review-required gate.
4. **Teach loop** — `reclassify_record` store API + candidate lifecycle +
   promote ceremony.
5. **Test-corpus gate** — runner + panel table + go-live toggle.
6. **Shadow suggester + backlog packs** — stretch.

## 10. Remaining open questions for operator

1. **Multi-school horizon** — v2 is built single-school (Claudia); if a second
   school is real in the next month, per-school bot-spec management moves up.
2. **Slack half of the teach loop** — build the Approve/Ignore DM in this
   pass, or desktop-only first?
3. **Facilities default** — spec says ON in the v1-parity compile (behavior
   preservation) but off by default for new schools. Confirm.

(Resolved since spec v1, by ruling or audit: pack format/location, setup
surface = desktop panel, candidate generalization = conservative
exact-keyphrase, roster = env map unchanged, reload = atomic in-process swap,
disabled-pack fallback = core `other`, go-live gate scoped to
bot-spec-present installs only.)
