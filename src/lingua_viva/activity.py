"""Action Queue / activity feed — Slice 3.

Spec: dev/SPEC_NATIVE_WORKSTATION_SURFACES_2026-07-28.md §Lingua Viva, item 1.
LV has 22 views and no answer to "what did I do today, and what is still
waiting for me?". This builds that feed from artefacts that already exist —
the trace log and the privacy log — rather than introducing a new store that
would only be populated going forward.

Two rules shape everything here:

**No invented history.** Every entry corresponds to a real recorded line. If
nothing was recorded, the feed is empty and says so; it never pads itself with
plausible-looking activity.

**No student names.** The spec's LV constraint: these surfaces get projected
in classrooms and screen-shared in meetings. Anything student-linked uses the
same anonymous reference the governance packs use, so a feed on a projector
cannot expose a child. The trace log is already hash-only, which is why it is
safe to render here at all.
"""

from __future__ import annotations

from typing import Any

# Privacy-log event types that represent something the teacher DID, mapped to
# teacher-facing language. Events that are internal bookkeeping are left out
# rather than dressed up as actions.
ACTION_EVENTS: dict[str, dict[str, str]] = {
    "observation_saved_locally": {
        "label": "Observation saved",
        "detail": "Saved on this computer only.",
        "kind": "observation",
    },
    "ai_attribution_stripped": {
        "label": "Parent draft cleaned",
        "detail": "Wording crediting AI was removed before you saw it.",
        "kind": "parent",
    },
    "drive_files_imported": {
        "label": "Files imported from Drive",
        "detail": "Copied to this computer.",
        "kind": "source",
    },
    "drive_upload_shared": {
        "label": "Shared to Drive",
        "detail": "A deliverable was uploaded to the connected folder.",
        "kind": "source",
    },
    "drive_folder_connected": {
        "label": "Drive folder connected",
        "detail": "Folder access verified. No file content moved.",
        "kind": "source",
    },
    "student_data_kept_local_for_reasoning": {
        "label": "Kept on this computer",
        "detail": "A question mentioning a student was answered locally, not by a cloud model.",
        "kind": "privacy",
    },
    "student_data_blocked": {
        "label": "Details removed",
        "detail": "Student or family details were removed before anything was written.",
        "kind": "privacy",
    },
}


def _trace_entries(limit: int) -> list[dict[str, Any]]:
    from src.lingua_viva.traces import read_traces

    entries = []
    for trace in read_traces(limit=limit):
        external = bool(trace.external_calls)
        entries.append({
            "at": trace.timestamp,
            "kind": "question",
            "label": "Question answered",
            "detail": (
                f"{trace.classification_domain or 'general'} · "
                f"{'answered by a cloud model' if external else 'answered on this computer'}"
            ),
            "status": "done",
            "model": trace.model_used,
            "route": trace.route,
            "sources": list(trace.source_citations or []),
            "reference": trace.trace_id,
        })
    return entries


def _privacy_entries(limit: int) -> list[dict[str, Any]]:
    from src.lingua_viva.privacy_log import read_privacy_events

    entries = []
    for event in read_privacy_events(limit=limit):
        mapped = ACTION_EVENTS.get(event.event_type)
        if not mapped:
            continue  # bookkeeping, not an action the teacher took
        entries.append({
            "at": event.timestamp,
            "kind": mapped["kind"],
            "label": mapped["label"],
            "detail": mapped["detail"],
            "status": "done",
            "model": None,
            "route": "local",
            "sources": [],
            "reference": None,
        })
    return entries


def pending_items() -> list[dict[str, Any]]:
    """Things genuinely waiting on the teacher.

    Read from the student record. When that record cannot be read this
    returns a single explicit "unknown" entry rather than an empty list — an
    empty pending list reads as "you are all caught up", which is a claim this
    function would not be entitled to make.
    """
    import os
    from pathlib import Path

    from src.lingua_viva.config import lv_home

    try:
        from src.education.student_lens import StudentLensStore
        from src.lingua_viva.governance import aron_ref

        override = os.environ.get("LV_STUDENT_DB_PATH")
        path = Path(override) if override else lv_home() / "runtime" / "student_lenses.db"
        if not path.exists():
            return []

        pending: list[dict[str, Any]] = []
        with StudentLensStore(db_path=path) as store:
            for lens in store.list_lenses():
                try:
                    report = store.export_ethos_report(
                        lens["student_id"], include_unconfirmed=True
                    )
                except Exception:
                    continue
                review = report.get("pending_review", {})
                count = len(review.get("traits", [])) + len(review.get("strengths", []))
                if count:
                    pending.append({
                        # Anonymous: this list is designed to be projectable.
                        "reference": aron_ref(lens["student_id"]),
                        "label": "Suggestions awaiting your confirmation",
                        "count": count,
                        "detail": (
                            "Kept out of parent reports until you confirm them."
                        ),
                    })
        return pending
    except Exception as exc:  # noqa: BLE001
        return [{
            "reference": None,
            "label": "Could not read what is pending",
            "count": None,
            "detail": (
                f"The student record could not be opened ({type(exc).__name__}). "
                "This is not the same as having nothing to review."
            ),
            "unknown": True,
        }]


def activity_feed(limit: int = 40) -> dict[str, Any]:
    """Recent actions, newest first, merged from the real local logs."""
    entries = _trace_entries(limit) + _privacy_entries(limit)
    entries.sort(key=lambda item: item.get("at") or "", reverse=True)
    trimmed = entries[:limit]

    pending = pending_items()
    unknown_pending = any(item.get("unknown") for item in pending)

    return {
        "entries": trimmed,
        "entry_count": len(trimmed),
        "pending": pending,
        "pending_total": (
            None if unknown_pending else sum(item.get("count") or 0 for item in pending)
        ),
        "empty_reason": (
            None if trimmed
            else "Nothing has been recorded on this computer yet. Ask a question or save an observation and it will appear here."
        ),
        "privacy_note": (
            "No question text and no student names appear here. Questions are "
            "recorded as a hash; anything student-linked uses an anonymous reference."
        ),
    }
