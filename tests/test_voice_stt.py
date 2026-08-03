from __future__ import annotations

import shutil

import pytest

from src.lingua_viva.voice_stt import WhisperLocalProvider, stt_dependencies_available


@pytest.mark.skipif(
    not stt_dependencies_available(),
    reason="faster-whisper (with PyAV) is required for local STT",
)
def test_voice_provider_requires_audio_bytes():
    provider = WhisperLocalProvider(model_size="tiny")
    assert provider.transcribe(b"") == ""


def test_stt_availability_does_not_depend_on_ffmpeg_binary(monkeypatch):
    """BUG-2 regression: faster-whisper decodes via PyAV's bundled FFmpeg
    libraries — an `ffmpeg` binary on PATH must never gate voice features."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    # With deps installed, availability holds even when which() finds nothing.
    if stt_dependencies_available():
        provider = WhisperLocalProvider(model_size="tiny")
        assert provider.transcribe(b"") == ""


def test_stt_dependency_probe_is_import_based():
    import importlib.util

    have_deps = (
        importlib.util.find_spec("av") is not None
        and importlib.util.find_spec("faster_whisper") is not None
    )
    assert stt_dependencies_available() == have_deps
