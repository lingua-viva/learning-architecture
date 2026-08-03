from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import vault
from .contracts import ExtractionRecord, LensRecord, ObservationRecord


PROFILE_FIELDS = (
    "learning_and_cognition",
    "communication_and_language",
    "executive_functioning",
    "social_skills",
    "emotional_regulation",
    "physical_sensory_needs",
    "attendance_and_engagement",
    "strategies_trialed",
    "academic_strengths",
    "personal_strengths",
)

SUPPORT_CATEGORY_FIELDS = frozenset(PROFILE_FIELDS[:7])

FIELD_KEYWORDS = {
    "communication_and_language": (
        "quotation",
        "explains",
        "vocabulary",
        "sentence",
        "language",
        "italian",
        "response",
    ),
    "executive_functioning": (
        "checklist",
        "organize",
        "organization",
        "topic sentence",
        "before writing",
        "task",
        "sequenc",
    ),
    "academic_strengths": (
        "strong",
        "careful",
        "extend",
        "can extend",
        "relevant quotation",
        "inference",
    ),
    "strategies_trialed": (
        "strategy",
        "benefits from",
        "helped",
        "checklist",
        "sentence starter",
    ),
}


def create_from_extraction(
    extraction: ExtractionRecord,
    *,
    student_id: str,
    student_name: str,
    added_by: str,
    root: Path | None = None,
    student_store: Any | None = None,
) -> LensRecord:
    try:
        current = vault.get_lens(student_id, root=root)
        data = copy.deepcopy(current.data)
    except FileNotFoundError:
        data = _empty_lens(student_id, student_name)

    source_id = extraction.source_id
    span_ids = _span_ids_for_student(extraction.data, student_id, student_name)
    spans = [
        span
        for span in extraction.data.get("spans", [])
        if span.get("span_id") in span_ids or _mentions_student(span.get("text"), student_name)
    ]
    added_fields: list[str] = []
    for span in spans:
        for field_id in _fields_for_span(str(span.get("text") or "")):
            evidence = {
                "source_ref": {
                    "type": "DOCUMENT",
                    "source_id": source_id,
                    "path": f"extracted/{source_id}.json",
                },
                "span_id": str(span["span_id"]),
                "confidence": _student_confidence(extraction.data, student_id, span["span_id"]),
                "added_at": _now(),
                "added_by": added_by,
            }
            if _append_field_value(data, field_id, _clean_span_text(span["text"]), evidence):
                added_fields.append(field_id)

    metadata = data.setdefault("metadata", {})
    metadata.setdefault("source_ids", [])
    if source_id not in metadata["source_ids"]:
        metadata["source_ids"].append(source_id)
    metadata.setdefault("observation_ids", [])
    metadata.setdefault("merge_events", []).append(
        {
            "event_type": "create_from_extraction",
            "source_id": source_id,
            "fields": sorted(set(added_fields)),
            "added_at": _now(),
            "added_by": added_by,
        }
    )
    data["updated_at"] = _now()
    _assert_grounded(data)
    record = vault.put_lens(LensRecord(data), root=root)
    if student_store is not None:
        record = _sync_to_student_store(record, student_store, root=root)
    return record


def merge_observation(
    lens: LensRecord,
    observation: ObservationRecord,
    *,
    added_by: str,
    root: Path | None = None,
    student_store: Any | None = None,
) -> LensRecord:
    data = copy.deepcopy(lens.data)
    if observation.student_id != data.get("student_id"):
        raise ValueError("observation student_id does not match lens student_id")

    added_fields: list[str] = []
    for claim in observation.data.get("claims", []):
        if not isinstance(claim, dict):
            continue
        field_id = claim.get("field_id")
        if field_id not in PROFILE_FIELDS:
            raise ValueError(f"unknown lens field_id {field_id!r}")
        value = claim.get("value")
        if _is_empty(value):
            continue
        evidence = {
            "source_ref": {
                "type": "OBSERVATION",
                "obs_id": observation.obs_id,
                "path": (
                    f"lenses/{observation.student_id}/observations/"
                    f"{observation.obs_id}.json"
                ),
            },
            "obs_id": observation.obs_id,
            "confidence": float(claim.get("confidence", 0.75)),
            "added_at": _now(),
            "added_by": added_by,
        }
        if _append_field_value(data, field_id, value, evidence):
            added_fields.append(field_id)

    metadata = data.setdefault("metadata", {})
    metadata.setdefault("source_ids", [])
    metadata.setdefault("observation_ids", [])
    if observation.obs_id not in metadata["observation_ids"]:
        metadata["observation_ids"].append(observation.obs_id)
    metadata.setdefault("merge_events", []).append(
        {
            "event_type": "merge_observation",
            "obs_id": observation.obs_id,
            "fields": sorted(set(added_fields)),
            "added_at": _now(),
            "added_by": added_by,
        }
    )
    data["updated_at"] = _now()
    _assert_grounded(data)
    record = vault.put_lens(LensRecord(data), root=root)
    if student_store is not None:
        record = _sync_to_student_store(record, student_store, root=root)
    return record


