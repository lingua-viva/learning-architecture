# LV Claudia-Lens Repass — Spec

**Status**: DRAFT — ready for execution by a fresh model/session.
**Author context**: written 2026-07-20, immediately after the P0 technical-correctness improvement cycle closed (`SPEC_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md` — all 9 P0 experiences live-verified, 3 real bugs found and fixed, 476/476 tests passing). Mirrors Mission Canvas's proven two-pass pattern: technical-correctness pass, then a founder/person-lens differentiation repass (`mission-canvas/dev/SPEC_P0_FOUNDER_LENS_REPASS_2026-07-20.md`), before entering numbered P1/P2/... improvement cycles.
**Companion prompt**: `dev/EXECUTION_PROMPT_LV_CLAUDIA_LENS_REPASS_2026-07-20.md` — the self-contained kickoff prompt for the executing model.

---

## Why this spec exists

The just-closed P0 pass measured **correctness**: does each experience do what the happy-state doc claims, end to end, against the real running app. All 9 P0s now pass that bar.

Correctness is necessary but not sufficient. Lingua Viva is not a generic edtech wrapper — it exists to embody a specific educator's design philosophy. Claudia Canu Fautré (`lenses/LENS-PERSON-002_claudia_canu.yaml`) is a systems-thinking curriculum architect: builder-first, evidence-based, allergic to deficit language about children, and explicit about when a document should carry Malaguzzi's poetic-philosophical voice and when it should not (`lenses/VOICE-EDU-001_malaguzzi_inspired.md`). A screen or response can be technically correct and privacy-safe and still fail to read like something *she* would have built — generic in tone, wrong register for its audience, or quietly undermining the teacher's own judgment instead of supporting it.

This pass asks a different question of LV's built experiences: **would Claudia recognize this as reflecting her actual values and voice, or does it read like any other AI education product?**

This is a deliberate second pass with a different evaluative posture, not a request to re-open the P0 pass's settled technical decisions.

---

## What is already settled — do not re-litigate

All investigated live, with tests and evidence, in the just-closed P0 pass. Re-opening without new evidence wastes this pass:

1. **EXP04's `external_calls` counter** — now counts real `external_call_made` events instead of a hardcoded `0`. Confirmed correct via mocked external-route test and live local-Ollama re-run.
2. **EXP08's response-budget timeout** — now genuinely cancellable via `asyncio.to_thread`; confirmed live at `timeout_seconds: 1` returning in ~1.15s.
3. **EXP09's `PRIVATE_RISK` vs. `WARN` badge** — now visually distinct (`healthBadgeClass()` + `.badge.risk`). UI contract at v7.
4. **EXP01, EXP02, EXP03, EXP05, EXP06, EXP07** — confirmed matching the happy-state doc exactly, no technical gap.
5. **LV's protection model is architectural exclusion, not runtime interception** (per the happy-state doc's own "does not claim" section) — do not propose a gate/interception pattern as a "fix"; that would misdescribe the design LV actually has.

If this pass surfaces a genuine factual error in one of these (not a tone/voice disagreement), flag it explicitly and separately — don't silently patch over a settled technical decision.

---

## What "Claudia lens" means for this pass

Evaluate each experience as Claudia herself would, reading it the way she reads a colleague's curriculum draft or a proposal headed to leadership. Ground every judgment in a specific, named section of `lenses/LENS-PERSON-002_claudia_canu.yaml` or `lenses/VOICE-EDU-001_malaguzzi_inspired.md` — do not invent taste. Specifically:

- **Competence, not deficit, when describing children or students.** Malaguzzi's voice guide is explicit: children are never "struggling," "behind," "at-risk," or "needing remediation" — they are described through competence and wonder (`VOICE-EDU-001` §4.2, §7.5). Any LV copy that surfaces a student's name, progress, or need (Students roster, Assess, Reflect, Activity Pack drafts, Parent Message Moment) should be checked line-by-line against this. This is not a style preference — it is a hard line in both source documents.

- **The right voice in the right place — not Malaguzzi everywhere.** Claudia's own lens draws an explicit boundary: Malaguzzi's poetic register belongs in family-facing communications, institutional proposals, PD materials, and Italian curriculum documents — and explicitly *not* in data reports, assessment analysis, or operational/compliance surfaces (`LENS-PERSON-002` §how_to_work_with.writing_voice.when_to_use / when_NOT_to_use). Check each experience against this split: does the Parent Message Moment (family-facing) read with any warmth and image at all, or is it flat and templated? Conversely, does the Privacy view, Health/Doctor view, or Profile/export view stay in plain, evidence-based language instead of drifting into unearned poetic framing? Getting this backwards — bureaucratic language to parents, flowery language in a data report — is itself a finding.

