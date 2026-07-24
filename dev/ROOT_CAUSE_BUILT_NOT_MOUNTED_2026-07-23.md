# Root-Cause Analysis: Why Built Features Don't Reach the App (Lingua Viva)

**Date**: 2026-07-23
**Status**: REFERENCE — durable, not a build spec. Read this before writing the Definition of
Done section of any spec that adds a new backend capability.
**Author**: Claude, this session
**Trigger**: `AUDIT: Built But Not UI-Mounted (Lingua Viva)` (operator-provided, 2026-07-23)
identified 9 backend capabilities (`LV-BLT-001..009`) that are correctly built, tested, and
served, with no UI control anywhere in the actual app that ever calls them. That audit answers
**what** is disconnected. This document answers **why it keeps happening** — traced by commit,
not by re-reading spec status lines — so future specs can be written in a way that structurally
prevents the next 9.

---

## 1. The question this document answers

Not "what's currently disconnected" — the audit already did that, precisely, by tracing the real
render chain (`desktop/electron/main.ts` → `BACKEND_URL` → FastAPI root route → the exact
`static/index.html` served) rather than trusting spec status.

This document answers: **why does correct, tested, sometimes-hardened-15-times backend code keep
landing with no path for a teacher to ever trigger it — across more than a month of independent
build sessions, by different agents, using different verification methods — and what has to
change so that stops being a thing vigilance has to catch, and becomes a thing that structurally
can't happen silently?**

## 2. Method

Every finding below is traced to its originating commit via `git log -S` / `git blame` against
the actual code (`src/web.py`, `desktop/electron/*.ts`), not against spec files — spec status
lines in this repo are separately known to go stale (the audit's own housekeeping note found 4 of
the newest specs missing from `dev/INDEX.md` entirely). A commit hash and message is cited for
every claim in §3; nothing here is inferred from a docstring alone without checking the actual
history.

## 3. Four root-cause patterns, not one

The 9 findings do not share one cause. They cluster into four, and the fix for each is different.

### Pattern A — Wholesale infrastructure ports (`LV-BLT-004`, `LV-BLT-007`)

**Evidence**: both `/ws` (`websocket_endpoint`) and `/api/stats` trace to `c2a9bf5`, *"feat(engine):
integrate Mission Canvas as governed AI engine"* — the **first commit in this repo's history**
(2026-06-16). Their only consumer anywhere in the codebase is `FALLBACK_HTML`
(`src/web.py:1707`), a break-glass page served **only** if the real `static/index.html` can't be
found on disk (`src/web.py:121`) — verified by reading the fallback's own inline JS, which is a
WebSocket-driven query console + stats readout, i.e. Mission Canvas's internal developer debug
tool.

**What happened**: adopting MC's engine architecture was a wholesale code port (import the whole
module), not a feature-level rebuild (bring over only what a Lingua Viva teacher needs). MC's own
internal dev tooling came along for the ride.

**Why nothing caught it**: this code was never *supposed* to be teacher-facing. The gap isn't
"someone forgot to build a UI" — it's that **no one ever decided** whether this ported dev tool
should become a real feature, get deleted, or stay explicitly internal-only. An undecided status
looks identical, in a `git status`/test-suite sense, to a forgotten task.

### Pattern B — Backend built ahead of a UI that never landed (`LV-BLT-001`, `LV-BLT-002`)

**Evidence**: `provider_connect`/`provider_disconnect` and `POST /api/ingest` trace to the **same**
commit, `32175b2`, *"feat(engine): one-click local app — BYOK provider connect, education
pipeline wiring, doc ingest, PWA polish"*. The provider-connect route's own docstring names the UI
it was built for: a "Gap 5a onboarding screen."

**What happened**: the backend for a named, planned UI screen shipped in the same commit as three
other unrelated capabilities, bundled under one umbrella feature name. The onboarding screen
itself did not ship — in this commit or any later one found by this trace.

**Why nothing caught it**: "Gap 5a" was a real, named commitment at the moment this commit was
written — but nothing tracked it as *open* once the commit closed. A spec's Definition of Done
checks what's IN the diff; nothing in this repo's process checks what a diff's own docstrings
promise is coming *next*.

### Pattern C — Eval-driven builds where "eval green" was mistaken for "reachable" (`LV-BLT-003`, `LV-BLT-008`)

**Evidence**: `TeacherLensBuilder` + `/api/teacher/ingest` + `/api/teacher/holdout` trace to
`028d1b1`, **today's** commit — *"feat(edu): TeacherLensBuilder + generate_with_teacher_lens,
unblock Layer 2/3/4 teacher-lens evals"*. The commit message states its own goal plainly: unblock
eval layers. Not: ship a teacher-usable feature.

**This pattern is not historical — it happened again in this exact session, in my own work.**
`LV-BLT-008` (the Extract+Fill+Verify engine, `src/lingua_viva/extraction_engine.py`) is the same
shape: built and hardened across 15 rounds this session, with a genuinely rigorous eval harness —
and exercised through the actual served page **zero times**, because the spec I wrote for it
never scoped a UI trigger at all. `SPEC_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md`'s own Build
Order explicitly defers the writer (Spec 6/7) and any UI to "a follow-up spec, not this one" — a
real, deliberate scoping decision, correctly documented — but Spec 6/7 was never written this
session, so the deferral quietly became permanent, and the engine landed exactly as unreachable as
`LV-BLT-003`.

