from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib import error, parse, request

from src.lingua_viva.config import lv_home


DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SUPPORTED_IMPORT_MIME_TYPES = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/vnd.google-apps.document": ".txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
EXTRACTION_SUFFIXES = {".pdf", ".txt", ".md"}
SUPPORTED_EXPORT_MIME_TYPES = {
    ".json": "application/json",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".yaml": "application/x-yaml",
    ".yml": "application/x-yaml",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
PURPOSES = {
    "student_lens_source",
    "curriculum_unit_source",
    "teacher_artifact_source",
    "unassigned",
}


# H2 (SPEC_LV_DRIVE_FINAL_HARDENING_2026-07-27): downloads are bounded —
# timeouts alone don't stop a huge file from exhausting memory.
MAX_IMPORT_BYTES = 100 * 1024 * 1024


class DriveConfigError(RuntimeError):
    pass


class DriveAuthError(RuntimeError):
    pass


class DriveFileTooLarge(RuntimeError):
    pass


def _read_bounded(response: Any, limit: int) -> bytes:
    """Read an HTTP response body, refusing to exceed `limit` bytes.

    Checks Content-Length when the server sends one, and hard-caps the
    chunked read regardless (a lying or absent header can't bypass it).
    """
    declared = response.headers.get("Content-Length") if getattr(response, "headers", None) else None
    if declared:
        try:
            if int(declared) > limit:
                raise DriveFileTooLarge(str(declared))
        except ValueError:
            pass  # malformed header — fall through to the streaming cap
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise DriveFileTooLarge(str(total))
        chunks.append(chunk)
    return b"".join(chunks)


class DriveTransport(Protocol):
    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        ...

    def get_json(self, url: str, token: str) -> dict[str, Any]:
        ...

    def get_bytes(self, url: str, token: str) -> bytes:
        ...

    def post_multipart(
        self, url: str, token: str, metadata: dict[str, Any], content: bytes, content_type: str
    ) -> dict[str, Any]:
        ...


class UrlLibDriveTransport:
    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        encoded = parse.urlencode(data).encode("utf-8")
        req = request.Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_json(self, url: str, token: str) -> dict[str, Any]:
        req = request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_bytes(self, url: str, token: str) -> bytes:
        req = request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
        with request.urlopen(req, timeout=30) as response:
            return _read_bounded(response, MAX_IMPORT_BYTES)

    def post_multipart(
        self, url: str, token: str, metadata: dict[str, Any], content: bytes, content_type: str
    ) -> dict[str, Any]:
        boundary = "lv_drive_upload_boundary"
        meta_part = json.dumps(metadata, ensure_ascii=True).encode("utf-8")
        body = b"".join([
            f"--{boundary}\r\n".encode("ascii"),
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
            meta_part,
            f"\r\n--{boundary}\r\n".encode("ascii"),
            f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
            content,
            f"\r\n--{boundary}--\r\n".encode("ascii"),
        ])
        req = request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))


class FixtureDriveTransport:
    """Local fixture transport for served-app verification; never contacts Google."""

    def __init__(self, fixture_path: str | Path):
        self.fixture_path = Path(fixture_path)
        self.data = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self.uploads: list[dict[str, Any]] = []

    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        return {"access_token": "fixture-access-token"}

    def get_json(self, url: str, token: str) -> dict[str, Any]:
        files = self.data.get("files", [])
        if "/files?" in url:
            return {"files": files, "nextPageToken": None}
        file_id = parse.unquote(url.split("/files/", 1)[1].split("?", 1)[0])
        for item in files:
            if item.get("id") == file_id:
                return item
        raise FileNotFoundError(file_id)

    def get_bytes(self, url: str, token: str) -> bytes:
        file_id = parse.unquote(url.split("/files/", 1)[1].split("?", 1)[0])
        for item in self.data.get("files", []):
            if item.get("id") == file_id:
                return str(item.get("content", "")).encode("utf-8")
        raise FileNotFoundError(file_id)

    def post_multipart(
        self, url: str, token: str, metadata: dict[str, Any], content: bytes, content_type: str
    ) -> dict[str, Any]:
        upload_id = f"fixture-upload-{len(self.uploads) + 1}"
        record = {
            "id": upload_id,
            "name": str(metadata.get("name") or "untitled"),
            "parents": metadata.get("parents") or [],
            "mime_type": content_type,
            "size": len(content),
        }
        self.uploads.append(record)
        return {"id": upload_id, "name": record["name"]}


