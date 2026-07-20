# Handoff: Lingua Viva / Still I Rise — 2026-07-20

**Purpose**: orientation doc for picking this repo back up in a fresh window. Read this before re-reading specs — it tells you what's real, what's stubbed, and what to fix first.

**As of**: commit `a05313b` on `main`, pushed, plus uncommitted handoff/fix work in this window.

---

## 1. What this repo actually is

Two things live in one repo, and their naming history is confusing — read this first:

- **The portfolio layer** (`case-studies/`, `methods/`, `skills/`, `resume-cv/`) — Claudia Canu Fautré's public professional portfolio. Case study 03 (`case-studies/03-lingua-viva/`) is the *design* for an Italian K-5 curriculum at her own school. Case study 04 (`case-studies/04-still-i-rise/`) is a **separate, still-prospective** engagement — free IB education for refugee/vulnerable children across 4 countries, status as of the file itself: "Initial discovery, June 19 2026 meeting, if aligned → Phase 1." It has NOT progressed since — treat it as a dormant pitch, not shipped work.
- **The runtime app** (`src/lingua_viva/`, `src/education/`, `static/`, `desktop/`) — a real local-first FastAPI + vanilla-JS + Electron app. It was originally built and branded for the Still I Rise engagement (binary `sir`, `~/.still-i-rise/`, port variants), then **rebranded to "Lingua Viva"** in a 2026-07-18 sweep (binary `lv`, `~/.lingua-viva/`, port 8787) to serve Claudia's own Italian program instead. **They are the same codebase.** "Still I Rise" now only survives as (a) the dormant case-study/pitch content and (b) residual naming in a few not-yet-swept corners (installer comments, `mc.spec`→`lv.spec` history). If you're asked to "work on the Still I Rise app," you're working on this same runtime.

v1.0.0 shipped 2026-07-14 (3-platform binaries on GitHub Releases). Everything described below is what's landed since.

---

## 2. How to orient fast in a new session

```bash
cd ~/learning-architecture
git log --oneline -5                              # confirm you're where this doc says
python3 -m pytest tests/ -q                        # full suite (~90s, 437 tests)
python3 -m src.lingua_viva.cli health --full --json  # doctor + pytest + gauntlet + golden eval + 5xx check
python3 -m src.lingua_viva.cli preflight             # <1s structural gate (UI contract, imports, ontology/MANIFEST parity)
scripts/gate3_sweep.sh 15                            # 15x non-mutating endpoint sweep
npm run build --prefix desktop                       # Electron rebuild
```

Read `dev/INDEX.md` for the authoritative spec-status table before trusting any individual spec file's own header — statuses have gone stale inside spec files before (that's exactly why `dev/INDEX.md` exists).

---

## 3. Current state (verified today, 2026-07-20)

- **454 tests total (437 app + 15 doctor + 2 doctor-hardening branch cases): all passing** after the follow-up sanitizer client fix in this window. The original handoff pass found `tests/test_sanitizer_client.py::test_fail_closed_production_mode` red; `sanitizer/client.py` now resolves `LV_SANITIZER_URL` lazily so the production fail-closed path honors per-test env overrides.
- **`python3 -m doctor.support_loop doctor` → WARN**, not BLOCKED. Fixed in the Doctor sweep: `EXPECTED_BRANCH = "LINGUA-VIVA-UPDATE"` was a hard-coded single-branch gate left over from feature-branch work; Doctor now accepts either `main` or `LINGUA-VIVA-UPDATE` (`EXPECTED_BRANCHES` in `doctor/support_loop/doctor.py`). Remaining WARN after commit: expected private `.docx` source exclusions are present and intentionally not read. See `dev/REPORT_DOCTOR_SWEEP_2026-07-20.md`.
- Ontology: 111 nodes / 25 domains. Knowledge: 178 entries / 559 citations. (MANIFEST.yaml, doc counts pinned by `tests/test_doc_counts.py`.)
- Desktop: version 0.2.0, AppImage built locally (not committed — gitignored, not a release).
- Latest local commits after this note cover this handoff/index, the sanitizer client fix, and the Doctor branch-gate sweep.

---

## 4. Full spec inventory

Source of truth: `dev/INDEX.md` (18 specs + 3 reports as of this doc). Summary:

| Status | Count | Specs |
|---|---|---|
| **SHIPPED** | 9 | MC_LESSONS sweep, FULL_ARCHITECTURE_SWEEP, PHASE6_TRUST_UI, PHASE5_FILE_MAP, PHASE4_ONBOARDING_UX, MC_BACKEND_MIGRATION (partial), LINGUA_VIVA_APP_COMPLETE_BUILD, ADDENDUM_THREE_TIER_SIDEBAR, LV_PHASE_1_3_HARDENING, LV_SUPPORT_LOOP_MVP_HARDENING |
| **DRAFT / proposed, unbuilt** | 6 | LOCAL_SUPPORT_LOOP, DOCTOR_PHASE_B_SUPPORT_BUNDLE, APP_UNIFIED_BUILD, ACCOUNTABLE_CURRICULUM_SYSTEM, MC_TRANSFER_APPENDIX, MC_TRANSFER_FULL_TABLE |
| **TRIAGE** | 1 | LV_PUBLICATION_READINESS_AUDIT — audit complete, package explicitly **not publication-ready** (see §5.6) |

Two 2026-07-18 reports (`REPORT_ARCHITECTURE_SWEEP`, `REPORT_FINAL_POLISH`) and the 2026-07-19 MC-lessons report are the three "close-out" documents — read those for line-item detail on any individual fix mentioned below.

**Note on the ADDENDUM_THREE_TIER_SIDEBAR spec specifically**: it's marked SHIPPED in the index, but it shipped *partially*. Its own API table proposed endpoints that were never built — see §5.2. Nobody has gone back to either build the rest or formally descope it in the spec itself. That's a real gap, not just a documentation nit.

---

## 5. Three-tier breakdown — what's built, what isn't

The app has three designed user tiers (`dev/specs/ADDENDUM_THREE_TIER_SIDEBAR_2026-07-16.md`). Role is a client-side toggle in `static/index.html` (`data-role="teacher"` / `data-role="coordinator"`) — **there is no auth, no login, no server-side role enforcement.** Anyone with the app open can flip roles in the DOM.

### 5.1 Teacher tier — mostly real, some gaps

Sidebar (built, matches spec): Plan · Prepare · Observe · Students · Assess · Ask · Parents, + utility bar Health · Privacy · Settings · Reflect.

**Built and real** (backed by working endpoints in `src/web.py`):
- `GET /api/curriculum/overview`, `/grade/{grade}`, `/unit/{unit_id}` — curriculum navigation
- `POST /api/prepare/activity` — 3-level activity generation
- `POST /api/observe/capture` — the "killer feature," <30s speech-to-text-style capture, tagged to a student, feeds the student lens
- `GET /api/students`, `/api/students/unobserved`, `/api/students/{id}/lens` — roster + per-student lens viewer
- `GET /api/assess/rubric/{unit_id}` — rubric view
- `POST /api/parents/recommendation` — AI-opaque parent message drafts (governance-isolated, no AI attribution reaches output)
- `POST /api/reflect/note` — private end-of-day journal, full accountability schema
- `POST /api/query` (Ask, free-form fallback) — governed through `EntryGate.scan()`
- Trust/transparency surfaces: `/api/why`, `/api/privacy`, `/api/profile` (+ `/export`, `/clear`), `/api/filemap/*`
- `sanitizer/app.py`-mediated PII redaction on the way in; `src/lingua_viva/privacy.py` runtime redaction; NDJSON audit trail

