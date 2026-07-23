"""Tests for the Add Student and RTI Decision routes (UI wiring fixes)."""
import pytest
from httpx import ASGITransport, AsyncClient
from src.web import app


@pytest.mark.asyncio
async def test_add_student_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/students", json={
            "display_name": "Integration Test Kid",
            "grade_level": "G5",
            "home_languages": ["fr"],
        })
        data = resp.json()

    assert resp.status_code == 200
    assert data["display_name"] == "Integration Test Kid"
    assert "student_id" in data


@pytest.mark.asyncio
async def test_add_student_empty_name_returns_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/students", json={"display_name": ""})
        data = resp.json()

    assert resp.status_code == 400
    assert "required" in data["error"]


@pytest.mark.asyncio
async def test_rti_decision_confirm():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/students/student-marco/rti/decision",
            json={"decision": "confirm"},
        )
        data = resp.json()

    assert resp.status_code == 200
    assert data["decision"] == "confirm"
    assert data["status"] == "recorded"


@pytest.mark.asyncio
async def test_rti_decision_defer():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/students/student-nora/rti/decision",
            json={"decision": "defer"},
        )
        data = resp.json()

    assert resp.status_code == 200
    assert data["decision"] == "defer"


@pytest.mark.asyncio
async def test_rti_decision_invalid_returns_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/students/student-marco/rti/decision",
            json={"decision": "reject"},
        )
        data = resp.json()

    assert resp.status_code == 400
    assert "confirm" in data["error"]
