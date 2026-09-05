"""
Student Lens — Product A core data model + CRUD

A student lens is a structured, accumulating profile that a teacher owns
and controls: CEFR level, RTI tier, learning differences, home language,
and observation history. It is built entirely from teacher observations
and is append-only — no observation is ever overwritten or deleted, only
added. The lens is a *recalculated snapshot* over that append-only log.

Design references:
  - case-studies/04-still-i-rise/architecture/observation-capture.md
    (Section 2.1 Observation Record, 2.3 Student Longitudinal Profile,
    Stage 6 RTI Escalation Logic — Rules A-E)
  - case-studies/04-still-i-rise/architecture/rti-tiers.md
    (3-tier RTI model, CEFR-as-parallel-spine)

Storage: local SQLite (offline-first — this file lives on the teacher's
device, not a cloud service). Matches the "SQLite (device) + Postgres
(cloud, optional)" split in data-model.md; this build ships the device
half only, per the Friday vertical-slice scope decision in
BUILD_JOURNAL.md Turn 0.

Privacy: this module never calls any external model or API. It is pure
local data storage and arithmetic. Nothing here routes through the MC
pipeline's external-model path. The DB file defaults to
~/.lingua-viva/runtime/student_lenses.db; tests and deployments can
override it with LV_STUDENT_DB_PATH. Student data must never enter git
history.

Rights (mirrors MC-GOV-008 operator-lens pattern): a teacher can view
(get_lens), export (export_lens — full profile + raw observation log),
and delete (delete_lens — soft tombstone by default, hard purge on
explicit request) any student lens they own.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict, fields as dataclass_fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

def default_db_path() -> Path:
    override = os.environ.get("LV_STUDENT_DB_PATH")
    if override:
        return Path(override)
    from src.lingua_viva.config import lv_home
    return lv_home() / "runtime" / "student_lenses.db"

VALID_RTI_TIERS = (1, 2, 3)
VALID_CEFR_DIMENSIONS = ("reading", "writing", "speaking", "listening")
VALID_CEFR_LEVELS = ("Pre-A1", "A1", "A1+", "A2", "A2+", "B1", "B1+", "B2", "C1", "C2")
VALID_CEFR_DIRECTIONS = ("progressing", "plateaued", "regressing")
VALID_SEL_VALENCE = ("positive", "concern", "neutral")
VALID_TEMPLATE_TYPES = ("general", "literacy", "cefr", "sel_incident", "sel_positive", "rti_flag")

SUPPORT_CATEGORY_IDS = (
    "learning_and_cognition",
    "communication_and_language",
    "executive_functioning",
    "social_skills",
    "emotional_regulation",
    "physical_sensory_needs",
    "attendance_and_engagement",
    "advanced_enrichment",
    "personal_context",
)

SUPPORT_CATEGORY_LABELS = {
    "learning_and_cognition": "Learning and Cognition",
    "communication_and_language": "Communication and Language",
    "executive_functioning": "Executive Functioning",
    "social_skills": "Social Skills",
    "emotional_regulation": "Emotional Regulation",
    "physical_sensory_needs": "Physical/Sensory Needs",
    "attendance_and_engagement": "Attendance and Engagement",
    "advanced_enrichment": "Advanced Students / Enrichment",
    "personal_context": "Personal Context",
}

VALID_CONFIDENCE_VALUES = (
    "teacher_confirmed",
    "model_suggested",
    "imported_verified",
    "imported_needs_confirmation",
)

VALID_EVIDENCE_TYPES = (
    "observation",
    "slack",
    "google_drive",
    "local_file",
    "report",
    "teacher_note",
)

VALID_SUPPORT_BUCKETS = (
    "needs",
    "strengths",
    "strategies_worked",
    "strategies_not_worked",
    "open_questions",
)

VALID_STRATEGY_OUTCOMES = ("worked", "did_not_work", "unknown")

# DOES boundary (Lens Primitive, 2026-08-04): raw narration never leaves the
# machine. Every observation that travels off-device (ledger export, Drive
# lens) has its narration fields overwritten with this fixed marker at the
# export boundary — never filtered by scanning their contents, always
# replaced by construction. See dev/SPEC_LENS_PRIMITIVE_2026-08-04.md.
NARRATION_NOT_SHARED = "(observation narration is device-local and is not shared)"

# Profile-level strengths (v2.1): separate from the per-category strengths
# buckets inside support_profile. These answer the report-facing ask
# "Academic Strengths / Personal Strengths" as top-level profile sections.
VALID_STRENGTH_KINDS = ("academic", "personal")

# Unified evidence ledger (SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01): a
# dated, teacher-attributed claim about a student, tied to a target, with
# provenance. Append-only — soft-delete tombstone only, no UPDATE path.
# Evidence that can be silently edited isn't evidence.
VALID_EVIDENCE_KINDS = ("document", "teacher_feedback", "observation_ref")
VALID_EVIDENCE_TARGET_TYPES = (
    "support_category",
    "ethos_trait",
    "strengths",
    "background",
)

# evidence_type values that describe a stored artifact rather than words a
# teacher typed/spoke — used to derive the ledger `kind` for evidence that
# arrives through the profile-level ethos path.
_DOCUMENT_EVIDENCE_TYPES = ("google_drive", "local_file", "report")

# Ledger kind -> profile evidence_type, for evidence arriving through the
# unified append_evidence() path and mirrored into ethos_profile.
_EVIDENCE_KIND_TO_TYPE = {
    "document": "local_file",
    "teacher_feedback": "teacher_note",
    "observation_ref": "observation",
}

# Sources-ledger source_type -> profile evidence_type, for kind=document
# evidence whose source_ref points at a sources record.
_SOURCE_TYPE_TO_EVIDENCE_TYPE = {
    "drive": "google_drive",
    "local": "local_file",
    "slack": "slack",
}

# Only these confidence levels are eligible for student reports — a
# model_suggested or imported_needs_confirmation item has not been
# teacher-verified and must never appear in a report as fact.
REPORT_GRADE_CONFIDENCE = ("teacher_confirmed", "imported_verified")
LENS_SHARE_AUDIENCES = ("teacher", "family", "hr")
PERSONAL_SUPPORT_CATEGORIES = {"personal_context"}

VALID_SOURCE_TYPES = (
    "observation",
    "slack",
    "google_drive",
    "local_file",
    "report",
    "teacher_note",
)

VALID_SUPPORT_CONTEXT_LANGUAGES = ("it", "en", "multilingual", "unknown")
VALID_SUPPORT_CONTEXT_SETTINGS = (
    "intervention",
    "classroom",
    "small_group",
    "one_to_one",
    "unknown",
)


def support_category_definition(category_id: str) -> str:
    definitions = {
        "learning_and_cognition": "learning pace, memory, comprehension, concept formation, and academic processing evidence",
        "communication_and_language": "receptive language, expressive language, vocabulary, pragmatic communication, and multilingual access evidence",
        "executive_functioning": "planning, sequencing, organization, attention, working memory, transition, and task-initiation evidence",
        "social_skills": "peer interaction, collaboration, turn-taking, conflict repair, and group participation evidence",
        "emotional_regulation": "self-regulation, frustration tolerance, anxiety signs, recovery, and help-seeking evidence",
        "physical_sensory_needs": "sensory access, movement, fatigue, fine/gross motor, seating, hearing, vision, and environmental access evidence",
        "attendance_and_engagement": "attendance, punctuality, participation, stamina, avoidance, withdrawal, and sustained engagement evidence",
        "advanced_enrichment": "high-readiness, acceleration, extension, challenge, and enrichment evidence",
        "personal_context": "teacher-confirmed personal-life, wellbeing, safeguarding, family, or living-context evidence that may affect support planning and should be handled with restricted review",
    }
    return definitions.get(category_id, "support-planning evidence")


def _normalize_context_tags(value: object) -> dict:
    tags = value if isinstance(value, dict) else {}
    language = tags.get("language") if isinstance(tags, dict) else None
    setting = tags.get("setting") if isinstance(tags, dict) else None
    return {
        "language": language if language in VALID_SUPPORT_CONTEXT_LANGUAGES else "unknown",
        "setting": setting if setting in VALID_SUPPORT_CONTEXT_SETTINGS else "unknown",
    }


def _clean_optional_statement(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:2000] if cleaned else None


def normalize_support_entry(raw: object) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    category = raw.get("support_category")
    if category not in SUPPORT_CATEGORY_IDS:
        return None
    outcome = raw.get("strategy_outcome")
    if outcome not in VALID_STRATEGY_OUTCOMES:
        outcome = None
    entry = {
        "support_category": category,
        "need_statement": _clean_optional_statement(raw.get("need_statement")),
        "strength_statement": _clean_optional_statement(raw.get("strength_statement")),
        "strategy_statement": _clean_optional_statement(raw.get("strategy_statement")),
        "strategy_outcome": outcome,
        "evidence_summary": _clean_optional_statement(raw.get("evidence_summary")),
        "context_tags": _normalize_context_tags(raw.get("context_tags")),
        "teacher_edited": bool(raw.get("teacher_edited", False)),
        "model_suggested": bool(raw.get("model_suggested", False)),
        "teacher_confirmed": bool(raw.get("teacher_confirmed", True)),
    }
    if not any(
        entry.get(field)
        for field in (
            "need_statement",
            "strength_statement",
            "strategy_statement",
            "evidence_summary",
        )
    ):
        return None
    return entry


def normalize_support_entries(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    entries = []
    for item in raw:
        normalized = normalize_support_entry(item)
        if normalized is not None:
            entries.append(normalized)
    return entries


def support_entry_from_scalar_fields(
    support_category: Optional[str],
    need_statement: Optional[str],
    strength_statement: Optional[str],
    strategy_statement: Optional[str],
    strategy_outcome: Optional[str],
    evidence_summary: Optional[str],
) -> list[dict]:
    return normalize_support_entries(
        [
            {
                "support_category": support_category,
                "need_statement": need_statement,
                "strength_statement": strength_statement,
                "strategy_statement": strategy_statement,
                "strategy_outcome": strategy_outcome,
                "evidence_summary": evidence_summary,
                "context_tags": {"language": "unknown", "setting": "unknown"},
                "teacher_confirmed": True,
                "model_suggested": False,
            }
        ]
    )


def _support_feedback_message(categories_updated: list[str], saved_entries: int) -> str:
    if saved_entries <= 0 or not categories_updated:
        return "Observation saved. No support-profile category was updated."
    if len(categories_updated) == 1:
        label = SUPPORT_CATEGORY_LABELS.get(categories_updated[0], categories_updated[0])
        definition = support_category_definition(categories_updated[0])
        return f"Saved under {label}. This category is used for {definition}."
    labels = [SUPPORT_CATEGORY_LABELS.get(cat, cat) for cat in categories_updated]
    return f"Saved {saved_entries} support-profile entries across: {', '.join(labels)}."


def _support_next_review_prompt(support_entries: list[dict]) -> Optional[str]:
    if any(entry.get("strategy_statement") for entry in support_entries):
        return "Check whether the strategy outcome was language-specific or setting-specific."
    if support_entries:
        return "Review whether this is a need, a strength, evidence, or a strategy outcome."
    return None


def support_profile_default() -> dict:
    """Return default v2 support profile with all canonical categories initialized."""
    return {
        "schema_version": 2,
        "categories": {
            cat_id: {
                "needs": [],
                "strengths": [],
                "strategies_worked": [],
                "strategies_not_worked": [],
                "evidence": [],
                "open_questions": [],
            }
            for cat_id in SUPPORT_CATEGORY_IDS
        },
        "last_reviewed_at": None,
        "last_reviewed_by": None,
    }


def _normalize_support_profile_with_warnings(raw: str | dict | None) -> tuple[dict, list[str]]:
    default = support_profile_default()
    warnings = []
    if not raw:
        return default, warnings
    if isinstance(raw, str):
        try:
            sp = json.loads(raw)
        except Exception:
            return default, ["support_profile contained invalid JSON; default v2 profile returned"]
    elif isinstance(raw, dict):
        sp = raw
    else:
        return default, ["support_profile had an invalid storage type; default v2 profile returned"]

    if not isinstance(sp, dict):
        return default, ["support_profile root was not an object; default v2 profile returned"]

    categories = sp.get("categories")
    if not isinstance(categories, dict):
        categories = {}
        warnings.append("support_profile categories were missing or invalid; defaults filled")

    normalized_categories = {}
    for cat_id in SUPPORT_CATEGORY_IDS:
        cat_data = categories.get(cat_id)
        if not isinstance(cat_data, dict):
            cat_data = {}
            warnings.append(
                f"support_profile category '{cat_id}' was missing or invalid; defaults filled"
            )
        normalized_categories[cat_id] = {
            "needs": cat_data.get("needs") if isinstance(cat_data.get("needs"), list) else [],
            "strengths": (
                cat_data.get("strengths")
                if isinstance(cat_data.get("strengths"), list)
                else []
            ),
            "strategies_worked": (
                cat_data.get("strategies_worked")
                if isinstance(cat_data.get("strategies_worked"), list)
                else []
            ),
            "strategies_not_worked": (
                cat_data.get("strategies_not_worked")
                if isinstance(cat_data.get("strategies_not_worked"), list)
                else []
            ),
            "evidence": (
                cat_data.get("evidence")
                if isinstance(cat_data.get("evidence"), list)
                else []
            ),
            "open_questions": (
                cat_data.get("open_questions")
                if isinstance(cat_data.get("open_questions"), list)
                else []
            ),
        }

        for bucket in (*VALID_SUPPORT_BUCKETS, "evidence"):
            if bucket in cat_data and not isinstance(cat_data.get(bucket), list):
                warnings.append(
                    f"support_profile category '{cat_id}' bucket '{bucket}' was invalid; "
                    "defaulted to []"
                )

    return (
        {
            "schema_version": 2,
            "categories": normalized_categories,
            "last_reviewed_at": sp.get("last_reviewed_at"),
            "last_reviewed_by": sp.get("last_reviewed_by"),
        },
        warnings,
    )


def _normalize_support_profile(raw: str | dict | None) -> dict:
    return _normalize_support_profile_with_warnings(raw)[0]


def _validate_non_empty_string(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_source_ref_ids(source_ref_ids: Optional[list[str]]) -> list[str]:
    if source_ref_ids is None:
        return []
    if not isinstance(source_ref_ids, list) or not all(
        isinstance(item, str) and item.strip() for item in source_ref_ids
    ):
        raise ValueError("source_ref_ids must be a list of non-empty strings")
    return source_ref_ids


def _validate_support_entry(entry: dict) -> None:
    if not isinstance(entry, dict):
        raise ValueError("support profile entries must be objects")
    text = entry.get("text")
    if not (isinstance(text, str) and text.strip() and len(text) <= 2000):
        raise ValueError("Entry text must be non-empty and <= 2000 characters")
    confidence = entry.get("confidence", "teacher_confirmed")
    if confidence not in VALID_CONFIDENCE_VALUES:
        raise ValueError(
            f"Invalid confidence '{confidence}'. Allowed: {VALID_CONFIDENCE_VALUES}"
        )
    _validate_non_empty_string(entry.get("created_by"), "created_by")
    _validate_non_empty_string(entry.get("source_observation_id"), "source_observation_id")
    _validate_source_ref_ids(entry.get("source_ref_ids"))


def _validate_support_evidence(item: dict) -> None:
    if not isinstance(item, dict):
        raise ValueError("support profile evidence items must be objects")
    summary = item.get("summary")
    if not (isinstance(summary, str) and summary.strip() and len(summary) <= 2000):
        raise ValueError("Evidence summary must be non-empty and <= 2000 characters")
    evidence_type = item.get("evidence_type", "observation")
    if evidence_type not in VALID_EVIDENCE_TYPES:
        raise ValueError(
            f"Invalid evidence_type '{evidence_type}'. Allowed: {VALID_EVIDENCE_TYPES}"
        )
    _validate_non_empty_string(item.get("created_by"), "created_by")
    _validate_non_empty_string(item.get("source_observation_id"), "source_observation_id")
    _validate_source_ref_ids(item.get("source_ref_ids"))


def _report_grade_support_item(item: dict, *, text_keys: tuple[str, ...]) -> dict | None:
    if not isinstance(item, dict):
        return None
    if item.get("active", True) is False:
        return None
    if item.get("confidence", "teacher_confirmed") not in REPORT_GRADE_CONFIDENCE:
        return None
    text_value = ""
    for key in text_keys:
        value = str(item.get(key) or "").strip()
        if value:
            text_value = value
            break
    if not text_value:
        return None
    allowed = {
        "id",
        "text",
        "summary",
        "created_at",
        "created_by",
        "source_observation_id",
        "source_ref_ids",
        "confidence",
        "evidence_type",
        "active",
    }
    return {key: value for key, value in item.items() if key in allowed}


def support_profile_for_audience(profile: dict, audience: str) -> dict:
    audience = audience if audience in LENS_SHARE_AUDIENCES else "teacher"
    include_personal = audience == "hr"
    normalized = _normalize_support_profile(profile)
    categories: dict[str, dict] = {}
    text_keys = ("text", "summary", "need_statement", "strategy", "question")
    for cat_id, cat_data in normalized.get("categories", {}).items():
        if cat_id in PERSONAL_SUPPORT_CATEGORIES and not include_personal:
            continue
        filtered = {
            "needs": [],
            "strengths": [],
            "strategies_worked": [],
            "strategies_not_worked": [],
            "evidence": [],
            "open_questions": [],
        }
        for bucket in filtered:
            kept = []
            for item in cat_data.get(bucket, []) or []:
                clean = _report_grade_support_item(item, text_keys=text_keys)
                if clean is not None:
                    kept.append(clean)
            filtered[bucket] = kept
        if any(filtered.values()) or include_personal:
            categories[cat_id] = filtered
    return {
        "schema_version": normalized.get("schema_version", 2),
        "share_scope": {
            "audience": audience,
            "personal_context_included": include_personal,
            "unconfirmed_evidence_included": False,
        },
        "categories": categories,
        "last_reviewed_at": normalized.get("last_reviewed_at"),
        "last_reviewed_by": normalized.get("last_reviewed_by"),
    }


def _validate_support_profile(profile: dict) -> None:
    if not isinstance(profile, dict):
        raise ValueError("profile must be a dictionary")
    cats = profile.get("categories", {})
    if not isinstance(cats, dict):
        raise ValueError("support profile categories must be a dictionary")
    for cat_id, cat_data in cats.items():
        if cat_id not in SUPPORT_CATEGORY_IDS:
            raise ValueError(
                f"Unknown category ID '{cat_id}'. Allowed: {SUPPORT_CATEGORY_IDS}"
            )
        if not isinstance(cat_data, dict):
            raise ValueError("support profile category values must be objects")
        for bucket in VALID_SUPPORT_BUCKETS:
            items = cat_data.get(bucket, [])
            if not isinstance(items, list):
                raise ValueError(f"{bucket} must be a list")
            for entry in items:
                _validate_support_entry(entry)
        evidence = cat_data.get("evidence", [])
        if not isinstance(evidence, list):
            raise ValueError("evidence must be a list")
        for item in evidence:
            _validate_support_evidence(item)



_ETHOS_TRAIT_KEY_RE_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"


def strengths_profile_default() -> dict:
    """Default v2.1 profile-level strengths (academic + personal)."""
    return {
        "schema_version": 1,
        "academic_strengths": [],
        "personal_strengths": [],
        "last_reviewed_at": None,
        "last_reviewed_by": None,
    }


def _normalize_strengths_profile_with_warnings(
    raw: str | dict | None,
) -> tuple[dict, list[str]]:
    default = strengths_profile_default()
    warnings: list[str] = []
    if not raw:
        return default, warnings
    if isinstance(raw, str):
        try:
            sp = json.loads(raw)
        except Exception:
            return default, [
                "strengths_profile contained invalid JSON; default profile returned"
            ]
    elif isinstance(raw, dict):
        sp = raw
    else:
        return default, [
            "strengths_profile had an invalid storage type; default profile returned"
        ]
    if not isinstance(sp, dict):
        return default, ["strengths_profile root was not an object; default returned"]

    normalized = {
        "schema_version": 1,
        "academic_strengths": [],
        "personal_strengths": [],
        "last_reviewed_at": sp.get("last_reviewed_at"),
        "last_reviewed_by": sp.get("last_reviewed_by"),
    }
    for key in ("academic_strengths", "personal_strengths"):
        raw_items = sp.get(key)
        if not isinstance(raw_items, list):
            if key in sp:
                warnings.append(f"strengths_profile '{key}' was invalid; defaulted to []")
            continue
        kept = [item for item in raw_items if isinstance(item, dict)]
        if len(kept) != len(raw_items):
            warnings.append(
                f"strengths_profile '{key}' contained non-object items; dropped"
            )
        normalized[key] = kept
    return normalized, warnings


def _validate_strengths_profile(profile: dict) -> None:
    if not isinstance(profile, dict):
        raise ValueError("strengths_profile must be a dictionary")
    for key in ("academic_strengths", "personal_strengths"):
        items = profile.get(key, [])
        if not isinstance(items, list):
            raise ValueError(f"{key} must be a list")
        for entry in items:
            _validate_support_entry(entry)


def ethos_profile_default() -> dict:
    """Default v2.1 ethos profile.

    Trait ids are NOT fixed here (unlike SUPPORT_CATEGORY_IDS) — they come
    from the configurable school-ethos taxonomy (src/education/ethos.py,
    local data at ~/.lingua-viva/ethos.yaml). Membership is enforced at
    write time in add_ethos_evidence; normalization only enforces shape.
    """
    return {
        "schema_version": 1,
        "ethos_name": None,
        "traits": {},
        "last_reviewed_at": None,
        "last_reviewed_by": None,
    }


def _normalize_ethos_profile_with_warnings(
    raw: str | dict | None,
) -> tuple[dict, list[str]]:
    default = ethos_profile_default()
    warnings: list[str] = []
    if not raw:
        return default, warnings
    if isinstance(raw, str):
        try:
            ep = json.loads(raw)
        except Exception:
            return default, [
                "ethos_profile contained invalid JSON; default profile returned"
            ]
    elif isinstance(raw, dict):
        ep = raw
    else:
        return default, [
            "ethos_profile had an invalid storage type; default profile returned"
        ]
    if not isinstance(ep, dict):
        return default, ["ethos_profile root was not an object; default returned"]

    traits = ep.get("traits")
    if not isinstance(traits, dict):
        traits = {}
        if "traits" in ep:
            warnings.append("ethos_profile traits were invalid; defaulted to {}")

    normalized_traits: dict[str, dict] = {}
    for trait_id, trait_data in traits.items():
        if not (
            isinstance(trait_id, str)
            and re.match(_ETHOS_TRAIT_KEY_RE_PATTERN, trait_id)
        ):
            warnings.append(f"ethos_profile trait key {trait_id!r} invalid; dropped")
            continue
        if not isinstance(trait_data, dict):
            trait_data = {}
            warnings.append(
                f"ethos_profile trait '{trait_id}' data was invalid; defaults filled"
            )
        evidence = trait_data.get("evidence")
        if not isinstance(evidence, list):
            if "evidence" in trait_data:
                warnings.append(
                    f"ethos_profile trait '{trait_id}' evidence was invalid; "
                    "defaulted to []"
                )
            evidence = []
        kept = [item for item in evidence if isinstance(item, dict)]
        if len(kept) != len(evidence):
            warnings.append(
                f"ethos_profile trait '{trait_id}' contained non-object "
                "evidence items; dropped"
            )
        normalized = {"evidence": kept}
        # Per-trait rollups recomputed from the evidence_records ledger
        # (SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01) survive normalization;
        # anything with the wrong shape is dropped, not defaulted — the
        # recompute is the source of truth, not this normalizer.
        count = trait_data.get("evidence_count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            normalized["evidence_count"] = count
        last_at = trait_data.get("last_evidence_at")
        if isinstance(last_at, str) or (
            last_at is None and "last_evidence_at" in trait_data
        ):
            normalized["last_evidence_at"] = last_at
        normalized_traits[trait_id] = normalized

    return (
        {
            "schema_version": 1,
            "ethos_name": ep.get("ethos_name"),
            "traits": normalized_traits,
            "last_reviewed_at": ep.get("last_reviewed_at"),
            "last_reviewed_by": ep.get("last_reviewed_by"),
        },
        warnings,
    )


def _validate_ethos_evidence(item: dict) -> None:
    """Ethos evidence = support evidence shape + a confidence field, so a
    model-suggested trait match is never indistinguishable from a
    teacher-confirmed one in a report."""
    _validate_support_evidence(item)
    confidence = item.get("confidence", "teacher_confirmed")
    if confidence not in VALID_CONFIDENCE_VALUES:
        raise ValueError(
            f"Invalid confidence '{confidence}'. Allowed: {VALID_CONFIDENCE_VALUES}"
        )


def _validate_ethos_profile(profile: dict) -> None:
    if not isinstance(profile, dict):
        raise ValueError("ethos_profile must be a dictionary")
    traits = profile.get("traits", {})
    if not isinstance(traits, dict):
        raise ValueError("ethos_profile traits must be a dictionary")
    for trait_id, trait_data in traits.items():
        if not (
            isinstance(trait_id, str)
            and re.match(_ETHOS_TRAIT_KEY_RE_PATTERN, trait_id)
        ):
            raise ValueError(
                f"Invalid trait id '{trait_id}' "
                f"(must match {_ETHOS_TRAIT_KEY_RE_PATTERN})"
            )
        if not isinstance(trait_data, dict):
            raise ValueError("ethos_profile trait values must be objects")
        evidence = trait_data.get("evidence", [])
        if not isinstance(evidence, list):
            raise ValueError("ethos_profile trait evidence must be a list")
        for item in evidence:
            _validate_ethos_evidence(item)


class LensNotFoundError(Exception):
    """Raised when an operation targets a student_id with no lens."""


class ObservationValidationError(Exception):
    """Raised when an observation fails required-field / value validation."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Observation:
    """
    One teacher observation. Append-only — never mutated after save.
    Mirrors observation-capture.md Section 2.1, trimmed to what the
    Friday vertical slice actually needs (no audio/device metadata,
    since STT capture is handled upstream by the Slack bot / app layer
    before this module ever sees text).
    """

    student_id: str
    teacher_id: str
    template_type: str
    raw_transcript: str
    observation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    teacher_edited_transcript: Optional[str] = None
    recorded_at: str = field(default_factory=_now_iso)

    rti_tier: Optional[int] = None
    rti_tier_changed_this_obs: bool = False
    cefr_dimension: Optional[str] = None
    cefr_level_observed: Optional[str] = None
    cefr_direction: Optional[str] = None
    sel_domain: Optional[str] = None
    sel_valence: Optional[str] = None
    urgency_flag: bool = False

    ontology_node: Optional[str] = None
    sync_status: str = "pending"

    support_category: Optional[str] = None
    need_statement: Optional[str] = None
    strength_statement: Optional[str] = None
    strategy_statement: Optional[str] = None
    strategy_outcome: Optional[str] = None
    evidence_summary: Optional[str] = None
    source_type: Optional[str] = None
    support_entries: list[dict] = field(default_factory=list)
    classification_guidance: Optional[dict] = None
    teacher_feedback: Optional[dict] = None

    def validate(self) -> list[str]:
        """Return a list of validation errors. Empty list = valid.

        Mirrors observation-capture.md Stage 2 (Local Validation): errors
        are recorded and surfaced, but do NOT block save — an observation
        a teacher spoke is never silently discarded.
        """
        errors = []
        if not self.student_id:
            errors.append("student_id is required")
        if not self.teacher_id:
            errors.append("teacher_id is required")
        if self.template_type not in VALID_TEMPLATE_TYPES:
            errors.append(f"template_type must be one of {VALID_TEMPLATE_TYPES}")
        if not (self.raw_transcript or "").strip():
            errors.append("raw_transcript must not be empty")
        if self.rti_tier is not None and self.rti_tier not in VALID_RTI_TIERS:
            errors.append(f"rti_tier must be one of {VALID_RTI_TIERS}")
        if self.template_type == "cefr":
            if self.cefr_dimension not in VALID_CEFR_DIMENSIONS:
                errors.append("cefr template requires a valid cefr_dimension")
            if self.cefr_level_observed not in VALID_CEFR_LEVELS:
                errors.append("cefr template requires a valid cefr_level_observed")
        if self.template_type in ("sel_incident", "sel_positive"):
            if not self.sel_domain:
                errors.append("sel template requires sel_domain")
        if self.support_category is not None and self.support_category not in SUPPORT_CATEGORY_IDS:
            errors.append(f"support_category must be one of {SUPPORT_CATEGORY_IDS}")
        if self.strategy_outcome is not None and self.strategy_outcome not in VALID_STRATEGY_OUTCOMES:
            errors.append(f"strategy_outcome must be one of {VALID_STRATEGY_OUTCOMES}")
        if self.source_type is not None and self.source_type not in VALID_SOURCE_TYPES:
            errors.append(f"source_type must be one of {VALID_SOURCE_TYPES}")
        if not isinstance(self.support_entries, list):
            errors.append("support_entries must be a list")
        elif self.support_entries:
            normalized_count = len(normalize_support_entries(self.support_entries))
            if normalized_count != len(self.support_entries):
                errors.append("support_entries contains invalid entries")
        return errors

    def to_row(self) -> dict:
        return asdict(self)