def sync_to_student_lens_store(
    lens: LensRecord,
    student_store: Any,
    *,
    root: Path | None = None,
) -> LensRecord:
    return _sync_to_student_store(lens, student_store, root=root)


def _empty_lens(student_id: str, display_name: str) -> dict[str, Any]:
    return {
        "schema_version": "docpipe.lens.v1",
        "student_id": student_id,
        "display_name": display_name,
        "created_at": _now(),
        "updated_at": _now(),
        "profile": {
            field_id: {"value": None, "evidence": []}
            for field_id in PROFILE_FIELDS
        },
        "metadata": {
            "source_ids": [],
            "observation_ids": [],
            "merge_events": [],
        },
    }


def _span_ids_for_student(data: dict[str, Any], student_id: str, student_name: str) -> set[str]:
    ids: set[str] = set()
    for student in data.get("structure", {}).get("students_detected", []):
        if not isinstance(student, dict):
            continue
        if student.get("student_id") == student_id or student.get("display_name") == student_name:
            ids.update(str(span_id) for span_id in student.get("span_ids", []) if span_id)
    return ids


def _mentions_student(text: object, student_name: str) -> bool:
    if not isinstance(text, str) or not student_name:
        return False
    return student_name.lower() in text.lower()


def _fields_for_span(text: str) -> list[str]:
    lower = text.lower()
    fields = [
        field_id
        for field_id, keywords in FIELD_KEYWORDS.items()
        if any(keyword in lower for keyword in keywords)
    ]
    return fields


def _student_confidence(data: dict[str, Any], student_id: str, span_id: str) -> float:
    for student in data.get("structure", {}).get("students_detected", []):
        if not isinstance(student, dict):
            continue
        if student.get("student_id") == student_id and span_id in student.get("span_ids", []):
            try:
                return float(student.get("confidence", 0.8))
            except (TypeError, ValueError):
                return 0.8
    return 0.8


def _clean_span_text(text: object) -> str:
    return " ".join(str(text or "").split())[:2000]


def _append_field_value(
    lens_data: dict[str, Any],
    field_id: str,
    value: Any,
    evidence: dict[str, Any],
) -> bool:
    field = lens_data["profile"][field_id]
    current = field.get("value")
    key = _evidence_key(field_id, evidence)
    existing_keys = {
        _evidence_key(field_id, item)
        for item in field.get("evidence", [])
    }
    if key in existing_keys:
        return False

    evidence = copy.deepcopy(evidence)

    if _is_empty(current):
        field["value"] = value
    elif current == value:
        pass
    elif isinstance(current, list):
        if value not in current:
            current.append(value)
    else:
        field["value"] = [current, value]
    field.setdefault("evidence", []).append(evidence)
    return True


def _assert_grounded(lens_data: dict[str, Any]) -> None:
    for field_id, field in lens_data.get("profile", {}).items():
        value = field.get("value")
        evidence = field.get("evidence", [])
        if _is_empty(value):
            if evidence:
                raise ValueError(f"{field_id} is empty but has evidence")
            continue
        if not evidence:
            raise ValueError(f"{field_id} is populated without evidence")
        for item in evidence:
            source_ref = item.get("source_ref", {})
            if source_ref.get("type") == "DOCUMENT" and not item.get("span_id"):
                raise ValueError(f"{field_id} document evidence missing span_id")
            if source_ref.get("type") == "OBSERVATION" and not item.get("obs_id"):
                raise ValueError(f"{field_id} observation evidence missing obs_id")


