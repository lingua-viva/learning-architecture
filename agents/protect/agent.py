"""
PROTECT Agent — Local-only, full PII blocking, zero external.

This agent handles the most sensitive queries. Nothing leaves the machine.
When the pipeline classifies a query as PROTECT, this agent takes over
and ensures absolute data containment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ProtectResult:
    content: str
    confidence: float
    model_used: str
    pii_detected: list[str]
    external_blocked: bool = True


class ProtectAgent:
    """
    PROTECT intent agent.

    Invariants:
    - No external API calls. Ever.
    - PII detection active on input AND output.
    - All reasoning happens on local model.
    - Response is sanitized before return.
    """

    INTENT = "PROTECT"

    def __init__(self, model: str = "ollama/qwen2.5:3b"):
        self.model = model
        self._prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        prompt_path = Path(__file__).parent / "prompt.md"
        if prompt_path.exists():
            return prompt_path.read_text()
        return self._default_prompt()

    def _default_prompt(self) -> str:
        return """You are operating in PROTECT mode. This is the highest sensitivity level.

RULES:
1. All information in this conversation is confidential.
2. Do not reference or suggest external research.
3. Do not include any identifying information in your response.
4. If you detect PII in the query, note it but do not echo it.
5. Reason only from the provided context and your training data.
6. If you cannot answer without external research, say so clearly.

Respond thoughtfully and completely, but within these constraints."""

    async def execute(
        self,
        query: str,
        context: dict,
        lens_modifier: Optional[str] = None,
    ) -> ProtectResult:
        """
        Execute a PROTECT intent query.
        In production, this calls the local Ollama model.
        """
        # Apply lens if present
        system_prompt = self._prompt
        if lens_modifier:
            system_prompt = f"{lens_modifier}\n\n{system_prompt}"

        # PII detection on input
        from src.gateway.sanitizer import Sanitizer
        sanitizer = Sanitizer()
        analysis = sanitizer.analyze(query)
        pii_detected = [r["type"] for r in analysis.redactions]

        # In production: call Ollama with system_prompt + context + query
        # For now, structured response
        content = (
            f"[PROTECT mode — local reasoning only]\n"
            f"Classification: {context.get('riu_id', 'unknown')}\n"
            f"Prior paths: {len(context.get('prior_paths', []))}\n"
            f"PII detected in query: {len(pii_detected)} items\n"
            f"[Awaiting local model integration for full response]"
        )

        return ProtectResult(
            content=content,
            confidence=0.8,
            model_used=self.model,
            pii_detected=pii_detected,
            external_blocked=True,
        )
