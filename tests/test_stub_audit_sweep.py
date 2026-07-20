from fastapi.testclient import TestClient

from src.pipeline import EntryGate, ExitGate, GatewayInterface, IntegrityGate
from src.web import app


client = TestClient(app)


def test_entry_gate_blocks_private_runtime_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))

    report = EntryGate().scan("student name: Marco needs support")

    assert report.blocked is True
    assert report.sensitivity_level == "high"
    assert "Marco" not in report.sanitized_query


def test_gateway_external_research_disabled_for_lingua_viva():
    import asyncio

    class Classification:
        blocks_external = False

    assert asyncio.run(GatewayInterface().needs_external(Classification(), 0.1, user_intent="RESEARCH")) is False


def test_exit_gate_deferred_noop_contract():
    safe, threats = ExitGate().scan_response("local response", "local")

    assert safe is True
    assert threats == []


def test_integrity_gate_deferred_noop_contract():
    result = IntegrityGate(ontology_nodes={"LV-CUR-001"}, knowledge_ids={"KL-1"}).check("local content")

    assert result.warnings == []


def test_admin_deferred_endpoints_explain_prerequisites():
    for path in ("/api/admin/evidence", "/api/admin/capacity", "/api/admin/trends"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "deferred"
        assert body["phase"] == "LV Phase 7 admin dashboard"
        assert body["reason"]
        assert body["requires"]
