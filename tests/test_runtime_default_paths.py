import src.web as web
from src.education.student_lens import StudentLensStore, default_db_path
import src.lingua_viva.ingest as ingest


def _use_clean_lv_home(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    for name in (
        "LV_STUDENT_DB_PATH",
        "LV_DOCUMENT_STORE_PATH",
        "LV_INGEST_TMP_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


def test_student_lens_default_db_uses_lingua_viva_runtime_home(monkeypatch, tmp_path):
    _use_clean_lv_home(monkeypatch, tmp_path)

    expected = tmp_path / "runtime" / "student_lenses.db"
    assert default_db_path() == expected

    store = StudentLensStore()
    try:
        assert store.db_path == expected
    finally:
        store.close()


def test_document_store_default_uses_lingua_viva_runtime_home(monkeypatch, tmp_path):
    _use_clean_lv_home(monkeypatch, tmp_path)
    monkeypatch.setattr(ingest, "DOCUMENT_STORE_PATH", None)

    assert ingest.document_store_path() == tmp_path / "runtime" / "documents.db"


def test_ingest_temp_dir_default_uses_lingua_viva_runtime_home(monkeypatch, tmp_path):
    _use_clean_lv_home(monkeypatch, tmp_path)

    path = web._ingest_temp_dir()

    assert path == tmp_path / "runtime" / "ingest-tmp"
    assert path.exists()
