"""Routing Memory — append-only log of routing decisions + teacher corrections.

SPEC_LV_ROUTING_MEMORY_LOOP_2026-08-01. LV's routers (voice intent,
student detection, category suggestion) are deterministic signal lists.
This module records what they decided and when a teacher disagreed —
collection and reporting ONLY. Nothing here is read at inference time;
no threshold or signal list ever changes because of this file.

Inherited constraints (non-negotiable, from the spec):
  * Passive below threshold — v1 never adjusts weights; `lv audit` /
    `lv distill` turn the memory into proposals a HUMAN approves.
  * Content-free — signal-list keys and ids only. Never transcripts,
    never names, never free text. ALLOWED_KEYS is enforced defensively
    on every write and by a key-set test.
  * Append-only — corrections are new rows referencing decision_id;
    no row is ever rewritten. Every row carries schema "lv_route_mem_v1";
    unknown-schema rows are skipped WITH a count on read.
  * Fire-and-forget — a full disk or read-only path must never surface
    in a teacher-facing response (same swallow-and-log posture as the
    privacy log's callers).
  * Safety gates are outside the loop — check_publication_safety, the
    TTS privacy gate, exit gates, and the never-guess clarification rule
    emit nothing here, by design.

Paths resolve lazily per call (module-constant paths broke hermeticity
twice before in this repo — sanitizer/client.py, 2026-07-20).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

SCHEMA = "lv_route_mem_v1"

# The three routing decision types this memory covers. Safety gates are
# deliberately NOT representable here.
DECISION_TYPES = frozenset({"intent", "student_detect", "category_suggest"})

# Exact top-level key set for every row. record_* strips anything else
# defensively; the key-set test asserts no content field can ride along.
ALLOWED_KEYS = frozenset({
    "ts", "schema", "decision_id", "trace_id", "decision",
    "outcome", "confidence", "signals_matched", "subject_ref", "corrected",
})

# subject_ref carries ids only — never a display name or text.
SUBJECT_REF_KEYS = frozenset({"observation_id", "student_id"})

# corrected payload vocabulary: enums, ids, and a positive/negative flag.
CORRECTED_KEYS = frozenset({
    "type",         # decision type being corrected (DECISION_TYPES)
    "to",           # the teacher's value (enum/id: intent name, category_id)
    "source",       # which hook fired (enum: e.g. "support_entry_confirm")
    "positive",     # True = confirmation (suggestion was right)
    "student_id",   # detection corrections: the teacher's student (id only)
    "category_id",  # category corrections/confirmations (id only)
})


def routing_memory_path() -> Path:
    return Path(os.environ.get(
        "LV_ROUTING_MEMORY_PATH",
        str(REPO_ROOT / "memory" / "data" / "routing_memory_v1.ndjson")))


def _append(row: dict) -> bool:
    """Append one row, swallowing every failure (fire-and-forget).

    Returns whether the write landed — callers may ignore it; no caller
    on a teacher-facing path is allowed to surface a failure.
    """
    try:
        path = routing_memory_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")
        return True
    except Exception:
        logger.warning("routing memory append failed (ignored)", exc_info=True)
        return False


def record_decision(
    decision: str,
    outcome: str,
    confidence: float,
    signals_matched: list[str] | None = None,
    subject_ref: dict | None = None,
    trace_id: str = "",
) -> str:
    """Record one routing decision; returns its decision_id.

    The id is returned even when the append fails — a dangling correction
    is harmless, while raising here would break a teacher-facing response.
    """
    decision_id = uuid.uuid4().hex
    try:
        confidence_f = round(float(confidence), 4)
    except (TypeError, ValueError):
        confidence_f = 0.0
    row = {
        "ts": time.time(),
        "schema": SCHEMA,
        "decision_id": decision_id,
        "trace_id": str(trace_id or ""),
        "decision": str(decision),
        "outcome": str(outcome),
        "confidence": confidence_f,
        "signals_matched": [str(s) for s in (signals_matched or [])],
        "subject_ref": {
            k: str(v)
            for k, v in (subject_ref or {}).items()
            if k in SUBJECT_REF_KEYS and v
        },
        "corrected": None,
    }
    _append({k: v for k, v in row.items() if k in ALLOWED_KEYS})
    return decision_id


def record_correction(decision_id: str, corrected: dict) -> None:
    """Append a correction row referencing an earlier decision.

    Never rewrites the decision row. Unknown keys in `corrected` are
    dropped defensively; values are coerced to bool/str (ids and enums
    only — free text has no representable shape here).
    """
    if not decision_id:
        return
    clean: dict = {}
    for key, value in (corrected or {}).items():
        if key not in CORRECTED_KEYS or value is None:
            continue
        clean[key] = value if isinstance(value, bool) else str(value)
    _append({
        "ts": time.time(),
        "schema": SCHEMA,
        "decision_id": str(decision_id),
        "corrected": clean,
    })


def read_memory() -> tuple[list[dict], int]:
    """Read all rows; returns (rows, skipped_count).

    Skips (and counts) malformed lines and unknown schemas — a future
    lv_route_mem_v2 writer must never crash a v1 reader.
    """
    path = routing_memory_path()
    if not path.is_file():
        return [], 0
    rows: list[dict] = []
    skipped = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.warning("routing memory unreadable at %s (ignored)", path)
        return [], 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(record, dict) or record.get("schema") != SCHEMA:
            skipped += 1
            continue
        rows.append(record)
    if skipped:
        logger.warning(
            "routing memory: skipped %d unknown/malformed row(s)", skipped)
    return rows, skipped


def is_correction(row: dict) -> bool:
    """A correction row carries a corrected payload and no decision field."""
    return isinstance(row.get("corrected"), dict)
