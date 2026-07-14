import os
import shutil
import pytest
from src.integration_onboarding import (
    IntegrationOnboarding,
    PHASE_PURPOSE,
    PHASE_PATTERN,
    PHASE_SCOPE,
    PHASE_GOVERNANCE,
    PHASE_ASSEMBLY,
    PHASE_VERIFY,
    PHASE_DONE,
)


@pytest.fixture
def temp_onboarding_dir():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    scratch_dir = os.path.join(base_dir, "scratch", "onboarding")
    os.makedirs(scratch_dir, exist_ok=True)
    yield base_dir


def _make(base_dir, purpose):
    io = IntegrationOnboarding(base_dir=base_dir)
    io.start(purpose)
    return io


def test_start_captures_purpose_and_advances_to_pattern(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "We need a Slack bot ops staff can ask about scorecard status conversationally.")
    assert io.onboarding_id.startswith("IO-")
    assert io.state["current_phase"] == PHASE_PATTERN
    assert io.state["purpose"]["description"].startswith("We need a Slack bot")
    assert os.path.exists(io.get_onboarding_dir())


def test_pattern_recommends_bridge_for_conversational_signals(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "Ops staff want to ask conversational questions and get real-time answers back.")
    decision = io.get_pattern_decision()
    ids = {opt["id"]: opt for opt in decision["options"]}
    assert ids["BRIDGE"]["recommended"] is True
    assert ids["CAPTURE"]["recommended"] is False


def test_pattern_recommends_capture_for_logging_signals(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "We just need to capture and record transcript observations, append-only, no dialogue.")
    decision = io.get_pattern_decision()
    ids = {opt["id"]: opt for opt in decision["options"]}
    assert ids["CAPTURE"]["recommended"] is True
    assert ids["BRIDGE"]["recommended"] is False


def test_pattern_decision_rejects_invalid_option(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "Generic purpose text with no strong signal.")
    ok, msg = io.decide_pattern("NOPE", "bad option")
    assert ok is False
    assert "Invalid option" in msg
    assert io.state["current_phase"] == PHASE_PATTERN


def test_full_happy_path_conservative_governance(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "Append-only capture of transcripts, no dialogue, local store only.")

    ok, msg = io.decide_pattern("CAPTURE", "This is observation-only, never conversational.")
    assert ok
    assert io.state["current_phase"] == PHASE_SCOPE

    ok, msg = io.set_scope("slack", ["#classroom-1"], "local_store")
    assert ok
    assert io.state["current_phase"] == PHASE_GOVERNANCE

    # rationale too short is rejected
    ok, msg = io.decide_governance("CONSERVATIVE", "short")
    assert ok is False

    ok, msg = io.decide_governance("CONSERVATIVE", "No data needs to leave the local boundary for this case.")
    assert ok
    assert io.state["governance"]["blocks_external"] is True
    assert io.state["governance"]["requires_local"] is True
    assert io.state["current_phase"] == PHASE_ASSEMBLY

    ok, msg = io.run_assembly()
    assert ok
    assert os.path.exists(io.state["artifacts"]["integration_config"])
    assert os.path.exists(io.state["artifacts"]["bridge_wiring_record"])
    assert io.state["current_phase"] == PHASE_VERIFY

    with open(io.state["artifacts"]["bridge_wiring_record"]) as f:
        wiring = f.read()
    assert "Governed Capture pattern" in wiring

    ok, msg = io.run_verify("does the bot record a tagged message", "pass", "verified manually")
    assert ok
    assert io.state["current_phase"] == PHASE_DONE


def test_widen_governance_requires_rationale(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "Conversational bot answering scorecard questions in real time.")
    io.decide_pattern("BRIDGE", "Users ask questions and need real-time answers.")
    io.set_scope("slack", [], "existing_pipeline")

    ok, msg = io.decide_governance("WIDEN", "")
    assert ok is False

    ok, msg = io.decide_governance("WIDEN", "External model needed to answer scorecard Q&A conversationally.")
    assert ok
    assert io.state["governance"]["blocks_external"] is False


def test_assembly_blocked_without_governance_approval(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "Generic bot purpose.")
    io.decide_pattern("CAPTURE", "reasoning")
    io.set_scope("slack", [], "local_store")
    # Do NOT approve governance
    ok, msg = io.run_assembly()
    assert ok is False


def test_verify_fail_keeps_state_in_verify_phase(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "Generic capture-only bot for archiving.")
    io.decide_pattern("CAPTURE", "reasoning here")
    io.set_scope("slack", [], "local_store")
    io.decide_governance("CONSERVATIVE", "No external routing needed for this integration.")
    io.run_assembly()

    ok, msg = io.run_verify("smoke query", "fail", "did not respond correctly")
    assert ok
    assert io.state["current_phase"] == PHASE_VERIFY

    ok, msg = io.run_verify("smoke query", "pass", "fixed and retested")
    assert ok
    assert io.state["current_phase"] == PHASE_DONE


def test_save_and_load_roundtrip(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "Roundtrip persistence check purpose text.")
    io.decide_pattern("CAPTURE", "reasoning")
    oid = io.onboarding_id

    io2 = IntegrationOnboarding(base_dir=temp_onboarding_dir)
    assert io2.load(oid) is True
    assert io2.state["current_phase"] == PHASE_SCOPE
    assert io2.state["pattern"]["decision"] == "CAPTURE"


def test_list_all_finds_started_onboardings(temp_onboarding_dir):
    io = _make(temp_onboarding_dir, "Listing check purpose text unique.")
    ids = IntegrationOnboarding.list_all(base_dir=temp_onboarding_dir)
    assert io.onboarding_id in ids
