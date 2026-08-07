"""Observation deduplication guard — teacher-readiness C7.

Both /api/observe/capture and /api/voice/act must reject a duplicate
observation (same student, same teacher, same transcript, within 60s)
and return the existing observation_id with deduplicated=True instead
of creating a second record.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

import src.web as web

client = TestClient(web.app)


@pytest.fixture()
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "student_lenses.db"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "ethos.yaml"))
    return tmp_path


def _create_student(name="Marco Bianchi", grade="G3"):
    response = client.post("/api/students", json={"display_name": name, "grade_level": grade})
    assert response.status_code == 200, response.text
    return response.json()["student_id"]


def test_observe_capture_dedup_within_60s(isolated_state):
    student_id = _create_student()
    payload = {
        "student_id": student_id,
        "transcript": "Marco helped a classmate understand the task today.",
        "template_type": "general",
    }
    first = client.post("/api/observe/capture", json=payload)
    assert first.status_code == 200, first.text
    first_obs = first.json()["observation"]
    assert "deduplicated" not in first_obs or not first_obs.get("deduplicated")

    second = client.post("/api/observe/capture", json=payload)
    assert second.status_code == 200, second.text
    second_obs = second.json()["observation"]
    assert second_obs["deduplicated"] is True
    assert second_obs["observation_id"] == first_obs["observation_id"]


def test_voice_act_dedup_within_60s(isolated_state):
    student_id = _create_student()
    seed = client.post(
        "/api/observe/capture",
        json={
            "student_id": student_id,
            "teacher_id": "local-teacher",
            "transcript": "Private raw transcript phrase.",
            "template_type": "cefr",
            "cefr_dimension": "speaking",
            "cefr_level_observed": "A2",
            "cefr_direction": "progressing",
        },
    )
    assert seed.status_code == 200, seed.text

    payload = {
        "teacher_id": "local-teacher",
        "transcript": "Marco helped a classmate understand the task today.",
    }
    first = client.post("/api/voice/act", json=payload)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["action_taken"] == "saved"
    first_obs = first_body["result"]["observation"]
    assert "deduplicated" not in first_obs or not first_obs.get("deduplicated")

    second = client.post("/api/voice/act", json=payload)
    assert second.status_code == 200, second.text
    second_obs = second.json()["result"]["observation"]
    assert second_obs["deduplicated"] is True
    assert second_obs["observation_id"] == first_obs["observation_id"]

    lens = client.get(f"/api/students/{student_id}/lens").json()
    matching = [
        obs for obs in lens["observations"]
        if obs["raw_transcript"] == payload["transcript"]
    ]
    assert len(matching) == 1
