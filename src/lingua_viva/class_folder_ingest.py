from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.education.student_lens import StudentLensStore
from src.lingua_viva.docpipe.contracts import ExtractionRecord, SourceRecord


FOLDER_MIME = "application/vnd.google-apps.folder"
MAX_FILES_PER_RUN = 60
MAX_DEPTH = 4


@dataclass(frozen=True)
class Attribution:
    student_id: str
    display_name: str
    method: str
    confidence: float


def ingest_class_folder(
    folder_id: str,
    teacher_id: str,
    *,
    store: StudentLensStore,
    max_files: int = MAX_FILES_PER_RUN,
    max_depth: int = MAX_DEPTH,
) -> dict[str, Any]:
    """Import a Drive class folder into student lenses.

    Attribution is intentionally conservative. Exact filename matches against
    existing roster names win, exact header/text matches come next, then
    verbatim docpipe detections. Anything else is returned for manual review.
    """
    from src.lingua_viva import google_drive_integration as drive
    from src.lingua_viva.docpipe import extract as docpipe_extract
    from src.lingua_viva.docpipe import lens as docpipe_lens
    from src.lingua_viva.docpipe import vault as docpipe_vault

    teacher = str(teacher_id or "teacher:drive").strip() or "teacher:drive"
    roster = _roster(store)
    files = _walk_folder(drive, folder_id, max_files=max_files, max_depth=max_depth)
    created_or_updated: list[dict[str, Any]] = []
    unattributed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    processed = 0

    for file_meta in files:
        if processed >= max_files:
            break
        if file_meta.get("mime_type") == FOLDER_MIME:
            continue
        processed += 1
        file_id = str(file_meta.get("id") or "")
        name = str(file_meta.get("name") or "drive-file")
        try:
            imported = drive.import_files([file_id], "unassigned")
            if imported.get("failed"):
                failed.extend(imported["failed"])
                continue
            imported_item = imported["imported"][0]
            local_path = Path(imported_item["local_path"])
            content = local_path.read_bytes()
            source = _source_record(
                filename=name,
                content=content,
                path=str(local_path),
                drive_file_id=file_id,
                mime=str(file_meta.get("mime_type") or ""),
            )
            docpipe_vault.put_source(source, content)
            extraction = _run_extractor(docpipe_extract, source, content)
            docpipe_vault.put_extraction(extraction)
        except Exception as exc:  # noqa: BLE001 - one bad document must not stop the folder.
            failed.append({"drive_id": file_id, "name": name, "status": "failed", "message": str(exc)})
            continue

        attributions = _attribute_document(file_meta, extraction, roster)
        if not attributions:
            unattributed.append({
                "drive_id": file_id,
                "name": name,
                "reason": "No exact roster or document-name match.",
                "students_detected": [
                    s for s in extraction.data.get("structure", {}).get("students_detected", [])
                    if isinstance(s, dict)
                ],
            })
            continue

        for attribution in attributions:
            record = docpipe_lens.create_from_extraction(
                extraction,
                student_id=attribution.student_id,
                student_name=attribution.display_name,
                added_by=teacher,
                student_store=store,
            )
            evidence_id = store.append_evidence({
                "student_id": attribution.student_id,
                "teacher_id": teacher,
                "kind": "document",
                "target_type": "background",
                "target_id": None,
                "summary": (
                    f"Drive document '{name}' attributed by "
                    f"{attribution.method} ({attribution.confidence:.2f})."
                ),
                "source_ref": {
                    "source_type": "drive",
                    "drive_file_id": file_id,
                    "source_id": source.source_id,
                    "attribution_method": attribution.method,
                    "attribution_confidence": attribution.confidence,
                },
                "confidence_level": "imported_verified",
            })
            created_or_updated.append({
                "student_id": attribution.student_id,
                "display_name": attribution.display_name,
                "drive_id": file_id,
                "name": name,
                "attribution_method": attribution.method,
                "attribution_confidence": attribution.confidence,
                "evidence_id": evidence_id,
                "fields_populated": _populated_fields(record.data),
            })

    return {
        "folder_id": folder_id,
        "teacher_id": teacher,
        "files_seen": len(files),
        "files_processed": processed,
        "students_created_or_updated": created_or_updated,
        "unattributed": unattributed,
        "failed": failed,
        "truncated": len(files) > max_files,
    }


