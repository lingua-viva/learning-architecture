from __future__ import annotations

from pathlib import Path

from .contracts import DriveItem, DriveWriteResult, SourceBytes


def list_folder(folder_ref: str, *, recursive: bool = False) -> list[DriveItem]:
    raise NotImplementedError("T1 implements Drive folder listing")


def fetch_file(file_ref: str) -> SourceBytes:
    raise NotImplementedError("T1 implements Drive file fetching")


def push_file(
    local_path: Path,
    destination_ref: str,
    *,
    mime: str | None = None,
) -> DriveWriteResult:
    raise NotImplementedError("T6 implements Drive write-back")

