from __future__ import annotations

from src.lingua_viva.deliverables.schema import DeliverableLocation, DeliverableRecord, compute_deliverable_id
from src.lingua_viva.deliverables.store import read_deliverable, read_deliverables, upsert_deliverable


def test_deliverable_store_round_trips(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    deliverable = DeliverableRecord(
        deliverable_id=compute_deliverable_id("TRACE-1", "APL-1"),
        session_id="S1",
        trace_id="TRACE-1",
        action_plan_id="APL-1",
        type="parent_report",
        title="Parent report",
        location=DeliverableLocation(kind="local_path", path="/tmp/report.md"),
        source_record_ids=["SRC-1"],
    )
    upsert_deliverable(deliverable)
    assert read_deliverable(deliverable.deliverable_id).title == "Parent report"  # type: ignore[union-attr]
    assert read_deliverables(action_plan_id="APL-1")[0]["type"] == "parent_report"