**Why nothing caught it**: eval suites and hardening loops are the right tool for verifying
*correctness* — "does this function produce the right answer when I call it" — but that is a
different claim from "can a teacher make this happen by clicking something," and only one of
tonight's several "live-verified" claims actually tested the second one (the doctor.py and
ontology-packaging fixes, both verified by restarting the real installed desktop app and hitting
it as a user would — contrast this with the extraction engine and the teacher-lens builder, both
verified exclusively via direct function/API calls). **"Live-verified" was used tonight to mean
two structurally different things, and nothing forced a distinction between them.**

### Pattern D — Partial-batch wiring (`LV-BLT-005`, `LV-BLT-006`)

**Evidence**: `GET /api/students/{id}/lens-as-of` traces to `4f5e072`, *"feat(web,ui): wire
teacher-lens/RTI API endpoints + Phase 5B surface cards"* — a commit whose own message says it
**wired** endpoints, and it did wire several (the ones the audit confirms are reachable today) —
just not all of the routes introduced in the same batch.

**What happened**: when N related routes are built together and M<N get a UI call site in the
same pass, the remaining N−M routes are byte-for-byte indistinguishable, in the diff, from
"finished" work — same file, same commit, same test coverage shape.

**Why nothing caught it**: nothing in this repo's process asks, per route, "did this one get a UI
call site, and if not, was that on purpose?" A batch commit either wires everything or it doesn't
say which parts it left out.

## 4. The one insight underneath all four patterns

Every pattern above has a different *origin story*, but the same *failure to be caught*: **this
repo has no mechanical check for "does a UI control actually call this route,"** so the only
thing standing between "built" and "reachable" was an individual session remembering to ask the
question — across a month, four different build shapes, and (per Pattern C) even a session that
had *just finished reading an audit about this exact problem*. That last point is the important
one: **this is not a vigilance problem, and treating it as one will not fix it.** A process that
depends on every future session independently remembering to check reachability will fail exactly
as often as this one did, regardless of how carefully any single spec is written.

## 5. The structural fix — make this mechanically enforced, not remembered

This repo already has the right shaped tool for this, half-built: `contracts/UI_CONTRACT.yaml` +
`scripts/check_ui_contract.py` currently hash-locks `static/index.html`/`src/web.py` and forces a
version bump whenever either changes. It answers "did the UI change" — it does not answer "does
every backend route have somewhere to be called from."

**Proposed extension** (not built by this document — this is the spec for whoever builds it
next): a `ROUTE_REACHABILITY` manifest, checked by the same script, that requires every
`@app.get`/`@app.post`/`@app.websocket` route in `src/web.py` to be in exactly one of two lists:

- `reachable_from_ui`: the route string, plus the exact `fetch()`/form-action call-site string
  expected in `static/index.html` — the check fails if that string is ever removed without the
  route also being removed (catches future Pattern D).
- `intentionally_backend_only`: the route string, plus a short reason and (if applicable) the ID
  of the follow-up spec that will make it reachable — CLI-only, debug fallback, or explicitly
  deferred. New routes not in either list fail the check outright — the default is "prove it,"
  not "assume it's fine."

This turns "is this reachable" from a manual audit (expensive, easy to skip, apparently skipped
for a month) into a mechanical gate that runs on every change touching `src/web.py`, the same way
`check_ui_contract.py --bump` already runs today.

## 6. What every future spec must include, starting now — cheap, no tooling required yet

Until §5 is built, this is the zero-cost interim discipline. Every spec proposing a new backend
route must answer, explicitly, in its own text — not left implicit in a docstring the way `LV-BLT-001`'s "Gap 5a" was:

1. **Which exact UI control calls this route, and in which file/line?** If the answer is "none
   yet," that is allowed — but it must be stated as a decision, not discovered later by an audit.
2. **If backend-only for now, what specifically will build the UI, and when?** "A follow-up spec"
   is not an answer — name it, or don't defer it.
3. **"Live-verified" must say which of two things it means**: verified by calling the
   function/route directly (proves correctness), or verified by using the actual served app as a
   teacher would (proves reachability). Tonight's reports used the same phrase for both — that
   ambiguity is precisely what let Pattern C recur inside a single session.
4. **A batch commit that introduces N related routes must state, per route, whether it also
   wired a UI call site.** Silence is not a safe default (Pattern D).

## 7. What this session did right — worth keeping, not just what went wrong

Not every "live-verified" claim tonight was the weak kind. The Doctor desktop-mode fix and the
ontology-packaging fix were both verified by mirroring the fix into the actual installed desktop
app, restarting the real server process, and hitting it exactly as a teacher's app would run —
that is the standard §6.3 is asking every future spec to meet, and it caught real bugs (the grade-
grounding representation mismatch, the CEFR "+" normalization collapse) that a pure eval-harness
pass would not have surfaced. The fix isn't "verify less confidently" — it's "know which kind of
verification you just did, and say so."

## 8. Provenance

Commit trace performed directly against `src/web.py`, `desktop/electron/main.ts`,
`desktop/electron/preload.ts`, and `src/education/teacher_lens_builder.py` via `git log -S` /
`git blame` — not inferred from spec files, which this document's own §1 explicitly declines to
trust as a source given their independently-confirmed staleness. Commits cited: `c2a9bf5`
(2026-06-16), `32175b2` (2026-06-16), `4f5e072` (undated in this trace, precedes today),
`028d1b1` (2026-07-23, today). `FALLBACK_HTML`'s role confirmed by direct read of
`src/web.py:121` and `:1707-1861`, not assumed from its name. Companion:
`AUDIT: Built But Not UI-Mounted (Lingua Viva)` (operator-provided, 2026-07-23) and its sibling
`mission-canvas/dev/AUDIT_BUILT_NOT_FIXED_BY_RELEASE_AUTOMATION_2026-07-23.md`.