def default_transport() -> DriveTransport:
    fixture = os.environ.get("LV_GOOGLE_DRIVE_MOCK_FIXTURE")
    if fixture:
        return FixtureDriveTransport(fixture)
    return UrlLibDriveTransport()


@dataclass(frozen=True)
class DriveSettings:
    enabled: bool
    client_id: str | None
    client_secret: str | None
    refresh_token: str | None
    root_id: str | None
    # "env" (operator-provisioned) or "stored" (in-app Google sign-in,
    # SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27 §A2). Env always wins.
    auth_source: str = "env"

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.client_id and self.client_secret and self.refresh_token)


def settings_from_env() -> DriveSettings:
    def clean(name: str) -> str | None:
        value = os.environ.get(name)
        if value is None:
            return None
        value = value.strip()
        return value or None

    return DriveSettings(
        enabled=os.environ.get("LV_GOOGLE_DRIVE_ENABLED", "").lower() in {"1", "true", "yes", "on"},
        client_id=clean("LV_GOOGLE_CLIENT_ID"),
        client_secret=clean("LV_GOOGLE_CLIENT_SECRET"),
        refresh_token=clean("LV_GOOGLE_REFRESH_TOKEN"),
        root_id=clean("LV_GOOGLE_DRIVE_ROOT_ID"),
    )


def load_settings() -> DriveSettings:
    """Effective Drive settings: env > in-app sign-in > unconfigured (§A2).

    A fully env-configured machine (operator provisioning) always shadows the
    stored sign-in; stored auth marked needs_signin (dead refresh token) is
    never used.
    """
    env = settings_from_env()
    if env.configured:
        return env
    from src.lingua_viva import google_drive_oauth as oauth  # lazy: avoids import cycle

    stored = oauth.load_stored_auth() or {}
    if (
        stored.get("refresh_token")
        and stored.get("client_id")
        and stored.get("client_secret")
        and not stored.get("needs_signin")
    ):
        return DriveSettings(
            enabled=True,
            client_id=str(stored["client_id"]),
            client_secret=str(stored["client_secret"]),
            refresh_token=str(stored["refresh_token"]),
            root_id=env.root_id,
            auth_source="stored",
        )
    return env


def import_dir() -> Path:
    override = os.environ.get("LV_GOOGLE_DRIVE_IMPORT_DIR")
    return Path(override).expanduser() if override else lv_home() / "runtime" / "drive_imports"


def export_dir() -> Path:
    override = os.environ.get("LV_GOOGLE_DRIVE_EXPORT_DIR")
    return Path(override).expanduser() if override else lv_home() / "runtime" / "drive_exports"


def folders_path() -> Path:
    override = os.environ.get("LV_GOOGLE_DRIVE_FOLDERS_PATH")
    return Path(override).expanduser() if override else lv_home() / "runtime" / "drive_folders.json"


FOLDER_URL_PATTERNS = [
    re.compile(r"/folders/([A-Za-z0-9_-]{5,})"),
    re.compile(r"[?&]id=([A-Za-z0-9_-]{5,})"),
]
BARE_FOLDER_ID = re.compile(r"^[A-Za-z0-9_-]{5,}$")


def parse_folder_link(link: str) -> str | None:
    """Extract a Drive folder ID from a pasted URL (or accept a bare ID)."""
    link = (link or "").strip()
    if not link:
        return None
    for pattern in FOLDER_URL_PATTERNS:
        match = pattern.search(link)
        if match:
            return match.group(1)
    if BARE_FOLDER_ID.match(link) and "://" not in link:
        return link
    return None


# Serializes read-modify-write cycles on the folder registry. Routes run these
# helpers via asyncio.to_thread, so a connect landing while the list route
# stamps last_checked would otherwise be lost to a last-writer-wins overwrite.
_FOLDERS_LOCK = threading.Lock()

