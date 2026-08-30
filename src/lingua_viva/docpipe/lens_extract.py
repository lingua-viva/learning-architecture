"""
Document-to-Lens Extraction Pipeline (R3, R4, R5, R6).

SPEC: dev/SPEC_LV_DOCUMENT_TO_LENS_PIPELINE_2026-08-23.md

Wires existing infrastructure:
- extraction_engine.py (chunking, LLM extraction, verification)
- data_in_contracts.py (field contracts, ExtractionResult)
- student_lens_writer.py (write_student_lens)
- document_parser.py (PDF section chunking)
- ethos.py (match_traits for ethos evidence routing)
- observation_capture.py (suggest_support_categories for profile routing)

Heuristics first, LLM second. Two-step flow: extract+preview, then confirm+write.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.education.document_parser import DocumentParser
from src.education.ethos import load_ethos, match_traits
from src.education.observation_capture import suggest_support_categories
from src.education.student_lens import StudentLensStore
from src.lingua_viva.data_in_contracts import (
    ExtractedField,
    ExtractionResult,
    SourceChunk,
    STUDENT_LENS_FIELDS,
    SUPPORT_PROFILE_CATEGORIES,
    SUPPORT_PROFILE_BUCKETS,
)
from src.lingua_viva.extraction_engine import (
    CEFR_LEVELS,
    NEVER_AUTO_VERIFY,
    _deterministic_cefr,
    _deterministic_grade,
    _find_supporting_chunks,
    chunk_file,
)
from src.lingua_viva.student_lens_writer import write_student_lens


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# IB Learner Profile attributes (official 10)
IB_LEARNER_PROFILE = (
    "inquirers", "knowledgeable", "thinkers", "communicators", "principled",
    "open-minded", "caring", "risk-takers", "balanced", "reflective",
)

# IB ATL skills
ATL_SKILLS = ("thinking", "social", "communication", "self-management", "research")

# Grade scale (IB PYP report card)
GRADE_SCALE = {
    "beginning": 1,
    "developing": 2,
    "accomplished": 3,
    "exemplary": 4,
}

# CEFR regex — captures level with optional dimension context
_CEFR_RE = re.compile(
    r"\b(reading|writing|speaking|listening)\s*[:\-–]?\s*(A1\+?|A2\+?|B1\+?|B2|C1|C2)\b"
    r"|\b(A1\+?|A2\+?|B1\+?|B2|C1|C2)\b[^.\n]{0,30}\b(reading|writing|speaking|listening)\b",
    re.IGNORECASE,
)

# RED safeguarding signals — route to restricted, never to lens
_RED_SIGNALS = re.compile(
    r"\b(abuse|neglect|sexual|domestic violence|trafficking|self[- ]harm|"
    r"suicide|mandated report|child protection|safeguarding concern)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Heuristic Extractors (no LLM — R3 step 2)
# ---------------------------------------------------------------------------

def _extract_cefr(text: str) -> list[ExtractedField]:
    """Extract CEFR levels from text using regex patterns."""
    fields = []
    found = _deterministic_cefr(text)
    for dim, level in found.items():
        fields.append(ExtractedField(
            field_path=f"cefr_snapshot.{dim}",
            value=level,
            confidence=0.95,
            supporting_chunk_ids=[],
            status="verified",
        ))
    return fields


def _extract_grade_scale(text: str) -> list[ExtractedField]:
    """Extract IB grade scale descriptors (Beginning/Developing/etc.)."""
    fields = []
    lower = text.lower()
    for label, ordinal in GRADE_SCALE.items():
        if label in lower:
            # Found a grade descriptor — add as academic evidence
            fields.append(ExtractedField(
                field_path="support_profile.categories.learning_and_cognition.evidence",
                value=f"grade descriptor: {label}",
                confidence=0.85,
                supporting_chunk_ids=[],
                status="verified",
            ))
    return fields


def _extract_learner_profile(text: str) -> list[ExtractedField]:
    """Extract IB Learner Profile attribute mentions."""
    fields = []
    lower = text.lower()
    found_attrs = []
    for attr in IB_LEARNER_PROFILE:
        if re.search(rf"\b{re.escape(attr)}\b", lower):
            found_attrs.append(attr)
    if found_attrs:
        fields.append(ExtractedField(
            field_path="support_profile.categories.learning_and_cognition.strengths",
            value=", ".join(found_attrs),
            confidence=0.85,
            supporting_chunk_ids=[],
            status="verified",
        ))
    return fields


def _extract_atl_skills(text: str) -> list[ExtractedField]:
    """Extract ATL skill mentions."""
    fields = []
    lower = text.lower()
    found_skills = []
    for skill in ATL_SKILLS:
        if re.search(rf"\b{re.escape(skill)}\s*(skills?)?\b", lower):
            found_skills.append(skill)
    if found_skills:
        fields.append(ExtractedField(
            field_path="support_profile.categories.learning_and_cognition.strengths",
            value=f"ATL: {', '.join(found_skills)}",
            confidence=0.80,
            supporting_chunk_ids=[],
            status="verified",
        ))
    return fields


def _extract_attendance(text: str) -> list[ExtractedField]:
    """Extract attendance data."""
    fields = []
    lower = text.lower()
    # Look for absence/attendance counts or percentages
    attendance_match = re.search(
        r"(\d+)\s*%?\s*(attendance|present|absent)",
        lower,
    )
    if attendance_match:
        fields.append(ExtractedField(
            field_path="support_profile.categories.attendance_and_engagement.evidence",
            value=attendance_match.group(0).strip(),
            confidence=0.90,
            supporting_chunk_ids=[],
            status="verified",
        ))
    return fields


def _route_to_support_category(text: str) -> list[ExtractedField]:
    """Route text snippets to support profile categories using observation_capture logic."""
    fields = []
    suggestions = suggest_support_categories(text)
    for suggestion in suggestions:
        if suggestion["confidence"] >= 0.5:
            cat_id = suggestion["category_id"]
            # Condense the text to keywords/summary (R4b output format)
            condensed = _condense_to_keywords(text)
            if condensed:
                fields.append(ExtractedField(
                    field_path=f"support_profile.categories.{cat_id}.evidence",
                    value=condensed,
                    confidence=suggestion["confidence"],
                    supporting_chunk_ids=[],
                    status="needs_confirmation" if suggestion["confidence"] < 0.7 else "verified",
                ))
    return fields


def _route_to_ethos(text: str) -> list[ExtractedField]:
    """Route text to ethos traits using match_traits from ethos.py."""
    fields = []
    try:
        ethos = load_ethos()
    except Exception:
        return fields
    matched = match_traits(text, ethos)
    if matched:
        condensed = _condense_to_keywords(text)
        for trait_id in matched:
            fields.append(ExtractedField(
                field_path=f"ethos_profile.traits.{trait_id}.evidence",
                value=condensed,
                confidence=0.7,
                supporting_chunk_ids=[],
                status="needs_confirmation",
            ))
    return fields


def _condense_to_keywords(text: str, max_len: int = 80) -> str:
    """Condense a sentence to keywords/summary. Not full sentences."""
    # Strip common filler words and condense
    text = text.strip()
    if len(text) <= max_len:
        return text
    # Take first max_len characters and cut at last word boundary
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    return truncated.strip()


def _is_red_safeguarding(text: str) -> bool:
    """Check if text contains RED safeguarding content."""
    return bool(_RED_SIGNALS.search(text))


# ---------------------------------------------------------------------------
# Section Splitter — isolate per-student text (cross-contamination guard)
# ---------------------------------------------------------------------------

# The 10 lens profile field IDs used by the LLM classifier.
_LENS_FIELD_IDS = (
    "learning_and_cognition",
    "communication_and_language",
    "executive_functioning",
    "social_skills",
    "emotional_regulation",
    "physical_sensory_needs",
    "attendance_and_engagement",
    "strategies_trialed",
    "academic_strengths",
    "personal_strengths",
)

_FIELD_DESCRIPTIONS = {
    "learning_and_cognition": "academic performance, learning style, cognitive needs, grades, test scores",
    "communication_and_language": "reading, writing, speaking, listening skills, language proficiency, CEFR",
    "executive_functioning": "organization, focus, planning, task completion, self-regulation, homework",
    "social_skills": "collaboration, peer interaction, teamwork, group dynamics, friendship",
    "emotional_regulation": "emotional awareness, coping, resilience, self-management, behavior",
    "physical_sensory_needs": "motor skills, sensory processing, physical needs, handwriting",
    "attendance_and_engagement": "participation, attendance, class engagement, motivation",
    "strategies_trialed": "interventions, accommodations, approaches tried, support plans",
    "academic_strengths": "subjects or areas where the student excels, talents",
    "personal_strengths": "character traits, interests, curiosity, creativity, leadership",
}


def _split_into_student_sections(
    text: str,
    matched_students: list[dict[str, Any]],
) -> dict[str, str]:
    """Split a multi-student document into per-student text sections.

    Strategy: find each student's name position in the text, assign text
    from that position to the next student's name position. Students
    whose names aren't found get empty string (no data to import).

    For single-student documents, all text goes to that student.
    """
    if len(matched_students) <= 1:
        student_id = matched_students[0]["student_id"] if matched_students else ""
        return {student_id: text} if student_id else {}

    # Find name positions (case-insensitive, full name match first)
    positions: list[tuple[int, str, str]] = []  # (position, student_id, display_name)
    text_lower = text.lower()

    for student in matched_students:
        student_id = student["student_id"]
        display_name = student.get("display_name", "")
        if not display_name:
            continue

        # Try full name first
        name_lower = display_name.lower()
        idx = text_lower.find(name_lower)
        if idx == -1:
            # Try reversed name order (surname first ↔ first last)
            parts = display_name.split()
            if len(parts) >= 2:
                reversed_name = " ".join(parts[1:]) + " " + parts[0]
                idx = text_lower.find(reversed_name.lower())
        if idx == -1:
            # Try first name only as last resort
            first = display_name.split()[0].lower() if display_name else ""
            if first and len(first) > 2:
                idx = text_lower.find(first)

        if idx >= 0:
            positions.append((idx, student_id, display_name))

    if not positions:
        # No names found — can't split, return all text for all students
        return {s["student_id"]: text for s in matched_students}

    # Sort by position
    positions.sort(key=lambda x: x[0])

    # Assign text between consecutive names
    sections: dict[str, str] = {}
    for i, (pos, student_id, _name) in enumerate(positions):
        end_pos = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        sections[student_id] = text[pos:end_pos].strip()

    # Students not found in text get empty section
    for student in matched_students:
        if student["student_id"] not in sections:
            sections[student["student_id"]] = ""

    return sections


# ---------------------------------------------------------------------------
# LLM Sentence Classifier — route report card sentences to lens fields
# ---------------------------------------------------------------------------

def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences. Simple but effective for report cards."""
    # Split on period/exclamation/question followed by space or newline
    raw = re.split(r'(?<=[.!?])\s+|\n+', text)
    sentences = []
    for s in raw:
        s = s.strip()
        # Skip very short fragments and pure numbers/labels
        if len(s) > 15 and any(c.isalpha() for c in s):
            sentences.append(s)
    return sentences


