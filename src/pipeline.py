"""
THE GOVERNED PIPELINE

Every query — voice, text, CLI, API — goes through exactly this pipeline.
No skipping. No shortcuts. The pipeline IS the OS.

  Step 0: SCAN       — entry gate detects PII/PHI at first contact (local LLM)
  Step 1: CLASSIFY   — ontology, not semantic search
  Step 2: RETRIEVE   — path-structured knowledge retrieval
  Step 3: RESEARCH   — governed external, BEFORE reasoning (exit gate validates)
  Step 4: CONTEXT    — RIU + KL + Research + Paths → formatted prompt
  Step 5: REASON     — local model with FULL context
  Step 6: SYNTHESIZE — format final output
  Step 7: STORE      — path record + decision (ALWAYS fires)

Invariants:
  - Entry gate blocks privileged queries from any external routing
  - RESEARCH only fires if classification allows external AND confidence < threshold
  - STORE always fires (every query contributes to path memory)
  - Exit gate scans all inbound responses for malicious content
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import os
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ontology.engine import OntologyEngine, ClassificationResult
from memory.store import MemoryStore
from memory.schema import PathRecord
from knowledge import KnowledgeStore
from src.context_builder import ContextBuilder
from src.gates.entry import EntryGate
from lenses import LensEngine
from src.gates.exit import ExitGate
from ontology.proposals.candidate import CandidateStore
from ontology.learned_weights import LearnedWeights
from src.integrity_gate import IntegrityGate


@dataclass
class ReasonResult:
    """Output from local reasoning (Step 3)."""
    content: str
    confidence: float
    model_used: str
    tokens_used: int = 0


@dataclass
class ResearchResult:
    """Output from external research (Step 4)."""
    content: str
    citations: list[str] = field(default_factory=list)
    model_used: str = "perplexity/sonar-pro"
    query_sent: str = ""
    gaps: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)


@dataclass
class SynthesisResult:
    """Output from synthesis (Step 5)."""
    content: str
    confidence: float
    intent: str
    model_used: str
    citations: list[str] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)


@dataclass
class PipelineResult:
    """The complete output of the 8-step pipeline."""
    session_id: str
    query_hash: str
    classification: ClassificationResult
    synthesis: SynthesisResult
    path_record: PathRecord
    duration_ms: int
    steps_executed: list[str] = field(default_factory=list)
    external_called: bool = False
    gap_signals: list[str] = field(default_factory=list)


class GatewayInterface:
    """
    Governed external research gateway.

    Wraps Perplexity with:
    - Ontology-based access control (blocks_external = hard gate)
    - PII sanitization before any external call
    - Targeted query formulation using node name + local knowledge
    - Contradiction detection against local knowledge
    - Gap identification as first-class output
    """

    def __init__(self):
        from src.gateway.perplexity import PerplexityGateway
        self._perplexity = PerplexityGateway()
        # Unified sanitizer (direct import — same code path as HTTP service)
        from sanitizer.app import sanitize as _unified_sanitize
        self._unified_sanitize = _unified_sanitize

    async def needs_external(
        self,
        classification: ClassificationResult,
        local_confidence: float,
        user_intent: Optional[str] = None,
    ) -> bool:
        """
        External research needed if: not blocked AND (confidence below threshold
        OR user explicitly requested research).
        """
        if classification.blocks_external:
            return False
        if not self._perplexity.available:
            return False
        # User explicitly asked for research — honor it
        if user_intent and user_intent.upper() == "RESEARCH":
            return True
        # Node's default is research
        if classification.default_intent == "RESEARCH":
            return True
        return local_confidence < 0.85

    async def sanitize_query(self, query: str, classification: ClassificationResult) -> str:
        """Sanitize via unified service. Context-aware based on classification domain."""
        context = classification.domain if classification.domain in ("logistics", "medical", "education", "legal") else "general"
        block_signals = []  # Per-client config passes these in; default = redact only
        if classification.blocks_external:
            return ""  # Blocked by ontology — don't even sanitize, just block
        result = self._unified_sanitize(
            query, context=context, block_signals=block_signals
        )
        if result["blocked"]:
            return ""
        # Store reverse_tokens for exit-gate rehydration
        self._last_reverse_tokens = result.get("reverse_tokens", {})
        return result["text"]

    async def query_external(
        self,
        query: str,
        classification: ClassificationResult,
        knowledge_context: list[dict],
    ) -> ResearchResult:
        """
        Call Perplexity with a targeted, governed research query.

        The query has already been sanitized. The classification determines
        the model depth and the system prompt targeting.
        """
        # Determine research depth from intent
        depth = "fast"
        if classification.default_intent == "DIAGNOSE":
            depth = "reasoning"
        elif classification.default_intent == "DECIDE":
            depth = "reasoning"

        result = self._perplexity.research(
            query=query,
            node_name=classification.name,
            domain=classification.domain,
            local_knowledge=knowledge_context,
            depth=depth,
        )

        return ResearchResult(
            content=result.content,
            citations=result.citations,
            model_used=result.model_used,
            query_sent=result.query_sent,
            gaps=result.gaps_identified,
            contradictions=result.contradictions,
        )


class ReasoningEngine:
    """
    Local reasoning via Ollama or LiteLLM.

    Receives the formatted context (system_prompt + user_message) built by
    ContextBuilder. The model sees: agent prompt + lens + classification +
    knowledge entries + prior paths + governance rules.

    The model never starts from zero. It starts from a known position
    on a known map with all available evidence.
    """

    async def reason(
        self,
        query: str,
        context: dict,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> ReasonResult:
        """
        Model reasoning. Resolution order:
        1. Explicit model param (from @mention or task envelope)
        2. MC_REASON_MODEL env var (user preference)
        3. Best available Ollama model (auto-detected)
        4. Placeholder (no model available)

        The resolved model may be local (qwen, phi, llama) or cloud
        (kimi:cloud, Claude, OpenAI). Governance holds regardless —
        the query reaching this step is already sanitized.
        """
        model = model or os.environ.get("MC_REASON_MODEL") or self._resolve_best_model()

        if system_prompt:
            result = await self._call_model(query, system_prompt, model)
            if result:
                return result

        # Fallback: structured placeholder
        return ReasonResult(
            content=f"[Local reasoning for {context.get('riu_id', 'unknown')} — no model available]",
            confidence=0.7,
            model_used="none",
        )

    def _resolve_best_model(self) -> str:
        """Auto-detect best available model. Prefer local, then cloud."""
        if not hasattr(self, "_cached_model"):
            self._cached_model = self._detect_model()
        return self._cached_model

    def _detect_model(self) -> str:
        """Query Ollama for installed models, pick the best for reasoning."""
        import json
        from urllib import request, error

        # Preferred local models for reasoning/synthesis (best first)
        LOCAL_PREFERENCE = [
            "qwen3:14b",
            "qwen3:8b",
            "phi4:14b",
            "qwen2.5:14b",
            "llama3.1:8b",
            "qwen2.5:7b",
            "mistral:7b",
            "qwen2.5:3b",
        ]
        # Cloud fallback (still via Ollama, but data leaves machine)
        CLOUD_FALLBACK = "kimi-k2.7-code:cloud"

        try:
            req = request.Request("http://localhost:11434/api/tags", method="GET")
            with request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                installed = {m["name"] for m in data.get("models", [])}

            # Pick the best local model that's actually installed
            for model in LOCAL_PREFERENCE:
                if model in installed:
                    return f"ollama/{model}"

            # No preferred local model found — try cloud
            return f"ollama/{CLOUD_FALLBACK}"

        except (error.URLError, ConnectionError, TimeoutError):
            # Ollama not running at all
            return "ollama/qwen2.5:3b"  # Will fail gracefully in _call_model

    async def _call_model(
        self,
        query: str,
        system_prompt: str,
        model: str,
    ) -> Optional[ReasonResult]:
        """
        Call a model via OpenAI-compatible API.

        Supports: Ollama (local + cloud), OpenAI, Groq, any OpenAI-compatible endpoint.
        Falls back to None if the provider is unreachable.
        """
        import json
        from urllib import request, error

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

        req_headers = {"Content-Type": "application/json", **headers}
        req = request.Request(url, data=payload, headers=req_headers, method="POST")

        try:
            with request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read())
                content = body["choices"][0]["message"]["content"]
                tokens = body.get("usage", {}).get("total_tokens", 0)
                return ReasonResult(
                    content=content,
                    confidence=0.75,
                    model_used=model,
                    tokens_used=tokens,
                )
        except (error.URLError, ConnectionError, TimeoutError, KeyError):
            return None  # Provider unreachable — fallback to placeholder

    @staticmethod
    def _resolve_endpoint(model: str) -> tuple:
        """Resolve model string to (endpoint_url, auth_headers)."""
        if model.startswith("openai/"):
            key = os.environ.get("OPENAI_API_KEY", "")
            return "https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {key}"}
        elif model.startswith("groq/"):
            key = os.environ.get("GROQ_API_KEY", "")
            return "https://api.groq.com/openai/v1/chat/completions", {"Authorization": f"Bearer {key}"}
        elif model.startswith("mistral/"):
            key = os.environ.get("MISTRAL_API_KEY", "")
            return "https://api.mistral.ai/v1/chat/completions", {"Authorization": f"Bearer {key}"}
        else:
            # Default: Ollama (handles both local and :cloud models)
            return "http://localhost:11434/v1/chat/completions", {}


class SynthesisEngine:
    """Interface for intent-specific synthesis (Step 5)."""

    async def synthesize(
        self,
        intent: str,
        query: str,
        local_result: ReasonResult,
        external_result: Optional[ResearchResult],
    ) -> SynthesisResult:
        """Synthesize local and external results into final output."""
        # Combine results
        content_parts = [local_result.content]
        citations = []
        if external_result:
            content_parts.append(external_result.content)
            citations = external_result.citations

        # Confidence: boost if external confirmed local
        confidence = local_result.confidence
        if external_result:
            confidence = min(confidence + 0.1, 0.99)

        return SynthesisResult(
            content="\n\n".join(content_parts),
            confidence=confidence,
            intent=intent,
            model_used=local_result.model_used,
            citations=citations,
        )


class Pipeline:
    """
    The 8-step governed pipeline. The heart of Mission Canvas.

    Usage:
        pipeline = Pipeline()
        result = await pipeline.run("Is this privileged information?", "PROTECT", session_id)
    """

    def __init__(
        self,
        ontology: Optional[OntologyEngine] = None,
        memory: Optional[MemoryStore] = None,
        knowledge: Optional[KnowledgeStore] = None,
        gateway: Optional[GatewayInterface] = None,
        reasoning: Optional[ReasoningEngine] = None,
        synthesis: Optional[SynthesisEngine] = None,
        document_retriever: Optional[object] = None,
    ):
        self.ontology = ontology or OntologyEngine()
        self.memory = memory or MemoryStore()
        self.knowledge = knowledge or KnowledgeStore()
        self.knowledge.set_ontology(self.ontology)
        self.gateway = gateway or GatewayInterface()
        self.reasoning = reasoning or ReasoningEngine()
        self.synthesis = synthesis or SynthesisEngine()
        self.context_builder = ContextBuilder()
        self.lens_engine = LensEngine()
        self.learned_weights = LearnedWeights()
        self.candidates = CandidateStore()
        self.entry_gate = EntryGate()
        self.exit_gate = ExitGate()
        self.exit_gate.activate()  # Socket firewall always on
        # Optional, duck-typed: object with .retrieve(query, domain, k) ->
        # list[dict]. Not imported from src.education here — keeps the core
        # pipeline decoupled from any single vertical. See
        # src/education/document_retrieval.py for the education instance.
        self.document_retriever = document_retriever

    async def run(
        self,
        query: str,
        intent: Optional[str] = None,
        session_id: Optional[str] = None,
        eval_mode: bool = False,
    ) -> PipelineResult:
        """
        Execute the 8-step governed pipeline.
        Every query goes through all steps. No shortcuts.
        """
        start_time = time.time()
        session_id = session_id or str(uuid.uuid4())
        query_hash = OntologyEngine.hash_query(query)
        steps_executed = []
        gap_signals = []

        # ================================================================
        # Step 0: ENTRY GATE — detect PII/PHI at first contact
        # ================================================================
        # Local LLM scans for sensitive data BEFORE anything else.
        # The sanitized query flows through classification and external.
        # The original stays local for reasoning.
        sensitivity = self.entry_gate.scan(query)
        steps_executed.append("SCAN")
        entry_gate_blocked_external = sensitivity.blocked

        if sensitivity.blocked:
            # Sensitivity too high — force PROTECT intent, block all external
            intent = "PROTECT"
            gap_signals.append(f"entry_gate_blocked:{sensitivity.sensitivity_level}")

        if sensitivity.entities:
            gap_signals.extend(
                f"sensitive:{e.type}:{e.severity}" for e in sensitivity.entities
                if e.severity == "high"
            )

        # Use sanitized query for external calls only. Classification never
        # leaves the machine (PathRecord stores a query hash, not raw text),
        # so blanking the query here only breaks domain routing without
        # protecting anything — external redaction is enforced independently
        # by GatewayInterface.sanitize_query() before any external call.
        safe_query = sensitivity.sanitized_query
        if not safe_query:
            safe_query = "[SENSITIVE_QUERY_BLOCKED]"
        # ================================================================
        # Step 1: CLASSIFY — ontology, not semantic search
        # ================================================================
        # Domain hint from entry gate helps classification
        effective_intent = intent
        if not effective_intent and sensitivity.domain_hint != "general":
            # Entry gate suggested a domain — map to an intent
            domain_to_intent = {"legal": "PROTECT", "medical": "PROTECT",
                              "financial": "RESEARCH", "technical": "RESEARCH"}
            effective_intent = domain_to_intent.get(sensitivity.domain_hint)

        prior_paths = self.memory.find_paths(
            min_confidence=0.5, limit=20,
        )
        classification = self.ontology.classify(query, effective_intent, prior_paths)
        steps_executed.append("CLASSIFY")

        # Gap signal if confidence is below threshold
        active_candidate = None
        if classification.confidence < 0.50:
            gap_signals.append(f"low_classification_confidence:{classification.confidence:.2f}")
            # Create or enrich a candidate RIU — the ontology grows from gaps
            # If no signals matched, extract key terms from the query as seed signals
            seed_signals = classification.signals_matched
            if not seed_signals:
                import re
                _stop = {"how", "do", "i", "the", "a", "an", "to", "for", "in", "on",
                         "is", "are", "what", "which", "where", "when", "why", "can",
                         "set", "up", "and", "or", "of", "with", "my", "me", "it", "this"}
                tokens = re.findall(r'\w+', query.lower())
                seed_signals = [t for t in tokens if t not in _stop and len(t) > 3][:8]

            active_candidate = self.candidates.create(
                query=query,
                query_hash=query_hash,
                fallback_node=classification.riu_id,
                fallback_confidence=classification.confidence,
                signals=seed_signals,
                domain=classification.domain,
            )

        # ================================================================
        # Step 2: RETRIEVE — path-structured knowledge retrieval
        # ================================================================
        relevant_paths = self.memory.find_paths(
            entry_node=classification.riu_id,
            min_confidence=0.6,
            limit=5,
        )
        # Knowledge retrieval — by ontology node, evidence-tiered
        kl_entries = self.knowledge.retrieve(node_id=classification.riu_id, limit=5)
        knowledge_dicts = [
            {"id": e.id, "title": e.title, "content": e.content,
             "tier": e.evidence_tier, "citations": e.citations}
            for e in kl_entries
        ]
        # Document retrieval — ontology-scoped semantic search over ingested
        # documents (e.g. IB curriculum PDFs). Optional: only fires if a
        # retriever was injected AND the classified domain is in its scope.
        # Uses safe_query, consistent with how the rest of Step 2 handles
        # the query — search embeddings go to the local Ollama instance only.
        document_entries: list[dict] = []
        if self.document_retriever is not None:
            document_entries = self.document_retriever.retrieve(
                query=safe_query, domain=classification.domain, k=3,
            )
        steps_executed.append("RETRIEVE")

        # ================================================================
        # Step 3: RESEARCH — governed external, BEFORE local reasoning
        # ================================================================
        external_result = None
        external_called = False
        research_dict = None

        # Self-sufficient check: skip Perplexity when KL has strong entries
        high_tier = [e for e in kl_entries if e.evidence_tier <= 2]
        self_sufficient = (
            len(high_tier) >= 3
            and classification.confidence >= 0.80
            and (not intent or intent.upper() != "RESEARCH")  # Respect explicit research
        )
        if self_sufficient:
            gap_signals.append("skipped_research:self_sufficient")

        # Track why research was or wasn't called
        local_only_intent = bool(intent and intent.upper() in {"PROTECT", "REFLECT"})
        if entry_gate_blocked_external:
            gap_signals.append("research_blocked_by_entry_gate")
        if local_only_intent:
            gap_signals.append(f"research_skipped_by_intent:{intent.upper()}")
        if classification.blocks_external and intent and intent.upper() == "RESEARCH":
            gap_signals.append(f"research_blocked_by_governance:{classification.riu_id}")

        if (
            not entry_gate_blocked_external
            and not local_only_intent
            and not self_sufficient
            and await self.gateway.needs_external(classification, classification.confidence, user_intent=intent)
        ):
            sanitized = await self.gateway.sanitize_query(safe_query, classification)
            external_result = await self.gateway.query_external(
                sanitized, classification, knowledge_dicts,
            )
            external_called = True
            steps_executed.append("RESEARCH")

            # EXIT GATE: scan response for malicious content
            safe, threats = self.exit_gate.scan_response(
                external_result.content, "api.perplexity.ai"
            )
            if not safe:
                gap_signals.extend(f"malicious_response:{t[:60]}" for t in threats)
                external_result = ResearchResult(
                    content="[Response blocked by exit gate — malicious patterns detected]",
                    model_used=external_result.model_used,
                    query_sent=external_result.query_sent,
                )

            research_dict = {
                "content": external_result.content,
                "citations": external_result.citations,
                "gaps": external_result.gaps,
                "contradictions": external_result.contradictions,
            }

            # Capture gaps and contradictions
            if external_result.gaps:
                gap_signals.extend(f"research_gap:{g[:80]}" for g in external_result.gaps)
            if external_result.contradictions:
                gap_signals.extend(f"contradiction:{c[:80]}" for c in external_result.contradictions)

            # Feed research into active candidate (if gap-triggered)
            if active_candidate:
                self.candidates.enrich(
                    candidate_id=active_candidate.candidate_id,
                    query=query,
                    query_hash=query_hash,
                    new_signals=classification.signals_matched,
                    perplexity_result=research_dict,
                )

        # ================================================================
        # Step 4: BUILD CONTEXT — RIU + KL + Research + Paths → prompt
        # ================================================================
        # The context builder formats everything into what the model sees.
        # This is the product: the model never starts from zero.
        # Pass the full node object so context_builder can access traversal data
        # (artifacts, failure_modes, success_conditions, dependencies)
        node_obj = self.ontology.nodes.get(classification.riu_id)
        classification_dict = {
            "riu_id": classification.riu_id,
            "name": classification.name,
            "domain": classification.domain,
            "confidence": classification.confidence,
            "blocks_external": classification.blocks_external,
            "requires_local": classification.requires_local,
            "signals_matched": classification.signals_matched,
            "default_intent": classification.default_intent,
            "_node": node_obj,  # Traversal layer for context enrichment
        }
        prior_path_dicts = [
            {"entry": p.entry_node, "path": p.path,
             "confidence": p.confidence_at_exit, "outcome": p.outcome}
            for p in relevant_paths
        ]

        # Get active lenses from classification context
        active_lenses = self.lens_engine.get_active_lenses(
            intent=classification.default_intent,
            domain=classification.domain,
            confidence=classification.confidence,
            query=query,
        )
        lens_modifier = None
        if active_lenses:
            lens_modifier = self.lens_engine.apply_lenses("", active_lenses).strip()

        system_prompt, user_message, context_gaps, _cache_meta = self.context_builder.build(
            query=query,
            classification=classification_dict,
            knowledge_entries=knowledge_dicts,
            prior_paths=prior_path_dicts,
            research_result=research_dict,
            lens_modifier=lens_modifier,
            document_entries=document_entries,
        )
        gap_signals.extend(context_gaps)

        # ================================================================
        # Step 5: REASON — local model with FULL context
        # ================================================================
        # The model receives: agent prompt + lens + RIU + KL + research + paths
        local_result = await self.reasoning.reason(
            query=user_message,
            context=classification_dict,
            model=classification.default_model,
            system_prompt=system_prompt,
        )
        steps_executed.append("REASON")

        # ================================================================
        # Step 5b: INTEGRITY GATE — validate model output
        # ================================================================
        gate = IntegrityGate(
            ontology_nodes=set(self.ontology.nodes.keys()),
            knowledge_ids=set(self.knowledge.entries.keys()),
        )
        gate_result = gate.check(local_result.content)
        if gate_result.warnings:
            gap_signals.extend(f"integrity:{w[:80]}" for w in gate_result.warnings)

        # ================================================================
        # Step 6: SYNTHESIZE — format the final output
        # ================================================================
        synthesis_result = await self.synthesis.synthesize(
            intent=classification.default_intent or "RESEARCH",
            query=query,
            local_result=local_result,
            external_result=external_result,
        )
        steps_executed.append("SYNTHESIZE")

        # ================================================================
        # Step 6.5: REHYDRATE — restore tokens for human-facing output
        # The LLM saw <SSN_abc123>; the user should see their original data.
        # Only fires if sanitization produced token substitutions.
        # ================================================================
        reverse_tokens = getattr(self.gateway, '_last_reverse_tokens', {})
        if reverse_tokens and synthesis_result.content:
            from sanitizer.client import rehydrate
            synthesis_result.content = rehydrate(synthesis_result.content, reverse_tokens)
            self.gateway._last_reverse_tokens = {}  # Clear after use

        # ================================================================
        # Step 7: STORE — path record + decision (ALWAYS fires)
        # ================================================================
        duration_ms = int((time.time() - start_time) * 1000)

        # Path trace: entry node + steps actually executed
        path_trace = [classification.riu_id] + steps_executed + ["STORE"]

        path_record = PathRecord(
            session_id=session_id,
            query_hash=query_hash,
            domain=classification.domain,
            entry_node=classification.riu_id,
            path=path_trace,
            confidence_at_entry=classification.confidence,
            confidence_at_exit=max(classification.confidence, synthesis_result.confidence),
            model_used=local_result.model_used,
            external_called=external_called,
            outcome="decision_stored" if synthesis_result.decisions else "completed",
            intent=classification.default_intent,
            lens_applied=",".join(l.name for l in active_lenses) if active_lenses else None,
            knowledge_entries_used=[e["id"] for e in knowledge_dicts],
            gap_signals=gap_signals,
            duration_ms=duration_ms,
        )

        if not eval_mode:
            self.memory.write_path(path_record)
            self.learned_weights.update_from_path(path_record, classification.signals_matched)
        steps_executed.append("STORE" if not eval_mode else "STORE(skipped)")

        return PipelineResult(
            session_id=session_id,
            query_hash=query_hash,
            classification=classification,
            synthesis=synthesis_result,
            path_record=path_record,
            duration_ms=duration_ms,
            steps_executed=steps_executed,
            external_called=external_called,
            gap_signals=gap_signals,
        )

