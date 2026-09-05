from __future__ import annotations

import tempfile
import threading
import os
from io import BytesIO
from abc import ABC, abstractmethod
from pathlib import Path


def stt_dependencies_available() -> bool:
    """True when local STT can actually run.

    faster-whisper decodes audio through PyAV (`av`), which bundles the
    FFmpeg shared libraries as a pip wheel — no `ffmpeg` binary on PATH is
    ever invoked (BUG-2, 2026-08-02: the old `shutil.which("ffmpeg")` gate
    was a false requirement that disabled voice on every clean install).
    """
    try:
        import av  # noqa: F401
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> str:
        raise NotImplementedError


class WhisperLocalProvider(STTProvider):
    """Local faster-whisper STT. Audio stays on this computer."""

    def __init__(self, model_size: str = "tiny") -> None:
        if not stt_dependencies_available():
            raise RuntimeError(
                "faster-whisper (with PyAV) is required for local voice transcription."
            )
        self.model_size = model_size
        self._model = None
        self._lock = threading.Lock()

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""
        self._ensure_model()
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            segments, _info = self._model.transcribe(tmp_path, beam_size=1)
            return " ".join(segment.text for segment in segments).strip()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def transcribe_detailed(self, audio_bytes: bytes, *, language: str = 'auto') -> dict:
        """Validated oral sample with timed evidence; decoding/transcription stay local."""
        from faster_whisper.audio import decode_audio
        import numpy as np
        samples = decode_audio(BytesIO(audio_bytes), sampling_rate=16000)
        duration = len(samples) / 16000
        if duration < 2:
            raise RuntimeError('This recording is too short. Record at least two seconds of speech.')
        if duration > 240:
            raise RuntimeError('This recording is longer than four minutes. Choose a shorter sample.')
        if float(np.sqrt(np.mean(np.square(samples)))) < 0.0001:
            raise RuntimeError('This recording is too quiet. Check the microphone and record again.')
        if language not in {'auto', 'en', 'it'}:
            raise RuntimeError('Choose Italian, English or automatic language detection.')
        self._ensure_model()
        segments, info = self._model.transcribe(samples, language=None if language == 'auto' else language,
                                               beam_size=5, vad_filter=True)
        spans = [{'start': float(item.start), 'end': float(item.end), 'text': item.text.strip()} for item in segments]
        return {'text': ' '.join(item['text'] for item in spans).strip(), 'segments': spans,
                'language': info.language, 'duration_seconds': duration}


_provider: WhisperLocalProvider | None = None
_provider_lock = threading.Lock()


def get_stt_provider(model_size: str | None = None) -> WhisperLocalProvider:
    global _provider
    model_size = model_size or os.environ.get('LV_WHISPER_MODEL', 'small')
    if model_size not in {'tiny', 'base', 'small', 'medium'}:
        raise RuntimeError('Choose a supported local speech model: tiny, base, small or medium.')
    if _provider is not None and _provider.model_size == model_size:
        return _provider
    with _provider_lock:
        if _provider is None or _provider.model_size != model_size:
            _provider = WhisperLocalProvider(model_size=model_size)
        return _provider