class StudentLensStore:
    """
    SQLite-backed, offline-first store for student lenses + their
    append-only observation logs. One instance per device/school-server.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "StudentLensStore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @staticmethod
    def support_profile_default() -> dict:
        return support_profile_default()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS assessment_records (
                assessment_id TEXT PRIMARY KEY, student_id TEXT NOT NULL,
                teacher_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assessment_withdrawals (
                assessment_id TEXT PRIMARY KEY, teacher_id TEXT NOT NULL, recorded_at TEXT NOT NULL
            );
        """)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                display_name TEXT,
                campus TEXT,
                grade_level TEXT,
                home_languages TEXT NOT NULL DEFAULT '[]',
                learning_differences TEXT NOT NULL DEFAULT '[]',
                trauma_flag INTEGER NOT NULL DEFAULT 0,
                avoid_pairing_with TEXT NOT NULL DEFAULT '[]',
                rti_current_tier INTEGER NOT NULL DEFAULT 1,
                rti_tier_history TEXT NOT NULL DEFAULT '[]',
                cefr_snapshot TEXT NOT NULL DEFAULT '{}',
                cefr_trajectory_30d TEXT NOT NULL DEFAULT 'insufficient_data',
                sel_summary TEXT NOT NULL DEFAULT '{}',
                support_profile TEXT NOT NULL DEFAULT '{}',
                strengths_profile TEXT NOT NULL DEFAULT '{}',
                ethos_profile TEXT NOT NULL DEFAULT '{}',
                background_notes TEXT NOT NULL DEFAULT '',
                profile_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT
            );

            CREATE TABLE IF NOT EXISTS observations (
                observation_id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                teacher_id TEXT NOT NULL,
                template_type TEXT NOT NULL,
                raw_transcript TEXT NOT NULL,
                teacher_edited_transcript TEXT,
                recorded_at TEXT NOT NULL,
                rti_tier INTEGER,
                rti_tier_changed_this_obs INTEGER NOT NULL DEFAULT 0,
                cefr_dimension TEXT,
                cefr_level_observed TEXT,
                cefr_direction TEXT,
                sel_domain TEXT,
                sel_valence TEXT,
                urgency_flag INTEGER NOT NULL DEFAULT 0,
                ontology_node TEXT,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                validation_errors TEXT NOT NULL DEFAULT '[]',
                support_category TEXT,
                need_statement TEXT,
                strength_statement TEXT,
                strategy_statement TEXT,
                strategy_outcome TEXT,
                evidence_summary TEXT,
                source_type TEXT,
                support_entries TEXT NOT NULL DEFAULT '[]',
                classification_guidance TEXT,
                teacher_feedback TEXT,
                origin TEXT NOT NULL DEFAULT 'local',
                routing_decision_ids TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (student_id) REFERENCES students(student_id)
            );

            CREATE INDEX IF NOT EXISTS idx_obs_student
                ON observations(student_id, recorded_at);

            CREATE TABLE IF NOT EXISTS rti_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                decided_at TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(student_id)
            );

            CREATE TABLE IF NOT EXISTS evidence_records (
                evidence_id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                teacher_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                summary TEXT NOT NULL,
                source_ref TEXT,
                confidence_level TEXT NOT NULL,
                deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                FOREIGN KEY (student_id) REFERENCES students(student_id)
            );

            CREATE INDEX IF NOT EXISTS idx_evidence_student
                ON evidence_records(student_id, created_at);

            CREATE TABLE IF NOT EXISTS teacher_roster (
                teacher_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                added_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'observation',
                PRIMARY KEY (teacher_id, student_id)
            );
            """
        )
        # Backfill roster membership from observation history (Prepare-fix
        # P3b): before the teacher_roster table existed, "has observed" was
        # the only ownership signal. INSERT OR IGNORE keeps this idempotent
        # on every open; explicit roster rows always win over backfill.
        self._conn.execute(
            """
            INSERT OR IGNORE INTO teacher_roster (teacher_id, student_id, added_at, source)
            SELECT teacher_id, student_id, MIN(recorded_at), 'backfill:observation'
            FROM observations
            WHERE teacher_id != ''
            GROUP BY teacher_id, student_id
            """
        )
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA table_info(students)")
        columns = [row[1] for row in cursor.fetchall()]
        if "support_profile" not in columns:
            self._conn.execute(
                "ALTER TABLE students ADD COLUMN support_profile TEXT NOT NULL DEFAULT '{}'"
            )
        for col in ("strengths_profile", "ethos_profile"):
            if col not in columns:
                self._conn.execute(
                    f"ALTER TABLE students ADD COLUMN {col} TEXT NOT NULL DEFAULT '{{}}'"
                )
        if "background_notes" not in columns:
            self._conn.execute(
                "ALTER TABLE students ADD COLUMN background_notes TEXT NOT NULL DEFAULT ''"
            )
        cursor.execute("PRAGMA table_info(observations)")
        obs_columns = [row[1] for row in cursor.fetchall()]
        new_obs_cols = (
            "support_category",
            "need_statement",
            "strength_statement",
            "strategy_statement",
            "strategy_outcome",
            "evidence_summary",
            "source_type",
            "support_entries",
            "classification_guidance",
            "teacher_feedback",
        )
        for col in new_obs_cols:
            if col not in obs_columns:
                if col == "support_entries":
                    self._conn.execute(
                        "ALTER TABLE observations ADD COLUMN support_entries TEXT NOT NULL DEFAULT '[]'"
                    )
                else:
                    self._conn.execute(f"ALTER TABLE observations ADD COLUMN {col} TEXT")
        # Multi-teacher triangulation (SPEC_LV_MULTI_TEACHER_TRIANGULATION
        # 2026-08-01): provenance column. Existing rows are by definition
        # locally authored, so the default is correct for the migration.
        if "origin" not in obs_columns:
            self._conn.execute(
                "ALTER TABLE observations ADD COLUMN origin TEXT NOT NULL DEFAULT 'local'"
            )
        # Routing memory (SPEC_LV_ROUTING_MEMORY_LOOP_2026-08-01): decision
        # ids persisted on the observation row so correction hooks can pair
        # rows server-side. Ids only — never content. Pre-feature rows keep
        # '{}' and hooks skip them silently.
        if "routing_decision_ids" not in obs_columns:
            self._conn.execute(
                "ALTER TABLE observations ADD COLUMN routing_decision_ids TEXT NOT NULL DEFAULT '{}'"
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_lens(
        self,
        student_id: Optional[str] = None,
        display_name: str = "",
        campus: str = "",
        grade_level: str = "",
        home_languages: Optional[list[str]] = None,
        learning_differences: Optional[list[str]] = None,
        trauma_flag: bool = False,
        avoid_pairing_with: Optional[list[str]] = None,
        rti_current_tier: int = 1,
    ) -> str:
        """Create a new student lens. Returns the student_id."""
        if rti_current_tier not in VALID_RTI_TIERS:
            raise ObservationValidationError(
                f"rti_current_tier must be one of {VALID_RTI_TIERS}"
            )
        if student_id:
            # Creation-time namespace gate (SPEC_ONE_BUTTON_UPDATE_2026-07-27
            # Phase 4): caller-supplied IDs must not use the reserved shipped
            # `lv-` prefix — collisions are prevented by construction, never
            # discovered at update time (the Anki numeric-ID lesson).
            from src.lingua_viva.reconcile import validate_user_artifact_id

            ok, message = validate_user_artifact_id(student_id)
            if not ok:
                raise ObservationValidationError(message)
        student_id = student_id or str(uuid.uuid4())
        now = _now_iso()
        self._conn.execute(
            """
            INSERT INTO students (
                student_id, display_name, campus, grade_level,
                home_languages, learning_differences, trauma_flag,
                avoid_pairing_with,
                rti_current_tier, rti_tier_history, cefr_snapshot,
                cefr_trajectory_30d, sel_summary, support_profile,
                profile_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                student_id,
                display_name,
                campus,
                grade_level,
                json.dumps(home_languages or []),
                json.dumps(learning_differences or []),
                int(trauma_flag),
                json.dumps(avoid_pairing_with or []),
                rti_current_tier,
                json.dumps(
                    [{"tier": rti_current_tier, "from": now, "to": None, "trigger": None}]
                ),
                json.dumps({d: None for d in VALID_CEFR_DIMENSIONS}),
                "insufficient_data",
                json.dumps(
                    {
                        "recent_concerns": 0,
                        "recent_positives": 0,
                        "dominant_domain": None,
                        "last_urgency_flag": None,
                    }
                ),
                json.dumps(support_profile_default()),
                now,
                now,
            ),
        )
        self._conn.commit()
        return student_id

    def set_initial_cefr(
        self, student_id: str, cefr_level: str, teacher_id: str = "teacher:import"
    ) -> dict:
        """Teacher-declared starting CEFR level at import time (Prepare-fix
        P3c). Written as ordinary cefr observations (one per dimension), NOT
        a direct snapshot write: cefr_snapshot must stay derived from the
        append-only observation log so get_lens_as_of reconstruction holds —
        the same law that keeps rti_current_tier out of update_profile().
        Returns the refreshed lens dict."""
        level = str(cefr_level or "").strip()
        if level not in VALID_CEFR_LEVELS:
            raise ObservationValidationError(
                f"cefr_level must be one of {VALID_CEFR_LEVELS}"
            )
        row = self._get_student_row(student_id)
        if row is None:
            raise LensNotFoundError(student_id)
        for dimension in VALID_CEFR_DIMENSIONS:
            self.append_observation(
                Observation(
                    student_id=student_id,
                    teacher_id=str(teacher_id or "teacher:import") or "teacher:import",
                    template_type="cefr",
                    raw_transcript=(
                        f"Starting CEFR level {level} ({dimension}) set by the "
                        "teacher during import."
                    ),
                    cefr_dimension=dimension,
                    cefr_level_observed=level,
                    source_type="teacher_note",
                )
            )
        return self.get_lens(student_id)

    def set_avoid_pairing_with(self, student_id: str, avoid_ids: list[str]) -> None:
        """
        Teacher-set social-emotional grouping constraint ("kids cannot
        work if near a kid with conflict" — meeting notes, not academic
        data). This is a roster/relationship fact a teacher sets directly,
        not something derived from an observation, so it bypasses
        append_observation()'s recalculation path entirely. Full replace,
        not append — a teacher correcting/clearing a stale conflict is a
        normal, expected action (unlike an observation, this is not an
        append-only log).
        """
        row = self._get_student_row(student_id)
        if row is None:
            raise LensNotFoundError(student_id)
        self._conn.execute(
            "UPDATE students SET avoid_pairing_with = ?, updated_at = ? WHERE student_id = ?",
            (json.dumps(avoid_ids or []), _now_iso(), student_id),
        )
        self._conn.commit()

    # Fields a teacher may edit on an existing profile ("where can we add
    # any background info?" — SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES_2026-08-01).
    # Everything else (support_profile, CEFR aggregates, RTI history...) is
    # derived from observations or has its own audited write path. In
    # particular rti_current_tier is NOT editable here: tier changes must go
    # through update_rti_tier() so rti_tier_history stays reconstructable
    # (get_lens_as_of) — a PATCH bypass was caught in the 2026-08-01 review.
    UPDATABLE_PROFILE_FIELDS = (
        "campus",
        "grade_level",
        "home_languages",
        "learning_differences",
        "background_notes",
    )

    def update_profile(self, student_id: str, fields: dict) -> dict:
        """Teacher-directed edit of profile background fields. Accepts any
        subset of UPDATABLE_PROFILE_FIELDS; unknown keys are rejected with
        ValueError (never silently dropped). Bumps profile_version and
        updated_at. Returns the updated lens dict."""
        if not isinstance(fields, dict) or not fields:
            raise ValueError("fields must be a non-empty dict")
        unknown = [k for k in fields if k not in self.UPDATABLE_PROFILE_FIELDS]
        if unknown:
            raise ValueError(
                f"Unknown profile field(s) {unknown}. "
                f"Allowed: {self.UPDATABLE_PROFILE_FIELDS}"
            )
        row = self._get_student_row(student_id)
        if row is None:
            raise LensNotFoundError(student_id)

        assignments: list[str] = []
        params: list = []
        for key, value in fields.items():
            if key in ("home_languages", "learning_differences"):
                if not (
                    isinstance(value, list)
                    and all(isinstance(item, str) for item in value)
                ):
                    raise ValueError(f"{key} must be a list of strings")
                params.append(json.dumps(value))
            else:  # campus, grade_level, background_notes — free text
                if not isinstance(value, str):
                    raise ValueError(f"{key} must be a string")
                if len(value) > 10_000:
                    raise ValueError(f"{key} must be 10000 characters or fewer")
                params.append(value)
            assignments.append(f"{key} = ?")

        params.extend([_now_iso(), student_id])
        self._conn.execute(
            f"""
            UPDATE students SET
                {", ".join(assignments)},
                profile_version = profile_version + 1,
                updated_at = ?
            WHERE student_id = ?
            """,
            params,
        )
        self._conn.commit()
        return self.get_lens(student_id)

    def confirm_support_entry(
        self, student_id: str, category_id: str, bucket: str, entry_id: str
    ) -> dict:
        """Teacher confirms a model_suggested support-profile entry (the
        tap-to-confirm path). Flips confidence to teacher_confirmed in
        place — the ONLY way a suggestion becomes evidence-grade. Raises
        ValueError if the entry does not exist."""
        if category_id not in SUPPORT_CATEGORY_IDS:
            raise ValueError(
                f"Unknown category ID '{category_id}'. Allowed: {SUPPORT_CATEGORY_IDS}"
            )
        if bucket not in VALID_SUPPORT_BUCKETS:
            raise ValueError(
                f"Unknown bucket '{bucket}'. Allowed: {VALID_SUPPORT_BUCKETS}"
            )
        row = self._get_student_row(student_id)
        if row is None:
            raise LensNotFoundError(student_id)

        sp = self._row_to_lens_dict(row)["support_profile"]
        target = None
        for entry in sp["categories"][category_id][bucket]:
            if entry.get("id") == entry_id:
                target = entry
                break
        if target is None:
            raise ValueError(
                f"No entry '{entry_id}' in {category_id}/{bucket} for this student"
            )
        target["confidence"] = "teacher_confirmed"

        self._conn.execute(
            """
            UPDATE students SET
                support_profile = ?,
                profile_version = profile_version + 1,
                updated_at = ?
            WHERE student_id = ?
            """,
            (json.dumps(sp), _now_iso(), student_id),
        )
        self._conn.commit()
        return sp

    def dismiss_support_entry(
        self, student_id: str, category_id: str, bucket: str, entry_id: str,
        dismissed_by: str = "local-teacher",
    ) -> dict:
        """U8 (2026-09-04): the two-second undo for an automatic write. Marks
        one support-profile entry inactive (never deletes - the record stays
        auditable, and every reader already honours `active`). Idempotent.
        Unknown category / bucket / entry are named ValueErrors."""
        if category_id not in SUPPORT_CATEGORY_IDS:
            raise ValueError(
                f"Unknown category ID '{category_id}'. Allowed: {SUPPORT_CATEGORY_IDS}"
            )
        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)
        sp = self._row_to_lens_dict(row)["support_profile"]
        buckets = sp["categories"].get(category_id) or {}
        if bucket not in buckets or not isinstance(buckets.get(bucket), list):
            raise ValueError(
                f"Unknown bucket '{bucket}' in {category_id}. Allowed: {sorted(k for k, v in buckets.items() if isinstance(v, list))}"
            )
        target = next((e for e in buckets[bucket] if isinstance(e, dict) and e.get("id") == entry_id), None)
        if target is None:
            raise ValueError(f"No support entry '{entry_id}' in {category_id}/{bucket} for this student")
        if target.get("active", True) is not False:
            target["active"] = False
            target["dismissed_at"] = _now_iso()
            target["dismissed_by"] = _validate_non_empty_string(dismissed_by, "dismissed_by")
            now = _now_iso()
            self._conn.execute(
                """
                UPDATE students SET
                    support_profile = ?,
                    profile_version = profile_version + 1,
                    updated_at = ?
                WHERE student_id = ?
                """,
                (json.dumps(sp), now, student_id),
            )
            self._conn.commit()
        return sp

    def set_routing_decision_ids(self, observation_id: str, ids: dict) -> None:
        """Persist routing-memory decision ids on an observation row
        (SPEC_LV_ROUTING_MEMORY_LOOP_2026-08-01). Ids only — keys are
        decision types, values are decision-id strings. No-op on empty."""
        clean = {
            str(key): str(value)
            for key, value in (ids or {}).items()
            if value
        }
        if not clean or not observation_id:
            return
        self._conn.execute(
            "UPDATE observations SET routing_decision_ids = ? WHERE observation_id = ?",
            (json.dumps(clean), observation_id),
        )
        self._conn.commit()

    def routing_decision_ids_for_support_entry(
        self, student_id: str, category_id: str, bucket: str, entry_id: str
    ) -> dict:
        """Resolve the decision ids of the observation that fanned out a
        support entry (correction hooks pair rows server-side, so old
        clients need send nothing). Empty dict for pre-feature rows."""
        row = self._get_student_row(student_id)
        if row is None:
            return {}
        sp = self._row_to_lens_dict(row)["support_profile"]
        entries = sp.get("categories", {}).get(category_id, {}).get(bucket, [])
        obs_id = next(
            (
                entry.get("source_observation_id")
                for entry in entries
                if entry.get("id") == entry_id
            ),
            None,
        )
        if not obs_id:
            return {}
        cursor = self._conn.execute(
            "SELECT routing_decision_ids FROM observations WHERE observation_id = ?",
            (obs_id,),
        )
        result = cursor.fetchone()
        if result is None:
            return {}
        try:
            ids = json.loads(result[0] or "{}")
        except (TypeError, ValueError):
            return {}
        return ids if isinstance(ids, dict) else {}

    def record_rti_decision(self, student_id: str, decision: str, note: str = "") -> None:
        """Record a teacher's confirm/defer decision on an RTI proposal.

        This is a separate decision record, not an observation — it does NOT
        modify rti_tier_history or the append-only observation log.
        """
        if decision not in ("confirm", "defer"):
            raise ObservationValidationError(
                f"decision must be 'confirm' or 'defer', got '{decision}'"
            )
        row = self._get_student_row(student_id)
        if row is None:
            raise LensNotFoundError(student_id)
        self._conn.execute(
            "INSERT INTO rti_decisions (student_id, decision, note, decided_at) VALUES (?, ?, ?, ?)",
            (student_id, decision, note, _now_iso()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Append observation (the only way a lens changes)
    # ------------------------------------------------------------------

    def validate_observation_timestamp(self, obs: "Observation") -> list[str]:
        """Reject observations with timestamps in the future.

        Behavioral contracts (per tests/evals/CONTRACTS.md):
            - Returns empty list if timestamp is valid (<= now + 5 minutes tolerance)
            - Returns ["Observation timestamp is in the future"] if > now + 5 minutes
            - Does NOT block save (validation is advisory per existing convention)
            - "now" is UTC
        """
        try:
            recorded = datetime.fromisoformat(obs.recorded_at)
        except (TypeError, ValueError):
            return []
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        if recorded > datetime.now(timezone.utc) + timedelta(minutes=5):
            return ["Observation timestamp is in the future"]
        return []

    def append_observation(
        self, observation: Observation, duplicate_window_seconds: int = 0
    ) -> dict:
        """
        Append one observation to a student's history and recalculate the
        lens snapshot from it. Never overwrites or deletes prior
        observations. Returns {"observation": ..., "validation_errors": [...],
        "escalations": [...]}.
        """
        row = self._get_student_row(observation.student_id)
        if row is None:
            raise LensNotFoundError(observation.student_id)

        errors = observation.validate()
        errors.extend(self.validate_observation_timestamp(observation))

        duplicate_row = self._find_recent_duplicate_observation(
            observation, duplicate_window_seconds
        )
        if duplicate_row is not None:
            existing = self._observation_row_to_dict(duplicate_row)
            existing["duplicate"] = True
            existing["deduplicated"] = True
            return {
                "observation": existing,
                "validation_errors": existing.get("validation_errors", []),
                "escalations": [],
                "duplicate": True,
                "deduplicated": True,
                "feedback": {
                    "saved_entries": 0,
                    "categories_updated": [],
                    "message": "Already saved.",
                    "next_review_prompt": None,
                },
            }

        current_tier = row["rti_current_tier"]
        if observation.rti_tier is not None and observation.rti_tier != current_tier:
            observation.rti_tier_changed_this_obs = True
        elif observation.rti_tier is None:
            # default to current tier, matching Stage 1 UX: tier tag
            # pre-populates from the student's current status
            observation.rti_tier = current_tier

        self._conn.execute(
            """
            INSERT INTO observations (
                observation_id, student_id, teacher_id, template_type,
                raw_transcript, teacher_edited_transcript, recorded_at,
                rti_tier, rti_tier_changed_this_obs, cefr_dimension,
                cefr_level_observed, cefr_direction, sel_domain,
                sel_valence, urgency_flag, ontology_node, sync_status,
                validation_errors, support_category, need_statement,
                strength_statement, strategy_statement, strategy_outcome,
                evidence_summary, source_type, support_entries,
                classification_guidance, teacher_feedback
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.observation_id,
                observation.student_id,
                observation.teacher_id,
                observation.template_type,
                observation.raw_transcript,
                observation.teacher_edited_transcript,
                observation.recorded_at,
                observation.rti_tier,
                int(observation.rti_tier_changed_this_obs),
                observation.cefr_dimension,
                observation.cefr_level_observed,
                observation.cefr_direction,
                observation.sel_domain,
                observation.sel_valence,
                int(observation.urgency_flag),
                observation.ontology_node,
                observation.sync_status,
                json.dumps(errors),
                observation.support_category,
                observation.need_statement,
                observation.strength_statement,
                observation.strategy_statement,
                observation.strategy_outcome,
                observation.evidence_summary,
                observation.source_type,
                json.dumps(normalize_support_entries(observation.support_entries)),
                json.dumps(observation.classification_guidance)
                if observation.classification_guidance is not None
                else None,
                json.dumps(observation.teacher_feedback)
                if observation.teacher_feedback is not None
                else None,
            ),
        )
        # First observation registers roster membership (Prepare-fix P3b).
        if str(observation.teacher_id or "").strip():
            self._conn.execute(
                "INSERT OR IGNORE INTO teacher_roster (teacher_id, student_id, added_at, source) VALUES (?, ?, ?, 'observation')",
                (observation.teacher_id, observation.student_id, _now_iso()),
            )
        self._conn.commit()

        support_entries = normalize_support_entries(observation.support_entries)
        if not support_entries:
            support_entries = support_entry_from_scalar_fields(
                observation.support_category,
                observation.need_statement,
                observation.strength_statement,
                observation.strategy_statement,
                observation.strategy_outcome,
                observation.evidence_summary,
            )

        categories_updated = []
        saved_entries = 0
        for support_entry in support_entries:
            if support_entry.get("teacher_confirmed") is False:
                continue
            cat_id = support_entry["support_category"]
            obs_id = observation.observation_id
            created_by = observation.teacher_id
            context_tags = support_entry.get("context_tags") or {}
            source_ref_ids = [
                f"context:language:{context_tags.get('language', 'unknown')}",
                f"context:setting:{context_tags.get('setting', 'unknown')}",
            ]
            confidence = "teacher_confirmed"

            if support_entry.get("need_statement"):
                self.add_support_entry(
                    student_id=observation.student_id,
                    category_id=cat_id,
                    bucket="needs",
                    text=support_entry["need_statement"],
                    created_by=created_by,
                    source_observation_id=obs_id,
                    source_ref_ids=source_ref_ids,
                    confidence=confidence,
                )
                saved_entries += 1

            if support_entry.get("strength_statement"):
                self.add_support_entry(
                    student_id=observation.student_id,
                    category_id=cat_id,
                    bucket="strengths",
                    text=support_entry["strength_statement"],
                    created_by=created_by,
                    source_observation_id=obs_id,
                    source_ref_ids=source_ref_ids,
                    confidence=confidence,
                )
                saved_entries += 1

            if support_entry.get("strategy_statement"):
                outcome = support_entry.get("strategy_outcome")
                if outcome == "worked":
                    self.add_support_entry(
                        student_id=observation.student_id,
                        category_id=cat_id,
                        bucket="strategies_worked",
                        text=support_entry["strategy_statement"],
                        created_by=created_by,
                        source_observation_id=obs_id,
                        source_ref_ids=source_ref_ids,
                        confidence=confidence,
                    )
                    saved_entries += 1
                elif outcome == "did_not_work":
                    self.add_support_entry(
                        student_id=observation.student_id,
                        category_id=cat_id,
                        bucket="strategies_not_worked",
                        text=support_entry["strategy_statement"],
                        created_by=created_by,
                        source_observation_id=obs_id,
                        source_ref_ids=source_ref_ids,
                        confidence=confidence,
                    )
                    saved_entries += 1

            if support_entry.get("evidence_summary"):
                self.add_support_evidence(
                    student_id=observation.student_id,
                    category_id=cat_id,
                    summary=support_entry["evidence_summary"],
                    created_by=created_by,
                    evidence_type=observation.source_type or "observation",
                    source_observation_id=obs_id,
                    source_ref_ids=source_ref_ids,
                )
                saved_entries += 1
            if cat_id not in categories_updated:
                categories_updated.append(cat_id)

        self._recalculate_lens(observation.student_id, observation)
        refreshed_lens = self.get_lens(observation.student_id)
        escalations = self._evaluate_rti_rules(observation.student_id)

        return {
            "observation": observation.to_row(),
            "validation_errors": errors,
            "escalations": escalations,
            "lens_refresh": {
                "student_id": observation.student_id,
                "profile_version": refreshed_lens["profile_version"],
                "updated_at": refreshed_lens["updated_at"],
                "cefr_snapshot": refreshed_lens["cefr_snapshot"],
                "cefr_trajectory_30d": refreshed_lens["cefr_trajectory_30d"],
                "rti_current_tier": refreshed_lens["rti_current_tier"],
                "sel_summary": refreshed_lens["sel_summary"],
            },
            "feedback": {
                "saved_entries": saved_entries,
                "categories_updated": categories_updated,
                "message": _support_feedback_message(categories_updated, saved_entries),
                "next_review_prompt": _support_next_review_prompt(support_entries),
            },
        }

    def _find_recent_duplicate_observation(
        self, observation: Observation, duplicate_window_seconds: int
    ) -> Optional[sqlite3.Row]:
        if duplicate_window_seconds <= 0:
            return None
        try:
            recorded = datetime.fromisoformat(observation.recorded_at)
        except (TypeError, ValueError):
            recorded = datetime.now(timezone.utc)
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        cutoff = (recorded - timedelta(seconds=duplicate_window_seconds)).isoformat()
        return self._conn.execute(
            """
            SELECT * FROM observations
            WHERE student_id = ?
              AND teacher_id = ?
              AND template_type = ?
              AND raw_transcript = ?
              AND recorded_at >= ?
              AND recorded_at <= ?
            ORDER BY recorded_at DESC, observation_id DESC
            LIMIT 1
            """,
            (
                observation.student_id,
                observation.teacher_id,
                observation.template_type,
                observation.raw_transcript,
                cutoff,
                recorded.isoformat(),
            ),
        ).fetchone()

    # ------------------------------------------------------------------
    # Read / export / delete (teacher rights)
    # ------------------------------------------------------------------

    def get_lens(self, student_id: str) -> dict:
        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)
        return self._row_to_lens_dict(row)

    def export_lens(self, student_id: str) -> dict:
        """Full export: lens snapshot + complete observation history.
        This is the teacher's export right — the raw record, unfiltered."""
        row = self._get_student_row(student_id, include_deleted=True)
        if row is None:
            raise LensNotFoundError(student_id)
        lens = self._row_to_lens_dict(row)
        obs_rows = self._conn.execute(
            "SELECT * FROM observations WHERE student_id = ? ORDER BY recorded_at ASC",
            (student_id,),
        ).fetchall()
        lens["observations"] = [self._observation_row_to_dict(r) for r in obs_rows]
        return lens

    def append_assessment(self, student_id: str, value: dict, teacher_id: str) -> None:
        from src.lingua_viva.assessment_data import validate_assessment
        refusal = validate_assessment(value)
        if refusal:
            raise ValueError(refusal)
        self.get_lens(student_id)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        existing = self._conn.execute(
            "SELECT student_id, payload FROM assessment_records WHERE assessment_id = ?", (value['assessment_id'],)
        ).fetchone()
        if existing:
            if existing['student_id'] != student_id or existing['payload'] != encoded:
                raise ValueError('Use a new revision identifier to change an assessment.')
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute('INSERT INTO assessment_records VALUES (?, ?, ?, ?, ?)',
                               (value['assessment_id'], student_id, teacher_id, now, encoded))
            self._conn.execute('UPDATE students SET profile_version = profile_version + 1, updated_at = ? WHERE student_id = ?',
                               (now, student_id))

    def withdraw_assessment(self, student_id: str, assessment_id: str, teacher_id: str) -> None:
        row = self._conn.execute('SELECT student_id FROM assessment_records WHERE assessment_id = ?', (assessment_id,)).fetchone()
        if row is None or row['student_id'] != student_id:
            raise ValueError('Assessment not found for this student.')
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            changed = self._conn.execute('INSERT OR IGNORE INTO assessment_withdrawals VALUES (?, ?, ?)',
                                        (assessment_id, teacher_id, now)).rowcount
            if changed:
                self._conn.execute('UPDATE students SET profile_version = profile_version + 1, updated_at = ? WHERE student_id = ?',
                                   (now, student_id))

    def export_lens_view(self, student_id: str, audience: str = "teacher") -> dict:
        """Share-scoped lens view for teacher/family/HR PDFs.

        Family and teacher views exclude Personal Context and unconfirmed
        evidence. HR view includes Personal Context but still excludes raw
        observation narration from the PDF-ready view.
        """
        audience = audience if audience in LENS_SHARE_AUDIENCES else "teacher"
        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)
        lens = self._row_to_lens_dict(row)
        keep = {
            "student_id",
            "display_name",
            "campus",
            "grade_level",
            "home_languages",
            "cefr_snapshot",
            "cefr_trajectory_30d",
            "rti_current_tier",
            "updated_at",
            "profile_version",
        }
        view = {key: lens.get(key) for key in keep}
        view["support_profile"] = support_profile_for_audience(lens.get("support_profile") or {}, audience)
        view["share_scope"] = {
            "audience": audience,
            "personal_context_included": audience == "hr",
            "raw_observations_included": False,
            "unconfirmed_evidence_included": False,
        }
        return view

    def delete_lens(self, student_id: str, hard: bool = False) -> None:
        """
        Teacher delete right. Default is a soft tombstone (deleted=1,
        excluded from get_lens / normal reads, still exportable for
        audit). hard=True permanently purges the student row and every
        observation — irreversible, must be an explicit caller choice.
        """
        row = self._get_student_row(student_id, include_deleted=True)
        if row is None:
            raise LensNotFoundError(student_id)
        if hard:
            self._conn.execute(
                "DELETE FROM observations WHERE student_id = ?", (student_id,)
            )
            self._conn.execute(
                "DELETE FROM students WHERE student_id = ?", (student_id,)
            )
        else:
            self._conn.execute(
                "UPDATE students SET deleted = 1, deleted_at = ? WHERE student_id = ?",
                (_now_iso(), student_id),
            )
        self._conn.commit()

    def list_lenses(self, campus: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM students WHERE deleted = 0"
        params: tuple = ()
        if campus:
            query += " AND campus = ?"
            params = (campus,)
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_lens_dict(r) for r in rows]

    def add_to_roster(self, teacher_id: str, student_id: str, source: str = "manual") -> None:
        """Register a student on a teacher's roster (idempotent). Sources:
        'observation' (first observation), 'ingest' (document import),
        'backfill:observation' (schema migration), 'manual'."""
        teacher = str(teacher_id or "").strip()
        student = str(student_id or "").strip()
        if not teacher or not student:
            return
        self._conn.execute(
            "INSERT OR IGNORE INTO teacher_roster (teacher_id, student_id, added_at, source) VALUES (?, ?, ?, ?)",
            (teacher, student, _now_iso(), str(source or "manual")),
        )
        self._conn.commit()

    def list_lenses_for_teacher(self, teacher_id: str) -> list[dict]:
        """
        A teacher's roster: every non-deleted student on the teacher_roster
        table for this teacher_id, union every student this teacher has
        recorded at least one observation for (the pre-roster ownership
        signal, kept live so the cross-teacher view — same question,
        different teacher_id — still works). Prepare-fix P3b fallback:
        a teacher with NO roster and NO observations sees ALL active
        students rather than an inexplicable empty Prepare view — a fresh
        single-teacher install must work before any observation exists.
        """
        rows = self._conn.execute(
            """
            SELECT s.* FROM students s
            WHERE s.deleted = 0
              AND (
                  s.student_id IN (
                      SELECT student_id FROM teacher_roster WHERE teacher_id = ?
                  )
                  OR s.student_id IN (
                      SELECT DISTINCT student_id FROM observations WHERE teacher_id = ?
                  )
              )
            """,
            (teacher_id, teacher_id),
        ).fetchall()
        if not rows:
            return self.list_lenses()
        return [self._row_to_lens_dict(r) for r in rows]

    def teachers_for_student(self, student_id: str) -> list[str]:
        """All teacher_ids who have recorded at least one observation for
        this student — the basis for the cross-teacher shared-student view."""
        rows = self._conn.execute(
            "SELECT DISTINCT teacher_id FROM observations WHERE student_id = ? ORDER BY teacher_id",
            (student_id,),
        ).fetchall()
        return [r["teacher_id"] for r in rows]

    # ------------------------------------------------------------------
    # Multi-teacher triangulation (SPEC_LV_MULTI_TEACHER_TRIANGULATION
    # 2026-08-01): ledger export rows, append-only union import, and
    # per-colleague removal. Merge rule: known UUID -> skip. Two teachers'
    # observations are two facts, never a conflict to resolve.
    # ------------------------------------------------------------------

    def local_observation_rows(self, student_id: str, teacher_id: str) -> list[dict]:
        """This teacher's locally-authored observation rows for a student,
        shaped for the shared-Drive ledger (Observation schema fields only —
        the local `origin` provenance column never travels).

        DOES boundary: this is the one place a local observation becomes a
        row that can leave the machine, so this is where narration gets
        neutralized — `raw_transcript` / `teacher_edited_transcript` are
        always overwritten with a fixed, non-informative marker
        (NARRATION_NOT_SHARED), never passed through, regardless of
        content. Spoken/typed narration is exactly where causal ("why")
        language shows up (the specific trauma, the family history behind
        a need) — the categorized fields (support_category,
        need_statement, strength_statement, strategy_statement,
        evidence_summary, support_entries) describe *what* a student
        needs inside a fixed category vocabulary and travel intact; that
        distinction, not a name or a keyword scan, is the actual privacy
        boundary. See dev/SPEC_LENS_PRIMITIVE_2026-08-04.md.
        """
        field_names = {f.name for f in dataclass_fields(Observation)}
        rows = self._conn.execute(
            "SELECT * FROM observations WHERE student_id = ? AND teacher_id = ?"
            " AND origin = 'local' ORDER BY recorded_at ASC",
            (student_id, teacher_id),
        ).fetchall()
        shareable = []
        for r in rows:
            row = {k: v for k, v in self._observation_row_to_dict(r).items() if k in field_names}
            row["raw_transcript"] = NARRATION_NOT_SHARED
            row["teacher_edited_transcript"] = None
            shareable.append(row)
        return shareable

    def local_teacher_ids(self, student_id: Optional[str] = None) -> list[str]:
        """Teacher ids with locally-authored observations — 'us', as opposed
        to colleagues whose rows arrived via ledger import."""
        query = "SELECT DISTINCT teacher_id FROM observations WHERE origin = 'local'"
        params: tuple = ()
        if student_id:
            query += " AND student_id = ?"
            params = (student_id,)
        return [r["teacher_id"] for r in self._conn.execute(query, params).fetchall()]

    def import_observation_rows(self, rows: list[dict]) -> dict:
        """Append-only union merge of colleague ledger rows.

        Per row: validate against the Observation schema, skip unknown
        students and known UUIDs, insert with origin='imported' and the
        original teacher_id intact, and fan support entries into the
        category rollups at imported_verified confidence. Aggregates are
        recomputed once per affected student at the end, not per row —
        which also makes partial imports safe (merge is idempotent).
        """
        field_names = {f.name for f in dataclass_fields(Observation)}
        imported = 0
        skipped = 0
        affected: set[str] = set()
        for raw in rows or []:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            filtered = {k: raw[k] for k in field_names if k in raw}
            try:
                obs = Observation(**filtered)
            except TypeError:
                skipped += 1
                continue
            if obs.validate():
                skipped += 1
                continue
            if self._get_student_row(obs.student_id) is None:
                skipped += 1
                continue
            exists = self._conn.execute(
                "SELECT 1 FROM observations WHERE observation_id = ?",
                (obs.observation_id,),
            ).fetchone()
            if exists is not None:
                # Known UUID — never overwrite, never touch local rows.
                skipped += 1
                continue
            self._conn.execute(
                """
                INSERT INTO observations (
                    observation_id, student_id, teacher_id, template_type,
                    raw_transcript, teacher_edited_transcript, recorded_at,
                    rti_tier, rti_tier_changed_this_obs, cefr_dimension,
                    cefr_level_observed, cefr_direction, sel_domain,
                    sel_valence, urgency_flag, ontology_node, sync_status,
                    validation_errors, support_category, need_statement,
                    strength_statement, strategy_statement, strategy_outcome,
                    evidence_summary, source_type, support_entries,
                    classification_guidance, teacher_feedback, origin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported')
                """,
                (
                    obs.observation_id,
                    obs.student_id,
                    obs.teacher_id,
                    obs.template_type,
                    obs.raw_transcript,
                    obs.teacher_edited_transcript,
                    obs.recorded_at,
                    obs.rti_tier,
                    int(obs.rti_tier_changed_this_obs),
                    obs.cefr_dimension,
                    obs.cefr_level_observed,
                    obs.cefr_direction,
                    obs.sel_domain,
                    obs.sel_valence,
                    int(obs.urgency_flag),
                    obs.ontology_node,
                    obs.sync_status,
                    "[]",
                    obs.support_category,
                    obs.need_statement,
                    obs.strength_statement,
                    obs.strategy_statement,
                    obs.strategy_outcome,
                    obs.evidence_summary,
                    obs.source_type,
                    json.dumps(normalize_support_entries(obs.support_entries)),
                    json.dumps(obs.classification_guidance)
                    if obs.classification_guidance is not None
                    else None,
                    json.dumps(obs.teacher_feedback)
                    if obs.teacher_feedback is not None
                    else None,
                ),
            )
            self._fan_out_support(obs, confidence="imported_verified")
            affected.add(obs.student_id)
            imported += 1
        for sid in affected:
            self._recalculate_aggregates(sid)
        self._conn.commit()
        return {"imported": imported, "skipped": skipped}

    def remove_imported(self, student_id: str, teacher_id: str) -> dict:
        """Delete exactly this colleague's imported rows for this student —
        the teacher's 'remove colleague data' right. Local rows and other
        colleagues' rows are untouched; category-rollup entries traced to
        the removed observations go with them."""
        removed_ids = {
            r["observation_id"]
            for r in self._conn.execute(
                "SELECT observation_id FROM observations WHERE student_id = ?"
                " AND teacher_id = ? AND origin = 'imported'",
                (student_id, teacher_id),
            ).fetchall()
        }
        if not removed_ids:
            return {"removed": 0}
        self._conn.execute(
            "DELETE FROM observations WHERE student_id = ? AND teacher_id = ?"
            " AND origin = 'imported'",
            (student_id, teacher_id),
        )
        row = self._get_student_row(student_id, include_deleted=True)
        if row is not None:
            sp = self._row_to_lens_dict(row)["support_profile"]
            changed = False
            for category in (sp.get("categories") or {}).values():
                for bucket in (*VALID_SUPPORT_BUCKETS, "evidence"):
                    items = category.get(bucket)
                    if not isinstance(items, list):
                        continue
                    kept = [
                        item for item in items
                        if item.get("source_observation_id") not in removed_ids
                    ]
                    if len(kept) != len(items):
                        category[bucket] = kept
                        changed = True
            if changed:
                self._conn.execute(
                    "UPDATE students SET support_profile = ?,"
                    " profile_version = profile_version + 1, updated_at = ?"
                    " WHERE student_id = ?",
                    (json.dumps(sp), _now_iso(), student_id),
                )
        self._recalculate_aggregates(student_id)
        self._conn.commit()
        return {"removed": len(removed_ids)}

    def rename_local_teacher(self, old_id: str, new_id: str) -> dict:
        """Backfill for teacher-identity provisioning (P1, 2026-08-02):
        re-attribute locally-authored rows from old_id — typically the
        un-provisioned "local-teacher" sentinel every pre-identity write
        defaulted to — to the newly configured id, so triangulation
        authorship and future ledger exports carry the real identity.

        Surgical by construction: only origin='local' observations are
        renamed, and profile entries are skipped when their
        source_observation_id traces to an imported row, so a colleague's
        attribution can never be rewritten."""
        old_id = _validate_non_empty_string(old_id, "old_id")
        new_id = _validate_non_empty_string(new_id, "new_id")
        if old_id == new_id:
            return {"renamed": 0}
        imported_ids = {
            r["observation_id"]
            for r in self._conn.execute(
                "SELECT observation_id FROM observations WHERE origin = 'imported'"
            ).fetchall()
        }
        cursor = self._conn.execute(
            "UPDATE observations SET teacher_id = ?"
            " WHERE teacher_id = ? AND origin = 'local'",
            (new_id, old_id),
        )
        renamed = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        # evidence_records rows are only ever written by local teacher
        # actions (imports fan out into the support_profile JSON instead),
        # so a flat rename is safe here.
        self._conn.execute(
            "UPDATE evidence_records SET teacher_id = ? WHERE teacher_id = ?",
            (new_id, old_id),
        )
        student_rows = self._conn.execute("SELECT student_id FROM students").fetchall()
        for srow in student_rows:
            student_id = srow["student_id"]
            row = self._get_student_row(student_id, include_deleted=True)
            if row is None:
                continue
            lens = self._row_to_lens_dict(row)
            sp = lens["support_profile"]
            changed = False
            for category in (sp.get("categories") or {}).values():
                for bucket in (*VALID_SUPPORT_BUCKETS, "evidence"):
                    items = category.get(bucket)
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if (
                            isinstance(item, dict)
                            and item.get("created_by") == old_id
                            and item.get("source_observation_id") not in imported_ids
                        ):
                            item["created_by"] = new_id
                            changed = True
            strengths = lens["strengths_profile"]
            for key in ("academic_strengths", "personal_strengths"):
                for item in strengths.get(key) or []:
                    if isinstance(item, dict) and item.get("created_by") == old_id:
                        item["created_by"] = new_id
                        changed = True
            if strengths.get("last_reviewed_by") == old_id:
                strengths["last_reviewed_by"] = new_id
                changed = True
            if changed:
                self._conn.execute(
                    "UPDATE students SET support_profile = ?, strengths_profile = ?,"
                    " profile_version = profile_version + 1, updated_at = ?"
                    " WHERE student_id = ?",
                    (json.dumps(sp), json.dumps(strengths), _now_iso(), student_id),
                )
        self._conn.commit()
        return {"renamed": renamed}

    def _fan_out_support(self, obs: Observation, confidence: str) -> None:
        """Category-rollup fan-out for one observation (mirrors
        append_observation's inline fan-out, at the caller's confidence)."""
        entries = normalize_support_entries(obs.support_entries)
        if not entries:
            entries = support_entry_from_scalar_fields(
                obs.support_category,
                obs.need_statement,
                obs.strength_statement,
                obs.strategy_statement,
                obs.strategy_outcome,
                obs.evidence_summary,
            )
        bucket_map = {
            "need_statement": "needs",
            "strength_statement": "strengths",
        }
        for entry in entries:
            if entry.get("teacher_confirmed") is False:
                continue
            cat_id = entry["support_category"]
            tags = entry.get("context_tags") or {}
            refs = [
                f"context:language:{tags.get('language', 'unknown')}",
                f"context:setting:{tags.get('setting', 'unknown')}",
            ]
            for statement_key, bucket in bucket_map.items():
                if entry.get(statement_key):
                    self.add_support_entry(
                        student_id=obs.student_id,
                        category_id=cat_id,
                        bucket=bucket,
                        text=entry[statement_key],
                        created_by=obs.teacher_id,
                        source_observation_id=obs.observation_id,
                        source_ref_ids=refs,
                        confidence=confidence,
                    )
            if entry.get("strategy_statement"):
                outcome = entry.get("strategy_outcome")
                strategy_bucket = {
                    "worked": "strategies_worked",
                    "did_not_work": "strategies_not_worked",
                }.get(outcome)
                if strategy_bucket:
                    self.add_support_entry(
                        student_id=obs.student_id,
                        category_id=cat_id,
                        bucket=strategy_bucket,
                        text=entry["strategy_statement"],
                        created_by=obs.teacher_id,
                        source_observation_id=obs.observation_id,
                        source_ref_ids=refs,
                        confidence=confidence,
                    )
            if entry.get("evidence_summary"):
                self.add_support_evidence(
                    student_id=obs.student_id,
                    category_id=cat_id,
                    summary=entry["evidence_summary"],
                    created_by=obs.teacher_id,
                    evidence_type=obs.source_type or "observation",
                    source_observation_id=obs.observation_id,
                    source_ref_ids=refs,
                )

    def _recalculate_aggregates(self, student_id: str) -> None:
        """Rebuild history-derived aggregates (CEFR snapshot, trajectory,
        SEL summary) from the full observation table — imported rows enter
        naturally. Deliberately does NOT touch rti_current_tier or
        rti_tier_history: the tier is a local human decision, and a
        colleague's tier view surfaces as a divergence signal in the
        triangulation view instead of silently changing local state."""
        row = self._get_student_row(student_id, include_deleted=True)
        if row is None:
            return
        obs_rows = self._conn.execute(
            "SELECT * FROM observations WHERE student_id = ? ORDER BY recorded_at DESC",
            (student_id,),
        ).fetchall()
        snapshot: dict = {}
        for r in obs_rows:
            dim = r["cefr_dimension"]
            if dim and r["cefr_level_observed"] and dim not in snapshot:
                snapshot[dim] = r["cefr_level_observed"]
        recent = [dict(r) for r in obs_rows[:50]]
        concerns = sum(1 for o in recent if o["sel_valence"] == "concern")
        positives = sum(1 for o in recent if o["sel_valence"] == "positive")
        domains = [o["sel_domain"] for o in recent if o["sel_domain"]]
        dominant = max(set(domains), key=domains.count) if domains else None
        last_urgency = next((o["recorded_at"] for o in recent if o["urgency_flag"]), None)
        self._conn.execute(
            """
            UPDATE students SET
                cefr_snapshot = ?, cefr_trajectory_30d = ?, sel_summary = ?,
                profile_version = profile_version + 1, updated_at = ?
            WHERE student_id = ?
            """,
            (
                json.dumps(snapshot),
                self._compute_cefr_trajectory(student_id),
                json.dumps({
                    "recent_concerns": concerns,
                    "recent_positives": positives,
                    "dominant_domain": dominant,
                    "last_urgency_flag": last_urgency,
                }),
                _now_iso(),
                student_id,
            ),
        )
        self._conn.commit()

    def evaluate_rti_rules(self, student_id: str) -> list[dict]:
        """Public wrapper: re-evaluate RTI escalation rules A-E against a
        student's current stored history, without appending a new
        observation. Used for proactive surfacing (morning brief, alert
        sweep) where we need to know "is this student currently flagged"
        independent of whichever observation last triggered the rule."""
        return self._evaluate_rti_rules(student_id)

    def update_rti_tier(self, student_id: str, new_tier: int, trigger: str) -> None:
        """Manually change a student's RTI tier, with an audit trail.

        Distinct from the tier changes that ride along with an observation
        (see _recalculate_lens's rti_tier_changed_this_obs branch): this is
        a teacher decision made independent of any single observation
        (e.g. a team meeting decision), so it closes/opens
        rti_tier_history entries directly rather than going through
        append_observation(). Never touches cefr_snapshot or observations
        — an RTI tier change is a decision about intervention intensity,
        not a claim about language ability.
        """
        if new_tier not in VALID_RTI_TIERS:
            raise ValueError(f"new_tier must be one of {VALID_RTI_TIERS}")
        row = self._get_student_row(student_id)
        if row is None:
            raise LensNotFoundError(student_id)

        lens = self._row_to_lens_dict(row)
        now = _now_iso()
        history = lens["rti_tier_history"]
        if history and history[-1]["to"] is None:
            history[-1]["to"] = now
        history.append({"tier": new_tier, "from": now, "to": None, "trigger": trigger})

        self._conn.execute(
            """
            UPDATE students SET
                rti_current_tier = ?, rti_tier_history = ?,
                profile_version = profile_version + 1, updated_at = ?
            WHERE student_id = ?
            """,
            (new_tier, json.dumps(history), now, student_id),
        )
        self._conn.commit()

    def get_lens_as_of(self, student_id: str, as_of: str) -> dict:
        """Return the lens as it stood at a specific point in time.

        Reconstructs cefr_snapshot and rti_current_tier from the
        append-only observations/history logs, bounded to
        recorded_at/from <= as_of, rather than mutating live state — the
        append-only log is the source of truth and this is purely a
        read-time projection over it.
        """
        try:
            datetime.fromisoformat(as_of)
        except (TypeError, ValueError):
            raise ValueError(f"as_of must be a valid ISO8601 timestamp, got {as_of!r}")

        row = self._get_student_row(student_id, include_deleted=True)
        if row is None:
            raise LensNotFoundError(student_id)
        lens = self._row_to_lens_dict(row)

        obs_rows = self._conn.execute(
            "SELECT * FROM observations WHERE student_id = ? AND recorded_at <= ? "
            "ORDER BY recorded_at ASC",
            (student_id, as_of),
        ).fetchall()
        obs = [dict(r) for r in obs_rows]

        # CEFR snapshot: latest observed level per dimension, as of that time
        cefr_snapshot = {d: None for d in VALID_CEFR_DIMENSIONS}
        for o in obs:
            if o["cefr_dimension"] and o["cefr_level_observed"]:
                cefr_snapshot[o["cefr_dimension"]] = o["cefr_level_observed"]
        lens["cefr_snapshot"] = cefr_snapshot

        # RTI tier: whichever history entry was open ("to" is None or > as_of)
        # at as_of. rti_tier_history entries are already chronological.
        current_tier = lens["rti_current_tier"]
        for entry in lens["rti_tier_history"]:
            if entry["from"] <= as_of and (entry["to"] is None or entry["to"] > as_of):
                current_tier = entry["tier"]
                break
        lens["rti_current_tier"] = current_tier

        return lens

    # ------------------------------------------------------------------
    # Support profile v2 methods
    # ------------------------------------------------------------------

    def get_support_profile(self, student_id: str) -> dict:
        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)
        lens = self._row_to_lens_dict(row)
        return lens["support_profile"]

    def replace_support_profile(
        self, student_id: str, profile: dict, reviewed_by: Optional[str] = None
    ) -> dict:
        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)
        _validate_support_profile(profile)
        reviewed_by = _validate_non_empty_string(reviewed_by, "reviewed_by")

        now = _now_iso()
        normalized = _normalize_support_profile(profile)
        normalized["last_reviewed_at"] = now
        if reviewed_by is not None:
            normalized["last_reviewed_by"] = reviewed_by

        self._conn.execute(
            """
            UPDATE students SET
                support_profile = ?,
                profile_version = profile_version + 1,
                updated_at = ?
            WHERE student_id = ?
            """,
            (json.dumps(normalized), now, student_id),
        )
        self._conn.commit()
        return normalized

    def add_support_entry(
        self,
        student_id: str,
        category_id: str,
        bucket: str,
        text: str,
        created_by: str,
        source_observation_id: Optional[str] = None,
        source_ref_ids: Optional[list[str]] = None,
        confidence: str = "teacher_confirmed",
    ) -> dict:
        if category_id not in SUPPORT_CATEGORY_IDS:
            raise ValueError(
                f"Unknown category ID '{category_id}'. Allowed: {SUPPORT_CATEGORY_IDS}"
            )
        if bucket not in VALID_SUPPORT_BUCKETS:
            raise ValueError(
                f"Unknown bucket '{bucket}'. Allowed: {VALID_SUPPORT_BUCKETS}"
            )
        if not (isinstance(text, str) and text.strip() and len(text) <= 2000):
            raise ValueError("Entry text must be non-empty and <= 2000 characters")
        if confidence not in VALID_CONFIDENCE_VALUES:
            raise ValueError(
                f"Invalid confidence '{confidence}'. Allowed: {VALID_CONFIDENCE_VALUES}"
            )
        created_by = _validate_non_empty_string(created_by, "created_by")
        source_observation_id = _validate_non_empty_string(
            source_observation_id, "source_observation_id"
        )

        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)

        sp = self._row_to_lens_dict(row)["support_profile"]
        entry = {
            "id": str(uuid.uuid4()),
            "text": text,
            "created_at": _now_iso(),
            "created_by": created_by,
            "source_observation_id": source_observation_id,
            "source_ref_ids": _validate_source_ref_ids(source_ref_ids),
            "confidence": confidence,
            "active": True,
        }
        sp["categories"][category_id][bucket].append(entry)

        now = _now_iso()
        self._conn.execute(
            """
            UPDATE students SET
                support_profile = ?,
                profile_version = profile_version + 1,
                updated_at = ?
            WHERE student_id = ?
            """,
            (json.dumps(sp), now, student_id),
        )
        self._conn.commit()
        return sp

    def add_support_evidence(
        self,
        student_id: str,
        category_id: str,
        summary: str,
        created_by: str,
        evidence_type: str = "observation",
        source_observation_id: Optional[str] = None,
        source_ref_ids: Optional[list[str]] = None,
    ) -> dict:
        if category_id not in SUPPORT_CATEGORY_IDS:
            raise ValueError(
                f"Unknown category ID '{category_id}'. Allowed: {SUPPORT_CATEGORY_IDS}"
            )
        if not (isinstance(summary, str) and summary.strip() and len(summary) <= 2000):
            raise ValueError("Evidence summary must be non-empty and <= 2000 characters")
        if evidence_type not in VALID_EVIDENCE_TYPES:
            raise ValueError(
                f"Invalid evidence_type '{evidence_type}'. Allowed: {VALID_EVIDENCE_TYPES}"
            )
        created_by = _validate_non_empty_string(created_by, "created_by")
        source_observation_id = _validate_non_empty_string(
            source_observation_id, "source_observation_id"
        )

        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)

        sp = self._row_to_lens_dict(row)["support_profile"]
        item = {
            "id": str(uuid.uuid4()),
            "summary": summary,
            "evidence_type": evidence_type,
            "source_observation_id": source_observation_id,
            "source_ref_ids": _validate_source_ref_ids(source_ref_ids),
            "created_at": _now_iso(),
            "created_by": created_by,
        }
        sp["categories"][category_id]["evidence"].append(item)

        now = _now_iso()
        self._conn.execute(
            """
            UPDATE students SET
                support_profile = ?,
                profile_version = profile_version + 1,
                updated_at = ?
            WHERE student_id = ?
            """,
            (json.dumps(sp), now, student_id),
        )
        self._conn.commit()
        return sp

    # ------------------------------------------------------------------
    # v2.1: profile-level strengths + ethos trait evidence
    # ------------------------------------------------------------------

    def add_profile_strength(
        self,
        student_id: str,
        kind: str,
        text: str,
        created_by: str,
        source_observation_id: Optional[str] = None,
        source_ref_ids: Optional[list[str]] = None,
        confidence: str = "teacher_confirmed",
    ) -> dict:
        """Append an entry to the profile-level Academic/Personal Strengths."""
        if kind not in VALID_STRENGTH_KINDS:
            raise ValueError(
                f"Unknown strength kind '{kind}'. Allowed: {VALID_STRENGTH_KINDS}"
            )
        if not (isinstance(text, str) and text.strip() and len(text) <= 2000):
            raise ValueError("Entry text must be non-empty and <= 2000 characters")
        if confidence not in VALID_CONFIDENCE_VALUES:
            raise ValueError(
                f"Invalid confidence '{confidence}'. Allowed: {VALID_CONFIDENCE_VALUES}"
            )
        created_by = _validate_non_empty_string(created_by, "created_by")
        source_observation_id = _validate_non_empty_string(
            source_observation_id, "source_observation_id"
        )

        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)

        profile = self._row_to_lens_dict(row)["strengths_profile"]
        text = text.strip()
        # Idempotency: an identical active entry (same text + source) is a
        # double-submit, not new information — return unchanged, no
        # profile_version bump.
        for existing in profile[f"{kind}_strengths"]:
            if (
                existing.get("text") == text
                and existing.get("source_observation_id") == source_observation_id
                and existing.get("active", True)
            ):
                return profile
        entry = {
            "id": str(uuid.uuid4()),
            "text": text,
            "created_at": _now_iso(),
            "created_by": created_by,
            "source_observation_id": source_observation_id,
            "source_ref_ids": _validate_source_ref_ids(source_ref_ids),
            "confidence": confidence,
            "active": True,
        }
        profile[f"{kind}_strengths"].append(entry)

        now = _now_iso()
        self._conn.execute(
            """
            UPDATE students SET
                strengths_profile = ?,
                profile_version = profile_version + 1,
                updated_at = ?
            WHERE student_id = ?
            """,
            (json.dumps(profile), now, student_id),
        )
        self._conn.commit()
        return profile

    def confirm_profile_strength(
        self, student_id: str, kind: str, entry_id: str
    ) -> dict:
        """Teacher confirms a suggested profile-level strength in place."""
        return self._review_profile_strength(student_id, kind, entry_id, "confirm")

    def dismiss_profile_strength(
        self, student_id: str, kind: str, entry_id: str
    ) -> dict:
        """Teacher dismisses a suggested profile-level strength without deleting it."""
        return self._review_profile_strength(student_id, kind, entry_id, "dismiss")

    def _review_profile_strength(
        self, student_id: str, kind: str, entry_id: str, action: str
    ) -> dict:
        if kind not in VALID_STRENGTH_KINDS:
            raise ValueError(
                f"Unknown strength kind '{kind}'. Allowed: {VALID_STRENGTH_KINDS}"
            )
        if action not in ("confirm", "dismiss"):
            raise ValueError("action must be confirm or dismiss")
        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)

        profile = self._row_to_lens_dict(row)["strengths_profile"]
        bucket = profile[f"{kind}_strengths"]
        target = None
        for entry in bucket:
            if entry.get("id") == entry_id:
                target = entry
                break
        if target is None:
            raise ValueError(f"No strength entry '{entry_id}' in {kind} for this student")

        if action == "confirm":
            target["confidence"] = "teacher_confirmed"
        else:
            target["active"] = False

        now = _now_iso()
        self._conn.execute(
            """
            UPDATE students SET
                strengths_profile = ?,
                profile_version = profile_version + 1,
                updated_at = ?
            WHERE student_id = ?
            """,
            (json.dumps(profile), now, student_id),
        )
        self._conn.commit()
        return profile

    def add_ethos_evidence(
        self,
        student_id: str,
        trait_id: str,
        summary: str,
        created_by: str,
        evidence_type: str = "observation",
        source_observation_id: Optional[str] = None,
        source_ref_ids: Optional[list[str]] = None,
        confidence: str = "teacher_confirmed",
        allowed_trait_ids: Optional[list[str]] = None,
    ) -> dict:
        """Append evidence for a school-ethos trait on a student profile.

        trait_id must belong to the active ethos taxonomy
        (src/education/ethos.py). Pass allowed_trait_ids to inject the
        taxonomy explicitly (tests, batch imports); otherwise the active
        taxonomy is loaded from the configured ethos path.

        Dual-write (SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01): the same
        item also lands in the append-only evidence_records ledger under
        the same id, so the unified evidence views and the shipped ethos
        report/compliance paths can never diverge.
        """
        profile, _item = self._append_ethos_evidence_item(
            student_id=student_id,
            trait_id=trait_id,
            summary=summary,
            created_by=created_by,
            evidence_type=evidence_type,
            source_observation_id=source_observation_id,
            source_ref_ids=source_ref_ids,
            confidence=confidence,
            allowed_trait_ids=allowed_trait_ids,
        )
        return profile

    def confirm_ethos_evidence(
        self, student_id: str, trait_id: str, evidence_id: str
    ) -> dict:
        """Teacher confirms suggested ethos-trait evidence in profile and ledger."""
        return self._review_ethos_evidence(student_id, trait_id, evidence_id, "confirm")

    def dismiss_ethos_evidence(
        self, student_id: str, trait_id: str, evidence_id: str
    ) -> dict:
        """Teacher dismisses suggested ethos-trait evidence without deleting it."""
        return self._review_ethos_evidence(student_id, trait_id, evidence_id, "dismiss")

    def _review_ethos_evidence(
        self, student_id: str, trait_id: str, evidence_id: str, action: str
    ) -> dict:
        if action not in ("confirm", "dismiss"):
            raise ValueError("action must be confirm or dismiss")
        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)

        profile = self._row_to_lens_dict(row)["ethos_profile"]
        trait_data = profile["traits"].get(trait_id)
        if trait_data is None:
            raise ValueError(f"Unknown ethos trait '{trait_id}' for this student")

        target = None
        for item in trait_data.get("evidence", []):
            if item.get("id") == evidence_id:
                target = item
                break
        if target is None:
            raise ValueError(
                f"No evidence '{evidence_id}' in ethos trait '{trait_id}' for this student"
            )

        if action == "confirm":
            target["confidence"] = "teacher_confirmed"
            self._conn.execute(
                """
                UPDATE evidence_records SET confidence_level = ?
                WHERE evidence_id = ? AND student_id = ?
                """,
                ("teacher_confirmed", evidence_id, student_id),
            )
        else:
            target["active"] = False

        self._recompute_ethos_rollup(student_id, profile)
        now = _now_iso()
        self._conn.execute(
            """
            UPDATE students SET
                ethos_profile = ?,
                profile_version = profile_version + 1,
                updated_at = ?
            WHERE student_id = ?
            """,
            (json.dumps(profile), now, student_id),
        )
        self._conn.commit()
        return profile

    def _append_ethos_evidence_item(
        self,
        *,
        student_id: str,
        trait_id: str,
        summary: str,
        created_by: str,
        evidence_type: str = "observation",
        source_observation_id: Optional[str] = None,
        source_ref_ids: Optional[list[str]] = None,
        confidence: str = "teacher_confirmed",
        allowed_trait_ids: Optional[list[str]] = None,
        kind: Optional[str] = None,
        source_ref: Optional[dict] = None,
    ) -> tuple[dict, dict]:
        """Core ethos-evidence writer: profile array + ledger row + rollup
        in one transaction. Returns (profile, item) where item is the
        appended item — or the pre-existing one on an idempotent
        double-submit (in which case nothing is written)."""
        if allowed_trait_ids is None:
            from src.education import ethos as ethos_mod

            active = ethos_mod.load_ethos()
            allowed_trait_ids = list(ethos_mod.trait_ids(active))
            ethos_name = active.get("ethos_name")
        else:
            ethos_name = None
        if trait_id not in allowed_trait_ids:
            raise ValueError(
                f"Unknown ethos trait '{trait_id}'. Allowed: {tuple(allowed_trait_ids)}"
            )
        if not (isinstance(summary, str) and summary.strip() and len(summary) <= 2000):
            raise ValueError("Evidence summary must be non-empty and <= 2000 characters")
        if evidence_type not in VALID_EVIDENCE_TYPES:
            raise ValueError(
                f"Invalid evidence_type '{evidence_type}'. Allowed: {VALID_EVIDENCE_TYPES}"
            )
        if confidence not in VALID_CONFIDENCE_VALUES:
            raise ValueError(
                f"Invalid confidence '{confidence}'. Allowed: {VALID_CONFIDENCE_VALUES}"
            )
        created_by = _validate_non_empty_string(created_by, "created_by")
        source_observation_id = _validate_non_empty_string(
            source_observation_id, "source_observation_id"
        )

        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)

        profile = self._row_to_lens_dict(row)["ethos_profile"]
        if ethos_name and not profile.get("ethos_name"):
            profile["ethos_name"] = ethos_name
        trait_bucket = profile["traits"].setdefault(trait_id, {"evidence": []})
        summary = summary.strip()
        # Idempotency: identical summary + source for the same trait is a
        # double-submit — return unchanged, no profile_version bump.
        for existing in trait_bucket["evidence"]:
            same_source = (
                existing.get("source_observation_id") == source_observation_id
            )
            if (
                existing.get("summary") == summary
                and same_source
            ):
                return profile, existing
            if (
                same_source
                and existing.get("confidence") == "model_suggested"
                and confidence == "teacher_confirmed"
            ):
                existing["summary"] = summary
                existing["evidence_type"] = evidence_type
                existing["source_ref_ids"] = _validate_source_ref_ids(source_ref_ids)
                existing["created_by"] = created_by
                existing["confidence"] = confidence
                if kind is None:
                    kind = (
                        "observation_ref"
                        if source_observation_id
                        else "teacher_feedback"
                    )
                if source_ref is None:
                    source_ref = (
                        {"observation_id": source_observation_id}
                        if source_observation_id
                        else None
                    )
                self._conn.execute(
                    """
                    UPDATE evidence_records SET
                        teacher_id = ?,
                        kind = ?,
                        summary = ?,
                        source_ref = ?,
                        confidence_level = ?
                    WHERE evidence_id = ?
                    """,
                    (
                        created_by,
                        kind,
                        summary,
                        json.dumps(source_ref) if source_ref is not None else None,
                        confidence,
                        existing["id"],
                    ),
                )
                self._recompute_ethos_rollup(student_id, profile)
                now = _now_iso()
                self._conn.execute(
                    """
                    UPDATE students SET
                        ethos_profile = ?,
                        profile_version = profile_version + 1,
                        updated_at = ?
                    WHERE student_id = ?
                    """,
                    (json.dumps(profile), now, student_id),
                )
                self._conn.commit()
                return profile, existing
        item = {
            "id": str(uuid.uuid4()),
            "summary": summary,
            "evidence_type": evidence_type,
            "source_observation_id": source_observation_id,
            "source_ref_ids": _validate_source_ref_ids(source_ref_ids),
            "created_at": _now_iso(),
            "created_by": created_by,
            "confidence": confidence,
        }
        trait_bucket["evidence"].append(item)

        if kind is None:
            if source_observation_id:
                kind = "observation_ref"
            elif evidence_type in _DOCUMENT_EVIDENCE_TYPES:
                kind = "document"
            else:
                kind = "teacher_feedback"
        if source_ref is None:
            if source_observation_id:
                source_ref = {"observation_id": source_observation_id}
            elif item["source_ref_ids"]:
                source_ref = {"source_ref_ids": item["source_ref_ids"]}
        self._insert_evidence_row(
            evidence_id=item["id"],
            student_id=student_id,
            teacher_id=created_by,
            created_at=item["created_at"],
            kind=kind,
            target_type="ethos_trait",
            target_id=trait_id,
            summary=summary,
            source_ref=source_ref,
            confidence_level=confidence,
        )
        self._recompute_ethos_rollup(student_id, profile)

        now = _now_iso()
        self._conn.execute(
            """
            UPDATE students SET
                ethos_profile = ?,
                profile_version = profile_version + 1,
                updated_at = ?
            WHERE student_id = ?
            """,
            (json.dumps(profile), now, student_id),
        )
        self._conn.commit()
        return profile, item

    # ------------------------------------------------------------------
    # Unified evidence ledger (SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01)
    # ------------------------------------------------------------------

    def _insert_evidence_row(
        self,
        *,
        evidence_id: str,
        student_id: str,
        teacher_id: str,
        created_at: str,
        kind: str,
        target_type: str,
        target_id: Optional[str],
        summary: str,
        source_ref: Optional[dict],
        confidence_level: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO evidence_records (
                evidence_id, student_id, teacher_id, created_at, kind,
                target_type, target_id, summary, source_ref,
                confidence_level, deleted, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
            """,
            (
                evidence_id,
                student_id,
                teacher_id,
                created_at,
                kind,
                target_type,
                target_id,
                summary,
                json.dumps(source_ref) if source_ref is not None else None,
                confidence_level,
            ),
        )

    def append_evidence(
        self,
        record: dict,
        allowed_trait_ids: Optional[list[str]] = None,
    ) -> str:
        """Append one record to the append-only evidence ledger.

        record keys: student_id, teacher_id, kind, target_type, target_id,
        summary, source_ref (optional dict), confidence_level (optional,
        default teacher_confirmed). Returns the evidence_id.

        ethos_trait targets route through the same core writer as
        add_ethos_evidence, so the profile array, the ledger, and the
        per-trait rollups stay coherent no matter which door the evidence
        came in through. Provenance is a pointer (source_ref), never file
        bytes — content stays where it lives.
        """
        if not isinstance(record, dict):
            raise ValueError("evidence record must be a dictionary")
        student_id = _validate_non_empty_string(
            record.get("student_id"), "student_id"
        )
        teacher_id = _validate_non_empty_string(
            record.get("teacher_id"), "teacher_id"
        )
        kind = record.get("kind")
        if kind not in VALID_EVIDENCE_KINDS:
            raise ValueError(
                f"Invalid kind '{kind}'. Allowed: {VALID_EVIDENCE_KINDS}"
            )
        target_type = record.get("target_type")
        if target_type not in VALID_EVIDENCE_TARGET_TYPES:
            raise ValueError(
                f"Invalid target_type '{target_type}'. "
                f"Allowed: {VALID_EVIDENCE_TARGET_TYPES}"
            )
        target_id = record.get("target_id")
        summary = record.get("summary")
        if not (isinstance(summary, str) and summary.strip() and len(summary) <= 2000):
            raise ValueError("Evidence summary must be non-empty and <= 2000 characters")
        summary = summary.strip()
        confidence = record.get("confidence_level", "teacher_confirmed")
        if confidence not in VALID_CONFIDENCE_VALUES:
            raise ValueError(
                f"Invalid confidence '{confidence}'. Allowed: {VALID_CONFIDENCE_VALUES}"
            )
        source_ref = record.get("source_ref")
        if source_ref is not None and not isinstance(source_ref, dict):
            raise ValueError("source_ref must be an object or null")

        if target_type == "support_category":
            if target_id not in SUPPORT_CATEGORY_IDS:
                raise ValueError(
                    f"Unknown category ID '{target_id}'. Allowed: {SUPPORT_CATEGORY_IDS}"
                )
        elif target_type == "strengths":
            if target_id not in VALID_STRENGTH_KINDS:
                raise ValueError(
                    f"Unknown strengths kind '{target_id}'. "
                    f"Allowed: {VALID_STRENGTH_KINDS}"
                )
        elif target_type == "background":
            if target_id is not None:
                raise ValueError("background evidence takes no target_id")

        if target_type == "ethos_trait":
            evidence_type = _EVIDENCE_KIND_TO_TYPE[kind]
            if kind == "document" and source_ref:
                evidence_type = _SOURCE_TYPE_TO_EVIDENCE_TYPE.get(
                    str(source_ref.get("source_type") or ""), evidence_type
                )
            source_ref_ids = None
            if source_ref and source_ref.get("source_record_id"):
                source_ref_ids = [str(source_ref["source_record_id"])]
            _profile, item = self._append_ethos_evidence_item(
                student_id=student_id,
                trait_id=target_id,
                summary=summary,
                created_by=teacher_id,
                evidence_type=evidence_type,
                source_observation_id=(
                    _validate_non_empty_string(
                        source_ref.get("observation_id"), "observation_id"
                    )
                    if source_ref and source_ref.get("observation_id")
                    else None
                ),
                source_ref_ids=source_ref_ids,
                confidence=confidence,
                allowed_trait_ids=allowed_trait_ids,
                kind=kind,
                source_ref=source_ref,
            )
            return item["id"]

        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)

        evidence_id = str(uuid.uuid4())
        self._insert_evidence_row(
            evidence_id=evidence_id,
            student_id=student_id,
            teacher_id=teacher_id,
            created_at=_now_iso(),
            kind=kind,
            target_type=target_type,
            target_id=target_id,
            summary=summary,
            source_ref=source_ref,
            confidence_level=confidence,
        )
        self._conn.commit()
        return evidence_id

    def list_evidence(
        self,
        student_id: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        include_deleted: bool = False,
    ) -> list[dict]:
        """Ledger listing, newest first. source_ref comes back parsed."""
        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)
        query = "SELECT * FROM evidence_records WHERE student_id = ?"
        params: list = [student_id]
        if target_type is not None:
            query += " AND target_type = ?"
            params.append(target_type)
        if target_id is not None:
            query += " AND target_id = ?"
            params.append(target_id)
        if not include_deleted:
            query += " AND deleted = 0"
        query += " ORDER BY created_at DESC, evidence_id"
        results = []
        for r in self._conn.execute(query, params).fetchall():
            d = dict(r)
            d["deleted"] = bool(d["deleted"])
            raw_ref = d.get("source_ref")
            if raw_ref:
                try:
                    d["source_ref"] = json.loads(raw_ref)
                except (TypeError, ValueError):
                    d["source_ref"] = None
            else:
                d["source_ref"] = None
            results.append(d)
        return results

    def soft_delete_evidence(self, evidence_id: str) -> None:
        """Tombstone a ledger row (append-only: never a hard DELETE, same
        pattern as the students table). ethos_trait rows also mark the
        mirrored profile item inactive and refresh the trait rollups, so
        every view retires the evidence together."""
        row = self._conn.execute(
            "SELECT * FROM evidence_records WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown evidence_id '{evidence_id}'")
        if row["deleted"]:
            return
        now = _now_iso()
        self._conn.execute(
            "UPDATE evidence_records SET deleted = 1, deleted_at = ? "
            "WHERE evidence_id = ?",
            (now, evidence_id),
        )
        if row["target_type"] == "ethos_trait":
            srow = self._get_student_row(row["student_id"], include_deleted=True)
            if srow is not None:
                profile = self._row_to_lens_dict(srow)["ethos_profile"]
                for trait_data in profile["traits"].values():
                    for item in trait_data.get("evidence", []):
                        if item.get("id") == evidence_id:
                            item["active"] = False
                self._recompute_ethos_rollup(row["student_id"], profile)
                self._conn.execute(
                    """
                    UPDATE students SET
                        ethos_profile = ?,
                        profile_version = profile_version + 1,
                        updated_at = ?
                    WHERE student_id = ?
                    """,
                    (json.dumps(profile), now, row["student_id"]),
                )
        self._conn.commit()

    def _recompute_ethos_rollup(
        self, student_id: str, profile: Optional[dict] = None
    ) -> dict:
        """Recompute per-trait {evidence_count, last_evidence_at} from the
        evidence_records ledger into ethos_profile — same
        recompute-on-write pattern as the CEFR/RTI aggregates in
        append_observation. Verdict at the moment of truth, in the code
        path that has ground truth; never rebuilt later from a proxy.

        With profile given, mutates it in place and lets the caller
        persist (single UPDATE per write). Without it, loads, recomputes,
        persists, and commits."""
        rows = self._conn.execute(
            """
            SELECT target_id, COUNT(*) AS n, MAX(created_at) AS last_at
            FROM evidence_records
            WHERE student_id = ? AND target_type = 'ethos_trait' AND deleted = 0
            GROUP BY target_id
            """,
            (student_id,),
        ).fetchall()
        persist = profile is None
        if profile is None:
            srow = self._get_student_row(student_id, include_deleted=True)
            if srow is None:
                raise LensNotFoundError(student_id)
            profile = self._row_to_lens_dict(srow)["ethos_profile"]
        for trait_data in profile["traits"].values():
            trait_data["evidence_count"] = 0
            trait_data["last_evidence_at"] = None
        for r in rows:
            bucket = profile["traits"].setdefault(r["target_id"], {"evidence": []})
            bucket["evidence_count"] = int(r["n"])
            bucket["last_evidence_at"] = r["last_at"]
        if persist:
            self._conn.execute(
                "UPDATE students SET ethos_profile = ?, updated_at = ? "
                "WHERE student_id = ?",
                (json.dumps(profile), _now_iso(), student_id),
            )
            self._conn.commit()
        return profile

    def export_ethos_report(
        self,
        student_id: str,
        include_unconfirmed: bool = False,
    ) -> dict:
        """Report-ready export of ethos trait evidence + profile-level
        strengths for a student report.

        Only REPORT_GRADE_CONFIDENCE items (teacher_confirmed /
        imported_verified) appear in the report sections. Unconfirmed
        items (model_suggested / imported_needs_confirmation) are ALWAYS
        excluded from the report body; include_unconfirmed=True surfaces
        them in a separate pending_review section for the teacher's own
        prep view, never for the report itself.

        Trait labels resolve from the active ethos taxonomy when it loads;
        a broken taxonomy degrades to raw trait ids (the evidence itself
        is already on the profile and must remain exportable).
        """
        row = self._get_student_row(student_id, include_deleted=False)
        if row is None:
            raise LensNotFoundError(student_id)
        lens = self._row_to_lens_dict(row)

        labels: dict[str, str] = {}
        ethos_name = lens["ethos_profile"].get("ethos_name")
        try:
            from src.education import ethos as ethos_mod

            taxonomy = ethos_mod.load_ethos()
            labels = {t["id"]: t["label"] for t in taxonomy.get("traits", [])}
            ethos_name = ethos_name or taxonomy.get("ethos_name")
        except Exception:
            pass  # degrade to trait ids; never block an export

        def _report_grade(items: list[dict], text_key: str) -> list[dict]:
            return [
                {
                    text_key: item.get(text_key),
                    "evidence_type": item.get("evidence_type"),
                    "created_at": item.get("created_at"),
                    "created_by": item.get("created_by"),
                    "source_observation_id": item.get("source_observation_id"),
                }
                for item in items
                # Fail-closed: every legitimate write path sets confidence
                # explicitly, so a missing field means the item did not come
                # through a governed path — it never reaches a report body.
                if item.get("confidence") in REPORT_GRADE_CONFIDENCE
                and item.get("active", True)
            ]

        def _pending(items: list[dict], text_key: str) -> list[dict]:
            return [
                {
                    "id": item.get("id"),
                    text_key: item.get(text_key),
                    "evidence_type": item.get("evidence_type"),
                    "source_observation_id": item.get("source_observation_id"),
                    "created_by": item.get("created_by"),
                    "confidence": item.get("confidence"),
                    "created_at": item.get("created_at"),
                }
                for item in items
                if item.get("confidence") not in REPORT_GRADE_CONFIDENCE
                and item.get("active", True)
            ]

        sp = lens["strengths_profile"]
        traits_out = []
        pending_traits = []
        for trait_id, trait_data in sorted(lens["ethos_profile"]["traits"].items()):
            evidence = _report_grade(trait_data.get("evidence", []), "summary")
            if evidence:
                traits_out.append(
                    {
                        "trait_id": trait_id,
                        "label": labels.get(trait_id, trait_id),
                        "evidence": evidence,
                    }
                )
            if include_unconfirmed:
                pending = _pending(trait_data.get("evidence", []), "summary")
                if pending:
                    pending_traits.append(
                        {
                            "trait_id": trait_id,
                            "label": labels.get(trait_id, trait_id),
                            "items": pending,
                        }
                    )

        report = {
            "student_id": student_id,
            "display_name": lens.get("display_name"),
            "generated_at": _now_iso(),
            "ethos_name": ethos_name,
            "academic_strengths": _report_grade(sp["academic_strengths"], "text"),
            "personal_strengths": _report_grade(sp["personal_strengths"], "text"),
            "traits": traits_out,
        }
        if include_unconfirmed:
            report["pending_review"] = {
                "academic_strengths": _pending(sp["academic_strengths"], "text"),
                "personal_strengths": _pending(sp["personal_strengths"], "text"),
                "traits": pending_traits,
            }
        return report

    # ------------------------------------------------------------------
    # Internal: recalculation + RTI escalation (observation-capture.md
    # Stage 3 Local Enrichment + Stage 6 RTI Escalation Logic)
    # ------------------------------------------------------------------

    def _get_student_row(
        self, student_id: str, include_deleted: bool = False
    ) -> Optional[sqlite3.Row]:
        query = "SELECT * FROM students WHERE student_id = ?"
        if not include_deleted:
            query += " AND deleted = 0"
        return self._conn.execute(query, (student_id,)).fetchone()

    def _row_to_lens_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d['assessment_profile'] = [json.loads(item['payload']) for item in self._conn.execute(
            'SELECT payload FROM assessment_records WHERE student_id = ? AND assessment_id NOT IN '
            '(SELECT assessment_id FROM assessment_withdrawals) ORDER BY created_at', (d['student_id'],)
        )]
        d["home_languages"] = json.loads(d["home_languages"])
        d["learning_differences"] = json.loads(d["learning_differences"])
        d["trauma_flag"] = bool(d["trauma_flag"])
        d["avoid_pairing_with"] = json.loads(d["avoid_pairing_with"])
        d["rti_tier_history"] = json.loads(d["rti_tier_history"])
        d["cefr_snapshot"] = json.loads(d["cefr_snapshot"])
        d["sel_summary"] = json.loads(d["sel_summary"])
        raw_sp = d.get("support_profile")
        d["support_profile"], d["support_profile_warnings"] = (
            _normalize_support_profile_with_warnings(raw_sp)
        )
        d["strengths_profile"], d["strengths_profile_warnings"] = (
            _normalize_strengths_profile_with_warnings(d.get("strengths_profile"))
        )
        d["ethos_profile"], d["ethos_profile_warnings"] = (
            _normalize_ethos_profile_with_warnings(d.get("ethos_profile"))
        )
        d["deleted"] = bool(d["deleted"])
        return d

    def _observation_row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["urgency_flag"] = bool(d.get("urgency_flag"))
        d["rti_tier_changed_this_obs"] = bool(d.get("rti_tier_changed_this_obs"))
        for field_name, default in (
            ("validation_errors", []),
            ("support_entries", []),
            ("classification_guidance", None),
            ("teacher_feedback", None),
        ):
            raw = d.get(field_name)
            if raw in (None, ""):
                d[field_name] = default
                continue
            try:
                d[field_name] = json.loads(raw)
            except (TypeError, ValueError):
                d[field_name] = default
        return d

    def _recalculate_lens(self, student_id: str, latest_obs: Observation) -> None:
        row = self._get_student_row(student_id, include_deleted=True)
        lens = self._row_to_lens_dict(row)

        # RTI tier + history (Rule E: any manual/observed tier change is logged)
        if latest_obs.rti_tier_changed_this_obs:
            history = lens["rti_tier_history"]
            if history and history[-1]["to"] is None:
                history[-1]["to"] = latest_obs.recorded_at
            history.append(
                {
                    "tier": latest_obs.rti_tier,
                    "from": latest_obs.recorded_at,
                    "to": None,
                    "trigger": latest_obs.observation_id,
                }
            )
            lens["rti_tier_history"] = history
            lens["rti_current_tier"] = latest_obs.rti_tier

        # CEFR snapshot: latest observed level per dimension
        if latest_obs.cefr_dimension and latest_obs.cefr_level_observed:
            lens["cefr_snapshot"][latest_obs.cefr_dimension] = latest_obs.cefr_level_observed

        lens["cefr_trajectory_30d"] = self._compute_cefr_trajectory(student_id)

        # SEL summary: rolling counts, last 14 days for concerns/positives
        obs_rows = self._conn.execute(
            "SELECT * FROM observations WHERE student_id = ? ORDER BY recorded_at DESC",
            (student_id,),
        ).fetchall()
        recent = [dict(r) for r in obs_rows[:50]]  # bounded scan, most-recent-first
        concerns = sum(1 for o in recent if o["sel_valence"] == "concern")
        positives = sum(1 for o in recent if o["sel_valence"] == "positive")
        domains = [o["sel_domain"] for o in recent if o["sel_domain"]]
        dominant = max(set(domains), key=domains.count) if domains else None
        last_urgency = next(
            (o["recorded_at"] for o in recent if o["urgency_flag"]), None
        )
        lens["sel_summary"] = {
            "recent_concerns": concerns,
            "recent_positives": positives,
            "dominant_domain": dominant,
            "last_urgency_flag": last_urgency,
        }

        lens["profile_version"] = lens["profile_version"] + 1
        lens["updated_at"] = _now_iso()

        self._conn.execute(
            """
            UPDATE students SET
                rti_current_tier = ?, rti_tier_history = ?, cefr_snapshot = ?,
                cefr_trajectory_30d = ?, sel_summary = ?, profile_version = ?,
                updated_at = ?
            WHERE student_id = ?
            """,
            (
                lens["rti_current_tier"],
                json.dumps(lens["rti_tier_history"]),
                json.dumps(lens["cefr_snapshot"]),
                lens["cefr_trajectory_30d"],
                json.dumps(lens["sel_summary"]),
                lens["profile_version"],
                lens["updated_at"],
                student_id,
            ),
        )
        self._conn.commit()

    def _compute_cefr_trajectory(self, student_id: str) -> str:
        """progressing | plateaued | regressing | mixed | insufficient_data
        over the last 30 days of cefr-tagged observations."""
        cutoff = time.time() - 30 * 86400
        rows = self._conn.execute(
            "SELECT cefr_direction, recorded_at FROM observations "
            "WHERE student_id = ? AND cefr_direction IS NOT NULL "
            "ORDER BY recorded_at ASC",
            (student_id,),
        ).fetchall()
        directions = []
        for r in rows:
            try:
                ts = datetime.fromisoformat(r["recorded_at"]).timestamp()
            except ValueError:
                continue
            if ts >= cutoff:
                directions.append(r["cefr_direction"])
        if not directions:
            return "insufficient_data"
        unique = set(directions)
        if unique == {"progressing"}:
            return "progressing"
        if unique == {"regressing"}:
            return "regressing"
        if unique == {"plateaued"}:
            return "plateaued"
        return "mixed"

    def _evaluate_rti_rules(self, student_id: str) -> list[dict]:
        """
        RTI escalation rules A-E from observation-capture.md Stage 6.
        Returns triggered escalation events (not yet persisted anywhere
        beyond this call's return value — persistence + notification
        delivery is the observation_capture pipeline module's job).

        Simplification for the Friday vertical slice: "school days" in
        the architecture doc is approximated as calendar days here. If
        this matters for real escalation timing (it will, once a school
        has weekends/holidays in the mix), tighten with a school
        calendar before the pilot scales past the first onboarding week.
        """
        escalations = []
        now_ts = time.time()
        rows = self._conn.execute(
            "SELECT * FROM observations WHERE student_id = ? ORDER BY recorded_at DESC",
            (student_id,),
        ).fetchall()
        obs = [dict(r) for r in rows]
        if not obs:
            return escalations

        def within_days(o: dict, days: int) -> bool:
            try:
                ts = datetime.fromisoformat(o["recorded_at"]).timestamp()
            except ValueError:
                return False
            return (now_ts - ts) <= days * 86400

        # Rule A: >=3 tier-2 observations in 10 days, >=2 of them regressing
        last10 = [o for o in obs if within_days(o, 10) and o["rti_tier"] == 2]
        regressing_in_last10 = [o for o in last10 if o["cefr_direction"] == "regressing"]
        if len(last10) >= 3 and len(regressing_in_last10) >= 2:
            escalations.append(
                {"rule": "A", "action": "escalate_to_tier2_review",
                 "trigger_observation_id": obs[0]["observation_id"]}
            )

        # Rule B: any single urgency_flag = true observation (check latest only —
        # older urgency flags already triggered on their own append)
        if obs[0]["urgency_flag"]:
            escalations.append(
                {"rule": "B", "action": "immediate_notification",
                 "trigger_observation_id": obs[0]["observation_id"]}
            )

        # Rule C: current tier 1, no observations in 15 days (checked against
        # the second-most-recent observation, since the one just saved
        # necessarily breaks the gap)
        if len(obs) >= 2 and obs[0]["rti_tier"] == 1:
            try:
                latest_ts = datetime.fromisoformat(obs[0]["recorded_at"]).timestamp()
                prior_ts = datetime.fromisoformat(obs[1]["recorded_at"]).timestamp()
                if (latest_ts - prior_ts) > 15 * 86400:
                    escalations.append(
                        {"rule": "C", "action": "monitoring_gap_alert",
                         "trigger_observation_id": obs[0]["observation_id"]}
                    )
            except ValueError:
                pass

        # Rule D: >=3 sel concerns in 7 days
        last7_concerns = [
            o for o in obs if within_days(o, 7) and o["sel_valence"] == "concern"
        ]
        if len(last7_concerns) >= 3:
            escalations.append(
                {"rule": "D", "action": "sel_support_flag",
                 "trigger_observation_id": obs[0]["observation_id"]}
            )

        # Rule E: manual tier change always triggers review
        if obs[0]["rti_tier_changed_this_obs"]:
            escalations.append(
                {"rule": "E", "action": "tier_change_review_queue",
                 "trigger_observation_id": obs[0]["observation_id"]}
            )

        return escalations


DIVERGENCE_WINDOW_DAYS = 30


def compute_triangulation(lens: dict) -> dict:
    """Deterministic multi-teacher convergence signals for one exported lens
    (SPEC_LV_MULTI_TEACHER_TRIANGULATION_2026-08-01 §3). Counting and date
    comparison only — no LLM, nothing auto-resolved.

    - colleagues: every contributing teacher, local vs imported, last-seen
    - categories: corroborated (2+ distinct authors), single_source, none
    - divergence: opposing CEFR directions (progressing vs regressing) from
      different teachers within DIVERGENCE_WINDOW_DAYS — surfaced as a
      "worth a conversation" prompt with both observation ids
    """
    observations = lens.get("observations") or []
    teachers: dict[str, dict] = {}
    for o in observations:
        tid = str(o.get("teacher_id") or "")
        if not tid:
            continue
        rec = teachers.setdefault(
            tid,
            {"teacher_id": tid, "observation_count": 0, "last_seen": "", "origin": "local"},
        )
        rec["observation_count"] += 1
        recorded = str(o.get("recorded_at") or "")
        if recorded > rec["last_seen"]:
            rec["last_seen"] = recorded
        if o.get("origin") == "imported":
            rec["origin"] = "imported"

    categories: dict[str, dict] = {}
    support_categories = (lens.get("support_profile") or {}).get("categories") or {}
    for cat_id, category in support_categories.items():
        authors: set[str] = set()
        for bucket in (*VALID_SUPPORT_BUCKETS, "evidence"):
            items = category.get(bucket)
            if not isinstance(items, list):
                continue
            for item in items:
                author = str(item.get("created_by") or "")
                if author:
                    authors.add(author)
        if len(authors) >= 2:
            status = "corroborated"
        elif len(authors) == 1:
            status = "single_source"
        else:
            status = "none"
        categories[cat_id] = {"status": status, "teachers": sorted(authors)}

    directional = []
    for o in observations:
        if o.get("cefr_direction") not in ("progressing", "regressing"):
            continue
        try:
            ts = datetime.fromisoformat(str(o.get("recorded_at"))).timestamp()
        except (TypeError, ValueError):
            continue
        directional.append((ts, o))
    divergence: list[dict] = []
    window = DIVERGENCE_WINDOW_DAYS * 86400
    for i, (ts_a, a) in enumerate(directional):
        for ts_b, b in directional[i + 1:]:
            if a.get("teacher_id") == b.get("teacher_id"):
                continue
            if a.get("cefr_direction") == b.get("cefr_direction"):
                continue
            if abs(ts_a - ts_b) > window:
                continue
            divergence.append({
                "observation_ids": [a.get("observation_id"), b.get("observation_id")],
                "teachers": [str(a.get("teacher_id")), str(b.get("teacher_id"))],
                "directions": [str(a.get("cefr_direction")), str(b.get("cefr_direction"))],
            })
    # Bounded output: the most recent flags are the actionable ones.
    divergence = divergence[-5:]

    local_ids = sorted(
        tid for tid, rec in teachers.items() if rec["origin"] == "local"
    )
    return {
        "colleagues": sorted(teachers.values(), key=lambda r: r["teacher_id"]),
        "local_teacher_ids": local_ids,
        "categories": categories,
        "divergence": divergence,
    }
