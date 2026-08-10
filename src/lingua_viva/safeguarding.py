"""Safeguarding severity tier + restricted routing for Lingua Viva.

W2 slice (2026-08-09): classify teacher observations into severity tiers
(GREEN / AMBER / RED) with deterministic, glass-box heuristics, and keep
RED (possible abuse / safeguarding indicator) content in a restricted
ledger that only coordinator+ roles can read.

Containment design (why RED can never reach the daily brief or parents)
-----------------------------------------------------------------------
The normal observation path writes into the SQLite-backed
``StudentLensStore`` (src/education/student_lens.py). Everything the app
surfaces broadly — the ``/api/daily/briefing`` widgets, BriefService,
parent-facing recommendation output — reads from that store or from
artifacts derived from it. This module NEVER writes RED content there:

  * ``capture_with_safeguarding(...)`` classifies FIRST. A RED result is
    written only to ``<LV_STATE_HOME>/safeguarding/restricted.ndjson``
    and the delegate call into ``ObservationCapturePipeline.capture()``
    is skipped entirely. RED items therefore do not exist in any stream
    the brief or parent output reads — containment by separation of
    stores, not by filtering at render time. (Filtering at render time
    would require editing SHA-locked web.py and would fail open if one
    render path forgot the filter.)
  * The restricted ledger is exposed through exactly one chokepoint,
    ``filter_for_role(items, role)``: roles below coordinator — including
    unknown/empty roles and "parent" — get an empty list. Fail closed.
  * Queued notifications carry NO observation content — only an opaque
    entry id and a generic message — because the notification queue is
    what a future Slack/Drive drain reads, and safeguarding narrative
    must never transit an external channel from this system.

Zero-egress: this module performs no network I/O. Notifications follow
the local outbox/queue pattern of src/lingua_viva/docpipe/sync.py (queue
entry with a pending status; a separate drain owned by the existing
integration modules would deliver). With the ``safeguarding_channel`` /
``restricted_drive_folder`` config keys unset (the default), entries stay
queued locally with status ``pending_config``.

Severity policy (fail closed): when in doubt, round UP.
  * Any RED indicator match -> RED.
  * Any AMBIGUOUS indicator match (could be innocent, could be a
    safeguarding sign — e.g. unexplained bruising) -> RED. Ambiguity
    rounds up, never down.
  * AMBER indicator match -> AMBER (wellbeing concern, monitor).
  * A secondary deterministic signal (the existing personal_context
    support-category classifier in observation_capture.py) may RAISE
    GREEN to AMBER, never lower anything: the deterministic tier here is
    the floor.

Indicator list grounding: categories follow recognized safeguarding
practice taxonomies (e.g. UK Keeping Children Safe in Education / NSPCC
indicator categories): physical abuse, emotional abuse, sexual abuse,
neglect, and disclosure language. The list is a reviewable module-level
constant so Claudia can audit every pattern.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from src.lingua_viva.access_roles import ROLE_HIERARCHY

GREEN = "GREEN"
AMBER = "AMBER"
RED = "RED"

_TIER_RANK = {GREEN: 0, AMBER: 1, RED: 2}

RESTRICTED_STATUS_OPEN = "open"
RESTRICTED_STATUS_ACKNOWLEDGED = "acknowledged"
RESTRICTED_STATUS_CLOSED = "closed"
RESTRICTED_STATUSES = frozenset(
    {
        RESTRICTED_STATUS_OPEN,
        RESTRICTED_STATUS_ACKNOWLEDGED,
        RESTRICTED_STATUS_CLOSED,
    }
)

# ---------------------------------------------------------------------------
# Indicator taxonomy — reviewable data, not scattered strings.
# Each entry: (category, pattern, note). Categories cite the recognized
# safeguarding-practice grouping the pattern belongs to.
# ---------------------------------------------------------------------------

# RED: explicit safeguarding indicators. Any match -> RED.
RED_INDICATORS: list[tuple[str, str, str]] = [
    # -- Disclosure language (KCSIE-style: a child telling, or being told
    #    to keep secrets, is treated as a disclosure signal).
    ("disclosure", r"\btold me (that )?(someone|he|she|they|[a-z]+) (hurts?|hit|touched|scares?)\b",
     "child disclosed harm by a person"),
    ("disclosure", r"\b(asked|told|begged) me not to tell\b",
     "secrecy request around a concern"),
    ("disclosure", r"\b(don'?t|do not) tell (anyone|my (mum|mom|dad|parents|family))\b",
     "secrecy request around a concern"),
    ("disclosure", r"\b(keep|it'?s) (this |a )?secret\b",
     "secrecy framing by the child"),
    ("disclosure", r"\bsaid (that )?(someone|he|she|they) (hurt|hurts|touched) (him|her|them|me)\b",
     "reported harm to self"),
    # -- Physical abuse indicators.
    ("physical_abuse", r"\b(hit(s|ting)?|beat(s|en|ing)?|punch(es|ed|ing)?|slapp?(s|ed|ing)?|kick(s|ed|ing)?|smack(s|ed|ing)?)\b[^.!?\n]{0,40}\b(at home|by (his|her|their|my))\b",
     "reported physical harm at home / by a named adult"),
    ("physical_abuse", r"\b(dad|daddy|father|mum|mom|mommy|mother|stepdad|stepfather|stepmum|stepmother|uncle|aunt|grandpa|grandma|carer|caregiver|an? adult)\b[^.!?\n]{0,30}\b(hit(s|ting)?|beat(s|ing)?|punch(es|ed|ing)?|slapp?(s|ed|ing)?|kick(s|ed|ing)?|smack(s|ed|ing)?|hurts?)\b",
     "named household adult physically harming the child"),
    ("physical_abuse", r"\b(cigarette )?burn(s| marks?)\b",
     "burn marks"),
    ("physical_abuse", r"\bflinch(es|ed|ing)? (when|at)\b",
     "flinching at contact/approach"),
    # -- Sexual abuse indicators.
    ("sexual_abuse", r"\b(inappropriate|sexuali[sz]ed) (touch(ing)?|behaviou?r|language|knowledge)\b",
     "sexualized behavior/knowledge beyond age expectation"),
    ("sexual_abuse", r"\btouched (him|her|them|me) (somewhere|in a way|where)\b",
     "disclosure of inappropriate touch"),
    # -- Emotional abuse indicators.
    ("emotional_abuse", r"\b(afraid|scared|terrified) (to go|of going) home\b",
     "fear of going home"),
    ("emotional_abuse", r"\bunsafe at home\b",
     "explicit statement of feeling unsafe at home"),
    # -- Neglect indicators.
    ("neglect", r"\b(left|home) alone (at night|for days|overnight|all (day|night))\b",
     "unsupervised for extended periods"),
    ("neglect", r"\bno (food|dinner|breakfast) at home\b",
     "reported lack of food at home"),
    # -- Explicit safeguarding vocabulary (already-escalated language).
    ("explicit", r"\b(safeguarding|child protection) (concern|referral|issue|disclosure)\b",
     "teacher used explicit safeguarding vocabulary"),
    ("explicit", r"\b(abuse|abused|neglect(ed)?|domestic violence)\b",
     "explicit abuse/neglect vocabulary"),
]

# AMBIGUOUS: could be innocent, could be an indicator. Fail closed: any
# match ROUNDS UP to RED for coordinator review (a coordinator dismissing
# a false positive is cheap; a missed indicator is not).
AMBIGUOUS_INDICATORS: list[tuple[str, str, str]] = [
    ("physical_abuse", r"\b(unexplained|recurring|frequent) (bruis(e|es|ing)|marks?|injur(y|ies))\b",
     "unexplained/recurring physical marks"),
    ("physical_abuse", r"\bbruis(e|es|ing)\b",
     "bruising mentioned in a school observation — cause unknown here"),
    ("neglect", r"\b(always|often|constantly|persistently) (hungry|tired|exhausted|unwashed|dirty)\b",
     "persistent hunger/fatigue/poor care pattern"),
    ("neglect", r"\bsame (clothes|uniform) (all week|for days|every day)\b",
     "persistent unchanged clothing"),
    ("emotional_abuse", r"\b(scared|afraid|frightened) of (his|her|their) (dad|father|mum|mom|mother|uncle|aunt|stepdad|stepmum|carer|caregiver)\b",
     "fear of a specific household adult"),
    ("disclosure", r"\bstarted to (tell|say) (me )?something (about home )?(but|and) stopped\b",
     "interrupted possible disclosure"),
]

# AMBER: wellbeing concerns — patterns worth monitoring, not (alone)
# safeguarding indicators.
AMBER_INDICATORS: list[tuple[str, str, str]] = [
    ("wellbeing", r"\b(withdrawn|isolat(ed|ing)|stopped (talking|playing|participating))\b",
     "social withdrawal"),
    ("wellbeing", r"\b(tearful|crying|cried|in tears)\b",
     "tearfulness"),
    ("wellbeing", r"\b(anxious|anxiety|worried|overwhelmed)\b",
     "anxiety signals"),
    ("wellbeing", r"\b(sudden|marked|noticeable) change in (behaviou?r|mood|engagement)\b",
     "sudden behavior change"),
    ("wellbeing", r"\b(hungry|no (lunch|snack)) (today|this morning)\b",
     "one-off hunger/no lunch — monitor for a pattern"),
    ("wellbeing", r"\b(tired|exhausted|falling asleep) (today|in class|this morning)\b",
     "one-off fatigue — monitor for a pattern"),
    ("wellbeing", r"\b(bereavement|grief|family emergency|parents? (are )?(separating|divorcing))\b",
     "difficult personal context affecting wellbeing"),
    ("wellbeing", r"\blow self[- ]esteem|puts? (himself|herself|themselves) down\b",
     "self-esteem concern"),
]


@dataclass(frozen=True)
class SeverityResult:
    tier: str
    matched: tuple[dict, ...] = field(default_factory=tuple)
    rounded_up: bool = False
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "matched": [dict(m) for m in self.matched],
            "rounded_up": self.rounded_up,
            "rationale": self.rationale,
        }


def _scan(text: str, indicators: list[tuple[str, str, str]]) -> list[dict]:
    hits = []
    for category, pattern, note in indicators:
        if re.search(pattern, text):
            hits.append({"category": category, "pattern": pattern, "note": note})
    return hits


def classify_severity(text: str) -> SeverityResult:
    """Deterministic severity classification. Ambiguity rounds UP.

    The deterministic result is the floor: the optional secondary signal
    (existing personal_context support-category classifier) may only
    raise GREEN to AMBER, never lower a tier.
    """
    lowered = " ".join(str(text or "").lower().split())
    if not lowered:
        # An empty transcript cannot be assessed — that is doubt, and
        # doubt rounds up past "normal": mark AMBER so a human looks.
        return SeverityResult(
            tier=AMBER, rounded_up=True,
            rationale="empty/unreadable transcript — cannot rule out a concern (fail closed)",
        )

    red_hits = _scan(lowered, RED_INDICATORS)
    if red_hits:
        return SeverityResult(
            tier=RED, matched=tuple(red_hits),
            rationale="explicit safeguarding indicator matched",
        )

    ambiguous_hits = _scan(lowered, AMBIGUOUS_INDICATORS)
    if ambiguous_hits:
        return SeverityResult(
            tier=RED, matched=tuple(ambiguous_hits), rounded_up=True,
            rationale="ambiguous indicator — rounded up to RED (fail closed)",
        )

    amber_hits = _scan(lowered, AMBER_INDICATORS)
    tier = AMBER if amber_hits else GREEN
    rationale = "wellbeing concern — monitor" if amber_hits else "normal teaching observation"
    rounded_up = False

    if tier == GREEN:
        # Secondary deterministic signal, reused (not duplicated) from the
        # existing capture pipeline. Optional: if it cannot load, the
        # deterministic floor above still stands.
        try:
            from src.education.observation_capture import (
                CATEGORY_SUGGESTION_THRESHOLD,
                suggest_support_categories,
            )

            for suggestion in suggest_support_categories(lowered):
                if (
                    suggestion["category_id"] == "personal_context"
                    and suggestion["confidence"] >= CATEGORY_SUGGESTION_THRESHOLD
                ):
                    tier = AMBER
                    rounded_up = True
                    rationale = (
                        "personal_context secondary signal — raised GREEN to AMBER"
                    )
                    amber_hits = [{
                        "category": "personal_context",
                        "pattern": "suggest_support_categories(personal_context)",
                        "note": "secondary signal from observation_capture",
                    }]
                    break
        except Exception:  # noqa: BLE001 — secondary signal is best-effort
            pass

    return SeverityResult(
        tier=tier, matched=tuple(amber_hits), rounded_up=rounded_up,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Restricted ledger + role chokepoint
# ---------------------------------------------------------------------------

def _state_home() -> Path:
    """LV_STATE_HOME convention (same as teacher_readiness/routing_memory)."""
    return Path(os.environ.get("LV_STATE_HOME", str(Path.home() / ".lingua-viva")))


def safeguarding_dir() -> Path:
    path = _state_home() / "safeguarding"
    path.mkdir(parents=True, exist_ok=True)
    return path


def restricted_ledger_path() -> Path:
    return safeguarding_dir() / "restricted.ndjson"


def notifications_path() -> Path:
    return safeguarding_dir() / "notifications.ndjson"


def _config_path() -> Path:
    return safeguarding_dir() / "config.json"


def safeguarding_config() -> dict:
    """Routing config. Both keys unset by default — notifications then stay
    queued locally with status pending_config. No network code lives here;
    a drain in the existing integration modules would deliver."""
    defaults = {"safeguarding_channel": "", "restricted_drive_folder": ""}
    path = _config_path()
    if not path.exists():
        return defaults
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(loaded, dict):
        return defaults
    return {**defaults, **{k: str(loaded.get(k) or "") for k in defaults}}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_ndjson(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_ndjson(path: Path) -> list[dict]:
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


def _write_ndjson(path: Path, entries: list[dict]) -> None:
    """Rewrite an NDJSON ledger after verified, in-place metadata updates.

    Pattern matches notification_drain._write_all: parse every row, update
    structured fields, then rewrite the complete NDJSON file. Restricted
    narrative fields are preserved on the same entry; they are never copied
    to a public audit stream.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)
    path.write_text(text, encoding="utf-8")