# Serializes append cycles on the import/export manifests (also read-modify-write).
_MANIFEST_LOCK = threading.Lock()


def _atomic_write_private_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON that is 0600 from birth and can never be half-written.

    Same-dir temp file + os.replace: a crash mid-write leaves the previous
    file intact, and the content is never observable with wider permissions.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=True))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def _atomic_write_private_text(path: Path, content: str) -> None:
    """Write private UTF-8 text with the same 0600 atomic semantics as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(content or ""))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def list_connected_folders() -> list[dict[str, Any]]:
    try:
        data = json.loads(folders_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    folders = data.get("folders") if isinstance(data, dict) else None
    return folders if isinstance(folders, list) else []


def _save_connected_folders(folders: list[dict[str, Any]]) -> None:
    _atomic_write_private_json(
        folders_path(),
        {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "folders": folders,
        },
    )


def connect_folder(
    link: str,
    name: str = "",
    purpose: str = "unassigned",
    *,
    settings: DriveSettings | None = None,
    transport: DriveTransport | None = None,
) -> dict[str, Any]:
    """Connect a Drive folder from a pasted link, verifying access before saving."""
    folder_id = parse_folder_link(link)
    if not folder_id:
        raise ValueError("That does not look like a Google Drive folder link.")
    if purpose not in PURPOSES:
        raise ValueError("Invalid folder purpose.")

    settings = ensure_configured(settings)
    transport = transport or default_transport()
    token = _access_token(settings, transport)
    try:
        meta = transport.get_json(
            f"{DRIVE_API}/files/{parse.quote(folder_id, safe='')}?fields=id,name,mimeType",
            token,
        )
    except (error.HTTPError, error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise DriveAuthError(
            "Lingua Viva could not open that folder. Check the link and that it is shared with the connected account."
        ) from exc
    if not isinstance(meta, dict):  # H5: malformed metadata response
        raise DriveAuthError(
            "Lingua Viva could not open that folder. Check the link and that it is shared with the connected account."
        )
    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        raise ValueError("That link points to a file, not a folder.")

    display_name = (name or "").strip() or str(meta.get("name") or "Drive folder")
    entry = {
        "id": folder_id,
        "name": display_name,
        "purpose": purpose,
        "connected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "last_checked": None,
        "share_back": False,
    }
    with _FOLDERS_LOCK:
        folders = [f for f in list_connected_folders() if f.get("id") != folder_id]
        folders.append(entry)
        _save_connected_folders(folders)
    return entry


def disconnect_folder(folder_id: str) -> bool:
    with _FOLDERS_LOCK:
        folders = list_connected_folders()
        remaining = [f for f in folders if f.get("id") != folder_id]
        if len(remaining) == len(folders):
            return False
        _save_connected_folders(remaining)
        return True


def mark_folder_checked(folder_id: str) -> None:
    with _FOLDERS_LOCK:
        folders = list_connected_folders()
        changed = False
        for entry in folders:
            if entry.get("id") == folder_id:
                entry["last_checked"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                changed = True
        if changed:
            _save_connected_folders(folders)


def manifest_path() -> Path:
    return import_dir() / "import_manifest.json"


def status(settings: DriveSettings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    from src.lingua_viva import google_drive_oauth as oauth  # lazy: avoids import cycle

    auth = oauth.auth_status()
    configured = settings.configured
    if configured:
        setup_message = "Google Drive import is configured for explicit local import."
    elif auth["needs_signin"]:
        setup_message = "Google sign-in has expired. Please sign in to Google again."
    elif auth["can_signin"]:
        setup_message = "Sign in with Google to connect Drive on this machine."
    else:
        setup_message = "Google Drive import is not configured on this machine."
    return {
        "configured": configured,
        "mode": "explicit_import",
        "enabled": settings.enabled,
        "client_id_set": bool(settings.client_id),
        "client_secret_set": bool(settings.client_secret),
        "refresh_token_set": bool(settings.refresh_token),
        "root_id_set": bool(settings.root_id),
        "can_list": configured,
        "can_download": configured,
        # Root folder is optional with in-app sign-in (§A5): a connected
        # folder is an equally explicit destination.
        "can_upload": bool(configured and (settings.root_id or list_connected_folders())),
        "local_only_after_import": True,
        "auth_source": settings.auth_source if configured else None,
        # Shown for in-app sign-in (incl. the "sign in again" state); hidden
        # when env credentials shadow it — the account is not the teacher's.
        "account_email": (
            auth["account_email"]
            if (settings.auth_source == "stored" or not configured)
            else None
        ),
        "needs_signin": auth["needs_signin"],
        "can_signin": auth["can_signin"],
        "flow_pending": auth["flow_pending"],
        "setup_message": setup_message,
    }


def ensure_configured(settings: DriveSettings | None = None) -> DriveSettings:
    settings = settings or load_settings()
    if not settings.configured:
        raise DriveConfigError("Google Drive import is not configured on this machine.")
    return settings


def _is_invalid_grant(exc: error.HTTPError) -> bool:
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:
        return False
    return "invalid_grant" in body


def _access_token(settings: DriveSettings, transport: DriveTransport) -> str:
    try:
        payload = transport.post_form(
            TOKEN_URL,
            {
                "client_id": settings.client_id or "",
                "client_secret": settings.client_secret or "",
                "refresh_token": settings.refresh_token or "",
                "grant_type": "refresh_token",
            },
        )
    except error.HTTPError as exc:
        # A stored refresh token that Google reports as invalid_grant is dead
        # (revoked, or expired under a Testing-status consent screen). Flag it
        # so the UI offers "Sign in again" instead of an opaque failure (§A6).
        if settings.auth_source == "stored" and _is_invalid_grant(exc):
            from src.lingua_viva import google_drive_oauth as oauth  # lazy: avoids import cycle

            oauth.mark_needs_signin()
            raise DriveAuthError(
                "Google sign-in has expired. Please sign in to Google again."
            ) from exc
        raise DriveAuthError("Google Drive authorization failed.") from exc
    except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise DriveAuthError("Google Drive authorization failed.") from exc
    if not isinstance(payload, dict):  # H5: malformed token response
        raise DriveAuthError("Google Drive authorization failed.")
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise DriveAuthError("Google Drive authorization failed.")
    return token


def _supports(mime_type: str) -> tuple[bool, bool, str | None]:
    suffix = SUPPORTED_IMPORT_MIME_TYPES.get(mime_type)
    if not suffix:
        return False, False, None
    return True, suffix in EXTRACTION_SUFFIXES, suffix


def _file_metadata(item: dict[str, Any]) -> dict[str, Any]:
    mime_type = str(item.get("mimeType") or item.get("mime_type") or "")
    supported_import, supported_extraction, _suffix = _supports(mime_type)
    size_value = item.get("size")
    try:
        size = int(size_value) if size_value not in (None, "") else None
    except (TypeError, ValueError):
        size = None
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or "untitled"),
        "mime_type": mime_type,
        "modified_time": item.get("modifiedTime") or item.get("modified_time"),
        "size": size,
        "supported_for_import": supported_import,
        "supported_for_extraction": supported_extraction,
    }


def list_files(
    query: str = "",
    folder_id: str = "",
    page_token: str = "",
    *,
    settings: DriveSettings | None = None,
    transport: DriveTransport | None = None,
) -> dict[str, Any]:
    settings = ensure_configured(settings)
    transport = transport or default_transport()
    token = _access_token(settings, transport)

    q_parts = ["trashed = false"]
    root = folder_id.strip() or settings.root_id
    if root:
        # Drive query injection guard: folder IDs are opaque [A-Za-z0-9_-]
        # tokens; anything else could break out of the quoted q expression
        # and list files outside the intended folder scope.
        if not BARE_FOLDER_ID.match(root):
            raise ValueError("That folder ID does not look valid.")
        q_parts.append(f"'{root}' in parents")
    if query.strip():
        # H4: bound search text pre-escape — Drive q expressions have server
        # limits and an unbounded value is pointless for a name search.
        if len(query) > 1024:
            raise ValueError("Search text is too long. Try a shorter search.")
        safe_query = query.strip().replace("\\", "\\\\").replace("'", "\\'")
        q_parts.append(f"name contains '{safe_query}'")
    params = {
        "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,size)",
        "pageSize": "25",
        "q": " and ".join(q_parts),
    }
    if page_token.strip():
        params["pageToken"] = page_token.strip()
    url = f"{DRIVE_API}/files?{parse.urlencode(params)}"
    try:
        data = transport.get_json(url, token)
    except (error.HTTPError, error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise DriveAuthError("Google Drive list failed.") from exc
    if not isinstance(data, dict):  # H5: malformed list response
        raise DriveAuthError("Google Drive list failed.")
    raw_files = data.get("files")
    if not isinstance(raw_files, list):
        raw_files = []
    files = [_file_metadata(item) for item in raw_files if isinstance(item, dict)]
    try:
        from src.lingua_viva.sources.ledger import compute_source_record_id, now_iso, upsert
        from src.lingua_viva.sources.schema import SourceRecord

        observed_at = now_iso()
        container = root or "drive-root"
        for file_meta in files:
            source_record_id = compute_source_record_id("drive", file_meta["id"], container, file_meta["id"])
            upsert(SourceRecord(
                source_record_id=source_record_id,
                source_type="drive",
                source_id=file_meta["id"],
                container=container,
                record_id=file_meta["id"],
                title=file_meta["name"],
                uri=f"gdrive://{file_meta['id']}",
                retrieval_scope="metadata",
                created_at=observed_at,
                observed_at=observed_at,
                provenance="fetch",
                sensitivity_hint="medium" if "student" in file_meta["name"].lower() else "low",
                content_hash=str(file_meta.get("modified_time") or file_meta.get("size") or ""),
                summary=file_meta["mime_type"],
            ), detail={"operation": "list_files"})
    except Exception:
        pass
    next_token = data.get("nextPageToken")
    return {"files": files, "next_page_token": next_token if isinstance(next_token, str) else None}


def list_folder_files(
    folder_id: str,
    *,
    settings: DriveSettings | None = None,
    transport: DriveTransport | None = None,
) -> list[dict[str, Any]]:
    """Lean folder listing for sync plumbing (ledger pull): id + name only,
    no source-ledger side effects — ledger files are transport artifacts,
    not teacher sources. Same auth/error patterns as list_files."""
    folder_id = (folder_id or "").strip()
    if not BARE_FOLDER_ID.match(folder_id):
        raise ValueError("That folder ID does not look valid.")
    settings = ensure_configured(settings)
    transport = transport or default_transport()
    token = _access_token(settings, transport)
    params = {
        "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,size)",
        "pageSize": "100",
        "q": f"trashed = false and '{folder_id}' in parents",
    }
    files: list[dict[str, Any]] = []
    page_token = ""
    while True:
        if page_token:
            params["pageToken"] = page_token
        url = f"{DRIVE_API}/files?{parse.urlencode(params)}"
        try:
            data = transport.get_json(url, token)
        except (error.HTTPError, error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise DriveAuthError("Google Drive list failed.") from exc
        if not isinstance(data, dict):
            raise DriveAuthError("Google Drive list failed.")
        raw_files = data.get("files")
        if isinstance(raw_files, list):
            files.extend(
                _file_metadata(item)
                for item in raw_files
                if isinstance(item, dict) and item.get("id")
            )
        page_token = data.get("nextPageToken") if isinstance(data.get("nextPageToken"), str) else ""
        if not page_token:
            break
    return files


def download_file_text(
    file_id: str,
    *,
    settings: DriveSettings | None = None,
    transport: DriveTransport | None = None,
) -> str:
    """Download one Drive file's content as UTF-8 text (bounded read)."""
    file_id = (file_id or "").strip()
    if not file_id:
        raise ValueError("file_id is required.")
    settings = ensure_configured(settings)
    transport = transport or default_transport()
    token = _access_token(settings, transport)
    url = f"{DRIVE_API}/files/{parse.quote(file_id, safe='')}?alt=media"
    try:
        content = transport.get_bytes(url, token)
    except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
        raise DriveAuthError("Google Drive download failed.") from exc
    if len(content) > MAX_IMPORT_BYTES:
        raise DriveFileTooLarge(str(len(content)))
    return content.decode("utf-8", errors="replace")


