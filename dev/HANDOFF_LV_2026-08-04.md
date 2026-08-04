# LINGUA VIVA — FULL HANDOFF (written 2026-08-04, post-wave, pre-v0.2.36)

**Audience:** the next Claude Code context window on the build machine (and any
agent joining mid-stream). Read this, then `dev/CLOSURE_WORKLIST_2026-08-04.md`
(the active plan), then check `git log origin/main` before believing anything
about build state. Disk is truth; this doc is orientation.

---

## 1. What this is

Lingua Viva: local-first desktop app for teachers — document ingest → grounded
student lenses → voice observations → Drive sync. Public repo doubles as
Claudia Canu Fautré's education portfolio. **Real teachers started using it the
morning of 2026-08-04.**

- Repo: `git@lingua-viva:lingua-viva/learning-architecture.git` (SSH alias
  `lingua-viva`, key `~/.ssh/lingua-viva`). Single remote, branch `main`.
- Live site: **linguaviva.art** (GitHub Pages from `docs/` — NOTHING lands in
  docs/ except deliberate site changes).
- Releases: `auto-release.yml` fires on ANY push touching `src/**`, `static/**`,
  `desktop/**`, `docs/index.html`, `pyproject.toml` → tests → tags next
  `desktop-v*` → pins `docs/index.html` → `desktop-release.yml` builds+signs.
  **To push WITHOUT releasing: `[skip ci]` in the HEAD commit message of the push.**
- "Pushed" = downloadable on linguaviva.art right now, verified by the
  **AGENTS.md 7-step checklist** (read it; step 7 = exactly ONE version live —
  retire old releases with `gh release delete <tag> --yes`, keep tags for
  version computation).
- Governance: repo `CLAUDE.md` + `publication-policy.md`. Privacy first: no
  institution names, no real student/colleague names, honest maturity labels.
- MC/palette/pretendhome repos are under a SEPARATE standing push hold (patent
  material). LV pushes are allowed and expected.

## 2. Release state right now

- **desktop-v0.2.35 is the sole live build** (0.2.32–34 releases retired
  2026-08-04, tags kept). macOS signed+notarized (verified in CI log).
  **Windows build UNSIGNED** → SmartScreen wall (worklist C1: Azure Trusted
  Signing port; B3: warning copy on download page).
- 0.2.35 is an **honest package of an incomplete wave**: safety rails, vault,
  lens engine, Ask+PII gate, Students ingest UI all shipped and verified live —
  but extraction (T3), Observe mic/edit (T5), and Drive ingest (T1) are ABSENT.
  `docpipe/extract.py` and `drive.py` are still T0's NotImplementedError stubs
  unless T3/T5 have landed since this was written — CHECK.

## 3. The 2026-08-04 wave build — who built what

Planned in `dev/RUNBOOK_LV_BUILD_WAVES_2026-08-04.md` (waves, file-ownership
matrix, cross-cutting rules, "what must work by morning") + 12 prompt pairs
`dev/PROMPT_PAIR_*_2026-08-04.md`. Two machines:

**This machine ("lingua-viva" account, Linux):**
- Build pack authoring + push (a9b80f4)
- T0 contract freeze (30d4cac → pushed in e174f53's push)
- HF2 backend hotfixes: F4 false no-model refusal (stale breaker + dup
  ReasoningEngine), F6 bundle-relative path → LV_STATE_HOME (e174f53)
- T2 vault + T4 lens engine, 15-pass hardened together (78387e8, 674c7d4)
- real_anon gitignore guard (c477d29) — **last push from this account during
  the wave: 23:53 UTC**
- Closure worklist (12c26b0)

**Windows machine ("pretendhome" account):**
- HF1 frontend hotfixes: F2 GIR warning in text via renderAnswerSafety, F1b mic
  release, F5 student placeholder, companion mic hidden (97534fd) + CRLF
  contract relock (785b9dd, 5d6dcbf)
- T8 Ask = Perplexity + PII egress gate (f8bf166)
- 15-pass HF1+T8 hardening (0bfd896)
- T6 Drive write-back + sync queue (4ef8259) — push_file deferred pending T1
- T9 Students-from-file ingest UI (db5b6b9, c372024)
- Windows operator QA + `POSTMORTEM_WAVE_CONVERGENCE_FAILURE_2026-08-04.md`
  (~/Downloads, local)

**Never built by anyone (the hole):** T1 Drive ingest, T3 extraction, T5
Observe capture, T7 e2e gate. No SPEC_T1/T3/T5 files exist = lanes never ran
(H2 confirmed: not lost work — never dispatched). T5 was queued on this machine
but the window was never opened; T1/T3 were orphaned when the Windows machine
was verbally redirected to T9/T6.

**As of this handoff: T3 and T5 windows were dispatched on this machine**
(prompt pairs T3/T5, with Claudia-report addenda folded in: .txt ingest + JSON
error bodies for T3; CEFR-force removal + mic-first for T5). T7 runs after
they land. T1 slipped by rule (local-only loop acceptable day one).

## 4. The convergence failure — lessons now binding

Full analysis: `~/Downloads/POSTMORTEM_WAVE_CONVERGENCE_FAILURE_2026-08-04.md`
(local). Short version: three releases shipped in one hour, each honestly
packaging an incomplete main; "done" claims crossed machines through human
relay without git verification; the designed gate (T7) was never run; nothing
in CI refuses a NotImplementedError on the critical path.

**Rules adopted (enforce in every session):**
1. No lane is "done" until the RECEIVING side sees the sha:
   `git fetch && git log origin/main --oneline -3`. Status relayed to the
   operator includes the sha on origin or the word UNVERIFIED.
2. Lane reassignments get one written line in the runbook BEFORE they take
   effect. Verbal reassignment orphaned T1/T3.
3. A green auto-release ≠ the build is done. The T7 gate (and worklist C4: T7
   as a CI gate) is what "done" means.
4. Fix failure CLASSES at chokepoints (e.g., bare-500s → endpoint-layer JSON
   error handler), and add a test locking the class.

## 5. QA inputs (three landed, two pending)

1. **Windows operator report** (email, 2026-08-04 evening): W1 SmartScreen UGLY,
   W3 no mic (=T5), W4b __pycache__ litter (C2), W5 docpipe packaging CLEAN,
   V6 honest-failure ingest PASS, H10 PII gate AIRTIGHT (external_calls:0,
   hashed log), NEW-1 Drive connect broken on Windows (repro needed), NEW-2
   observations not editable (=T5), NEW-3 stale dev roster on operator box
   (wipe ~/.lingua-viva before demos). Verdict: not shippable standalone;
   skeleton healthy, muscle missing.
2. **Claudia (live teacher, macOS)**: `qa/2026-08-04_teacher-readiness-claudia.md`
   (committed 4b77a04). P0-1 import broken (bare 500s + .txt rejected), P1-1 no
   mic, P1-2 CEFR force regression (invented-data risk — her strongest product
   point), P1-3 Settings missing voice/sync/privacy, P2s: TTS Italian accent on
   English, refusal wording ("The Ask section…"), Sources nav, permission
   pileup. Quit condition, verbatim: "If the voice doesn't work and I have to
   type everything manually." Positive: zero invented data, refusal held
   airtight on a real teacher's machine.
3. **Postmortem** (see §4).
4. **PENDING: Chip's macOS QA** (synthetic-only session, harness below) and
   **Kiro's build audit** (`dev/AUDIT_KIRO_BUILD_2026-08-04.md` expected —
   prompt given, was running). Fold both into the worklist on arrival.

## 6. The active plan

**`dev/CLOSURE_WORKLIST_2026-08-04.md`** (on main, 12c26b0) is the single
accumulation point. Gate A = morning bar (T3, T5, JSON errors, CEFR regression,
T7, regression floor — each with a DONE-PROOF command). Gate B = same-day
(refusal wording via `src/lingua_viva/messages.py`, TTS locale, SmartScreen
copy, Settings sections, aborted Windows checks, Perplexity keys). Gate C =
this week (signing, PYTHONDONTWRITEBYTECODE, T1, T7-in-CI, hygiene, FRs).

**Roles:** Kiro is the closer — executes the worklist, captures DONE-PROOF
output, STOPS before push. This machine's Claude window is the reviewer: re-run
pytest + teacher-readiness harness + T7, spot-check every DONE-PROOF, then push
→ v0.2.36 → 7-step verification → retire 0.2.35.

## 7. Testing packets + harnesses (all LOCAL, ~/Downloads on this machine)

- `lingua-viva-teacher-readiness-test-packet-2026-08-01/` — Chip's original
  synthetic packet (Marco Bianchi / Nora Rossi + G3 PDF). Its QA plan is
  RETIRED (pre-wave flows; Scenario D now inverted — student-name questions
  must REFUSE).
- `lingua-viva-teacher-readiness-test-packet-2026-08-03/` — the current packet:
  synthetic docs + REAL ANONYMIZED student documents (aliases Aron Park / Jerry
  Park / Ponte Academy / Federica Baldi over real progress reports, lesson
  plans, work samples) + both new harnesses:
  - `HARNESS_PROMPT_CHIP_2026-08-04.md` — technical QA, synthetic-only fence,
    Scenario B field-invention check is the centerpiece, Scenario E refusal
    inverted.
  - `HARNESS_PROMPT_CLAUDIA_2026-08-04.md` — teacher-truth: grounding read,
    dictation rhythm (It/En/code-switched), refusal WORDING judgment, Drive
    loop as parent-conference doc, Malaguzzi language check. Verbatim quotes.
