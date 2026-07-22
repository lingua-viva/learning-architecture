# Prompt: LV Claudia-Lens Repass

Copy everything below the line into a fresh session with a different model. It is self-contained — the executing model has no memory of the session that produced it.

---

You are working in the `learning-architecture` repo (Lingua Viva). Start by reading `CLAUDE.md` at the repo root for orientation — publication-safety rules, repo architecture, and the two-layer structure (curriculum/portfolio layer + Lingua Viva runtime layer). You are operating under those rules for this task.

Then read `dev/specs/SPEC_LV_CLAUDIA_LENS_REPASS_2026-07-20.md` in full. That spec is your task definition — it explains why this pass exists, what's already settled from the prior technical-correctness pass (do not re-litigate it), what "Claudia lens" means for this evaluation, the experience inventory to start from, the method, and the deliverable format. Follow it as written.

**One-sentence summary of the ask**: all 9 P0 experiences were just verified for technical correctness (`dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md` — 3 real bugs found and fixed, 476/476 tests passing). This pass is a different read of LV's built experiences — both the 9 P0s and the ~9 other named, built (non-deferred) experiences — through the lens of Claudia Canu Fautré, the real educator LV's product and voice are modeled on: does each experience's actual copy and UX read as something she would recognize as hers (evidence-first, competence-not-deficit about children, builder-first respect for the teacher's own judgment, and — critically — the *right* voice register in the *right* place, per her own documented rule that Malaguzzi's poetic register belongs in family/proposal/PD writing and explicitly not in data reports or operational surfaces) — or does it read like generic edtech that could have come from anyone?

Before you evaluate anything, read the two grounding sources in full — do not evaluate from memory or general impression of "warm educator voice":
- `lenses/LENS-PERSON-002_claudia_canu.yaml` — Claudia's full person lens (values, working style, blind spots, growth edges, how-to-work-with, and the writing-voice section with its explicit when-to-use / when-NOT-to-use split).
- `lenses/VOICE-EDU-001_malaguzzi_inspired.md` — the Malaguzzi voice guide her writing-voice section points to, including its explicit list of language to avoid (deficit framing, clinical/compliance language) and language patterns to emulate.

**Hard constraints**:
- Do not re-open the P0 pass's settled technical decisions (EXP04's external-call counter, EXP08's timeout cancellability, EXP09's badge CSS, or the confirmed-correct EXP01/02/03/05/06/07) unless you find a genuine new factual error — report that separately and explicitly, don't silently patch it.
- This is a craft/voice/UX-sequencing pass, not an architecture pass. No new experiences, no new privacy/governance mechanisms, no rebuild of LV's protection model (which is architectural exclusion, not runtime interception — don't propose a gate/interception pattern, that would misdescribe the actual design).
- Live-run every experience against the real running app (`python3 -m src.lv_cli serve 8787`) and read the actual copy/response text a teacher or parent would see. Do not evaluate from reading source code or the happy-state doc's prose alone.
- Ground every verdict in a specific, named section of one of the two lens files. No general taste calls.
- Respect this repo's publication-safety rules (`CLAUDE.md`): no real student data, no institution names, no colleague names in the report — reference lens *sections*, don't restate biographical specifics from the lens file that aren't needed for the finding.
- If you change any code or copy (`static/index.html`, `src/web.py`) as part of this pass, it requires a UI contract version bump (`python3 scripts/check_ui_contract.py --bump`) — but this pass is expected to land as a findings/recommendations doc first; check with the spec on whether shipping fixes is in scope before you touch the contract. Per this repo's standing convention, leave any changes uncommitted — the operator holds the sole commit window in this repo.

**Deliverable**: `dev/reports/REPORT_LV_CLAUDIA_LENS_REPASS_2026-07-20.md`, with the per-experience verdict table (18 rows minimum: 9 P0 + 9 named non-P0 experiences, plus any additional experiences you confirm exist during inventory), a ranked 2-3-item punch list, any settled-list corrections, and a `dev/INDEX.md` status line — exact format is in the spec's "Deliverable" section.

Work through the full experience inventory (confirm it against the real app/codebase first — the happy-state doc's "~40 experiences" figure is approximate and not fully enumerated) before writing the report. When done, give a short summary (under 200 words) of the top findings — don't paste the full report inline.
