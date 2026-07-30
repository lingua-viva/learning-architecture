# Build Prompt - Lingua Viva Server-Side Auth And Role Gate

You are building the next highest-impact Lingua Viva hardening slice.

Schedule acknowledgements are already present in the working tree, so the next selected item from `dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30_2.md` is:

```text
SPEC_LV_SERVER_SIDE_AUTH_ROLE_GATE_2026-07-30.md
```

This is a blocker before any second real user. Build a minimal server-side route guard, not a full authentication platform.

Read first:

```text
dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30_2.md
dev/SPEC_LV_SERVER_SIDE_AUTH_ROLE_GATE_2026-07-30.md
src/education/access_control.py
tests/test_access_control.py
src/web.py
contracts/ROUTE_REACHABILITY.yaml
contracts/UI_CONTRACT.yaml
```

## Hard Rules

1. **Do not commit.** Leave all changes uncommitted for the operator.
2. **Do not build cookies, JWT, password login, OAuth login, or Slack identity federation.**
3. **Do not replace `src/education/access_control.py` observe-once access in this slice.** It remains a known limitation for the next roster/co-teacher spec.
4. **Do not break local single-user mode.** `LV_AUTH_MODE=off` must be the default and must preserve current behavior.
5. **Do not log secrets or auth headers.**
6. **Do not weaken existing privacy/export/student-name gates.**
7. **Do not broaden Slack or Google Drive permissions.**

## Step 0: Orient And Baseline

Run:

```bash
git status --short --branch --untracked-files=all
pytest -q tests/test_access_control.py tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

The repo may contain uncommitted work from SlackBot, voice, route-contract, or UI-contract builds. Do not revert unrelated changes.

## Step 1: Add Central Role Helpers

Create a small module such as `src/lingua_viva/access_roles.py`.

Implement:

- `AccessContext`
- `auth_mode()`
- `access_context_from_request(request)`
- `role_allows(actual_role, required_roles)`
- `require_role(request_or_context, allowed_roles)`
- a helper to get the effective teacher id in auth mode

Required behavior:

- Default mode is `off`.
- `LV_AUTH_MODE=local_header` reads:
  - `X-LV-User-Id`
  - `X-LV-Role`
  - `X-LV-Teacher-Id`
  - `X-LV-Campus`
- Missing local-header identity on protected routes returns `401`.
- Unknown or insufficient role returns `403`.
- JSON errors are stable:
  - `{"error": "authentication_required"}`
  - `{"error": "forbidden"}`

Keep the hierarchy explicit:

```text
admin > coordinator > co_teacher > teacher
```

## Step 2: Wire Guards Into `src/web.py`

Protect the route groups listed in the spec.

Teacher-or-higher examples:

- observe capture/classify
- student roster/lens/rti decision routes
- parent recommendation
- profile/export

Coordinator-or-admin examples:

- admin evidence/capacity/trends/programme
- governance observation export
- audit receipt export
- ops summary endpoints
- cross-teacher ops daily/records

Admin-only examples:

- Slack credentials
- ops setup/catalog/spec/roster/corpus/rule decision
- provider connect/disconnect
- Google Drive auth/list/folders/import/upload

When adding `Request` parameters to endpoints, keep paths and HTTP methods unchanged.

## Step 3: Close Teacher-ID Impersonation

In `LV_AUTH_MODE=local_header`, a teacher-level caller must not be able to act as another teacher by sending a different `teacher_id`.

Apply this to routes that accept or default a teacher id, including:

- `POST /api/observe/capture`
- `POST /api/parents/recommendation`
- `GET /api/ops/daily`
- `GET /api/ops/records`
- any profile/export route that exposes teacher-owned state

Accept either of these implementation patterns:

- overwrite the payload/query teacher id with `AccessContext.teacher_id` for plain teacher callers, or
- reject mismatched teacher ids with `403`.

Be consistent and test it.

## Step 4: Tests

Add `tests/test_server_side_auth_role_gate.py`.

Use FastAPI `TestClient` or the repo's existing web-test pattern. Use monkeypatching to enable `LV_AUTH_MODE=local_header` only inside specific tests.

Cover:

- auth off preserves an existing sensitive route without headers
- missing identity gets `401`
- unknown role gets `403`
- teacher can call a teacher route
- teacher cannot call admin-only route
- coordinator can call coordinator-level summary
- teacher cannot fetch all ops records by omitting `teacher_id`
- teacher can fetch their own ops records
- mismatched payload/query `teacher_id` cannot impersonate another teacher
- admin can call an admin-only route far enough to pass the role gate
- `tests/test_access_control.py` remains unchanged and green

Avoid network. For provider or Drive admin-route tests, monkeypatch the downstream function or choose an endpoint where validation reaches the guard before external work.

## Step 5: Contracts

If route signatures or route metadata checks change, update:

```text
contracts/ROUTE_REACHABILITY.yaml
contracts/UI_CONTRACT.yaml
contracts/UI_CONTRACT.lock
tests/test_ui_contract.py
```

Do not bump UI contract just because internals changed. Bump only if the existing contract test requires it or visible API contract metadata changed.

## Step 6: Verification

Run focused:

```bash
pytest -q tests/test_server_side_auth_role_gate.py tests/test_access_control.py tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
```

Then run:

```bash
pytest -q
```

Fix any real regressions. If there is an inherited failure, document the exact test and evidence before proceeding.

## Final Report

Report:

- files changed
- protected route groups
- auth mode behavior
- teacher-id impersonation behavior
- focused test result
- preflight result
- full suite result
- any routes intentionally left unprotected and why

Do not claim production authentication. This is the first server-side role gate scaffold.
