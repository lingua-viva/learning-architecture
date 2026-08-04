"""Governance control plane — Trust Status and signed observation export.

Spec: dev/SPEC_GOVERNANCE_CONTROL_PLANE_2026-07-28.md §Lingua Viva.

The acceptance criteria that matter here are about honesty, not features:
  - zero student-identifiable information in an export without confirmation
  - publication-safety violations BLOCK the export with a clear explanation
  - Trust Status shows "all student data local" when true — and says
    "unknown" when it genuinely cannot tell, rather than printing a zero

That last one is the one worth guarding hardest. A governance screen that
turns an unreadable database into a confident 0 is worse than no screen,
because it converts an unknown into a false assurance for an administrator.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.lingua_viva import governance
from src.web import app

# Demo-roster seeding was removed from web.py (T9 / acceptance A6) —
# these tests exercise flows that need students on the roster, so they
# opt in to the explicit demo_roster fixture from conftest.py.
pytestmark = pytest.mark.usefixtures("demo_roster")


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_EXPORT_SIGNING_KEY_PATH", str(tmp_path / "signing_key"))
    yield


# --- sealing ---------------------------------------------------------------


def test_seal_verifies_and_survives_a_json_round_trip():
    body = {"pack_type": "observation_export", "items": [1, 2, 3]}
    pack = dict(body)
    pack["seal"] = governance.sign_payload(body)

    assert governance.verify_pack(pack) is True
    # A pack is handed over as a file, so it must still verify after being
    # written and read back.
    assert governance.verify_pack(json.loads(json.dumps(pack))) is True


def test_tampering_is_detected():
    body = {"pack_type": "observation_export", "confirmed": 2}
    pack = dict(body)
    pack["seal"] = governance.sign_payload(body)

    tampered = json.loads(json.dumps(pack))
    tampered["confirmed"] = 99
    assert governance.verify_pack(tampered) is False


def test_a_pack_with_no_seal_does_not_verify():
    assert governance.verify_pack({"pack_type": "x"}) is False
    assert governance.verify_pack({"seal": {}}) is False
    assert governance.verify_pack("not a pack") is False


def test_signing_key_is_private_and_stable(tmp_path):
    import os
    import stat

    first = governance.key_fingerprint()
    mode = stat.S_IMODE(os.stat(governance.signing_key_path()).st_mode)
    assert mode == 0o600
    assert governance.key_fingerprint() == first, "key must not regenerate per call"


def test_anonymous_reference_is_stable_unique_and_not_the_id():
    ref = governance.anonymous_student_ref("student-marco")
    assert ref == governance.anonymous_student_ref("student-marco")
    assert ref != governance.anonymous_student_ref("student-ana")
    assert "marco" not in ref.lower()


# --- publication safety ----------------------------------------------------


def test_a_student_name_in_a_pack_blocks_the_export():
    pack = {"notes": "Marco did well this term"}
    result = governance.check_publication_safety(pack, student_names=["Marco"])
    assert result["blocked"] is True
    assert result["violations"][0]["rule"] == "privacy_rules.student_data"


def test_ai_attribution_blocks_the_export():
    pack = {"summary": "This assessment was AI-generated from the observations."}
    result = governance.check_publication_safety(pack, student_names=[])
    assert result["blocked"] is True
    assert result["violations"][0]["rule"] == "privacy_rules.ai_attribution"


def test_a_clean_pack_passes_and_still_reports_what_it_cannot_judge():
    result = governance.check_publication_safety({"a": 1}, student_names=["Marco"])
    assert result["blocked"] is False
    # The policy is mostly judgement; the check must not imply it cleared
    # rules it never evaluated.
    assert result["advisory"]
    assert "privacy_rules.student_data" in result["enforced_rules"]


def test_very_short_names_do_not_cause_false_blocks():
    """A two-letter name would match inside ordinary words and block every
    export, which trains a teacher to ignore the warning."""
    result = governance.check_publication_safety(
        {"text": "an ordinary sentence"}, student_names=["Al"]
    )
    assert result["blocked"] is False


# --- Trust Status ----------------------------------------------------------


def test_trust_status_answers_all_five_questions():
    status = governance.trust_status()
    ids = [question["id"] for question in status["questions"]]
    assert ids == ["accessed", "stayed_local", "sent_externally", "redacted", "needs_review"]
    for question in status["questions"]:
        assert question["question"].endswith("?")
        assert question["answer"]
        assert question["status"] in {"ok", "attention", "unknown"}


def test_external_question_answers_no():
    status = governance.trust_status()
    external = next(q for q in status["questions"] if q["id"] == "sent_externally")
    assert external["answer"] == "No"


def test_unreadable_student_record_reports_unknown_not_zero(monkeypatch):
    """The single most important honesty guard in this module."""
    monkeypatch.setattr(
        governance, "_student_totals", lambda: {"available": False, "reason": "OSError"}
    )
    status = governance.trust_status()

    assert status["student_record_readable"] is False
    accessed = next(q for q in status["questions"] if q["id"] == "accessed")
    assert accessed["status"] == "unknown"
    assert "0 student" not in accessed["answer"]
    review = next(q for q in status["questions"] if q["id"] == "needs_review")
    assert review["answer"] == "Unknown"


def test_counters_reflect_real_privacy_events():
    from src.lingua_viva.privacy_log import log_event

    log_event("student_data_blocked")
    log_event("student_data_blocked")
    log_event("student_data_kept_local_for_reasoning")

    counters = governance.trust_status()["counters"]
    assert counters["redactions"] == 2
    assert counters["kept_local_for_student_data"] == 1


# --- routes ----------------------------------------------------------------


def test_trust_route_returns_the_five_questions():
    response = client.get("/api/governance/trust")
    assert response.status_code == 200
    assert len(response.json()["questions"]) == 5


def test_observation_export_is_sealed_and_carries_no_student_name():
    roster = client.get("/api/students").json()["students"]
    assert roster, "demo roster should seed at least one student"
    student = roster[0]

    response = client.post(
        "/api/governance/observation-export", json={"student_id": student["student_id"]}
    )
    assert response.status_code == 200
    pack = response.json()["pack"]

    assert pack["student"]["reference"].startswith("S-")
    name = (student.get("display_name") or "").lower()
    if len(name) >= 3:
        assert name not in json.dumps(pack).lower(), "the child's name is in the pack"

    verify = client.post("/api/governance/verify-pack", json={"pack": pack})
    assert verify.json()["valid"] is True


def test_export_separates_confirmed_from_model_suggested():
    """An administrator needs to see that unconfirmed model output never
    entered the report body."""
    roster = client.get("/api/students").json()["students"]
    pack = client.post(
        "/api/governance/observation-export", json={"student_id": roster[0]["student_id"]}
    ).json()["pack"]

    assert "confirmed_by_teacher" in pack
    assert "model_suggested_not_confirmed" in pack
    assert pack["model_suggested_not_confirmed"]["note"]


def test_export_rejects_an_unknown_student():
    response = client.post(
        "/api/governance/observation-export", json={"student_id": "no-such-student"}
    )
    assert response.status_code == 404
    assert "error" in response.json()


def test_export_requires_a_student_id():
    assert client.post("/api/governance/observation-export", json={}).status_code == 400


def test_verify_route_rejects_a_tampered_pack():
    roster = client.get("/api/students").json()["students"]
    pack = client.post(
        "/api/governance/observation-export", json={"student_id": roster[0]["student_id"]}
    ).json()["pack"]

    pack["confirmed_by_teacher"]["count"] = 999
    result = client.post("/api/governance/verify-pack", json={"pack": pack}).json()
    assert result["valid"] is False
    assert "changed" in result["detail"]


def test_seal_does_not_overclaim_what_it_proves():
    """An administrator must not read this as a school or third-party
    signature."""
    roster = client.get("/api/students").json()["students"]
    pack = client.post(
        "/api/governance/observation-export", json={"student_id": roster[0]["student_id"]}
    ).json()["pack"]
    means = pack["seal"]["means"].lower()
    assert "not a signature from the school" in means


# --- the UI actually calls all of this -------------------------------------


def test_governance_view_is_reachable_and_wired():
    body = client.get("/").text
    assert '["governance", "Governance"' in body, "no Governance entry in the nav"
    assert "governance: renderGovernance," in body, "view not registered"
    assert 'api("/api/governance/trust")' in body
    assert 'api("/api/governance/observation-export", {' in body
    assert 'api("/api/governance/verify-pack", {' in body


def test_old_views_no_longer_assert_untrue_things():
    """Three claims that were rendered regardless of the facts: a hardcoded
    'external calls: 0' badge, a count labelled 'No external calls', and a
    flat 'No data has left this machine.'"""
    body = client.get("/").text
    assert 'external calls: 0</span>' not in body
    assert "<p>No external calls</p>" not in body
    assert "No data has left this machine." not in body
