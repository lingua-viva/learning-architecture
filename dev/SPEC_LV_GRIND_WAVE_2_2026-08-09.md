# SPEC — LV Grind Wave 2: Close Every Gap the 08-09 Wave Left Open

Status: authored 2026-08-09 by the conscience window, for the next build window.
Companion prompt: `dev/PROMPT_LV_GRIND_WAVE_2_2026-08-09.md`
Prior wave record: `dev/SESSION_REPORT_LV_BUILD_WAVE_2026-08-09.md` (read it first — it
defines the 7 gaps this spec turns into build items).

Operator mandate (standing, 08-09): "take the reins and drive this repo all the way to
being usable by teachers tomorrow... just grind until cannot grind anymore. identify
everything and anything that we don't know."

The 08-09 wave shipped all five goals live (desktop-v0.2.47, origin/main 27808a5,
contract v136, suite 2204 pass). This wave's job is different: **finish, harden, and
surface** — no new goal areas. Ship line: every G-item below either DONE or honestly
documented as blocked-on-operator, and at least one full grind loop (G8) run after.

---

## G1 — Restricted-ledger review/close workflow (completes Goal 1)

Today `<state>/safeguarding/restricted.ndjson` is append-only; a coordinator can read
(`read_restricted(role)` in `src/lingua_viva/safeguarding.py`) but never act. Build:

- Status field on restricted entries: `open` → `acknowledged` → `closed` (with
  `closed_reason`, `reviewed_by`, timestamps). NDJSON rewrite pattern already exists in
  `src/lingua_viva/notification_drain.py` (`_read_all`/`_write_all`) — reuse it.
- Routes (router plug-in, `src/lingua_viva/routers/safeguarding.py`, coordinator+ gate):
  `POST /api/safeguarding/restricted/{entry_id}/status`. GET already exists.
- Every transition appended to an audit trail (who/when/what) — transitions must never
  destroy the original entry content.
- Containment invariants unchanged and re-locked by test: content never leaves the
  restricted store; brief/lens/sources never read it; `filter_for_role` chokepoint intact.
- Acceptance: tests for full lifecycle, role denial below coordinator, audit-trail
  immutability; existing safeguarding tests all green.

## G2 — PoI progression UI surface (completes Goal 4)

`PoIProgressionStore` (`src/lingua_viva/poi_progression.py`) has data + worked examples
(Nora Rossi, Rafael) but nothing renders it. Build:

- A per-student progression view in the app UI (web.py is protected/SHA-locked — this
  REQUIRES a UI-contract bump; follow the v134-v136 bump-log pattern in
  `contracts/UI_CONTRACT.yaml` + move `EXPECTED_VERSION` in `tests/test_ui_contract.py`).
- Render: per-unit objective phases (beginning→developing→consolidating→secure), trend,
  ranked `consolidate_next`. Data comes from the existing
  `/api/poi/progression/{id}` route — the UI change is a consumer, not a new API.
- Projection constraint: if the view can appear in a shared/projected surface, follow the
  daily-brief anonymity precedent (`tests/test_daily_briefing.py`); a per-student view
  behind explicit student selection may show the (synthetic) display name.
- Acceptance: UI-mount test in the style of
  `test_daily_view_renders_the_briefing`; contract bump clean (`scripts/check_ui_contract.py`).

## G3 — C8 harness check: root-cause the latency envelope failure

C8 (`src/lingua_viva/teacher_readiness.py`, P1, <120s envelope) fails on qwen2.5:3b with
the 60s reasoning timeout (`LV_REASON_TIMEOUT_SECONDS`, `src/lingua_viva/reasoning.py`).
This is an INVESTIGATION first, fix second:

- Measure, don't guess: reproduce the C8 chain, capture `duration_ms` evidence per step,
  find where the time actually goes (model load? prompt size? socket timeout interplay —
  see the reasoning.py comment about timeout_seconds=1 still taking ~20s).
- Candidate fixes in preference order: prompt-size reduction, keep-alive/warm-up before
  the envelope starts, timeout/budget alignment. Model swap only as last resort and only
  to another already-local model.
- Acceptance: C8 green on a real run (`lv eval teacher-readiness`), harness 17/19+, and
  the fix explained in the run history (`TEACHER_READINESS_HISTORY.ndjson` shows the
  before/after). If genuinely hardware-bound, document with measurements and mark the
  check `expected_fail` honestly — do not loosen the envelope silently.

## G4 — Term-holiday calendar for absence escalation

`src/lingua_viva/absence_escalation.py` counts school days as weekdays only
(`_next_school_day`/`_school_days_back`) — holidays inflate escalations (safe direction,
but noisy). Build:

- Optional calendar file `<state>/calendar/holidays.yaml` (or .json): list of date ranges
  with labels. Absent file = current behavior exactly (no regression).