- **Evidence over reassurance.** Claudia's peak moment is Prove MT's 93%-improvement result — she is "motivated by measurable impact on children. The data is the point" (`LENS-PERSON-002` §values.peak_moment). Vague reassurance ("your data is safe," "we care about privacy") is weaker, in her value system, than a specific, legible trace of what happened and why. This is the same standard the P0 pass already applied technically (EXP04/EXP08's "confirmed means reproduced" discipline) — this pass asks whether the *language* lives up to what the architecture now actually does.

- **Supports the teacher's judgment; doesn't replace it.** Claudia's working style is bottom-up and builder-first — she designs environments where people succeed by design, not by being told what to do (`LENS-PERSON-002` §working_style.process, §patterns.strengths). Her trust-builders include "acting on her proposals rather than praising them and shelving them" and "treating her as a peer in institutional design" (§how_to_work_with.trust_builders); her trust-breakers include being treated as an executor of someone else's plan. Read Plan, Assess, Activity Pack/Prepare, and Reflect through this lens: does the copy position the teacher as the author making a judgment call LV supports with evidence, or does it read like the tool is prescribing the answer?

- **Don't overwhelm — sequence.** Claudia's own named blind spot is presenting too many ideas at once, read by leadership as "not focused" rather than "has a vision" (`LENS-PERSON-002` §patterns.blind_spots, §growth_edges — "one proposal at a time, with evidence"). Mirror this onto the teacher-facing UI itself: does any single screen (first-run setup, the sidebar, Prepare/Activity Pack) dump too much at once on a teacher mid-lesson, or does it sequence the way she's had to learn to for leadership?

- **Family communication should show warmth *and* competence together, not one without the other.** Her "Family & Community Engagement" cluster is rated `exceptional`, evidenced by genuine trust built through both care and effectiveness (`LENS-PERSON-002` §capabilities.clusters). The Parent Message Moment (EXP07) already strips student names and AI-attribution phrases per the P0 pass — this pass asks whether what's left, after stripping, still sounds like something a trusted, warm educator would send, or whether the sanitization left it cold.

- **Explicitly out of scope for this pass**: no new experiences, no architecture changes, no new privacy/governance mechanisms. This is a craft/voice pass on existing copy and UX sequencing, not a rebuild. If it surfaces a genuine missing capability (not a tone gap), name it as a separate backlog item — don't build it here.

---

## Experience inventory for this pass

Per `dev/LV_HAPPY_STATE_P0_2026-07-20.md`'s own "Build Status Reference," LV has roughly 40 built experiences; the happy-state doc only scripts the 9 P0s in full and names the rest without enumerating them. **Do not assume the list below is exhaustive** — the first step of this pass's method is confirming the real, current experience inventory against the running app/codebase (nav items in `static/index.html`, routes in `src/web.py`), not against this table alone.

Known/named experiences to start from:

| Group | Experience |
|---|---|
| P0 (already technically verified) | Install, First-Run Setup, Why view, Privacy view, Profile view, Observation moment, Parent Message moment, Activity Pack/Prepare moment, Health/Doctor |
| Named, not yet lens-reviewed | Plan, Assess, Students roster, Reflect, Quick Capture, Settings, PWA install, native launcher, coordinator Programme view |
| Explicitly out of scope | Coordinator Evidence, Capacity, Trends — spec'd only, return `deferred`, no happy path exists yet |

Prioritize the experiences most likely to surface a Claudia-lens finding first: **Parent Message Moment** (family voice), **Students roster / Assess / Reflect** (child-competence language), **Plan / Activity Pack / Prepare** (teacher-judgment support), then work outward.

---

## Method

1. Read `CLAUDE.md` (repo root) for orientation and publication-safety rules.
2. Read `lenses/LENS-PERSON-002_claudia_canu.yaml` and `lenses/VOICE-EDU-001_malaguzzi_inspired.md` in full. These are the grounding sources — every verdict must cite a specific section of one or both, not general taste.
3. Confirm the real experience inventory against the running app (`python3 -m src.lv_cli serve 8787`) and `static/index.html`'s nav — reconcile against the table above before starting the review.
4. For each experience, live-run it against the real running app (curl/browser walk, not reading source alone — same "confirmed means reproduced" discipline as the P0 pass) and capture the actual copy/response text a teacher or parent would see.
5. For each experience, produce: (a) a one-line verdict — *sharp / adequate-but-generic / undersells or misreads Claudia's voice*, (b) the specific line(s) of copy that support the verdict, (c) which lens section grounds the judgment, (d) one concrete, low-risk suggestion (copy change, register change, sequencing change) that would move it up a tier — or "none, this is already sharp" if genuinely true.
6. Do not edit privacy/governance/routing code as part of this pass. Copy and UI-sequencing changes to `static/index.html` are in scope but require a UI contract bump (`python3 scripts/check_ui_contract.py --bump`) if shipped — check whether this pass is findings-only or expected to ship fixes before touching the contract.
7. Respect this repo's publication-safety rules (`CLAUDE.md`): no real student data, no institution names, no colleague names in the deliverable — even though the source lens file itself contains some of this, the new report should reference lens *sections*, not restate biographical specifics that aren't needed for the finding.

---

## Deliverable

A new report doc, `dev/reports/REPORT_LV_CLAUDIA_LENS_REPASS_2026-07-20.md`, containing:

- The per-experience verdict + evidence + lens-citation + suggestion table, covering at minimum the 9 P0s plus the 9 named non-P0 experiences (18 rows), noting any additional experiences found during inventory confirmation.
- A prioritized punch list: which 2-3 suggestions would most move the "would Claudia recognize this as hers" needle, ranked.
- Any settled-list factual errors found (should be rare/none) — called out separately, not folded into the punch list.
- A same-day status line added to `dev/INDEX.md` per repo convention.

This pass does not require code changes to ship — it can land as a findings/recommendations doc, same as MC's founder-lens precedent. If the operator wants specific suggestions implemented, that's a follow-up decision after reading the report, not part of this pass's done-criteria. Per this repo's standing convention, any code/copy changes that *are* made during this pass stay uncommitted — the operator holds the sole commit window in this repo.
