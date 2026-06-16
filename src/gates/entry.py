"""
Entry Gate — First Contact Sensitivity Detection

The FIRST thing that touches any query. Before classification, before
knowledge retrieval, before anything — the entry gate uses a local LLM
to detect PII, PHI, and sensitive information.

Why a local LLM instead of just regex:
  - An LLM understands context: "Dr. Smith's treatment" → PHI (medical context)
  - An LLM catches implicit PII: "the CEO's wife" → relationship identifier
  - An LLM understands domain: "the plaintiff in Doe v. Roe" → legal party
  - An LLM detects intent: "don't tell anyone" → sensitivity signal

The entry gate produces TWO outputs:
  1. SensitivityReport — what was found, tagged by type, severity scored
  2. Sanitized query — PII replaced with type placeholders ([PII_NAME], [PHI_DIAGNOSIS])

The sanitized query flows through classification and external research.
The original + sensitivity report stay local for reasoning.

One Ollama call does both:
  - Pre-classification (domain hint for the ontology)
  - Sensitivity detection (PII/PHI entities with types)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib import request, error


ENTRY_GATE_PROMPT = """You are a sensitivity detection system. Analyze the query below and return a JSON object with exactly these fields:

1. "domain_hint": The most likely domain — one of: "legal", "medical", "financial", "technical", "general"
2. "sensitivity": The sensitivity level — one of: "public", "internal", "confidential", "privileged"
3. "entities": A list of sensitive entities found. Each entity has:
   - "text": the exact text found
   - "type": one of PII_NAME, PII_EMAIL, PII_PHONE, PII_SSN, PII_ADDRESS, PII_DOB,
              PHI_DIAGNOSIS, PHI_TREATMENT, PHI_PROVIDER, PHI_RECORD,
              LEGAL_CASE_REF, LEGAL_MATTER, LEGAL_PARTY, LEGAL_STRATEGY,
              FINANCIAL_ACCOUNT, FINANCIAL_AMOUNT, FINANCIAL_MNPI,
              CREDENTIAL, API_KEY, SECRET
   - "severity": "high" (must redact), "medium" (should redact), "low" (flag but may keep)
4. "signals": List of sensitivity signal phrases detected (e.g., "don't share", "between us", "confidential")

If no sensitive entities found, return empty entities list. Always return valid JSON.

