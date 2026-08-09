# SPEC — Pending Evidence Review Loop (One Piece to Perfect) — 2026-08-08

Status: DRAFT — ready to build
Scope ruling: one UX piece taken all the way to done (operator ruling 2026-08-08,
no whole-system passes). This piece: **model-suggested ethos-trait and strengths
evidence gets a teacher confirm/dismiss path** — closing the loop that today
dead-ends silently.

## The verified gap (all checked against disk 2026-08-08)

The evidence-grade system is honest but one-way. Report bodies only ever include
`REPORT_GRADE_CONFIDENCE = ("teacher_confirmed", "imported_verified")`
(`src/education/student_lens.py:161`). Anything `model_suggested` is filtered
out, fail-closed (comment at ~2764: missing confidence never reaches a report).
Good. But:

- `export_ethos_report(student_id, include_unconfirmed=True)`
  (student_lens.py:2719) builds a `pending_review` payload (~2817-2821:
  academic_strengths / personal_strengths / traits) — and **no web route ever
  passes `include_unconfirmed`** (`grep include_unconfirmed src/web.py` → 0).
  Only `governance.py:443` (signed observation pack) and `activity.py:139` use it.
- **`grep -c "pending_review\|include_unconfirmed" static/index.html` → 0.** The
  teacher never sees what is waiting.
- The ONLY suggestion→evidence-grade path in the whole product is
  `confirm_support_entry` (student_lens.py:1123, route
  `POST /api/students/{student_id}/support-entry/confirm` at src/web.py:~4735,
  docstring: "The only path from suggestion to evidence-grade"). It covers
  support-profile entries ONLY. Ethos-trait evidence and profile strengths have
  **no confirm path at all** — not in the store, not in a route, not in the UI.
- The items are confirmable in principle: both ethos evidence items
  (`_append_ethos_evidence_item`, ~2393) and strength entries
  (`add_profile_strength`, ~2209) carry `"id": uuid4` and `"active": True`.
  There is even a latent in-place upgrade branch for ethos evidence
  (~2337-2353: same `source_observation_id`, `model_suggested` →
  `teacher_confirmed` flips the existing entry) that nothing reachable exercises.
- The pending payload is not actionable even if surfaced: `_pending`
  (student_lens.py:2771-2781) strips the `id` — a client could see pending items
  but never reference them.

Net effect: any model-suggested strength or trait evidence is invisible AND
unconfirmable — a permanent dead letter. The honest filter without the review
loop silently discards the model's contribution and the teacher never knows
there was anything to review.

## What to build

### Phase 1 — actionable pending payload + confirm/dismiss chokepoints (store)

In `src/education/student_lens.py`:

1. `_pending` additionally returns `"id"`, `"evidence_type"`,
   `"source_observation_id"`, `"created_by"` for each item. (Pending traits
   already carry `trait_id` at the group level — keep that shape.)
2. `confirm_profile_strength(student_id, kind, entry_id) -> dict` — mirrors
   `confirm_support_entry` exactly: locate by id in
   `strengths_profile[f"{kind}_strengths"]`, flip `confidence` to
   `"teacher_confirmed"`, bump `profile_version`, ValueError on unknown id/kind.
3. `confirm_ethos_evidence(student_id, trait_id, evidence_id) -> dict` — same
   pattern against `ethos_profile["traits"][trait_id]["evidence"]`. If the
   dual-write ledger row exists for that id (SPEC_LV_EVIDENCE_ETHOS_TRAITS
   dual-write), update its confidence too — profile and ledger must not diverge.
4. `dismiss_*` variants (or a `dismiss=True` flag): set `active = False` on the
   item (both `_report_grade` and `_pending` already filter on
   `item.get("active", True)` — dismissal drops it from BOTH lists). Never
   delete; append-only history preserved.

Locking tests (new module `tests/test_pending_evidence_review.py`):
- model_suggested strength → invisible in report → `confirm_profile_strength` →
  visible in report body; pending list empty.
- Same loop for ethos evidence, asserting the ledger row (if present) also flips.
- dismiss → item leaves pending AND can never reach a report body.
- Unknown id / unknown kind / unknown trait → ValueError, zero writes
  (profile_version unchanged).

### Phase 2 — routes

- `GET /api/students/{student_id}/evidence/pending` — returns the
  `pending_review` shape (via `export_ethos_report(..., include_unconfirmed=True)`
  or the store equivalent), items carrying ids. 404 unknown student.
- `POST /api/students/{student_id}/evidence/confirm` — body
  `{"target": "strength"|"trait", "kind"/"trait_id": ..., "entry_id": ...,
  "action": "confirm"|"dismiss"}` → calls the Phase-1 chokepoints. Unknown
  id/kind/trait → 422 and ZERO writes (locking test). Mirror the
  support-entry/confirm route's teacher-id handling.
- No bulk endpoint. One item per call — same philosophy as tap-to-confirm.

### Phase 3 — UI (Students detail view)

In the student lens view in `static/index.html` (strengths render around
~2948-2955):

- A **"Waiting for your confirmation (N)"** section listing pending strengths
  (grouped academic / personal) and pending trait evidence (grouped by trait
  label), each row: the text, when it was suggested, **Confirm** and **Dismiss**
  buttons.
- House language already exists at src/web.py:2915 — reuse it: "Kept out of
  parent reports until you confirm them."
- Confirm → toast + section refresh + strengths/traits display refresh (the item
  visibly moves from pending to confirmed). Dismiss → toast + row leaves.
- Empty state: "Nothing waiting for review." Section renders only for
  teacher-role views (same visibility rules as the support profile surface).
- F5 rule analog: no auto-confirm, no "confirm all".

### Phase 4 — ceremony + surface lock

- Classify both routes in `contracts/ROUTE_REACHABILITY.yaml`.
- UI contract bump (live version + 1 on the merged tree; bump-log line;
  `EXPECTED_VERSION`; yaml+lock+test one commit).
- Surface-lock test in `tests/test_pending_evidence_review.py` (house grep
  style): index.html consumes `/evidence/pending`, contains
  "Waiting for your confirmation", Confirm/Dismiss controls, the kept-out
  language, and contains NO "confirm all" string.

## Acceptance

1. A model_suggested strength appears in the student's "Waiting for your
   confirmation" section, not in the report body.
2. One tap on Confirm → it appears in the report body (report-grade) and leaves
   pending. One tap on Dismiss → gone from pending, still excluded from reports,
   underlying item preserved with `active: false`.
3. Ethos-trait evidence: same loop.
4. Off-map ids → 422, zero writes.
5. Existing ethos/strengths/support tests untouched and green
   (`tests/test_ethos.py` especially — report-grade filter semantics unchanged).

## Non-goals (off the map)

- Changing what counts as REPORT_GRADE_CONFIDENCE.
- Bulk confirmation, auto-confirmation, confidence scores in the UI.
- Touching the support-profile confirm path (already done) or parent-report
  generation.
- Editing evidence text during confirm — confirm confirms what was suggested;
  editing is a different piece.
