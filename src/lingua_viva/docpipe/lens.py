from __future__ import annotations

from .contracts import ExtractionRecord, LensRecord, ObservationRecord


def create_from_extraction(
    extraction: ExtractionRecord,
    *,
    student_id: str,
    student_name: str,
    added_by: str,
) -> LensRecord:
    raise NotImplementedError("T4 implements lens creation from extraction")


def merge_observation(
    lens: LensRecord,
    observation: ObservationRecord,
    *,
    added_by: str,
) -> LensRecord:
    raise NotImplementedError("T4 implements observation merge")

