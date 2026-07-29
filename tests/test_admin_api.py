from fastapi.testclient import TestClient

from src.web import app


client = TestClient(app)


def test_admin_programme_returns_overview():
    response = client.get("/api/admin/programme")

    assert response.status_code == 200
    body = response.json()
    assert body["grade_bands"]
    assert body["source_status"]["badge"] == "Authoritative source: Manuale v1"


def test_admin_trends_reports_a_real_distribution_or_withholds_it():
    """Was: asserted the deferred stub. Gap 4 built the view, and the concern
    the stub named — not overclaiming on a handful of children — is now
    enforced by a minimum-cohort guard rather than by refusing to render."""
    response = client.get("/api/admin/trends")

    assert response.status_code == 200
    body = response.json()
    assert "status" not in body, "the deferred stub is gone"
    assert body["available"] is True
    if body["withheld"]:
        assert body["current"] == []
        assert body["empty_reason"]
    else:
        assert sum(row["students"] for row in body["current"]) == body["cohort"]