def _safe_filename(name: str, suffix: str) -> str:
    stem = Path(name).name
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" .") or "drive-file"
    current_suffix = Path(stem).suffix.lower()
    if current_suffix != suffix:
        stem = f"{Path(stem).stem or 'drive-file'}{suffix}"
    return stem


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def _load_manifest() -> dict[str, Any]:
    path = manifest_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    return data if isinstance(data, dict) else {}


def _write_manifest(entries: list[dict[str, Any]]) -> None:
    with _MANIFEST_LOCK:
        existing = _load_manifest()
        existing_entries = existing.get("imports") if isinstance(existing.get("imports"), list) else []
        _atomic_write_private_json(
            manifest_path(),
            {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "imports": [*existing_entries, *entries],
            },
        )


def _download_url(file_id: str, mime_type: str) -> str:
    if mime_type == "application/vnd.google-apps.document":
        return f"{DRIVE_API}/files/{parse.quote(file_id, safe='')}/export?mimeType=text/plain"
    return f"{DRIVE_API}/files/{parse.quote(file_id, safe='')}?alt=media"


def _record_assignment(local_path: Path, purpose: str, assigned_student_id: str | None) -> None:
    from src.lingua_viva.filemap import record_imported_file_assignment

    record_imported_file_assignment(local_path, purpose, assigned_student_id)


