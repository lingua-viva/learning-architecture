# Kiro Prompt — Lingua Viva Failure Modes + Still I Rise Readiness Build

Date: 2026-08-06  
Repo: `/home/mical/learning-architecture`  
Branch state at handoff: `main` is ahead of `origin/main` by 2 local commits:

- `303b7cc feat: build Still I Rise phase 1 fixes`
- `f164359 feat: add SIR traits and absence signal`

## Source Priority

1. `dev/PROMPT_LV_TWO_WEEK_PHASE1_BUILD_2026-08-06.md` wins on disagreement unless the operator explicitly overrides it.
2. This prompt is an execution prompt for Kiro after the 2026-08-06 build work.
3. QA evidence in `qa/` is the basis for failure-mode discovery.
4. Treat older handoffs as useful context, not current truth.

## Read First

Read these files before editing:

- `AGENTS.md`
- `.codex/memories/2026-07-23_letter_to_future_self.md`
- `qa/README.md`
- `qa/2026-08-03_teacher-readiness-claudia.md`
- `qa/2026-08-04_teacher-readiness-claudia.md`
- `qa/2026-08-04_chip-qa-0.2.36-macos-1.md`
- `qa/traces/2026-08-04_0.2.36_macos-1/chip_feedback.md`
- `dev/PROMPT_LV_TWO_WEEK_PHASE1_BUILD_2026-08-06.md`
- `dev/BUILD_PLAN_TWO_WEEK_2026-08-06.md`
- `dev/HANDOFF_KIRO_2026-08-06.md`

Then inspect today’s commits:

```bash
git show --stat 303b7cc
git show --stat f164359
git show --name-only 303b7cc f164359
```

## Core Instruction

Assume the bar is not met anywhere. Your job is not to confirm that the app is fine. Your job is to define as many failure modes as possible, then build against the highest-risk ones until you can build no more.

Do not ask whether to proceed. Execute. If you disagree with a previous handoff, use the source priority above.

## QA-Derived Failure Modes To Expand

Start with these, then add more from your own inspection.

### Voice / Mic / TTS

- Mic visible in backend but not visible in UI.
- Mic visible in UI but captures silence.
- macOS hardened-runtime entitlements missing audio input.
- Browser asks permission but Electron shell cannot actually access the device.
- Voice probe says available while teacher-facing mic is hidden, disabled, or broken.
- Voice probe says unavailable but gives no plain remediation.
- STT dependency exists in dev but not packaged build.
- STT returns empty transcript without diagnosing silence vs no speech vs permission.
- Mic remains locked after error.
- Mic state says listening when no audio is flowing.
- TTS reads English with Italian voice, or Italian with English voice.
- Rime key missing but UI does not explain fallback voice limits.
- Voice action saves wrong student because context memory is stale.
- Voice action writes inferred CEFR/SEL facts not explicitly present.
- Voice action fails without visible recovery path.

### Ask / Grounding / Fabrication

- Ask refuses every student-named question, leaving no local grounded student Q&A surface.
- Ask sends student data externally.
- Ask claims web grounding without citations.
- Ask gives a useful-looking answer with GIR 0 or weak grounding.
- Ask hides GIR warnings in UI or voice.
- Ask says “no model available” when actual issue is provider key, Ollama down, or route refusal.
- Ask uses Perplexity for questions that contain student PII.
- Ask uses stale lens data after import or observation.
- Ask cites Manuale v1 or curriculum without actually retrieving relevant passages.
- Ask answers with generic teacher advice when the teacher asked for student-specific evidence.
- Ask cannot be reached from Prepare/Plan where the teacher naturally needs it.
- Ask is not interruptible in voice.
- Ask answer metadata lies about route, model, duration, or external calls.

### Document Import / Student Ingest

