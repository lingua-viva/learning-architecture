"""Shared web-surface helpers (P1-ARCH-001 web.py split, 2026-08-22).

Definitions needed by BOTH src/web.py and the feature routers in
src/lingua_viva/routers/ live here, because router modules must NEVER
import src.web (circular import — web.py includes the routers at startup).

Everything in this module was moved verbatim from src/web.py. web.py
re-imports these names so existing ``web.X`` references (tests, monkeypatch
targets like ``web._with_student_store``) keep working unchanged.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import WebSocket

STUDENT_GRADE_LEVELS = tuple(f"G{grade}" for grade in range(1, 13))


class SessionBroadcaster:
    """Manages WebSocket connections and broadcasts app events."""

    def __init__(self):
        self.connections: list[WebSocket] = []
        self.history: list[dict] = []
        self.session_id: Optional[str] = None
        self.governance_context: Optional[str] = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)
        # Send session history to new connection
        for entry in self.history:
            await ws.send_json(entry)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, event: dict):
        self.history.append(event)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_sync(self, event: dict):
        """Synchronous broadcast for use from CLI thread."""
        self.history.append(event)
        # Will be picked up by the event loop in the web thread


broadcaster = SessionBroadcaster()


def _student_db_path() -> Path:
    override = os.environ.get("LV_STUDENT_DB_PATH")
    if override:
        return Path(override)
    from src.lingua_viva.config import lv_home
    return lv_home() / "runtime" / "student_lenses.db"


def _with_student_store(callback):
    from src.education.student_lens import StudentLensStore

    with StudentLensStore(db_path=_student_db_path()) as store:
        return callback(store)


def _decision_deliverable(record: dict, record_type: str, session_id: str = "") -> tuple[dict, dict]:
    if record_type == "cohort_lesson_plan":
        from src.education.cohort_planning import content_hash
    else:
        from src.education.help_artifacts import content_hash
    from src.lingua_viva.audit_receipts.builder import build_receipt
    from src.lingua_viva.deliverables.schema import (
        DeliverableLocation,
        DeliverableRecord,
        compute_deliverable_id,
    )
    from src.lingua_viva.deliverables.store import upsert_deliverable

    record_id = str(record.get("artifact_id") or record.get("portfolio_entry_id") or record.get("plan_id") or uuid.uuid4().hex)
    trace_id = f"{record_type}-{record_id}"
    deliverable_id = compute_deliverable_id(trace_id, "")
    title = str(record.get("title") or record_type.replace("_", " ").title())
    deliverable = DeliverableRecord(
        deliverable_id=deliverable_id,
        session_id=session_id,
        trace_id=trace_id,
        type=record_type,
        title=title,
        status="created",
        location=DeliverableLocation(kind="none"),
        summary="Teacher-approved local learning artifact. Not sent or shared.",
        content_hash=content_hash(record),  # type: ignore[arg-type]
    )
    upsert_deliverable(deliverable)
    receipt = build_receipt(
        scope=record_type,
        session_id=session_id,
        trace_id=trace_id,
        deliverable_id=deliverable_id,
        source_record_ids=[
            str(item)
            for item in (
                record.get("source_observation_ids", [])
                if record_type != "cohort_lesson_plan"
                else [
                    assignment.get("student_id", "")
                    for assignment in record.get("student_assignments", [])
                    if isinstance(assignment, dict)
                ]
            )
            if str(item).strip()
        ],
    )
    return deliverable.as_dict(), receipt.as_dict()
