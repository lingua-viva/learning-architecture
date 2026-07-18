import json

from fastapi.testclient import TestClient

from src.web import app


client = TestClient(app)


def test_today_endpoint_returns_unit_for_configured_day():
    schedule = {"monday": {"grade": "G3", "unit_id": "g3-unit-1"}}

    response = client.get(
        "/api/teacher/today",
        params={"day": "Monday", "schedule": json.dumps(schedule)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["day"] == "Monday"
    assert body["grade"] == "G3"
    assert body["unit_id"] == "g3-unit-1"
    assert body["cefr_targets"]
    assert body["source"].startswith("Manuale")


def test_today_endpoint_returns_unconfigured_when_no_schedule():
    response = client.get("/api/teacher/today", params={"day": "Monday"})

    assert response.status_code == 200
    assert response.json() == {"configured": False, "day": "Monday"}
