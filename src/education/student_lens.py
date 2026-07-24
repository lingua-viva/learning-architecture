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
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
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
VALID_TEMPLATE_TYPES = ("literacy", "cefr", "sel_incident", "sel_positive", "rti_flag")

SUPPORT_CATEGORY_IDS = (
    "learning_and_cognition",
    "communication_and_language",
    "executive_functioning",
    "social_skills",
    "emotional_regulation",
    "physical_sensory_needs",
    "attendance_and_engagement",
    "advanced_enrichment",
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
            """
        )
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA table_info(students)")
        columns = [row[1] for row in cursor.fetchall()]
        if "support_profile" not in columns:
            self._conn.execute(
                "ALTER TABLE students ADD COLUMN support_profile TEXT NOT NULL DEFAULT '{}'"
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

    def append_observation(self, observation: Observation) -> dict:
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
        escalations = self._evaluate_rti_rules(observation.student_id)

        return {
            "observation": observation.to_row(),
            "validation_errors": errors,
            "escalations": escalations,
            "feedback": {
                "saved_entries": saved_entries,
                "categories_updated": categories_updated,
                "message": _support_feedback_message(categories_updated, saved_entries),
                "next_review_prompt": _support_next_review_prompt(support_entries),
            },
        }

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

    def list_lenses_for_teacher(self, teacher_id: str) -> list[dict]:
        """
        A teacher's roster, defined as: every non-deleted student this
        teacher has recorded at least one observation for. There is no
        separate homeroom/class-roster table in this vertical slice —
        the observation history itself is the ownership signal, which
        also means this same query is what makes the cross-teacher view
        possible (Turn 11): ask the same question with a different
        teacher_id and you get that teacher's overlapping students.
        """
        rows = self._conn.execute(
            """
            SELECT s.* FROM students s
            WHERE s.deleted = 0
              AND s.student_id IN (
                  SELECT DISTINCT student_id FROM observations WHERE teacher_id = ?
              )
            """,
            (teacher_id,),
        ).fetchall()
        return [self._row_to_lens_dict(r) for r in rows]

    def teachers_for_student(self, student_id: str) -> list[str]:
        """All teacher_ids who have recorded at least one observation for
        this student — the basis for the cross-teacher shared-student view."""
        rows = self._conn.execute(
            "SELECT DISTINCT teacher_id FROM observations WHERE student_id = ? ORDER BY teacher_id",
            (student_id,),
        ).fetchall()
        return [r["teacher_id"] for r in rows]

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
