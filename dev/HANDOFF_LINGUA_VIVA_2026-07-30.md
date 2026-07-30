# Handoff — Lingua Viva, 2026-07-30

**To the agent picking this up**: you are inheriting a live, uncommitted build in a repo
that ships to real teachers Monday. Read this whole document before touching anything.
Do not assume prior context — verify everything stated here against the actual files
before acting on it, the same way it was verified to write this.

---

## 0. Ground Rules (read first, these are not optional)

1. **Do NOT commit.** The operator has one dedicated commit window for this repo and
   commits it themselves — this has been stated explicitly in prior sessions. Your job
   is to build, test, and report status. Leave the working tree as modified/untracked
   files for the operator to review and commit.
2. **PUSH = downloadable on the live site, right now.** Nothing else counts — not
   committed, not on `main`, not a green CI run. See `AGENTS.md` §"THE Definition of
   Pushed" if you get anywhere near a release question. You almost certainly won't
   need to touch this — flagging it so you don't accidentally assume "tests pass" means
   "shipped."
3. **Verify, don't assume.** Every claim in this document was checked against the
   actual file/line/test state as of this handoff (timestamps below). Repo state
   changes fast in this project — re-verify anything load-bearing before you act on it,
   especially file existence and line numbers.
4. **Privacy first.** This is a children's education product (refugee students). Never
   let student names/data reach an external service without the existing gates
   (`check_publication_safety`, the Rime privacy gate in `/api/voice/tts`). If your work
   touches anything that could weaken those gates, stop and flag it — don't "improve"
   past them.
5. **File discipline**: specs and prompts go in `dev/`, named `SPEC_LV_<TOPIC>_<date>.md`
   / `PROMPT_LV_<TOPIC>_BUILD_<date>.md`, matching every existing file in that directory.
   Don't invent a new convention.
6. **Hermetic tests only in CI-path code.** This repo has been bitten twice before by
   module-level path/env constants breaking test hermeticity (`sanitizer/client.py`,
   `2026-07-20`). Resolve paths/env lazily inside functions, not as module constants.

---

## 1. Where Things Stand Right Now — Voice/GIR Build

### 1a. What just landed (verified, uncommitted)

Two specs were built back-to-back this session:
- `dev/SPEC_LV_GIR_VOICE_TONE_2026-07-29.md` / `dev/PROMPT_LV_GIR_VOICE_TONE_BUILD_2026-07-29.md`
- `dev/SPEC_LV_GOLDEN_VOICE_LOOP_2026-07-30.md` / `dev/PROMPT_LV_GOLDEN_VOICE_LOOP_BUILD_2026-07-30.md`

Verified landed in the working tree (uncommitted — `git status --short` shows these as
`M`/`??`):

| What | Verified at |
|---|---|
| `PathRecord.gir_score`, `.gir_method`, `.voice_tone` fields | `memory/schema/path.py:45-47` |
| Inline grounding computation ("Step 6.25: GROUND") in the pipeline, before STORE | `src/pipeline.py:920-996` |
| `PipelineResult.grounding` field | `src/pipeline.py:158` |
| `resolve_voice_tone()` pure function | `src/lingua_viva/voice_tone.py` (new file) |
| `/api/query` returns `grounding`, `gir_score`, `gir_method`, `voice_tone`, `tone_prefix` | `src/web.py:4002-4039` |
| `/api/voice/tts` accepts and prepends `tone_prefix` | `src/web.py:1737-1739` |
| Frontend passes `tone_prefix` from query response into `speak()` | `static/index.html:834, 1874-1884` |
| `GW-VOICE-006` golden workflow (STT→pipeline→grounding→tone→hermetic-TTS check) | `src/lingua_viva/golden_workflows/schema.py:6`, `runner.py` |
| New/modified tests | `tests/test_voice_tone.py`, `tests/test_golden_workflows.py`, `tests/fixtures/voice/` |

**Targeted test run at handoff time**: `pytest -q tests/test_voice_tone.py
tests/test_golden_workflows.py tests/test_voice_tts_privacy_gate.py
tests/test_voice_recognition_language.py tests/test_ui_contract.py` → **46 passed**.
The **full suite has not been run** as of this handoff — run it first, before anything
else, and read the output rather than trusting a pass/fail label.

### 1b. What is explicitly NOT covered yet — item 1 of the original 5 gaps

The original 5-gap analysis (below, for reference) is 4/5 addressed by the two specs
above. **Item 1 was explicitly excluded from both specs** and has no spec written yet:

> **1. Voice loop is fully sequential — no streaming, no early TTS.**
> `static/index.html` does `/api/voice/stt` → `/api/query` → `/api/voice/tts` as three
> separate blocking round trips, each awaiting a full JSON response before the next
> starts. No SSE/streaming exists anywhere server-side. A student waits for
> STT-complete → full-answer-complete → TTS-complete in full serial.

