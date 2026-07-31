# SPEC: Lingua Viva Server-Side Auth And Role Gate

**Date**: 2026-07-30
**Status**: SHIPPED - committed `2fa5cd9`, tested
**Source matrix**: `dev/LV_IMPROVEMENT_CYCLE_SPEC_IDEA_MATRICES_GROUPED_2026-07-30_2.md`
**Primary surface**: Lingua Viva local web API
**Selection rationale**: Schedule acknowledgements are already present in the working tree. The matrix ranks this as the next highest-leverage slice and calls it a hard blocker before any second real user.

---

## Goal

Add the first real server-side access boundary for Lingua Viva's web API.

The current app has privacy-aware local workflows and some student-lens access helpers, but many web routes still trust client-provided IDs or local defaults. This slice should create a small, testable role gate that can be enabled for pilots without pretending to be a production identity system.

```text
HTTP request -> AccessContext -> route policy -> allowed / 401 / 403
```

Default local single-user behavior must remain unchanged unless auth mode is explicitly enabled.

## Existing Repo Capabilities To Reuse

| Capability | Existing implementation | Use in this build |
|---|---|---|
| Observe-once student access | `src/education/access_control.py` | Treat as a known student-lens limitation; do not replace it in this slice. |
| Local web API | `src/web.py` | Add route-level guards around high-risk endpoints. |
| Student store helpers | `_with_student_store`, `StudentLensStore` | Use only where a route already uses them. |
| Ops records | `src/education/ops_records.py` | Ops summary/setup routes need role classification. |
| Route contracts | `contracts/ROUTE_REACHABILITY.yaml` | Update if route signatures or visibility change. |
| Existing access tests | `tests/test_access_control.py` | Keep observe-once behavior green. Add separate web auth tests. |

## Current Gaps This Spec Closes

1. Sensitive web routes are not consistently protected server-side.
2. Client-supplied `teacher_id` can become the effective authority on some routes.
3. Provider, Drive, export, governance, student-lens, and ops setup routes lack a shared policy layer.
4. There is no opt-in auth mode that tests the app as a multi-user service while preserving local single-user development.

## Auth Mode

Add an environment-controlled mode:

```text
LV_AUTH_MODE=off           # default; current local behavior
LV_AUTH_MODE=local_header  # opt-in test/pilot mode
```

In `off` mode:

- Do not reject existing local requests.
- Ignore auth headers.
- Preserve the current full test suite unless tests explicitly enable `LV_AUTH_MODE`.

In `local_header` mode:

- Build an `AccessContext` from trusted local headers only:
  - `X-LV-User-Id`
  - `X-LV-Role`
  - `X-LV-Teacher-Id`, optional
  - `X-LV-Campus`, optional
- Missing identity returns `401`.
- Present identity with insufficient role returns `403`.
- Unknown roles return `403`.

This is not production authentication. It is a server-side enforcement scaffold that can later sit behind a real session, reverse proxy, or OAuth provider.

## Roles

Define roles centrally, preferably in a new small module such as `src/lingua_viva/access_roles.py`.

Required roles:

- `teacher`
- `co_teacher`
- `coordinator`
- `admin`

Recommended role hierarchy:

```text
admin > coordinator > co_teacher > teacher
```

Treat role comparisons as explicit policy, not string sorting.

## Route Policy For This Slice

Keep the first pass intentionally conservative. Protect only routes where accidental second-user access is high-risk, and do not redesign every endpoint.

### Teacher Or Higher

Require authenticated `teacher`, `co_teacher`, `coordinator`, or `admin` in `local_header` mode:

- `POST /api/observe/capture`
- `POST /api/observe/classify`
- `GET /api/students`
- `GET /api/students/{student_id}/lens`
- `GET /api/students/{student_id}/lens-as-of`
- `POST /api/students/{student_id}/rti/decision`
- `PUT /api/students/{student_id}/rti`
- `POST /api/parents/recommendation`
- `GET /api/profile`
- `GET /api/profile/export`

Where a request supplies `teacher_id`, replace or validate it against `AccessContext.teacher_id` in `local_header` mode. A plain teacher must not impersonate another teacher by changing the payload.

### Coordinator Or Admin

Require `coordinator` or `admin`:

