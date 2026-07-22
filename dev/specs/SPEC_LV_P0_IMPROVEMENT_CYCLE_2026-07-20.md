# LV P0 Improvement Cycle — Spec

**Status**: DRAFT — ready for execution by a fresh model/session.
**Author context**: written 2026-07-20, mirroring the improvement-cycle pattern run this same day in the companion Mission Canvas (MC) repo (`mission-canvas/dev/SPEC_P1_IMPROVEMENT_CYCLE_2026-07-20.md`, `SPEC_P2_...`, `SPEC_P3_...`), which itself followed an MC P0 technical-correctness pass and a founder-lens differentiation repass. This spec applies the same method to Lingua Viva's (LV's) own P0 tier.
**Companion prompt**: `dev/EXECUTION_PROMPT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md` — the self-contained kickoff prompt for the executing model.
**Companion input doc**: `dev/LV_HAPPY_STATE_P0_2026-07-20.md` — already-written happy-state scripting for all 9 P0 experiences below. This spec's step 1 (define the happy-state) is **already done** for this tier — treat that doc as the target, not something to redo from scratch.

---

## Why this spec exists

MC ran a fine-toothed-comb improvement cycle across its own experience catalogue this session: for each experience, define what "genuinely excellent" looks like, live-run the actual query, gap-analyze the real response against that target, then fix and wire the gap closed — not just report on it. That pattern is being ported here because LV shares MC's core claim (governed, local-first, trust-legible AI) and deserves the same rigor applied to its own actual interaction surface, not MC's.

