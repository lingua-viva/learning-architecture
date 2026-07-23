# Eval Interface Contracts

**Purpose**: This file specifies every function/class the eval suite expects to exist.  
**Audience**: The implementation team building to these contracts.  
**Rule**: If an eval calls it, it's listed here. If it's not listed here, no eval calls it.

---

## 1. TeacherLensBuilder (NEW — `src/education/teacher_lens_builder.py`)

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class IngestResult:
    doc_id: str
    classified_type: str  # "exam" | "parent_update" | "evaluation" | "lesson_plan" | "rubric"
    patterns_extracted: list[str]
    confidence: float  # 0.0–1.0


@dataclass
class DocClassification:
    doc_type: str  # "exam" | "parent_update" | "evaluation" | "lesson_plan" | "rubric" | "unknown"
    confidence: float  # 0.0–1.0
    signals: list[str]  # what triggered the classification


@dataclass
class TeacherLens:
    teacher_id: str
    grading_calibration: dict  # criterion_name → {"weight": float, "examples": [...]}
    differentiation_style: dict  # tier → {"scaffolding": [...], "extensions": [...]}
    communication_voice: dict  # {"formality": str, "l1_l2_ratio": float, "focus_areas": [...]}
    assessment_weighting: dict  # dimension → float (must sum to 1.0 ±0.01)
    pacing_style: dict  # unit → {"typical_duration_minutes": int}
    ingested_doc_count: int
    last_updated: str  # ISO8601
    source_documents: list[dict]  # [{"doc_id": str, "type": str, "ingested_at": str}]


@dataclass
class HoldoutResult:
    overall_score: float  # 0.0–1.0
    criteria_overlap: float  # 0.0–1.0 (for exams/rubrics)
    vocabulary_overlap: float  # 0.0–1.0 (for parent updates)
    structural_match: float  # 0.0–1.0 (for lesson plans)
    detail: str  # human-readable explanation


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
        """
        Args:
            teacher_id: Unique identifier for the teacher
            storage_path: Directory for persisting lens data
        """
        ...

    def ingest(self, file_path: Path, doc_type: str = "auto") -> IngestResult:
        """Ingest one historical document.

        Behavioral contracts:
            - "auto" doc_type triggers classification from content
            - Same file ingested twice → idempotent (no duplicates)
            - Ingesting a file updates the lens incrementally
            - doc_type "student-records" → raises ValueError (privacy boundary)
            - Returns confidence 0.0 if classification fails

        Args:
            file_path: Path to the document (JSON format, schema per doc type)
            doc_type: "auto" | "exam" | "parent_update" | "evaluation" | "lesson_plan" | "rubric"

        Returns:
            IngestResult with classification and extracted patterns
        """
        ...

    def classify(self, file_path: Path) -> DocClassification:
        """Identify document type without ingesting.

        Behavioral contracts:
            - Pure read-only — does not modify stored state
            - Returns doc_type="unknown" with confidence=0.0 if unrecognizable
            - signals list explains what triggered the classification

        Args:
            file_path: Path to the document

        Returns:
            DocClassification with type, confidence, and signals
        """
        ...

    def build_lens(self) -> TeacherLens:
        """Synthesize all ingested patterns into a coherent Teacher Lens.

        Behavioral contracts:
            - Deterministic: same ingested documents → same lens (byte-identical)
            - assessment_weighting values sum to 1.0 ±0.01
            - Every pattern in grading_calibration cites at least one source doc_id
            - If zero documents ingested → raises ValueError("No documents ingested")
            - source_documents list includes every successfully ingested doc

        Returns:
            TeacherLens with all pattern dimensions populated
        """
        ...

    def holdout_score(self, test_artifact: Path, artifact_type: str) -> HoldoutResult:
        """Score a held-out artifact against the current lens.

        Behavioral contracts:
            - Does NOT ingest the test artifact (read-only scoring)
            - overall_score is the weighted average of dimension scores
            - For exam type: criteria_overlap is primary (weight 0.6)
            - For parent_update type: vocabulary_overlap is primary (weight 0.6)
            - For lesson_plan type: structural_match is primary (weight 0.6)
            - If lens has zero documents → raises ValueError

        Args:
            test_artifact: Path to the artifact being scored
            artifact_type: "exam" | "parent_update" | "evaluation" | "lesson_plan"

        Returns:
            HoldoutResult with dimensional scores
        """
        ...
