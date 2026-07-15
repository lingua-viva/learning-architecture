"""
Candidate RIU System — The ontology grows from its own gaps.

When a query falls to fallback (low confidence, no signal match), a candidate
RIU is created. The candidate is a YAML file that evolves as the user works:

  1. CREATED  — query fell to fallback, logged with initial signals
  2. ENRICHED — user keeps working, candidate accumulates context
  3. EVALUATED — task ends, system checks: new RIU or existing fit?
  4. PROMOTED  — becomes a real node in the ontology
  5. DISCARDED — mapped to existing node, candidate archived

The candidate YAML is static but improved — it gets updated as the user
solves their problem. When the task is done, re-evaluate. If it's real,
promote it. If not, discard it.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class CandidateRIU:
    """A proposed ontology node grown from a gap in classification."""
    candidate_id: str
    status: str = "CREATED"  # CREATED, ENRICHED, EVALUATED, PROMOTED, DISCARDED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # From the original query that triggered the gap
    original_query: str = ""
    query_hash: str = ""
    fallback_node: str = ""        # Which node it fell back to
    fallback_confidence: float = 0.0

    # Accumulated signals — grows as user works
    signals: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)  # Hashed queries that hit this candidate
    domain: str = "unknown"

    # Knowledge gathered during the session
    perplexity_findings: list[dict] = field(default_factory=list)  # Research results
    knowledge_refs: list[str] = field(default_factory=list)         # KL entries found useful
    path_records: list[str] = field(default_factory=list)           # Path record IDs

    # Evaluation data
    hit_count: int = 1             # How many queries hit this candidate
    avg_confidence: float = 0.0    # Average exit confidence for paths at this candidate
    resolution: Optional[str] = None   # "promoted:NEW-RIU-ID" or "discarded:EXISTING-RIU-ID"
    evaluation_notes: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, d: dict) -> CandidateRIU:
        valid = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in valid})


class CandidateStore:
    """
    Manages candidate RIUs. Stores as individual YAML files in ontology/proposals/.

    The files are human-readable and editable — a person can review candidates
    and make promotion decisions. The system proposes, the human disposes.
    """

    def __init__(self, proposals_dir: Optional[Path] = None):
        self._dir = proposals_dir or Path(__file__).parent
        self._dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        query: str,
        query_hash: str,
        fallback_node: str,
        fallback_confidence: float,
        signals: list[str],
        domain: str = "unknown",
        perplexity_result: Optional[dict] = None,
    ) -> CandidateRIU:
        """Create a new candidate from a gap signal."""
        # Check if a candidate already exists for similar signals
        existing = self._find_similar(signals, fallback_node)
        if existing:
            return self.enrich(existing.candidate_id, query, query_hash,
                             signals, perplexity_result)

        candidate = CandidateRIU(
            candidate_id=f"CAND-{uuid.uuid4().hex[:8].upper()}",
            original_query=query,
            query_hash=query_hash,
            fallback_node=fallback_node,
            fallback_confidence=fallback_confidence,
            signals=signals,
            queries=[query_hash],
            domain=domain,
        )

        if perplexity_result:
            candidate.perplexity_findings.append(perplexity_result)

        self._save(candidate)
        return candidate

    def enrich(
        self,
        candidate_id: str,
        query: str,
        query_hash: str,
        new_signals: list[str],
        perplexity_result: Optional[dict] = None,
    ) -> CandidateRIU:
        """Enrich an existing candidate with new context from continued work."""
        candidate = self.get(candidate_id)
        if not candidate:
            return None

        candidate.status = "ENRICHED"
        candidate.updated_at = time.time()
        candidate.hit_count += 1

        # Add new signals (deduplicated)
        for s in new_signals:
            if s not in candidate.signals:
                candidate.signals.append(s)

        # Track the query
        if query_hash not in candidate.queries:
            candidate.queries.append(query_hash)

        # Add research findings
        if perplexity_result:
            candidate.perplexity_findings.append(perplexity_result)

        self._save(candidate)
        return candidate

    def evaluate(self, candidate_id: str, ontology_engine) -> CandidateRIU:
        """
        Evaluate a candidate: should it become a real RIU?

        Criteria:
          1. Hit count > 1 (multiple queries needed this node)
          2. Signals are distinct from existing nodes
          3. Average path confidence was reasonable (>0.5)
          4. Domain is identifiable

        Returns the candidate with evaluation result.
        """
        candidate = self.get(candidate_id)
        if not candidate:
            return None

        candidate.status = "EVALUATED"
        candidate.updated_at = time.time()

        # Check 1: Was it used by more than one unique query?
        unique_queries = len(set(candidate.queries))
        if unique_queries < 2:
            candidate.resolution = "discarded:single_use"
            candidate.evaluation_notes = (
                f"Only {unique_queries} unique query — may be a one-off, not a pattern. "
                f"(hit_count={candidate.hit_count} includes enrichment calls)"
            )
            self._save(candidate)
            return candidate

        # Check 2: Do the signals overlap significantly with an existing node?
        best_overlap = self._find_best_overlap(candidate.signals, ontology_engine)
        if best_overlap and best_overlap[1] > 0.7:
            candidate.resolution = f"discarded:overlaps_{best_overlap[0]}"
            candidate.evaluation_notes = (
                f"Signals overlap {best_overlap[1]:.0%} with {best_overlap[0]}. "
                f"Map these queries to the existing node instead."
            )
            self._save(candidate)
            return candidate

        # Check 3: Is there enough signal diversity?
        if len(candidate.signals) < 3:
            candidate.resolution = "discarded:insufficient_signals"
            candidate.evaluation_notes = "Fewer than 3 signals — not enough to define a node."
            self._save(candidate)
            return candidate

        # Passes all checks — recommend promotion
        candidate.resolution = "promote"
        candidate.evaluation_notes = (
            f"{unique_queries} unique queries, {len(candidate.signals)} distinct signals, "
            f"domain '{candidate.domain}'. Ready for promotion to ontology node."
        )
        self._save(candidate)
        return candidate

    def promote(self, candidate_id: str, new_riu_id: str, ontology_engine) -> Optional[dict]:
        """
        Promote a candidate to a real ontology node.

        Returns the node dict ready to be added to a domain YAML.
        This is a Tier 1 change — requires human approval.
        """
        candidate = self.get(candidate_id)
        if not candidate or candidate.resolution != "promote":
            return None

        node = {
            "id": new_riu_id,
            "name": self._generate_name(candidate),
            "description": self._generate_description(candidate),
            "domain": candidate.domain,
            "parent": candidate.fallback_node,
            "signals": candidate.signals,
            "blocks_external": False,
            "requires_local": False,
            "escalates_to": [candidate.fallback_node],
            "resolves_to": [],
            "evidence_tier": 3,  # Community tier — needs validation
            "path_weight": 1.0,
            "default_intent": "RESEARCH",
        }

        candidate.status = "PROMOTED"
        candidate.resolution = f"promoted:{new_riu_id}"
        candidate.updated_at = time.time()
        self._save(candidate)

        return node

    def get(self, candidate_id: str) -> Optional[CandidateRIU]:
        path = self._dir / f"{candidate_id}.yaml"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return CandidateRIU.from_dict(data) if data else None

    def list_active(self) -> list[CandidateRIU]:
        """List all candidates that haven't been resolved."""
        active = []
        for path in self._dir.glob("CAND-*.yaml"):
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and data.get("status") in ("CREATED", "ENRICHED"):
                active.append(CandidateRIU.from_dict(data))
        return active

    def list_ready(self) -> list[CandidateRIU]:
        """List candidates evaluated and ready for promotion."""
        ready = []
        for path in self._dir.glob("CAND-*.yaml"):
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and data.get("resolution") == "promote":
                ready.append(CandidateRIU.from_dict(data))
        return ready

    # --- Private ---

    def _save(self, candidate: CandidateRIU) -> None:
        path = self._dir / f"{candidate.candidate_id}.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(candidate.to_dict(), f, default_flow_style=False,
                     sort_keys=False, allow_unicode=True)

    def _find_similar(self, signals: list[str], fallback_node: str = "") -> Optional[CandidateRIU]:
        """
        Find an active candidate with overlapping signals.

        Two queries that fall to the same node AND share any signal
        are likely the same gap. Merge them.
        """
        signal_set = set(s.lower() for s in signals)
        best = None
        best_score = 0

        for candidate in self.list_active():
            candidate_signals = set(s.lower() for s in candidate.signals)
            overlap = len(signal_set & candidate_signals)
            if overlap == 0:
                continue

            # Same fallback node + any overlap = strong match
            if fallback_node and candidate.fallback_node == fallback_node:
                score = overlap + 3  # Bonus for same fallback
            else:
                score = overlap

            if score > best_score:
                best_score = score
                best = candidate

        # Require meaningful overlap — at least 2 shared signals or
        # 20% of the smaller set, whichever is higher
        if best and best_score >= 2:
            return best
        if best:
            smaller = min(len(signal_set), len(set(s.lower() for s in best.signals)))
            if smaller > 0 and (best_score - 3) / smaller >= 0.2:  # subtract fallback bonus
                return best
        return None

    def _find_best_overlap(self, signals: list[str], ontology_engine) -> Optional[tuple[str, float]]:
        """Find the existing ontology node with highest signal overlap."""
        signal_set = set(s.lower() for s in signals)
        best_id = None
        best_score = 0.0

        for node_id, node in ontology_engine.nodes.items():
            node_signals = set(s.lower() for s in node.signals)
            if not node_signals:
                continue
            overlap = len(signal_set & node_signals)
            score = overlap / max(len(signal_set), 1)
            if score > best_score:
                best_score = score
                best_id = node_id

        if best_id and best_score > 0:
            return (best_id, best_score)
        return None

    def _generate_name(self, candidate: CandidateRIU) -> str:
        """Generate a node name from the candidate's signals."""
        if candidate.signals:
            # Use the most common words from signals as the name
            words = " ".join(candidate.signals).title()
            return words[:60]
        return f"Candidate {candidate.candidate_id}"

    def _generate_description(self, candidate: CandidateRIU) -> str:
        """Generate a node description from the candidate's context."""
        parts = [f"Auto-generated from {candidate.hit_count} gap queries."]
        if candidate.perplexity_findings:
            first = candidate.perplexity_findings[0]
            content = first.get("content", "")
            if content:
                parts.append(content[:200])
        return " ".join(parts)