def import_files(
    file_ids: list[str],
    purpose: str,
    assigned_student_id: str | None = None,
    *,
    settings: DriveSettings | None = None,
    transport: DriveTransport | None = None,
    student_exists: Any = None,
) -> dict[str, Any]:
    if not file_ids or not all(isinstance(item, str) and item.strip() for item in file_ids):
        raise ValueError("file_ids must be a non-empty list of opaque IDs.")
    if purpose not in PURPOSES:
        raise ValueError("Invalid Drive import purpose.")
    if purpose == "student_lens_source":
        if not assigned_student_id:
            raise ValueError("assigned_student_id is required for student_lens_source.")
        if student_exists is not None and not student_exists(assigned_student_id):
            raise ValueError("assigned_student_id is not in the current roster.")

    settings = ensure_configured(settings)
    transport = transport or default_transport()
    token = _access_token(settings, transport)
    target_dir = import_dir().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    imported: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    manifest_entries: list[dict[str, Any]] = []

    for file_id in [item.strip() for item in file_ids]:
        try:
            meta = transport.get_json(
                f"{DRIVE_API}/files/{parse.quote(file_id, safe='')}?fields=id,name,mimeType,modifiedTime,size",
                token,
            )
            file_meta = _file_metadata(meta)
            supported_import, supported_extraction, suffix = _supports(file_meta["mime_type"])
            if not supported_import or not suffix:
                failed.append({
                    "drive_id": file_id,
                    "status": "unsupported_for_import",
                    "message": "This file type is not supported yet.",
                })
                continue
            # H2: refuse oversized files before downloading (metadata size),
            # during (bounded transport read), and after (covers transports
            # that don't stream, e.g. fixtures).
            if file_meta["size"] is not None and file_meta["size"] > MAX_IMPORT_BYTES:
                raise DriveFileTooLarge(str(file_meta["size"]))
            content = transport.get_bytes(_download_url(file_id, file_meta["mime_type"]), token)
            if len(content) > MAX_IMPORT_BYTES:
                raise DriveFileTooLarge(str(len(content)))
            local_path = _unique_path(target_dir, _safe_filename(file_meta["name"], suffix)).resolve()
            if target_dir not in local_path.parents:
                raise ValueError("Drive filename resolved outside the import cache.")
            local_path.write_bytes(content)
            os.chmod(local_path, 0o600)
            if purpose != "unassigned":
                _record_assignment(local_path, purpose, assigned_student_id)
            item = {
                "drive_id": file_id,
                "name": file_meta["name"],
                "local_path": str(local_path),
                "purpose": purpose,
                "assigned_student_id": assigned_student_id,
                "supported_for_extraction": supported_extraction,
                "status": "imported",
            }
            imported.append(item)
            manifest_entries.append({
                "imported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "drive_id": file_id,
                "drive_name": file_meta["name"],
                "mime_type": file_meta["mime_type"],
                "modified_time": file_meta.get("modified_time"),
                "local_path": str(local_path),
                "purpose": purpose,
                "assigned_student_id": assigned_student_id,
                "supported_for_extraction": supported_extraction,
                "status": "imported",
            })
            try:
                from src.lingua_viva.sources.ledger import compute_source_record_id, now_iso, upsert
                from src.lingua_viva.sources.schema import SourceRecord

                observed_at = now_iso()
                source_record_id = compute_source_record_id("drive", file_id, "drive-import", file_id)
                upsert(SourceRecord(
                    source_record_id=source_record_id,
                    source_type="drive",
                    source_id=file_id,
                    container="drive-import",
                    record_id=file_id,
                    title=file_meta["name"],
                    uri=str(local_path),
                    retrieval_scope="content" if supported_extraction else "metadata",
                    created_at=observed_at,
                    observed_at=observed_at,
                    provenance="import",
                    student_data=purpose == "student_lens_source",
                    sensitivity_hint="protect" if purpose == "student_lens_source" else "medium",
                    content_hash=hashlib.sha256(content).hexdigest(),
                    summary=f"Drive import for {purpose}",
                ), detail={"purpose": purpose})
            except Exception:
                pass
        except DriveFileTooLarge:
            failed.append({
                "drive_id": file_id,
                "status": "file_too_large",
                "code": "file_too_large",
                "message": "This file is too large for Lingua Viva to bring in.",
            })
        except Exception:
            failed.append({
                "drive_id": file_id,
                "status": "download_failed",
                "message": "This file could not be imported safely.",
            })
    if manifest_entries:
        _write_manifest(manifest_entries)
    return {
        "imported": imported,
        "failed": failed,
        "local_only_after_import": True,
    }