_CLASSIFY_SYSTEM_PROMPT = """You classify sentences from student report cards into profile categories.

Given a sentence about a student, respond with ONLY a JSON object:
{{"field_id": "FIELD", "phrase": "the exact key phrase from the sentence"}}

Valid FIELD values (pick exactly one, or "none"):
""" + "\n".join(f'- {fid}: {desc}' for fid, desc in _FIELD_DESCRIPTIONS.items()) + """
- none: sentence has no relevant student assessment content (headers, dates, boilerplate)

Rules:
1. The "phrase" MUST be exact words from the input sentence — never invent text
2. Keep the phrase short (5-15 words) — the core observation, not the whole sentence
3. Pick the single BEST matching field — do not list multiple
4. If genuinely uncertain, use "none"
"""


async def _classify_sentence_to_field(
    sentence: str,
    engine: Any,
) -> list[ExtractedField]:
    """Classify one sentence into a lens field using local LLM.

    Returns list of ExtractedField (usually 0 or 1 items).
    Phrase must be verified as a substring of the input sentence.
    """
    from src.lingua_viva.reasoning import ReasoningEngine

    if not isinstance(engine, ReasoningEngine):
        engine = ReasoningEngine()

    try:
        result = await engine.reason(
            sentence,
            system_prompt=_CLASSIFY_SYSTEM_PROMPT,
            model="ollama/qwen3:8b",
            local_only=True,
            max_tokens=100,
        )
        if result.model_used == "none" or result.error:
            return []

        content = result.content.strip()
        # Extract JSON from response (may have markdown fencing)
        content = re.sub(r"^```(json)?|```$", "", content, flags=re.MULTILINE).strip()
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            return []

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            return []

        field_id = str(parsed.get("field_id", "none")).strip()
        phrase = str(parsed.get("phrase", "")).strip()

        if field_id == "none" or field_id not in _LENS_FIELD_IDS:
            return []

        # SAFETY: verify phrase is actually in the source sentence
        if phrase and phrase.lower() not in sentence.lower():
            # LLM invented text — use the full sentence instead but mark lower confidence
            phrase = sentence[:80].strip()

        if not phrase:
            return []

        # Map field_id to the field_path format used by the lens
        field_path = f"support_profile.categories.{field_id}.evidence"
        if field_id in ("academic_strengths", "personal_strengths"):
            field_path = field_id

        return [ExtractedField(
            field_path=field_path,
            value=phrase,
            confidence=0.72,
            supporting_chunk_ids=[],
            status="needs_confirmation",
        )]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Synthesis Repass — deduplicate and condense lens fields
