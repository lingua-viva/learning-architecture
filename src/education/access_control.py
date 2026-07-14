"""
Cross-Teacher Access Control — "What are other teachers seeing with this
student?"

A student who appears across subjects (a Math teacher and an English
teacher both teaching Amina) needs both teachers to see the full shared
picture — that's normal, expected school practice: co-teachers of the
same student already share access to that student's file in any real
school. The concern this build's PII rules address is EXTERNAL routing
(never send observation content to a model or third party), not
staff-to-staff sharing among a student's own legitimate teachers. So
unlike parent_report.py (which redacts and reframes for an outside
audience), this module does NOT redact between two teachers who both
actually teach the shared student — it gates *who counts as* one of that
student's teachers, then gives full access.

Permission model (v1, documented limitation): a teacher is authorized
for a student if and only if that teacher has personally recorded at
least one observation for them (`StudentLensStore.teachers_for_student`,
added in Turn 8). There is no admin-managed roster/co-teacher assignment
table in this vertical slice — "you must have observed them at least
once" is a bootstrap proxy for "you are one of this student's teachers."
This is enough to stop an unrelated staff member from browsing an
arbitrary student's lens, which is the acceptance criterion's real
concern ("with permissions"), but it is not equivalent to a real
school's official class-roster system. A production deployment needs an
admin tool to grant/revoke teacher-student roster links independent of
observation history (e.g., a newly-assigned co-teacher who hasn't
observed the student yet should still get day-one access) — noted as a
follow-up, not built here.

Local-only: this is an authorization check over StudentLensStore reads.
No external call, no new PII surface — it restricts an existing read
path rather than creating a new one.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.education.student_lens import StudentLensStore, LensNotFoundError


class UnauthorizedLensAccessError(PermissionError):
    """Raised when a teacher_id requests a student lens they are not
    authorized to view (they have never recorded an observation for
    that student, i.e. they are not one of that student's teachers)."""


@dataclass
class SharedStudent:
    student_id: str
    display_name: str
    co_teachers: list  # other teacher_ids who also observe this student


class TeacherLensAccess:
    def __init__(self, store: StudentLensStore):
        self.store = store

    def _authorize(self, teacher_id: str, student_id: str) -> None:
        authorized_teachers = self.store.teachers_for_student(student_id)
        if teacher_id not in authorized_teachers:
            raise UnauthorizedLensAccessError(
                f"teacher {teacher_id!r} has not recorded any observation for "
                f"student {student_id!r} and is not authorized to view this lens"
            )

    def get_lens(self, teacher_id: str, student_id: str) -> dict:
        """Authorized read of a student lens. Raises
        UnauthorizedLensAccessError if this teacher has never observed
        this student; raises LensNotFoundError if the student doesn't
        exist (checked after authorization so we never leak "student
        exists but you can't see it" vs "student doesn't exist" — both
        collapse to the caller getting nothing, matching the export/
        delete rights pattern already used elsewhere in this store)."""
        self._authorize(teacher_id, student_id)
        return self.store.get_lens(student_id)

    def list_shared_students(self, teacher_id: str) -> list:
        """For every student on this teacher's own roster, list which
        other teachers also observe them. Empty co_teachers means this
        teacher is currently the student's only recorded observer."""
        roster = self.store.list_lenses_for_teacher(teacher_id)
        shared = []
        for lens in roster:
            all_teachers = self.store.teachers_for_student(lens["student_id"])
            co_teachers = [t for t in all_teachers if t != teacher_id]
            shared.append(SharedStudent(
                student_id=lens["student_id"],
                display_name=lens.get("display_name", ""),
                co_teachers=co_teachers,
            ))
        return shared

    def get_colleague_observations(self, teacher_id: str, student_id: str) -> list:
        """Observations recorded by OTHER teachers for a shared student —
        answers "what are other teachers seeing with this student?"
        Requires teacher_id to be authorized first (must be one of this
        student's own teachers). No redaction: both are the student's
        actual teachers, this is normal shared-file access, not an
        external disclosure."""
        self._authorize(teacher_id, student_id)
        export = self.store.export_lens(student_id)
        return [o for o in export["observations"] if o["teacher_id"] != teacher_id]
