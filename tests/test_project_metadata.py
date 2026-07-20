import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STALE_PRODUCT_TERMS = ("still-i-rise", "mission-canvas", "Mission Canvas", "Governed Agent OS")


def test_python_project_metadata_is_lingua_viva_branded():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]

    assert project["name"] == "lingua-viva"
    assert "Lingua Viva" in project["description"]
    assert not any(term in project["name"] for term in STALE_PRODUCT_TERMS)
    assert not any(term in project["description"] for term in STALE_PRODUCT_TERMS)


def test_runtime_package_metadata_is_lingua_viva_branded():
    package = json.loads((ROOT / "runtime" / "package.json").read_text(encoding="utf-8"))

    assert package["name"] == "lingua-viva-runtime"
    assert "Lingua Viva" in package["description"]
    assert not any(term in package["name"] for term in STALE_PRODUCT_TERMS)
    assert not any(term in package["description"] for term in STALE_PRODUCT_TERMS)
