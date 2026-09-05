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

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/admin")


@router.post("/lens-query/{question_id}/save")
async def save_lens_query(question_id: str, request: Request, payload: dict):
    from src.lingua_viva.access_roles import require_role, effective_teacher_id
    refusal = require_role(request, {'coordinator'})
    if refusal is not None:
        return refusal
    import csv
    import io
    from src.lingua_viva.lens_query import QUESTIONS
    from src.lingua_viva.deliverables.store import save_snapshot
    result = await lens_query_run(question_id, names=0, days=payload.get('days'),
                                 min_categories=payload.get('min_categories'), term=payload.get('term'), student=payload.get('student'))
    if not isinstance(result, dict):
        return result
    title = next((q['q'] for q in QUESTIONS if q['id'] == question_id), 'Lens query')
    rows = []
    def flatten(value, label='Result'):
        if isinstance(value, dict):
            for key, item in value.items():
                flatten(item, label + ' / ' + key.replace('_', ' '))
        elif isinstance(value, list):
            if not value:
                rows.append([label, 'None'])
            for index, item in enumerate(value, 1):
                flatten(item, label + f' {index}')
        else:
            rows.append([label, 'Not recorded' if value is None else str(value)])
    flatten(result)
    stream = io.StringIO(newline=''); writer = csv.writer(stream)
    writer.writerow(['Field', 'Value'])
    for row in rows:
        writer.writerow([("'" + value if value.startswith(('=', '+', '-', '@')) else value) for value in row])
    csv_text = stream.getvalue()
    printable = title + '\n\n' + '\n'.join(f'{label}: {value}' for label, value in rows)
    try:
        saved = save_snapshot('lens_query', title, {'printable_text': printable, 'csv': csv_text, 'result': result},
                              teacher_id=effective_teacher_id(request, 'local-teacher'))
    except OSError:
        return JSONResponse({'error': 'query_not_saved', 'message': 'The answer could not be saved. Check free disk space and retry.'}, status_code=503)
    return {'result': result, 'csv': csv_text, 'saved_deliverable': saved}


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
