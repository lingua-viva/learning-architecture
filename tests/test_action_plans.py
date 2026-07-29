from __future__ import annotations

from src.lingua_viva.action_plans.schema import ActionPlan, Approval, GroundingSummary, PlanPolicy, PlannedAction
from src.lingua_viva.action_plans.store import compute_action_plan_id, now_iso, read_plan, read_plans, upsert_plan


def test_action_plan_round_trips(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    plan = ActionPlan(
        action_plan_id=compute_action_plan_id(),
        created_at=now_iso(),
        grounding_id="GRD-1",
        source_record_ids=["SRC-1"],
        grounding_summary=GroundingSummary(tier_used="local", gir_score=0.95),
        actions=[PlannedAction(action_id="parent_report", name="Parent report")],
        approval=Approval(status="pending"),
    )
    upsert_plan(plan)
    loaded = read_plan(plan.action_plan_id)
    assert loaded is not None
    assert loaded.grounding_id == "GRD-1"
    assert read_plans(status="pending")[0]["action_plan_id"] == plan.action_plan_id


def test_approval_state_is_mutable(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    plan = ActionPlan(
        action_plan_id=compute_action_plan_id(),
        created_at=now_iso(),
        actions=[PlannedAction(action_id="import_document")],
        approval=Approval(status="pending"),
        policy=PlanPolicy(can_execute=False),
    )
    upsert_plan(plan)
    plan.approval.status = "approved"
    plan.policy.can_execute = True
    upsert_plan(plan)
    assert read_plan(plan.action_plan_id).approval.status == "approved"  # type: ignore[union-attr]