def _sync_to_student_store(
    record: LensRecord,
    student_store: Any,
    *,
    root: Path | None = None,
) -> LensRecord:
    data = copy.deepcopy(record.data)
    _ensure_student_store_lens(student_store, data["student_id"], data["display_name"])
    sync = data.setdefault("metadata", {}).setdefault(
        "student_store_sync",
        {"synced_evidence_keys": []},
    )
    synced = set(sync.setdefault("synced_evidence_keys", []))
    for field_id, field in data["profile"].items():
        values = _values_for_evidence(field.get("value"), field.get("evidence", []))
        for evidence, value in zip(field.get("evidence", []), values):
            evidence_key = _evidence_key(field_id, evidence)
            if evidence_key in synced:
                continue
            _bridge_one_field(student_store, data["student_id"], field_id, value, evidence)
            synced.add(evidence_key)
    sync["synced_evidence_keys"] = sorted(synced)
    _assert_grounded(data)
    return vault.put_lens(LensRecord(data), root=root)


def _ensure_student_store_lens(student_store: Any, student_id: str, display_name: str) -> None:
    try:
        student_store.get_lens(student_id)
        return
    except Exception as exc:
        if exc.__class__.__name__ != "LensNotFoundError":
            raise
    student_store.create_lens(student_id=student_id, display_name=display_name)


def _bridge_one_field(
    student_store: Any,
    student_id: str,
    field_id: str,
    value: Any,
    evidence: dict[str, Any],
) -> None:
    text = _value_text(value)
    if not text:
        return
    source_ref = evidence.get("source_ref") or {}
    source_observation_id = evidence.get("obs_id") or source_ref.get("obs_id")
    source_ref_ids = []
    if source_ref.get("source_id"):
        source_ref_ids.append(str(source_ref["source_id"]))
    confidence = (
        "teacher_confirmed"
        if source_ref.get("type") == "OBSERVATION"
        else "imported_verified"
    )
    if field_id in SUPPORT_CATEGORY_FIELDS:
        student_store.add_support_evidence(
            student_id=student_id,
            category_id=field_id,
            summary=text,
            created_by=str(evidence.get("added_by") or "docpipe"),
            evidence_type=(
                "observation"
                if source_ref.get("type") == "OBSERVATION"
                else "local_file"
            ),
            source_observation_id=source_observation_id,
            source_ref_ids=source_ref_ids,
        )
        return
    if field_id == "academic_strengths":
        student_store.add_profile_strength(
            student_id=student_id,
            kind="academic",
            text=text,
            created_by=str(evidence.get("added_by") or "docpipe"),
            source_observation_id=source_observation_id,
            source_ref_ids=source_ref_ids,
            confidence=confidence,
        )
        return
    if field_id == "personal_strengths":
        student_store.add_profile_strength(
            student_id=student_id,
            kind="personal",
            text=text,
            created_by=str(evidence.get("added_by") or "docpipe"),
            source_observation_id=source_observation_id,
            source_ref_ids=source_ref_ids,
            confidence=confidence,
        )
        return
    if field_id == "strategies_trialed":
        outcome = value.get("outcome") if isinstance(value, dict) else None
        bucket = {
            "worked": "strategies_worked",
            "did_not_work": "strategies_not_worked",
        }.get(outcome, "open_questions")
        student_store.add_support_entry(
            student_id=student_id,
            category_id="learning_and_cognition",
            bucket=bucket,
            text=text,
            created_by=str(evidence.get("added_by") or "docpipe"),
            source_observation_id=source_observation_id,
            source_ref_ids=source_ref_ids,
            confidence=confidence,
        )


def _values_for_evidence(value: Any, evidence: list[dict[str, Any]]) -> list[Any]:
    if not isinstance(value, list):
        return [value for _ in evidence]
    if len(value) == len(evidence):
        return value
    return [value for _ in evidence]


def _value_text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split())[:2000]
    if isinstance(value, dict):
        parts = []
        for key in ("strategy", "outcome", "evidence", "summary"):
            if value.get(key):
                parts.append(f"{key}: {value[key]}")
        return "; ".join(parts)[:2000]
    if isinstance(value, list):
        return "; ".join(_value_text(item) for item in value if not _is_empty(item))[:2000]
    return ""


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _evidence_key(field_id: str, evidence: dict[str, Any]) -> str:
    payload = {
        "field_id": field_id,
        "source_ref": evidence.get("source_ref"),
        "span_id": evidence.get("span_id"),
        "obs_id": evidence.get("obs_id"),
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