def _export_manifest_path() -> Path:
    return export_dir() / "export_manifest.json"


def _write_export_manifest(entries: list[dict[str, Any]]) -> None:
    path = _export_manifest_path()
    with _MANIFEST_LOCK:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            existing = {}
        existing_entries = existing.get("exports") if isinstance(existing, dict) and isinstance(existing.get("exports"), list) else []
        _atomic_write_private_json(
            path,
            {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "exports": [*existing_entries, *entries],
            },
        )


def prune_student_exports(student_id: str, keep: int = 3) -> int:
    """H3 (SPEC_LV_DRIVE_FINAL_HARDENING_2026-07-27): cap per-student lens
    snapshots in the export dir — the `keep` newest stay, older ones go.

    `drive_imports/` is deliberately NOT pruned: imports are teacher working
    materials referenced by the file map and extraction flow (teacher-owned).
    """
    prefix = f"student-lens-{student_id}-"
    try:
        candidates = [
            p
            for p in export_dir().iterdir()
            if p.is_file() and p.name.startswith(prefix) and p.suffix in {".json", ".md"}
        ]
    except (FileNotFoundError, OSError):
        return 0
    # The stamp (YYYYMMDD-HHMMSS) is fixed-width, so name order == time order;
    # sorting by name avoids stat() races on files vanishing mid-prune.
    candidates.sort(key=lambda p: p.name, reverse=True)
    removed = 0
    for stale in candidates[max(keep, 0):]:
        try:
            stale.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _allowed_export_roots() -> list[Path]:
    roots = [lv_home().resolve(), export_dir().resolve()]
    return roots


