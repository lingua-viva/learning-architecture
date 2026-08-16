"""Rung 1 — Launch route audit: every route responds, pipeline smokes, data integrity.

SPEC_LV_TEACHER_LAUNCH_VERIFICATION_2026-08-16.md §1
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ["LV_LOCAL_MODEL_ALLOWLIST"] = "test-model"
os.environ["LV_AUTH_MODE"] = "off"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def app():
    from src.web import app as lv_app

    return lv_app


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── 1.1 Route Audit ─────────────────────────────────────────────────────────


def _extract_routes(app) -> list[tuple[str, str]]:
    """Extract all (method, path) from FastAPI app."""
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                routes.append((method.upper(), route.path))
    return routes


@pytest.mark.anyio
async def test_every_route_responds_without_500(client, app):
    """Hit every API route with minimal valid input. None should 500.

    We accept 400/401/403/404/422 (validation/auth errors expected with
    minimal input) but 500 means an unhandled crash — launch blocking.
    """
    routes = _extract_routes(app)
    api_routes = [(m, p) for m, p in routes if p.startswith("/api/")]
    failures = []

    for method, path in api_routes:
        # Skip websocket and streaming-only routes
        if "ws" in path.lower() and method == "GET":
            continue

        # Substitute path params with safe test values
        test_path = re.sub(r"\{[^}]+\}", "test-placeholder", path)

        try:
            if method == "GET":
                resp = await client.get(test_path)
            elif method == "POST":
                resp = await client.post(test_path, json={})
            elif method == "PUT":
                resp = await client.put(test_path, json={})
            elif method == "DELETE":
                resp = await client.delete(test_path)
            elif method == "PATCH":
                resp = await client.patch(test_path, json={})
            else:
                continue

            if resp.status_code == 500:
                failures.append(f"{method} {path} → 500: {resp.text[:200]}")
        except Exception as exc:
            failures.append(f"{method} {path} → exception: {exc}")

    assert not failures, f"Routes returning 500:\n" + "\n".join(failures)


@pytest.mark.anyio
async def test_student_data_routes_are_local_only(monkeypatch):
    """Routes that handle student PII must not call external models.

    Verify model_gate classification logic is correct.
    """
    from src.lingua_viva.model_gate import (
        clear_model_gate_cache,
        is_external_model,
        is_provably_local_model,
        is_syntactically_local_model,
    )

    # External models must be detected
    assert is_external_model("openai/gpt-4")
    assert is_external_model("groq/llama-3.1-70b")
    assert is_external_model("mistral/mistral-large")

    # Local models must NOT be external
    assert not is_external_model("ollama/llama3")
    assert not is_external_model("test-model")
    assert not is_external_model("")

    # Syntactically local check
    assert is_syntactically_local_model("test-model")
    assert is_syntactically_local_model("ollama/llama3")
    assert not is_syntactically_local_model("openai/gpt-4")
    assert not is_syntactically_local_model("llama3:cloud")

    # is_provably_local checks the allowlist at call time
    monkeypatch.setenv("LV_LOCAL_MODEL_ALLOWLIST", "test-model")
    clear_model_gate_cache()
    assert is_provably_local_model("test-model"), (
        "LV_LOCAL_MODEL_ALLOWLIST=test-model should make test-model provably local"
    )

    # External model must never be provably local
    assert not is_provably_local_model("openai/gpt-4")
    assert not is_provably_local_model("groq/llama-3.1-70b")


@pytest.mark.anyio
async def test_no_dead_routes():
    """Every defined route has at least one UI call site OR is documented
    as intentionally backend-only in the reachability manifest."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_route_reachability.py")],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, (
        f"Route reachability check failed:\n{result.stdout}\n{result.stderr}"
    )


# ─── 1.2 Pipeline Smoke ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_pipeline_student_query_stays_local():
    """A query about a specific student routes local, never external.

    When local_only=True and no local model is available, the pipeline
    must fail closed (return a safe message, not call external).
    """
    from src.lingua_viva.model_gate import clear_model_gate_cache
    from src.pipeline import ReasonResult, ReasoningEngine

    engine = ReasoningEngine()

    # Clear the allowlist so no model is provably local
    with patch.dict(os.environ, {"LV_LOCAL_MODEL_ALLOWLIST": ""}):
        clear_model_gate_cache()
        result = await engine.reason(
            query="Tell me about Marco's reading progress",
            context={},
            local_only=True,
        )
        assert isinstance(result, ReasonResult)
        # Must fail closed — no external call allowed
        assert result.model_used in ("none:local_only", "none"), (
            f"Expected fail-closed but got model_used={result.model_used}"
        )
        assert "openai" not in (result.model_used or "")
        assert "groq" not in (result.model_used or "")

    # Restore
    os.environ["LV_LOCAL_MODEL_ALLOWLIST"] = "test-model"
    clear_model_gate_cache()


