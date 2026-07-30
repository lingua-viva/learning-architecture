# Lingua Viva Build Session Handoff — 2026-07-30

**Session**: overnight build (evening Jul 29 → morning Jul 30)
**Agent**: Claude Opus 4.6 (1M context)
**Builds completed**: 8 (all Lingua Viva)
**Final suite**: 1622 passed, 13 skipped, 0 failed
**Final preflight**: 6/6
**Commit status**: ALL UNCOMMITTED — operator owns the commit window

---

## What I Built, In Order

| # | Build | New tests | Suite at close |
|---|---|---|---|
| 1 | GIR → Voice Delivery Tone | 14 | 1544 |
| 2 | Golden Voice Loop (GW-VOICE-006) | 6 | 1553 |
| 3 | GIR + Voice Hardening Loop (15 scenarios) | harness | 1557 |
| 4 | Still I Rise: Absence + Coverage MVP | 14 | 1575 |
| 5 | Still I Rise: Ops Request Center (Phase 2A) | 11 | 1586 |
| 6 | Still I Rise: Schedule Change Acks (Phase 2B) | 12 | 1601 |
| 7 | Server-Side Auth Role Gate | 17 | 1622 |

Build 3 was a product-reality hardening pass, not a code build — it produced a report, a reusable harness script, and two P2 findings that the other window fixed while I continued.

---

## What I Learned And Why It Mattered

### 1. The GIR scorer was structurally incapable of distinguishing thin answers from strong ones

The spec told me to wire `build_grounding_result()` into the pipeline and resolve voice tone from the score. Straightforward wiring task. But when I ran the hardening loop afterward (Build 3), every single scenario — including "what is the school's lunch policy on rainy days?" — scored GIR 1.0.

The root cause was in `build_grounding_result()` itself: it checked `knowledge_hit = bool(source_citations)`, and the pipeline always populated `source_citations` with at least `["Manuale v1"]` as a default. So `grounded` was always `True`, `unsupported_claims` was always 0, and the score was always 1.0. The GIR scorer was computing the right answer to the wrong question — it was measuring "does any citation exist?" instead of "does a relevant citation exist?"

**Why knowing this mattered**: without the hardening loop, I would have shipped code that worked at the unit-test level but gave teachers false confidence. A confidently-voiced thin answer is the spec's own definition of the worst failure mode. The hardening loop caught what unit tests could not: the wiring was correct but the upstream data contract was broken.

**What I did**: I documented it as F1 (GIR calibration) and F2 (GIR on error text) in the hardening report. The other window fixed both during this session — `build_grounding_result()` now requires lexical relevance before treating ledger records as grounding, and synthesis confidence < 0.1 floors GIR to 0.0. I verified both fixes by re-running golden workflows and the full suite.

### 2. Ollama's OpenAI-compat endpoint becomes unresponsive under burst load

When I ran 15 scenarios through the live app rapidly, the first 3 queries hit Ollama's 20-second timeout, which tripped the circuit breaker (`_ollama_breaker_open`). Every subsequent query got the fast-fail "Ollama appears to be down" message. Meanwhile, Ollama's native `/api/generate` endpoint still responded fine.

**Why knowing this mattered**: it meant the "GIR always 1.0" finding from the HTTP harness was actually two separate bugs stacked — the GIR calibration issue AND the model unavailability issue. The TestClient pass (which bypasses HTTP entirely) showed GIR correctly scoring 0.0 in clean-state conditions, which confirmed the GIR wiring was correct and the problem was upstream data, not the resolver.

**What I did**: I ran two complementary passes — the HTTP harness (proves streaming + routing + TTS work end to end) and the TestClient pass (proves GIR differentiation with controlled state). Together they gave full coverage despite the environment limitation.

### 3. The privacy gate ordering in `/api/voice/tts` is the thing worth pinning

The spec said to prepend `tone_prefix` to text BEFORE `check_publication_safety()` and BEFORE the character limit check. This ordering matters: the prefix is static non-student-data copy, so including it before the safety gate doesn't change the gate's behavior — but if someone later reorders the operations to put the prefix after the gate, a student-data text that gets privacy-refused would lose its hedge on the local-TTS fallback path.

**Why knowing this mattered**: the `speakLocally()` fallback is exactly the path that handles student-data text (the privacy refusal routes it there). If the hedge prefix doesn't survive that path, the lowest-grounding answers about specific students — the ones most likely to be thin — would lose their "take this as a starting point" signal. That's the inverse of what the spec intended.

**What I did**: I explicitly wired the prefix through both the remote-TTS path AND the local-TTS fallback in `speak()`, and added a test confirming the prefix survives the privacy fallback path. The existing TTS privacy gate tests verified the ordering with a test that posts roster-name text with a tone_prefix and confirms the 403 still fires correctly.

### 4. The SlackBot code is structurally ready for multi-workflow extension

When I built the absence/coverage MVP (Build 4), I established a pattern: slash command → modal → `view_submission` → records + card + DM receipt. Builds 5 and 6 (ops request center, schedule acks) followed the exact same pattern with different field sets and different business logic. The code grew linearly, not exponentially.

**Why knowing this mattered**: the spec authors (the other window) were generating specs faster than I could build them, so execution speed was the constraint. Recognizing that the pattern was stable meant I could move to implementation immediately without re-reading the Slack transport or ops record code each time. The existing `_extract_modal_values()` helper worked unchanged across all three workflows.

**What I did**: I kept each workflow's methods grouped under a section comment (`Phase 2A`, `Phase 2B`) so the next agent can find them by searching for the section header rather than reading the full file. I also kept action IDs stable and prefixed by domain (`ops_coverage_*`, `ops_request_*`, `ops_schedule_*`) so they never collide.

