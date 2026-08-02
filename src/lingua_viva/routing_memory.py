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
import math
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


# Content-free guard: every string this module persists is an enum, an id,
# or a signal-list key — a short single token. Anything with whitespace or
# beyond this length is, by definition, not one of those (it is most likely
# free text that must never land in the file).
_MAX_TOKEN_LEN = 80
_INVALID_TOKEN = "invalid_token"


def _safe_token(value) -> str:
    token = str(value or "")
    if not token:
        return ""
    if len(token) > _MAX_TOKEN_LEN or any(ch.isspace() for ch in token):
        logger.warning(
            "routing memory: non-token value dropped (len=%d)", len(token))
        return _INVALID_TOKEN
    return token


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
    The whole body is fire-and-forget: malformed arguments (wrong types,
    non-iterables) are swallowed and logged, never raised to the caller.
    """
    decision_id = uuid.uuid4().hex
    try:
        if decision not in DECISION_TYPES:
            logger.warning(
                "routing memory: unknown decision type %r dropped", decision)
            return decision_id
        try:
            confidence_f = round(float(confidence), 4)
        except (TypeError, ValueError):
            confidence_f = 0.0
        if not math.isfinite(confidence_f):
            confidence_f = 0.0
        row = {
            "ts": time.time(),
            "schema": SCHEMA,
            "decision_id": decision_id,
            "trace_id": _safe_token(trace_id),
            "decision": decision,
            "outcome": _safe_token(outcome),
            "confidence": confidence_f,
            "signals_matched": [_safe_token(s) for s in (signals_matched or [])],
            "subject_ref": {
                k: _safe_token(v)
                for k, v in (subject_ref or {}).items()
                if k in SUBJECT_REF_KEYS and v
            },
            "corrected": None,
        }
        _append({k: v for k, v in row.items() if k in ALLOWED_KEYS})
    except Exception:
        logger.warning(
            "routing memory record_decision failed (ignored)", exc_info=True)
    return decision_id


def record_correction(decision_id: str, corrected: dict) -> None:
    """Append a correction row referencing an earlier decision.

    Never rewrites the decision row. Unknown keys in `corrected` are
    dropped defensively; values are coerced to bool/str (ids and enums
    only — free text has no representable shape here). A payload with no
    surviving keys is NOT appended: an empty `corrected` dict would read
    as a negative correction downstream and inflate correction rates.
    Fire-and-forget: never raises to the caller.
    """
    try:
        if not decision_id:
            return
        clean: dict = {}
        for key, value in (corrected or {}).items():
            if key not in CORRECTED_KEYS or value is None:
                continue
            clean[key] = value if isinstance(value, bool) else _safe_token(value)
        if not clean:
            logger.warning(
                "routing memory: empty correction payload dropped (id=%s)",
                decision_id)
            return
        _append({
            "ts": time.time(),
            "schema": SCHEMA,
            "decision_id": _safe_token(decision_id),
            "corrected": clean,
        })
    except Exception:
        logger.warning(
            "routing memory record_correction failed (ignored)", exc_info=True)


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
