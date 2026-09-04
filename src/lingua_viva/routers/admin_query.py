"""Admin lens query routes (U18, 2026-09-03).

Registered via the router plug-in point (routers/__init__.py ROUTER_MODULES).
Contract: never import src.web; runtime modules only. Paths sit under
/api/admin/ so the existing role-gate middleware in src/web.py covers them.

Endpoints:
- GET /api/admin/lens-query/questions            — the declared question list
- GET /api/admin/lens-query/{question_id}        — run one (L1..L12) over the
  student lens STORE through the lens field contract; ARON codes unless
  names=1; extra params: days, min_categories, term, student

Every response carries scored / targets / cannot_tell / empty_reason —
absence is a verdict, never a zero.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/admin")


@router.get("/lens-query/questions")
async def lens_query_questions() -> dict:
    from src.lingua_viva.lens_query import QUESTIONS

    return {"questions": QUESTIONS, "source": "student lens store (SQLite), declared paths only"}


@router.get("/lens-query/{question_id}")
async def lens_query_run(
    question_id: str,
    names: int = 0,
    days: Optional[int] = None,
    min_categories: Optional[int] = None,
    term: Optional[str] = None,
    student: Optional[str] = None,
):
    import asyncio

    from src.education.student_lens import StudentLensStore
    from src.lingua_viva.lens_query import run_question

    overrides = {k: v for k, v in dict(days=days, min_categories=min_categories, term=term, student=student).items()
                 if v is not None}

    def run():
        store = StudentLensStore()
        try:
            return run_question(store, question_id, names=bool(names), **overrides)
        finally:
            store.close()

    try:
        return await asyncio.to_thread(run)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
