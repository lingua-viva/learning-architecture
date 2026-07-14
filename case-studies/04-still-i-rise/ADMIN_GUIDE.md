# Administrator Guide — Lingua Viva / Mission Canvas Education System

**5-minute read.** For school leadership and administrators evaluating this system, not for teachers using it day-to-day.

---

## 1. What This Is

A **governed AI assistant for teachers** — not a chatbot, not a student-facing tool. Teachers ask it things in plain language ("I need to plan a unit on migration," "How do I differentiate this for mixed CEFR levels?") and it routes the request through a fixed set of ~38 known education workflows (unit planning, differentiation, assessment, RTI monitoring, parent communication, etc.), each with its own rules about what data it can touch and where it can send it.

The key design choice: **every request is classified against a fixed rulebook before any AI model sees it.** The AI never decides on its own whether something is sensitive — a lookup table does, and that lookup table is auditable, human-edited YAML, not a black box.

## 2. What It Can Do Today

- Draft unit plans, differentiated activities, and assessment rubrics aligned to IB PYP + CEFR
- Generate weekly plans and substitute-teacher context packs
- Turn a teacher's raw observation note into a structured, evidence-based record
- Draft parent-facing progress summaries in plain language (no jargon, no AI attribution)
- Flag RTI (Response to Intervention) tier escalations from accumulated observation data
- Answer "what should I focus on next week" by combining active alerts, CEFR trajectory, and unobserved students

**Honest scope limits**: no student-facing interface, no real-time assessment auto-grading, no promise of clinical/diagnostic accuracy on RTI flags — those are teacher decision-support signals, not automated determinations. RTI tier decisions and CEFR level assignments are explicitly designed as **teacher decision gates**: the system proposes, the teacher confirms. It never assigns a level or tier unilaterally.

## 3. Where Student Data Lives

- **Local-first.** Anything touching an individual student (`blocks_external: true` in the system's classification rules) is processed and stored on local infrastructure only — it is architecturally blocked from being sent to any external AI provider (Claude, GPT, etc.), not just policy-blocked.
- **3-layer sanitizer.** Before any query is allowed to leave the machine, it passes through: (1) regex PII scrubbing (names, emails, phone, DOB, case numbers), (2) NER-based entity redaction (organization/person/location names in context), (3) an ontology-driven hard block for anything classified as sensitive — the request is refused outright rather than sent redacted, when the classification demands it.
- **No write-back to source systems.** For schools using Toddle (or a similar LMS) as the record of truth, this system reads from Toddle exports — it never writes back to Toddle. There's no path for the assistant to alter an official student record.
- **Every request leaves an audit trail.** Every completed query produces a path record — what was asked, what it was classified as, what fired — so nothing is a black box after the fact.

## 4. Integration Path

- **Toddle**: designed as a read-only export/import integration (student profiles, portfolios, gradebooks, progress reports, attendance flow in; nothing flows back). Toddle's public API is limited, so in practice this starts as a scheduled export ingestion, not a live API sync — that's a known constraint, not a hidden one.
- **Slack or other messaging tools**: **not built yet.** There is no Slack integration in this system today. If your workflow depends on Slack-based delivery (e.g., substitute plans or weekly summaries posted to a channel), that's a scoped follow-on project, not a current capability — flagging this now so it isn't assumed.
- **Everything else** (unit plans, observation capture, parent summaries) works standalone through a command-line or lightweight web interface — it does not require any particular school platform to function.

## 5. What It Requires to Run

- **Local compute**: a machine capable of running a local language model (the reference deployment uses Ollama running an open-weight model on-device) — this is what keeps student-data-touching queries fully offline.
- **Optional external model access**: for non-sensitive queries (general research, curriculum design with no student data attached), the system can optionally route to a hosted model (Claude, GPT, etc.) via API key — entirely optional, and never used for anything the classifier marks as student-sensitive.
- **No proprietary infrastructure lock-in**: the codebase is plain Python, YAML configuration, and local file/Redis-backed storage. A school (or its technical partner) owns the deployment outright; there is no vendor dependency required to keep it running.
- **No internet dependency for core teacher workflows**: offline-first is a design principle, not an aspiration — but see the open risk below.

## 6. What's Still Open (said plainly, not buried)

- Offline-first sync and real-time RTI gating are in tension: if a device doesn't sync for several days, a tier decision could fire on stale data. This is a known, documented architectural risk, not yet mitigated with a timestamp-aware gate — see `architecture/integration-risks.md` for the full analysis.
- Speech-to-text observation capture (if used) has not been validated against a specific school's acoustic environment or language mix — this needs a pre-deployment accuracy test, not an assumption.
- This system has been built and tested against a validated Italian-immersion IB PYP program. Adapting it to a new context (different languages, different curriculum framework, different student population) is real engineering work, not a configuration toggle.

---

*Full technical detail: `PRODUCTION_READINESS_REPORT.md` (repo root) and `BUILD_JOURNAL.md` (this directory) for the complete build and verification history.*