- `GET /api/admin/evidence`
- `GET /api/admin/capacity`
- `GET /api/admin/trends`
- `GET /api/admin/programme`
- `POST /api/governance/observation-export`
- `POST /api/audit-receipts/export`
- `GET /api/ops/request-summary`
- `GET /api/ops/schedule-ack-summary`
- `GET /api/ops/staffing-summary`
- `GET /api/ops/daily` when `teacher_id` is absent or not the caller's teacher id
- `GET /api/ops/records` when `teacher_id` is absent or not the caller's teacher id

### Admin Only

Require `admin`:

- `GET /api/slack/credentials`
- `PUT /api/slack/credentials`
- `DELETE /api/slack/credentials`
- `POST /api/slack/credentials/test`
- `GET /api/ops/setup/catalog`
- `GET /api/ops/setup/bot-spec`
- `PUT /api/ops/setup/bot-spec`
- `GET /api/ops/setup/roster`
- `GET /api/ops/setup/suggestions`
- `POST /api/ops/setup/corpus/run`
- `POST /api/ops/setup/corpus/sentences`
- `POST /api/ops/setup/rules/decide`
- `POST /api/provider/connect`
- `POST /api/provider/disconnect`
- `POST /api/google-drive/auth/start`
- `POST /api/google-drive/auth/disconnect`
- `POST /api/google-drive/list`
- `GET /api/google-drive/folders`
- `POST /api/google-drive/folders`
- `DELETE /api/google-drive/folders/{folder_id}`
- `POST /api/google-drive/import`
- `POST /api/google-drive/upload`

## Out Of Scope

- No cookies.
- No JWT.
- No password system.
- No OAuth login.
- No Slack identity federation.
- No Google Workspace domain verification.
- No admin-managed roster/co-teacher assignment table. That is the next matrix slice: `SPEC_LV_ROSTER_COTEACHER_ACCESS_MODEL_2026-07-30.md`.
- No live production deployment claim.
- No weakening existing privacy, export, or student-name redaction gates.

## Implementation Notes

- Prefer a small dependency/helper in `src/web.py`, for example:

```python
context = access_context_from_request(request)
denied = require_role(context, {"coordinator", "admin"})
if denied:
    return denied
```

- Keep route edits mechanical and visible.
- Return JSON errors with stable status codes:
  - `401`: `{"error": "authentication_required"}`
  - `403`: `{"error": "forbidden"}`
- Never log auth headers or secrets.
- In `local_header` mode, do not allow `payload["teacher_id"]` to override a teacher caller's own `teacher_id`.
- Admin and coordinator callers may query cross-teacher operational summaries.
- If a route needs a `Request` parameter only for the guard, add it without changing the public path.

## Tests

Add focused tests, preferably in `tests/test_server_side_auth_role_gate.py`.

Cover:

1. Default `LV_AUTH_MODE=off` preserves an existing sensitive route without auth headers.
2. `local_header` mode returns `401` when a protected route has no identity.
3. Unknown role returns `403`.
4. Teacher can call a teacher-level route with valid headers.
5. Teacher cannot call an admin-only route.
6. Coordinator can call coordinator-level ops summary.
7. Teacher cannot retrieve all ops records by omitting `teacher_id`.
8. Teacher can retrieve their own ops records.
9. Teacher payload `teacher_id` is overwritten or rejected when it differs from `X-LV-Teacher-Id`.
10. Admin can call provider or Slack credential routes.
11. Existing `tests/test_access_control.py` still passes unchanged.
12. Full route reachability and UI contract tests remain green.

Run:

```bash
pytest -q tests/test_server_side_auth_role_gate.py tests/test_access_control.py tests/test_route_reachability.py tests/test_ui_contract.py
python3 -m src.lingua_viva.cli preflight
pytest -q
```

## Acceptance Criteria

- `LV_AUTH_MODE=off` remains backwards compatible.
- `LV_AUTH_MODE=local_header` enforces `401`/`403` on protected route groups.
- Role policy is centralized and tested.
- High-risk admin/provider/Drive/Slack credential routes are admin-only in auth mode.
- Teacher identity cannot be silently impersonated through payload/query parameters in auth mode.
- Existing observe-once student access tests remain green.
- Full suite and preflight pass.
- Working tree remains uncommitted.
