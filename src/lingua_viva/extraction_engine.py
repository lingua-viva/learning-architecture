"""
Extract+Fill+Verify Engine — SPEC_LV_EXTRACT_FILL_VERIFY_ENGINE_2026-07-22.md

Turns a teacher-confirmed file list into verified structured field values for
one of the two target schemas defined in data_in_contracts.py. Concrete
implementation of that module's `extract()` stub — import `extract` from HERE,
not from data_in_contracts (that module stays a frozen interface reference).

Design invariant, enforced by construction, not just documented: a field can
only reach status="verified" if (a) its value is deterministically grounded —
literally present, or a known lexical variant, in its cited source chunk(s) —
AND (b) a separate LLM call, given only the claimed value and the cited text,
explicitly confirms it. If the local model is unavailable, the LLM check
returns "unsure", which can only ever produce needs_confirmation, never
verified. A missing/misconfigured model degrades recall, never correctness.

trauma_flag is hard-excluded from ever reaching "verified" regardless of what
either check concludes — see NEVER_AUTO_VERIFY and data_in_contracts.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from src.education.document_parser import DocumentParser
from src.lingua_viva.data_in_contracts import (
    CURRICULUM_UNIT_FIELDS,
    STUDENT_LENS_FIELDS,
    ExtractedField,
    ExtractionResult,
    SourceChunk,
)
from src.lingua_viva.reasoning import ReasoningEngine

DEFAULT_MODEL = "ollama/qwen2.5:3b"

CEFR_LEVELS = ("A1", "A1+", "A2", "A2+", "B1", "B1+", "B2", "C1", "C2")

GRADE_LABELS: dict[str, list[str]] = {
    "G1": ["grade 1", "1st grade", "first grade", "prima", " g1 ", " g1."],
    "G2": ["grade 2", "2nd grade", "second grade", "seconda", " g2 ", " g2."],
    "G3": ["grade 3", "3rd grade", "third grade", "terza", " g3 ", " g3."],
    "G4": ["grade 4", "4th grade", "fourth grade", "quarta", " g4 ", " g4."],
    "G5": ["grade 5", "5th grade", "fifth grade", "quinta", " g5 ", " g5."],
}

LANGUAGE_LABELS: dict[str, list[str]] = {
    "it": ["italian", "italiano"],
    "en": ["english", "inglese"],
    "fr": ["french", "francese"],
    "es": ["spanish", "spagnolo"],
    "ar": ["arabic", "arabo"],
}

# See module docstring — this rule is enforced here, not just documented.
NEVER_AUTO_VERIFY = {"trauma_flag"}

EXTRACTION_SYSTEM_PROMPT_STUDENT = (
    "You are extracting facts about ONE student strictly from the teacher's notes "
    "given below. Return ONLY a JSON object (no prose, no markdown code fences) "
    "mapping field names to values. Only include a field if the text explicitly "
    "supports it — never guess or infer beyond what is written; omit anything "
    "uncertain rather than guessing. Valid fields: display_name, campus, "
    "grade_level (one of G1,G2,G3,G4,G5), home_languages (list of ISO codes from "
    "it,en,fr,es,ar), cefr_snapshot (object with any of reading/writing/speaking/"
    "listening, each valued A1,A1+,A2,A2+,B1,B1+,B2,C1,C2), trauma_flag (true/"
    "false, only if the text is explicit about this)."
)

EXTRACTION_SYSTEM_PROMPT_UNIT = (
    "You are extracting curriculum unit metadata strictly from the document text "
    "given below. Return ONLY a JSON object (no prose, no markdown code fences) "
    "mapping field names to values. Only include a field if the text explicitly "
    "supports it. Valid fields: grade (one of G1,G2,G3,G4,G5), title, focus, "
    "cefr_target, materials (list of strings)."
)

VERIFY_SYSTEM_PROMPT = (
    "You are checking whether a specific claimed value is actually supported by "
    "a specific piece of source text. Say 'yes' if the source text states this "
    "value directly or as a clear, unambiguous paraphrase — you do not need an "
    "exact verbatim match, just real support. Say 'no' if the source text "
    "contradicts the value or the value is about something the text doesn't "
    "address. Say 'unsure' only for genuine ambiguity — texts that plausibly "
    "support more than one different answer. Answer with exactly one word: yes, "
    "no, or unsure. Do not explain."
)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_plaintext(path: Path, source_file: str) -> list[SourceChunk]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[SourceChunk] = []
    cursor = 0
    buf: list[str] = []
    buf_start = 0
    for para in paragraphs:
        idx = text.find(para, cursor)
        if idx == -1:
            idx = cursor
        if not buf:
            buf_start = idx
        buf.append(para)
        cursor = idx + len(para)
        if sum(len(p) for p in buf) > 800:
            chunk_text = "\n\n".join(buf)
            chunks.append(SourceChunk(
                chunk_id=f"{path.stem}-{len(chunks):04d}",
                file_path=source_file,
                text=chunk_text,
                char_start=buf_start,
                char_end=cursor,
            ))
            buf = []
    if buf:
        chunk_text = "\n\n".join(buf)
        chunks.append(SourceChunk(
            chunk_id=f"{path.stem}-{len(chunks):04d}",
            file_path=source_file,
            text=chunk_text,
            char_start=buf_start,
            char_end=cursor,
        ))
    return chunks


def _chunk_pdf(path: Path, source_file: str) -> list[SourceChunk]:
    records = DocumentParser().parse(path)
    return [
        SourceChunk(
            chunk_id=rec.chunk_id,
            file_path=source_file,
            text=rec.text,
            char_start=0,
            char_end=len(rec.text),
        )
        for rec in records
    ]


def chunk_file(file_path: str) -> list[SourceChunk]:
    """Format-agnostic dispatch. PDF reuses DocumentParser (heading-based,
    PII-redacted). .txt/.md get a simple paragraph-window chunker — the
    realistic shape of messy teacher notes. Anything else raises ValueError,
    which extract() turns into an unresolved_question rather than a crash."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _chunk_pdf(path, file_path)
    if suffix in (".txt", ".md"):
        return _chunk_plaintext(path, file_path)
    raise ValueError(f"Unsupported file type for extraction: {suffix}")


