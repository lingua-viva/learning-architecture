"""
Pipeline EXECUTE-step wiring tests — Gap 4, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md.

Verifies the pipeline-level contract around `education_executor`, not the
education modules themselves (see test_education_pipeline_execute.py for
those): EXECUTE only fires when an executor is injected AND the classified
node is one it handles; RESEARCH never fires once EXECUTE has produced a
result (even when it otherwise would, i.e. low confidence + not blocked);
"missing_data" bypasses the local-reasoning model call entirely; "ok"
wraps the verbatim module markdown with a short model-written intro
rather than letting the model regenerate or paraphrase it.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio

from src.pipeline import Pipeline, ReasonResult
from src.education.pipeline_execute import ExecutionResult


class RecordingGateway:
    """Would normally trigger RESEARCH (needs_external always True) — used
    to prove EXECUTE suppresses it, not just that RESEARCH happens to not
    be needed for other reasons."""

    def __init__(self):
        self.needs_external_called = False

    async def needs_external(self, classification, local_confidence, user_intent=None):
        self.needs_external_called = True
        return True

    async def sanitize_query(self, query, classification):
        raise AssertionError("sanitize_query must not be called when EXECUTE already ran")

    async def query_external(self, query, classification, knowledge_context):
        raise AssertionError("query_external must not be called when EXECUTE already ran")


class RecordingReasoning:
    def __init__(self, response_content="wrapper intro"):
        self.call_count = 0
        self.response_content = response_content

    async def reason(self, query, context, model=None, default_model=None, system_prompt=None):
        self.call_count += 1
        return ReasonResult(content=self.response_content, confidence=0.8, model_used="fake-model")


class StubExecutor:
    def __init__(self, result: ExecutionResult):
        self._result = result

    def execute(self, riu_id, query):
        return self._result


def test_execute_suppresses_research_even_when_low_confidence():
    gateway = RecordingGateway()
    # LV-CUR-002 classifies at ~0.6 confidence and blocks_external=False —
    # would normally trigger RESEARCH.
    executor = StubExecutor(ExecutionResult("LV-CUR-002", "ok", "# grounded content"))
    reasoning = RecordingReasoning()
    pipeline = Pipeline(gateway=gateway, reasoning=reasoning, education_executor=executor)

    result = asyncio.run(pipeline.run(
        "differentiate this photosynthesis lesson for three levels",
        eval_mode=True,
    ))

    assert "EXECUTE" in result.steps_executed
    assert "RESEARCH" not in result.steps_executed
    assert result.external_called is False
    assert gateway.needs_external_called is False


def test_missing_data_bypasses_reasoning_model_call():
    reasoning = RecordingReasoning()
    executor = StubExecutor(ExecutionResult(
        "LV-STU-003", "missing_data",
        "I don't have enough observation history for this student yet.",
    ))
    pipeline = Pipeline(reasoning=reasoning, education_executor=executor)

    result = asyncio.run(pipeline.run(
        "Amina RTI tier support intervention",
        eval_mode=True,
    ))

    assert reasoning.call_count == 0
    assert "I don't have enough observation history" in result.synthesis.content


def test_ok_status_wraps_and_appends_verbatim_markdown_unaltered():
    reasoning = RecordingReasoning(response_content="Here's the grouping for tomorrow.")
    markdown = "# Teacher Guide\n\n- Group A: Amina, Karim\n- Group B: Noor"
    executor = StubExecutor(ExecutionResult("LV-TCH-002", "ok", markdown))
    pipeline = Pipeline(reasoning=reasoning, education_executor=executor)

    result = asyncio.run(pipeline.run(
        "group my students for tomorrow flexible grouping",
        eval_mode=True,
    ))

    assert reasoning.call_count == 1
    assert "Here's the grouping for tomorrow." in result.synthesis.content
    # The module's markdown must appear byte-for-byte, not re-derived.
    assert markdown in result.synthesis.content


def test_execute_does_not_fire_for_unwired_node():
    reasoning = RecordingReasoning()

    class NoneExecutor:
        def execute(self, riu_id, query):
            return None

    pipeline = Pipeline(reasoning=reasoning, education_executor=NoneExecutor())
    result = asyncio.run(pipeline.run("what has codex done this week?", intent="REFLECT", eval_mode=True))

    assert "EXECUTE" not in result.steps_executed
    assert reasoning.call_count == 1