- **OPEN OPERATOR DECISIONS (asked repeatedly, never ruled):**
  1. SCRUB the two real progress reports — they still contain real school
    leadership names and a ministry registry number (school-identifying). The
    packet's "zero leakage" claim only grepped the alias key. Blocks wider
    distribution; Claudia (trust circle) already tested with them.
  2. SPLIT a synthetic-only `chip-test-documents/` folder so real-anon files
    never land on Chip's machine (she may already have the full Drive folder).
- Windows operator harness was delivered inline in chat (self-contained paste
  block, checks W/V/H/X) — re-issue from this handoff's §5 findings if needed.

## 8. Privacy traps (do not learn these twice)

- `tests/fixtures/docpipe/real_anon/` — REAL anonymized student data + the
  alias key. **Gitignored (c477d29). Never commit. Never quote its contents
  into repo files.** The repo is public.
- Repo-committed fixtures use ONLY Marco Bianchi / Nora Rossi (synthetic, match
  the T0 fixtures in `tests/fixtures/docpipe/`).
- Never `git add -A` in this repo. Perma-dirty local files: two
  `ontology/proposals/CAND-*.yaml`, `sanitizer/data/firewall_log.ndjson`, two
  `dev/PROMPT_CHIP_QA_*` drafts. Commit by explicit path only.
- Ask/PII gate: student-name queries get REFUSAL (never sanitize-and-send);
  message class lives in `src/lingua_viva/messages.py`.

## 9. Document index

**In repo (dev/):**
- `RUNBOOK_LV_BUILD_WAVES_2026-08-04.md` — wave plan, ownership matrix, rules,
  morning bar, machine-agnostic run instructions
- `PROMPT_PAIR_{T0,HF1,HF2,T1..T9}_2026-08-04.md` — 12 spec/impl prompt pairs
- `CONTRACTS_V1_2026-08-04.md` — frozen vault layout, schemas, module seams
- `SPEC_T2_VAULT / SPEC_T4_LENS_ENGINE / SPEC_T6_SYNC / SPEC_T8_ASK /
  SPEC_T9_INGEST_UI _2026-08-04.md` — landed lanes' Phase-1 specs (absence of
  SPEC_T1/T3/T5/T7 = how we proved the lanes never ran)
- `LV_BUILD_BRIEF_2026-08-04.md` — operator-ruled brief (source of all rulings)
- `QA_DEEP_DIVE_CHIP_0.2.32_2026-08-04.md` — pre-wave bug source (F1–F6)
- `CONVERGENCE_BRIEF_LV_VOICE_EXPERIENCE_2026-08-03.md` — superseded voice
  redesign (context for HF1/T5 decisions)
- `CLOSURE_WORKLIST_2026-08-04.md` — THE ACTIVE PLAN
- `assets/ask-render-reference-2026-08-03.png` — Ask text-render reference
- `qa/2026-08-04_teacher-readiness-claudia.md` — Claudia's report

**Local only (~/Downloads):** postmortem, both test packets + harnesses,
`2026-08-04_teacher-readiness-claudia.md` (source of the committed copy).

**Governance:** `CLAUDE.md`, `AGENTS.md` (7-step), `publication-policy.md`.

## 10. Operator rulings ledger (all binding)

1. Ask = external Perplexity only; text populates the Ask tab; NO artifacts in
   Ask yet; student questions → refusal (supersedes deep-dive F3).
2. ONE student lens format — T4 bridges to existing StudentLensStore; teacher
   lens is later.
3. Day-one bar: "working at all"; refine after. Wrong output worse than missing.
4. Offline-first: everything except Perplexity + Drive sync works with no
   internet; offline is a supported state, not an error.
5. Christi's 10 profile categories are the lens's first-class fields, aligned
   with the existing support_category enum.
6. Voice: Observe gets STT; TTS belongs to Ask. Companion mic hidden (§8.2)
   pending T5's proper Observe mic — postmortem offers a one-line un-hide
   (`voice-hidden` on `<body>`) as an emergency stopgap; decide deliberately.
7. Kiro closes, Claude reviews, THEN push. Operator holds prod decisions.

## 11. First moves for the next window

1. `git fetch && git log origin/main --oneline -10` — did T3/T5/T7 land? Did
   Kiro's audit or Chip's report arrive? Update the worklist accordingly.
2. If Kiro reports done: run the reviewer pass (worklist Release sequence
   step 3) — full pytest, `lv eval teacher-readiness`, T7 gate, DONE-PROOF
   spot-checks — then push, 7-step verify v0.2.36, retire 0.2.35.
3. Chase the two open operator decisions (§7): scrub + split.
4. Keep every status line sha-verified or marked UNVERIFIED.
