from __future__ import annotations

from pathlib import Path

from .contracts import DriveItem, DriveWriteResult, SourceBytes


def list_folder(folder_ref: str, *, recursive: bool = False) -> list[DriveItem]:
    raise NotImplementedError("T1 implements Drive folder listing")


# Google-native formats are exported to a text form the extractor understands
# (docpipe.extract TEXT_MIMES covers text/plain + text/csv). Everything else
# downloads as raw bytes via alt=media.
_EXPORT_MAP = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
}


def fetch_file(file_ref: str) -> SourceBytes:
    """Fetch one Drive file for ingest (SPEC_LV_DRIVE_OOTB 2026-08-18, G2).

    Accepts a pasted Drive URL or a bare file ID. Delegates auth/transport to
    google_drive_integration; raises its DriveConfigError/DriveAuthError (and
    ValueError for an unparseable ref) — callers surface those honestly.
    """
    from urllib import parse

    from src.lingua_viva.google_drive_integration import (
        DRIVE_API,
        PER_FILE_ACCESS_HINT,
        DriveAuthError,
        DriveFileTooLarge,
        MAX_IMPORT_BYTES,
        _access_token,
        _is_access_denied,
        default_transport,
        ensure_configured,
        parse_file_link,
    )

    file_id = parse_file_link(file_ref)
    if not file_id:
        raise ValueError("That does not look like a Google Drive file link or ID.")
    settings = ensure_configured()
    transport = default_transport()
    token = _access_token(settings, transport)
    quoted = parse.quote(file_id, safe="")
    try:
        meta = transport.get_json(
            f"{DRIVE_API}/files/{quoted}?fields=id,name,mimeType,size", token
        )
    except Exception as exc:
        if _is_access_denied(exc):
            raise DriveAuthError(PER_FILE_ACCESS_HINT) from exc
        raise DriveAuthError("Could not read that file from Google Drive.") from exc
    if not isinstance(meta, dict) or not meta.get("id"):
        raise DriveAuthError("Could not read that file from Google Drive.")
    name = str(meta.get("name") or "imported-file")
    mime = str(meta.get("mimeType") or "")
    size_raw = meta.get("size")
    try:
        size = int(size_raw) if size_raw not in (None, "") else None
    except (TypeError, ValueError):
        size = None
    if size is not None and size > MAX_IMPORT_BYTES:
        raise DriveFileTooLarge(str(size))

    export = _EXPORT_MAP.get(mime)
    if export:
        out_mime, suffix = export
        url = f"{DRIVE_API}/files/{quoted}/export?mimeType={parse.quote(out_mime, safe='')}"
        filename = name if name.lower().endswith(suffix) else name + suffix
    else:
        out_mime = mime
        url = f"{DRIVE_API}/files/{quoted}?alt=media"
        filename = name
    try:
        content = transport.get_bytes(url, token)
    except Exception as exc:
        if _is_access_denied(exc):
            raise DriveAuthError(PER_FILE_ACCESS_HINT) from exc
        raise DriveAuthError("Could not download that file from Google Drive.") from exc
    if len(content) > MAX_IMPORT_BYTES:
        raise DriveFileTooLarge(str(len(content)))
    return SourceBytes(
        file_ref=file_id,
        filename=filename,
        mime=out_mime,
        content=content,
        origin="drive",
        path=name,
        drive_file_id=file_id,
    )


def push_file(
    local_path: Path,
    destination_ref: str,
    *,
    mime: str | None = None,
) -> DriveWriteResult:
    raise NotImplementedError("T6 implements Drive write-back")

