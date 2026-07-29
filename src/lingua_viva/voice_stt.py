from __future__ import annotations

import shutil
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path


class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> str:
        raise NotImplementedError


class WhisperLocalProvider(STTProvider):
    """Local faster-whisper STT. Audio stays on this computer."""

    def __init__(self, model_size: str = "tiny") -> None:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg is required for local voice transcription.")
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


_provider: WhisperLocalProvider | None = None
_provider_lock = threading.Lock()


def get_stt_provider(model_size: str = "tiny") -> WhisperLocalProvider:
    global _provider
    if _provider is not None:
        return _provider
    with _provider_lock:
        if _provider is None:
            _provider = WhisperLocalProvider(model_size=model_size)
        return _provider