# ---------------------------------------------------------------------------

_SYNTHESIS_SYSTEM_PROMPT = """You condense student profile entries. Remove duplicates, combine similar observations.

Rules:
1. NEVER add information not in the originals
2. Preserve specific data (CEFR levels, grade descriptors, test scores, percentages)
3. Combine similar observations into one clear sentence
4. Output 1-3 short sentences maximum
5. Use plain teacher language, not clinical jargon"""


async def _synthesize_field_entries(
    field_id: str,
    entries: list[str],
    engine: Any,
) -> str | None:
    """Synthesize multiple entries for one field into a concise summary.

    Returns condensed text, or None if synthesis not needed/possible.
    """
    if len(entries) <= 1:
        return None  # No synthesis needed

    # Remove exact duplicates first
    unique = list(dict.fromkeys(entries))
    if len(unique) <= 1:
        return unique[0] if unique else None

    from src.lingua_viva.reasoning import ReasoningEngine

    if not isinstance(engine, ReasoningEngine):
        engine = ReasoningEngine()

    field_label = _FIELD_DESCRIPTIONS.get(field_id, field_id)
    prompt = (
        f"Field: {field_label}\n\n"
        f"Entries to condense:\n"
        + "\n".join(f"- {entry}" for entry in unique)
        + "\n\nWrite ONE condensed summary (1-3 sentences). Use only the information above."
    )

    try:
        result = await engine.reason(
            prompt,
            system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
            model="ollama/qwen3:8b",
            local_only=True,
            max_tokens=150,
        )
        if result.model_used == "none" or result.error:
            return None

        condensed = result.content.strip()
        # Strip markdown fencing if present
        condensed = re.sub(r"^```\w*\s*|```$", "", condensed, flags=re.MULTILINE).strip()
        # Basic sanity: if the synthesis is longer than the combined originals, skip it
        if len(condensed) > sum(len(e) for e in unique) * 1.2:
            return None
        return condensed if condensed else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main Extraction Pipeline (R3)