@pytest.mark.anyio
async def test_pipeline_run_does_not_crash():
    """A basic pipeline.run() call should not raise — even without a model."""
    from src.pipeline import Pipeline

    pipeline = Pipeline()
    # With no model available, it should return a result (possibly degraded)
    # but never crash.
    result = await pipeline.run(
        query="What strategies help emergent readers?",
        intent="RESEARCH",
        session_id="test-session",
    )
    assert result is not None
    assert hasattr(result, "synthesis")
    assert result.synthesis is not None


# ─── 1.3 Data Integrity ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_student_lens_read_write_roundtrip(tmp_path):
    """Write an observation, read it back, verify identical."""
    from src.education.observation_capture import ObservationCapturePipeline
    from src.education.student_lens import StudentLensStore

    db_path = tmp_path / "test_lens.db"
    store = StudentLensStore(db_path=db_path)
    try:
        student_id = store.create_lens(display_name="Test Student")
        pipeline = ObservationCapturePipeline(store=store)
        pipeline.capture(
            student_id=student_id,
            teacher_id="teacher-1",
            raw_transcript="Student showed strong engagement with peer reading activity.",
            template_type="general",
        )
        lens = store.export_lens(student_id)
        assert lens["student_id"] == student_id
        assert lens["display_name"] == "Test Student"
        observations = lens.get("observations") or []
        assert len(observations) >= 1
        assert "strong engagement" in observations[0]["raw_transcript"]
    finally:
        store.close()


@pytest.mark.anyio
async def test_observation_dedup(tmp_path):
    """Double-submit same observation within 300s returns duplicate:true."""
    from src.education.observation_capture import ObservationCapturePipeline
    from src.education.student_lens import StudentLensStore

    db_path = tmp_path / "test_dedup.db"
    store = StudentLensStore(db_path=db_path)
    try:
        student_id = store.create_lens(display_name="Dedup Test")
        pipeline = ObservationCapturePipeline(store=store)
        result1 = pipeline.capture(
            student_id=student_id,
            teacher_id="teacher-1",
            raw_transcript="Student completed the writing task independently.",
            template_type="general",
            duplicate_window_seconds=300,
        )
        assert not result1.get("duplicate")

        result2 = pipeline.capture(
            student_id=student_id,
            teacher_id="teacher-1",
            raw_transcript="Student completed the writing task independently.",
            template_type="general",
            duplicate_window_seconds=300,
        )
        assert result2.get("duplicate") is True
    finally:
        store.close()


@pytest.mark.anyio
async def test_lesson_materials_input_validation():
    """LessonInput validates required fields correctly."""
    from src.lingua_viva.lesson_materials import LessonInput

    lesson = LessonInput(
        ib_programme="PYP",
        subject="Mathematics",
        unit_title="Number Sense",
        topic="Introduction to fractions",
        atl_skills=["thinking", "communication"],
        cefr_target="B1",
        duration_minutes=45,
    )
    assert lesson.topic == "Introduction to fractions"
    assert lesson.subject == "Mathematics"
    assert lesson.cefr_target == "B1"
    assert lesson.duration_minutes == 45


# ─── 1.4 Demo Fallback Detection ─────────────────────────────────────────────


def test_observe_capture_no_demo_fallback():
    """POST /api/observe/capture must not default to 'student-marco' when
    student_id is missing.

    🚨 LAUNCH BLOCKER: line 4350 of web.py defaults to 'student-marco'.
    This test verifies the source code does NOT contain the demo fallback.
    """
    web_src = (REPO / "src" / "web.py").read_text()
    # After the fix, this line should be gone:
    assert 'or "student-marco"' not in web_src, (
        "LAUNCH BLOCKER: /api/observe/capture still defaults to 'student-marco' "
        "when student_id is missing. Must return 400 instead."
    )
