from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib import error, request

from . import config
from .filemap import build_filemap_context, infer_education_domain
from .privacy_log import log_event
from .traces import append_trace, new_trace


@dataclass
class ReasonResult:
    content: str
    confidence: float
    model_used: str
    tokens_used: int = 0


class ReasoningEngine:
    """Thin Lingua Viva reasoning client for local-first model calls."""

    async def reason(
        self,
        query: str,
        context: dict | None = None,
        model: Optional[str] = None,
        default_model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> ReasonResult:
        context = context or {}
        start = time.time()
        resolved_model = (
            model
            or config.resolve_provider_model()
            or default_model
            or os.environ.get("LV_REASON_MODEL")
            or self._resolve_best_model()
        )

        if system_prompt:
            prompt = system_prompt
            if not self._is_external_model(resolved_model):
                query_domain = context.get("filemap_domain") or context.get("domain") or infer_education_domain(query)
                filemap_context = build_filemap_context(query_domain, local_only=True)
                if filemap_context:
                    prompt = f"{system_prompt}\n\nLocal curriculum file locations:\n{filemap_context}"
            result = await self._call_model(query, prompt, resolved_model)
            if result:
                self._append_trace(query, context, result, start)
                return result

        result = ReasonResult(
            content=f"[Local reasoning for {context.get('riu_id', 'lingua-viva')} - no model available]",
            confidence=0.7,
            model_used="none",
        )
        self._append_trace(query, context, result, start)
        return result

    def _resolve_provider_model(self) -> Optional[str]:
        return config.resolve_provider_model()

    def _resolve_best_model(self) -> str:
        if not hasattr(self, "_cached_model"):
            self._cached_model = config.detect_model()
        return self._cached_model

    async def _call_model(self, query: str, system_prompt: str, model: str) -> Optional[ReasonResult]:
        url, headers = self._resolve_endpoint(model)
        model_name = model.split("/", 1)[-1] if "/" in model else model
        payload = json.dumps({
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }).encode("utf-8")
        req = request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            timeout_seconds = float(os.environ.get("LV_REASON_TIMEOUT_SECONDS", "20"))
            with request.urlopen(req, timeout=timeout_seconds) as response:
                body = json.loads(response.read())
        except (error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError):
            return None

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None
        tokens = body.get("usage", {}).get("total_tokens", 0)
        return ReasonResult(content=content, confidence=0.75, model_used=model, tokens_used=tokens)

    @staticmethod
    def _resolve_endpoint(model: str) -> tuple[str, dict[str, str]]:
        if model.startswith("openai/"):
            key = config.provider_api_key("openai") or os.environ.get("OPENAI_API_KEY", "")
            return "https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {key}"}
        if model.startswith("groq/"):
            key = config.provider_api_key("groq") or os.environ.get("GROQ_API_KEY", "")
            return "https://api.groq.com/openai/v1/chat/completions", {"Authorization": f"Bearer {key}"}
        if model.startswith("mistral/"):
            key = config.provider_api_key("mistral") or os.environ.get("MISTRAL_API_KEY", "")
            return "https://api.mistral.ai/v1/chat/completions", {"Authorization": f"Bearer {key}"}
        return "http://localhost:11434/v1/chat/completions", {}

    @staticmethod
    def _is_external_model(model: str) -> bool:
        return model.startswith(("openai/", "groq/", "mistral/"))

    def _append_trace(self, query: str, context: dict, result: ReasonResult, start: float) -> None:
        try:
            domain = str(context.get("domain") or context.get("classification_domain") or infer_education_domain(query) or "general")
            sources = context.get("source_citations") or context.get("sources") or []
            if isinstance(sources, str):
                sources = [sources]
            trace = new_trace(
                query,
                domain=domain,
                model_used=result.model_used,
                duration_ms=int((time.time() - start) * 1000),
                token_count=result.tokens_used,
                source_citations=[str(item) for item in sources],
                privacy_events=[],
            )
            append_trace(trace)
            log_event("query_processed_locally", query_text=query)
        except Exception:
            return
