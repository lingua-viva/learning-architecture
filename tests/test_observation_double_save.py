from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.education.student_lens import Observation, StudentLensStore
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
    return store.create_lens(display_name="Synthetic Observer", grade_level="G4")


def _iso(minutes: int = 0) -> str:
    base = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    return (base + timedelta(minutes=minutes)).isoformat()


def _obs(student_id: str, **overrides) -> Observation:
    payload = {
        "student_id": student_id,
        "teacher_id": "teacher-a",
        "template_type": "general",
        "raw_transcript": "Synthetic learner used a sentence frame during partner practice.",
        "recorded_at": _iso(),
    }
    payload.update(overrides)
    return Observation(**payload)


def _observation_ids(store: StudentLensStore, student_id: str) -> list[str]:
    return [obs["observation_id"] for obs in store.export_lens(student_id)["observations"]]


def test_identical_append_returns_existing_observation_without_second_row(store, student):
    first = store.append_observation(_obs(student, observation_id="obs-one"), duplicate_window_seconds=300)
    second = store.append_observation(_obs(student, observation_id="obs-two", recorded_at=_iso(1)), duplicate_window_seconds=300)

    assert second["duplicate"] is True
    assert second["observation"]["duplicate"] is True
    assert second["observation"]["deduplicated"] is True
    assert second["observation"]["observation_id"] == first["observation"]["observation_id"]
    assert _observation_ids(store, student) == ["obs-one"]


def test_different_text_teacher_or_template_are_legitimate_repeats(store, student):
    store.append_observation(_obs(student, observation_id="base"))
    store.append_observation(
        _obs(
            student,
            observation_id="different-text",
            raw_transcript="Synthetic learner asked a clarifying question.",
            recorded_at=_iso(1),
        )
    )
    store.append_observation(
        _obs(
            student,
            observation_id="different-teacher",
            teacher_id="teacher-b",
            recorded_at=_iso(2),
        )
    )
    store.append_observation(
        _obs(
            student,
            observation_id="different-template",
            template_type="sel_positive",
            sel_domain="peer_interaction",
            recorded_at=_iso(3),
        )
    )

    assert _observation_ids(store, student) == [
        "base",
        "different-text",
        "different-teacher",
        "different-template",
    ]


def test_same_capture_after_window_creates_second_row(store, student):
    first = store.append_observation(_obs(student, observation_id="first"), duplicate_window_seconds=300)
    second = store.append_observation(_obs(student, observation_id="later", recorded_at=_iso(6)), duplicate_window_seconds=300)

    assert not second.get("duplicate")
    assert second["observation"]["observation_id"] != first["observation"]["observation_id"]
    assert _observation_ids(store, student) == ["first", "later"]


def test_duplicate_path_leaves_enrichment_and_rti_state_unchanged(store, student):
    first = store.append_observation(
        _obs(
            student,
            observation_id="single-save",
            rti_tier=2,
            support_entries=[
                {
                    "support_category": "communication_and_language",
                    "need_statement": "Needs wait time before answering.",
                    "teacher_confirmed": True,
                }
            ],
        ),
        duplicate_window_seconds=300,
    )
    after_first = store.get_lens(student)

    second = store.append_observation(
        _obs(
            student,
            observation_id="double-save",
            recorded_at=_iso(1),
            rti_tier=2,
            support_entries=[
                {
                    "support_category": "communication_and_language",
                    "need_statement": "Needs wait time before answering.",
                    "teacher_confirmed": True,
                }
            ],
        ),
        duplicate_window_seconds=300,
    )
    after_second = store.get_lens(student)

    assert first["observation"]["observation_id"] == "single-save"
    assert second["duplicate"] is True
    assert "lens_refresh" not in second
    assert after_second["profile_version"] == after_first["profile_version"]
    assert after_second["rti_tier_history"] == after_first["rti_tier_history"]
    assert after_second["support_profile"] == after_first["support_profile"]
    assert _observation_ids(store, student) == ["single-save"]


def test_capture_route_c7_predicate_one_created_id(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "ethos.yaml"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)

    with TestClient(app) as client:
        created = client.post(
            "/api/students",
            json={"display_name": "Synthetic Route Learner", "grade_level": "G4"},
        )
        assert created.status_code == 200
        student_id = created.json()["student_id"]

        before = {
            obs["observation_id"]
            for obs in client.get(f"/api/students/{student_id}/lens").json()["observations"]
        }
        payload = {
            "student_id": student_id,
            "teacher_id": "teacher-a",
            "transcript": "Synthetic route learner practiced the same sentence frame twice.",
            "template_type": "general",
        }
        first = client.post("/api/observe/capture", json=payload)
        second = client.post("/api/observe/capture", json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["duplicate"] is True
        assert second.json()["observation"]["observation_id"] == first.json()["observation"]["observation_id"]

        after = {
            obs["observation_id"]
            for obs in client.get(f"/api/students/{student_id}/lens").json()["observations"]
        }
        assert len(after - before) == 1


def test_observation_double_save_surface_lock():
    assert "Already saved." in HTML
    assert "result.duplicate" in HTML
    assert "result.observation && result.observation.duplicate" in HTML
    save_handler = HTML[HTML.index("async function saveObservation(") : HTML.index("const GROWTH_BADGE")]
    duplicate_branch = save_handler.index("Already saved.")
    lens_refresh = save_handler.index('await loadLens("obs-lens", false)')
    assert duplicate_branch < lens_refresh
    assert "return;" in save_handler[duplicate_branch:lens_refresh]
