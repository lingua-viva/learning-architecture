"""Integration tests for bridges, missions, web_search, and skill_loader."""
import tempfile
import shutil
import pytest


def test_bridges_import():
    from bridges import EmailBridge, SlackBridge, WhatsAppBridge, DiscordBridge, SignalBridge, TeamsBridge
    assert EmailBridge.is_configured() is False  # No env vars set
    assert SlackBridge.is_configured() is False


def test_missions_lifecycle():
    from src.missions import MissionEngine, StepState
    tmp = tempfile.mkdtemp()
    try:
        engine = MissionEngine(store_dir=tmp)
        m = engine.create("test-mission", steps=[
            {"title": "Step A", "description": "First step"},
            {"title": "Step B", "description": "Second step"},
        ], mission_class="sequential")

        assert m.slug == "test-mission"
        assert len(m.steps) == 2

        # State machine: can't skip pending→completed
        r = engine.update_step(m.slug, "step-a", StepState.COMPLETED)
        assert "error" in r

        # Valid: pending→in_progress→completed
        r = engine.update_step(m.slug, "step-a", StepState.IN_PROGRESS)
        assert r["ok"] is True
        r = engine.update_step(m.slug, "step-a", StepState.COMPLETED)
        assert r["ok"] is True

        # Can't complete mission with pending steps
        r = engine.complete(m.slug, "Done")
        assert "error" in r

        # Skip remaining, then complete
        engine.update_step(m.slug, "step-b", StepState.SKIPPED)
        r = engine.complete(m.slug, "Done")
        assert r["ok"] is True
    finally:
        shutil.rmtree(tmp)


def test_missions_memory():
    from src.missions import MissionEngine
    tmp = tempfile.mkdtemp()
    try:
        engine = MissionEngine(store_dir=tmp)
        engine.create("mem-test", steps=[{"title": "A"}])
        engine.save_memory("mem-test", "key1", {"data": "value"})
        engine.append_memory("mem-test", "list1", "item1")
        engine.append_memory("mem-test", "list1", "item2")

        assert engine.get_memory("mem-test", "key1") == {"data": "value"}
        assert engine.get_memory("mem-test", "list1") == ["item1", "item2"]
    finally:
        shutil.rmtree(tmp)


def test_skill_loader():
    from skills.loader import load_skills_dir
    import os
    # Load existing skills directory
    skills_dir = os.path.join(os.path.dirname(__file__), "..", "skills")
    skills = load_skills_dir(skills_dir)
    # May find SKILL.md files or not — just shouldn't crash
    assert isinstance(skills, list)


def test_web_search_no_key():
    """Without API keys, search returns graceful error."""
    import asyncio
    from src.gateway.web_search import search
    results = asyncio.run(search("test query"))
    assert isinstance(results, list)
    # Should indicate no key available
    assert len(results) >= 1
