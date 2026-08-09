"""Absence tracking + coordinator escalation — worked example for W2.

Tracks per-student absences in an NDJSON ledger under
``<LV_STATE_HOME>/absences/`` and escalates to the coordinator when a
threshold is crossed:

  * ``consecutive_threshold`` (default 3) consecutive SCHOOL days, or
  * ``window_threshold`` (default 5) absences within the last
    ``window_days`` (default 20) school days.

School days are weekdays (Mon-Fri); a Friday absence followed by a
Monday absence is consecutive. Term-calendar holidays are out of scope
for this slice — a weekday holiday counts as a school day, which can
only make escalation MORE eager (fail closed in the safe direction).

Escalations are queued through the same local notification outbox as
safeguarding (src/lingua_viva/safeguarding.py — docpipe sync-queue
pattern): no network code, and the notification carries the escalation
id, not student narrative. One pending escalation per (student, reason)
— re-running check_escalations() does not duplicate.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.lingua_viva.safeguarding import enqueue_notification

DEFAULT_CONSECUTIVE_THRESHOLD = 3
DEFAULT_WINDOW_THRESHOLD = 5
DEFAULT_WINDOW_SCHOOL_DAYS = 20


def _state_home() -> Path:
    """LV_STATE_HOME convention (same as teacher_readiness/routing_memory)."""
    return Path(os.environ.get("LV_STATE_HOME", str(Path.home() / ".lingua-viva")))


def _absence_dir() -> Path:
    path = _state_home() / "absences"
    path.mkdir(parents=True, exist_ok=True)
    return path


def absences_path() -> Path:
    return _absence_dir() / "absences.ndjson"


def escalations_path() -> Path:
    return _absence_dir() / "escalations.ndjson"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            items.append(parsed)
    return items


def _parse_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value).strip())


def record_absence(student_id: str, absence_date) -> dict:
    """Record one absence day. Idempotent per (student_id, date)."""
    student = str(student_id or "").strip()
    if not student:
        raise ValueError("student_id is required")
    day = _parse_date(absence_date)
    for existing in _read(absences_path()):
        if existing.get("student_id") == student and existing.get("date") == day.isoformat():
            return {**existing, "duplicate": True}
    entry = {
        "absence_id": f"abs-{uuid.uuid4().hex[:12]}",
        "student_id": student,
        "date": day.isoformat(),
        "recorded_at": _now(),
    }
    _append(absences_path(), entry)
    return {**entry, "duplicate": False}


def _next_school_day(day: date) -> date:
    step = day + timedelta(days=1)
    while step.weekday() >= 5:  # Sat=5, Sun=6
        step += timedelta(days=1)
    return step


def _school_days_back(from_day: date, count: int) -> date:
    """The date `count` school days before from_day (inclusive window start)."""
    day = from_day
    remaining = count - 1
    while remaining > 0:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day


def _max_consecutive_run(days: list[date]) -> tuple[int, list[date]]:
    """Longest run of consecutive school-day absences."""
    if not days:
        return 0, []
    ordered = sorted(set(days))
    best_run: list[date] = [ordered[0]]
    run: list[date] = [ordered[0]]
    for day in ordered[1:]:
        if day == _next_school_day(run[-1]):
            run.append(day)
        else:
            run = [day]
        if len(run) > len(best_run):
            best_run = run
    return len(best_run), best_run


def check_escalations(
    *,
    today: Optional[date] = None,
    consecutive_threshold: int = DEFAULT_CONSECUTIVE_THRESHOLD,
    window_threshold: int = DEFAULT_WINDOW_THRESHOLD,
    window_days: int = DEFAULT_WINDOW_SCHOOL_DAYS,
) -> list[dict]:
    """Evaluate thresholds, persist NEW escalations (queued to the
    coordinator via the notification outbox), return ALL pending ones."""
    today = today or date.today()
    window_start = _school_days_back(today, max(1, int(window_days)))

    by_student: dict[str, list[date]] = {}
    for entry in _read(absences_path()):
        try:
            day = _parse_date(entry.get("date"))
        except (ValueError, TypeError):
            continue
        by_student.setdefault(str(entry.get("student_id") or ""), []).append(day)

    existing = _read(escalations_path())
    pending_keys = {
        (e.get("student_id"), e.get("reason"))
        for e in existing
        if e.get("status") == "pending"
    }

    new_escalations: list[dict] = []
    for student, days in sorted(by_student.items()):
        if not student:
            continue
        weekday_days = [d for d in days if d.weekday() < 5]

        run_length, run_days = _max_consecutive_run(weekday_days)
        if run_length >= max(1, int(consecutive_threshold)) and (student, "consecutive") not in pending_keys:
            new_escalations.append({
                "student_id": student,
                "reason": "consecutive",
                "count": run_length,
                "threshold": int(consecutive_threshold),
                "dates": [d.isoformat() for d in run_days],
            })

        in_window = [d for d in weekday_days if window_start <= d <= today]
        if len(in_window) >= max(1, int(window_threshold)) and (student, "window") not in pending_keys:
            new_escalations.append({
                "student_id": student,
                "reason": "window",
                "count": len(in_window),
                "threshold": int(window_threshold),
                "window_school_days": int(window_days),
                "dates": [d.isoformat() for d in sorted(in_window)],
            })

    for item in new_escalations:
        item.update({
            "escalation_id": f"esc-{uuid.uuid4().hex[:12]}",
            "created_at": _now(),
            "status": "pending",
            "escalate_to": "coordinator",
        })
        # Content discipline: the queued notification carries the id only.
        item["notification_id"] = enqueue_notification(
            kind="absence_escalation",
            ref_id=item["escalation_id"],
            summary="An attendance threshold was crossed — coordinator review needed.",
        )["notification_id"]
        _append(escalations_path(), item)

    return [e for e in _read(escalations_path()) if e.get("status") == "pending"]
