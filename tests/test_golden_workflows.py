from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock

from src.lingua_viva.golden_workflows.runner import run_workflows


def test_golden_workflows_run_hermetically(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    results = run_workflows(mode="hermetic")
    assert len(results) == 6
    # The original 5 workflows are purely hermetic (no pipeline/Ollama needed)
    non_voice = [r for r in results if r.workflow_id != "GW-VOICE-006"]
    voice = [r for r in results if r.workflow_id == "GW-VOICE-006"]
    assert len(non_voice) == 5
    assert len(voice) == 1
    assert all(result.status == "PASS" for result in non_voice)
    assert voice[0].status == "PASS", voice[0].notes
    assert all("audit_receipt_id" in result.contract_ids for result in non_voice)


# --- Golden Voice Loop (GW-VOICE-006) ---


@dataclass
class _MockGIR:
    score: float = 0.85
    method: str = "claim_support_v1_heuristic"


@dataclass
class _MockGrounding:
    gir: _MockGIR = field(default_factory=_MockGIR)
    grounding_id: str = "GRD-test"


@dataclass
class _MockPathRecord:
    voice_tone: str = "plain"
    gir_score: float = 0.85
    gir_method: str = "claim_support_v1_heuristic"


@dataclass
class _MockSynthesis:
    content: str = "Test answer."
    confidence: float = 0.9
    model_used: str = "test"
    citations: list = field(default_factory=list)


@dataclass
class _MockPipelineResult:
    session_id: str = "SESSION-GW-VOICE-006"
    query_hash: str = "testhash"
    classification: object = None
    synthesis: _MockSynthesis = field(default_factory=_MockSynthesis)
    path_record: _MockPathRecord = field(default_factory=_MockPathRecord)
    duration_ms: int = 100
    steps_executed: list = field(default_factory=lambda: ["CLASSIFY", "SYNTHESIZE", "STORE"])
    external_called: bool = False
    gap_signals: list = field(default_factory=list)
    grounding: _MockGrounding = field(default_factory=_MockGrounding)


def _patch_voice_loop(monkeypatch, tmp_path, pipeline_result=None, transcript=None):
    """Common setup for voice loop tests."""
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path))
    gap_path = tmp_path / "gap_signals.ndjson"
    monkeypatch.setenv("LV_GAP_SIGNALS_PATH", str(gap_path))

    # Mock the pipeline (avoids needing Ollama)
    result = pipeline_result or _MockPipelineResult()

    async def mock_query(*args, **kwargs):
        return result

    import src.lingua_viva.app as app_mod
    monkeypatch.setattr(app_mod, "run_teacher_query", mock_query)

    # Mock whisper transcription
    from src.lingua_viva import voice_stt

    class MockWhisper:
        def __init__(self, model_size="tiny"):
            pass

        def _ensure_model(self):
            pass

        def transcribe(self, audio_bytes):
            return transcript or "Show me the current project status."

    monkeypatch.setattr(voice_stt, "WhisperLocalProvider", MockWhisper)
    return gap_path


def test_voice_loop_passes_with_good_fixture(monkeypatch, tmp_path):
    _patch_voice_loop(monkeypatch, tmp_path)
    results = run_workflows(mode="hermetic", only="GW-VOICE-006")
    assert len(results) == 1
    result = results[0]
    assert result.workflow_id == "GW-VOICE-006"
    assert result.status == "PASS", f"Expected PASS, got {result.status}: {result.notes}"
    assert len(result.steps) == 5
    step_names = [s.name for s in result.steps]
    assert step_names == ["stt_transcribe", "pipeline_run", "grounding_result", "tone_resolved", "tts_hermetic"]
    assert all(s.status == "PASS" for s in result.steps), [
        f"{s.name}={s.status}" for s in result.steps if s.status != "PASS"
    ]


