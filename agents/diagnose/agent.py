"""
DIAGNOSE Agent — Structured root cause analysis.

Structures model output into: symptom → hypotheses → evidence → root cause → fix.
Diagnosis paths are the highest-value memory artifacts the system produces.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiagnosisRecord:
    """A structured root cause analysis."""
    session_id: str
    query_hash: str
    symptom: str = ""
    hypotheses: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    root_cause: str = ""
    recommendation: str = ""
    reversibility: str = "unknown"
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# Section markers the model might use (from the DIAGNOSE prompt)
SECTION_MARKERS = {
    "symptom": ["symptom:", "problem:", "issue:", "the symptom is"],
    "hypothesis": ["hypothesis:", "hypotheses:", "possible cause:", "why:"],
    "evidence": ["evidence:", "because:", "data shows:", "confirmed by:"],
    "root_cause": ["root cause:", "root-cause:", "the root cause is", "determined:"],
    "recommendation": ["recommendation:", "fix:", "solution:", "next step:"],
}


class DiagnoseAgent:
    """
    DIAGNOSE intent agent. Structures root cause analysis.

    Extracts structured diagnosis from model output.
    The structured record feeds back into path records more
    usefully than free-text — enables pattern matching across diagnoses.
    """

    INTENT = "DIAGNOSE"

    def __init__(self):
        self._diagnoses_file = Path(__file__).parent.parent.parent / "memory" / "data" / "diagnoses.ndjson"
        self._diagnoses_file.parent.mkdir(parents=True, exist_ok=True)

    def analyze(self, content: str, session_id: str, query_hash: str, confidence: float) -> DiagnosisRecord:
        """Parse model output into structured diagnosis."""
        record = DiagnosisRecord(
            session_id=session_id,
            query_hash=query_hash,
            confidence=confidence,
        )

        # Try to extract structured sections
        content_lower = content.lower()
        sections = self._extract_sections(content, content_lower)

        record.symptom = sections.get("symptom", content[:200].strip())
        record.hypotheses = self._split_list(sections.get("hypothesis", ""))
        record.evidence = self._split_list(sections.get("evidence", ""))
        record.root_cause = sections.get("root_cause", "")
        record.recommendation = sections.get("recommendation", "")

        self._persist(record)
        return record

    def _extract_sections(self, content: str, content_lower: str) -> dict[str, str]:
        """Extract named sections from the model output."""
        sections = {}
        for section_name, markers in SECTION_MARKERS.items():
            for marker in markers:
                idx = content_lower.find(marker)
                if idx >= 0:
                    start = idx + len(marker)
                    # Find end: next section marker or end of content
                    end = len(content)
                    for other_name, other_markers in SECTION_MARKERS.items():
                        if other_name == section_name:
                            continue
                        for other_marker in other_markers:
                            other_idx = content_lower.find(other_marker, start)
                            if other_idx > start and other_idx < end:
                                end = other_idx
                    sections[section_name] = content[start:end].strip()
                    break
        return sections

    def _split_list(self, text: str) -> list[str]:
        """Split a text block into list items."""
        if not text:
            return []
        items = []
        for line in text.split("\n"):
            line = line.strip().lstrip("-•*1234567890.")
            line = line.strip()
            if line and len(line) > 5:
                items.append(line)
        return items if items else [text.strip()]

    def _persist(self, record: DiagnosisRecord) -> None:
        """Append to diagnoses NDJSON."""
        with open(self._diagnoses_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