Query to analyze:
"""


@dataclass
class SensitiveEntity:
    """A detected sensitive entity in the query."""
    text: str
    type: str
    severity: str  # high, medium, low


@dataclass
class SensitivityReport:
    """Complete sensitivity analysis of a query."""
    original_query: str
    sanitized_query: str
    domain_hint: str = "general"
    sensitivity_level: str = "public"  # public, internal, confidential, privileged
    entities: list[SensitiveEntity] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    llm_used: bool = False  # True if Ollama was used, False if regex fallback
    blocked: bool = False    # True if sensitivity is too high for ANY processing

    @property
    def has_pii(self) -> bool:
        return any(e.type.startswith("PII_") for e in self.entities)

    @property
    def has_phi(self) -> bool:
        return any(e.type.startswith("PHI_") for e in self.entities)

    @property
    def has_legal_sensitive(self) -> bool:
        return any(e.type.startswith("LEGAL_") for e in self.entities)

    @property
    def high_severity_count(self) -> int:
        return sum(1 for e in self.entities if e.severity == "high")


class EntryGate:
    """
    First contact sensitivity detection using local LLM.

    Tries Ollama first. Falls back to regex patterns if Ollama unavailable.
    The gate NEVER sends data externally — all detection is local.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "qwen2.5:3b"):
        self._ollama_url = ollama_url
        self._model = model
        self._ollama_available = None  # Lazy check

    def scan(self, query: str) -> SensitivityReport:
        """
        Scan a query for sensitive information. This is the entry gate.

        Returns a SensitivityReport with:
        - sanitized_query: PII replaced with type placeholders
        - entities: list of detected sensitive entities
        - domain_hint: suggested domain for classification
        - sensitivity_level: overall sensitivity assessment
        """
        # Fast path: regex first (< 1ms)
        regex_report = self._scan_with_regex(query)

        # If regex found PII or blocked the query, return immediately — no LLM needed
        if regex_report.blocked or regex_report.entities:
            return regex_report

        # If regex found nothing and query is short/simple, skip LLM
        if len(query.split()) < 15:
            return regex_report

        # Ambiguous query: regex found nothing but it's long enough to contain
        # contextual PII that regex misses. Use LLM for deeper scan.
        if self._check_ollama():
            llm_report = self._scan_with_llm(query)
            if llm_report:
                return llm_report

        return regex_report

    def _check_ollama(self) -> bool:
        """Check if Ollama is available (cached after first check)."""
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            req = request.Request(f"{self._ollama_url}/api/tags", method="GET")
            with request.urlopen(req, timeout=2) as resp:
                self._ollama_available = resp.status == 200
        except Exception:
            self._ollama_available = False
        return self._ollama_available

    def _scan_with_llm(self, query: str) -> Optional[SensitivityReport]:
        """Use Ollama to detect sensitive information."""
        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": ENTRY_GATE_PROMPT},
                {"role": "user", "content": query},
            ],
            "temperature": 0.1,
            "max_tokens": 500,
            "format": "json",
        }).encode("utf-8")

        req = request.Request(
            f"{self._ollama_url}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
                content = body["choices"][0]["message"]["content"]
                return self._parse_llm_response(query, content)
        except Exception:
            return None

    def _parse_llm_response(self, query: str, response: str) -> Optional[SensitivityReport]:
        """Parse the LLM's JSON response into a SensitivityReport."""
        try:
            # Handle potential markdown wrapping
            clean = response.strip()
            if clean.startswith("```"):
                clean = re.sub(r'^```(?:json)?\s*', '', clean)
                clean = re.sub(r'\s*```$', '', clean)
            data = json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            return None

        entities = []
        for e in data.get("entities", []):
            entities.append(SensitiveEntity(
                text=e.get("text", ""),
                type=e.get("type", "UNKNOWN"),
                severity=e.get("severity", "medium"),
            ))

        # Build sanitized query — replace detected entities with placeholders
        sanitized = query
        for entity in sorted(entities, key=lambda e: len(e.text), reverse=True):
            if entity.text and entity.severity in ("high", "medium"):
                sanitized = sanitized.replace(entity.text, f"[{entity.type}]")

        sensitivity = data.get("sensitivity", "public")

        return SensitivityReport(
            original_query=query,
            sanitized_query=sanitized,
            domain_hint=data.get("domain_hint", "general"),
            sensitivity_level=sensitivity,
            entities=entities,
            signals=data.get("signals", []),
            llm_used=True,
            blocked=(sensitivity == "privileged"),
        )

    def _scan_with_regex(self, query: str) -> SensitivityReport:
        """
        Fallback regex-based detection when Ollama is unavailable.

        Less sophisticated but catches the obvious patterns.
        Combined with the pipeline's existing sanitizer for defense-in-depth.
        """
        from src.gateway.sanitizer import Sanitizer
        sanitizer = Sanitizer()
        analysis = sanitizer.analyze(query)

        entities = []
        for r in analysis.redactions:
            entities.append(SensitiveEntity(
                text=r.get("value", ""),
                type=f"PII_{r.get('type', 'UNKNOWN').upper()}",
                severity="high" if r.get("layer") == 1 else "medium",
            ))

        # Domain hint from keyword detection
        domain_hint = "general"
        q_lower = query.lower()
        if any(w in q_lower for w in ("attorney", "counsel", "privilege", "litigation", "fiduciary")):
            domain_hint = "legal"
        elif any(w in q_lower for w in ("patient", "diagnosis", "treatment", "hipaa", "clinical")):
            domain_hint = "medical"
        elif any(w in q_lower for w in ("portfolio", "investment", "securities", "mnpi", "trading")):
            domain_hint = "financial"

        # Sensitivity from block signals
        sensitivity = "public"
        if analysis.blocked:
            sensitivity = "privileged"
        elif entities:
            sensitivity = "confidential"

        sanitized = analysis.sanitized if not analysis.blocked else ""

        return SensitivityReport(
            original_query=query,
            sanitized_query=sanitized,
            domain_hint=domain_hint,
            sensitivity_level=sensitivity,
            entities=entities,
            signals=[analysis.block_reason] if analysis.block_reason else [],
            llm_used=False,
            blocked=analysis.blocked,
        )
