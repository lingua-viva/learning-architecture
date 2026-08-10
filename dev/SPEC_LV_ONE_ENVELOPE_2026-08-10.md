# SPEC — LV One Envelope (2026-08-10)

Status: DRAFT — awaiting operator review. Start only after the Fail-Closed
Wave (`SPEC_LV_FAIL_CLOSED_WAVE_2026-08-10.md`) is green and pushed.
Priority: E1 = P1, E2 = P1, E3 = P2, E4 = gate.
Origin: reflection synthesis — "contracts before surfaces" + "one chokepoint
per invariant". The C9/C10 honesty work this week had to be implemented
TWICE (native engine + legacy pipeline copy) because two reasoning engines
coexist. This wave makes the honest-degradation envelope a single contract
with a single implementation, and removes the duplicate engine that forced
the DR harness check to exist.

---

## E1 (P1) — One response envelope, one sentinel vocabulary

### Problem
Honest degradation is the product, but its shape is assembled ad hoc at each
emitter: `reason()` in `src/lingua_viva/reasoning.py` (ReasonResult with
error/error_detail), the legacy mirror in `src/pipeline.py:331` (ReasonResult
WITHOUT error fields), `_query_timeout_error()` in `src/web.py`, the
deterministic materials fallback in `lesson_materials.py`, coursework
enrichment degradation in `coursework_pack.py:305`. The sentinel vocabulary
(`none`, `none:blocked_provider`, `none:deterministic_only`, `none:local_only`)
exists only as scattered string literals — nothing stops a new path from
inventing `none-fallback` or omitting `model_used` entirely.

