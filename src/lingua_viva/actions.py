"""Lightweight teacher action registry — Slice 2.

Spec: dev/SPEC_ACTION_DISPATCHER_FORMS_2026-07-28.md §Lingua Viva.

LV has no actions/*.yaml and does not need MC's 63-action registry: execution
is wired into the pipeline through src/education/pipeline_execute.py. What it
lacked was a declared answer to the question the spec's item 3 asks — *before*
an action runs, what will it read, and can any of it leave this computer?

So this registry is deliberately small and code-defined. Each entry names the
route that actually implements it, so a route rename breaks the test rather
than leaving the registry quietly describing something that no longer exists.

`leaves_machine` is the field that matters. It is set from what the action
genuinely does, not from what would be reassuring:
  - Drive upload is the one action here that sends anything out, and it says so.
  - Everything else is local, including the ones that read student records.

The preview text is what a teacher sees before they act, so it is written in
their language and never promises more than the code delivers.
"""

from __future__ import annotations

from typing import Any

ACTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "capture_observation",
        "label": "Save an observation",
        "view": "observe",
        "route": "POST /api/observe/capture",
        "reads_student_data": True,
        "writes_student_data": True,
        "leaves_machine": False,
        "preview": (
            "Writes to the student record on this computer. Nothing is uploaded "
            "or shared. You review the text before it is saved."
        ),
    },
    {
        "id": "generate_activity_pack",
        "label": "Generate a three-level activity pack",
        "view": "prepare",
        "route": "POST /api/prepare/activity",
        "reads_student_data": True,
        "writes_student_data": False,
        "leaves_machine": False,
        "preview": (
            "Reads the support tiers on this computer to group learners. The pack "
            "itself contains no child's name."
        ),
    },
    {
        "id": "build_rubric",
        "label": "Show an assessment rubric",
        "view": "assess",
        "route": "GET /api/assess/rubric/{unit_id}",
        "reads_student_data": False,
        "writes_student_data": False,
        "leaves_machine": False,
        "preview": "Reads the curriculum only. No student record is opened.",
    },
    {
        "id": "parent_report",
        "label": "Draft a message for a parent",
        "view": "parents",
        "route": "POST /api/parents/recommendation",
        "reads_student_data": True,
        "writes_student_data": False,
        "leaves_machine": False,
        "preview": (
            "Reads one child's record to write a draft you review. Wording that "
            "credits AI is removed. Nothing is sent — you send it yourself."
        ),
    },
    {
        "id": "rti_decision",
        "label": "Record a support-tier decision",
        "view": "students",
        "route": "PUT /api/students/{student_id}/rti",
        "reads_student_data": True,
        "writes_student_data": True,
        "leaves_machine": False,
        "preview": (
            "Changes a child's support tier on this computer. The system suggests; "
            "you decide and the decision is recorded as yours."
        ),
    },
    {
        "id": "student_profile",
        "label": "Open a student profile",
        "view": "students",
        "route": "GET /api/students",
        "reads_student_data": True,
        "writes_student_data": False,
        "leaves_machine": False,
        "preview": "Opens the record stored on this computer.",
    },
    {
        "id": "export_lens_to_drive",
        "label": "Share a deliverable to Google Drive",
        "view": "sources",
        "route": "POST /api/google-drive/upload",
        "reads_student_data": True,
        "writes_student_data": False,
        # The only action here that sends anything out. Said plainly.
        "leaves_machine": True,
        "preview": (
            "This uploads a file to the Google Drive folder you connected. It is "
            "the one action on this list that sends something off this computer. "
            "Check what it contains before you share it."
        ),
    },
    {
        "id": "import_document",
        "label": "Import a document to read",
        "view": "sources",
        "route": "POST /api/google-drive/import",
        "reads_student_data": False,
        "writes_student_data": False,
        "leaves_machine": False,
        "preview": (
            "Copies a file from Drive onto this computer. Nothing is sent the "
            "other way."
        ),
    },
)


def registry() -> dict[str, Any]:
    """The action list plus the counts a governance preview needs."""
    student_data = [a for a in ACTIONS if a["reads_student_data"]]
    outbound = [a for a in ACTIONS if a["leaves_machine"]]
    return {
        "actions": list(ACTIONS),
        "total": len(ACTIONS),
        "touch_student_data": len(student_data),
        "leave_this_computer": len(outbound),
        "outbound_ids": [a["id"] for a in outbound],
        "note": (
            "Every action here runs on this computer unless it is marked as "
            "sending something out."
        ),
    }


def preview_for(action_id: str) -> dict[str, Any] | None:
    """The governance preview for one action, or None if unknown.

    Returns None rather than a generic reassurance for an unrecognised id — a
    preview that says "this is safe" about an action the registry has never
    heard of is exactly the fake affordance the build order's law forbids.
    """
    for action in ACTIONS:
        if action["id"] == action_id:
            return {
                "id": action["id"],
                "label": action["label"],
                "preview": action["preview"],
                "reads_student_data": action["reads_student_data"],
                "writes_student_data": action["writes_student_data"],
                "leaves_machine": action["leaves_machine"],
            }
    return None