def _walk_folder(drive: Any, folder_id: str, *, max_files: int, max_depth: int) -> list[dict[str, Any]]:
    seen_folders: set[str] = set()
    out: list[dict[str, Any]] = []

    def visit(current_id: str, depth: int) -> None:
        if depth > max_depth or len(out) >= max_files:
            return
        if current_id in seen_folders:
            return
        seen_folders.add(current_id)
        for item in drive.list_folder_files(current_id):
            meta = dict(item)
            meta.setdefault("mime_type", meta.get("mimeType"))
            if meta.get("mime_type") == FOLDER_MIME:
                visit(str(meta.get("id") or ""), depth + 1)
            else:
                out.append(meta)
            if len(out) >= max_files:
                return

    visit(folder_id, 0)
    return out


def _roster(store: StudentLensStore) -> list[dict[str, str]]:
    rows = store.list_lenses()
    return [
        {"student_id": str(row["student_id"]), "display_name": str(row.get("display_name") or "")}
        for row in rows
        if str(row.get("display_name") or "").strip()
    ]


def _attribute_document(
    file_meta: dict[str, Any],
    extraction: ExtractionRecord,
    roster: list[dict[str, str]],
) -> list[Attribution]:
    filename = str(file_meta.get("name") or "")
    header = str(extraction.data.get("normalized_text") or "")[:1800]
    matches: list[Attribution] = []
    for row in roster:
        name = row["display_name"]
        if _contains_name(filename, name):
            matches.append(Attribution(row["student_id"], name, "filename_roster_exact", 0.98))
        elif _contains_name(header, name):
            matches.append(Attribution(row["student_id"], name, "document_header_roster_exact", 0.92))
    if matches:
        return _dedupe(matches)

    detected = [
        s for s in extraction.data.get("structure", {}).get("students_detected", [])
        if isinstance(s, dict) and str(s.get("display_name") or "").strip()
    ]
    for student in detected:
        name = str(student.get("display_name") or "").strip()
        sid = str(student.get("student_id") or _student_id_from_name(name))
        try:
            confidence = float(student.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        matches.append(Attribution(sid, name, "document_detected_name", min(confidence, 0.9)))
    return _dedupe(matches)


def _dedupe(matches: list[Attribution]) -> list[Attribution]:
    seen: set[str] = set()
    out: list[Attribution] = []
    for match in matches:
        if match.student_id in seen:
            continue
        seen.add(match.student_id)
        out.append(match)
    return out


def _contains_name(text: str, display_name: str) -> bool:
    if not text or not display_name:
        return False
    pattern = r"(?<![A-Za-z])" + re.escape(display_name.strip()) + r"(?![A-Za-z])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _student_id_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"student-{slug or uuid.uuid4()}"


def _source_record(
    *,
    filename: str,
    content: bytes,
    path: str,
    drive_file_id: str,
    mime: str,
) -> SourceRecord:
    ext = Path(filename).suffix.lower()
    guessed_mime = mime or mimetypes.guess_type(filename)[0] or "text/plain"
    return SourceRecord({
        "schema_version": "docpipe.source.v1",
        "source_id": f"SRC-{uuid.uuid4()}",
        "origin": "drive",
        "drive_file_id": drive_file_id,
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "imported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "mime": guessed_mime,
        "owner": "teacher:drive",
        "original_filename": filename,
        "original_ext": ext,
        "byte_size": len(content),
    })


def _run_extractor(docpipe_extract: Any, source: SourceRecord, content: bytes) -> ExtractionRecord:
    async def run() -> ExtractionRecord:
        return await docpipe_extract.extract_document(source, content, model_client=None)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run())
    raise RuntimeError("ingest_class_folder must run outside the event loop; use asyncio.to_thread")


def _populated_fields(data: dict[str, Any]) -> list[str]:
    return [
        field_id
        for field_id, field in data.get("profile", {}).items()
        if isinstance(field, dict) and field.get("evidence")
    ]