- `.docx` or `.xlsx` extraction works in tests but not packaged app.
- Bulk roster import creates students automatically without review.
- Bulk roster import review UI silently drops rows.
- Undo only partially reverses imported students.
- Unsupported files return HTML/bare 500 instead of JSON error.
- PDF extraction crash still exists in older `/api/ingest` path.
- Large files hang or block the UI.
- Extracted names are wrong but appear authoritative.
- Duplicate student names create duplicate lenses without conflict handling.
- Uploaded documents write raw student data into repo or app bundle.
- Import creates support/ethos claims without teacher confirmation.
- Import mixes roster ingestion and document evidence ingestion.
- Import lacks provenance to the source file and row/page.
- Import does not persist job state across app restart.

### Student Lens / Evidence / Ethos / Categories

- Untyped observations infer CEFR levels, SEL valence, RTI changes, or support categories without basis.
- Teacher-confirmed and model-suggested evidence are visually indistinguishable.
- Personal Context/CPS-sensitive evidence appears in parent/student summaries.
- Sensitive evidence is exported or synced without special review.
- Still I Rise traits exist in taxonomy but are not visible in student profile.
- Trait suggestions write automatically instead of requiring teacher confirmation.
- Trait evidence counts drift from the ledger.
- Soft-deleted evidence still appears in summaries.
- Category labels differ between backend, frontend, reports, and docs.
- Existing local `ethos.yaml` hides the new Still I Rise seed without notice.
- Existing lenses lack the new `personal_context` category after migration.
- Triangulation ignores Personal Context or shows it too broadly.
- Background notes become a dumping ground for sensitive information with no review boundary.
- Strengths, needs, strategies, open questions, and evidence are not clearly separated.

### Student Summaries / Parent-Safe Output

- “Student Summary” still behaves like parent-only messaging in hidden places.
- Summary includes model-suggested claims.
- Summary includes raw observation text that should remain local.
- Summary includes Personal Context or safeguarding data.
- Summary says “source: observations” without listing source observation ids.
- Zero-observation summary sounds confident.
- Summary does not show what was omitted for safety.
- Publication safety gate fires after content is already shown or spoken.
- Teacher cannot edit before sharing.
- The UI says “No AI attribution” but generated text includes AI/process language.

### Slack Ops / Absence Workflow

- `@absence` classifies in tests but is not enabled in the live bot spec.
- `@absence` in an arbitrary channel is ignored without the sender understanding why.
- `@absence` from an unmapped Slack user fabricates an identity.
- Absence records do not show centrally per school/day.
- Central absence list is hidden from the correct coordinator/admin role.
- Central absence list exposes raw private Slack text.
- Absence date defaults incorrectly across time zones.
- `@absence tomorrow` records today.
- Coverage request does not link to the absence.
- Coverage claim state gets stuck after bot restart.
- Partial coverage is treated as full coverage.
- Cancel removes the daily file entry but not the audit record.
- Slack retries create duplicate absence records.
- Slash command `/absence` and typed `@absence` diverge in fields and review rules.
- Slack bot touches student lenses, violating the ops/student-data boundary.

### Google Drive / Sync / Sources

- Two Drive/Sources surfaces confuse users.
- Sync status 500s because dependencies are missing.
- Drive configured state is unclear.
- Drive import/export can happen without a clear “data leaves device” boundary.
- Sources list and Settings link disagree.
- Import from Drive lacks provenance.
- Drive sync writes to wrong school folder.
- CPS/Personal Context folder routing is not restricted by school policy.
- Sync queue failures show global red banners on every page.

### Packaging / Desktop / Install

- Packaged app lacks Python dependencies present in dev.
- Runtime writes `.pyc` into the signed app bundle.
- Entitlements differ from Info.plist claims.
- App passes health locally but fails after DMG install.
- Multiple macOS permission dialogs appear without teacher-readable explanation.
- Health says OK while core teacher workflow is unavailable.
- Local server port conflict silently opens wrong app or stale code.
- UI contract bump hides behavioral breakage.

### UI / Teacher Workflow

