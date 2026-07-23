"""Teacher Lens Builder — learns a teacher's grading, differentiation, and
communication patterns from historical teaching artifacts (graded exams,
parent updates, lesson plans, student evaluations) so that generated content
can be adapted to match that specific teacher's style.

Classification is signal-based on document *structure*, not on a
pre-existing `doc_type` field a source file might already carry — real
teacher archives are rarely pre-tagged, so the builder has to recognize
document types the same way a person skimming the file would: by which
keys are present.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Privacy boundary: this ingest path is for a teacher's own historical
# artifacts (exams, plans, updates they authored), never raw student
# records — those go through the redaction-hardened path in
# src/lingua_viva/ingest.py, if at all.
BLOCKED_INGEST_TYPES = {"student-records"}

# (required_keys, doc_type) — first structural match wins. Deliberately
# does not read any `doc_type` field the source JSON might already carry.
_CLASSIFICATION_SIGNALS: list[tuple[set[str], str]] = [
    ({"criteria", "rubric_levels"}, "exam"),
    ({"learning_objectives", "scaffolding_pattern"}, "lesson_plan"),
    ({"sections", "voice_notes"}, "parent_update"),
    ({"assessment_dimensions", "rti_status"}, "evaluation"),
]

_TIERS = ("foundational", "on_track", "extended")

_WORD_RE = re.compile(r"[a-zàèéìòù']+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


@dataclass
class IngestResult:
    doc_id: str
    classified_type: str
    patterns_extracted: list[str]
    confidence: float


@dataclass
class DocClassification:
    doc_type: str
    confidence: float
    signals: list[str]


@dataclass
class TeacherLens:
    teacher_id: str
    grading_calibration: dict = field(default_factory=dict)
    differentiation_style: dict = field(default_factory=dict)
    communication_voice: dict = field(default_factory=dict)
    assessment_weighting: dict = field(default_factory=dict)
    pacing_style: dict = field(default_factory=dict)
    ingested_doc_count: int = 0
    last_updated: str = ""
    source_documents: list[dict] = field(default_factory=list)


@dataclass
class HoldoutResult:
    overall_score: float
    criteria_overlap: float
    vocabulary_overlap: float
    structural_match: float
    detail: str


class TeacherLensBuilder:
    """Build a Teacher Lens from historical teaching artifacts.

    Lifecycle:
        builder = TeacherLensBuilder("teacher-claudia", Path("~/.lingua-viva/teacher_lenses/"))
        builder.ingest(Path("exam_g3_u1.json"), doc_type="auto")
        builder.ingest(Path("parent_update_marco.json"), doc_type="auto")
        lens = builder.build_lens()
        score = builder.holdout_score(Path("exam_g3_u3.json"), "exam")
    """

    def __init__(self, teacher_id: str, storage_path: Path):
        self.teacher_id = teacher_id
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, dict] = {}
        self._load_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _state_path(self) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", self.teacher_id)
        return self.storage_path / f"{safe_id}.json"

    def _load_state(self) -> None:
        p = self._state_path()
        if p.exists():
            try:
                data = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                return
            self._docs = data.get("docs", {})

    def _save_state(self) -> None:
        self._state_path().write_text(json.dumps({"docs": self._docs}, indent=2))

    @staticmethod
    def _doc_id_for(file_path: Path) -> str:
        # Content-derived id (not path-derived) so identical content ingested
        # twice — even from a different path — is idempotent.
        content = Path(file_path).read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(self, file_path: Path) -> DocClassification:
        """Identify document type without ingesting. Pure read-only."""
        try:
            data = json.loads(Path(file_path).read_text())
        except (OSError, json.JSONDecodeError):
            return DocClassification(doc_type="unknown", confidence=0.0, signals=[])
        if not isinstance(data, dict):
            return DocClassification(doc_type="unknown", confidence=0.0, signals=[])

        keys = set(data.keys())
        for required, doc_type in _CLASSIFICATION_SIGNALS:
            matched = required & keys
            if matched == required:
                return DocClassification(doc_type=doc_type, confidence=1.0, signals=sorted(matched))
        return DocClassification(doc_type="unknown", confidence=0.0, signals=[])

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    def ingest(self, file_path: Path, doc_type: str = "auto") -> IngestResult:
        file_path = Path(file_path)
        if doc_type in BLOCKED_INGEST_TYPES:
            raise ValueError(
                f"doc_type '{doc_type}' is not permitted for teacher-history ingest "
                "(privacy boundary — see src/lingua_viva/ingest.py BLOCKED_DOC_TYPES)"
            )

        classification = self.classify(file_path)
        doc_id = self._doc_id_for(file_path)

        if doc_type == "auto":
            resolved_type = classification.doc_type
            confidence = classification.confidence
        else:
            resolved_type = doc_type
            confidence = 1.0

        if confidence == 0.0:
            # Unrecognizable content — do not ingest, report faithfully.
            return IngestResult(
                doc_id=doc_id, classified_type=resolved_type, patterns_extracted=[], confidence=0.0
            )

        try:
            content = json.loads(file_path.read_text())
        except (OSError, json.JSONDecodeError):
            content = {}

        patterns = self._extract_patterns(resolved_type, content)
        now = datetime.now(timezone.utc).isoformat()

        # Idempotent: re-ingesting identical content overwrites its own
        # entry (same doc_id) rather than duplicating it.
        self._docs[doc_id] = {
            "type": resolved_type,
            "content": content,
            "ingested_at": now,
            "patterns": patterns,
        }
        self._save_state()

        return IngestResult(
            doc_id=doc_id, classified_type=resolved_type, patterns_extracted=patterns, confidence=confidence
        )

    def _extract_patterns(self, doc_type: str, content: dict) -> list[str]:
        """Human-readable pattern labels extracted at ingest time (used for
        IngestResult reporting; build_lens() re-derives the structured lens
        from self._docs directly so it stays a pure function of stored state)."""
        patterns: list[str] = []
        if doc_type == "exam":
            for c in content.get("criteria", []):
                if isinstance(c, dict) and c.get("name"):
                    patterns.append(f"criterion:{c['name']}")
        elif doc_type == "lesson_plan":
            for tier in _TIERS:
                if tier in content.get("scaffolding_pattern", {}):
                    patterns.append(f"scaffolding:{tier}")
        elif doc_type == "parent_update":
            for section in content.get("sections", []):
                if isinstance(section, dict) and section.get("heading"):
                    patterns.append(f"section:{section['heading']}")
        elif doc_type == "evaluation":
            for dim in content.get("assessment_dimensions", {}):
                patterns.append(f"dimension:{dim}")
        return patterns

    # ------------------------------------------------------------------
    # Lens synthesis
    # ------------------------------------------------------------------

    def _docs_of_type(self, doc_type: str) -> list[dict]:
        return [d for d in self._docs.values() if d["type"] == doc_type]

    def _doc_id_for_content(self, entry: dict) -> str:
        # Recover the doc_id for citation purposes by matching identity.
        for doc_id, d in self._docs.items():
            if d is entry:
                return doc_id
        return "unknown"

    def build_lens(self) -> TeacherLens:
        if not self._docs:
            raise ValueError("No documents ingested")

        grading_calibration = self._build_grading_calibration()
        differentiation_style = self._build_differentiation_style()
        communication_voice = self._build_communication_voice()
        assessment_weighting = self._build_assessment_weighting()
        pacing_style = self._build_pacing_style()

        source_documents = sorted(
            (
                {"doc_id": doc_id, "type": d["type"], "ingested_at": d["ingested_at"]}
                for doc_id, d in self._docs.items()
            ),
            key=lambda x: x["doc_id"],
        )

        return TeacherLens(
            teacher_id=self.teacher_id,
            grading_calibration=grading_calibration,
            differentiation_style=differentiation_style,
            communication_voice=communication_voice,
            assessment_weighting=assessment_weighting,
            pacing_style=pacing_style,
            ingested_doc_count=len(self._docs),
            last_updated=datetime.now(timezone.utc).isoformat(),
            source_documents=source_documents,
        )

    def _build_grading_calibration(self) -> dict:
        calibration: dict[str, dict] = {}
        for doc_id, d in self._docs.items():
            if d["type"] != "exam":
                continue
            for c in d["content"].get("criteria", []):
                if not isinstance(c, dict) or not c.get("name"):
                    continue
                name = c["name"]
                entry = calibration.setdefault(name, {"weight": 0.0, "examples": [], "_n": 0})
                entry["weight"] = (entry["weight"] * entry["_n"] + float(c.get("weight", 0.0))) / (
                    entry["_n"] + 1
                )
                entry["_n"] += 1
                descriptor = c.get("descriptor", "")
                entry["examples"].append(f"{doc_id}: {descriptor}" if descriptor else doc_id)
        for entry in calibration.values():
            entry.pop("_n", None)
        return calibration

    def _build_differentiation_style(self) -> dict:
        style = {tier: {"scaffolding": [], "extensions": []} for tier in _TIERS}
        for d in self._docs.values():
            if d["type"] != "lesson_plan":
                continue
            pattern = d["content"].get("scaffolding_pattern", {})
            for tier in _TIERS:
                techniques = pattern.get(tier, [])
                if not isinstance(techniques, list):
                    continue
                for t in techniques:
                    if t not in style[tier]["scaffolding"]:
                        style[tier]["scaffolding"].append(t)
                if tier == "extended":
                    for t in techniques:
                        if t not in style[tier]["extensions"]:
                            style[tier]["extensions"].append(t)
        return style

    def _build_communication_voice(self) -> dict:
        parent_docs = self._docs_of_type("parent_update")
        if not parent_docs:
            return {"formality": "", "l1_l2_ratio": 0.5, "focus_areas": []}

        formalities = [d["content"].get("formality", "") for d in parent_docs if d["content"].get("formality")]
        formality = formalities[0] if formalities else ""

        ratios = [
            float(d["content"]["l1_l2_ratio"])
            for d in parent_docs
            if d["content"].get("l1_l2_ratio") is not None
        ]
        l1_l2_ratio = sum(ratios) / len(ratios) if ratios else 0.5

        focus_areas: list[str] = []
        for d in parent_docs:
            for section in d["content"].get("sections", []):
                heading = section.get("heading") if isinstance(section, dict) else None
                if heading and heading not in focus_areas:
                    focus_areas.append(heading)

        return {"formality": formality, "l1_l2_ratio": l1_l2_ratio, "focus_areas": focus_areas}

    def _build_assessment_weighting(self) -> dict:
        eval_docs = self._docs_of_type("evaluation")
        if not eval_docs:
            return {}

        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for d in eval_docs:
            for dim, spec in d["content"].get("assessment_dimensions", {}).items():
                weight = float(spec.get("weight", 0.0)) if isinstance(spec, dict) else 0.0
                totals[dim] = totals.get(dim, 0.0) + weight
                counts[dim] = counts.get(dim, 0) + 1

        averaged = {dim: totals[dim] / counts[dim] for dim in totals}
        total = sum(averaged.values())
        if total <= 0:
            return {}
        return {dim: w / total for dim, w in averaged.items()}

    def _build_pacing_style(self) -> dict:
        pacing: dict[str, dict] = {}
        for d in self._docs.values():
            content = d["content"]
            unit = content.get("unit")
            duration = content.get("duration_minutes")
            if unit and duration is not None:
                pacing[unit] = {"typical_duration_minutes": int(duration)}
        return pacing

    # ------------------------------------------------------------------
    # Holdout scoring
    # ------------------------------------------------------------------

    def holdout_score(self, test_artifact: Path, artifact_type: str) -> HoldoutResult:
        if not self._docs:
            raise ValueError("No documents ingested")

        try:
            content = json.loads(Path(test_artifact).read_text())
        except (OSError, json.JSONDecodeError):
            content = {}

        criteria_overlap = 0.0
        vocabulary_overlap = 0.0
        structural_match = 0.0

        if artifact_type == "exam":
            criteria_overlap = self._score_criteria_overlap(content, "exam", "criteria")
            overall = criteria_overlap
            detail = f"criteria_overlap={criteria_overlap:.2f} against {len(self._docs_of_type('exam'))} trained exam(s)"
        elif artifact_type == "evaluation":
            criteria_overlap = self._score_criteria_overlap(content, "evaluation", "assessment_dimensions")
            overall = criteria_overlap
            detail = f"dimension_overlap={criteria_overlap:.2f} against {len(self._docs_of_type('evaluation'))} trained evaluation(s)"
        elif artifact_type == "parent_update":
            vocabulary_overlap = self._score_vocabulary_overlap(content)
            overall = vocabulary_overlap
            detail = f"vocabulary_overlap={vocabulary_overlap:.2f} against {len(self._docs_of_type('parent_update'))} trained parent update(s)"
        elif artifact_type == "lesson_plan":
            structural_match = self._score_structural_match(content)
            overall = structural_match
            detail = f"structural_match={structural_match:.2f} against {len(self._docs_of_type('lesson_plan'))} trained lesson plan(s)"
        else:
            overall = 0.0
            detail = f"Unrecognized artifact_type '{artifact_type}' — no scoring dimension applies."

        return HoldoutResult(
            overall_score=overall,
            criteria_overlap=criteria_overlap,
            vocabulary_overlap=vocabulary_overlap,
            structural_match=structural_match,
            detail=detail,
        )

    def _score_criteria_overlap(self, content: dict, doc_type: str, key: str) -> float:
        trained = self._docs_of_type(doc_type)
        if not trained:
            return 0.0
        trained_names: set[str] = set()
        for d in trained:
            raw = d["content"].get(key, [])
            if isinstance(raw, dict):
                trained_names |= set(raw.keys())
            elif isinstance(raw, list):
                trained_names |= {c["name"] for c in raw if isinstance(c, dict) and c.get("name")}

        raw = content.get(key, [])
        if isinstance(raw, dict):
            test_names = set(raw.keys())
        elif isinstance(raw, list):
            test_names = {c["name"] for c in raw if isinstance(c, dict) and c.get("name")}
        else:
            test_names = set()

        if not test_names:
            return 0.0
        return len(trained_names & test_names) / len(test_names)

    def _score_vocabulary_overlap(self, content: dict) -> float:
        trained = self._docs_of_type("parent_update")
        if not trained:
            return 0.0

        def heading_words(sections: list) -> set[str]:
            words: set[str] = set()
            for s in sections:
                if isinstance(s, dict) and s.get("heading"):
                    words |= _tokenize(s["heading"])
            return words

        def body_words(sections: list) -> set[str]:
            words: set[str] = set()
            for s in sections:
                if not isinstance(s, dict):
                    continue
                words |= _tokenize(s.get("content_it", ""))
                words |= _tokenize(s.get("content_en", ""))
            return words

        trained_headings: set[str] = set()
        trained_body: set[str] = set()
        for d in trained:
            sections = d["content"].get("sections", [])
            trained_headings |= heading_words(sections)
            trained_body |= body_words(sections)

        test_sections = content.get("sections", [])
        test_headings = heading_words(test_sections)
        test_body = body_words(test_sections)

        heading_overlap = (
            len(trained_headings & test_headings) / len(test_headings) if test_headings else 0.0
        )
        body_overlap = (
            len(trained_body & test_body) / min(len(trained_body), len(test_body))
            if trained_body and test_body
            else 0.0
        )
        return 0.5 * heading_overlap + 0.5 * body_overlap

    def _score_structural_match(self, content: dict) -> float:
        trained = self._docs_of_type("lesson_plan")
        if not trained:
            return 0.0

        def technique_words(pattern: dict) -> set[str]:
            words: set[str] = set()
            for tier in _TIERS:
                for t in pattern.get(tier, []) or []:
                    words |= _tokenize(str(t))
            return words

        trained_tiers: set[str] = set()
        trained_words: set[str] = set()
        for d in trained:
            pattern = d["content"].get("scaffolding_pattern", {})
            trained_tiers |= set(pattern.keys())
            trained_words |= technique_words(pattern)

        test_pattern = content.get("scaffolding_pattern", {})
        test_tiers = set(test_pattern.keys())
        test_words = technique_words(test_pattern)

        tier_overlap = len(trained_tiers & test_tiers) / len(test_tiers) if test_tiers else 0.0
        word_overlap = (
            len(trained_words & test_words) / min(len(trained_words), len(test_words))
            if trained_words and test_words
            else 0.0
        )
        return 0.5 * tier_overlap + 0.5 * word_overlap