### 5. The auth gate belongs in middleware, not in 40 route handlers

The spec listed ~40 routes across three policy groups (teacher+, coordinator+, admin-only). Editing each handler individually would have been error-prone and would have made future route additions easy to forget. The middleware pattern — classify the path, check the role, short-circuit with 401/403 — keeps all policy in one place.

**Why knowing this mattered**: the spec explicitly called out teacher-ID impersonation as the main risk. A per-route implementation could easily miss one route where `teacher_id` is accepted from a query parameter. The middleware catches it at the request level regardless of how individual handlers parse their parameters.

**What I did**: I built one middleware (`_enforce_role_gate`) that classifies routes by path prefix into policy groups, plus `effective_teacher_id()` in `access_roles.py` for the few routes that need to resolve a caller's teacher_id from the payload. The middleware is a no-op when `LV_AUTH_MODE=off`, so the entire existing test suite passes unchanged.

---

## How I Handled The Iterative Improvement Loops

### The 15-iteration hardening pattern

Builds 1 and 2 each got a 15-iteration full-suite hardening loop (30 total). The discipline: run `pytest -q tests/`, if anything fails, diagnose whether it's my change or pre-existing, fix if mine, document if not, then run again. Across 30 iterations:

- **28 clean passes**
- **2 hits of the pre-existing flaky `test_profile_export`** (timing-dependent, passes on retry, not related to any build)
- **1 UI contract hash mismatch** (caused by the other window committing concurrently — I re-bumped and continued)

The hardening loops caught zero regressions from my code — which is the point. The value isn't in finding bugs (the unit tests already did that); it's in proving stability under repeated execution with the full dependency graph loaded.

### The product-reality hardening pass (Build 3)

This was different from the code-level loops. The spec required 15 live-app scenarios across 6 buckets (curriculum, thin-source, student-support, admin, follow-up, stress). I built a reusable harness (`scripts/run_lv_voice_gir_hardening.py`) that:

1. Posts each question to `/api/query/stream`
2. Parses SSE events
3. Probes `/api/voice/tts` with the first sentence + tone_prefix
4. Records JSONL evidence

Then I ran complementary verification passes:
- Privacy gate: confirmed `Marco` (roster name) blocked at TTS with 403
- Streaming: confirmed SSE events include `query_received`, `status`, `answer_sentence`, `result`
- GIR differentiation: confirmed via TestClient that clean-state GIR correctly scores 0.0

The two P2 findings (F1: calibration, F2: error-state) were real product defects that the unit tests couldn't catch. The other window fixed both within the same session.

### Concurrent-window coordination

The other window was building specs, reviewing my code, and making small fixes throughout the session. This created a coordination challenge: files I'd edited were being modified concurrently. I handled this by:

- **Re-reading files before editing** when I got `File has been modified since read` errors
- **Re-bumping UI contract** when the other window's commits changed file hashes (happened twice)
- **Updating tests** that the other window added (e.g., `test_schedule_change_command_not_exposed_until_ack_workflow_is_built` — I updated it when I built that feature)
- **Adding route reachability entries** for routes the other window created (e.g., `/api/query/stream`)

The key insight: treat the other window's changes as constraints, not conflicts. Read the system-reminders showing what changed, incorporate them, and move on.

---

## What's Uncommitted And Why

All 21 dirty files are from this session's builds. They break down as:

**Core implementation (7 files)**:
- `src/lingua_viva/access_roles.py` — NEW: auth role gate module
- `src/education/slack_ops_bot.py` — 3 SIR workflows + 30+ message templates
- `src/education/ops_records.py` — `claimed → open` transition for coordinator rejection
- `src/web.py` — 3 summary endpoints + auth middleware

**Tests (4 files)**:
- `tests/test_sir_ops_request_center.py` — 11 tests
- `tests/test_sir_schedule_acks.py` — 12 tests
- `tests/test_server_side_auth_role_gate.py` — 17 tests
- `tests/test_ui_contract.py` — EXPECTED_VERSION sync

**Contracts (3 files)**:
- `contracts/ROUTE_REACHABILITY.yaml` — 3 backend-only routes + `/api/query/stream`
- `contracts/UI_CONTRACT.yaml` + `.lock` — v78

**Reports + specs (7 files)**: dev/ docs from the other window

**Pre-existing dirty**: `ontology/proposals/CAND-BDD09D9D.yaml`

NOTE: Builds 1-2 (GIR voice tone, golden voice loop) were committed by the other window during this session. The test files and voice_tone.py from those builds are already on `main`.

---

## What The Next Agent Should Know

1. **The GIR calibration fix landed but is conservative.** The lexical relevance guard is deterministic but coarse. A real calibration spec against teacher queries with expected GIR bands is still needed.

2. **The SIR SlackBot is three workflows, not one.** `/absence`, `/ops-request`, and `/schedule-change` share the same patterns but have different business logic. Read the section comments in `slack_ops_bot.py` to navigate.

3. **The auth gate is a middleware, not per-route.** Policy changes go in `_enforce_role_gate` in `web.py`, role definitions in `access_roles.py`. The next slice (roster/co-teacher model) should extend `AccessContext`, not add a second gate.

4. **The other window improved my schedule-ack code after I wrote it.** The current `_resolve_affected_staff_detail()` returns `(targets, unmatched)` — mine only returned targets. The `_handle_schedule_ack` now validates against `SCHEDULE_ACK_STATUSES` and checks roster membership before affected-list membership. Trust the current code, not my original description.

5. **Test count is 1622.** If the next agent sees fewer, something regressed between sessions.

6. **UI contract is at v78.** If the next agent touches `src/web.py` or `static/index.html`, bump and re-lock before running `test_ui_contract.py`.
