"""
Ops Records — operational record store + status machine for the Slack
Daily Operations Assistant.

Spec: dev/specs/SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27.md §3.3 (Lane C).

Design decisions (operator-locked 2026-07-27):
  - This is the *operational* record store: absences, coverage, schedule
    changes, announcements, logistics. It is a completely separate module
    from student_lens.py — Slack messages NEVER create or update student
    lenses (spec §0), and nothing here imports StudentLensStore or
    ObservationCapturePipeline.
  - Append-oriented SQLite, same house style as student_lens.py: stdlib
    sqlite3, plain connection (student_lens does not enable WAL, so
    neither do we), Row factory, parameterized SQL only, explicit
    commit per mutation. DB defaults to lv_home()/ops/ops_records.db;
    LV_OPS_DB_PATH overrides (config.py home-resolution seam,
    MC-lessons §1). An explicit db_path argument wins over both, same
    precedence as StudentLensStore(db_path=...).
  - Status machine (spec §3.3): only coverage_request uses more than
    "logged". coverage_request: open -> claimed -> confirmed (v1: a
    claim may auto-confirm, so open -> confirmed directly is also
    legal). All other categories: logged | needs_review -> resolved.
    Invalid transitions raise ValueError — the bot layer must never be
    able to, e.g., "claim" an announcement.
  - needs_review is a boolean flag (drives the daily file's "To Review"
    section) that is loosely coupled to status: a coverage_request can
    be open AND flagged for review at the same time (so it stays
    claimable while ambiguous). For non-coverage categories the flag
    and the "needs_review" status move together.
  - Every mutation appends an audit entry to the existing privacy log
    (src/lingua_viva/privacy_log.py). The entry carries ONLY structural
    metadata — action, category, record id, and a permalink-style
    source reference (slack://<channel>/p<ts>) — never message text.
    Note on mechanism: privacy_log.log_privacy_event() deliberately
    force-genericizes the detail field (its job is to keep free text
    out of the log), and privacy_log.py currently carries another
    lane's uncommitted work, so it must not be modified mid-crunch.
    We therefore build the event with the module's own PrivacyEvent
    dataclass / path helper / hash helper and append it in the module's
    exact NDJSON format, preserving the structural detail. The detail
    string is constructed exclusively from identifiers, so the
    no-free-text invariant the genericizer protects still holds.
  - Timestamps are UTC ISO-8601 (house convention: datetime.now(
    timezone.utc).isoformat()). date_for is a plain ISO date string in
    the teacher's local calendar — the daily file is a *local-day*
    artifact, so callers (classifier/bot) resolve "tomorrow" etc.
    against local time before the record ever gets here.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.lingua_viva import privacy_log
from src.education import ops_packs


# v2 (SPEC_LV_SLACK_OPS_V2_WORKFLOW_PACKS_2026-07-27 §3.1): categories and
# broadcast membership derive from the pack registry instead of being
# hardcoded here. CATEGORIES validates against the FULL shipped catalog
# (all packs, enabled or not, plus core `other`) so historical records
# from a since-disabled pack stay loadable. BROADCAST_CATEGORIES keeps its
# name and v1-parity value as the module-level default; callers holding a
# compiled rule set (daily engine, bot) pass its broadcast set explicitly.
CATEGORIES = ops_packs.known_categories()

STATUSES = ("logged", "needs_review", "resolved", "open", "claimed", "confirmed")

# open/claimed/confirmed are ONLY valid for coverage_request (spec §3.3).
COVERAGE_ONLY_STATUSES = frozenset({"open", "claimed", "confirmed"})

# Categories that apply to every teacher's daily file, regardless of the
# teacher_id on the record (spec §1 workflows 3 and 4; reminders posted in
# the ops channel — "field trip forms due" — likewise concern everyone).
# Derived from the v1-parity default compile.
BROADCAST_CATEGORIES = ops_packs.default_rule_set().broadcast_categories

# Status machine. Key: current status -> set of legal next statuses.
_COVERAGE_TRANSITIONS: dict[str, frozenset[str]] = {
    # "resolved" from open/claimed = withdrawn (teacher pressed Cancel on
    # the absence flow, or the request became moot before confirmation).
    "open": frozenset({"claimed", "confirmed", "resolved"}),
    "claimed": frozenset({"confirmed", "resolved", "open"}),  # open = coordinator rejection
    "confirmed": frozenset(),
    "resolved": frozenset(),
}
_DEFAULT_TRANSITIONS: dict[str, frozenset[str]] = {
    "logged": frozenset({"resolved"}),
    "needs_review": frozenset({"logged", "resolved"}),
    "resolved": frozenset(),
}


def default_db_path() -> Path:
    override = os.environ.get("LV_OPS_DB_PATH")
    if override:
        return Path(override).expanduser()
    from src.lingua_viva.config import lv_home
    return lv_home() / "ops" / "ops_records.db"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_reference(source_channel: str, source_ts: str) -> str:
    """Permalink-style reference for a Slack message, safe for audit logs.

    Mirrors the Slack permalink anchor shape (/archives/<channel>/p<ts>
    with the dot stripped from the ts) without requiring a workspace URL.
    """
    if not source_channel and not source_ts:
        return "local"
    anchor = f"p{source_ts.replace('.', '')}" if source_ts else "p0"
    return f"slack://{source_channel or 'unknown'}/{anchor}"


@dataclass
class OpsRecord:
    """One operational record (spec §3.3 schema, field-for-field)."""

    id: str
    created_at: str
    updated_at: str
    category: str
    status: str
    teacher_id: str = ""
    actor_slack_id: str = ""
    actor_name: str = ""
    date_for: str = ""  # ISO date the record applies to
    time_window: str = ""
    periods: list = field(default_factory=list)  # stored as JSON
    text_raw: str = ""
    text_clean: str = ""
    source_channel: str = ""
    source_ts: str = ""  # permalink anchor
    thread_ts: str = ""
    needs_review: bool = False
    review_reason: str = ""
    claim_by: str = ""
    claim_at: str = ""
    extra: dict = field(default_factory=dict)  # stored as JSON

    def source_reference(self) -> str:
        return source_reference(self.source_channel, self.source_ts)


class OpsRecordStore:
    """SQLite-backed store for operational records + coverage status machine.

    One instance per device (offline-first, local-only — no external
    call is ever made from this module).
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "OpsRecordStore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ops_records (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                teacher_id TEXT NOT NULL DEFAULT '',
                actor_slack_id TEXT NOT NULL DEFAULT '',
                actor_name TEXT NOT NULL DEFAULT '',
                date_for TEXT NOT NULL DEFAULT '',
                time_window TEXT NOT NULL DEFAULT '',
                periods TEXT NOT NULL DEFAULT '[]',
                text_raw TEXT NOT NULL DEFAULT '',
                text_clean TEXT NOT NULL DEFAULT '',
                source_channel TEXT NOT NULL DEFAULT '',
                source_ts TEXT NOT NULL DEFAULT '',
                thread_ts TEXT NOT NULL DEFAULT '',
                needs_review INTEGER NOT NULL DEFAULT 0,
                review_reason TEXT NOT NULL DEFAULT '',
                claim_by TEXT NOT NULL DEFAULT '',
                claim_at TEXT NOT NULL DEFAULT '',
                extra TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_ops_records_day
                ON ops_records(date_for, teacher_id);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add_record(
        self,
        *,
        category: str,
        teacher_id: str = "",
        actor_slack_id: str = "",
        actor_name: str = "",
        date_for: str = "",
        time_window: str = "",
        periods: Optional[list] = None,
        text_raw: str = "",
        text_clean: str = "",
        source_channel: str = "",
        source_ts: str = "",
        thread_ts: str = "",
        needs_review: bool = False,
        review_reason: str = "",
        extra: Optional[dict] = None,
        status: Optional[str] = None,
    ) -> OpsRecord:
        if category not in CATEGORIES:
            raise ValueError(f"unknown category: {category!r}")
        if status is None:
            if category == "coverage_request":
                # Coverage always enters the machine at "open" so it stays
                # claimable even while flagged for review (spec §3.3).
                status = "open"
            else:
                status = "needs_review" if needs_review else "logged"
        self._validate_status_for_category(category, status)
        if status == "needs_review":
            needs_review = True

        now = utc_now_iso()
        record = OpsRecord(
            id=uuid.uuid4().hex,
            created_at=now,
            updated_at=now,
            category=category,
            status=status,
            teacher_id=teacher_id,
            actor_slack_id=actor_slack_id,
            actor_name=actor_name,
            date_for=date_for,
            time_window=time_window,
            periods=list(periods or []),
            text_raw=text_raw,
            text_clean=text_clean,
            source_channel=source_channel,
            source_ts=source_ts,
            thread_ts=thread_ts,
            needs_review=bool(needs_review),
            review_reason=review_reason,
            claim_by="",
            claim_at="",
            extra=dict(extra or {}),
        )
        self._conn.execute(
            """
            INSERT INTO ops_records (
                id, created_at, updated_at, category, status, teacher_id,
                actor_slack_id, actor_name, date_for, time_window, periods,
                text_raw, text_clean, source_channel, source_ts, thread_ts,
                needs_review, review_reason, claim_by, claim_at, extra
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.created_at,
                record.updated_at,
                record.category,
                record.status,
                record.teacher_id,
                record.actor_slack_id,
                record.actor_name,
                record.date_for,
                record.time_window,
                json.dumps(record.periods, ensure_ascii=True),
                record.text_raw,
                record.text_clean,
                record.source_channel,
                record.source_ts,
                record.thread_ts,
                int(record.needs_review),
                record.review_reason,
                record.claim_by,
                record.claim_at,
                json.dumps(record.extra, ensure_ascii=True),
            ),
        )
        self._conn.commit()
        self._audit("ops_record_added", record)
        return record

    def update_status(
        self,
        record_id: str,
        status: str,
        claim_by: Optional[str] = None,
        claim_at: Optional[str] = None,
    ) -> OpsRecord:
        record = self.get_record(record_id)
        if record is None:
            raise ValueError(f"unknown record: {record_id!r}")
        self._validate_status_for_category(record.category, status)

        transitions = (
            _COVERAGE_TRANSITIONS
            if record.category == "coverage_request"
            else _DEFAULT_TRANSITIONS
        )
        allowed = transitions.get(record.status, frozenset())
        if status not in allowed:
            raise ValueError(
                f"invalid transition for {record.category}: "
                f"{record.status!r} -> {status!r}"
            )

        now = utc_now_iso()
        new_claim_by = record.claim_by
        new_claim_at = record.claim_at
        if status in ("claimed", "confirmed") and claim_by is not None:
            new_claim_by = claim_by
            new_claim_at = claim_at or now
        # Leaving needs_review via the machine also clears the review flag
        # (the item is no longer awaiting a human look).
        new_needs_review = record.needs_review and status == "needs_review"

        self._conn.execute(
            """
            UPDATE ops_records
               SET status = ?, updated_at = ?, claim_by = ?, claim_at = ?,
                   needs_review = ?
             WHERE id = ?
            """,
            (status, now, new_claim_by, new_claim_at, int(new_needs_review), record_id),
        )
        self._conn.commit()
        updated = self.get_record(record_id)
        assert updated is not None
        self._audit("ops_record_updated", updated)
        return updated

    def mark_reviewed(self, record_id: str) -> OpsRecord:
        """Clear the needs_review flag (human looked at it).

        A non-coverage record sitting in the "needs_review" status moves
        to "logged"; a coverage_request keeps its machine status (it was
        never parked — spec §3.3 keeps coverage claimable while flagged).
        """
        record = self.get_record(record_id)
        if record is None:
            raise ValueError(f"unknown record: {record_id!r}")
        new_status = "logged" if record.status == "needs_review" else record.status
        now = utc_now_iso()
        self._conn.execute(
            "UPDATE ops_records SET needs_review = 0, status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, record_id),
        )
        self._conn.commit()
        updated = self.get_record(record_id)
        assert updated is not None
        self._audit("ops_record_reviewed", updated)
        return updated

    def reclassify_record(self, record_id: str, category: str) -> OpsRecord:
        """Admin teach-loop record fix (spec v2 §4): move a record to the
        category it should have been filed under, clearing the review flag.

        Coverage-machine guards: the open/claimed/confirmed machine owns
        coverage_request records (cards, claim buttons, restart-safe
        state) — reclassifying one out from under the machine would strand
        its Slack card, and relabeling a plain capture INTO the machine
        would fabricate a request no card ever announced. Both are refused;
        coverage corrections go through the machine (withdraw/cancel), and
        future messages get coverage treatment via a learned rule instead.
        """
        record = self.get_record(record_id)
        if record is None:
            raise ValueError(f"unknown record: {record_id!r}")
        if category not in CATEGORIES:
            raise ValueError(f"unknown category: {category!r}")
        if record.category in ("coverage_request", "coverage_claim"):
            raise ValueError(
                "coverage records belong to the claim machine and cannot be "
                "reclassified — withdraw or resolve them there"
            )
        if category in ("coverage_request", "coverage_claim"):
            raise ValueError(
                "records cannot be reclassified into the coverage machine — "
                "approve a learned rule so future messages start a real "
                "coverage request"
            )
        if category == record.category:
            return self.mark_reviewed(record_id)
        new_status = "logged" if record.status == "needs_review" else record.status
        now = utc_now_iso()
        self._conn.execute(
            """
            UPDATE ops_records
               SET category = ?, status = ?, needs_review = 0,
                   review_reason = '', updated_at = ?
             WHERE id = ?
            """,
            (category, new_status, now, record_id),
        )
        self._conn.commit()
        updated = self.get_record(record_id)
        assert updated is not None
        self._audit(
            "ops_record_reclassified",
            updated,
            extra_detail=f"from={record.category}",
        )
        return updated

    def update_extra(self, record_id: str, **updates) -> OpsRecord:
        """Merge keys into the record's extra JSON.

        Used by the bot layer for workflow side-state that is data, not
        status: attached lesson notes, emergency-plan flag, the ops-channel
        card ts a coverage request was posted under, etc.
        """
        record = self.get_record(record_id)
        if record is None:
            raise ValueError(f"unknown record: {record_id!r}")
        merged = dict(record.extra or {})
        merged.update(updates)
        self._conn.execute(
            "UPDATE ops_records SET extra = ?, updated_at = ? WHERE id = ?",
            (json.dumps(merged), utc_now_iso(), record_id),
        )
        self._conn.commit()
        updated = self.get_record(record_id)
        assert updated is not None
        self._audit("ops_record_updated", updated)
        return updated

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_record(self, record_id: str) -> Optional[OpsRecord]:
        row = self._conn.execute(
            "SELECT * FROM ops_records WHERE id = ?", (record_id,)
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def records_for_day(
        self,
        date_iso: str,
        teacher_id: Optional[str] = None,
        broadcast_categories: Optional[frozenset] = None,
    ) -> list[OpsRecord]:
        """All records applying to `date_iso`, optionally for one teacher.

        A record is "for" a teacher if its teacher_id matches OR its
        category broadcasts to everyone (announcement, schedule_change).
        teacher_id=None returns every record for the day.

        broadcast_categories defaults to the v1-parity set; callers with
        a compiled rule set pass its (enabled-packs-only) broadcast set
        so a disabled pack stops broadcasting (spec v2 §3.4).
        """
        broadcast = (
            BROADCAST_CATEGORIES
            if broadcast_categories is None
            else broadcast_categories
        )
        if teacher_id is None:
            rows = self._conn.execute(
                "SELECT * FROM ops_records WHERE date_for = ? ORDER BY created_at, rowid",
                (date_iso,),
            ).fetchall()
        elif broadcast:
            placeholders = ", ".join("?" for _ in broadcast)
            rows = self._conn.execute(
                f"""
                SELECT * FROM ops_records
                 WHERE date_for = ?
                   AND (teacher_id = ? OR category IN ({placeholders}))
                 ORDER BY created_at, rowid
                """,
                (date_iso, teacher_id, *sorted(broadcast)),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM ops_records
                 WHERE date_for = ? AND teacher_id = ?
                 ORDER BY created_at, rowid
                """,
                (date_iso, teacher_id),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def recent_records_in_categories(
        self, categories, *, since_iso: str
    ) -> list[OpsRecord]:
        """Records created at/after `since_iso` (UTC ISO — lexicographic
        compare is chronological) in any of `categories`. Used by the
        shadow suggester (spec v2 §8) to scan the week's unmatched
        traffic; counts only ever leave this data, never text."""
        wanted = sorted(set(categories))
        if not wanted:
            return []
        placeholders = ", ".join("?" for _ in wanted)
        rows = self._conn.execute(
            f"""
            SELECT * FROM ops_records
             WHERE created_at >= ? AND category IN ({placeholders})
             ORDER BY created_at, rowid
            """,
            (since_iso, *wanted),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def needs_review_count(
        self, date_iso: str, teacher_id: Optional[str] = None
    ) -> int:
        return sum(
            1
            for record in self.records_for_day(date_iso, teacher_id)
            if record.needs_review
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_status_for_category(category: str, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status!r}")
        if status in COVERAGE_ONLY_STATUSES and category != "coverage_request":
            raise ValueError(
                f"status {status!r} is only valid for coverage_request, "
                f"not {category!r}"
            )
        if (
            category == "coverage_request"
            and status not in COVERAGE_ONLY_STATUSES
            and status != "resolved"
        ):
            raise ValueError(
                f"coverage_request uses the open/claimed/confirmed machine "
                f"(plus terminal 'resolved' for withdrawal), not {status!r}"
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> OpsRecord:
        data = dict(row)
        data["periods"] = json.loads(data.get("periods") or "[]")
        data["extra"] = json.loads(data.get("extra") or "{}")
        data["needs_review"] = bool(data.get("needs_review"))
        return OpsRecord(**data)

    @staticmethod
    def _audit(action: str, record: OpsRecord, extra_detail: str = "") -> None:
        """Append a structural audit entry to the shared privacy log.

        Detail contains identifiers only — category, record id, status,
        source permalink reference. NO message text (see module
        docstring for why this appends in privacy_log's own NDJSON
        format instead of going through log_privacy_event, which
        force-genericizes the detail field).
        """
        ref = record.source_reference()
        event = privacy_log.PrivacyEvent(
            timestamp=utc_now_iso(),
            event_type=action,
            detail=(
                f"category={record.category} record={record.id} "
                f"status={record.status} source={ref}"
                + (f" {extra_detail}" if extra_detail else "")
            ),
            query_hash=privacy_log.event_hash(ref),
        )
        path = privacy_log.privacy_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
        os.chmod(path, 0o600)