- Save confirmation is too subtle, causing double-save.
- Duplicate observations are accepted with no warning.
- Observation type/CEFR fields pressure teachers into invented data.
- “Settings” does not show voice, sync, privacy, keys, and Drive clearly.
- Teacher cannot tell what is local-only vs shareable.
- Teacher cannot see next best action after an observation.
- App surfaces too many admin/utility concepts to a busy teacher.
- Error messages are technically accurate but not actionable.
- Empty states do not say what the teacher can do next.
- Navigation hides the thing a teacher needs in the moment.
- A green badge says connected/ready when the next action will fail.

### Privacy / Governance / Auditability

- External calls occur without ledger evidence.
- Privacy log omits blocked attempts.
- Audit receipts omit source IDs.
- Route reachability says wired but UI path is role-blocked without explanation.
- Raw observation narration leaks into exports.
- Support/ethos evidence loses provenance.
- The app cannot prove a claim came from a teacher-confirmed source.
- Data written by Slack, Drive, and manual entry are not distinguishable.

## Today’s Build Surface To Audit

Audit every file touched by the two 2026-08-06 commits, especially:

- `src/lingua_viva/docpipe/extract.py`
- `src/web.py`
- `static/index.html`
- `src/lingua_viva/config.py`
- `src/education/ethos.py`
- `src/education/student_lens.py`
- `src/education/observation_capture.py`
- `config/ops_packs/absence_coverage.yaml`
- `desktop/electron/bootstrap.ts`
- `contracts/ROUTE_REACHABILITY.yaml`
- `contracts/UI_CONTRACT.yaml`

Today’s new/changed behavior to challenge:

- `.docx` and `.xlsx` extraction.
- Bulk student ingest review gate.
- Bulk undo for student ingest.
- G1-G12 grade validation.
- Saved Perplexity/Rime service keys.
- Still I Rise 2 traits + 7 characteristics seed taxonomy.
- `Personal Context` support category.
- `@absence` Slack trigger.
- Daily Absences panel and staffing-summary absence rows.
- Parents nav renamed to Summaries / Student Summary.

## High-Bar Readiness Matrix

Create or update a worklist from this matrix. Assume no row is done until you personally verify it with code inspection and tests. The right column is the bar, not a suggestion.

