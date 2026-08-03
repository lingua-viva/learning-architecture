from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib import error, request

from . import config
from .filemap import build_filemap_context, infer_education_domain
from .messages import local_only_no_model_message, no_model_message
from .privacy_log import log_event
from .traces import append_trace, new_trace


@dataclass
class ReasonResult:
    content: str
    confidence: float
    model_used: str
    tokens_used: int = 0
    error: str = ""
    error_detail: str = ""


class ReasoningEngine:
    """Thin Lingua Viva reasoning client for local-first model calls."""

    _ollama_failures = 0
    _ollama_breaker_open_until = 0.0

    async def reason(
        self,
        query: str,
        context: dict | None = None,
        model: Optional[str] = None,
        default_model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        local_only: bool = False,
        max_tokens: int = 2000,
    ) -> ReasonResult:
        """`local_only` is set by Pipeline.run() when the entry gate detected
        student/family data in this query.

        This engine is the one the real teacher path uses — src/web.py's
        /api/query calls run_teacher_query(), which injects it into Pipeline —
        so this is where the guarantee has to hold. The query arriving here is
        the raw text (ContextBuilder is built from `query`, not the gate's
        sanitized copy), which is fine for a local model and unsafe for a
        cloud one. Every external candidate is discarded, including an
        explicit `model` override; with no local model it fails closed rather
        than falling back to a provider.
        """
        context = context or {}
        start = time.time()
        resolved_model = (
            model
            or config.resolve_provider_model()
            or default_model
            or os.environ.get("LV_REASON_MODEL")
            or self._resolve_best_model()
        )

        if local_only and self._is_external_model(resolved_model):
            try:
                from src.lingua_viva.exit_gates import ExitRequest, check_exit

                check_exit(
                    ExitRequest(
                        surface="reasoning",
                        destination=self._exit_destination(resolved_model),
                        payload_text=query,
                        student_names=tuple(self._known_student_names()),
                        metadata={"local_only": True},
                    )
                )
            except Exception:
                pass
            fallback = next(
                (
                    candidate
                    for candidate in (
                        default_model,
                        os.environ.get("LV_REASON_MODEL"),
                        self._resolve_best_model(),
                    )
                    if candidate and not self._is_external_model(candidate)
                ),
                None,
            )
            try:
                log_event("student_data_kept_local_for_reasoning")
            except Exception:
                pass
            if fallback is None:
                result = ReasonResult(
                    content=local_only_no_model_message(),
                    confidence=0.0,
                    model_used="none:local_only",
                )
                # Still traced: a query that was refused for privacy reasons is
                # exactly the kind the governance view must be able to show.
                self._append_trace(query, context, result, start)
                return result
            resolved_model = fallback

        if system_prompt:
            prompt = system_prompt
            if not self._is_external_model(resolved_model):
                if self._ollama_breaker_open(resolved_model):
                    result = ReasonResult(
                        content="Ollama appears to be down - check if it's running, then try again.",
                        confidence=0.0,
                        model_used=resolved_model,
                    )
                    self._append_trace(query, context, result, start)
                    return result
                query_domain = context.get("filemap_domain") or context.get("domain") or infer_education_domain(query)
                filemap_context = build_filemap_context(query_domain, local_only=True)
                if filemap_context:
                    prompt = f"{system_prompt}\n\nLocal curriculum file locations:\n{filemap_context}"
            result = await self._call_model(query, prompt, resolved_model, max_tokens=max_tokens)
            if result:
                self._append_trace(query, context, result, start)
                return result

        # P1-2 (Claudia QA 2026-08-03): this used to be a bracketed developer
        # placeholder that the UI rendered and the voice path read aloud.
        # Speak an actionable setup message instead; model_used="none" is the
        # signal every downstream degradation check keys on — keep it.
        result = ReasonResult(
            content=no_model_message(),
            confidence=0.0,
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

    async def _call_model(self, query: str, system_prompt: str, model: str, max_tokens: int = 2000) -> Optional[ReasonResult]:
        if self._is_external_model(model):
            from src.lingua_viva.exit_gates import ExitRequest, check_exit

            decision = check_exit(
                ExitRequest(
                    surface="reasoning",
                    destination=self._exit_destination(model),
                    payload_text=f"{system_prompt}\n\n{query}",
                    student_names=tuple(self._known_student_names()),
                )
            )
            if not decision.allowed:
                return None
        url, headers = self._resolve_endpoint(model)
        if self._is_external_model(model):
            log_event("external_call_made", query_text=query)
        model_name = model.split("/", 1)[-1] if "/" in model else model
        payload = json.dumps({
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "temperature": 0.3,
            "max_tokens": max_tokens,
        }).encode("utf-8")
        req = request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        def _blocking_call() -> dict:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                return json.loads(response.read())

        try:
            timeout_seconds = float(os.environ.get("LV_REASON_TIMEOUT_SECONDS", "60"))
            # `request.urlopen` is a blocking call with no await points, so it
            # was previously freezing the whole asyncio event loop for its
            # duration — that made outer `asyncio.wait_for(...)` callers
            # (query_endpoint's timeout_seconds budget) unable to actually
            # cancel it: cancellation can only be delivered at an await
            # point, and there wasn't one. Running it in a worker thread via
            # asyncio.to_thread restores real cancellability. Confirmed via
            # live repro: timeout_seconds=1 previously still took ~20s
            # (LV_REASON_TIMEOUT_SECONDS's own internal socket timeout)
            # before returning, instead of honoring the requested budget.
            body = await asyncio.to_thread(_blocking_call)
        except TimeoutError:
            if self._is_ollama_model(model):
                self._record_ollama_failure()
            return ReasonResult(
                content="",
                confidence=0.0,
                model_used=model,
                tokens_used=0,
                error="timeout",
                error_detail=f"The model took longer than {timeout_seconds:.0f}s to respond. Try a smaller model or a simpler question.",
            )
        except (error.URLError, ConnectionError, OSError, json.JSONDecodeError):
            if self._is_ollama_model(model):
                self._record_ollama_failure()
            return None

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None
        tokens = body.get("usage", {}).get("total_tokens", 0)
        if self._is_ollama_model(model):
            self._reset_ollama_failures()
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
        """True when the call leaves this machine.

        Ollama ":cloud" tags are dispatched through the local daemon but
        execute on Ollama's servers, so a localhost endpoint does not make
        them local. config.detect_model() falls back to a ":cloud" model when
        no preferred local model is installed, which is exactly the case a
        student-data query must not be answered by.
        """
        candidate = (model or "").lower()
        return candidate.startswith(("openai/", "groq/", "mistral/")) or ":cloud" in candidate

    @staticmethod
    def _exit_destination(model: str) -> str:
        candidate = (model or "").lower()
        if candidate.startswith("openai/"):
            return "openai"
        if candidate.startswith("groq/"):
            return "groq"
        if candidate.startswith("mistral/"):
            return "mistral"
        if ":cloud" in candidate:
            return "ollama:cloud"
        return "local"

    @staticmethod
    def _known_student_names() -> list[str]:
        """Best-effort roster names for outbound checks.

        Reasoning is lower-level than the web route, so it cannot depend on
        request context. Reading the local student store here gives the exit
        gate enough context to catch name-only prompts before cloud calls.
        Failure stays fail-soft because explicit privacy patterns and
        local_only still fail closed independently.
        """
        try:
            from src.education.student_lens import StudentLensStore

            with StudentLensStore() as store:
                return [
                    str(lens.get("display_name") or "")
                    for lens in store.list_lenses()
                    if str(lens.get("display_name") or "").strip()
                ]
        except Exception:
            return []

    @staticmethod
    def _is_ollama_model(model: str) -> bool:
        """Whether the Ollama circuit breaker applies. A ':cloud' tag is still
        dispatched via the local daemon, so it belongs to the breaker even
        though _is_external_model() counts it as leaving the machine."""
        candidate = (model or "").lower()
        return not candidate.startswith(("openai/", "groq/", "mistral/"))

    @classmethod
    def _ollama_breaker_open(cls, model: str) -> bool:
        return cls._is_ollama_model(model) and time.time() < cls._ollama_breaker_open_until

    @classmethod
    def _record_ollama_failure(cls) -> None:
        cls._ollama_failures += 1
        if cls._ollama_failures >= 3:
            cls._ollama_breaker_open_until = time.time() + 30

    @classmethod
    def _reset_ollama_failures(cls) -> None:
        cls._ollama_failures = 0
        cls._ollama_breaker_open_until = 0.0

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
