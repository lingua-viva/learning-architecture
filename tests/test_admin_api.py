from fastapi.testclient import TestClient

from src.web import app


client = TestClient(app)


def test_admin_programme_returns_overview():
    response = client.get("/api/admin/programme")

    assert response.status_code == 200
    body = response.json()
    assert body["grade_bands"]
    assert body["source_status"]["badge"] == "Authoritative source: Manuale v1"


def test_admin_trends_deferred_with_reason():
    response = client.get("/api/admin/trends")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "deferred"
    assert body["phase"] == "LV Phase 7 admin dashboard"
    assert "anonymized observations" in body["reason"]
    assert body["requires"]
