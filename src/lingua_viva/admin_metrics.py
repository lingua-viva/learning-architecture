"""Coordinator view metrics — Gap 4.

Spec: SPEC_LV_REMAINING_GAPS_2026-07-29.md Gap 4, Option A ("build minimal
real versions").

Evidence, Capacity and Trends were honest stubs: they said "deferred" rather
than faking a dashboard, which satisfied the no-fake-affordance law but left
three nav items that do nothing. Each has real data behind it already.

Three rules the stubs got right and these must not lose:

**Simple beats impressive.** Counts and distributions, no charts, no
projections, no LLM. A coordinator can act on "4 students have no observation
this week". They cannot act on a trend line drawn through six data points.

**Say when there is nothing.** A view with no data returns an explicit empty
reason, not a grid of zeros that reads as "everything is fine".

**Students appear as ARON codes.** These are coordinator views — read in
meetings, shown on projectors. Same constraint as Activity and Daily.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.lingua_viva.config import lv_home


def _student_db_path() -> Path:
    override = os.environ.get("LV_STUDENT_DB_PATH")
    if override:
        return Path(override)
    return lv_home() / "runtime" / "student_lenses.db"


def _with_store(callback: Callable[[Any], dict]) -> dict:
    """Run `callback` against the student store, or explain why we could not.

    An unreadable record is reported, never rendered as zeros — the same rule
    the governance Trust Status follows.
    """
    try:
        from src.education.student_lens import StudentLensStore

        path = _student_db_path()
        if not path.exists():
            return {
                "available": True,
                "empty_reason": (
                    "No student records on this computer yet. This fills in as "
                    "observations are saved."
                ),
            }
        with StudentLensStore(db_path=path) as store:
            return callback(store)
    except Exception as exc:  # noqa: BLE001 - reported, never raised at the UI
        return {
            "available": False,
            "reason": type(exc).__name__,
            "empty_reason": (
                "The student record could not be opened. These numbers are "
                "unknown, not zero."
            ),
        }


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# --- Evidence ---------------------------------------------------------------


def evidence_metrics(window_days: int = 7) -> dict:
    """Who has been observed, how often, and in which domains.

    The payload shape is the same whether or not there is data. An endpoint
    that drops keys when it has nothing forces every caller to guard each
    access, and the first one to forget gets a KeyError instead of an empty
    table.
    """

    def build(store) -> dict:
        from src.lingua_viva.governance import aron_ref

        lenses = store.list_lenses()
        if not lenses:
            return {
                "available": True,
                "empty_reason": "No students on this computer yet.",
                "students": [],
                "domains": [],
            }

        cutoff = _iso_days_ago(window_days)
        rows = store._conn.execute(
            "SELECT student_id, ontology_node, recorded_at FROM observations"
        ).fetchall()

        per_student: Counter = Counter()
        recent: Counter = Counter()
        domains: Counter = Counter()
        for row in rows:
            per_student[row["student_id"]] += 1
            if (row["recorded_at"] or "") >= cutoff:
                recent[row["student_id"]] += 1
            node = row["ontology_node"] or "unclassified"
            domains[node] += 1

        students = sorted(
            (
                {
                    "student": aron_ref(lens["student_id"]),
                    "observations": per_student.get(lens["student_id"], 0),
                    "this_window": recent.get(lens["student_id"], 0),
                    "covered": recent.get(lens["student_id"], 0) > 0,
                }
                for lens in lenses
            ),
            key=lambda item: (item["this_window"], item["observations"]),
        )

        return {
            "available": True,
            "window_days": window_days,
            "students": students,
            "domains": [
                {"domain": name, "observations": count}
                for name, count in domains.most_common()
            ],
            "total_observations": sum(per_student.values()),
            "not_covered": sum(1 for item in students if not item["covered"]),
            "empty_reason": (
                None if rows else
                "No observations recorded yet. Save one from the Observe view and it appears here."
            ),
        }

    defaults = {
        "window_days": window_days,
        "students": [],
        "domains": [],
        "total_observations": 0,
        "not_covered": 0,
    }
    return {**defaults, **_with_store(build)}


# --- Capacity ---------------------------------------------------------------


def capacity_metrics(weeks: int = 4) -> dict:
    """How much teacher activity this machine has actually seen, per week.

    Aggregated from the same activity feed the Activity view renders, so the
    two can never disagree. This measures recorded activity on this computer —
    not staffing, enrollment or workload, which the original stub correctly
    said LV has no inputs for. The payload says so rather than letting a
    coordinator read it as a staffing model.
    """
    from src.lingua_viva.activity import activity_feed

    feed = activity_feed(limit=5000)
    entries = feed.get("entries", [])

    buckets: Counter = Counter()
    kinds: Counter = Counter()
    cutoff = _iso_days_ago(weeks * 7)
    for entry in entries:
        at = entry.get("at") or ""
        if at < cutoff:
            continue
        try:
            when = datetime.fromisoformat(at)
        except ValueError:
            continue
        year, week, _ = when.isocalendar()
        buckets[f"{year}-W{week:02d}"] += 1
        kinds[entry.get("kind") or "other"] += 1

    return {
        "available": True,
        "weeks": weeks,
        "per_week": [
            {"week": label, "actions": count} for label, count in sorted(buckets.items())
        ],
        "per_kind": [
            {"kind": kind, "actions": count} for kind, count in kinds.most_common()
        ],
        "total_actions": sum(buckets.values()),
        "measures": (
            "Activity recorded on this computer. This is not a staffing, "
            "enrollment or workload model — Lingua Viva has no inputs for those."
        ),
        "empty_reason": (
            None if buckets else
            "Nothing recorded in this period yet. This fills in as you use Lingua Viva."
        ),
    }


# --- Trends -----------------------------------------------------------------


def trends_metrics(min_cohort: int = 1) -> dict:
    """Support-tier distribution now, and how it moved.

    `min_cohort` guards the concern the original stub raised — not
    overclaiming on a handful of children. Below it, the distribution is
    withheld and the reason is stated.
    """

    def build(store) -> dict:
        import json as _json

        lenses = store.list_lenses()
        if len(lenses) < min_cohort:
            return {
                "available": True,
                "cohort": len(lenses),
                "min_cohort": min_cohort,
                "withheld": True,
                "empty_reason": (
                    f"Only {len(lenses)} student record(s) on this computer. A "
                    "distribution over so few children would say more about the "
                    "sample than the school."
                ),
                "current": [],
                "changes": [],
            }

        current: Counter = Counter()
        changes: list[dict] = []
        for lens in lenses:
            tier = lens.get("rti_current_tier") or 1
            current[int(tier)] += 1
            raw = lens.get("rti_tier_history")
            history = raw if isinstance(raw, list) else []
            if not history and isinstance(raw, str):
                try:
                    history = _json.loads(raw) or []
                except (ValueError, TypeError):
                    history = []
            if history:
                changes.append({"entries": len(history)})

        return {
            "available": True,
            "cohort": len(lenses),
            "min_cohort": min_cohort,
            "withheld": False,
            "current": [
                {"tier": tier, "students": current.get(tier, 0)} for tier in (1, 2, 3)
            ],
            "tier_changes_recorded": sum(item["entries"] for item in changes),
            "students_with_tier_history": len(changes),
            "empty_reason": None,
            "note": (
                "Tier 1 is the default for a new record, so early on this mostly "
                "reflects how many children have been added, not how they are doing."
            ),
        }

    defaults = {
        "cohort": 0,
        "min_cohort": min_cohort,
        "withheld": False,
        "current": [],
        "tier_changes_recorded": 0,
        "students_with_tier_history": 0,
        "note": "",
    }
    return {**defaults, **_with_store(build)}
