"""Per-class coursework pack assembly (W3, 2026-08-09).

Builds a real coursework pack for a class/grade from the structures the
app already owns:

- curriculum.CurriculumService → units per grade (title, focus, CEFR
  wording, Manuale citation)
- src.education.content_differentiator.ContentDifferentiator → three
  CEFR-tier variants of every activity (deterministic, no LLM, no egress)
- knowledge/education/*.yaml → evidence-tiered teacher background reading
  matched to the unit (fail-soft: pack builds fine without it)

Two editions from one master structure:
- teacher pack: everything, including answer keys, teacher notes and
  background reading
- student pack: activities + tier instructions ONLY — ``student_view``
  strips answer keys/notes, and pdf_generator refuses to render them for
  the student audience anyway (defense in depth).

Where curriculum data is thin, activities are honest scaffolds generated
from the unit's topic + language objectives and are labeled
"draft — teacher review required" in the PDF.

Output PDFs land under <LV_STATE_HOME>/artifacts/coursework/.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from src.lingua_viva.curriculum import CurriculumService
from src.lingua_viva.pdf_generator import artifacts_dir, render_coursework_pack_pdf
from src.education.content_differentiator import (
    CEFR_ORDER,
    ContentDifferentiator,
    LessonInput,
)

_KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "education"

DRAFT_LABEL = "draft — teacher review required"

# Deterministic activity scaffolds cycled per unit. Each produces a real,
# runnable classroom activity from the unit topic; the differentiator then
# tiers it. All are auto-generated content → always labeled DRAFT.
_ACTIVITY_TEMPLATES: tuple[dict, ...] = (
    {
        "kind": "vocabolario",
        "title": "Vocabolario in contesto — {topic}",
        "instructions": (
            "Students collect and use key words for \"{topic}\". Introduce each "
            "term with a gesture or image, then students use it in one spoken "
            "and one written sentence of their own."
        ),
        "duration_minutes": 20,
        "answer_key": [
            "Accept any sentence that uses the target term accurately in context.",
            "Key terms to check: {terms}.",
            "Common error to watch: article/gender agreement with new nouns.",
        ],
        "teacher_notes": [
            "Pre-teach terms with visuals for foundational-tier students.",
            "Extended-tier students should also define each term in Italian.",
        ],
    },
    {
        "kind": "lettura",
        "title": "Lettura guidata — {topic}",
        "instructions": (
            "Guided reading on \"{topic}\". Read the tier text together, then "
            "students answer the comprehension prompts for their tier and mark "
            "one sentence they found difficult."
        ),
        "duration_minutes": 25,
        "answer_key": [
            "Comprehension answers must cite where in the text the answer appears.",
            "Foundational tier: pointing to the correct sentence counts as a full answer.",
            "Extended tier: answers should include one inference beyond the literal text.",
        ],
        "teacher_notes": [
            "Chunk the text: foundational reads the first sentences only.",
            "Pair a stronger reader with each foundational-tier reader for the second pass.",
        ],
    },
    {
        "kind": "produzione",
        "title": "Produzione — {topic}",
        "instructions": (
            "Production task on \"{topic}\". Students produce their tier's "
            "output (label, sentences, or short paragraph) and present one "
            "line of it aloud to a partner."
        ),
        "duration_minutes": 25,
        "answer_key": [
            "Foundational: 1-3 labeled items or single sentences; meaning over accuracy.",
            "On track: 3-4 connected sentences with at least one linking word.",
            "Extended: a short structured paragraph with an opinion and a reason.",
        ],
        "teacher_notes": [
            "Collect one sample per tier for the unit portfolio.",
            "Use the presentation line as a quick speaking check (no grade).",
        ],
    },
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:60] or "pack"


def _cefr_from_wording(wording: str) -> str:
    """Extract a concrete CEFR band from matrix wording like
    'designed to target A2 consolidation'. Defaults to A2 (mid-primary)."""
    for band in sorted(CEFR_ORDER, key=len, reverse=True):  # match A1+ before A1
        if re.search(rf"(?<![A-Za-z0-9+]){re.escape(band)}(?![0-9+])", str(wording or "")):
            return band
    return "A2"


def _key_terms_from_unit(unit: dict) -> list[str]:
    words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\-]+", f"{unit.get('title', '')} {unit.get('focus', '')}")
    seen: list[str] = []
    for word in words:
        low = word.lower()
        if len(low) < 4 or low in ("with", "from", "della", "delle", "degli", "con", "per"):
            continue
        if low not in [s.lower() for s in seen]:
            seen.append(word)
    return seen[:5]


def _background_reading(unit: dict, max_entries: int = 3) -> list[dict]:
    """Match knowledge/education entries to the unit by tag/title word
    overlap. Fail-soft: any error returns [] — a missing knowledge library
    must never block a pack."""
    try:
        unit_words = {
            w.lower()
            for w in re.findall(r"[A-Za-z]+", f"{unit.get('title', '')} {unit.get('focus', '')} "
                                              f"{unit.get('cefr_target', '')} CEFR IB PYP")
            if len(w) >= 3
        }
        scored: list[tuple[int, dict]] = []
        for path in sorted(_KNOWLEDGE_DIR.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for entry in data.get("entries", []) or []:
                if not isinstance(entry, dict) or not entry.get("verified"):
                    continue
                entry_words = {
                    w.lower()
                    for w in re.findall(
                        r"[A-Za-z]+",
                        f"{entry.get('title', '')} {' '.join(entry.get('tags', []) or [])}",
                    )
                }
                score = len(unit_words & entry_words)
                if score > 0:
                    scored.append((score, entry))
        scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("id", ""))))
        return [
            {
                "title": entry.get("title", ""),
                "citation": "; ".join(entry.get("citations", []) or []),
                "knowledge_id": entry.get("id", ""),
            }
            for _score, entry in scored[:max_entries]
        ]
    except Exception:
        return []


def _build_activity(index: int, unit: dict, cefr_target: str, differentiator: ContentDifferentiator) -> dict:
    template = _ACTIVITY_TEMPLATES[index % len(_ACTIVITY_TEMPLATES)]
    topic = unit.get("title", "the unit topic")
    terms = _key_terms_from_unit(unit)

    lesson = LessonInput(
        ib_programme="PYP",
        subject="Italian Language",
        unit_title=unit.get("title", ""),
        topic=topic,
        atl_skills=["Communication"],
        cefr_target=cefr_target,
        duration_minutes=template["duration_minutes"],
    )
    content_pack = differentiator.generate(lesson)

    return {
        "activity_id": f"{unit.get('unit_id', 'unit')}-act-{index + 1}",
        "kind": template["kind"],
        "title": template["title"].format(topic=topic),
        "instructions": template["instructions"].format(topic=topic),
        "duration_minutes": template["duration_minutes"],
        "draft": True,  # honest label: auto-generated scaffold
        "tiers": content_pack.tiers,
        "answer_key": [
            line.format(topic=topic, terms=", ".join(terms) or "unit vocabulary")
            for line in template["answer_key"]
        ],
        "teacher_notes": list(template["teacher_notes"]),
    }


def build_pack(
    class_ref: str,
    *,
    unit_id: Optional[str] = None,
    activities_per_unit: int = 3,
    matrix_path: Optional[Path | str] = None,
) -> dict:
    """Assemble the master (teacher-audience) coursework pack structure.

    ``class_ref``: a grade/class identifier CurriculumService understands
    ("G3", "3", "Grade 3"). ``unit_id`` limits the pack to one unit.
    Raises KeyError when the grade has no units or the unit is unknown.
    """
    service = CurriculumService(matrix_path=matrix_path)
    units = service.get_grade(class_ref)
    if unit_id:
        units = [u for u in units if u.get("unit_id") == unit_id]
    if not units:
        raise KeyError(f"no curriculum units found for class {class_ref!r}"
                       + (f" unit {unit_id!r}" if unit_id else ""))

    grade = units[0].get("grade", str(class_ref))
    differentiator = ContentDifferentiator()
    activities_per_unit = max(1, min(int(activities_per_unit), len(_ACTIVITY_TEMPLATES) * 2))

    pack_units = []
    for unit in units:
        cefr_target = _cefr_from_wording(unit.get("cefr_target", ""))
        activities = [
            _build_activity(i, unit, cefr_target, differentiator)
            for i in range(activities_per_unit)
        ]
        pack_units.append({
            "unit_id": unit.get("unit_id", ""),
            "title": unit.get("title", ""),
            "focus": unit.get("focus", ""),
            "cefr_target": cefr_target,
            "cefr_language": unit.get("cefr_language", ""),
            "manuale_section": unit.get("manuale_section", ""),
            "source_citation": unit.get("source_citation", ""),
            "overview": (
                f"This unit develops \"{unit.get('title', '')}\" — {unit.get('focus', '')} "
                f"Activities are tiered (foundational / on track / extended) so every "
                f"student works on the same concept at an accessible level."
            ),
            "activities": activities,
            "background_reading": _background_reading(unit),
        })

    focus = units[0].get("focus", "Italian language development")
    return {
        "pack_id": f"cwp-{_safe_slug(grade)}-{uuid.uuid4().hex[:8]}",
        "generated_at": _now_iso(),
        "audience": "teacher",
        "class_ref": {"grade": grade, "unit_id": unit_id},
        "cover": {
            "title": f"Grade {grade.removeprefix('G')} Italian coursework",
            "grade": grade,
            "focus": focus,
            "unit_count": len(pack_units),
        },
        "units": pack_units,
    }


_TEACHER_ONLY_ACTIVITY_KEYS = ("answer_key", "teacher_notes")
_TEACHER_ONLY_UNIT_KEYS = ("background_reading", "source_citation")


def student_view(pack: dict) -> dict:
    """Derive the student-safe edition: no answer keys, no teacher notes,
    no background reading, no draft flags. Never mutates the input."""
    student = {k: v for k, v in pack.items() if k != "units"}
    student["audience"] = "student"
    student_units = []
    for unit in pack.get("units", []):
        unit_copy = {k: v for k, v in unit.items()
                     if k not in _TEACHER_ONLY_UNIT_KEYS and k != "activities"}
        unit_copy["activities"] = [
            {k: v for k, v in activity.items()
             if k not in _TEACHER_ONLY_ACTIVITY_KEYS and k != "draft"}
            for activity in unit.get("activities", [])
        ]
        student_units.append(unit_copy)
    student["units"] = student_units
    return student


def generate_class_pack(
    class_ref: str,
    *,
    unit_id: Optional[str] = None,
    activities_per_unit: int = 3,
    include_student_version: bool = True,
    matrix_path: Optional[Path | str] = None,
    output_dir: Optional[Path | str] = None,
) -> dict:
    """Build the pack and write teacher (+ optional student) PDFs.

    Default output: <LV_STATE_HOME>/artifacts/coursework/. Returns metadata
    including generated file paths.
    """
    pack = build_pack(
        class_ref,
        unit_id=unit_id,
        activities_per_unit=activities_per_unit,
        matrix_path=matrix_path,
    )
    out_dir = Path(output_dir) if output_dir else artifacts_dir("coursework")
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_slug(f"{pack['cover']['grade']}-{unit_id or 'all-units'}")
    files: list[dict] = []

    teacher_path = out_dir / f"{stem}_{pack['pack_id']}_teacher.pdf"
    render_coursework_pack_pdf(pack, output_path=teacher_path)
    files.append({"audience": "teacher", "path": str(teacher_path),
                  "bytes": teacher_path.stat().st_size})

    if include_student_version:
        student_pack = student_view(pack)
        student_path = out_dir / f"{stem}_{pack['pack_id']}_student.pdf"
        render_coursework_pack_pdf(student_pack, output_path=student_path)
        files.append({"audience": "student", "path": str(student_path),
                      "bytes": student_path.stat().st_size})

    return {
        "pack_id": pack["pack_id"],
        "generated_at": pack["generated_at"],
        "grade": pack["cover"]["grade"],
        "unit_id": unit_id,
        "unit_count": pack["cover"]["unit_count"],
        "activities_per_unit": activities_per_unit,
        "files": files,
    }
