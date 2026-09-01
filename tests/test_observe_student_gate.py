"""BUG-T5.2 (Claudia QA v0.2.78) — the Observe save student gate.

The bug: with two Changs on the roster, "Chang was very helpful today"
saved silently under whichever student was pre-selected. The class: any
save path that trusts the dropdown over the words. The gate: /api/observe/
capture runs the same detection the voice surface uses; on ambiguity or
exact-mismatch it saves NOTHING and returns needs_student_confirmation.
An explicit teacher choice (student_confirmed: true) proceeds.
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


def _create_student(name, grade="G3"):
    response = client.post("/api/students", json={"display_name": name, "grade_level": grade})
    assert response.status_code == 200, response.text
    return response.json()["student_id"]


def _observation_count(student_id):
    lens = client.get(f"/api/students/{student_id}/lens").json()
    return len(lens.get("observations") or [])


def test_shared_surname_two_siblings_blocks_and_saves_nothing(isolated_state):
    abigail = _create_student("Chang Abigail")
    marco = _create_student("Chang Marco")

    response = client.post("/api/observe/capture", json={
        "student_id": abigail,
        "transcript": "Chang was very helpful today.",
        "template_type": "general",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["needs_student_confirmation"] is True
    assert body["reason"] == "ambiguous"
    assert {c["student_id"] for c in body["candidates"]} == {abigail, marco}
    assert body["selected"]["student_id"] == abigail
    # Nothing was saved for either sibling.
    assert _observation_count(abigail) == 0
    assert _observation_count(marco) == 0


def test_exact_mismatch_blocks_and_names_the_detected_student(isolated_state):
    abigail = _create_student("Chang Abigail")
    marco = _create_student("Marco Bianchi")

    response = client.post("/api/observe/capture", json={
        "student_id": abigail,
        "transcript": "Marco Bianchi finished his essay early.",
        "template_type": "general",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["needs_student_confirmation"] is True
    assert body["reason"] == "mismatch"
    assert body["detected"]["student_id"] == marco
    assert body["selected"]["student_id"] == abigail
    assert _observation_count(abigail) == 0
    assert _observation_count(marco) == 0


def test_student_confirmed_proceeds_after_teacher_choice(isolated_state):
    abigail = _create_student("Chang Abigail")
    _create_student("Chang Marco")

    payload = {
        "student_id": abigail,
        "transcript": "Chang was very helpful today.",
        "template_type": "general",
    }
    blocked = client.post("/api/observe/capture", json=payload)
    assert blocked.json()["needs_student_confirmation"] is True

    confirmed = client.post(
        "/api/observe/capture", json={**payload, "student_confirmed": True}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert "observation" in confirmed.json()
    assert _observation_count(abigail) == 1


def test_no_name_in_transcript_saves_normally(isolated_state):
    abigail = _create_student("Chang Abigail")
    _create_student("Chang Marco")

    response = client.post("/api/observe/capture", json={
        "student_id": abigail,
        "transcript": "Worked hard on the essay and asked good questions.",
        "template_type": "general",
    })
    assert response.status_code == 200, response.text
    assert "observation" in response.json()
    assert _observation_count(abigail) == 1


def test_transcript_naming_the_selected_student_saves_normally(isolated_state):
    abigail = _create_student("Chang Abigail")
    _create_student("Chang Marco")

    response = client.post("/api/observe/capture", json={
        "student_id": abigail,
        "transcript": "Abigail worked hard on her essay today.",
        "template_type": "general",
    })
    assert response.status_code == 200, response.text
    assert "observation" in response.json()
    assert _observation_count(abigail) == 1
