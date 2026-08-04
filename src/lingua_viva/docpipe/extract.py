"""Grounded document extraction (T3, SPEC_T3_EXTRACTION_2026-08-04).

Two layers:
- a deterministic core that always runs (offline is a supported state):
  normalization with stable character offsets, paragraph spans, structure,
  and student detection — everything is COPIED from the document, never
  generated;
- an optional local-model enrichment pass whose every claim is mechanically
  verified against its cited span by grounding_docs before inclusion.
  Unsupported claims are DROPPED, never demoted (T3 prompt rule).
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Optional

from .contracts import ExtractionRecord, SourceRecord
from .grounding_docs import name_tokens, span_contains_any_token, verify_extraction
from .model import ModelClient

EXTRACTOR_NAME = "docpipe.extract"
EXTRACTOR_VERSION = "1.0"

TEXT_MIMES = {"text/markdown", "text/plain", "text/csv", "text/x-markdown"}
TEXT_EXTS = {".md", ".markdown", ".txt", ".csv"}
PDF_MIMES = {"application/pdf"}

MODEL_STUDENT_CONFIDENCE = 0.7
VERBATIM_STUDENT_CONFIDENCE = 0.99
MODEL_MAX_SPANS = 60

# Capitalized words that are never a person's name in teaching documents.
# Keeps the First-Last bigram detector from inventing students out of
# headings ("Italian Literature") or labels ("Teacher Note").
_NAME_BLOCKLIST = {
    "italian", "english", "french", "spanish", "german", "literature",
    "language", "student", "students", "work", "sample", "task", "date",
    "class", "unit", "teacher", "note", "notes", "learning", "goal",
    "main", "activity", "exit", "ticket", "warm", "up", "poetry",
    "personal", "identity", "voice", "grade", "school", "lesson", "plan",
    "report", "progress", "term", "roster", "list", "level", "reading",
    "writing", "speaking", "listening", "differentiation", "next", "step",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
}

_IT_STOPWORDS = {"il", "la", "che", "di", "e", "un", "una", "per", "con", "del", "della", "gli", "sono"}
_EN_STOPWORDS = {"the", "and", "of", "to", "a", "in", "that", "with", "for", "is", "are", "on"}


async def extract_document(
    source: SourceRecord,
    content: bytes,
    *,
    model_client: ModelClient | None = None,
) -> ExtractionRecord:
    warnings: list[str] = []
    text = _normalize(source, content)
    spans = _build_spans(text)
    structure = _build_structure(text, spans)
    model_used: Optional[str] = None

    if model_client is not None:
        model_used, model_warnings = await _model_enrich_students(
            model_client, spans, structure["students_detected"]
        )
        warnings.extend(model_warnings)
    else:
        warnings.append("model_enrichment_unavailable:no local model client")

    data: dict[str, Any] = {
        "schema_version": "docpipe.extraction.v1",
        "source_id": source.source_id,
        "source_sha256": str(source.data.get("sha256") or ""),
        "extracted_at": _now(),
        "extractor": {
            "name": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "model": model_used,
        },
        "mime": str(source.data.get("mime") or ""),
        "language": _detect_language(text),
        "normalized_text": text,
        "spans": spans,
        "structure": structure,
        "warnings": warnings,
    }
    # The mechanical grounding gate runs INSIDE extraction too (jobs.py runs
    # it again before the vault write): anything unsupported is dropped here
    # so no caller can ever observe an unverified extraction.
    report = verify_extraction(data, apply_drops=True)
    if report.dropped:
        data["warnings"].extend(report.dropped)
    return ExtractionRecord(data)


# --- Normalization (stable offsets — computed once, never re-derived) --------


def _normalize(source: SourceRecord, content: bytes) -> str:
    mime = str(source.data.get("mime") or "").lower()
    ext = str(source.data.get("original_ext") or "").lower()
    if mime in TEXT_MIMES or ext in TEXT_EXTS or mime.startswith("text/"):
        raw = content.decode("utf-8", errors="replace")
    elif mime in PDF_MIMES or ext == ".pdf":
        raw = _pdf_text(content)
    else:
        raise ValueError(
            f"unsupported format for extraction: {mime or ext or 'unknown'} — "
            "supported today: markdown, plain text, csv, pdf"
        )
    return _normalize_text(raw)


def _normalize_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip("\n")
    return text + "\n\n" if text else ""


def _pdf_text(content: bytes) -> str:
    import io

    try:
        import pdfplumber
    except ImportError as error:
        raise ValueError(
            "PDF support is not available on this computer (pdfplumber missing)"
        ) from error
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\n\n".join(page for page in pages if page.strip())
    if not text.strip():
        raise ValueError("no extractable text found in this PDF")
    return text


# --- Spans -------------------------------------------------------------------


def _build_spans(text: str) -> list[dict[str, Any]]:
    """Paragraph spans. text == normalized_text[start:end] holds by
    construction: spans are slices of the canonical string."""
    spans: list[dict[str, Any]] = []
    index = 0
    cursor = 0
    length = len(text)
    while cursor < length:
        while cursor < length and text[cursor] == "\n":
            cursor += 1
        if cursor >= length:
            break
        end = text.find("\n\n", cursor)
        if end == -1:
            end = length
        block = text[cursor:end]
        stripped_end = cursor + len(block.rstrip("\n"))
        if text[cursor:stripped_end].strip():
            index += 1
            spans.append({
                "span_id": f"SPN-{index:04d}",
                "char_start": cursor,
                "char_end": stripped_end,
                "text": text[cursor:stripped_end],
            })
        cursor = end
    return spans


# --- Structure ---------------------------------------------------------------


def _build_structure(text: str, spans: list[dict[str, Any]]) -> dict[str, Any]:
    title = _detect_title(spans)
    students = _detect_students(spans)
    document_type = _detect_document_type(spans, students)
    sections = _build_sections(spans, document_type, title)
    structure: dict[str, Any] = {
        "title": title,
        "document_type": document_type,
        "sections": sections,
        "students_detected": students,
    }
    curriculum = _detect_curriculum(spans)
    if curriculum:
        structure["curriculum"] = curriculum
    return structure


def _detect_title(spans: list[dict[str, Any]]) -> Optional[str]:
    if not spans:
        return None
    first = str(spans[0]["text"]).split("\n")[0]
    if first.startswith("#"):
        return first.lstrip("#").strip()
    if len(first) <= 100 and not first.endswith((".", ":")):
        return first.strip()
    return None


def _labeled_value(span_text: str, label: str) -> Optional[str]:
    for line in span_text.split("\n"):
        if line.lower().startswith(label.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return None


def _detect_document_type(spans: list[dict[str, Any]], students: list[dict[str, Any]]) -> str:
    joined = " ".join(str(s["text"]).lower() for s in spans)
    if ("roster" in joined or "class list" in joined) and len(students) >= 3:
        return "roster"
    if any(k in joined for k in ("learning goal", "warm-up", "warm up", "main activity", "differentiation")):
        return "lesson_plan"
    if "work sample" in joined or ("task:" in joined and students):
        return "student_work_sample"
    if any(k in joined for k in ("criterion", "descriptor", "rubric", "band ")):
        return "rubric"
    if "progress report" in joined or "term report" in joined:
        return "report"
    return "unknown"


def _build_sections(
    spans: list[dict[str, Any]],
    document_type: str,
    title: Optional[str],
) -> list[dict[str, Any]]:
    if not spans:
        return []
    title_span_ids = {spans[0]["span_id"]} if title else set()
    meta_ids: list[str] = []
    differentiation_ids: list[str] = []
    task_ids: list[str] = []
    teacher_note_ids: list[str] = []
    flow_ids: list[str] = []
    prose_ids: list[str] = []
    for span in spans:
        sid = span["span_id"]
        if sid in title_span_ids:
            continue
        text = str(span["text"])
        lower = text.lower()
        if _labeled_value(text, "Class") is not None:
            meta_ids.append(sid)
        elif lower.startswith("differentiation"):
            differentiation_ids.append(sid)
        elif _labeled_value(text, "Task") is not None:
            task_ids.append(sid)
        elif lower.startswith("teacher note"):
            teacher_note_ids.append(sid)
        elif document_type == "lesson_plan":
            flow_ids.append(sid)
        else:
            prose_ids.append(sid)
    sections: list[dict[str, Any]] = []
    if meta_ids:
        sections.append({"section_id": "lesson-meta", "heading": "Class, date, unit", "span_ids": meta_ids})
    if task_ids:
        sections.append({"section_id": "task", "heading": "Task", "span_ids": task_ids})
    if flow_ids:
        sections.append({"section_id": "lesson-flow", "heading": "Lesson flow", "span_ids": flow_ids})
    if prose_ids:
        sections.append({"section_id": "student-response", "heading": "Student response", "span_ids": prose_ids})
    if differentiation_ids:
        sections.append({"section_id": "differentiation", "heading": "Differentiation notes", "span_ids": differentiation_ids})
    if teacher_note_ids:
        sections.append({"section_id": "teacher-note", "heading": "Teacher note", "span_ids": teacher_note_ids})
    return sections


def _detect_curriculum(spans: list[dict[str, Any]]) -> dict[str, Any]:
    curriculum: dict[str, Any] = {}
    for span in spans:
        text = str(span["text"])
        class_value = _labeled_value(text, "Class")
        if class_value and "grade" not in curriculum and "subject" not in curriculum:
            parts = class_value.split(None, 1)
            if parts and re.fullmatch(r"(MYP\d{1,2}|PYP\d{1,2}|DP\d?|G\d{1,2})", parts[0]):
                curriculum["grade"] = parts[0]
                if len(parts) > 1:
                    curriculum["subject"] = parts[1]
            else:
                curriculum["subject"] = class_value
        unit_value = _labeled_value(text, "Unit")
        if unit_value and "unit" not in curriculum:
            curriculum["unit"] = unit_value
        task_value = _labeled_value(text, "Task")
        if task_value and "task" not in curriculum:
            curriculum["task"] = task_value
    return curriculum


def _detect_language(text: str) -> str:
    words = re.findall(r"[a-zà-ù]+", text.lower())
    it_hits = sum(1 for w in words if w in _IT_STOPWORDS)
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
    return "it" if it_hits > en_hits else "en"


# --- Student detection (deterministic) ---------------------------------------


def _slug(name: str) -> str:
    folded = "".join(
        ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch)
    )
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


_NAME_BIGRAM = re.compile(r"\b([A-ZÀ-Þ][a-zà-ÿ]+)\s+([A-ZÀ-Þ][a-zà-ÿ]+)\b")


def _detect_students(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for span in spans:
        text = str(span["text"])
        for match in _NAME_BIGRAM.finditer(text):
            first, last = match.group(1), match.group(2)
            if first.lower() in _NAME_BLOCKLIST or last.lower() in _NAME_BLOCKLIST:
                continue
            display_name = f"{first} {last}"
            student_id = f"student-{_slug(display_name)}"
            if student_id not in found:
                found[student_id] = {
                    "student_id": student_id,
                    "display_name": display_name,
                    "confidence": VERBATIM_STUDENT_CONFIDENCE,
                    "span_ids": [],
                }
                order.append(student_id)
    # Span membership: full name OR first name as a whole word.
    for student_id in order:
        student = found[student_id]
        first_name = student["display_name"].split()[0]
        for span in spans:
            text = str(span["text"])
            if student["display_name"] in text or re.search(
                rf"\b{re.escape(first_name)}\b", text
            ):
                student["span_ids"].append(span["span_id"])
    return [found[student_id] for student_id in order]


# --- Model enrichment (optional, verified, drop-on-failure) ------------------


_MODEL_SYSTEM_PROMPT = (
    "You identify student names in a teaching document. Reply with STRICT "
    'JSON only, exactly: {"students": [{"display_name": "First Last", '
    '"span_id": "SPN-0001"}]} . Only include real student names that '
    "appear verbatim inside the cited span. If there are none, reply "
    '{"students": []}. No prose, no markdown fences.'
)


async def _model_enrich_students(
    model_client: ModelClient,
    spans: list[dict[str, Any]],
    students: list[dict[str, Any]],
) -> tuple[Optional[str], list[str]]:
    warnings: list[str] = []
    prompt_spans = spans[:MODEL_MAX_SPANS]
    if len(spans) > MODEL_MAX_SPANS:
        warnings.append(f"model_enrichment_truncated:{len(spans) - MODEL_MAX_SPANS} spans not sent")
    prompt = "Spans:\n" + "\n".join(
        f"[{span['span_id']}] {str(span['text'])[:500]}" for span in prompt_spans
    )
    model_used: Optional[str] = None
    parsed: Optional[dict[str, Any]] = None
    for attempt in range(2):
        try:
            result = await model_client.complete(
                prompt if attempt == 0 else prompt + "\n\nReply with the JSON object ONLY.",
                system_prompt=_MODEL_SYSTEM_PROMPT,
                max_tokens=500,
            )
        except Exception as error:
            warnings.append(f"model_enrichment_unavailable:{str(error)[:120]}")
            return None, warnings
        model_used = result.model_used or model_used
        if result.error:
            warnings.append(f"model_enrichment_unavailable:{result.error}")
            return (model_used if model_used not in (None, "none") else None), warnings
        parsed = _parse_model_json(result.content)
        if parsed is not None:
            break
    if parsed is None:
        warnings.append("model_enrichment_discarded:invalid JSON after retry")
        return model_used, warnings

    known_ids = {student["student_id"] for student in students}
    span_by_id = {span["span_id"]: span for span in spans}
    for claim in parsed.get("students", []):
        if not isinstance(claim, dict):
            continue
        display_name = str(claim.get("display_name") or "").strip()
        span_id = str(claim.get("span_id") or "").strip()
        span = span_by_id.get(span_id)
        if not display_name or span is None:
            warnings.append(
                f"grounding_dropped:model_student:{display_name or '?'}:span {span_id or '?'} does not exist"
            )
            continue
        tokens = name_tokens(display_name)
        # The mechanical support rule: every name token must appear in the
        # cited span. Fails → DROPPED, never demoted.
        if not tokens or not all(
            span_contains_any_token(str(span["text"]), [token]) for token in tokens
        ):
            warnings.append(
                f"grounding_dropped:model_student:{display_name}:cited span {span_id} does not contain the name"
            )
            continue
        student_id = f"student-{_slug(display_name)}"
        if student_id in known_ids:
            continue
        known_ids.add(student_id)
        first_name = display_name.split()[0]
        span_ids = [
            candidate["span_id"]
            for candidate in spans
            if display_name in str(candidate["text"])
            or re.search(rf"\b{re.escape(first_name)}\b", str(candidate["text"]))
        ]
        students.append({
            "student_id": student_id,
            "display_name": display_name,
            "confidence": MODEL_STUDENT_CONFIDENCE,
            "span_ids": span_ids or [span_id],
        })
    return model_used, warnings


def _parse_model_json(content: str) -> Optional[dict[str, Any]]:
    """Hardened JSON parse (observe/classify lessons): strip fences, take the
    first balanced object only, discard on invalid."""
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                try:
                    candidate = json.loads(text[start:index + 1])
                except json.JSONDecodeError:
                    return None
                return candidate if isinstance(candidate, dict) else None
    return None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