The groundwork is already done: `LV_HAPPY_STATE_P0_2026-07-20.md` scripts all 9 P0 experiences — screen-by-screen state, exact copy, response budgets (marked **(enforced)** where real code backs the number, **(proposed, unverified)** where it doesn't), and a "what the teacher must never see" list per experience. That document is honest about two things worth carrying into this pass without re-litigating them (see below). This spec's job is to take that already-defined happy-state and run the rest of the cycle: live-run, gap-analyze, fix, wire in, verify production-ready.

---

## What is already established — do not re-derive or contradict

These are conclusions from `LV_HAPPY_STATE_P0_2026-07-20.md` itself, not open questions:

1. **LV has no voice output.** The only audio-adjacent surface is the browser's native `SpeechRecognition` API used once, for dictating observation text in Observe (`static/index.html`, `startSpeech()`) — on-device STT, no TTS, nothing external. Do not treat this pass as an opportunity to sketch a voice layer; if LV ever gets one, MC's `VOICE_HAPPY_STATE_P0` doc is the pattern to port, not this one.
2. **LV's protection model is architectural exclusion, not runtime interception** — and this is a real, deliberate difference from MC, not a gap to close. MC's hard-block P0s catch sensitive content at an entry gate and refuse to process it (catch-and-refuse). LV's `observation_capture.py` never builds an external-routing code path for `blocks_external` content in the first place — `assert_never_external()` raises if such a path is ever reached, and none currently exists. This is why EXP06 (the Observation Moment) safely echoes the transcript back to the teacher — there's no external-leak risk to guard against on a path that structurally cannot leave the machine. **Do not "fix" this by adding a catch-and-refuse layer to mimic MC** — that would be solving a problem LV's architecture doesn't have, at the cost of removing a UX confirmation the teacher actually needs (seeing what was captured).
3. **Only one response-time budget is actually enforced in code**: the 25s timeout in `query_endpoint` (`src/web.py`), which fires on Prepare's Activity Pack generation (EXP08) with the message "Local reasoning timed out. Check Ollama, then try again." Every other budget in the happy-state doc is marked "(proposed, unverified)" deliberately — these are honest UX targets, not measured or enforced numbers. This pass may choose to formalize one or more of them (add an actual timeout/measurement) as part of closing a gap, but must not present an unverified number as though it were already a spec being met.
4. **A real bug is already found and named, not just implied**: `PRIVATE_RISK` and `WARN` doctor statuses currently render with the same CSS class (`status.data === "OK" ? "ok" : "warn"` in `static/index.html`, per EXP09's "what the teacher must never see" list). This is not a settled trade-off — it's a confirmed, fixable gap explicitly flagged as "worth flagging, not a designed choice." Fix it in this pass; don't treat it as something to merely acknowledge again.

If this pass finds a factual error in the happy-state doc's claims (not a stylistic disagreement — an actual wrong file path, wrong behavior description, or incorrect "enforced" vs. "proposed" label), flag it explicitly and correct it in place, since that doc is meant to stay accurate as a living reference.

---

## What "full improvement cycle" means for this pass

Same 6-step method as MC's P1/P2/P3 cycles, adapted since step 1 is pre-done here:

1. **Happy-state: already written.** Read the relevant section of `LV_HAPPY_STATE_P0_2026-07-20.md` for each experience before touching it. That is your target.
2. **Live-run the current behavior.** Actually exercise each experience for real — start the app (`lv serve` or however the dev entrypoint runs it per `CLAUDE.md`/`README.md`), click through the actual screen sequence, or run the actual CLI command for EXP01/EXP09's terminal path. Read the real response text, real UI state, real copy — not the test suite's assertions about it.
3. **Gap-analyze against the happy-state.** For each row in the happy-state doc's interaction sequence table, does the live behavior match the documented copy, state, and "what the teacher must never see" constraints? Categorize each gap found: (a) correctness bug, (b) wiring gap (the capability exists in the codebase but isn't reachable from this exact path), (c) craft/copy gap (technically correct but the copy doesn't land the trust claim the way the happy-state doc intends), (d) scope gap (genuinely missing, out of scope to build here — see boundary below).
4. **Fix it.** This pass ships real code changes for (a), (b), (c) gaps. Prefer the smallest fix that closes the gap.
5. **Wire it into the app and verify production-ready.** Reachable through the real UI/CLI path a teacher would actually hit — not just a passing unit test that calls an internal function directly. Relevant test(s) pass, `lv health` (or `lv health --full` where warranted) stays clean, and you have live-verified the actual screen/response post-fix.
6. **Document the delta.** Update `LV_HAPPY_STATE_P0_2026-07-20.md` itself if the fix changes what's true (e.g., a budget that moves from "(proposed, unverified)" to "(enforced)" because you added real instrumentation, or the EXP09 CSS-class note once fixed).

### Scope boundary — what NOT to build

Consistent with MC's cycles and with LV's own deferred/spec-only inventory (per the operator's framing: coordinator Evidence/Capacity/Trends, Slack bot voice notes, skill morphing, TTS are all explicitly deferred):

- No new voice/TTS surface (see "already established" #1).
- No new coordinator-facing features (Evidence, Capacity, Trends remain `deferred` status — out of scope).
- No new education-pipeline modules from scratch. Wiring an existing module more tightly into a P0 path is in scope; building a module that doesn't exist yet is not.
- Don't touch the architectural-exclusion protection model to make it resemble MC's catch-and-refuse pattern (see "already established" #2).
- Respect `CLAUDE.md`'s governance rules throughout: no real student PII in any test fixture, commit, or captured example used to verify a fix; no institution names; every claim in the happy-state doc or this report must stay evidence-based, not aspirational.

The test for in-scope-to-fix vs. backlog: does the capability already exist somewhere in the codebase (the classification, the endpoint, the UI element, the copy), just wrong, disconnected, or under-verified on this exact P0 path? If yes, fix it. If no — it requires a module, view, or surface that doesn't exist at all — name it as a backlog item instead.

---

## The 9 P0 experiences

Full detail lives in `dev/LV_HAPPY_STATE_P0_2026-07-20.md` — read it in full before starting. Summary:

| Code | Experience | Entry point | Key trust moment | Known gap to fix in this pass |
|---|---|---|---|---|
| EXP01 | Install | `curl \| sh` / `install.ps1`, no UI | Terminal-only, no screen | None named — verify install still completes cleanly on this machine |
| EXP02 | First-Run Setup | First page load | Role modal blocks paint; local-first by default, no key required to start | None named — verify the modal truly blocks and provider-connect test-call-before-save still holds |
| EXP03 | "Why did you answer that way?" (Why view) | Why nav / "Why?" button | Query hash persisted, never raw text (`event_hash()` SHA-256) | None named — verify no raw query text reaches disk via this path |
| EXP04 | "What left this machine?" (Privacy view) | Privacy nav | "all local" badge backed by architecture, `external calls: 0` | None named — verify the 0-count claim is real, not cosmetic |
| EXP05 | "What do you know about me?" (Profile view) | Profile nav | Full local-only summary + export + irreversible typed-confirmation clear | None named — verify export completeness and the clear confirmation gate |
| EXP06 | The Observation Moment | Observe → mic or type → save | Transcript echoed back safely (architectural exclusion, not catch-and-refuse — see "already established" #2) | None named — verify `assert_never_external()` still holds, zero outbound network calls during save |
| EXP07 | The Parent Message Moment | Parents → generate | Name-strip + AI-attribution-strip before the teacher sees the draft | None named — verify `_strip_parent_output()` actually catches all the attribution phrasings it claims to |
| EXP08 | The Activity Pack Moment | Prepare → generate | 25s hard timeout (the only enforced budget), friendly timeout copy, request/response not streamed | None named — verify the timeout actually fires and the copy is exactly as documented |
| EXP09 | Health / Doctor Check | Health nav / `lv health` / `lv doctor` | Doctor's own first-person plain-language status copy | **Named bug: `PRIVATE_RISK` and `WARN` render with the same CSS class — fix this** |

Note the asymmetry with MC's tiers: only EXP09 has a *named* bug going in. The other 8 have no confirmed gap yet — the happy-state doc's claims may hold exactly as written. Don't manufacture a fix where live-running confirms the documented behavior is correct; "verified, no gap found" is a legitimate, useful outcome for most of these 9 rows. The value of this pass for those 8 is confirmation with fresh eyes and current code, not assumed brokenness.

---

## Method

1. Read `CLAUDE.md` (repo root) for orientation — LV's governance rules, repo layout, privacy-first constraints. This is LV's equivalent of MC's `AGENTS.md`.
2. Read `dev/LV_HAPPY_STATE_P0_2026-07-20.md` in full — the happy-state target for all 9 experiences.
3. Skim `dev/HANDOFF_LINGUA_VIVA_2026-07-20.md` and `dev/INDEX.md` for current spec/build status and anything already in flight that might overlap.
4. For each of the 9 P0 rows, in the order given in the happy-state doc (EXP01 → EXP09), run the full cycle: live-run for real (start the app with `lv serve` or the documented dev entrypoint, walk the actual screen sequence in a browser, or run the actual `lv health`/`lv doctor` CLI commands for EXP09's terminal path), gap-analyze against the happy-state doc's interaction table and "what the teacher must never see" list, fix any real gap found, wire it into the actual app path, verify.
5. EXP09 first, since it has a named, confirmed bug — fix the CSS-class issue (likely a small `static/index.html` change distinguishing `PRIVATE_RISK` from `WARN` with its own class/styling) and verify Doctor's actual status output still renders correctly for all its documented states.
6. Run the relevant test suite (`pytest -q tests/`) and `lv health` after each row's fix (or a small batch of adjacent rows) — never let the suite go red across a batch boundary.
7. Where a row is confirmed correct with no gap, say so explicitly with the live-verification evidence (what you actually did, what you actually saw) — don't just cite the happy-state doc back at itself.

---

## Deliverable

A new report doc, `dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md` (this repo's live convention — reports live in `dev/reports/`, per `REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md`), containing:

- A 9-row table: Code | live-run evidence | gap found (or "none, confirmed as documented") | gap category (correctness/wiring/craft/scope) | fix shipped (or "backlog: <reason>") | verification evidence (test + live-run confirmation).
- Explicit confirmation the EXP09 CSS-class bug is fixed, with before/after description.
- Any corrections made to `LV_HAPPY_STATE_P0_2026-07-20.md` itself, called out separately (factual errors found, budgets newly formalized from "(proposed, unverified)" to "(enforced)", etc.).
- Final `pytest -q tests/` and `lv health` (or `lv health --full`) result after all fixes land.
- A same-day status line added to `dev/INDEX.md`'s spec table, per this repo's convention (see existing rows for format — link to this spec, date, status, evidence).

This pass is expected to ship real code changes where gaps are found, but given only one gap is named going in, most of the report's value is likely to be rigorous live-verification, not a large diff. Commit discipline: commit in small batches with messages naming which experience(s) changed and why. Respect `CLAUDE.md`'s commit convention (`<type>(<scope>): <description>`) and never commit anything containing real student names or institution names, even incidentally in a test fixture or screenshot description.
