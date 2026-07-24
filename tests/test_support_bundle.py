import json
from pathlib import Path

from src.lingua_viva.support_bundle import SupportBundleService


def _create_bundle(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx").write_text("private manual")
    (repo / "student_lens.db").write_text("student data")
    (repo / "parent_reports").mkdir()
    (repo / "parent_reports" / "draft.txt").write_text("parent message")
    service = SupportBundleService(repo_root=repo, support_root=tmp_path / "support")
    return service.create_bundle()


def test_bundle_creates_directory(tmp_path):
    result = _create_bundle(tmp_path)

    assert result["status"] == "OK"
    assert Path(result["bundle_path"]).is_dir()


def test_bundle_excludes_docx(tmp_path):
    result = _create_bundle(tmp_path)
    manifest = json.loads(Path(result["manifest_path"]).read_text())

    assert any(item["path"].endswith(".docx") for item in manifest["excluded"])
    assert not any(path.name.endswith(".docx") for path in Path(result["bundle_path"]).iterdir())


def test_bundle_excludes_student_data_patterns(tmp_path):
    result = _create_bundle(tmp_path)
    manifest = json.loads(Path(result["manifest_path"]).read_text())

    excluded = "\n".join(item["path"] for item in manifest["excluded"])
    assert "student_lens.db" in excluded
    assert "parent_reports" in excluded


def test_bundle_excludes_google_drive_imports(tmp_path):
    repo = tmp_path / "repo"
    drive_dir = repo / "runtime" / "drive_imports"
    drive_dir.mkdir(parents=True)
    (drive_dir / "student.pdf").write_text("student source text", encoding="utf-8")
    (drive_dir / "import_manifest.json").write_text('{"imports":[]}', encoding="utf-8")
    service = SupportBundleService(repo_root=repo, support_root=tmp_path / "support")
    result = service.create_bundle()
    manifest = json.loads(Path(result["manifest_path"]).read_text())

    excluded = "\n".join(item["path"] for item in manifest["excluded"])
    assert "runtime/drive_imports/student.pdf" in excluded
    assert "runtime/drive_imports/import_manifest.json" in excluded


def test_bundle_includes_manifest(tmp_path):
    result = _create_bundle(tmp_path)
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text())

    assert manifest_path.exists()
    assert manifest["checks"]["external_upload"] is False
    assert manifest["checks"]["docx_content_included"] is False


def test_bundle_includes_redaction_report(tmp_path):
    result = _create_bundle(tmp_path)
    report = Path(result["bundle_path"]) / "REDACTION_REPORT.md"

    assert report.exists()
    assert ".docx source/private drafts" in report.read_text()
