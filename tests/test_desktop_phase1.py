import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"


def test_desktop_package_targets_all_required_installers():
    package = json.loads((DESKTOP / "package.json").read_text())
    assert package["name"] == "lingua-viva-desktop"
    assert package["build"]["productName"] == "Lingua Viva"
    assert package["build"]["mac"]["target"] == ["dmg"]
    assert package["build"]["win"]["target"] == ["nsis"]
    assert package["build"]["linux"]["target"] == ["AppImage"]


def test_electron_shell_starts_backend_on_required_port():
    main = (DESKTOP / "electron" / "main.ts").read_text()
    bootstrap = (DESKTOP / "electron" / "bootstrap.ts").read_text()
    wizard = (DESKTOP / "electron" / "setup-wizard.html").read_text()
    assert "BrowserWindow" in main
    assert "contextIsolation: true" in main
    assert "sandbox: true" in main
    assert "nodeIntegration: false" in main
    assert "http://127.0.0.1:8787" in main
    assert "Setting up your teacher workbench" in wizard
    assert "Everything stays on your machine" in wizard
    assert "detectPython" in main
    assert "checkOllama" in main
    assert "python3" in bootstrap
    assert "src\", \"web.py" in bootstrap


def test_electron_preload_exposes_minimal_bridge():
    preload = (DESKTOP / "electron" / "preload.ts").read_text()
    assert "contextBridge.exposeInMainWorld" in preload
    assert "lvDesktop" in preload
    assert "readFile" in preload
    assert "onBackendReady" in preload
