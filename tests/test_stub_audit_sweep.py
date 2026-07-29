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


def test_admin_endpoints_return_real_data_not_a_deferred_stub():
    """Was: asserted these three returned status="deferred" with a list of
    prerequisites. Gap 4 (SPEC_LV_REMAINING_GAPS_2026-07-29) built them, so
    the stub contract is gone and the honesty requirement moved rather than
    disappeared — each must now report real state, and must say when it has
    nothing rather than rendering zeros that read as "all fine".
    """
    for path in ("/api/admin/evidence", "/api/admin/capacity", "/api/admin/trends"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()

        assert "status" not in body, f"{path} still returns the deferred stub"
        assert "requires" not in body
        assert "available" in body, f"{path} does not report whether it could read its data"

        # Either there is data, or there is a stated reason there is not.
        has_reason = bool(body.get("empty_reason"))
        has_data = any(
            isinstance(value, list) and value
            for key, value in body.items()
            if key not in {"requires"}
        )
        assert has_data or has_reason, f"{path} returned neither data nor a reason"
