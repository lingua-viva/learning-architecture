import builtins
import os
from pathlib import Path

from fastapi.testclient import TestClient

from src.lingua_viva import cli, filemap
from src.lingua_viva.filemap import (
    FileMap,
    FileMapEntry,
    ScanRoot,
    add_exclusion,
    build_filemap_context,
    clear_map,
    infer_education_domain,
    infer_sensitivity,
    get_confirmed_extraction_inputs,
    is_student_data_zone,
    list_files_in_zone,
    load_map,
    run_scan,
    save_map,
    scan_directory,
)
from src.web import app


client = TestClient(app)


def _map_path(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "home" / ".lingua-viva" / "file_map.yaml"
    monkeypatch.setenv("LV_FILE_MAP_PATH", str(path))
    return path


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "Teaching"
    for folder in (
        "curriculum/G3",
        "assessment/rubrics",
        "cefr/checklists",
        "programmazione",
        "valutazione",
        "Students/reports",
        ".git",
        "node_modules",
        "__pycache__",
    ):
        (root / folder).mkdir(parents=True, exist_ok=True)
    for index in range(3):
        (root / "curriculum" / "G3" / f"unit-{index}.pdf").write_text("x", encoding="utf-8")
    (root / "assessment" / "rubrics" / "rubric.pdf").write_text("x", encoding="utf-8")
    (root / "cefr" / "checklists" / "a1.pdf").write_text("x", encoding="utf-8")
    (root / "Students" / "reports" / "private.txt").write_text("x", encoding="utf-8")
    return root


def test_scan_directory_returns_entries(tmp_path):
    entries = scan_directory(_tree(tmp_path))
    assert entries


def test_depth_limit_respected(tmp_path):
    entries = scan_directory(_tree(tmp_path), max_depth=0)
    assert {entry.depth for entry in entries} == {0}


def test_hidden_dirs_skipped(tmp_path):
    entries = scan_directory(_tree(tmp_path))
    assert not any(".git" in entry.path for entry in entries)


def test_skip_dirs_skipped(tmp_path):
    entries = scan_directory(_tree(tmp_path))
    paths = "\n".join(entry.path for entry in entries)
    assert "node_modules" not in paths
    assert "__pycache__" not in paths


def test_symlinks_not_followed(tmp_path):
    root = _tree(tmp_path)
    target = tmp_path / "outside" / "curriculum"
    target.mkdir(parents=True)
    (root / "linked").symlink_to(target, target_is_directory=True)
    entries = scan_directory(root)
    assert not any("linked" in entry.path for entry in entries)


def test_student_data_zones_excluded(tmp_path):
    entries = scan_directory(_tree(tmp_path))
    assert not any("Students" in entry.path for entry in entries)


def test_student_zones_logged(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    mapped = run_scan(_tree(tmp_path))
    assert any("Students" in path for path in mapped.student_zones)


def test_scan_never_uses_builtin_open(monkeypatch, tmp_path):
    root = _tree(tmp_path)

    def blocked(*args, **kwargs):
        raise AssertionError("scanner must not open file contents")

    monkeypatch.setattr(builtins, "open", blocked)
    scan_directory(root)


def test_infer_education_domain_curriculum():
    assert infer_education_domain("~/curriculum/G3") == "curriculum"


def test_infer_education_domain_none():
    assert infer_education_domain("~/Photos") is None


def test_infer_sensitivity_high():
    assert infer_sensitivity("~/Students/reports") == "high"


def test_infer_sensitivity_low():
    assert infer_sensitivity("~/Teaching/resources") == "low"


def test_italian_keywords_work():
    assert infer_education_domain("~/programmazione") == "curriculum"
    assert infer_education_domain("~/valutazione") == "assessment"


def test_save_load_round_trip(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    curriculum = tmp_path / "curriculum"
    student_file = tmp_path / "Students" / "notes.txt"
    save_map(FileMap(
        roots=[ScanRoot(path=str(tmp_path), scanned_at="now")],
        entries=[FileMapEntry(path=str(curriculum), file_count=1, total_size_bytes=1, last_modified="now")],
        confirmations={str(curriculum): "curriculum_source"},
        student_assignments=[{
            "file_path": str(student_file),
            "assigned_student_id": "student-1",
            "assigned_purpose": "student_lens_source",
        }],
    ))
    loaded = load_map()
    assert loaded.roots
    assert loaded.entries[0].file_count == 1
    assert loaded.confirmations[str(curriculum)] == "curriculum_source"
    assert loaded.student_assignments[0]["assigned_student_id"] == "student-1"


def test_file_permissions(monkeypatch, tmp_path):
    path = _map_path(monkeypatch, tmp_path)
    save_map(FileMap())
    assert path.stat().st_mode & 0o777 == 0o600


def test_multi_root_scan_preserves_existing(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    first = _tree(tmp_path / "a")
    second = _tree(tmp_path / "b")
    run_scan(first)
    mapped = run_scan(second)
    assert len(mapped.roots) == 2


def test_add_exclusion_removes_entries(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    root = _tree(tmp_path)
    run_scan(root)
    mapped = add_exclusion(root / "curriculum")
    assert not any("curriculum" in entry.path for entry in mapped.entries)


def test_clear_map(monkeypatch, tmp_path):
    path = _map_path(monkeypatch, tmp_path)
    save_map(FileMap(roots=[ScanRoot(path=str(tmp_path), scanned_at="now")]))
    clear_map()
    assert not path.exists()
    assert load_map().roots == []


def test_api_scan_returns_summary(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    response = client.post("/api/filemap/scan", json={"root_path": str(_tree(tmp_path)), "max_depth": 3})
    assert response.status_code == 200
    assert response.json()["total_entries"] > 0
    assert "student_zones_detected" in response.json()


def test_api_scan_invalid_path(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    response = client.post("/api/filemap/scan", json={"root_path": str(tmp_path / "missing")})
    assert response.status_code == 400


def test_api_get_redacts_home(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    home_root = Path.home() / "Teaching"
    save_map(FileMap(entries=[FileMapEntry(path=str(home_root), file_count=0, total_size_bytes=0, last_modified="now")]))
    response = client.get("/api/filemap")
    body = response.text
    assert str(Path.home()) not in body
    assert "~" in body


def test_api_get_lists_detected_student_zones(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    save_map(FileMap(student_zones=[str(tmp_path / "Students" / "reports")]))
    response = client.get("/api/filemap")
    assert response.json()["student_zones_detected"] == 1
    assert response.json()["student_zones"]


def test_api_confirm_round_trip(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    root = _tree(tmp_path)
    run_scan(root)
    target = root / "curriculum"
    response = client.post(
        "/api/filemap/confirm",
        json={"path": str(target), "purpose": "curriculum_source"},
    )
    assert response.status_code == 200
    assert load_map().confirmations[str(target.resolve())] == "curriculum_source"


def test_confirmed_curriculum_files_feed_extraction_inputs(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    root = _tree(tmp_path)
    run_scan(root)
    target = root / "curriculum" / "G3"
    client.post(
        "/api/filemap/confirm",
        json={"path": str(target), "purpose": "curriculum_source"},
    )
    inputs = get_confirmed_extraction_inputs()
    assert len(inputs) == 3
    assert {item["target_schema_id"] for item in inputs} == {"curriculum_unit"}
    assert all(Path(item["file_path"]).is_absolute() for item in inputs)
    assert all(item["hint"]["confirmed_folder"] == str(target.resolve()) for item in inputs)


def test_api_confirm_rejects_unknown_path(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    save_map(FileMap())
    response = client.post(
        "/api/filemap/confirm",
        json={"path": str(tmp_path), "purpose": "curriculum_source"},
    )
    assert response.status_code == 400


def test_rescan_prunes_confirmation_for_removed_entry(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    root = _tree(tmp_path)
    run_scan(root)
    target = root / "curriculum"
    client.post(
        "/api/filemap/confirm",
        json={"path": str(target), "purpose": "curriculum_source"},
    )
    target.rename(root / "renamed")
    mapped = run_scan(root)
    assert mapped.confirmations == {}


def test_rescan_prunes_removed_student_zone_and_assignment(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    root = _tree(tmp_path)
    mapped = run_scan(root)
    zone = Path(mapped.student_zones[0])
    direct_file = zone / "assigned.pdf"
    direct_file.write_bytes(b"synthetic")
    filemap.assign_student_file(direct_file, "student-1")
    for child in sorted(zone.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    zone.rmdir()
    mapped = run_scan(root)
    assert mapped.student_zones == []
    assert mapped.student_assignments == []


def test_exclusion_prunes_confirmation(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    root = _tree(tmp_path)
    run_scan(root)
    target = root / "curriculum"
    client.post(
        "/api/filemap/confirm",
        json={"path": str(target), "purpose": "curriculum_source"},
    )
    mapped = add_exclusion(target)
    assert mapped.confirmations == {}


def test_zone_peek_lists_metadata_without_opening_content(monkeypatch, tmp_path):
    zone = _tree(tmp_path) / "Students"

    def blocked(*args, **kwargs):
        raise AssertionError("peek must not open file contents")

    monkeypatch.setattr(builtins, "open", blocked)
    items = list_files_in_zone(zone)
    assert items[0]["type"] == "directory"
    assert set(items[0]) == {"name", "path", "type", "size_bytes", "modified_at"}


def test_zone_peek_rejects_zone_symlink(tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    zone_link = tmp_path / "Students"
    zone_link.symlink_to(target, target_is_directory=True)
    try:
        list_files_in_zone(zone_link)
    except ValueError as exc:
        assert "symbolic link" in str(exc)
    else:
        raise AssertionError("zone symlink should be rejected")


def test_api_zone_peek_rejects_zone_replaced_by_symlink(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    root = _tree(tmp_path)
    mapped = run_scan(root)
    zone = Path(mapped.student_zones[0])
    for child in sorted(zone.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    zone.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    zone.symlink_to(outside, target_is_directory=True)
    response = client.post("/api/filemap/peek", json={"zone_path": str(zone)})
    assert response.status_code == 400
    assert "symbolic link" in response.json()["error"]


def test_api_peek_rejects_path_not_in_student_zones(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    arbitrary = tmp_path / "arbitrary"
    arbitrary.mkdir()
    save_map(FileMap())
    response = client.post("/api/filemap/peek", json={"zone_path": str(arbitrary)})
    assert response.status_code == 400
    assert "not a detected student zone" in response.json()["error"]


def test_api_peek_and_manual_assignment_persist(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    root = _tree(tmp_path)
    mapped = run_scan(root)
    zone = next(path for path in mapped.student_zones if Path(path).name == "Students")
    student_file = Path(zone) / "profile.pdf"
    student_file.write_bytes(b"synthetic")

    peek = client.post("/api/filemap/peek", json={"zone_path": zone})
    assert peek.status_code == 200
    file_item = next(item for item in peek.json()["items"] if item["name"] == "profile.pdf")
    assert set(file_item) == {"name", "path", "type", "size_bytes", "modified_at"}

    student = client.post("/api/students", json={"display_name": "Synthetic Learner"}).json()
    assigned = client.post(
        "/api/filemap/assign",
        json={"file_path": file_item["path"], "assigned_student_id": student["student_id"]},
    )
    assert assigned.status_code == 200
    assert load_map().student_assignments[0]["assigned_student_id"] == student["student_id"]
    extraction_inputs = get_confirmed_extraction_inputs()
    assert extraction_inputs[0]["target_schema_id"] == "student_lens"
    assert extraction_inputs[0]["hint"]["assigned_student_id"] == student["student_id"]

    unassigned = client.post(
        "/api/filemap/assign",
        json={"file_path": file_item["path"], "assigned_student_id": None},
    )
    assert unassigned.status_code == 200
    assert load_map().student_assignments == []
    assert get_confirmed_extraction_inputs() == []


def test_api_assignment_rejects_unknown_student(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    mapped = run_scan(_tree(tmp_path))
    zone = Path(mapped.student_zones[0])
    student_file = zone / "profile.pdf"
    student_file.write_bytes(b"synthetic")
    response = client.post(
        "/api/filemap/assign",
        json={"file_path": str(student_file), "assigned_student_id": "unknown"},
    )
    assert response.status_code == 400
    assert "not in the current roster" in response.json()["error"]


def test_api_exclude_adds_exclusion(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    target = _tree(tmp_path) / "curriculum"
    response = client.post("/api/filemap/exclude", json={"path": str(target), "action": "add"})
    assert response.status_code == 200
    assert response.json()["summary"]["configured"] is False
    assert load_map().exclusions


def test_api_clear_returns_empty(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    save_map(FileMap(entries=[FileMapEntry(path=str(tmp_path), file_count=0, total_size_bytes=0, last_modified="now")]))
    response = client.post("/api/filemap/clear")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert load_map().entries == []


def test_brief_includes_filemap_when_exists(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    save_map(FileMap(roots=[ScanRoot(path=str(tmp_path), scanned_at="now")], entries=[
        FileMapEntry(path=str(tmp_path / "curriculum"), file_count=1, total_size_bytes=1, last_modified="now", inferred_domain="curriculum")
    ]))
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    response = client.get("/api/brief")
    assert response.json()["filemap"]["root_count"] == 1


def test_brief_filemap_null_when_empty(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    response = client.get("/api/brief")
    assert response.json()["filemap"] is None


def test_build_filemap_context_curriculum_match(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    save_map(FileMap(entries=[
        FileMapEntry(path=str(tmp_path / "curriculum"), file_count=2, total_size_bytes=2, last_modified="now", inferred_domain="curriculum")
    ]))
    assert "curriculum folders" in build_filemap_context("curriculum")


def test_build_filemap_context_no_external_paths(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    save_map(FileMap(entries=[
        FileMapEntry(path=str(tmp_path / "curriculum"), file_count=2, total_size_bytes=2, last_modified="now", inferred_domain="curriculum")
    ]))
    assert build_filemap_context("curriculum", local_only=False) == ""


def test_cli_filemap_scan(monkeypatch, tmp_path, capsys):
    _map_path(monkeypatch, tmp_path)
    assert cli.main(["filemap", "scan", str(_tree(tmp_path))]) == 0
    assert "Scanned" in capsys.readouterr().out


def test_cli_filemap_show(monkeypatch, tmp_path, capsys):
    _map_path(monkeypatch, tmp_path)
    save_map(FileMap(roots=[ScanRoot(path=str(tmp_path), scanned_at="now", domain_summary={"curriculum": 1})]))
    assert cli.main(["filemap", "show"]) == 0
    output = capsys.readouterr().out
    assert "roots" in output or "curriculum" in output


def test_student_data_zone_detector():
    assert is_student_data_zone("~/Students/reports")