# ---------------------------------------------------------------------------
# Deterministic candidate proposal + grounding (the safety net)
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    # Keep "+" — CEFR levels ("A2" vs "A2+") are meaningfully different
    # strings and must not collapse to the same normalized form.
    return re.sub(r"[^a-z0-9+]+", " ", str(text).lower()).strip()


def _grounded_in(value, chunk_text: str) -> bool:
    """The hard gate. A value counts as grounded only if it (normalized)
    literally appears in the cited chunk text. Lists ground if every item
    grounds individually."""
    if isinstance(value, list):
        return bool(value) and all(_grounded_in(item, chunk_text) for item in value)
    norm_value = _norm(value)
    if not norm_value:
        return False
    return norm_value in _norm(chunk_text)


def _deterministic_grade(text: str) -> Optional[str]:
    lower = f" {text.lower()} "
    for grade, labels in GRADE_LABELS.items():
        if any(label in lower for label in labels):
            return grade
    return None


def _deterministic_cefr(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    lower = text.lower()
    dims = ("listening", "speaking", "reading", "writing")
    for level in sorted(CEFR_LEVELS, key=len, reverse=True):
        level_l = re.escape(level.lower())
        for dim in dims:
            if dim in found:
                continue
            patterns = [
                rf"{dim}\s*[:\-]?\s*{level_l}\b",
                rf"\b{level_l}\b[^.\n]{{0,25}}\b{dim}\b",
                rf"\b{dim}\b[^.\n]{{0,25}}\b{level_l}\b",
            ]
            if any(re.search(pat, lower) for pat in patterns):
                found[dim] = level
    return found


def _deterministic_languages(text: str) -> list[str]:
    lower = text.lower()
    return [code for code, labels in LANGUAGE_LABELS.items() if any(l in lower for l in labels)]


def _grounded_for_field(field_name: str, value, chunk_text: str) -> bool:
    """Field-aware grounding. Most fields ground on the literal value
    appearing in the text (title, focus, cefr_target, cefr_snapshot.* levels
    like "A2" all DO appear verbatim in real source text). Enum-coded fields
    don't: a grade of "G3" is never spelled "G3" in prose — it's "Grade 3" or
    "terza" — and a language code "it"/"en" is too short a substring to check
    literally without false-positiving on unrelated words ("it" inside
    "kitchen", "en" inside "again"). Those two ground against their known
    label sets instead, same ones _deterministic_grade/_deterministic_languages
    already use — one source of truth for "what counts as evidence of X"."""
    if field_name in ("grade", "grade_level"):
        labels = GRADE_LABELS.get(value, [])
        lower = f" {chunk_text.lower()} "
        return any(label in lower for label in labels)
    if field_name == "home_languages" and isinstance(value, list):
        lower = chunk_text.lower()
        return bool(value) and all(
            any(label in lower for label in LANGUAGE_LABELS.get(code, [])) for code in value
        )
    return _grounded_in(value, chunk_text)


def _find_supporting_chunks(field_name: str, value, chunks: list[SourceChunk]) -> list[str]:
    return [c.chunk_id for c in chunks if _grounded_for_field(field_name, value, c.text)]


def _flatten(proposals: dict) -> dict:
    flat: dict = {}
    if not isinstance(proposals, dict):
        return flat
    for key, value in proposals.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                flat[f"{key}.{sub_key}"] = sub_value
        else:
            flat[key] = value
    return flat


# ---------------------------------------------------------------------------
# LLM extraction proposal
# ---------------------------------------------------------------------------

async def _propose_fields(chunks: list[SourceChunk], target_schema_id: str, hint: Optional[dict]) -> dict:
    combined = "\n\n---\n\n".join(f"[{c.chunk_id}]\n{c.text}" for c in chunks)
    system_prompt = (
        EXTRACTION_SYSTEM_PROMPT_STUDENT if target_schema_id == "student_lens"
        else EXTRACTION_SYSTEM_PROMPT_UNIT
    )
    if hint:
        system_prompt += f"\n\nContext hint (orientation only, not a source of truth): {json.dumps(hint)}"

    engine = ReasoningEngine()
    result = await engine.reason(combined, system_prompt=system_prompt, model=DEFAULT_MODEL)
    if result.model_used == "none":
        return {}
    text = result.content.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    # Models sometimes wrap the object in surrounding prose despite instructions —
    # take the largest {...} span rather than failing outright.
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _display_value(value) -> str:
    """Natural-language form for prompts — a raw Python list repr
    ("['ar']") is a worse prompt than a plain comma-joined string."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


async def _llm_verify_once(field_path: str, value, chunk_text: str) -> str:
    engine = ReasoningEngine()
    query = (
        f"Claimed field: {field_path}\nClaimed value: {_display_value(value)}\n\n"
        f"Source text:\n{chunk_text}\n\n"
        "Does the source text actually support this claimed value?"
    )
    result = await engine.reason(query, system_prompt=VERIFY_SYSTEM_PROMPT, model=DEFAULT_MODEL)
    if result.model_used == "none":
        return "unsure"
    answer = result.content.strip().lower()
    if answer.startswith("yes"):
        return "yes"
    if answer.startswith("no"):
        return "no"
    return "unsure"


async def _llm_verify(field_path: str, value, chunk_text: str) -> str:
    """One retry on 'unsure' — a small local model's yes/no/unsure judgment has
    real sample-to-sample variance; a single retry resolves genuine coin-flips
    without weakening the check itself (still needs an explicit "yes" to ever
    reach "verified" — a second "unsure" or a "no" still doesn't verify)."""
    verdict = await _llm_verify_once(field_path, value, chunk_text)
    if verdict == "unsure":
        verdict = await _llm_verify_once(field_path, value, chunk_text)
    return verdict


async def _verify_field(
    field_path: str, value, supporting_chunk_ids: list[str], chunks_by_id: dict[str, SourceChunk]
) -> str:
    if not supporting_chunk_ids:
        return "unsupported"
    combined_text = "\n\n".join(
        chunks_by_id[cid].text for cid in supporting_chunk_ids if cid in chunks_by_id
    )
    if not _grounded_for_field(field_path, value, combined_text):
        return "unsupported"
    verdict = await _llm_verify(field_path, value, combined_text)
    if verdict == "yes":
        return "verified"
    if verdict == "no":
        return "unsupported"
    return "needs_confirmation"


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def extract(
    files: list[str],
    target_schema_id: str,
    hint: Optional[dict] = None,
) -> ExtractionResult:
    all_chunks: list[SourceChunk] = []
    unresolved: list[str] = []
    for file_path in files:
        try:
            all_chunks.extend(chunk_file(file_path))
        except (FileNotFoundError, ValueError) as exc:
            unresolved.append(f"Could not read {file_path}: {exc}")

    if not all_chunks:
        return ExtractionResult(
            target_schema_id=target_schema_id,
            fields=[],
            unresolved_questions=unresolved or ["No readable content found in the provided files."],
            source_files=list(files),
            chunks_used=[],
        )

    chunks_by_id = {c.chunk_id: c for c in all_chunks}
    field_names = CURRICULUM_UNIT_FIELDS if target_schema_id == "curriculum_unit" else STUDENT_LENS_FIELDS
    combined_text = "\n\n".join(c.text for c in all_chunks)

    proposals = _flatten(await _propose_fields(all_chunks, target_schema_id, hint))

    # Deterministic candidates fill gaps the model missed — never override an
    # LLM proposal, only add what's absent, and only when literally grounded
    # (these are found BY searching the text, so they always ground trivially).
    if target_schema_id == "student_lens":
        det_grade = _deterministic_grade(combined_text)
        if det_grade and "grade_level" not in proposals:
            proposals["grade_level"] = det_grade
        for dim, level in _deterministic_cefr(combined_text).items():
            proposals.setdefault(f"cefr_snapshot.{dim}", level)
        det_langs = _deterministic_languages(combined_text)
        if det_langs and "home_languages" not in proposals:
            proposals["home_languages"] = det_langs
    else:
        det_grade = _deterministic_grade(combined_text)
        if det_grade and "grade" not in proposals:
            proposals["grade"] = det_grade

    fields: list[ExtractedField] = []
    covered = set()
    for field_name, value in proposals.items():
        if field_name not in field_names or value in (None, "", [], {}):
            continue
        covered.add(field_name)
        supporting = _find_supporting_chunks(field_name, value, all_chunks)

        if field_name in NEVER_AUTO_VERIFY:
            # Always surfaced for a human to look at, never silently dropped
            # as "unsupported" and never auto-verified — that's the whole
            # point of this field being hard-excluded. Booleans rarely ground
            # on a literal text match ("True" doesn't appear in prose), so
            # "supporting" being empty is the normal case here, not a signal
            # to hide the field.
            status = "needs_confirmation"
        else:
            status = await _verify_field(field_name, value, supporting, chunks_by_id)

        confidence = {"verified": 0.85, "needs_confirmation": 0.5, "unsupported": 0.2}[status]
        fields.append(ExtractedField(
            field_path=field_name,
            value=value,
            confidence=confidence,
            supporting_chunk_ids=supporting,
            status=status,
        ))

    for field_name in field_names:
        if field_name not in covered:
            unresolved.append(f"No grounded value found for '{field_name}'.")

    return ExtractionResult(
        target_schema_id=target_schema_id,
        fields=fields,
        unresolved_questions=unresolved,
        source_files=list(files),
        chunks_used=all_chunks,
    )