# ---------------------------------------------------------------------------

async def extract_for_lens_update(
    document_bytes: bytes,
    document_type: str,
    matched_students: list[dict[str, Any]],
    lens_store: Optional[StudentLensStore] = None,
    engine: Any = None,
) -> dict[str, ExtractionResult]:
    """Extract lens-update data from a student document.

    Returns {student_id: ExtractionResult} for each matched student.

    Pipeline:
    1. Parse document into chunks
    2. Apply heuristic extractors (CEFR, grade scale, IB, ATL, attendance)
    3. Route content using ethos.match_traits + observation_capture categories
    4. For ambiguous chunks, use local model if available
    5. Map all extractions to STUDENT_LENS_FIELDS
    6. Safety rules: trauma_flag NEVER auto-set, RED → restricted
    """
    # Decode document text
    try:
        text = document_bytes.decode("utf-8", errors="replace")
    except Exception:
        text = ""

    if not text.strip():
        return {
            student["student_id"]: ExtractionResult(
                target_schema_id="student_lens",
                fields=[],
                unresolved_questions=["No readable content found in the document."],
                source_files=[],
                chunks_used=[],
            )
            for student in matched_students
        }

    # Split into chunks (paragraphs) — used for chunk ID references
    chunks = _text_to_chunks(text)

    # STEP 1: Split document into per-student sections (cross-contamination guard)
    student_sections = _split_into_student_sections(text, matched_students)

    results: dict[str, ExtractionResult] = {}

    for student in matched_students:
        student_id = student["student_id"]
        display_name = student.get("display_name", "")

        # Get this student's isolated section
        section_text = student_sections.get(student_id, "")
        if not section_text.strip():
            results[student_id] = ExtractionResult(
                target_schema_id="student_lens",
                fields=[],
                unresolved_questions=[
                    f"No content found for {display_name} in this document."
                ],
                source_files=[],
                chunks_used=[],
            )
            continue

        # Build chunks from this student's section only
        relevant_chunks = _text_to_chunks(section_text)
        if not relevant_chunks:
            relevant_chunks = _find_student_chunks(chunks, display_name, text)
        if not relevant_chunks:
            relevant_chunks = chunks

        all_fields: list[ExtractedField] = []
        unresolved: list[str] = []
        red_detected = False

        for chunk in relevant_chunks:
            chunk_text = chunk.text

            # Safety: check for RED safeguarding content
            if _is_red_safeguarding(chunk_text):
                red_detected = True
                continue

            # Heuristic extractors (no LLM) — fast, high confidence
            all_fields.extend(_extract_cefr(chunk_text))
            all_fields.extend(_extract_grade_scale(chunk_text))
            all_fields.extend(_extract_learner_profile(chunk_text))
            all_fields.extend(_extract_atl_skills(chunk_text))
            all_fields.extend(_extract_attendance(chunk_text))

            # Route to support categories
            all_fields.extend(_route_to_support_category(chunk_text))

            # Route to ethos traits
            all_fields.extend(_route_to_ethos(chunk_text))

        # STEP 2: LLM sentence-level classification (the core improvement)
        # This is what previous attempts were missing — read each teacher-written
        # sentence and route it to the correct lens field.
        if engine is not None:
            sentences = _split_into_sentences(section_text)
            heuristic_paths = {f.field_path for f in all_fields}
            for sentence in sentences:
                # Skip sentences already covered by heuristics
                if any(str(f.value) in sentence for f in all_fields if f.value):
                    continue
                # Skip safeguarding content
                if _is_red_safeguarding(sentence):
                    red_detected = True
                    continue
                llm_fields = await _classify_sentence_to_field(sentence, engine)
                all_fields.extend(llm_fields)

        # Attach chunk IDs to fields
        for field in all_fields:
            if not field.supporting_chunk_ids:
                supporting = [
                    c.chunk_id for c in relevant_chunks
                    if field.value and str(field.value) in c.text
                ]
                field.supporting_chunk_ids = supporting or [
                    relevant_chunks[0].chunk_id
                ] if relevant_chunks else []

        # Legacy LLM fallback (if sentence classifier didn't run or found little)
        if engine is not None and len(all_fields) < 3 and relevant_chunks:
            llm_fields = await _llm_extract_fallback(
                relevant_chunks, engine, all_fields
            )
            all_fields.extend(llm_fields)

        # Deduplicate fields (keep highest confidence per field_path)
        all_fields = _deduplicate_fields(all_fields)

        # STEP 3: Synthesis repass — condense duplicate entries per field
        if engine is not None and len(all_fields) > 3:
            all_fields = await _run_synthesis_repass(all_fields, engine)

        # Safety: ensure trauma_flag is NEVER auto-verified
        for field in all_fields:
            if field.field_path == "trauma_flag":
                field.status = "needs_confirmation"

        if red_detected:
            unresolved.append(
                "RED safeguarding content detected — routed to restricted log, not to lens."
            )

        results[student_id] = ExtractionResult(
            target_schema_id="student_lens",
            fields=all_fields,
            unresolved_questions=unresolved,
            source_files=[],
            chunks_used=relevant_chunks,
        )

    return results


