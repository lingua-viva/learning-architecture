# Prompt: LV P0 Improvement Cycle

Copy everything below the line into a fresh session with a different model. It is self-contained — the executing model has no memory of the session that produced it.

---

You are working in the Learning Architecture / Lingua Viva repo (`learning-architecture`). Start by reading `CLAUDE.md` at the repo root for orientation on the repo layout, governance rules, and privacy-first constraints — you are operating under that protocol for this task.

Then read `dev/specs/SPEC_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md` in full. That spec is your task definition — it explains why this pass exists, what's already established (do not re-derive or contradict it), the full improvement cycle method, the 9 P0 experiences, and the deliverable format. Follow it as written.

**One-sentence summary of the ask**: this repo's own P0 happy-state doc (`dev/LV_HAPPY_STATE_P0_2026-07-20.md`) already scripts what all 9 P0 experiences should look/feel like when working correctly — your job is to live-run each one for real, confirm the actual app behavior matches that documented happy-state (or find and fix the gap where it doesn't), and ship any needed fix wired into the real app path, verified production-ready.

Before you touch anything, read `dev/LV_HAPPY_STATE_P0_2026-07-20.md` in full — it is the target, already written, not something you need to redraft. Also skim `dev/HANDOFF_LINGUA_VIVA_2026-07-20.md` and `dev/INDEX.md` for current build status and anything already in flight.

**Hard constraints**:
- LV has no voice output and none should be added — the only audio-adjacent surface is browser-native STT dictation in Observe. Don't sketch a voice/TTS layer as part of this pass.
- LV's protection model (architectural exclusion — `observation_capture.py`'s `assert_never_external()`, no external-routing path exists for sensitive content at all) is a deliberate, different-from-MC design, not a gap. Do not add a catch-and-refuse layer to make it resemble MC's pattern — that would remove a UX confirmation the teacher needs (seeing what was captured) to solve a problem LV's architecture doesn't have.
- Only the 25s timeout in `query_endpoint` (`src/web.py`, fires on EXP08's Activity Pack generation) is an actually-enforced response budget. Every other timing figure in the happy-state doc is marked "(proposed, unverified)" deliberately — don't present one as met unless you've actually added real enforcement/measurement for it.
- **One bug is already named and confirmed**: EXP09's Health/Doctor view renders `PRIVATE_RISK` and `WARN` statuses with the same CSS class in `static/index.html` (`status.data === "OK" ? "ok" : "warn"`) — a privacy stop should read as more urgent than a routine warning. Fix this.
- Do not build: new coordinator-facing features (Evidence/Capacity/Trends stay `deferred`), new education-pipeline modules from scratch, Slack bot voice notes, skill morphing, TTS. Wiring an existing module more tightly into a P0 path is in scope; building something that doesn't exist at all is not — name it as backlog instead.
- Respect `CLAUDE.md`'s privacy-first rules throughout: no real student PII, no institution names, no colleague names in anything you commit, including test fixtures or examples used to verify a fix.
- Run `pytest -q tests/` and `lv health` after each fix (or small batch) — never let unverified changes accumulate.
- Commit in small batches, following `CLAUDE.md`'s commit convention (`<type>(<scope>): <description>`), with messages naming which experience(s) changed and why.

**Important expectation-setting**: only EXP09 has a confirmed bug going in. The other 8 experiences (EXP01-EXP08) may turn out to already match their documented happy-state exactly — "verified correct, no gap found" is a legitimate and useful outcome for most of these, not a failure to find something. Don't manufacture fixes where none are needed; the value for those 8 rows is rigorous live-verification with fresh eyes on current code, not assumed brokenness.

**Deliverable**: `dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md` (this repo's live report convention), with the 9-row table (live-run evidence / gap found or confirmed-correct / category / fix or backlog / verification), explicit confirmation of the EXP09 fix, any corrections made to the happy-state doc itself, final test/health results, and a `dev/INDEX.md` status line — exact format is in the spec's "Deliverable" section.

Work through all 9 P0 rows before writing the final report, starting with EXP09 since it has the named bug. When done, give a short summary (under 200 words) of what was confirmed, what was fixed, and final test/health status — don't paste the full report inline.
