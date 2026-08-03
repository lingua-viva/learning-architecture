from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.lingua_viva import config
from src.lingua_viva.model_gate import is_external_model
from src.lingua_viva.reasoning import ReasoningEngine


def _assert_no_external_default() -> None:
    resolved = config.resolve_provider_model()
    if resolved and is_external_model(resolved):
        raise RuntimeError(
            "docpipe requires a local-only model configuration; external default "
            f"{resolved!r} is not allowed"
        )


_assert_no_external_default()


@dataclass(frozen=True)
class ModelResult:
    content: str
    confidence: float
    model_used: str
    tokens_used: int = 0
    error: str = ""
    error_detail: str = ""


class ModelClient(Protocol):
    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        context: dict | None = None,
        max_tokens: int = 2000,
    ) -> ModelResult:
        ...


class LocalModelClient:
    """Local-only wrapper around the existing Lingua Viva reasoning path."""

    def __init__(self, engine: ReasoningEngine | None = None) -> None:
        self._engine = engine or ReasoningEngine()

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        context: dict | None = None,
        max_tokens: int = 2000,
    ) -> ModelResult:
        result = await self._engine.reason(
            prompt,
            context=context or {},
            model=config.detect_model(),
            system_prompt=system_prompt,
            local_only=True,
            max_tokens=max_tokens,
        )
        return ModelResult(
            content=result.content,
            confidence=result.confidence,
            model_used=result.model_used,
            tokens_used=result.tokens_used,
            error=result.error,
            error_detail=result.error_detail,
        )

