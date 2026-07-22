"""Regression coverage for dev/specs/SPEC_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md.

EXP09 is the one named, confirmed bug going into that spec: Doctor's
PRIVATE_RISK status rendered with the same CSS class as a routine WARN in
static/index.html's Health view (`status.data === "OK" ? "ok" : "warn"`),
so a privacy stop didn't read as more urgent than "something may need
attention." Live-repro before the fix (not just reasoning from reading):

    echo "dummy" > observations_repro_test.txt   # matches PRIVATE_PATH_PATTERNS
    curl -s http://127.0.0.1:8787/api/health | python3 -m json.tool
    # -> {"status": "PRIVATE_RISK", ...} confirmed reachable via the real
    #    Doctor check_privacy_paths(), not a hypothetical status value.
    rm observations_repro_test.txt

The fix adds a `healthBadgeClass()` helper and a `.badge.risk` CSS class so
PRIVATE_RISK gets distinct (red, filled) styling instead of sharing `.warn`
with FIXABLE/UPDATE_AVAILABLE/BLOCKED/WARN.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "static" / "index.html"

_needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not available on this machine")


def _extract_health_badge_class_fn() -> str:
    text = INDEX_HTML.read_text(encoding="utf-8")
    start = text.index("function healthBadgeClass")
    end = text.index("async function renderHealth")
    return text[start:end]


def _run_for_status(status: str) -> str:
    script = _extract_health_badge_class_fn() + f'\nconsole.log(healthBadgeClass("{status}"));\n'
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, f"node execution failed: {proc.stderr}"
    return proc.stdout.strip()


@_needs_node
def test_healthbadgeclass_extractable():
    fn = _extract_health_badge_class_fn()
    assert "function healthBadgeClass" in fn


@_needs_node
@pytest.mark.parametrize(
    "status,expected_class",
    [
        ("OK", "ok"),
        ("PRIVATE_RISK", "risk"),
        ("WARN", "warn"),
        ("FIXABLE", "warn"),
        ("UPDATE_AVAILABLE", "warn"),
        ("BLOCKED", "warn"),
    ],
)
def test_private_risk_gets_distinct_class_from_warn(status, expected_class):
    """Real execution of the actual JS function (via node), not a string
    match on the source — proves the logic, not just its presence."""
    assert _run_for_status(status) == expected_class


@_needs_node
def test_private_risk_and_warn_are_no_longer_the_same_class():
    assert _run_for_status("PRIVATE_RISK") != _run_for_status("WARN")


def test_risk_badge_css_class_exists_with_distinct_styling():
    text = INDEX_HTML.read_text(encoding="utf-8")
    assert ".badge.risk" in text
    risk_block = text[text.index(".badge.risk"):text.index(".badge.risk") + 200]
    warn_block = text[text.index(".badge.warn"):text.index(".badge.warn") + 200]
    # extract just the two rule bodies for a real inequality check, not eyeballing
    risk_body = re.search(r"\.badge\.risk\s*\{([^}]*)\}", text).group(1)
    warn_body = re.search(r"\.badge\.warn\s*\{([^}]*)\}", text).group(1)
    assert risk_body.strip() != warn_body.strip()


def test_render_health_uses_the_helper_not_the_old_inline_ternary():
    text = INDEX_HTML.read_text(encoding="utf-8")
    assert 'data.status === "OK" ? "ok" : "warn"' not in text
    assert "healthBadgeClass(data.status)" in text


# --- EXP04: Privacy view's "external_calls" claim -------------------------
#
# `src/lingua_viva/privacy_log.py::privacy_summary()` used to hardcode
# `"external_calls": 0` even though `ReasoningEngine._call_model`
# (src/lingua_viva/reasoning.py) has a real code path to
# openai/groq/mistral once a teacher connects a provider
# (src/provider_config.py::connect_provider). That made the Privacy
# view's "all local" claim false in that one real scenario — the badge
# would always read 0 regardless of what actually happened. Fix: log a
# real `external_call_made` privacy event whenever `_call_model` routes
# to an external endpoint, and count those events instead of a literal.
# Live-verified (not just reasoned about) via a mocked external HTTP
# call in an isolated LV_HOME during this pass: counter went 0 -> 1.


def test_external_call_made_is_a_real_privacy_event_type():
    from src.lingua_viva.privacy_log import _generic_detail

    assert _generic_detail("external_call_made") != "Privacy event recorded locally."


def test_privacy_summary_counts_real_external_call_events(monkeypatch, tmp_path):
    from src.lingua_viva.privacy_log import log_event, privacy_summary

    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))

    assert privacy_summary()["external_calls"] == 0
    log_event("external_call_made")
    log_event("external_call_made")
    assert privacy_summary()["external_calls"] == 2


def test_call_model_logs_external_call_for_external_provider_not_local_ollama(monkeypatch, tmp_path):
    """The counter must only move for openai/groq/mistral routing, never for
    the default local Ollama endpoint — otherwise every ordinary local query
    would falsely inflate the "external calls" the teacher sees."""
    import asyncio
    import json as json_module
    from unittest.mock import patch

    from src.lingua_viva.privacy_log import privacy_summary
    from src.lingua_viva.reasoning import ReasoningEngine

    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_TRACE_PATH", str(tmp_path / "traces.ndjson"))

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self):
            return json_module.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

    engine = ReasoningEngine()
    with patch("src.lingua_viva.reasoning.request.urlopen", return_value=_FakeResponse()):
        asyncio.run(engine._call_model("q", "sys", "ollama/qwen2.5:7b"))
        assert privacy_summary()["external_calls"] == 0

        asyncio.run(engine._call_model("q", "sys", "openai/gpt-4o-mini"))
        assert privacy_summary()["external_calls"] == 1


# --- EXP08: Activity Pack's response budget must be really cancellable ----
#
# `query_endpoint` (src/web.py) wraps reasoning in
# `asyncio.wait_for(..., timeout=timeout_seconds)`, but
# `ReasoningEngine._call_model` used to call the blocking
# `urllib.request.urlopen` directly inside an `async def` with no
# `await` point — so asyncio had nowhere to deliver the cancellation.
# Live repro before the fix: POSTing `timeout_seconds: 1` to
# `/api/query` against the real dev server still took ~20.1s
# (LV_REASON_TIMEOUT_SECONDS's own internal socket timeout), not ~1s.
# Fix: run the blocking call via `asyncio.to_thread` so the coroutine
# actually yields and `wait_for` can cancel it on schedule.


def test_call_model_is_actually_cancellable_within_requested_budget(monkeypatch):
    """A slow/hanging network call must not defeat asyncio.wait_for's
    outer timeout — proves real cancellation, not just that the code
    calls asyncio.wait_for somewhere.

    Uses a manual event loop (not asyncio.run) and measures only up to
    where TimeoutError is actually raised: asyncio.run()'s cleanup phase
    waits for the default executor's outstanding thread to finish
    (the still-sleeping urlopen call in the background), which would
    make this assertion measure unrelated shutdown time instead of the
    thing under test — how fast the *caller* gets its answer. That's
    exactly what a long-running uvicorn event loop does in production:
    it doesn't block the response on the orphaned background thread.
    """
    import asyncio
    import time as time_module
    from unittest.mock import patch

    from src.lingua_viva.reasoning import ReasoningEngine

    def _slow_urlopen(*_args, **_kwargs):
        time_module.sleep(5)
        raise AssertionError("should have been cancelled before this returned")

    engine = ReasoningEngine()

    async def _run():
        return await asyncio.wait_for(
            engine._call_model("q", "sys", "ollama/qwen2.5:7b"), timeout=0.5
        )

    loop = asyncio.new_event_loop()
    try:
        with patch("src.lingua_viva.reasoning.request.urlopen", side_effect=_slow_urlopen):
            start = time_module.monotonic()
            with pytest.raises(asyncio.TimeoutError):
                loop.run_until_complete(_run())
            elapsed = time_module.monotonic() - start
    finally:
        loop.close()  # does not wait for the orphaned background thread
    assert elapsed < 2.0, f"wait_for should have cancelled around 0.5s, took {elapsed:.2f}s"