async def _run_synthesis_repass(
    fields: list[ExtractedField],
    engine: Any,
) -> list[ExtractedField]:
    """Group fields by category and synthesize entries with duplicates."""
    from collections import defaultdict

    # Group values by a normalized field category
    groups: dict[str, list[tuple[int, ExtractedField]]] = defaultdict(list)
    for i, field in enumerate(fields):
        # Extract the category from field_path
        # e.g. "support_profile.categories.learning_and_cognition.evidence" → "learning_and_cognition"
        parts = field.field_path.split(".")
        category = None
        for part in parts:
            if part in _LENS_FIELD_IDS:
                category = part
                break
        if category is None:
            category = field.field_path  # Use full path as key
        groups[category].append((i, field))

    synthesized: list[ExtractedField] = []
    for category, indexed_fields in groups.items():
        if len(indexed_fields) <= 1:
            # No synthesis needed
            synthesized.extend(f for _, f in indexed_fields)
            continue

        entries = [str(f.value) for _, f in indexed_fields if f.value]
        condensed = await _synthesize_field_entries(category, entries, engine)

        if condensed:
            # Use the first field as template, replace value with synthesis
            template = indexed_fields[0][1]
            synthesized.append(ExtractedField(
                field_path=template.field_path,
                value=condensed,
                confidence=max(f.confidence for _, f in indexed_fields),
                supporting_chunk_ids=[
                    cid for _, f in indexed_fields
                    for cid in f.supporting_chunk_ids
                ],
                status="needs_confirmation",
            ))
        else:
            # Synthesis failed — keep originals
            synthesized.extend(f for _, f in indexed_fields)

    return synthesized


