from __future__ import annotations

import shutil

import pytest

from src.lingua_viva.voice_stt import WhisperLocalProvider


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required for local STT")
def test_voice_provider_requires_audio_bytes():
    provider = WhisperLocalProvider(model_size="tiny")
    assert provider.transcribe(b"") == ""
