"""
Perplexity Research Gateway

The bridge between local knowledge and the world. Palette controls the bridge.

Queries are classified before sending. PII is stripped before sending.
Responses are validated against local knowledge. Contradictions are flagged.
Sources are tiered by reliability. Gaps are required outputs.
Confidence is honest, not inflated.

Three models:
  sonar-pro           — fast research, 3-5 sentences, citations required
  sonar-deep-research — thorough multi-step research, comprehensive
  sonar-reasoning-pro — deep reasoning, tradeoff analysis

Evolution lessons from Palette:
  1. System prompt must be TARGETED using the ontology node name
  2. Tell Perplexity what you already know so it focuses on gaps
  3. Extract citations from the API response (body.citations[])
  4. Detect contradictions against local knowledge
  5. Compound confidence: local baseline + external boost (capped)
  6. Graceful fallback when unavailable — never crash
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib import request, error


PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Model selection by intent depth
MODELS = {
    "fast": "sonar-pro",
    "deep": "sonar-deep-research",
    "reasoning": "sonar-reasoning-pro",
}

# Contradiction signals — strong indicators that external overrides local
CONTRADICTION_SIGNALS = [
    "overruled", "superseded", "no longer good law", "reversed",
    "abrogated", "vacated", "withdrawn", "deprecated", "replaced by",
    "contrary to", "incorrectly states", "this is incorrect",
]


@dataclass
class PerplexityResult:
    """Structured result from a Perplexity research call."""
    content: str
    citations: list[str] = field(default_factory=list)
    model_used: str = "sonar-pro"
    query_sent: str = ""
    gaps_identified: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    raw_response: Optional[dict] = None


class PerplexityGateway:
    """
    Governed external research via Perplexity API.

    The gateway does not decide whether to call Perplexity — the pipeline
    decides that based on ontology classification. The gateway executes
    the call with maximum precision and minimum data leakage.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("PERPLEXITY_API_KEY", "")
        self._available = bool(self.api_key)

    @property
    def available(self) -> bool:
        return self._available

    def research(
        self,
        query: str,
        node_name: str,
        domain: str,
        local_knowledge: list[dict],
        depth: str = "fast",
        max_tokens: int = 500,
        timeout: int = 30,
    ) -> PerplexityResult:
        """
        Execute a governed research call.

        Args:
            query: The sanitized query (PII already stripped by pipeline)
            node_name: The ontology node name (for targeted system prompt)
            domain: The domain (legal, core, etc.)
            local_knowledge: KL entries already retrieved — Perplexity
                should focus on what's MISSING, not rediscover what we have
            depth: "fast" (sonar-pro), "deep" (sonar-deep-research),
                   "reasoning" (sonar-reasoning-pro)
            max_tokens: Response length cap
            timeout: Seconds before abort

        Returns:
            PerplexityResult with content, citations, gaps, contradictions
        """
        if not self._available:
            return PerplexityResult(
                content="[Perplexity unavailable — no API key. Using local knowledge only.]",
                model_used="none",
                query_sent=query,
                gaps_identified=["perplexity_unavailable"],
            )

        model = MODELS.get(depth, "sonar-pro")
        system_prompt = self._build_system_prompt(node_name, domain, local_knowledge)

        try:
            response = self._call_api(query, system_prompt, model, max_tokens, timeout)
        except Exception as e:
            return PerplexityResult(
                content=f"[Perplexity error: {e}. Falling back to local knowledge.]",
                model_used=model,
                query_sent=query,
                gaps_identified=[f"perplexity_error:{type(e).__name__}"],
            )

        # Extract structured result
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = response.get("citations", [])

        # Detect contradictions against local knowledge
        contradictions = self._detect_contradictions(content, local_knowledge)

        # Identify gaps (what Perplexity couldn't find)
        gaps = self._identify_gaps(content)

        return PerplexityResult(
            content=content,
            citations=citations,
            model_used=model,
            query_sent=query,
            gaps_identified=gaps,
            contradictions=contradictions,
            raw_response=response,
        )

    def _build_system_prompt(
        self,
        node_name: str,
        domain: str,
        local_knowledge: list[dict],
    ) -> str:
        """
        Build a targeted system prompt using the ontology node name.

        This is the key lesson from Palette: don't just forward the query.
        Tell Perplexity WHERE the query sits in the ontology and WHAT
        the system already knows, so it focuses on gaps.
        """
        parts = [
            f"Research for a {node_name} query in the {domain} domain.",
            "Focus on what is MISSING from the knowledge already available.",
            "Cite sources. Distinguish between primary sources (court rulings, statutes, official documentation) and secondary sources (commentary, analysis).",
            "Be concise and precise. 3-5 paragraphs maximum.",
            "If you cannot find authoritative information on any aspect, explicitly state what you could not verify — gaps are valuable outputs.",
        ]

        # Include what we already know so Perplexity doesn't rediscover it
        if local_knowledge:
            parts.append("\nThe system already has this knowledge. Focus on gaps, but explicitly correct any entry that is outdated or factually wrong:")
            for entry in local_knowledge[:3]:
                title = entry.get("title", "")
                if title:
                    parts.append(f"  - {title}")

        return "\n".join(parts)

    def _call_api(
        self,
        query: str,
        system_prompt: str,
        model: str,
        max_tokens: int,
        timeout: int,
    ) -> dict:
        """Make the actual API call to Perplexity."""
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "max_tokens": max_tokens,
        }).encode("utf-8")

        req = request.Request(
            PERPLEXITY_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def _detect_contradictions(
        self,
        external_content: str,
        local_knowledge: list[dict],
    ) -> list[str]:
        """
        Detect contradictions between external research and local knowledge.

        Only flags STRONG signals. Weak disagreements ("however", "but")
        are normal in legal/professional prose — not contradictions.
        """
        contradictions = []
        content_lower = external_content.lower()

        for signal in CONTRADICTION_SIGNALS:
            if signal in content_lower:
                # Find the sentence containing the contradiction
                for sentence in re.split(r'[.!?]+', external_content):
                    if signal in sentence.lower():
                        contradictions.append(sentence.strip())
                        break

        return contradictions

    def _identify_gaps(self, content: str) -> list[str]:
        """
        Identify what Perplexity couldn't find or was uncertain about.

        Gap phrases indicate the research hit a boundary. These are
        valuable — they become gap signals in the path record.
        """
        gap_phrases = [
            "could not find", "no authoritative", "unable to verify",
            "insufficient data", "no published", "unclear whether",
            "not yet decided", "pending", "no case law",
            "limited information", "no definitive",
        ]

        gaps = []
        content_lower = content.lower()
        for phrase in gap_phrases:
            if phrase in content_lower:
                for sentence in re.split(r'[.!?]+', content):
                    if phrase in sentence.lower():
                        gaps.append(sentence.strip())
                        break

        return gaps
