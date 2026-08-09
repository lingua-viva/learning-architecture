"""PDF artifact rendering layer (W3, 2026-08-09).

One small, reusable reportlab layer for every teacher-visible PDF the app
produces: lesson material packets, parent reports, and per-class coursework
packs. All layout code lives HERE so feature modules only assemble
structured dicts.

Constraints honored:
- Zero egress: built-in Helvetica/Times only — reportlab never fetches a
  font at runtime because we never register a TTF.
- Publication policy: branding is the generic product name "Lingua Viva";
  no institution name appears anywhere in this module. Callers are
  responsible for keeping student-identifying content out of student- and
  parent-facing payloads (parent_report.py already strips those upstream).
- Runtime state: default output locations resolve under LV_STATE_HOME
  (same convention as runtime_paths.py) — never a source-tree path.

API: each ``render_*_pdf`` takes the structured dict(s) the existing
modules produce and either returns raw PDF bytes (``output_path=None``)
or writes the file and returns the ``Path``.
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BRAND = "Lingua Viva"
FOOTER_NOTE = "Generated locally by Lingua Viva — no data left this device."

_BRAND_COLOR = colors.HexColor("#1a5276")
_ACCENT_COLOR = colors.HexColor("#7f8c8d")


def state_home() -> Path:
    """Resolve the app state home (LV_STATE_HOME convention)."""
    return Path(os.environ.get("LV_STATE_HOME") or Path.home() / ".lingua-viva")


def artifacts_dir(kind: str = "") -> Path:
    """Sanctioned output directory for generated PDF artifacts."""
    base = state_home() / "artifacts"
    if kind:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in kind)
        base = base / (safe or "misc")
    base.mkdir(parents=True, exist_ok=True)
    return base


# ── Styles ────────────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "LVBrand", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9, textColor=_BRAND_COLOR,
        ),
        "title": ParagraphStyle(
            "LVTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=18, textColor=_BRAND_COLOR, spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "LVMeta", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8.5, textColor=_ACCENT_COLOR, spaceAfter=6,
        ),
        "heading": ParagraphStyle(
            "LVHeading", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12.5, textColor=_BRAND_COLOR, spaceBefore=10, spaceAfter=4,
        ),
        "subheading": ParagraphStyle(
            "LVSubheading", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=10.5, spaceBefore=6, spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "LVBody", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, leading=13.5, spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "LVBullet", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, leading=13.5, leftIndent=10 * mm, bulletIndent=5 * mm,
            spaceAfter=2,
        ),
        "note": ParagraphStyle(
            "LVNote", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8.5, textColor=_ACCENT_COLOR, spaceAfter=4,
        ),
        "cover": ParagraphStyle(
            "LVCover", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=24, textColor=_BRAND_COLOR, alignment=TA_CENTER,
            spaceBefore=60, spaceAfter=10,
        ),
        "cover_sub": ParagraphStyle(
            "LVCoverSub", parent=base["Normal"], fontName="Helvetica",
            fontSize=12, alignment=TA_CENTER, textColor=_ACCENT_COLOR,
            spaceAfter=6,
        ),
    }


def _escape(text: Any) -> str:
    """Minimal XML escaping for Paragraph markup safety."""
    return (
        str(text if text is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(_ACCENT_COLOR)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    canvas.drawString(18 * mm, 12 * mm, f"{FOOTER_NOTE}  ·  {generated}")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _table_flowable(table_spec: dict, styles: dict) -> Table:
    header = [Paragraph(f"<b>{_escape(h)}</b>", styles["body"]) for h in table_spec.get("header", [])]
    rows = [
        [Paragraph(_escape(cell), styles["body"]) for cell in row]
        for row in table_spec.get("rows", [])
    ]
    data = ([header] if header else []) + rows
    if not data:
        data = [[Paragraph("—", styles["body"])]]
    table = Table(data, hAlign="LEFT", colWidths=table_spec.get("col_widths"))
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5d8dc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2f8")))
    table.setStyle(TableStyle(style))
    return table


def _section_flowables(section: dict, styles: dict) -> list:
    """One body section → flowables.

    Section shape (all keys optional):
      {"heading", "subheading", "paragraphs": [str], "bullets": [str],
       "table": {"header": [...], "rows": [[...]]}, "note": str,
       "page_break_before": bool}
    """
    out: list = []
    if section.get("page_break_before"):
        out.append(PageBreak())
    if section.get("heading"):
        out.append(Paragraph(_escape(section["heading"]), styles["heading"]))
    if section.get("subheading"):
        out.append(Paragraph(_escape(section["subheading"]), styles["subheading"]))
    for para in section.get("paragraphs", []) or []:
        out.append(Paragraph(_escape(para), styles["body"]))
    for bullet in section.get("bullets", []) or []:
        out.append(Paragraph(_escape(bullet), styles["bullet"], bulletText="•"))
    if section.get("table"):
        out.append(Spacer(1, 2 * mm))
        out.append(_table_flowable(section["table"], styles))
        out.append(Spacer(1, 2 * mm))
    if section.get("note"):
        out.append(Paragraph(_escape(section["note"]), styles["note"]))
    return out


def render_document(
    *,
    title: str,
    metadata: Optional[dict] = None,
    sections: Optional[list[dict]] = None,
    cover: Optional[dict] = None,
    output_path: Optional[Path | str] = None,
) -> bytes | Path:
    """Core renderer: branded header, title, metadata line, body sections,
    footer with generation date + local-generation note.

    ``cover`` (optional): {"title", "subtitle_lines": [str]} — rendered as a
    standalone cover page before the body.
    Returns bytes when ``output_path`` is None, else writes and returns Path.
    """
    styles = _styles()
    story: list = []

    if cover:
        story.append(Paragraph(_escape(BRAND), styles["brand"]))
        story.append(Paragraph(_escape(cover.get("title", title)), styles["cover"]))
        for line in cover.get("subtitle_lines", []) or []:
            story.append(Paragraph(_escape(line), styles["cover_sub"]))
        story.append(PageBreak())

    story.append(Paragraph(_escape(BRAND), styles["brand"]))
    story.append(HRFlowable(width="100%", thickness=0.7, color=_BRAND_COLOR, spaceAfter=4))
    story.append(Paragraph(_escape(title), styles["title"]))

    metadata = metadata or {}
    if metadata:
        meta_line = "  ·  ".join(
            f"{_escape(k)}: {_escape(v)}" for k, v in metadata.items() if v not in (None, "")
        )
        if meta_line:
            story.append(Paragraph(meta_line, styles["meta"]))
    story.append(Spacer(1, 3 * mm))

    for section in sections or []:
        story.extend(_section_flowables(section, styles))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=title,
        author=BRAND,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    pdf_bytes = buffer.getvalue()

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf_bytes)
        return path
    return pdf_bytes


# ── Feature renderers ─────────────────────────────────────────────────────

def render_lesson_pdf(
    lesson: dict,
    materials: list[dict],
    output_path: Optional[Path | str] = None,
) -> bytes | Path:
    """Render a differentiated lesson packet.

    ``lesson``: dict with subject / unit_title / topic / cefr_target /
    duration_minutes (the LessonInput shape from lesson_materials.py or
    content_differentiator.py, as a dict).
    ``materials``: list of tier dicts — accepts either lesson_materials
    TierMaterial dicts (title/instructions_for_student/exercise_body/
    scaffolding/teacher_note) or differentiator tier dicts
    (learning_objective/tasks/vocabulary_list).
    """
    sections: list[dict] = []
    for material in materials:
        tier = str(material.get("tier", "")).replace("_", " ").title()
        section: dict = {
            "heading": f"{tier} tier" if tier else "Material",
            "subheading": material.get("title", ""),
            "paragraphs": [],
            "bullets": [],
        }
        if material.get("learning_objective"):
            section["paragraphs"].append(f"Objective: {material['learning_objective']}")
        if material.get("cefr_target"):
            section["paragraphs"].append(f"CEFR target: {material['cefr_target']}")
        if material.get("instructions_for_student"):
            section["paragraphs"].append(material["instructions_for_student"])
        if material.get("exercise_body"):
            section["paragraphs"].append(material["exercise_body"])
        for task in material.get("tasks", []) or []:
            section["bullets"].append(
                f"[{task.get('type', 'task')} · {task.get('chunk_minutes', '?')} min] "
                f"{task.get('prompt', '')}"
            )
        vocab = [v.get("term", "") for v in material.get("vocabulary_list", []) or []]
        if vocab:
            section["bullets"].append("Key vocabulary: " + ", ".join(v for v in vocab if v))
        for item in material.get("scaffolding", []) or []:
            section["bullets"].append(f"Scaffold: {item}")
        if material.get("teacher_note"):
            section["note"] = f"Teacher note: {material['teacher_note']}"
        sections.append(section)

    return render_document(
        title=f"Lesson materials — {lesson.get('unit_title') or lesson.get('topic', 'Lesson')}",
        metadata={
            "Subject": lesson.get("subject", ""),
            "Topic": lesson.get("topic", ""),
            "CEFR target": lesson.get("cefr_target", ""),
            "Duration": f"{lesson.get('duration_minutes', '')} min" if lesson.get("duration_minutes") else "",
            "Status": "DRAFT — teacher review required",
        },
        sections=sections,
        output_path=output_path,
    )


def render_parent_report_pdf(
    report: dict,
    output_path: Optional[Path | str] = None,
) -> bytes | Path:
    """Render a parent-facing report from a ParentArtifact-shaped dict
    (subject_line / body / home_activities / from_label / language).

    Privacy: this renderer only ever sees the already-stripped parent
    artifact from parent_report.py — never the internal draft. It adds no
    fields of its own.
    """
    sections: list[dict] = [{"paragraphs": [report.get("body", "")]}]
    activities = report.get("home_activities", []) or []
    if activities:
        sections.append({
            "heading": "A few things you could try at home",
            "bullets": list(activities),
        })
    if report.get("from_label"):
        sections.append({"paragraphs": [f"— {report['from_label']}"]})

    return render_document(
        title=report.get("subject_line", "A note from class"),
        metadata={"Language": report.get("language", "")},
        sections=sections,
        output_path=output_path,
    )


def render_coursework_pack_pdf(
    pack: dict,
    output_path: Optional[Path | str] = None,
) -> bytes | Path:
    """Render a coursework pack (structure produced by coursework_pack.py).

    Honors ``pack["audience"]``: the "student" audience never renders
    answer keys, teacher notes, or background reading — coursework_pack
    strips them from the dict too, so this is defense in depth.
    """
    audience = pack.get("audience", "teacher")
    is_teacher = audience == "teacher"
    cover_info = pack.get("cover", {})
    sections: list[dict] = []

    for unit in pack.get("units", []):
        overview: dict = {
            "heading": f"Unit — {unit.get('title', unit.get('unit_id', ''))}",
            "paragraphs": [p for p in [
                unit.get("overview", ""),
                f"Focus: {unit.get('focus')}" if unit.get("focus") else "",
                f"CEFR: {unit.get('cefr_language') or unit.get('cefr_target', '')}",
            ] if p],
        }
        if is_teacher and unit.get("source_citation"):
            overview["note"] = f"Source: {unit['source_citation']}"
        sections.append(overview)

        for activity in unit.get("activities", []):
            act: dict = {
                "subheading": activity.get("title", activity.get("activity_id", "Activity")),
                "paragraphs": [],
                "bullets": [],
            }
            if activity.get("instructions"):
                act["paragraphs"].append(activity["instructions"])
            if activity.get("duration_minutes"):
                act["paragraphs"].append(f"Suggested time: {activity['duration_minutes']} minutes.")
            tiers = activity.get("tiers", {}) or {}
            for tier_name in ("foundational", "on_track", "extended"):
                tier = tiers.get(tier_name)
                if not tier:
                    continue
                label = tier_name.replace("_", " ").title()
                act["bullets"].append(
                    f"{label} ({tier.get('cefr_target', '')}): {tier.get('learning_objective', '')}"
                )
                for task in tier.get("tasks", []) or []:
                    act["bullets"].append(f"    – {task.get('prompt', '')}")
            if activity.get("draft") and is_teacher:
                act["note"] = "draft — teacher review required"
            sections.append(act)

        if is_teacher:
            key_sections = []
            for activity in unit.get("activities", []):
                if activity.get("answer_key"):
                    key_sections.append({
                        "subheading": f"Answer key — {activity.get('title', '')}",
                        "bullets": list(activity["answer_key"]),
                    })
                if activity.get("teacher_notes"):
                    key_sections.append({
                        "subheading": f"Teacher notes — {activity.get('title', '')}",
                        "bullets": list(activity["teacher_notes"]),
                    })
            if key_sections:
                sections.append({
                    "heading": "Answer key & teacher notes",
                    "page_break_before": True,
                    "note": "Teacher pack only — never distribute this section to students.",
                })
                sections.extend(key_sections)
            reading = unit.get("background_reading", []) or []
            if reading:
                sections.append({
                    "heading": "Teacher background reading",
                    "bullets": [
                        f"{item.get('title', '')} — {item.get('citation', '')}"
                        for item in reading
                    ],
                })

    audience_label = "Teacher pack" if is_teacher else "Student pack"
    return render_document(
        title=f"Coursework pack — {cover_info.get('title', pack.get('pack_id', ''))}",
        metadata={
            "Grade": cover_info.get("grade", ""),
            "Units": cover_info.get("unit_count", ""),
            "Edition": audience_label,
            "Status": "DRAFT — teacher review required" if is_teacher else "",
        },
        cover={
            "title": cover_info.get("title", "Coursework pack"),
            "subtitle_lines": [
                line for line in [
                    f"Grade {cover_info.get('grade', '')}".strip(),
                    cover_info.get("focus", ""),
                    audience_label,
                ] if line
            ],
        },
        sections=sections,
        output_path=output_path,
    )