```

---

## 2. ContentDifferentiator Extensions (`src/education/content_differentiator.py`)

```python
class ContentDifferentiator:
    # EXISTING — do not modify signatures:
    # generate(lesson: LessonInput, source_chunks=None) → ContentPack
    # generate_from_documents(lesson, retriever, domain, query=None, k=5) → ContentPack
    # assign_tier_for_student(student_lens: dict) → str
    # assign_packs_for_roster(pack, roster) → dict[str, str]

    def generate_with_teacher_lens(
        self,
        lesson: "LessonInput",
        teacher_lens: "TeacherLens",
        retriever=None,
        domain: str = "curriculum",
    ) -> "ContentPack":
        """Generate a pack that matches this specific teacher's style.

        Behavioral contracts:
            - Uses teacher_lens.differentiation_style to choose scaffolding
            - Uses teacher_lens.grading_calibration for assessment criteria
            - Uses teacher_lens.communication_voice for language register
            - Falls back to generate_from_documents() if teacher_lens is None
            - Falls back to generate() if retriever is also None
            - source_mode in output reflects which path was taken:
              "teacher_adapted" | "adapted" | "generated"
            - All provenance fields populated (same contract as generate_from_documents)

        Args:
            lesson: Standard LessonInput
            teacher_lens: TeacherLens from TeacherLensBuilder.build_lens()
            retriever: Optional DocumentRetriever (for document-grounding)
            domain: Retrieval domain (default "curriculum")

        Returns:
            ContentPack with teacher-style-matched content
        """
        ...
```

### assign_tier_for_student — Corrected Contract

The current implementation uses this logic:
- RTI 3 → foundational
- RTI 2 + CEFR < B1 → foundational
- RTI 2 + CEFR ≥ B1 → on_track
- RTI 1 + CEFR < B2 → on_track
- RTI 1 + CEFR ≥ B2 → extended

**Open question** (flagged for human decision): Should RTI 1 + CEFR null → "foundational" (safest) or "on_track" (current)? The eval truth table documents BOTH behaviors; the gauntlet flags the discrepancy.

---

## 3. StudentLensStore Extensions (`src/education/student_lens.py`)

```python
class StudentLensStore:
    # EXISTING — do not modify:
    # create_lens(...), append_observation(...), get_lens(...), list_lenses(...)

    def get_lens_as_of(self, student_id: str, as_of: str) -> dict:
        """Return lens state as it was at a specific point in time.

        Behavioral contracts:
            - Only includes observations with recorded_at <= as_of
            - CEFR snapshot reflects only those observations
            - RTI tier reflects the tier active at that time
            - If student doesn't exist → raises LensNotFoundError
            - If as_of is before first observation → returns default lens (RTI from create_lens)
            - as_of must be valid ISO8601; invalid → raises ValueError

        Args:
            student_id: The student identifier
            as_of: ISO8601 timestamp (inclusive upper bound)

        Returns:
            dict with same shape as get_lens() but time-bounded
        """
        ...

    def validate_observation_timestamp(self, obs: "Observation") -> list[str]:
        """Reject observations with timestamps in the future.

        Behavioral contracts:
            - Returns empty list if timestamp is valid (≤ now + 5 minutes tolerance)
            - Returns ["Observation timestamp is in the future"] if > now + 5 minutes
            - Does NOT block save (validation is advisory per existing convention)
            - "now" is UTC

        Args:
            obs: Observation to validate

        Returns:
            List of validation error strings (empty = valid)
        """
        ...
```

---

## 4. Summary: What Exists vs What's New

| Interface | File | Status |
|-----------|------|--------|
| `TeacherLensBuilder` | `src/education/teacher_lens_builder.py` | **NEW** — entire class |
| `TeacherLens` (dataclass) | `src/education/teacher_lens_builder.py` | **NEW** |
| `IngestResult` (dataclass) | `src/education/teacher_lens_builder.py` | **NEW** |
| `DocClassification` (dataclass) | `src/education/teacher_lens_builder.py` | **NEW** |
| `HoldoutResult` (dataclass) | `src/education/teacher_lens_builder.py` | **NEW** |
| `ContentDifferentiator.generate_with_teacher_lens()` | `src/education/content_differentiator.py` | **NEW** method |
| `StudentLensStore.get_lens_as_of()` | `src/education/student_lens.py` | **NEW** method |
| `StudentLensStore.validate_observation_timestamp()` | `src/education/student_lens.py` | **NEW** method |
| `ContentDifferentiator.assign_tier_for_student()` | `src/education/content_differentiator.py` | EXISTS — eval verifies behavior |
| `ContentDifferentiator.generate_from_documents()` | `src/education/content_differentiator.py` | EXISTS — eval verifies provenance |
| `DocumentStore.search()` | `src/education/document_store.py` | EXISTS — eval verifies grade fencing |

---

## 5. File Locations

All new implementation goes in `src/education/`. No changes to `src/lingua_viva/` or `src/web.py` are required for the evals to pass — the evals test the domain logic directly, not through HTTP endpoints.

---

**End of contracts.**
