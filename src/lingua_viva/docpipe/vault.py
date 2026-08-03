from __future__ import annotations

import os
from pathlib import Path

from src.lingua_viva import config

from .contracts import ExtractionRecord, LensRecord, ManifestRecord, SourceRecord


def vault_root() -> Path:
    state_home = os.environ.get("LV_STATE_HOME")
    base = Path(state_home) if state_home else config.lv_home()
    return base / "vault"


def _root(root: Path | None = None) -> Path:
    return root if root is not None else vault_root()


def put_source(
    source: SourceRecord,
    content: bytes,
    *,
    root: Path | None = None,
) -> SourceRecord:
    _root(root)
    raise NotImplementedError("T2 implements vault source persistence")


def get_source(source_id: str, *, root: Path | None = None) -> SourceRecord:
    _root(root)
    raise NotImplementedError("T2 implements vault source reads")


def put_extraction(
    extraction: ExtractionRecord,
    *,
    root: Path | None = None,
) -> ExtractionRecord:
    _root(root)
    raise NotImplementedError("T2 implements vault extraction persistence")


def get_extraction(source_id: str, *, root: Path | None = None) -> ExtractionRecord:
    _root(root)
    raise NotImplementedError("T2 implements vault extraction reads")


def get_lens(student_id: str, *, root: Path | None = None) -> LensRecord:
    _root(root)
    raise NotImplementedError("T2 implements vault lens reads")


def put_lens(lens: LensRecord, *, root: Path | None = None) -> LensRecord:
    _root(root)
    raise NotImplementedError("T2 implements vault lens persistence")


def manifest(*, root: Path | None = None) -> ManifestRecord:
    _root(root)
    raise NotImplementedError("T2 implements manifest reads")

