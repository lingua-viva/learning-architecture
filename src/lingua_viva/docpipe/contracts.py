from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class DriveItem:
    file_ref: str
    name: str
    mime: str
    path: str
    origin: Literal["drive"] = "drive"
    modified_at: str | None = None
    byte_size: int | None = None


@dataclass(frozen=True)
class SourceBytes:
    file_ref: str
    filename: str
    mime: str
    content: bytes
    origin: Literal["drive", "local"]
    path: str
    drive_file_id: str | None = None
    owner: str | None = None


@dataclass(frozen=True)
class DriveWriteResult:
    destination_ref: str
    path: str
    pushed_at: str
    status: Literal["pushed", "queued"]
    drive_file_id: str | None = None


@dataclass(frozen=True)
class SourceRecord:
    data: JsonObject

    @property
    def source_id(self) -> str:
        return str(self.data["source_id"])

    @property
    def original_ext(self) -> str:
        return str(self.data.get("original_ext") or "")


@dataclass(frozen=True)
class ExtractionRecord:
    data: JsonObject

    @property
    def source_id(self) -> str:
        return str(self.data["source_id"])


@dataclass(frozen=True)
class LensRecord:
    data: JsonObject

    @property
    def student_id(self) -> str:
        return str(self.data["student_id"])


@dataclass(frozen=True)
class ObservationRecord:
    data: JsonObject

    @property
    def obs_id(self) -> str:
        return str(self.data["obs_id"])

    @property
    def student_id(self) -> str:
        return str(self.data["student_id"])


@dataclass(frozen=True)
class ManifestRecord:
    data: JsonObject


@dataclass(frozen=True)
class GroundingIssue:
    path: str
    message: str


@dataclass(frozen=True)
class GroundingReport:
    ok: bool
    issues: tuple[GroundingIssue, ...] = ()


PathLike = str | Path