### Build
1. Canonical envelope in ONE place (`src/lingua_viva/reasoning.py` or a new
   small `envelope.py` — builder's choice, one module either way):
   - `MODEL_SENTINELS = ("none", "none:blocked_provider", "none:deterministic_only", "none:local_only")`
     with docstrings stating exactly when each is emitted.
   - One `ReasonResult` dataclass (superset: content, confidence, model_used,
     error, error_detail, plus whatever the native one already carries).
     `src/pipeline.py` imports it; the field-poor local copy is deleted (E2
     finishes the job).
   - Helper(s) for degraded envelopes, e.g.
     `degraded_result(sentinel, message, *, error, error_detail)` — asserts
     sentinel ∈ MODEL_SENTINELS.
2. Every degraded emitter goes through the helpers: reasoning.py chokepoints
   (blocked provider, local-only, deterministic banner), web.py
   `_query_timeout_error()`, lesson_materials deterministic fallback,
   coursework enrichment degradation. `external_calls: 0` asserted only when
   provably local (existing `resolve_provider_model` + `LV_REASON_MODEL`
   logic — keep it, centralize it beside the helper).
3. Vocabulary lock test `tests/test_response_envelope.py`:
   - Enumerates MODEL_SENTINELS and asserts each has at least one emitter
     test exercising it end-to-end.
   - Greps source (`src/`) for `"none:` literals outside the canonical
     module — any hit is a failure (new sentinels must be registered, new
     emitters must import).
   - Asserts every degraded HTTP payload from the covered routes carries
     `model_used` and, when local-only, `external_calls == 0`.
4. Response shapes on the wire DO NOT CHANGE (UI contract stays green). This
   is a consolidation, not a redesign — if a shape must change, stop and
   flag for operator ruling.

### Acceptance
- [ ] One sentinel tuple, one ReasonResult, one degraded-result helper; zero `"none:` literals outside the canonical module (test-locked).
- [ ] All existing honesty tests (`tests/test_model_failure_honesty.py`, C9/C10 harness) pass unmodified or with mechanical-only updates.
- [ ] UI contract + route reachability green; no wire-shape changes.

---

## E2 (P1) — Retire the legacy pipeline.py ReasoningEngine

### Problem
`src/pipeline.py:263` holds a DUPLICATE ReasoningEngine ("kept synchronized"
by hand — its own comment at :277 admits the real web path injects the
native engine). Every invariant fix is made twice (this week: blocked-provider
chokepoint, C9 honesty — both duplicated). The DR harness check (:449 in
teacher_readiness.py) exists solely to police this duplication and carries a
permanent-until-now `expected_fail`. One chokepoint per invariant means one
engine.

### Build
1. Inventory callers of the legacy class: `Pipeline` default at
   `pipeline.py:619-629` (`reasoning or ReasoningEngine()`); check who
   constructs `Pipeline()` without injecting (app.py:21-25 injects the
   native engine; tests may construct bare).
2. Make `src/lingua_viva.reasoning.ReasoningEngine` the ONLY implementation:
   - `pipeline.py` imports the native engine for its default
     (`from src.lingua_viva.reasoning import ReasoningEngine`).
   - Delete the legacy class body (:263-~360) including its mirrored
     `reason()` and `_is_external_model` alias. Preserve any
     resolution-order documentation worth keeping by moving it to the native
     engine's docstring (see the Gap 5a note at :667).
3. Update tests that exercised the legacy copy (e.g.
   `test_pipeline_engine_blocks_unsupported_provider_before_model_call` in
   `tests/test_model_failure_honesty.py`) to assert the pipeline path uses
   the native engine — the invariant they lock (no egress, honest sentinel)
   must survive; the duplicate-specific plumbing goes.
4. **DR check**: with one `def _is_external_model` in the tree, DR passes
   for real. Remove `expected_fail` (+ its ref/until from F2) from DR at
   `teacher_readiness.py:449`. Keep the check itself — it now guards against
   REINTRODUCTION of a second predicate.
5. Sweep: `grep -rn "kept.\?synchronized\|DUPLICATE" src/` — remove or
   update every stale synchronization comment.

### Acceptance
- [ ] Exactly one ReasoningEngine class and one `_is_external_model` definition in `src/` (DR green with no expected_fail).
- [ ] `Pipeline()` constructed bare uses the native engine; blocked-provider and honesty invariants hold on the pipeline path (tests updated, not deleted).
- [ ] Full suite green; harness green with DR as a real passing check.
- [ ] No behavior change on any route (UI contract, golden parses unchanged).

---

## E3 (P2) — Legacy parent-facing emitters through the sharing matrix

### Problem
G5 routed `/api/parents/recommendation` through
`sharing_matrix.filter_payload(..., "parent")` (`src/web.py:6232-6243`), but
older parent-facing paths — `ParentReportGenerator` (`src/web.py:6158`,
`src/education/parent_report.py`) and the PDF render input
(`src/lingua_viva/pdf_generator.py:316`) — still rely on their own bespoke
stripping. One chokepoint per invariant: everything leaving the building for
a parent passes the matrix, even when upstream already redacts
(defense-in-depth, exactly the G5 pattern).

### Build
1. Enumerate every route/artifact whose audience is "parent" (grep
   `parent_report`, `render_parent_report_pdf`, deliverables schema
   `parent_report` kind at `src/lingua_viva/deliverables/schema.py:8`).
2. At each emitter, pass the final payload through
   `filter_payload(payload, "parent")` immediately before serialization/
   render — keeping the legacy response/artifact shape (G5 precedent:
   additive filtering, no shape change).
3. Extend `src/lingua_viva/sharing_matrix.py` field rules only if a legacy
   payload carries fields the matrix does not yet know; any new rule must
   default to DROP for parents (fail closed).
4. Tests: for each converted emitter, a regression test that plants a
   non-parent-safe field (e.g. internal notes, raw severity, teacher-only
   keys) upstream and asserts it does not survive to the parent artifact —
   including through the PDF path (assert on the payload handed to the
   renderer).

### Acceptance
- [ ] Every parent-audience emitter passes `filter_payload(..., "parent")` at the last hop (enumerated in the report with file:line).
- [ ] Planted-field tests prove the matrix catches what bespoke stripping would miss, on every converted path.
- [ ] Response/artifact shapes unchanged; existing parent-report tests green.

---

## E4 — Exit gate

- [ ] `preflight` 6/6; `eval teacher-readiness --json` — all checks green, **0 expected_fail remaining except C11** (which now carries ref+until per F2).
- [ ] Full suite: no regressions vs the post-Fail-Closed-Wave baseline.
- [ ] Live walkthrough on `:8765`: ask-with-no-model (deterministic banner envelope), blocked-provider config refusal, parent report + PDF generation with a planted non-parent-safe field verified absent.
- [ ] Session report `dev/SESSION_REPORT_LV_ONE_ENVELOPE_2026-08-10.md` with the emitter inventory table.
- [ ] Push per Rule 0 (auto-release fires; done = 3 assets 200 + pin commit on origin).
