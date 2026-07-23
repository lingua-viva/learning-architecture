"""Test that /api/query returns an honest error message when ontology.engine is missing."""
import asyncio
from unittest.mock import patch, AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient
from src.web import app


@pytest.mark.asyncio
async def test_module_not_found_returns_honest_message():
    """When ontology.engine is missing, /api/query returns a user-friendly message."""
    broken = AsyncMock(side_effect=ModuleNotFoundError("No module named 'ontology.engine'"))

    with patch("src.lingua_viva.app.run_teacher_query", broken):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/query", json={"query": "test question", "intent": "TEACH"})
            data = resp.json()

    assert resp.status_code == 200
    assert "ontology" not in data["error"]
    assert data.get("unavailable") is True
    assert "isn't able to answer" in data["error"]


@pytest.mark.asyncio
async def test_import_error_returns_honest_message():
    """ImportError also triggers the honest message."""
    broken = AsyncMock(side_effect=ImportError("cannot import name 'OntologyEngine'"))

    with patch("src.lingua_viva.app.run_teacher_query", broken):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/query", json={"query": "hello", "intent": "TEACH"})
            data = resp.json()

    assert "ontology" not in data.get("error", "").lower()
    assert data.get("unavailable") is True


@pytest.mark.asyncio
async def test_generic_exception_still_returns_str():
    """Other exceptions still fall through to the generic handler."""
    broken = AsyncMock(side_effect=RuntimeError("something unexpected"))

    with patch("src.lingua_viva.app.run_teacher_query", broken):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/query", json={"query": "hello", "intent": "TEACH"})
            data = resp.json()

    assert data["error"] == "something unexpected"
    assert data.get("unavailable") is None
