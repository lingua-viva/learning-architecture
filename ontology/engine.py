"""
Mission Canvas Ontology Engine

The external symbolic verifier that escapes the No-Escape Theorem
(arxiv 2603.27116). Every query finds its coordinates on this map
before any model reasons about it.

Key operations:
  classify(query, intent) → ClassificationResult
  traverse(from_node, direction) → [Node]
  get_node(node_id) → Node
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from memory.schema.path import PathRecord


@dataclass
class OntologyNode:
    """A position on the map. Classification + traversal layers."""
    # ── Classification Layer (always loaded, used by classify()) ──
    id: str
    name: str
    description: str
    domain: str
    parent: Optional[str] = None
    signals: list[str] = field(default_factory=list)
    blocks_external: bool = False
    requires_local: bool = False
    escalates_to: list[str] = field(default_factory=list)
    resolves_to: list[str] = field(default_factory=list)
    contradicts: list[str] = field(default_factory=list)
    co_occurs_with: list[str] = field(default_factory=list)
    evidence_tier: int = 3
    path_weight: float = 1.0
    default_intent: Optional[str] = None
    default_model: Optional[str] = None
    default_lens: Optional[str] = None
    # ── Traversal Layer (rich, used by CONTEXT/REASON) ──
    artifacts: list[str] = field(default_factory=list)
    failure_modes: dict = field(default_factory=dict)
    success_conditions: dict = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    # ── Composability Layer (recursive pipeline support) ──
    produces: list[str] = field(default_factory=list)     # Artifacts this node creates
    requires: list[str] = field(default_factory=list)     # Artifacts needed before execution
    suggests_next: list[str] = field(default_factory=list) # Nodes that typically follow
    coordinates: dict = field(default_factory=dict)
    reversibility: str = "two_way"
    journey_stage: str = "foundation"
    agent_types: list[str] = field(default_factory=list)
    workstream: str = ""


@dataclass
class ClassificationResult:
    """The output of classifying a query against the ontology."""
    riu_id: str
    name: str
    domain: str
    confidence: float
    signals_matched: list[str]
    blocks_external: bool
    requires_local: bool
    default_intent: Optional[str]
    default_model: Optional[str]
    default_lens: Optional[str]
    escalation_targets: list[str]
    resolution_targets: list[str]
    co_occurring: list[str] = field(default_factory=list)


# Pre-compiled tokenizer for signal matching
_TOKENIZE = re.compile(r'\w+')


class OntologyEngine:
    """
    The map. Loads domain YAML files, builds the graph, classifies queries.

    The engine does not reason. It classifies. The model receives the
    classification and knows where it is before it starts thinking.
    """

    def __init__(self, domains_dir: Optional[Path] = None):
        self.nodes: dict[str, OntologyNode] = {}
        self.domains: dict[str, list[str]] = {}
        self._children: dict[str, list[str]] = {}  # parent_id -> [child_ids]
        self._signal_index: dict[str, list[tuple[str, str]]] = {}  # token -> [(node_id, signal)]
        self._schema: dict = {}

        if domains_dir is None:
            domains_dir = Path(__file__).parent / "domains"

        self._load_schema()
        # Load core ontology first (MC-native), then legacy domains, then customer extensions
        core_dir = Path(__file__).parent / "core"
        if core_dir.exists():
            self._load_domains(core_dir)
        self._load_domains(domains_dir)
        # Load customer extensions if present
        customers_dir = Path(__file__).parent / "customers"
        if customers_dir.exists():
            self._load_domains(customers_dir)
        self._build_indices()

    def _load_schema(self) -> None:
        schema_path = Path(__file__).parent / "schema.yaml"
        if schema_path.exists():
            with open(schema_path) as f:
                self._schema = yaml.safe_load(f) or {}

    def _load_domains(self, domains_dir: Path) -> None:
        if not domains_dir.exists():
            return
        for yaml_file in sorted(domains_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if not data or "nodes" not in data:
                continue
            domain_name = data.get("domain", yaml_file.stem)
            self.domains[domain_name] = []
            for node_data in data["nodes"]:
                node = OntologyNode(**{
                    k: v for k, v in node_data.items()
                    if k in OntologyNode.__dataclass_fields__
                })
                self.nodes[node.id] = node
                self.domains[domain_name].append(node.id)

    def _build_indices(self) -> None:
        """Build lookup indices after loading. O(1) children and signal lookups."""
        # Children index
        for node_id, node in self.nodes.items():
            if node.parent:
                self._children.setdefault(node.parent, []).append(node_id)

        # Signal token index: for each token in each signal, map to (node_id, full_signal)
        for node_id, node in self.nodes.items():
            for signal in node.signals:
                tokens = set(_TOKENIZE.findall(signal.lower()))
                for token in tokens:
                    self._signal_index.setdefault(token, []).append((node_id, signal))

            # Auto-index the node's name as an implicit signal.
            # Users type "convergence brief" when they mean RIU-001 — the name IS the signal.
            # Skip CORE- nodes (their names are generic intents, not domain concepts).
            if not node_id.startswith("CORE-"):
                name_signal = f"_name:{node.name.lower()}"
                name_tokens = set(_TOKENIZE.findall(node.name.lower()))
                # Only index name tokens that are meaningful (>2 chars, not stopwords)
                stopwords = {"a", "an", "the", "and", "or", "of", "for", "in", "on", "to", "is", "how", "do", "i", "my", "with"}
                meaningful = name_tokens - stopwords
                for token in meaningful:
                    if len(token) > 2:
                        self._signal_index.setdefault(token, []).append((node_id, name_signal))

                # Layer 2: Auto-index node description tokens.
                # Descriptions contain domain vocabulary that users naturally use.
                if node.description:
                    desc_signal = f"_desc:{node.name.lower()}"
                    desc_tokens = set(_TOKENIZE.findall(node.description.lower()))
                    desc_meaningful = desc_tokens - stopwords
                    for token in desc_meaningful:
                        if len(token) > 3:  # Stricter for descriptions (more noise)
                            self._signal_index.setdefault(token, []).append((node_id, desc_signal))

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def domain_count(self) -> int:
        return len(self.domains)

    def classify(
        self,
        query: str,
        intent: Optional[str] = None,
        prior_paths: Optional[list[PathRecord]] = None,
    ) -> ClassificationResult:
        """
        Classify a query against the ontology.

        Signal matching uses word-boundary tokenization, not substring matching.
        "client" matches "client" but not "client-server". Multi-word signals
        like "trade secret" require all tokens present.

        This is BM25-style: zero forgetting, zero false recall.
        """
        query_tokens = set(_TOKENIZE.findall(query.lower()))
        if not query_tokens:
            return self._fallback(intent)

        # Score each node by signal match quality
        # Partial matching: a signal fires if >50% of its tokens appear in query.
        # Single-word signals require exact match. Multi-word get partial credit.
        node_matches: dict[str, list[str]] = {}  # node_id -> matched signals
        seen: set[tuple[str, str]] = set()
        for token in query_tokens:
            for node_id, signal in self._signal_index.get(token, []):
                key = (node_id, signal)
                if key in seen:
                    continue
                seen.add(key)
                signal_tokens = set(_TOKENIZE.findall(signal.lower()))
                overlap = len(signal_tokens & query_tokens)
                # 1 word: exact match. 2-3 words: all required. 4+: >50% required.
                # Name-derived signals (_name:) use looser threshold: min 2 tokens.
                # Description-derived signals (_desc:) require 3+ matching tokens (high noise).
                n = len(signal_tokens)
                if signal.startswith("_name:"):
                    threshold = min(2, n)  # Name signals: 2 matching tokens is enough
                elif signal.startswith("_desc:"):
                    threshold = min(3, n)  # Description signals: need 3+ matches (strict)
                else:
                    threshold = n if n <= 3 else max(1, n // 2 + 1)
                if overlap >= threshold:
                    node_matches.setdefault(node_id, [])
                    if signal not in node_matches[node_id]:
                        node_matches[node_id].append(signal)

        if not node_matches:
            return self._fallback(intent)

        # Rank nodes
        scored: list[tuple[str, float, list[str]]] = []
        for node_id, matched in node_matches.items():
            node = self.nodes[node_id]
            score = self._rank_score(node, matched, intent, prior_paths)
            scored.append((node_id, score, matched))

        scored.sort(key=lambda x: x[1], reverse=True)

        # ── Two-pass classification ──
        # Pass 1: Intent (what do you want to do?) — INTENT-* and CORE-* nodes
        # Pass 2: Domain (what is this about?) — everything else
        # Intent and domain are separate axes, never competing.

        intent_nodes = [(nid, s, m) for nid, s, m in scored
                        if nid.startswith("INTENT-") or nid.startswith("CORE-")]
        domain_nodes = [(nid, s, m) for nid, s, m in scored
                        if not nid.startswith("INTENT-") and not nid.startswith("CORE-")]

        # Resolve intent: explicit > signal-matched > node default > RESEARCH
        if intent:
            resolved_intent = intent.upper()
        elif intent_nodes:
            intent_id = intent_nodes[0][0]
            resolved_intent = intent_id.replace("INTENT-", "").replace("CORE-", "")
        else:
            resolved_intent = None  # Will use domain node's default_intent

        # Resolve domain: prefer domain-specific nodes over intent nodes
        if domain_nodes:
            best_id, _, best_matched = domain_nodes[0]
        elif intent_nodes:
            # Only intents matched — use as domain (backwards compat)
            best_id, _, best_matched = intent_nodes[0]
        else:
            best_id, _, best_matched = scored[0]
        best_node = self.nodes[best_id]

        # Final intent: explicit > signal-resolved > node default > RESEARCH
        final_intent = resolved_intent or best_node.default_intent or "RESEARCH"

        # Confidence is computed separately from ranking
        confidence = self._compute_confidence(best_matched, best_node, prior_paths)

        # Co-occurring: other high-scoring domain nodes
        co_occurring = [
            nid for nid, s, _ in domain_nodes[1:4]
            if domain_nodes and s > domain_nodes[0][1] * 0.7
        ]

        return ClassificationResult(
            riu_id=best_id,
            name=best_node.name,
            domain=best_node.domain,
            confidence=confidence,
            signals_matched=best_matched,
            blocks_external=best_node.blocks_external,
            requires_local=best_node.requires_local,
            default_intent=final_intent,
            default_model=best_node.default_model,
            default_lens=best_node.default_lens,
            escalation_targets=best_node.escalates_to,
            resolution_targets=best_node.resolves_to,
            co_occurring=co_occurring,
        )

    def _rank_score(
        self,
        node: OntologyNode,
        matched: list[str],
        intent: Optional[str],
        prior_paths: Optional[list[PathRecord]],
    ) -> float:
        """Score for ranking which node wins. Separate from confidence."""
        # Signal coverage: what fraction of this node's signals fired
        coverage = len(matched) / max(len(node.signals), 1)

        # Absolute match count matters too (a node with 5/15 matches > 1/3 matches)
        volume = min(len(matched) * 0.1, 0.5)

        # Intent alignment
        intent_boost = 0.15 if (
            intent and node.default_intent
            and intent.upper() == node.default_intent.upper()
        ) else 0.0

        # Specificity: deeper nodes are more specific
        depth = 0.0
        if node.parent:
            depth = 0.1
            parent = self.nodes.get(node.parent)
            if parent and parent.parent:
                depth = 0.15

        return coverage + volume + intent_boost + depth

    def _compute_confidence(
        self,
        matched_signals: list[str],
        node: OntologyNode,
        prior_paths: Optional[list[PathRecord]],
    ) -> float:
        """
        Empirical confidence. Not self-reported.

        base (0.5) + signal boost (up to 0.3) + path history boost (up to 0.4)
        Capped at 0.99 — epistemic humility.
        """
        scoring = self._schema.get("confidence_model", {}).get("scoring", {})
        base = scoring.get("base_confidence", 0.5)
        signal_per = scoring.get("signal_match_boost", 0.1)
        path_per = scoring.get("path_boost", 0.05)
        cap = scoring.get("max_confidence", 0.99)

        signal_boost = min(len(matched_signals) * signal_per, 0.3)

        path_boost = 0.0
        if prior_paths:
            n = sum(1 for p in prior_paths if p.entry_node == node.id)
            path_boost = min(n * path_per, 0.4)

        return min(base + signal_boost + path_boost, cap)

    def _fallback(self, intent: Optional[str]) -> ClassificationResult:
        """No signals matched. Return low-confidence fallback."""
        node_id = self._intent_to_core_node(intent)
        node = self.nodes.get(node_id)
        if node:
            return ClassificationResult(
                riu_id=node_id, name=node.name, domain=node.domain,
                confidence=0.3, signals_matched=[],
                blocks_external=node.blocks_external,
                requires_local=node.requires_local,
                default_intent=node.default_intent,
                default_model=node.default_model,
                default_lens=node.default_lens,
                escalation_targets=node.escalates_to,
                resolution_targets=node.resolves_to,
            )
        return ClassificationResult(
            riu_id="CORE-RESEARCH", name="Research", domain="core",
            confidence=0.2, signals_matched=[],
            blocks_external=False, requires_local=False,
            default_intent="RESEARCH", default_model=None, default_lens=None,
            escalation_targets=[], resolution_targets=[],
        )

    def _intent_to_core_node(self, intent: Optional[str]) -> str:
        if intent:
            return f"CORE-{intent.upper()}"
        return "CORE-RESEARCH"

    def traverse(self, from_node: str, direction: str = "children") -> list[OntologyNode]:
        """Traverse the graph from a node. O(1) for children via index."""
        node = self.nodes.get(from_node)
        if not node:
            return []

        if direction == "children":
            return [self.nodes[cid] for cid in self._children.get(from_node, [])
                    if cid in self.nodes]
        elif direction == "parents":
            if node.parent and node.parent in self.nodes:
                return [self.nodes[node.parent]]
            return []
        elif direction == "escalates":
            return [self.nodes[nid] for nid in node.escalates_to if nid in self.nodes]
        elif direction == "resolves":
            return [self.nodes[nid] for nid in node.resolves_to if nid in self.nodes]
        elif direction == "contradicts":
            return [self.nodes[nid] for nid in node.contradicts if nid in self.nodes]
        elif direction == "co_occurs":
            return [self.nodes[nid] for nid in node.co_occurs_with if nid in self.nodes]
        return []

    def get_node(self, node_id: str) -> Optional[OntologyNode]:
        return self.nodes.get(node_id)

    def get_domain_nodes(self, domain: str) -> list[OntologyNode]:
        return [self.nodes[nid] for nid in self.domains.get(domain, [])
                if nid in self.nodes]

    @staticmethod
    def hash_query(query: str) -> str:
        """Deterministic hash for path record storage."""
        return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]