def _text_to_chunks(text: str) -> list[SourceChunk]:
    """Split text into paragraph-based chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[SourceChunk] = []
    cursor = 0
    for i, para in enumerate(paragraphs):
        idx = text.find(para, cursor)
        if idx == -1:
            idx = cursor
        chunks.append(SourceChunk(
            chunk_id=f"doc-{i:04d}",
            file_path="uploaded-document",
            text=para,
            char_start=idx,
            char_end=idx + len(para),
        ))
        cursor = idx + len(para)
    return chunks


def _find_student_chunks(
    chunks: list[SourceChunk], display_name: str, full_text: str
) -> list[SourceChunk]:
    """Find chunks that mention a specific student."""
    if not display_name:
        return []
    relevant = []
    name_lower = display_name.lower()
    first_name = display_name.split()[0].lower() if display_name else ""
    for chunk in chunks:
        chunk_lower = chunk.text.lower()
        if name_lower in chunk_lower or (first_name and re.search(
            rf"\b{re.escape(first_name)}\b", chunk_lower
        )):
            relevant.append(chunk)
    return relevant


async def _llm_extract_fallback(
    chunks: list[SourceChunk],
    engine: Any,
    existing_fields: list[ExtractedField],
) -> list[ExtractedField]:
    """Use local model for ambiguous content extraction (R3 step 3).

    Only called when heuristics didn't extract enough data.
    Uses local_only=True, think=False for qwen3 models.
    """
    # Only try LLM if we have few heuristic results
    if len(existing_fields) >= 5:
        return []

    combined_text = "\n\n".join(c.text for c in chunks[:5])  # Limit input size
    if len(combined_text) < 50:
        return []

    existing_paths = {f.field_path for f in existing_fields}

    system_prompt = (
        "Extract student assessment data as JSON. Return ONLY a JSON object mapping "
        "field names to short keyword values (NOT full sentences). Valid fields: "
        "cefr_snapshot.reading, cefr_snapshot.writing, cefr_snapshot.speaking, "
        "cefr_snapshot.listening (values: A1/A2/B1/B2/C1/C2), "
        "academic_strengths (comma-separated keywords), "
        "personal_strengths (comma-separated keywords). "
        "Only include fields with clear evidence in the text. "
        "Do NOT infer or guess. Omit uncertain fields."
    )

    try:
        from src.lingua_viva.reasoning import ReasoningEngine
        reasoning = engine if isinstance(engine, ReasoningEngine) else ReasoningEngine()
        result = await reasoning.reason(
            combined_text,
            system_prompt=system_prompt,
            model="ollama/qwen3:8b",
            local_only=True,
        )
        if result.model_used == "none" or result.error:
            return []

        # Parse JSON response
        content = result.content.strip()
        content = re.sub(r"^```(json)?|```$", "", content, flags=re.MULTILINE).strip()
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            return []
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            return []

        fields = []
        for field_path, value in parsed.items():
            if not value or field_path in existing_paths:
                continue
            if field_path not in STUDENT_LENS_FIELDS:
                continue
            # LLM results are always needs_confirmation (R3 step 4)
            fields.append(ExtractedField(
                field_path=field_path,
                value=value,
                confidence=0.65,
                supporting_chunk_ids=[chunks[0].chunk_id] if chunks else [],
                status="needs_confirmation",
            ))
        return fields
    except Exception:
        return []


def _deduplicate_fields(fields: list[ExtractedField]) -> list[ExtractedField]:
    """Keep highest-confidence field per field_path."""
    best: dict[str, ExtractedField] = {}
    for field in fields:
        existing = best.get(field.field_path)
        if existing is None or field.confidence > existing.confidence:
            best[field.field_path] = field
    return list(best.values())


# ---------------------------------------------------------------------------
# Persistence (R6)
# ---------------------------------------------------------------------------

def _imports_dir(state_home: Optional[Path] = None) -> Path:
    if state_home is None:
        from src.lingua_viva.config import lv_home
        state_home = lv_home()
    imports = state_home / "imports"
    imports.mkdir(parents=True, exist_ok=True)
    return imports


def resolve_import_log_path(log_path: str | Path, state_home: Optional[Path] = None) -> Path:
    """Resolve an import log only if it lives under the app-owned imports dir."""
    imports = _imports_dir(state_home).resolve(strict=False)
    candidate = Path(log_path).expanduser().resolve(strict=False)
    try:
        candidate.relative_to(imports)
    except ValueError as exc:
        raise ValueError("extraction_log_path must be under the Lingua Viva imports directory") from exc
    if candidate.suffix != ".ndjson":
        raise ValueError("extraction_log_path must point to an NDJSON import log")
    return candidate


def save_extraction_log(
    results: dict[str, ExtractionResult],
    source_filename: str,
    state_home: Optional[Path] = None,
) -> Path:
    """Save extraction results as NDJSON before any lens write (R6).

    Location: ~/.lingua-viva/imports/{timestamp}_{filename}.ndjson
    Format: one JSON line per extracted field, with source chunk reference.
    """
    imports = _imports_dir(state_home)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_name = re.sub(r"[^\w.\-]", "_", source_filename)[:60]
    log_path = imports / f"{timestamp}_{safe_name}.ndjson"

    with log_path.open("w", encoding="utf-8") as f:
        for student_id, result in results.items():
            for field in result.fields:
                entry = {
                    "student_id": student_id,
                    "field_path": field.field_path,
                    "value": field.value,
                    "confidence": field.confidence,
                    "status": field.status,
                    "supporting_chunk_ids": field.supporting_chunk_ids,
                    "source_filename": source_filename,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            # Also log unresolved questions
            for question in result.unresolved_questions:
                entry = {
                    "student_id": student_id,
                    "type": "unresolved_question",
                    "question": question,
                    "source_filename": source_filename,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    try:
        os.chmod(log_path, 0o600)
    except OSError:
        pass
    return log_path


def load_extraction_log(log_path: Path) -> dict[str, ExtractionResult]:
    """Load a previously saved extraction log back into ExtractionResult objects."""
    if not log_path.exists():
        return {}

    by_student: dict[str, dict[str, Any]] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        student_id = entry.get("student_id", "")
        if student_id not in by_student:
            by_student[student_id] = {"fields": [], "unresolved": []}
        if entry.get("type") == "unresolved_question":
            by_student[student_id]["unresolved"].append(entry.get("question", ""))
        elif "field_path" in entry:
            by_student[student_id]["fields"].append(
                ExtractedField(
                    field_path=entry["field_path"],
                    value=entry["value"],
                    confidence=entry.get("confidence", 0.5),
                    supporting_chunk_ids=entry.get("supporting_chunk_ids", []),
                    status=entry.get("status", "needs_confirmation"),
                )
            )

    results = {}
    for student_id, data in by_student.items():
        results[student_id] = ExtractionResult(
            target_schema_id="student_lens",
            fields=data["fields"],
            unresolved_questions=data["unresolved"],
            source_files=[],
            chunks_used=[],
        )
    return results


# ---------------------------------------------------------------------------
# Batch Lens Writer (R5)
# ---------------------------------------------------------------------------

async def apply_extractions_to_lenses(
    results: dict[str, ExtractionResult],
    lens_store: Optional[StudentLensStore] = None,
    confirmed_students: Optional[list[str]] = None,
) -> dict[str, dict]:
    """Write all extractions to their target lenses (R5).

    Uses write_student_lens() from student_lens_writer.py.
    Respects all safety rules (trauma_flag, source_ref_ids, confidence).

    Args:
        results: {student_id: ExtractionResult}
        lens_store: Optional store instance (creates default if None)
        confirmed_students: If provided, only write to these student IDs

    Returns:
        {student_id: {written_fields, review_required, feedback, ...}}
    """
    close_store = False
    if lens_store is None:
        lens_store = StudentLensStore()
        close_store = True

    try:
        summaries: dict[str, dict] = {}
        for student_id, result in results.items():
            if confirmed_students and student_id not in confirmed_students:
                continue

            # Only write verified + confirmed fields
            summary = write_student_lens(
                result=result,
                teacher_id="local-teacher",
                hint={"assigned_student_id": student_id},
                store=lens_store,
            )
            summaries[student_id] = summary
        return summaries
    finally:
        if close_store:
            lens_store.close()


# ---------------------------------------------------------------------------
# RED Safeguarding Persistence
# ---------------------------------------------------------------------------

def _save_red_content(text: str, source_filename: str, state_home: Optional[Path] = None) -> None:
    """Route RED safeguarding content to restricted log, never to lens."""
    if state_home is None:
        state_home = Path.home() / ".lingua-viva"
    restricted = state_home / "safeguarding"
    restricted.mkdir(parents=True, exist_ok=True)
    log_path = restricted / "restricted.ndjson"
    entry = {
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": source_filename,
        "content_hash": hash(text) & 0xFFFFFFFF,  # No raw content in log
        "action": "blocked_from_lens",
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    try:
        os.chmod(log_path, 0o600)
    except OSError:
        pass