_COORDINATOR_LEVEL = ROLE_HIERARCHY["coordinator"]


def filter_for_role(items: Iterable[dict], role: str) -> list[dict]:
    """THE chokepoint for restricted safeguarding content.

    Coordinator and above see items; everyone else — teacher, co_teacher,
    parent, empty, unknown, garbage — sees an empty list. Fail closed:
    an unknown role maps to level 0, below coordinator.
    """
    level = ROLE_HIERARCHY.get(str(role or "").strip(), 0)
    if level >= _COORDINATOR_LEVEL:
        return list(items)
    return []


def record_red_observation(
    *,
    student_id: str,
    teacher_id: str,
    raw_transcript: str,
    template_type: str = "",
    teacher_edited_transcript: Optional[str] = None,
    severity: Optional[SeverityResult] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Append a RED item to the restricted ledger (NOT the normal store)."""
    severity = severity or classify_severity(
        teacher_edited_transcript or raw_transcript
    )
    entry = {
        "entry_id": f"sg-{uuid.uuid4().hex[:12]}",
        "created_at": _now(),
        "student_id": str(student_id),
        "teacher_id": str(teacher_id),
        "template_type": str(template_type or ""),
        "raw_transcript": str(raw_transcript or ""),
        "teacher_edited_transcript": teacher_edited_transcript,
        "severity": severity.to_dict(),
        "extra": dict(extra or {}),
        "status": RESTRICTED_STATUS_OPEN,
        "status_updated_at": _now(),
        "review_audit": [],
    }
    _append_ndjson(restricted_ledger_path(), entry)
    return entry


def _normalized_restricted_status(entry: dict) -> str:
    status = str(entry.get("status") or "").strip()
    if status == "awaiting_coordinator_review":
        return RESTRICTED_STATUS_OPEN
    if status in RESTRICTED_STATUSES:
        return status
    return RESTRICTED_STATUS_OPEN


def update_restricted_status(
    *,
    entry_id: str,
    status: str,
    reviewed_by: str,
    closed_reason: str = "",
) -> dict:
    """Update coordinator review status for one restricted ledger entry.

    Allowed lifecycle: open -> acknowledged -> closed. Coordinators may also
    close directly from open when the review is completed in one pass. Closed
    entries are terminal. Every transition is recorded on the restricted entry
    itself, so no narrative leaves the restricted store.
    """
    entry_id = str(entry_id or "").strip()
    next_status = str(status or "").strip()
    reviewer = str(reviewed_by or "").strip()
    reason = str(closed_reason or "").strip()
    if not entry_id:
        raise ValueError("entry_id is required")
    if next_status not in RESTRICTED_STATUSES:
        raise ValueError("status must be open, acknowledged, or closed")
    if not reviewer:
        raise ValueError("reviewed_by is required")
    if next_status == RESTRICTED_STATUS_CLOSED and not reason:
        raise ValueError("closed_reason is required when closing an entry")

    entries = _read_ndjson(restricted_ledger_path())
    updated: dict | None = None
    now = _now()
    for entry in entries:
        if str(entry.get("entry_id") or "") != entry_id:
            continue
        current_status = _normalized_restricted_status(entry)
        allowed = {
            RESTRICTED_STATUS_OPEN: {
                RESTRICTED_STATUS_OPEN,
                RESTRICTED_STATUS_ACKNOWLEDGED,
                RESTRICTED_STATUS_CLOSED,
            },
            RESTRICTED_STATUS_ACKNOWLEDGED: {
                RESTRICTED_STATUS_ACKNOWLEDGED,
                RESTRICTED_STATUS_CLOSED,
            },
            RESTRICTED_STATUS_CLOSED: {RESTRICTED_STATUS_CLOSED},
        }[current_status]
        if next_status not in allowed:
            raise ValueError(f"cannot move restricted entry from {current_status} to {next_status}")
        if current_status == RESTRICTED_STATUS_CLOSED and next_status == RESTRICTED_STATUS_CLOSED:
            raise ValueError("restricted entry is already closed")

        audit = entry.get("review_audit")
        if not isinstance(audit, list):
            audit = []
        audit.append(
            {
                "from": current_status,
                "to": next_status,
                "at": now,
                "reviewed_by": reviewer,
                "closed_reason": reason if next_status == RESTRICTED_STATUS_CLOSED else "",
            }
        )
        entry["status"] = next_status
        entry["status_updated_at"] = now
        entry["reviewed_by"] = reviewer
        if next_status == RESTRICTED_STATUS_ACKNOWLEDGED:
            entry["acknowledged_at"] = now
        if next_status == RESTRICTED_STATUS_CLOSED:
            entry["closed_at"] = now
            entry["closed_reason"] = reason
        entry["review_audit"] = audit
        updated = entry
        break

    if updated is None:
        raise KeyError(entry_id)
    _write_ndjson(restricted_ledger_path(), entries)
    return updated


def read_restricted(role: str) -> list[dict]:
    """Read the restricted ledger THROUGH the chokepoint. There is no
    public raw reader — every consumer states a role."""
    return filter_for_role(_read_ndjson(restricted_ledger_path()), role)


# ---------------------------------------------------------------------------
# Notification outbox (local queue — no network, no content)
# ---------------------------------------------------------------------------

def enqueue_notification(*, kind: str, ref_id: str, summary: str = "") -> dict:
    """Queue a notification for the designated safeguarding channel.

    Mirrors the docpipe sync-queue pattern: a local NDJSON entry with an
    honest status. Content discipline: `summary` must be generic — the
    caller never puts observation narrative or student names here,
    because a future drain routes this through Slack/Drive.
    """
    config = safeguarding_config()
    configured = bool(config["safeguarding_channel"])
    entry = {
        "notification_id": f"sgn-{uuid.uuid4().hex[:12]}",
        "created_at": _now(),
        "kind": str(kind),
        "ref_id": str(ref_id),
        "summary": str(summary or "A restricted item requires review."),
        "channel": config["safeguarding_channel"],
        "restricted_drive_folder": config["restricted_drive_folder"],
        # pending_config: no safeguarding_channel configured yet — the
        # notification stays queued locally until an admin sets one and a
        # drain (existing Slack integration outbox) delivers it.
        "status": "queued" if configured else "pending_config",
        "delivery": "local_queue_only",
    }
    _append_ndjson(notifications_path(), entry)
    return entry


def pending_notifications() -> list[dict]:
    return [
        entry
        for entry in _read_ndjson(notifications_path())
        if entry.get("status") in ("queued", "pending_config")
    ]


# ---------------------------------------------------------------------------
# Capture wrapper — the wiring point into the observation flow
# ---------------------------------------------------------------------------

def capture_with_safeguarding(
    pipeline,
    *,
    student_id: str,
    teacher_id: str,
    raw_transcript: str,
    template_type: str,
    teacher_edited_transcript: Optional[str] = None,
    **capture_kwargs: Any,
) -> dict:
    """Severity-gate wrapper around ObservationCapturePipeline.capture().

    GREEN/AMBER: delegate to the normal pipeline unchanged; the result
    gains a ``safeguarding`` field with the tier.
    RED: the observation is written ONLY to the restricted ledger and a
    content-free notification is queued. `pipeline.capture` is never
    called, so RED content never enters the StudentLensStore streams the
    daily brief / parent output read. Fail closed by construction.
    """
    severity = classify_severity(teacher_edited_transcript or raw_transcript)

    if severity.tier == RED:
        entry = record_red_observation(
            student_id=student_id,
            teacher_id=teacher_id,
            raw_transcript=raw_transcript,
            template_type=template_type,
            teacher_edited_transcript=teacher_edited_transcript,
            severity=severity,
            extra={k: v for k, v in capture_kwargs.items() if isinstance(v, (str, int, float, bool))},
        )
        notification = enqueue_notification(
            kind="safeguarding_red",
            ref_id=entry["entry_id"],
            summary="A restricted safeguarding item requires coordinator review.",
        )
        return {
            "restricted": True,
            "observation_stored": False,
            "stored_in": "safeguarding/restricted.ndjson",
            "entry_id": entry["entry_id"],
            "safeguarding": severity.to_dict(),
            "notification": {
                "notification_id": notification["notification_id"],
                "status": notification["status"],
            },
            "note": (
                "This item was routed to the restricted safeguarding ledger. "
                "It is visible to coordinators and above only, and follows "
                "your school's human safeguarding process."
            ),
        }

    result = pipeline.capture(
        student_id=student_id,
        teacher_id=teacher_id,
        raw_transcript=raw_transcript,
        template_type=template_type,
        teacher_edited_transcript=teacher_edited_transcript,
        **capture_kwargs,
    )
    result["restricted"] = False
    result["safeguarding"] = severity.to_dict()
    return result
