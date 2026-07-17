from fastapi.testclient import TestClient

import doctor.support_loop.doctor as doctor_module
from src.web import app


client = TestClient(app)


def test_health_endpoint_returns_doctor_status(monkeypatch):
    monkeypatch.setattr(doctor_module, "run_doctor", lambda: {
        "status": "OK",
        "summary": "Everything looks healthy.",
        "checks": [],
        "external_calls": False,
    })

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert isinstance(body["status"], str)