- Escalation windows skip holiday dates when the file exists. CLI or route to show the
  active calendar (`GET /api/absences/calendar`).
- Acceptance: tests for both modes; a 3-consecutive run spanning a holiday break does NOT
  escalate; existing thresholds unchanged.

## G5 — Sharing matrix consumed by legacy parent-report paths

`src/lingua_viva/sharing_matrix.py` (`allowed_view`/`filter_payload`) is authoritative for
new routes, but legacy parent-report paths still carry their own ad-hoc stripping. Unify:

- Find every legacy path that filters content by audience (start: parent report
  generation, `/api/parents/*`). Route their filtering THROUGH `filter_payload` — one
  chokepoint, per the failure-class rule.
- The legacy behavior is the compatibility bar: no field that was stripped before may
  appear after. Write a differential test proving legacy output ⊆ matrix output per role.
- Safeguarding stays `none` below coordinator and NEVER reaches parent surfaces.

## G6 — Coursework enrichment path (local model, fail-soft)

`src/lingua_viva/coursework_pack.py` activities are deterministic scaffolds. Add an
OPTIONAL local-model enrichment pass:

- Local model only (existing model gate; zero egress unchanged). Deterministic scaffold
  is the always-available fallback — enrichment failure/timeout degrades to current
  output, never blocks pack generation.
- Enriched content keeps the existing "draft — teacher review required" label; enriched
  vs deterministic provenance recorded per activity.
- Student-safe pack rules unchanged (differential test: enrichment can never add content
  to the student pack that the teacher pack lacks).

## G7 — Library search ranking (stretch)

`src/lingua_viva/library.py` search is lexical exact-ish matching. Improve ranking
deterministically (BM25-style term weighting or similar — pure Python, no new heavy deps,
no embeddings/egress). Acceptance: ranking test with a fixture corpus where the better
doc wins; `lv library search` output unchanged in shape.

## G8 — The grind loop (after G1–G7): find what this spec missed

Run the repo's own instruments and fix what they surface, class-by-class:

1. `lv eval teacher-readiness` + preflight + full suite (PIPESTATUS discipline).
2. Wiring audit pass: every module in `src/lingua_viva/` reachable from a route, CLI, or
   pipeline (precedent: 08-08 audit, 131 wired/0 orphaned — keep it at 0 orphaned).
3. UI-mount audit: every user-facing API consumed somewhere in the UI or documented as
   API-only (precedent: `dev/AUDIT_BUILT_NOT_UI_MOUNTED_2026-07-23.md`).
4. Fresh-eyes teacher walkthrough: boot the app, do the five goals as a teacher would,
   log every friction point, fix the fixable, ledger the rest.
Repeat until a full pass surfaces nothing new you can fix. THAT is "cannot grind anymore."

---

## Blocked-on-operator — do NOT burn time here, surface instead

- Safeguarding destinations: `safeguarding_channel` / `restricted_drive_folder` values
  (config surface exists — `safeguarding_config()`; only the operator/Claudia can choose).
- `PERPLEXITY_API_KEY` + `LV_ALLOW_RESEARCH=1` live-fire.
- Auto-release PAT secret (tag re-push stays manual per v0.2.46/47 precedent — execute
  the manual step when shipping, don't try to fix the secret).
Build every code surface up to the config boundary; list these in the closing report.

## Ground rules (non-negotiable)

- AGENTS.md rule 0: PUSH = downloadable at linguaviva.art, verified bytes. Full 7-step
  checklist before claiming done. Expect the PAT-gap manual tag re-push.
- web.py + UI contract are protected: bump via `scripts/check_ui_contract.py --bump`,
  reverse-chronological bump-log comment, move the `EXPECTED_VERSION` pin — group all
  protected-file changes coherently per commit.
- Failure-class fixes: fix the class at the chokepoint + a test that locks the class.
- Publication policy: synthetic names only (Nora Rossi, Marco Bianchi, Rafael); no
  institution/colleague names; nothing identifiable in fixtures or docs.
- Zero egress default; pipeline RESEARCH stays hard-disabled; all state under
  LV_STATE_HOME; tests monkeypatch to tmp_path.
- Measurement: `cmd | tail` + `$?` lies — use PIPESTATUS. Background gates are alive only
  if output grows.

## Definition of done

1. G1–G6 shipped with tests (G7 stretch), G8 loop run to exhaustion.
2. Full suite green, preflight 6/6, harness ≥17/19 with C8 resolved or honestly ledgered.
3. Shipped per rule 0: pushed, released, live-verified download.
4. Closing report `dev/SESSION_REPORT_LV_GRIND_WAVE_2_<date>.md`: per-item outcome,
   new gaps found by G8, the blocked-on-operator list with exact config keys needed.
