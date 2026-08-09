from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.education.student_lens import StudentLensStore
from src.web import app

REPO = Path(__file__).resolve().parents[1]
HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "ethos.yaml"))
    with StudentLensStore() as s:
        yield s


@pytest.fixture
def student(store):
    return store.create_lens(display_name="Synthetic Learner", grade_level="G5")


def _isolate_web(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "ethos.yaml"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)


def test_model_suggested_strength_confirm_reaches_report_body(store, student):
    profile = store.add_profile_strength(
        student,
        "academic",
        "Explains fractions with clear examples",
        "model",
        confidence="model_suggested",
    )
    entry_id = profile["academic_strengths"][0]["id"]

    report = store.export_ethos_report(student, include_unconfirmed=True)
    assert report["academic_strengths"] == []
    assert report["pending_review"]["academic_strengths"][0]["id"] == entry_id
    assert report["pending_review"]["academic_strengths"][0]["created_by"] == "model"

    store.confirm_profile_strength(student, "academic", entry_id)

    confirmed = store.export_ethos_report(student, include_unconfirmed=True)
    assert confirmed["academic_strengths"][0]["text"] == "Explains fractions with clear examples"
    assert confirmed["pending_review"]["academic_strengths"] == []


def test_model_suggested_ethos_confirm_updates_profile_and_ledger(store, student):
    profile = store.add_ethos_evidence(
        student,
        "grit",
        "Kept revising after a first draft was returned",
        "model",
        confidence="model_suggested",
    )
    evidence_id = profile["traits"]["grit"]["evidence"][0]["id"]

    report = store.export_ethos_report(student, include_unconfirmed=True)
    assert report["traits"] == []
    pending_trait = report["pending_review"]["traits"][0]
    assert pending_trait["trait_id"] == "grit"
    assert pending_trait["items"][0]["id"] == evidence_id

    store.confirm_ethos_evidence(student, "grit", evidence_id)

    confirmed = store.export_ethos_report(student, include_unconfirmed=True)
    assert confirmed["traits"][0]["evidence"][0]["summary"] == (
        "Kept revising after a first draft was returned"
    )
    assert confirmed["pending_review"]["traits"] == []
    ledger = store.list_evidence(student, target_type="ethos_trait", target_id="grit")
    assert ledger[0]["evidence_id"] == evidence_id
    assert ledger[0]["confidence_level"] == "teacher_confirmed"


def test_dismiss_strength_leaves_pending_and_never_reaches_report(store, student):
    profile = store.add_profile_strength(
        student,
        "personal",
        "Invites quiet classmates into partner work",
        "model",
        confidence="model_suggested",
    )
    entry_id = profile["personal_strengths"][0]["id"]

    store.dismiss_profile_strength(student, "personal", entry_id)

    report = store.export_ethos_report(student, include_unconfirmed=True)
    assert report["pending_review"]["personal_strengths"] == []
    assert report["personal_strengths"] == []
    lens = store.get_lens(student)
    stored = lens["strengths_profile"]["personal_strengths"][0]
    assert stored["id"] == entry_id
    assert stored["active"] is False


@pytest.mark.parametrize(
    "call",
    [
        lambda s, sid: s.confirm_profile_strength(sid, "academic", "missing"),
        lambda s, sid: s.confirm_profile_strength(sid, "social", "missing"),
        lambda s, sid: s.confirm_ethos_evidence(sid, "missing_trait", "missing"),
        lambda s, sid: s.confirm_ethos_evidence(sid, "grit", "missing"),
    ],
)
def test_unknown_review_targets_raise_without_profile_version_bump(store, student, call):
    store.add_ethos_evidence(
        student,
        "grit",
        "Persisted through a challenging reading",
        "model",
        confidence="model_suggested",
    )
    before = store.get_lens(student)["profile_version"]

    with pytest.raises(ValueError):
        call(store, student)

    assert store.get_lens(student)["profile_version"] == before


def test_pending_evidence_routes_confirm_and_reject_unknown_without_write(monkeypatch, tmp_path):
    _isolate_web(monkeypatch, tmp_path)
    with StudentLensStore() as store:
        sid = store.create_lens(display_name="Synthetic Route Learner")
        profile = store.add_profile_strength(
            sid,
            "academic",
            "Uses evidence when explaining a choice",
            "model",
            confidence="model_suggested",
        )
        entry_id = profile["academic_strengths"][0]["id"]

    with TestClient(app) as client:
        pending = client.get(f"/api/students/{sid}/evidence/pending")
        assert pending.status_code == 200
        item = pending.json()["pending_review"]["academic_strengths"][0]
        assert item["id"] == entry_id

        missing = client.post(
            f"/api/students/{sid}/evidence/confirm",
            json={
                "target": "strength",
                "kind": "academic",
                "entry_id": "missing",
                "action": "confirm",
            },
        )
        assert missing.status_code == 422

        with StudentLensStore() as store:
            before = store.get_lens(sid)["profile_version"]

        confirmed = client.post(
            f"/api/students/{sid}/evidence/confirm",
            json={
                "target": "strength",
                "kind": "academic",
                "entry_id": entry_id,
                "action": "confirm",
            },
        )
        assert confirmed.status_code == 200
        with StudentLensStore() as store:
            lens = store.get_lens(sid)
            assert lens["profile_version"] == before + 1
            assert lens["strengths_profile"]["academic_strengths"][0]["confidence"] == "teacher_confirmed"

        not_found = client.get("/api/students/does-not-exist/evidence/pending")
        assert not_found.status_code == 404


def test_pending_evidence_review_surface_lock():
    assert "/api/students/${state.selectedStudent}/evidence/pending" in HTML
    assert "/api/students/${state.selectedStudent}/evidence/confirm" in HTML
    assert "Waiting for your confirmation" in HTML
    assert "Confirm" in HTML
    assert "Dismiss" in HTML
    assert "Kept out of parent reports until you confirm them." in HTML
    assert "Nothing waiting for review." in HTML
    assert "confirm all" not in HTML.lower()
