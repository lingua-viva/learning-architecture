"""
Server-side role gate for the Lingua Viva web API.

Spec: dev/SPEC_LV_SERVER_SIDE_AUTH_ROLE_GATE_2026-07-30.md

This is NOT production authentication. It is a minimal opt-in scaffold
that enforces server-side role checks when LV_AUTH_MODE=local_header,
while preserving the current local single-user experience when
LV_AUTH_MODE=off (the default).

In local_header mode, identity comes from trusted local headers only:
  X-LV-User-Id, X-LV-Role, X-LV-Teacher-Id, X-LV-Campus.

These headers are NOT secure on their own — they assume a trusted
reverse proxy or local development environment. A future slice will
add real session/OAuth support.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from fastapi.responses import JSONResponse

# Role hierarchy: admin > coordinator > co_teacher > teacher
ROLE_HIERARCHY = {
    "admin": 4,
    "coordinator": 3,
    "co_teacher": 2,
    "teacher": 1,
}
VALID_ROLES = frozenset(ROLE_HIERARCHY.keys())

# Stable JSON errors
RESPONSE_401 = JSONResponse({"error": "authentication_required"}, status_code=401)
RESPONSE_403 = JSONResponse({"error": "forbidden"}, status_code=403)


@dataclass(frozen=True)
class AccessContext:
    """Identity and role extracted from request headers."""
    user_id: str = ""
    role: str = ""
    teacher_id: str = ""
    campus: str = ""

    @property
    def authenticated(self) -> bool:
        return bool(self.user_id and self.role)

    @property
    def role_level(self) -> int:
        return ROLE_HIERARCHY.get(self.role, 0)


def auth_mode() -> str:
    """Return the current auth mode from environment."""
    return os.environ.get("LV_AUTH_MODE", "off").strip().lower()


def access_context_from_request(request) -> AccessContext:
    """Build an AccessContext from request headers.

    In 'off' mode, returns a permissive context (no enforcement).
    In 'local_header' mode, reads X-LV-* headers.
    """
    mode = auth_mode()
    if mode == "off":
        return AccessContext(user_id="local", role="admin", teacher_id="", campus="")
    if mode == "local_header":
        return AccessContext(
            user_id=request.headers.get("X-LV-User-Id", ""),
            role=request.headers.get("X-LV-Role", ""),
            teacher_id=request.headers.get("X-LV-Teacher-Id", ""),
            campus=request.headers.get("X-LV-Campus", ""),
        )
    # Unknown mode — fail closed
    return AccessContext()


def role_allows(actual_role: str, required_roles: set[str]) -> bool:
    """Check if actual_role meets any of the required roles (hierarchy-aware)."""
    actual_level = ROLE_HIERARCHY.get(actual_role, 0)
    return any(actual_level >= ROLE_HIERARCHY.get(r, 999) for r in required_roles)


def require_role(request, allowed_roles: set[str]) -> Optional[JSONResponse]:
    """Guard a route. Returns None if allowed, or a 401/403 JSONResponse.

    In 'off' mode, always returns None (no enforcement).
    """
    if auth_mode() == "off":
        return None
    ctx = access_context_from_request(request)
    if not ctx.authenticated:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    if ctx.role not in VALID_ROLES:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if not role_allows(ctx.role, allowed_roles):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return None


def effective_teacher_id(request, payload_teacher_id: str = "") -> str:
    """Return the effective teacher_id, preventing impersonation.

    In 'off' mode, returns whatever the caller provided.
    In 'local_header' mode, a teacher/co_teacher can only use their own id.
    Coordinator/admin may specify any teacher_id.
    """
    if auth_mode() == "off":
        return payload_teacher_id
    ctx = access_context_from_request(request)
    if ctx.role_level >= ROLE_HIERARCHY["coordinator"]:
        return payload_teacher_id or ctx.teacher_id
    # Teacher/co_teacher: force their own teacher_id. If the trusted
    # context does not carry one, do not fall back to a caller-supplied
    # payload id; that would re-open impersonation in auth mode.
    return ctx.teacher_id


TEACHER_OR_HIGHER = {"teacher", "co_teacher", "coordinator", "admin"}
COORDINATOR_OR_ADMIN = {"coordinator", "admin"}
ADMIN_ONLY = {"admin"}
