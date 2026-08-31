"""STEP 5 — identity resolution (SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19, L8).

`student_id = slug(display_name)` makes identity BE the spelling: "Marco B-R"
in a support file and "Marco Bianchi" in the class list silently become two
children. This module gives each child a canonical id plus a set of observed
SURFACE FORMS, and resolves new spellings against a class roster (~39 names,
never globally):

- **exact**    — the normalized spelling IS a roster student's display name or
  a surface form a human already ruled on → canonical student_id. Replaying a
  recorded ruling is deterministic, not a guess.
- **queue**    — the spelling plausibly matches roster students (first name
  exact + abbreviated-initial compatibility) → an unresolved queue for a
  human. Default per ruling §8-3: ALWAYS queue, NEVER auto-merge — confidence
  currently measures nothing (STEP 3 deleted the dead gate).
- **new**      — no plausible match → a genuinely new student.

The queue is the same NDJSON event-log pattern as ingest_review.py
(last-event-wins state). An "assigned" event is the `same_person_as` relation
of the MC lens precedent (DESIGN_LENS_SCHEMA_MC_LENS_V1_2026-08-10): a
relation between a spelling and an existing canonical record — never a new
entity type, never a coercive merge. Assigned events double as the
surface-form registry that future resolutions replay.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.lingua_viva.runtime_paths import runtime_data_dir


def identity_queue_path() -> Path:
    return runtime_data_dir("ingest_review") / "identity.ndjson"


def _now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_name(name: str) -> str:
    """One normal form for spelling comparison: NFKC, casefold, nickname
    parentheses dropped ("Anna (Annie) Villa" == "Anna Villa"), whitespace
    collapsed. Never used to REWRITE a display name — only to compare."""
    text = unicodedata.normalize("NFKC", str(name or ""))
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _name_tokens(name: str) -> list[str]:
    return [token for token in normalize_name(name).split(" ") if token]


def _initials(token: str) -> list[str]:
    """Initial letters carried by an abbreviated token: "b-r" → ["b", "r"],
    "b." → ["b"]. A token is abbreviation-shaped when every dash/dot part is
    a single letter."""
    parts = [part for part in re.split(r"[-.\u2010\u2011]", token) if part]
    if parts and all(len(part) == 1 for part in parts):
        return parts
    return []


def _compatible(detected_tokens: list[str], roster_tokens: list[str]) -> bool:
    """Plausible same-child match: first name exact, and every following
    detected token is either an exact roster token or an abbreviation whose
    initials all start roster tokens ("Marco B-R" ~ "Marco Bianchi-Rossi",
    and — one initial resolvable — "Marco B-R" ~ "Marco Bianchi")."""
    if not detected_tokens or not roster_tokens:
        return False
    if detected_tokens[0] != roster_tokens[0]:
        return False
    rest_roster = roster_tokens[1:]
    rest_detected = detected_tokens[1:]
    if not rest_detected or not rest_roster:
        # a bare first name against a roster child with that first name is
        # plausible — the human decides
        return True
    roster_initials = {token[0] for token in rest_roster}
    for token in rest_detected:
        if token in rest_roster:
            continue
        initials = _initials(token)
        if not initials:
            return False
        if not any(initial in roster_initials for initial in initials):
            return False
    return True


# ---------------------------------------------------------------------------
# Event log (clone of the ingest_review NDJSON pattern)
# ---------------------------------------------------------------------------


def _append_event(event: dict[str, Any]) -> dict[str, Any]:
    path = identity_queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_id": f"identity-{uuid.uuid4().hex}",
        "event_at": _now_z(),
        **event,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return payload


def read_events() -> list[dict[str, Any]]:
    try:
        lines = identity_queue_path().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events


def _item_key(teacher_id: str, display_name: str) -> str:
    return f"{teacher_id}|{normalize_name(display_name)}"


def current_items() -> dict[str, dict[str, Any]]:
    """Last-event-wins queue state, keyed by (teacher, normalized spelling)."""
    state: dict[str, dict[str, Any]] = {}
    for event in read_events():
        key = _item_key(str(event.get("teacher_id") or ""),
                        str(event.get("display_name") or ""))
        if key.strip("|"):
            state[key] = event
    return state


def list_open_items(teacher_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = [
        item for item in current_items().values()
        if item.get("status") == "open"
        and (not teacher_id or item.get("teacher_id") == teacher_id)
    ]
    return sorted(
        items,
        key=lambda item: str(item.get("queued_at") or item.get("event_at") or ""),
        reverse=True,
    )


def surface_forms() -> dict[str, str]:
    """The registry human rulings build: normalized spelling → canonical
    student_id, from every "assigned" event (the same_person_as relation).
    Later events win, so a corrected ruling replaces the old one."""
    forms: dict[str, str] = {}
    for event in read_events():
        if event.get("status") != "assigned":
            continue
        spelling = normalize_name(str(event.get("display_name") or ""))
        student_id = str(event.get("student_id") or "").strip()
        if spelling and student_id:
            forms[spelling] = student_id
    return forms


def enqueue_unresolved(
    *,
    teacher_id: str,
    display_name: str,
    source_id: str,
    candidates: list[dict[str, str]],
    job_id: str = "",
) -> dict[str, Any]:
    existing = current_items().get(_item_key(teacher_id, display_name))
    if existing and existing.get("status") == "open":
        return existing
    return _append_event({
        "status": "open",
        "queued_at": _now_z(),
        "teacher_id": teacher_id,
        "display_name": display_name,
        "source_id": source_id,
        "job_id": job_id,
        "candidates": [
            {
                "student_id": str(candidate.get("student_id") or ""),
                "display_name": str(candidate.get("display_name") or ""),
            }
            for candidate in candidates
        ],
    })


def mark_assigned(
    *,
    teacher_id: str,
    display_name: str,
    student_id: str,
    source_id: str = "",
) -> dict[str, Any]:
    """Record the same_person_as ruling: this spelling IS that student."""
    return _append_event({
        "status": "assigned",
        "assigned_at": _now_z(),
        "teacher_id": teacher_id,
        "display_name": display_name,
        "student_id": student_id,
        "source_id": source_id,
    })


def mark_created(*, teacher_id: str, display_name: str, student_id: str) -> dict[str, Any]:
    """The human ruled "genuinely new student" — closes the queue item."""
    return _append_event({
        "status": "created",
        "created_at": _now_z(),
        "teacher_id": teacher_id,
        "display_name": display_name,
        "student_id": student_id,
    })


def mark_dismissed(*, teacher_id: str, display_name: str) -> dict[str, Any]:
    return _append_event({
        "status": "dismissed",
        "dismissed_at": _now_z(),
        "teacher_id": teacher_id,
        "display_name": display_name,
    })


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve(
    display_name: str,
    roster: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve one detected spelling against a class roster.

    Returns {"status": "exact", "student_id": ...} |
            {"status": "queue", "candidates": [{student_id, display_name}]} |
            {"status": "new"}.
    Roster entries need student_id + display_name. Matching is scoped to the
    roster handed in — the caller passes the approving teacher's ~39, never
    the whole school.
    """
    spelling = normalize_name(display_name)
    if not spelling:
        return {"status": "new"}
    forms = surface_forms()
    if spelling in forms:
        return {"status": "exact", "student_id": forms[spelling]}
    detected_tokens = _name_tokens(display_name)
    # Also try reversed name order (handles "Abigail Chang" vs "Chang Abigail")
    reversed_spelling = " ".join(reversed(spelling.split()))
    reversed_tokens = list(reversed(detected_tokens))
    candidates: list[dict[str, str]] = []
    for entry in roster:
        roster_name = str(entry.get("display_name") or "")
        student_id = str(entry.get("student_id") or "")
        if not roster_name or not student_id:
            continue
        norm_roster = normalize_name(roster_name)
        if norm_roster == spelling or norm_roster == reversed_spelling:
            return {"status": "exact", "student_id": student_id}
        roster_tokens = _name_tokens(roster_name)
        if _compatible(detected_tokens, roster_tokens) or _compatible(reversed_tokens, roster_tokens):
            candidates.append({"student_id": student_id, "display_name": roster_name})
    if candidates:
        return {"status": "queue", "candidates": candidates}
    return {"status": "new"}
