"""Extra Daily-Brief widgets from the 2026-08-09 build wave.

The Daily view (`/api/daily/briefing` in src/web.py) is the coordination
surface: "what needs attention today, across the organization." This module
supplies additional widgets so web.py only needs a one-line, fail-soft hook.

Staff-room constraint (same as the base brief): every student is referenced
anonymously via governance.aron_ref — the brief is projected in meetings.

Deliberately ABSENT: safeguarding. RED items live in a separate restricted
ledger (src/lingua_viva/safeguarding.py) that the brief never reads —
containment by store separation, not by filtering.
"""

from __future__ import annotations


def _absence_widget() -> dict:
    from src.lingua_viva.absence_escalation import check_escalations
    from src.lingua_viva.governance import aron_ref

    pending = check_escalations()
    return {
        "id": "absence_escalations",
        "label": "Absence escalations for the coordinator",
        "count": len(pending),
        "students": sorted({aron_ref(e["student_id"]) for e in pending}),
        "detail": (
            "Attendance thresholds reached — the coordinator decides the follow-up."
            if pending
            else "No absence patterns above threshold."
        ),
        "status": "attention" if pending else "ok",
    }


def _library_widget() -> dict:
    from src.lingua_viva.library import status

    info = status()
    doc_count = int(info.get("doc_count", 0))
    return {
        "id": "knowledge_library",
        "label": "Knowledge library",
        "count": doc_count,
        "students": [],
        "detail": (
            f"{doc_count} documents / {info.get('chunk_count', 0)} chunks indexed locally."
            if doc_count
            else "Empty — upload IB guides and support materials in Sources or Prepare."
        ),
        "status": "ok",
    }


def _artifacts_widget(window_days: int) -> dict:
    import time
    from src.lingua_viva.pdf_generator import artifacts_dir

    root = artifacts_dir("coursework")
    cutoff = time.time() - window_days * 86400
    recent = (
        [p for p in root.glob("*.pdf") if p.stat().st_mtime >= cutoff]
        if root.is_dir()
        else []
    )
    return {
        "id": "coursework_artifacts",
        "label": f"Coursework packs generated in {window_days} days",
        "count": len(recent),
        "students": [],
        "detail": (
            "Ready to print from the artifacts folder."
            if recent
            else "None this window — generate per-class packs from the curriculum."
        ),
        "status": "ok",
    }


def extra_widgets(window_days: int) -> list[dict]:
    """Fail-soft: a broken extension must never blank the base brief."""
    widgets: list[dict] = []
    for build in (
        _absence_widget,
        _library_widget,
        lambda: _artifacts_widget(window_days),
    ):
        try:
            widgets.append(build())
        except Exception:  # noqa: BLE001 — degrade that widget only
            continue
    return widgets
