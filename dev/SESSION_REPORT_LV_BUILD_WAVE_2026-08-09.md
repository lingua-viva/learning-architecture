# LV Build Wave — Session Report (2026-08-09)

Operator mandate: "take the reins and drive this repo all the way to being
usable by teachers tomorrow" — five goals (observation→lens with restricted
abuse routing, information categorization, stakeholder sharing, artifact
creation with progression tracking, daily brief), plus PDFs of real
coursework, Slack connections, lens end-to-end, Perplexity fill-in-the-blanks.

Executed as one wave: W0 (spine) → W1/W2/W3 (three parallel builder agents,
router plug-in isolation) → W4 (integration, run by the conscience window)
→ W5 (ship).

## What shipped, by goal

### Goal 1 — Observation → lens, classified, abuse signs restricted
- `src/lingua_viva/safeguarding.py` (W2): deterministic KCSIE-style severity
  tiers GREEN/AMBER/RED, reviewable indicator constants, ambiguity rounds UP.
  RED items go ONLY to `<state>/safeguarding/restricted.ndjson`
  (coordinator+ visible, `filter_for_role` chokepoint); content-free
  notification outbox (`queued` / `pending_config`).
- **Live-wired (W4, contract v136)**: all three production capture sites —
  voice observe, `POST /api/observe/capture`, Slack bot — now route through
  `capture_with_safeguarding`. RED never enters the lens store; restricted
  responses skip routing memory, Drive sync, and the sources ledger.
  Slack ack `ACK_RESTRICTED` is content-free.
- **Classifier class fix (W4)**: direct disclosures ("his dad hits him at
  home") previously classified GREEN — verb-form + word-gap broadening and a
  household-adult-subject pattern added; class locked by test
  (peer-conflict phrasing stays non-RED).
- `src/lingua_viva/notification_drain.py` (W4): explicit (human-invoked)
  drain of queued notifications through the existing Slack chokepoint;
  `POST /api/safeguarding/drain` (coordinator+). pending_config never sends;
  failures stay queued with `last_error`.

### Goal 2 — Information categorization (per-machine library)
- `src/lingua_viva/library.py` (W1): ingest PDF/md/txt →
  chunk → classify against the 111-node ontology → NDJSON index +
  `library/docs/<id>/`; role tags; sha256 dedup; refuses private-data paths;
  deterministic lexical search by query/category/role.
- CLI: `lv library add|search|status`, `lv research "<q>" [--dry-run]`.
- `src/lingua_viva/perplexity_gateway.py` (W1): fail-closed (needs BOTH
  `PERPLEXITY_API_KEY` and `LV_ALLOW_RESEARCH=1`), teacher-initiated only,
  outbound passes roster scrub → privacy redaction → injection guard →
  sanitizer; results land ONLY in the library (source=perplexity). Pipeline
  RESEARCH stays hard-disabled.
- Routes: `/api/sources/records`, `/api/sources/observations`,
  `/api/library/{status,search,add}`, `/api/library/research`.

### Goal 3 — Stakeholder sharing
- `src/lingua_viva/sharing_matrix.py` (W2): declarative info-type × role
  matrix (full/summary/none); safeguarding = none below coordinator, parents
  never via this system.
- `src/lingua_viva/absence_escalation.py` (W2): NDJSON absence ledger,
  3-consecutive / 5-in-20-school-days thresholds → coordinator escalation
  queue. Routes: `/api/sharing/check`, `/api/absences` (POST teacher+,
  GET coordinator+).

### Goal 4 — Artifact creation + progression
- `src/lingua_viva/pdf_generator.py` (W3): reportlab (new dep, offline
  fonts), lesson / parent-report / coursework-pack renderers.
- `src/lingua_viva/coursework_pack.py` (W3): curriculum-driven packs, 3
  scaffolded activity types × CEFR tiers (ContentDifferentiator), teacher
  pack vs student-safe pack, auto-generated content labeled
  "draft — teacher review required". Output `<state>/artifacts/coursework/`;
  sample G1–G5 packs generated.
- `src/lingua_viva/poi_progression.py` (W3): PYP 6 themes, per-objective
  beginning→developing→consolidating→secure, iteration ledger in
  student_lenses.db, trend (progressing/plateauing/needs_consolidation),
  ranked `consolidate_next`. Nora Rossi + Rafael synthetic worked examples.
- Routes: `/api/artifacts/coursework-pack`, `/api/artifacts/list`,
  `/api/artifacts/download` (W4: traversal-proof, artifacts dir only),
  `/api/poi/progression/{id}`, `/api/poi/record`.

### Goal 5 — Daily brief
- `src/lingua_viva/brief_extensions.py` (W4, contract v135): three new
  fail-soft widgets appended to `/api/daily/briefing` — absence escalations
  (anonymous refs), knowledge-library status, recent coursework artifacts.
  Safeguarding deliberately never read by the brief (store separation,
  verified by test).

### Spine (W0)
- Greenlight exit-code fixes: doctor PRIVATE_RISK now exits 1;
  `lv eval teacher-readiness` gates on non-expected P0/P1 FAILs.
- Harness run history: `TEACHER_READINESS_HISTORY.ndjson` (verified live).
- Router plug-in point (contract v134): `src/lingua_viva/routers/`
  ROUTER_MODULES include loop in web.py — three parallel agents built
  feature routers with zero web.py collisions.

## Verification
- Preflight 6/6 (contract v136).
- Teacher-readiness harness: 16/19 (84.2%) — FAILs are known C8 (qwen2.5:3b
  60s timeout, pre-existing P1) + C9/C10 (red-forever expected_fail). CLI
  now honestly exits nonzero on C8 by design.
- App boot smoke: 160+ routes, briefing renders all 7 widgets.
- Full suite: 2204 passed, 13 skipped, 1 failed (10m16s) — the single
  failure was tests/test_daily_briefing.py's exact widget-list pin, updated
  for the three extension widgets and re-run green (test-only change).
- New tests this wave: ~130 across library/gateway/sources, safeguarding/
  sharing/absences (incl. live-wire + class-lock), pdf/pack/PoI (incl.
  traversal), brief extensions, notification drain.

## Known gaps / follow-ups
1. C8 remains red until the local model latency issue is addressed
   (reasoning.py timeout vs qwen2.5:3b).
2. Library search is lexical (no embeddings) — fine at current corpus size.
3. Sharing matrix not yet consumed by legacy parent-report paths (they have
   their own stripping; unification is a refactor for a calm day).
4. Absence calendar ignores term holidays (escalates more eagerly — safe
   direction).
5. Restricted-ledger review/close workflow (status transitions) not built.
6. PoI has no UI surface yet; coursework activities are deterministic
   scaffolds (no LLM enrichment path).
7. Auto-release PAT gap: tag re-push still manual (v0.2.46 precedent).
