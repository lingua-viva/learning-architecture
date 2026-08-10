"""Safeguarding / sharing / absences routes (W2 slice, 2026-08-09).

Plug-in router per src/lingua_viva/routers/__init__.py — src/web.py
includes this at startup. NEVER imports src.web.

Role enforcement uses the same header/session mechanism as the web.py
middleware (access_roles.access_context_from_request):
  * LV_AUTH_MODE=off (default local single-user) -> permissive admin
    context, consistent with the rest of the app.
  * LV_AUTH_MODE=local_header -> X-LV-* headers; missing identity is
    401, unknown/insufficient role is 403 (fail closed).
  * Unknown LV_AUTH_MODE -> unauthenticated context -> 401 (fail closed).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.lingua_viva.access_roles import (
    ROLE_HIERARCHY,
    TEACHER_OR_HIGHER,
    access_context_from_request,
    auth_mode,
    require_role,
)

router = APIRouter(prefix="/api")

_COORDINATOR_LEVEL = ROLE_HIERARCHY["coordinator"]


def _coordinator_gate(request: Request) -> JSONResponse | None:
    """Coordinator-or-higher gate that fails closed on unknown roles.

    Unlike require_role(), this is enforced in local_header AND unknown
    modes; only the explicit local single-user mode ("off") passes.
    """
    if auth_mode() == "off":
        return None
    ctx = access_context_from_request(request)
    if not ctx.authenticated:
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    if ctx.role_level < _COORDINATOR_LEVEL:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return None


def _caller_role(request: Request) -> str:
    return access_context_from_request(request).role


@router.get("/safeguarding/restricted")
async def restricted_items(request: Request):
    """Restricted safeguarding ledger — coordinator+ only."""
    from src.lingua_viva.safeguarding import read_restricted

    denied = _coordinator_gate(request)
    if denied is not None:
        return denied
    # Read through the single chokepoint (filter_for_role inside
    # read_restricted) with the caller's actual role — defense in depth
    # even after the gate above.
    role = _caller_role(request) if auth_mode() != "off" else "admin"
    items = read_restricted(role)
    return {"items": items, "count": len(items), "restricted": True}


@router.post("/safeguarding/drain")
async def drain_notifications_route(request: Request):
    """Explicitly deliver queued (content-free) notifications — coordinator+.

    Never runs in the background; a human presses this. pending_config
    entries stay local until safeguarding_channel + SLACK_BOT_TOKEN exist.
    """
    from src.lingua_viva.notification_drain import drain_notifications

    denied = _coordinator_gate(request)
    if denied is not None:
        return denied
    return drain_notifications()


@router.post("/safeguarding/restricted/{entry_id}/status")
async def restricted_status_route(entry_id: str, request: Request):
    """Coordinator review workflow for restricted safeguarding entries."""
    from src.lingua_viva.safeguarding import update_restricted_status

    denied = _coordinator_gate(request)
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — malformed body is a client error
        body = None
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    ctx = access_context_from_request(request)
    reviewed_by = str(body.get("reviewed_by") or ctx.user_id or "local").strip()
    try:
        entry = update_restricted_status(
            entry_id=entry_id,
            status=str(body.get("status") or ""),
            reviewed_by=reviewed_by,
            closed_reason=str(body.get("closed_reason") or ""),
        )
    except KeyError:
        return JSONResponse({"error": "restricted entry not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"updated": True, "entry": entry}


@router.get("/sharing/check")
async def sharing_check(info_type: str = "", role: str = ""):
    """Look up the sharing matrix: what view does this role get?"""
    from src.lingua_viva.sharing_matrix import allowed_view

    if not info_type or not role:
        return JSONResponse(
            {"error": "info_type and role query parameters are required"},
            status_code=400,
        )
    return {
        "info_type": info_type,
        "role": role,
        "allowed": allowed_view(info_type, role),
    }


@router.post("/absences")
async def record_absence_route(request: Request):
    """Record one absence day for a student (teacher and above)."""
    from src.lingua_viva.absence_escalation import record_absence

    denied = require_role(request, TEACHER_OR_HIGHER)
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — malformed body is a client error
        body = None
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    student_id = str(body.get("student_id") or "").strip()
    absence_date = body.get("date")
    if not student_id or not absence_date:
        return JSONResponse(
            {"error": "student_id and date are required"}, status_code=400
        )
    try:
        entry = record_absence(student_id, absence_date)
    except ValueError:
        return JSONResponse(
            {"error": "date must be an ISO date (YYYY-MM-DD)"}, status_code=400
        )
    return {"recorded": True, **entry}


@router.get("/absences")
async def pending_escalations_route(request: Request):
    """Pending attendance escalations — coordinator+ only (they are the
    escalation target and the list aggregates across students)."""
    from src.lingua_viva.absence_escalation import check_escalations

    denied = _coordinator_gate(request)
    if denied is not None:
        return denied
    pending = check_escalations()
    return {"pending_escalations": pending, "count": len(pending)}


@router.get("/absences/calendar")
async def absence_calendar_route(request: Request):
    """Configured attendance holiday calendar — coordinator+ only."""
    from src.lingua_viva.absence_escalation import load_holiday_calendar

    denied = _coordinator_gate(request)
    if denied is not None:
        return denied
    return load_holiday_calendar()
