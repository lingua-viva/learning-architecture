from fastapi.testclient import TestClient

from src.web import app


client = TestClient(app)


def test_curriculum_unit_endpoint_smoke():
    response = client.get("/api/curriculum/unit/g3-unit-1")

    assert response.status_code == 200
    assert response.json()["unit_id"] == "g3-unit-1"


def test_admin_evidence_endpoint_smoke():
    response = client.get("/api/admin/evidence")

    assert response.status_code == 200
    assert response.json()["status"] == "not_yet_implemented"


def test_admin_capacity_endpoint_smoke():
    response = client.get("/api/admin/capacity")

    assert response.status_code == 200
    assert response.json()["status"] == "not_yet_implemented"


def test_stats_endpoint_smoke():
    response = client.get("/api/stats")

    assert response.status_code == 200
    body = response.json()
    assert "ontology_nodes" in body or "error" in body


def test_session_endpoint_smoke():
    response = client.get("/api/session")

    assert response.status_code == 200
    assert "active" in response.json()
