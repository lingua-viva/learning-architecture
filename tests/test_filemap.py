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
    is_student_data_zone,
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
    save_map(FileMap(
        roots=[ScanRoot(path=str(tmp_path), scanned_at="now")],
        entries=[FileMapEntry(path=str(tmp_path / "curriculum"), file_count=1, total_size_bytes=1, last_modified="now")],
    ))
    loaded = load_map()
    assert loaded.roots
    assert loaded.entries[0].file_count == 1


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


def test_api_get_hides_student_zone_paths(monkeypatch, tmp_path):
    _map_path(monkeypatch, tmp_path)
    save_map(FileMap(student_zones=[str(tmp_path / "Students" / "reports")]))
    response = client.get("/api/filemap")
    assert response.json()["student_zones_detected"] == 1
    assert "Students" not in response.text


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
