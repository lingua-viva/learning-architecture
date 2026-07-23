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
                cefr_trajectory_30d, sel_summary, profile_version,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
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
                validation_errors
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        self._conn.commit()

        self._recalculate_lens(observation.student_id, observation)
        escalations = self._evaluate_rti_rules(observation.student_id)

        return {
            "observation": observation.to_row(),
            "validation_errors": errors,
            "escalations": escalations,
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
        lens["observations"] = [dict(r) for r in obs_rows]
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
        d["deleted"] = bool(d["deleted"])
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