| Thing that needs to work | What working looks like |
|---|---|
| Voice mic on macOS packaged app | User sees one clear permission prompt, mic indicator turns on, real classroom speech transcribes, silence is diagnosed, mic releases on success/error/navigation, and packaged entitlements prove audio input is allowed. |
| Voice STT dependency packaging | Fresh installed app reports STT available when dependencies are bundled; if unavailable, teacher gets exact remediation and no fake “listening” state. |
| Voice action routing | Spoken observation, spoken question, and spoken command route correctly; no wrong-student write; ambiguous student asks one question; no inferred CEFR/SEL without explicit evidence. |
| TTS language and privacy | English text uses English voice, Italian uses Italian voice, privacy refusals are spoken clearly, and no student data crosses Rime/browser cloud paths without gate approval. |
| General Ask | Web-backed general teaching questions answer with citations, route/model metadata, failure honesty, and useful setup guidance when Perplexity is missing. |
| Student-specific Ask | Student-named questions are answered only by a local, grounded lens/curriculum path; no external egress; cites exact observation/evidence ids; refuses when evidence is insufficient. |
| Ask grounding display | GIR, citations, route, model, elapsed time, and external-call status are visible and truthful in text and voice. |
| Ask from workflow context | Teacher can ask from Plan/Prepare/Observe/Students without losing current work, and the question inherits only safe context. |
| Document extraction | TXT/PDF/DOCX/XLSX all return JSON, never bare 500; extraction is deterministic, size-limited, and packaged dependencies are verified. |
| Roster import | Large roster requires review; no bulk auto-create; selected names create exactly once; duplicates/conflicts are visible; undo restores pre-import state. |
| Student document import | Student records from files become source/evidence candidates with provenance, not unreviewed facts. |
| Import error handling | Unsupported, corrupt, encrypted, oversized, and empty files produce teacher-readable JSON errors and no partial hidden writes. |
| Source provenance | Every imported field can point back to file, sheet/page/row when possible, import job, timestamp, and reviewer. |
| Student lens integrity | No observation, import, Ask answer, or Slack event can silently mutate CEFR, RTI, support, strengths, or ethos without the required confidence/review path. |
| Untyped observation safety | General observations save as general; no fabricated CEFR/SEL/RTI; suggestions remain suggestions. |
| Observation deduplication | Same teacher, same student, same transcript, near same time creates a warning/idempotent result, not duplicate evidence. |
| Support categories | All categories including Personal Context appear consistently across backend, UI, reports, migration, triangulation, and tests. |
| Personal Context boundary | Sensitive personal/CPS-style information is restricted, clearly labeled, review-gated, excluded from parent/student summaries by default, and never inferred from vague behavior. |
| Still I Rise traits | The 2 traits and 7 characteristics are visible on profile, selectable as evidence, suggested conservatively, reportable only when confirmed, and overrideable per school. |
| Existing ethos override | If local `ethos.yaml` differs from Still I Rise seed, UI explains active taxonomy and does not silently hide expected school categories. |
| Evidence ledger | Evidence is append-only, soft-deletable, source-linked, confidence-tagged, and rollups recompute from ledger truth. |
| Evidence UI | Teacher can add, review, confirm, reject, and remove evidence without confusing model suggestion with confirmed fact. |
| Student Summary surface | Summary is family/student-safe, editable, evidence-grounded, excludes sensitive categories unless explicitly allowed by policy, and never overclaims. |
| Summary citations | Summary exposes source observation/evidence ids for teacher review and never uses generic citation when specific evidence exists. |
| Zero-evidence summaries | Output is honest, short, and refuses to invent strengths/needs/next steps beyond safe generic advice. |
| Publication safety | Safety checks run before share/export/speech, return actionable reasons, and leave audit traces. |
| Lesson materials | Generates level-appropriate materials with no student PII, no placeholders, no unsupported claims, and clear teacher approval requirement. |
| CEFR next steps | Observations can produce teacher-reviewable CEFR young learner next steps/can-do suggestions without inventing level. |
| RTI decisions | Tier recommendations require evidence thresholds, cite source observations, and require teacher confirmation. |
| Triangulation | Multi-teacher differences are visible, anonymous where needed, and never auto-resolved. |
| Daily view | Daily is useful on first open: today’s work, review items, absences, sync health, and next actions, with no student names where inappropriate. |
| Slack setup | Bot setup shows exact missing env/config, enabled packs, roster mapping, corpus status, and safe go-live gate. |
| Slack `@absence` | In allowed Slack surfaces, anyone mapped can post `@absence [date/detail]`; record appears centrally by school/day; retries are idempotent; unmapped users are handled honestly. |
| Slack absence privacy | Central absence panel shows name/date/status/coverage, not raw private Slack text or medical detail. |
| Slack coverage | Absence with coverage creates linked coverage request; claims, partial claims, confirm/reject/cancel survive restart and update daily files. |
| Slack daily files | Per-teacher daily files are local, current, archived by day, and consistent with app Daily view. |
| Ops/student boundary | Slack ops records never create or update student lenses. |
| Drive setup | One coherent Sources/Drive flow exists; Settings points to it clearly; no duplicate confusing panels. |
| Drive import | User selects connected folder/files, sees privacy boundary, imports with provenance, and failures are recoverable. |
| Drive export/sync | Data leaves device only through explicit approval, correct school folder routing, audit receipt, and privacy gate. |
| Sync status | Sync queue never 500s from missing deps; shows per-item status, retry, and exact cause. |
| Service keys | Perplexity/Rime keys save locally, are never echoed, can be tested, cleared, and explained in Settings. |
| First-run setup | New teacher sees missing model/voice/Drive/key states as setup checklist, not random broken features. |
| Settings | Voice, sync, privacy, keys, Drive, teacher identity, and local model status are findable and actionable. |
| Health/Doctor | Health distinguishes dev vs packaged, dependency missing vs config missing, and core workflow unavailable vs optional service unavailable. |
| Packaging dependencies | Desktop bootstrap/packaging includes every runtime dependency used by import, sync, voice, Ask, and validation. |
| macOS signing | Entitlements, notarization, sealed-resource integrity, and no runtime bundle writes are verified by automated QA. |
| Runtime paths | All mutable state writes to `~/.lingua-viva` or approved state paths, never repo, app bundle, or temp bundle paths. |
| Route reachability | Every backend route is either reachable from UI or explicitly backend-only with reason; role-gated optional UI paths do not break teacher pages. |
| UI contract | Contract bumps are meaningful and accompanied by behavior tests; hash updates do not hide regressions. |
| Error UX | Every failed fetch shows a human-readable message in the relevant panel, not a global scary banner unless truly global. |
| Empty states | Every empty state says what to do next and never implies missing data is evidence. |
| Navigation | Teacher primary path is obvious: Daily, Observe, Students, Plan, Prepare, Ask, Summaries; utility/admin concepts do not crowd the teaching flow. |
| Save confirmation | Save/undo/import/share confirmations are visible, timestamped, and do not clear context before teacher sees outcome. |
| Privacy logs | Every blocked or approved external-boundary action logs what happened without storing raw sensitive text. |
| Test data hygiene | QA reports/traces use synthetic students only; no real names or sensitive data are committed. |
| Full regression suite | Full `env -u LV_STATE_HOME -u LV_DESKTOP pytest -q tests/` passes after changes, plus targeted packaged-app checks where relevant. |

