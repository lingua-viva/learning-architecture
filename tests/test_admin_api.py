from fastapi.testclient import TestClient

from src.web import app


client = TestClient(app)


def test_admin_programme_returns_overview():
    response = client.get("/api/admin/programme")

    assert response.status_code == 200
    body = response.json()
    assert body["grade_bands"]
    assert body["source_status"]["badge"] == "Authoritative source: Manuale v1"


def test_admin_trends_not_yet_implemented():
    response = client.get("/api/admin/trends")

    assert response.status_code == 200
    assert response.json() == {"status": "not_yet_implemented"}
