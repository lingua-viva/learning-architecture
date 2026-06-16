"""
CREATE Agent — Artifact generation with provenance tracking.

Every artifact the system produces gets a provenance record:
what knowledge entries informed it, which paths were relevant,
what research was used, and when it was created.

The provenance record IS the audit trail. A lawyer can trace
every claim in a generated memo back to its source.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ArtifactRecord:
    """Provenance record for a created artifact."""
    session_id: str
    query_hash: str
    artifact_type: str = "document"  # document, code, plan, analysis
    title: str = ""
    content_hash: str = ""
    knowledge_used: list[str] = field(default_factory=list)
    paths_referenced: list[str] = field(default_factory=list)
    research_used: bool = False
    ontology_node: str = ""
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# Artifact type detection patterns
TYPE_SIGNALS = {
    "code": ["```", "def ", "function ", "class ", "import ", "const "],
    "plan": ["step 1", "phase 1", "milestone", "timeline", "deliverable"],
    "analysis": ["finding", "conclusion", "recommendation", "assessment"],
    "memo": ["re:", "from:", "to:", "subject:", "memorandum"],
}


class CreateAgent:
    """
    CREATE intent agent. Tracks artifact provenance.

    After the model generates content, the CREATE agent:
    1. Detects what type of artifact was produced
    2. Records which KL entries and paths informed it
    3. Stores the provenance record for the audit trail
    """

    INTENT = "CREATE"

    def __init__(self):
        self._artifacts_file = Path(__file__).parent.parent.parent / "memory" / "data" / "artifacts.ndjson"
        self._artifacts_file.parent.mkdir(parents=True, exist_ok=True)

    def analyze(
        self,
        content: str,
        session_id: str,
        query_hash: str,
        node_id: str,
        knowledge_used: list[str],
        research_used: bool,
        confidence: float,
    ) -> ArtifactRecord:
        """Analyze created content and produce a provenance record."""
        artifact_type = self._detect_type(content)
        title = self._extract_title(content)

        import hashlib
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        record = ArtifactRecord(
            session_id=session_id,
            query_hash=query_hash,
            artifact_type=artifact_type,
            title=title,
            content_hash=content_hash,
            knowledge_used=knowledge_used,
            research_used=research_used,
            ontology_node=node_id,
            confidence=confidence,
        )

        self._persist(record)
        return record

    def _detect_type(self, content: str) -> str:
        """Detect artifact type from content patterns."""
        content_lower = content.lower()
        scores = {}
        for atype, signals in TYPE_SIGNALS.items():
            scores[atype] = sum(1 for s in signals if s in content_lower)
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                return best
        return "document"

    def _extract_title(self, content: str) -> str:
        """Extract a title from the first line or heading."""
        for line in content.split("\n"):
            line = line.strip().lstrip("#").strip()
            if line and len(line) > 5:
                return line[:100]
        return "Untitled artifact"

    def _persist(self, record: ArtifactRecord) -> None:
        with open(self._artifacts_file, "a") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
