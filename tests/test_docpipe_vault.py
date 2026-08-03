from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.lingua_viva.docpipe import vault
from src.lingua_viva.docpipe.contracts import ExtractionRecord, LensRecord, SourceRecord


FIXTURES = Path(__file__).parent / "fixtures" / "docpipe"


def _load(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _text(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _lens(student_id: str, display_name: str, value: str | None = None) -> LensRecord:
    data = copy.deepcopy(_load("lens_nora_rossi.json"))
    data["student_id"] = student_id
    data["display_name"] = display_name
    data["metadata"]["source_ids"] = ["SRC-WORK-NORA-ROSSI"]
    if value is not None:
        data["profile"]["academic_strengths"]["value"] = value
    return LensRecord(data)


def test_init_creates_empty_vault(tmp_path: Path) -> None:
    record = vault.init(root=tmp_path)

    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "sources").is_dir()
    assert (tmp_path / "extracted").is_dir()
    assert (tmp_path / "lenses").is_dir()
    assert (tmp_path / "sync" / "queue.json").exists()
    assert record.data["sources"] == {}
    assert record.data["extractions"] == {}
    assert record.data["lenses"] == {}
    assert record.data["sync"]["pending_count"] == 0


def test_put_and_get_source_extraction_lens_rebuilds_manifest(tmp_path: Path) -> None:
    source = SourceRecord(_load("source_lesson_plan_marco_nora.json"))
    extraction = ExtractionRecord(_load("expected_extraction_lesson_plan_marco_nora.json"))
    lens = LensRecord(_load("lens_nora_rossi.json"))

    vault.put_source(source, _text("lesson_plan_marco_nora.md"), root=tmp_path)
    vault.put_extraction(extraction, root=tmp_path)
    vault.put_lens(lens, root=tmp_path)

    assert vault.get_source(source.source_id, root=tmp_path).data == source.data
    assert vault.get_extraction(extraction.source_id, root=tmp_path).data == extraction.data
    assert vault.get_lens(lens.student_id, root=tmp_path).data == lens.data

    (tmp_path / "manifest.json").unlink()
    rebuilt = vault.manifest(root=tmp_path).data
    assert set(rebuilt["sources"]) == {source.source_id}
    assert set(rebuilt["extractions"]) == {extraction.source_id}
    assert set(rebuilt["lenses"]) == {lens.student_id}


def test_invalid_lens_payload_is_rejected_without_persisting(tmp_path: Path) -> None:
    good = LensRecord(_load("lens_nora_rossi.json"))
    vault.put_lens(good, root=tmp_path)

    bad_data = copy.deepcopy(good.data)
    bad_data["profile"]["academic_strengths"]["evidence"] = []

    with pytest.raises(ValueError):
        vault.put_lens(LensRecord(bad_data), root=tmp_path)

    assert vault.get_lens(good.student_id, root=tmp_path).data == good.data


def test_crash_before_rename_leaves_prior_lens_intact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _lens("student-nora-rossi", "Nora Rossi", "Original grounded value.")
    replacement = _lens("student-nora-rossi", "Nora Rossi", "Replacement grounded value.")
    vault.put_lens(original, root=tmp_path)

    real_replace = vault._replace

    def crash_once(src: Path, dst: Path) -> None:
        if dst.name == "lens.json":
            raise RuntimeError("simulated crash before rename")
        real_replace(src, dst)

    monkeypatch.setattr(vault, "_replace", crash_once)
    with pytest.raises(RuntimeError):
        vault.put_lens(replacement, root=tmp_path)

    assert vault.get_lens("student-nora-rossi", root=tmp_path).data == original.data


def test_concurrent_writes_to_different_lenses_succeed(tmp_path: Path) -> None:
    ids = [f"student-{idx}" for idx in range(8)]

    def write(student_id: str) -> str:
        record = _lens(student_id, f"Student {student_id}", f"Grounded value {student_id}")
        vault.put_lens(record, root=tmp_path)
        return student_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert set(executor.map(write, ids)) == set(ids)

    manifest = vault.manifest(root=tmp_path).data
    assert set(manifest["lenses"]) == set(ids)
    for student_id in ids:
        assert vault.get_lens(student_id, root=tmp_path).student_id == student_id


def test_concurrent_writes_to_same_lens_serialize(tmp_path: Path) -> None:
    values = [f"Grounded value {idx}" for idx in range(12)]

    def write(value: str) -> str:
        vault.put_lens(_lens("student-nora-rossi", "Nora Rossi", value), root=tmp_path)
        return value

    with ThreadPoolExecutor(max_workers=6) as executor:
        assert sorted(executor.map(write, values)) == sorted(values)

    final = vault.get_lens("student-nora-rossi", root=tmp_path).data
    assert final["profile"]["academic_strengths"]["value"] in values
    assert vault.manifest(root=tmp_path).data["lenses"]["student-nora-rossi"]["display_name"] == "Nora Rossi"


def test_put_source_rejects_sha_mismatch(tmp_path: Path) -> None:
    data = _load("source_lesson_plan_marco_nora.json")
    data["sha256"] = "0" * 64

    with pytest.raises(ValueError):
        vault.put_source(SourceRecord(data), _text("lesson_plan_marco_nora.md"), root=tmp_path)

    assert not (tmp_path / "sources" / data["source_id"] / "source.json").exists()