def upload_paths(
    local_paths: list[str],
    folder_id: str = "",
    *,
    settings: DriveSettings | None = None,
    transport: DriveTransport | None = None,
) -> dict[str, Any]:
    """Explicitly share local deliverable files into the connected Drive folder.

    Egress guard: only files that resolve inside the Lingua Viva home (or the
    export dir override) can be shared, and only into an explicit destination
    folder — never loose into My Drive.
    """
    if not local_paths or not all(isinstance(item, str) and item.strip() for item in local_paths):
        raise ValueError("local_paths must be a non-empty list of file paths.")

    settings = ensure_configured(settings)
    destination = folder_id.strip() or (settings.root_id or "")
    if not destination:
        raise DriveConfigError(
            "No destination Drive folder is configured. Set LV_GOOGLE_DRIVE_ROOT_ID or pass folder_id."
        )
    # Same opaque-ID guard as list_files: catches malformed destinations up
    # front with a clear message instead of an opaque per-file upload_failed.
    if not BARE_FOLDER_ID.match(destination):
        raise ValueError("That destination folder ID does not look valid.")
    transport = transport or default_transport()
    token = _access_token(settings, transport)
    allowed_roots = _allowed_export_roots()

    uploaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    manifest_entries: list[dict[str, Any]] = []

    for raw_path in [item.strip() for item in local_paths]:
        local_path = Path(raw_path).expanduser()
        try:
            resolved = local_path.resolve(strict=True)
        except OSError:
            failed.append({"local_path": raw_path, "status": "not_found", "message": "File not found."})
            continue
        if not resolved.is_file():
            failed.append({"local_path": raw_path, "status": "not_found", "message": "File not found."})
            continue
        if not any(root == resolved or root in resolved.parents for root in allowed_roots):
            failed.append({
                "local_path": raw_path,
                "status": "outside_shareable_area",
                "message": "Only Lingua Viva deliverables can be shared to Drive.",
            })
            continue
        mime_type = SUPPORTED_EXPORT_MIME_TYPES.get(resolved.suffix.lower())
        if not mime_type:
            failed.append({
                "local_path": raw_path,
                "status": "unsupported_for_upload",
                "message": "This file type is not supported for sharing yet.",
            })
            continue
        try:
            content = resolved.read_bytes()
            result = transport.post_multipart(
                DRIVE_UPLOAD_API,
                token,
                {"name": resolved.name, "parents": [destination]},
                content,
                mime_type,
            )
        except (error.HTTPError, error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            failed.append({
                "local_path": raw_path,
                "status": "upload_failed",
                "message": "This file could not be shared safely.",
            })
            continue
        drive_id = str(result.get("id") or "")
        item = {
            "local_path": str(resolved),
            "name": resolved.name,
            "drive_id": drive_id,
            "folder_id": destination,
            "status": "uploaded",
        }
        uploaded.append(item)
        manifest_entries.append({
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **item,
            "mime_type": mime_type,
            "size": len(content),
        })

    if manifest_entries:
        _write_export_manifest(manifest_entries)
    return {"uploaded": uploaded, "failed": failed}


def upload_text_to_folder(
    folder_id: str,
    filename: str,
    content: str,
    mime_type: str = "text/markdown",
    *,
    settings: DriveSettings | None = None,
    transport: DriveTransport | None = None,
) -> dict:
    """Upload text content directly to a Drive folder (for lens sync).

    If a file with the same name already exists in the folder, it is updated
    in place (Drive API update vs create).
    """
    settings = ensure_configured(settings)
    if not folder_id.strip():
        raise DriveConfigError("No folder_id provided for upload.")
    transport = transport or default_transport()
    token = _access_token(settings, transport)

    # Check if file already exists in folder
    existing_id = None
    try:
        query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        search_url = f"{DRIVE_API}/files?q={parse.quote(query)}&fields=files(id,name)"
        req = request.Request(search_url, headers={"Authorization": f"Bearer {token}"})
        with request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read())
            files = data.get("files", [])
            if files:
                existing_id = files[0]["id"]
    except Exception:
        pass  # If search fails, just create a new file

    body = content.encode("utf-8")

    if existing_id:
        # Update existing file
        url = f"https://www.googleapis.com/upload/drive/v3/files/{existing_id}?uploadType=media"
        req = request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": mime_type,
            },
            method="PATCH",
        )
    else:
        # Create new file (multipart upload)
        boundary = "---lingua-viva-sync-boundary---"
        metadata = json.dumps({
            "name": filename,
            "parents": [folder_id],
            "mimeType": mime_type,
        })
        multipart = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{metadata}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8") + body + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = request.Request(
            DRIVE_UPLOAD_API,
            data=multipart,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            method="POST",
        )

    with request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read())

    return {
        "id": result.get("id", ""),
        "name": filename,
        "folder_id": folder_id,
        "action": "updated" if existing_id else "created",
    }