def test_voice_loop_writes_gap_signal_on_stt_mismatch(monkeypatch, tmp_path):
    gap_path = _patch_voice_loop(
        monkeypatch, tmp_path,
        transcript="completely unrelated garbage text",
    )
    results = run_workflows(mode="hermetic", only="GW-VOICE-006")
    result = results[0]
    assert result.status == "FAIL"
    stt_step = result.steps[0]
    assert stt_step.name == "stt_transcribe"
    assert stt_step.status == "FAIL"

    # Verify gap signal was written
    assert gap_path.exists()
    records = [json.loads(line) for line in gap_path.read_text().splitlines() if line.strip()]
    voice_records = [r for r in records if r.get("entry_node") == "GW-VOICE-006"]
    assert voice_records
    assert any("voice_loop_failure:stt_mismatch" in r.get("gap_signals", []) for r in voice_records)


def test_voice_loop_requires_all_expected_stt_keywords(monkeypatch, tmp_path):
    gap_path = _patch_voice_loop(
        monkeypatch, tmp_path,
        transcript="Show me the current project.",
    )
    results = run_workflows(mode="hermetic", only="GW-VOICE-006")

    stt_step = results[0].steps[0]
    assert results[0].status == "FAIL"
    assert stt_step.status == "FAIL"
    assert stt_step.evidence["keywords_missing"] == ["status"]
    records = [json.loads(line) for line in gap_path.read_text().splitlines() if line.strip()]
    assert any("voice_loop_failure:stt_mismatch" in r.get("gap_signals", []) for r in records)


def test_voice_loop_writes_gap_signal_on_tone_mismatch(monkeypatch, tmp_path):
    # Create a result where stored tone doesn't match what the resolver would compute
    mock_result = _MockPipelineResult()
    mock_result.path_record = _MockPathRecord(voice_tone="name_boundary", gir_score=0.95)
    gap_path = _patch_voice_loop(monkeypatch, tmp_path, pipeline_result=mock_result)

    results = run_workflows(mode="hermetic", only="GW-VOICE-006")
    result = results[0]
    assert result.status == "FAIL"

    tone_step = [s for s in result.steps if s.name == "tone_resolved"][0]
    assert tone_step.status == "FAIL"

    records = [json.loads(line) for line in gap_path.read_text().splitlines() if line.strip()]
    assert any("voice_loop_failure:tone_mismatch" in r.get("gap_signals", []) for r in records)


def test_voice_loop_stt_skip_does_not_fail_workflow(monkeypatch, tmp_path):
    """If Whisper can't load, STT is SKIP but the rest of the pipeline still runs."""
    _patch_voice_loop(monkeypatch, tmp_path)

    from src.lingua_viva import voice_stt

    class BrokenWhisper:
        def __init__(self, model_size="tiny"):
            pass

        def _ensure_model(self):
            raise RuntimeError("Model download failed")

        def transcribe(self, audio_bytes):
            raise RuntimeError("Model download failed")

    monkeypatch.setattr(voice_stt, "WhisperLocalProvider", BrokenWhisper)

    results = run_workflows(mode="hermetic", only="GW-VOICE-006")
    result = results[0]
    stt_step = result.steps[0]
    assert stt_step.name == "stt_transcribe"
    assert stt_step.status == "SKIP"
    # Pipeline should still run with fallback transcript
    pipeline_step = result.steps[1]
    assert pipeline_step.name == "pipeline_run"
    assert pipeline_step.status == "PASS"


def test_voice_loop_audit_pickup(monkeypatch, tmp_path):
    """Voice loop failures surface in improvement_audit ranking."""
    gap_path = _patch_voice_loop(
        monkeypatch, tmp_path,
        transcript="garbage",
    )
    run_workflows(mode="hermetic", only="GW-VOICE-006")

    from src.lingua_viva.improvement_audit import distill_gap_signals, read_gap_signals

    signals = read_gap_signals()
    clusters = distill_gap_signals(signals)
    voice_clusters = [c for c in clusters if "voice_loop_failure" in c["signal"]]
    assert voice_clusters, "voice_loop_failure signal not found in audit ranking"
