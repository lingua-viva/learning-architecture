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


def test_release_pipeline_uses_lingua_viva_binary_contract():
    release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    install_test = (ROOT / ".github" / "workflows" / "install-test.yml").read_text(encoding="utf-8")
    unix_installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    windows_installer = (ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "pyinstaller lv.spec" in release_workflow
    assert "mc.spec" not in release_workflow
    assert "LV_CONFIG_HOME" in release_workflow
    assert "STILL_I_RISE_HOME" not in release_workflow
    assert '"dist/${{ matrix.name }}" health --json' in release_workflow
    assert '"dist/${{ matrix.name }}" preflight' not in release_workflow
    assert '"dist/${{ matrix.name }}" status' not in release_workflow
    assert all(asset in release_workflow for asset in ("lv-darwin-arm64", "lv-linux-x86_64", "lv-windows-x86_64.exe"))
    assert not any(asset in release_workflow for asset in ("sir-darwin-arm64", "sir-linux-x86_64", "sir-windows-x86_64.exe"))

    assert "$HOME/.local/bin/lv" in install_test
    assert "$HOME/.local/bin/sir" not in install_test
    assert '"$HOME/.local/bin/lv" health --json' in install_test
    assert '"$HOME/.local/bin/lv" preflight' not in install_test
    assert '"$HOME/.local/bin/lv" status' not in install_test
    assert 'grep -q "Lingua Viva health:"' in install_test

    assert "python3 -m src.lv_cli health" in unix_installer
    assert 'cd "$INSTALL_DIR" && exec python3 -m src.lv_cli "\\$@"' in unix_installer
    assert 'exec python3 "$INSTALL_DIR/src/lv_cli.py" "$@"' not in unix_installer

    assert "lv-windows-${arch}.exe" in windows_installer
    assert "$env:USERPROFILE\\.lingua-viva" in windows_installer
    assert "src\\lv_cli.py" in windows_installer
    assert "python -m src.lv_cli health" in windows_installer
    assert "http://localhost:8787" in windows_installer
    assert not any(term in windows_installer for term in ("Still I Rise", ".still-i-rise", "src\\mc_cli.py", "7896"))
