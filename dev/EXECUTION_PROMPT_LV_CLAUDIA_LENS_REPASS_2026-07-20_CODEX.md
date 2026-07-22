# Prompt: LV Claudia-Lens Repass (Codex variant)

Copy everything below the line into a fresh Codex session, run from the repo root (`learning-architecture`). Codex has shell + file access in this repo; no network access beyond `localhost:8787` is needed.

---

You are running as Codex inside the `learning-architecture` repo (Lingua Viva). This task is a **review pass**, not a build task — treat it that way: findings first, ordered by severity/impact, with explicit file and line references. Do not open with a summary of what you're about to do; start producing findings once you've done the required reading.

**Required reading, in order** (do not skip or skim — this pass lives or dies on accurate grounding):
1. `CLAUDE.md` (repo root) — publication-safety rules and repo architecture. You are bound by these for anything you write.
2. `dev/specs/SPEC_LV_CLAUDIA_LENS_REPASS_2026-07-20.md` — the full task definition: why this pass exists, what's already settled (do not re-litigate), what "Claudia lens" means for the evaluation, the experience inventory, method, and deliverable format.
3. `lenses/LENS-PERSON-002_claudia_canu.yaml` — Claudia's full person lens. Every verdict you write must cite a specific section of this file (e.g. `§working_style.process`, `§how_to_work_with.trust_builders`) — no general taste calls.
4. `lenses/VOICE-EDU-001_malaguzzi_inspired.md` — the voice guide Claudia's lens points to. Pay specific attention to §4.2 and §7.5 (deficit language to avoid) and the `when_to_use` / `when_NOT_to_use` split in the lens file — this is the sharpest, most checkable criterion in the whole pass.

**The task in one sentence**: LV's 9 P0 experiences were just verified for technical correctness (`dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`, 476/476 tests passing). This pass reviews those 9 plus ~9 more named, built experiences and asks whether each one's *actual copy and UX* — not its correctness — reads as something Claudia Canu Fautré would recognize as hers: evidence-first, competence-not-deficit toward children, respectful of the teacher's own judgment, and critically, using the *right* voice register in the *right* place (Malaguzzi's poetic voice belongs in family/proposal/PD writing per her own lens — and explicitly not in data reports, privacy views, or operational surfaces).

**Do not under-deliver.** The deliverable is a real file at `dev/reports/REPORT_LV_CLAUDIA_LENS_REPASS_2026-07-20.md`, not a conversational summary. Produce that file. If you find yourself writing more than a few paragraphs of framing without touching the file, stop and write the file.

**Hard constraints**:
- Do not re-open the P0 pass's settled technical decisions (EXP04's external-call counter, EXP08's timeout cancellability, EXP09's badge CSS, or the confirmed-correct EXP01/02/03/05/06/07). If you find a genuine new factual error in one, report it as a separately flagged item — do not silently patch it, and do not fold it into the main verdict table.
- Craft/voice/UX-sequencing pass only. No new experiences, no new privacy/governance mechanisms, no changes to LV's protection model (architectural exclusion, not runtime interception — don't propose a gate/interception pattern, it would misdescribe the actual design).
- Live-run every experience against the real running app before writing a verdict on it: `python3 -m src.lv_cli serve 8787` in one terminal, then `curl`/browser walk against it in another. Read the actual response text. Do not verdict from source code alone, and do not verdict from the happy-state doc's prose alone.
- Ground every verdict in a named section of one of the two lens files.
- Publication safety (`CLAUDE.md`): no real student data, no institution names, no colleague names in the report. Cite lens *sections*, don't restate biographical specifics from the lens file that aren't load-bearing for the finding.
- If you touch `static/index.html` or `src/web.py`, that requires a UI contract bump (`python3 scripts/check_ui_contract.py --bump`) — but default to findings-only unless a fix is truly trivial and low-risk. Whatever you change, leave it **uncommitted** — the operator holds the sole commit window in this repo. Do not run `git commit`.

**Report structure** (findings first, per the review mode above):
1. Per-experience verdict table — minimum 18 rows (9 P0 + 9 named non-P0), each row: verdict (`sharp` / `adequate-but-generic` / `undersells-or-misreads`), the specific copy line(s) that support it, the lens section that grounds the judgment, one concrete low-risk suggestion (or "none, already sharp").
2. A ranked punch list — top 2-3 suggestions most worth acting on, in priority order.
3. Any settled-list factual corrections found (should be rare/none), called out separately from the punch list.
4. A one-line status entry appended to `dev/INDEX.md`, matching the existing table format.

Before starting the verdict table, confirm the actual experience inventory against the running app and `static/index.html`'s nav — the happy-state doc's "~40 experiences" figure is approximate, not fully enumerated. Reconcile against the starting list in the spec's "Experience inventory for this pass" section.

When the report file is written, give a short final message (under 150 words): the file path, the punch-list top 3, and nothing else. No restated framing.