**Specified but never built** (from the addendum's own API table, still open):
- `POST /api/prepare/help-artifact` — per-student checklist+timer generator (UC3 in the spec)
- `POST /api/students/{id}/rti` — RTI tier confirm/defer decision gate ("system proposes, teacher confirms" — the actual decision-gate pattern the spec calls a core design principle is **not wired up**; the lens shows the proposed tier but there's no endpoint to act on it)
- `GET /api/students/grouping/{unit_id}` — suggested groupings by conflict-awareness (UC5)
- `POST /api/assess/portfolio-entry` — portfolio entry write path
- `GET /api/assess/gaps/{student_id}` — "what's next for this student" gap detection

So: capture → lens is real and is the strongest part of the product. The *decision* half of the loop (RTI tier changes, grouping, portfolio writes, gap-driven next-steps) is view-only or entirely absent.

### 5.2 Admin / Coordinator tier — mostly hollow

Sidebar (built): Programme · Evidence · Capacity · Trends, + same utility bar.

- `GET /api/admin/programme` — **real**, delegates to `CurriculumService().get_overview` (`src/web.py:782`)
- `GET /api/admin/evidence`, `/api/admin/capacity`, `/api/admin/trends` — **all three are literal stubs**:
  ```python
  # DEFERRED: requires accumulated, consent-aware teacher evidence data.
  # Date: 2026-07-18. Owner: LV Phase 7 admin dashboard.
  return {"status": "not_yet_implemented"}
  ```
  This is documented and tested (`tests/test_stub_audit_sweep.py::test_admin_deferred_endpoints_are_explicit_placeholders`), so it's an honest stub, not a hidden gap — but it means **3 of 4 admin sidebar items render a placeholder, not a feature.** The backing logic partially exists elsewhere and is unwired: `src/education/trend_analysis.py` and `src/education/weekly_recommendation.py` exist but nothing calls them from `/api/admin/trends`.

### 5.3 Student tier — does not exist

The addendum spec explicitly designed a student surface (My Tasks / Practice / Portfolio) and explicitly deferred it: *"Student surface is NOT built now... Phase 4+ after teacher adoption is proven."* That decision has never been revisited. There is:
- No student login, no student role, no student-facing view in `static/index.html`
- No student-facing API endpoint anywhere
- Students only ever appear as data *about* them (observations, lenses) captured *by* teachers — they have zero direct interaction with the system

If "build out the student tier" is ever the ask, it's a from-scratch build, not a gap-fill — there is no scaffolding to extend.

### 5.4 Cross-teacher access control — documented as a bootstrap, not production-ready

`src/education/access_control.py`: a teacher is authorized to view a student's lens **iff they have personally recorded at least one observation for that student.** There is no admin-managed roster/co-teacher table. The module's own docstring flags this: a newly-assigned co-teacher who hasn't observed the student yet gets zero access on day one, which is wrong for real school onboarding. Fine for a single-teacher pilot; not fine the moment a second real teacher account exists.

### 5.5 Governance gates — asymmetric

- `EntryGate.scan()` (§ input) is real: detects and redacts private runtime data, blocks external routing.
- `ExitGate` and `IntegrityGate` are **permanent documented no-ops**, deferred to "the native LV pipeline replacement" (no date attached, no owner beyond that phrase). `GatewayInterface.needs_external()` intentionally always returns false, so exit-scanning currently has nothing to scan — but if external routing is ever turned on, there is no exit gate ready to catch it.

### 5.6 Publication readiness — explicitly not ready

`dev/specs/LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md` (status: TRIAGE, Phase 0 only) already did the hard part of this analysis. Its conclusion stands unchanged: the portfolio layer (README claims, the `.docx` manual, CEFR/reference PDFs) overclaims uniqueness, transferability, and outcomes; several references have unverified redistribution rights; the `.docx` remains the sole authoritative source and hasn't been formally promoted past it. Minimum fix list is already written in that audit — it just hasn't been executed (Phase 1+ never started).

---

## 6. Biggest weaknesses, ranked

1. **No auth / no server-side role enforcement.** Role is a client-side DOM toggle. Anyone can become "coordinator" by clicking a different onboarding button. Not a concern for a single-teacher pilot; a hard blocker for any multi-user deployment.
2. **Admin tier is 75% placeholder.** 3 of 4 sidebar items return `not_yet_implemented`. The tier looks built in the UI but isn't.
3. **The teacher-tier decision half of the flywheel is missing.** Observation capture works; RTI confirm/defer, grouping, portfolio writes, and gap-detection endpoints specified in the addendum were never built. The system can *observe and propose* but a teacher currently cannot *act* on a proposal through the app — the addendum's own headline design principle ("system proposes, teacher confirms") isn't wired end-to-end.
4. **A second instance of the exact hermeticity bug MC-lessons §1 was built to close, found live today and fixed in this follow-up:** `sanitizer/client.py` kept `SANITIZER_URL = os.getenv("LV_SANITIZER_URL", "http://localhost:6100")` as a module-level import-time value, so `tests/conftest.py`'s per-test env override never reached it. The fix adds call-time URL resolution for `/health` and `/sanitize/fast`. The failure was real, not flaky, and is useful evidence that the "convert module constants to lazy functions" sweep in MC-lessons §1 wasn't repo-wide.
5. ~~Doctor's branch-name gate blocked on `main`.~~ **Fixed in the Doctor sweep** — `EXPECTED_BRANCHES` now accepts `main` alongside `LINGUA-VIVA-UPDATE` in `doctor/support_loop/doctor.py`. Left in the list as history/context; not a live weakness anymore.
6. **Access control is a single-teacher bootstrap, not a roster system.** Fine today; breaks the moment a second teacher account is real (see §5.4).
7. **Exit/integrity governance is a permanent no-op with no committed replacement date.** Currently safe only because external routing is hard-disabled elsewhere — that's a single point of failure if that assumption ever changes without someone remembering to build the exit gate first.
8. **Publication layer is explicitly not publication-ready** and the audit that says so (§5.6) has sat at Phase 0 since 2026-07-16 with no Phase 1 follow-through.
9. **Learned-weights / recursive-improvement is inert.** `ontology/learned_weights.yaml` was deliberately zeroed during the final-polish pass because golden-eval accuracy was unchanged with or without it (36/36 both ways) — meaning the self-tuning mechanism that's a real differentiator in the sibling Mission Canvas project isn't doing anything load-bearing in LV yet.
10. **No student-facing surface at all** (§5.3) — the full observe→lens→differentiate→re-observe loop currently depends entirely on the teacher; nothing closes it from the student side, which limits how much the system can actually learn about whether an intervention worked.

---

## 7. Where to focus next (suggested order)

1. **Decide the fate of the addendum's unbuilt teacher endpoints** (§5.1) — either build `/rti`, `/grouping`, `/portfolio-entry`, `/assess/gaps`, and `/help-artifact`, or formally descope them in the spec/`dev/INDEX.md` so the SHIPPED status stops overclaiming. Right now the spec says shipped and the code says partial.
2. **Same call for the admin tier** (§5.2) — either build evidence/capacity/trends for real (they need "accumulated, consent-aware teacher evidence data" per the code comments — i.e., they need enough real usage first) or explicitly message the coordinator sidebar as "coming after adoption" rather than a silent placeholder.
3. **Auth/roles, before any second real user.** Even a minimal server-side role check would close weakness #1.
4. **Roster model for access control** (§5.4) — replace "must have observed once" with an admin-grantable roster before a second teacher account is real.
5. **Publication-readiness Phase 1**, if any of this portfolio content is going public soon — the audit already tells you exactly what to fix.
6. **Student tier** — only after a genuine adoption signal from tier 1-2 usage, per the addendum's own reasoning. Don't build ahead of that signal.

---

## 8. Quick file map

| What | Where |
|---|---|
| Spec status source of truth | `dev/INDEX.md` |
| This handoff | `dev/HANDOFF_LINGUA_VIVA_2026-07-20.md` |
| Runtime app (FastAPI) | `src/web.py` (all routes), `src/lingua_viva/` (native runtime: config, privacy, reasoning, traces, CLI) |
| Teacher-facing product logic | `src/education/` (student_lens, observation_capture, content_differentiator, teacher_guide, access_control, parent_report, trend_analysis, weekly_recommendation) |
| Frontend | `static/index.html` (single-page app), `static/sw.js` (PWA/offline + client-side PII defense-in-depth) |
| Sanitizer (2 layers) | `sanitizer/app.py` (unified service), `sanitizer/client.py` (HTTP client + fail-closed fallback — §6.4 bug fixed after this handoff was first written) |
| Ontology / knowledge | `ontology/` (111 nodes/25 domains), `knowledge/` (178 entries/559 citations) |
| Doctor / health | `doctor/support_loop/`, `python3 -m doctor.support_loop doctor` |
| Desktop shell | `desktop/` (Electron, v0.2.0) |
| Tests | `tests/` (437), `tests/conftest.py` (hermeticity fixture — the pattern §6.4 needs applied to `sanitizer/client.py` too) |
| Publication policy / audit | `publication-policy.md`, `dev/specs/LV_PUBLICATION_READINESS_AUDIT_2026-07-16.md` |
| Case studies (portfolio) | `case-studies/01` through `04` — `04-still-i-rise` is the dormant refugee-education pitch, not the live app |

---

## 9. Closing note

The strongest part of the system right now is the teacher-tier capture-to-lens pipeline plus the trust/privacy surfaces (`/api/why`, `/api/privacy`, `/api/profile/export`, request-outcome logging) — those are genuinely built, tested, and governed end-to-end. The weakest part is everything downstream of a proposal: the app is good at observing and surfacing information, and much thinner on letting a teacher or coordinator act on what it surfaces. That's the throughline across almost every item in §6.