Re-verify this is still true (`grep -n "text/event-stream\|StreamingResponse\|/api/chat" src/web.py` should still return nothing) — if the sequential architecture changed since this handoff, update your plan accordingly.

**Your first substantive task**: write `dev/SPEC_LV_VOICE_STREAMING_2026-07-30.md` +
matching `PROMPT_LV_VOICE_STREAMING_BUILD_2026-07-30.md`, covering SSE (or an
equivalent incremental-delivery mechanism) for `/api/query` and an early-sentence-
trigger for TTS, mirroring MC's Slice 3 pattern but grounded in LV's actual FastAPI
route structure (read `src/web.py`'s `/api/query` handler fresh — don't assume the line
numbers above still hold after the GIR build's edits). Then build it, following the
same rigor as the two specs already in this directory — read them both first as the
format/rigor bar to match.

### 1c. The 15-iteration hardening loop — what "done" actually means

The user's explicit standard: **"questions to actually work when asked to the agent,
and GIR to actually be a grounding voice in all of this."** This is not "tests pass" —
it's "a real teacher asks a real question through the real voice path and gets a
correctly-toned, correctly-grounded spoken answer, every time, including edge cases."

Run a hardening loop (this repo's established pattern — see `a235614 fix(lv): 15-pass
hardening loop — app-reality eval + 4 real defects` in git log for precedent) that
does, for at least 15 iterations, real end-to-end passes:

1. Pick a real teacher-style question (vary domain/intent each pass: curriculum,
   student support, admin, something with strong local knowledge coverage, something
   with none).
2. Drive it through the **actual running app** — not just unit tests calling functions
   in isolation. Use `python3 -m src.lingua_viva.cli` or launch the app and hit the
   real `/api/query` and `/api/voice/tts` routes.
3. Confirm: the answer is correct/reasonable, `gir_score` reflects real grounding
   (spot-check: does a question you know has no local source actually get a low
   score and a hedge?), `voice_tone` matches the score, and the spoken audio (or the
   text sent to TTS) actually carries the tone prefix when it should.
4. Log every defect found — don't just fix and move on silently. Follow this repo's
   pattern: real defects get committed as `fix:` commits with the defect described (see
   `a235614`'s "4 real defects" as the bar), and non-obvious ones get a gap-signal or
   note for the operator.
5. After 15 passes, write a short report (`dev/reports/REPORT_LV_GIR_VOICE_HARDENING_2026-07-30.md`
   or similar, matching `dev/reports/` naming) — what broke, what got fixed, what's
   still open.

**Do not fake this.** Calling `resolve_voice_tone(0.3)` in a unit test and confirming it
returns `"clarify"` is not the same as confirming a real query through the real
pipeline produces a `gir_score` anywhere near 0.3 in a way that reflects real grounding
quality. The whole point of this loop is catching the gap between "the code path
exists" and "the code path does the right thing on real input."

---

## 2. Infra Essentials Review — Must Work by Monday

The user's explicit list of what has to work at 100% by Monday: **Slack, Google Drive,
lens creation from documents (desktop and Drive), and lesson planning per student
cohort.** This has not yet had a dedicated functional review in this session — you are
the first pass at this.

### 2a. What exists (verified present, functional status NOT yet verified)

| Area | Files found | Status |
|---|---|---|
| Slack | `src/lingua_viva/slack_socket.py`, `slack_integration.py`, `slack_credentials.py`, `src/education/slack_ops_bot.py`, `src/education/slack_bot.py` | Exists. Functional status unverified — was last touched per `SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27.md` / `REPORT_SLACK_OPS_HARDENING_2026-07-27.md` (read those first). |
| Google Drive | `src/lingua_viva/google_drive_integration.py`, `google_drive_oauth.py` | Exists. Related specs: `SPEC_LV_DRIVE_WORKSPACE_2026-07-27.md`, `SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27.md`, `SPEC_LV_DRIVE_FINAL_HARDENING_2026-07-27.md` — read all three, they document known hardening state. |
| Lens creation from documents | `src/lingua_viva/student_lens_writer.py`, `extraction_engine.py`, `src/education/teacher_lens_builder.py`, `src/lingua_viva/filemap.py` | Exists in some form for both student and teacher lenses. **Explicitly unverified**: does "desktop" document ingestion (local filesystem, not just Drive) actually flow into lens creation end-to-end? Trace it, don't assume from filenames. |
| Lesson planning per student cohort | **Weak/no direct signal** — `grep -rl "lesson_plan\|cohort" src/` returned no clearly dedicated module, only incidental string matches in `ingest.py`, `admin_metrics.py`, `web.py` | **This may be a real gap, not just an unverified feature.** Your first action here should be to determine whether "lesson planning per student cohort" exists as a distinct capability anywhere, or whether it's expected to be composed from existing pieces (per-student lens + curriculum knowledge + Ask). Report this honestly — don't force-fit an answer. |

### 2b. What to actually do

1. **For each of the 4 areas**, do a real functional trace: find the actual UI entry
   point in `static/index.html`, the route it calls in `src/web.py`, and run it against
   real (or realistic hermetic) data. Confirm it works, don't infer from file presence.
2. **Write a status report** — one file, e.g.
   `dev/reports/REPORT_LV_MONDAY_ESSENTIALS_STATUS_2026-07-30.md` — with a clear
   PASS/FAIL/PARTIAL/MISSING per area, evidence for each verdict (file:line, or a
   reproduction you ran), and a prioritized list of what's blocking each from being
   100% by Monday.
3. **Write an improvement-loop spec** for whatever is not yet at 100%, following the
   same `SPEC_LV_*` + `PROMPT_LV_*_BUILD_*` pattern as the voice/GIR work — sized to
   what's actually broken, not a rewrite.
4. **Integrate with the GIR/voice centralization from Section 1** where it's a real fit
   — e.g., if lesson-plan generation or lens-derived answers go through
   `run_teacher_query()` / `Pipeline.run()`, they should automatically inherit
   `gir_score`/`voice_tone` once Section 1's work is solid, since that's now computed
   inline in the pipeline itself. Don't bolt on a second, parallel grounding check —
   reuse the one that now exists at `pipeline.py`'s GROUND step. If Slack/Drive
   ingestion paths bypass the pipeline entirely, that's worth flagging as its own gap.
5. **Priority order**: fix real breakage before adding new capability. If "lesson
   planning per cohort" turns out to not exist at all, that's a scoping conversation
   for the operator, not something to invent unilaterally under deadline pressure —
   report it clearly and let them decide whether it's in scope for Monday or not.

---

## 3. Taxonomy + Matrix Docs — Mine for Reinforcing Specs

Two large reference docs already exist (created earlier today, both untracked):

- `dev/LV_SYSTEM_THING_OUTCOME_TAXONOMY_2026-07-30.md` (~43KB) — full System → Thing →
  Outcome taxonomy for this repo, 16 pillars (`RTE` Runtime Execution through `DLV`
  Delivery/Release Process), LV's equivalent of MC's own taxonomy doc. Read the
  vocabulary section (§0) and the ID scheme (§0.5) first to understand how to navigate
  it — it's a reference table, not prose to read linearly.
- `dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30.md` (~28KB) — derived
  from the taxonomy plus ~15 other specs/reports, grouped by system/pillar, each row
  tagged `A` (directly useful to issue awareness/measurement/ranking/recursive
  improvement) or `B` (other unimplemented/partial/deferred idea), each with a
  "Current status / note" column. **This already references both voice/GIR specs from
  Section 1 as sources** — it was built with knowledge of that work in flight.

### What to do with them

1. Read both in full before acting — they're large and already synthesize a lot of
   prior work; don't re-derive what's already there.
2. Cross-reference every `A`-tagged row against the actual current file state the same
   way this handoff and the two prior specs did — the matrix's "Current status / note"
   column is informative but was written by a prior pass, not guaranteed current.
3. Prioritize rows that reinforce or depend on Sections 1 and 2's work (grounding
   inline-computation reuse, gap-signal ranking, hermeticity sweeps) — those compound
   with what's already landed today rather than starting a new thread.
4. Write specs for the highest-leverage `A`-tagged ideas using the same rigor as
   `SPEC_LV_GIR_VOICE_TONE_2026-07-29.md` / `SPEC_LV_GOLDEN_VOICE_LOOP_2026-07-30.md` —
   verified file/line references, explicit "what this does NOT cover," dependency
   ordering, open risks. Don't write vague specs — every prior spec in this session was
   grounded in an actual grep/read pass, not paraphrased from a doc.
5. Do not build everything in the matrix. It's a menu, not a mandate. Pick the items
   that genuinely serve Monday's deadline (Section 2) and the voice/GIR closure
   (Section 1) first; flag the rest as a backlog for the operator to prioritize later.

---

## 4. Suggested Order of Operations

1. Re-verify Section 1a's claims are still true (fresh `grep`s, not trust).
2. Run the full test suite once, read the actual output.
3. Write + build the streaming spec (Section 1b) — the one remaining gap of the
   original 5.
4. Run the 15-iteration hardening loop (Section 1c) against the real running app.
5. Do the Monday-essentials functional review (Section 2) and write the status report.
6. Write improvement specs for whatever Section 2 finds broken, sized to actual need.
7. Only after 1-6, mine the taxonomy/matrix docs (Section 3) for additional
   reinforcing specs, time permitting before Monday.
8. Report back to the operator with a clear status summary — what's verified working,
   what's fixed, what's still open, and what needs their decision (especially anything
   like the "does lesson-planning-per-cohort exist at all" question from Section 2a).

Do not commit. Do not push. Leave the tree for the operator's review.