## Execution Requirements

1. Build failure-mode inventory first.
   - Add a new markdown artifact under `dev/` with your expanded failure-mode list if it materially improves this prompt.
   - Include source references to `qa/` report lines or trace filenames where possible.

2. Then implement fixes.
   - Prefer high-risk, teacher-blocking, privacy-blocking, or Still I Rise demo-blocking work.
   - Do not stop at a plan if the code can be changed safely.
   - Keep changes scoped and follow existing patterns.

3. Add or update tests.
   - Every fixed failure mode gets a focused regression test.
   - Any UI route change updates `contracts/ROUTE_REACHABILITY.yaml`.
   - Any protected UI change bumps `contracts/UI_CONTRACT.yaml` and lock.

4. Verify.
   - Run focused tests for touched areas.
   - Run full `env -u LV_STATE_HOME -u LV_DESKTOP pytest -q tests/` before committing if time allows.
   - For packaging/macOS issues, add code/config tests even if you cannot re-sign/notarize locally.

5. Commit.
   - Commit only your tracked code/test/contract changes.
   - Leave untracked handoff docs alone unless explicitly asked.

## Initial Priority Suggestions

If you need a starting order, use this:

1. Ask local grounded student Q&A: teacher must be able to ask about Marco/Nora/Still I Rise students without external egress and with source ids.
2. Untyped observation no-invention: ensure no CEFR/SEL/RTI fact appears unless explicitly supplied or teacher confirms.
3. Observation duplicate/idempotency warning.
4. Personal Context safety: exclude from summaries/export by default and add visible restricted-review semantics.
5. Daily absences role/visibility/idempotency: make `@absence` demo robust across auth roles and Slack retries.
6. Settings/first-run readiness: one coherent checklist for Voice, Ask, Drive, Sync, Rime/Perplexity, and local model.
7. Packaged-app hardening: dependencies, entitlements, no bundle writes.

## Non-Negotiables

- Do not fabricate student facts.
- Do not send student data externally.
- Do not mark a row as working because a unit test passes; working means a teacher can use it under the relevant deployment conditions.
- Do not hide setup/config failures behind green badges.
- Do not regress local-only/privacy boundaries to make a demo look better.
- Do not call anything “pushed,” “live,” or “done” unless `AGENTS.md` verification standards are met.
