from __future__ import annotations

from .contracts import GroundingReport, LensRecord, ManifestRecord


def verify(
    lens: LensRecord,
    *,
    manifest: ManifestRecord | None = None,
) -> GroundingReport:
    raise NotImplementedError("T7 implements grounding verification")

