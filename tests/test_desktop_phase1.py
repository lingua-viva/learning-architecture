import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"


def test_desktop_release_workflow_publishes_debian_artifact():
    release_workflow = (ROOT / ".github" / "workflows" / "desktop-release.yml").read_text()
    auto_release = (ROOT / ".github" / "workflows" / "auto-release.yml").read_text()
    assert "dist_args: --linux AppImage deb" in release_workflow
    assert "release/LinguaViva.deb" in release_workflow
    assert "artifacts/LinguaViva.deb" in release_workflow
    assert "LinguaViva.deb" in auto_release


def test_desktop_package_targets_all_required_installers():
    package = json.loads((DESKTOP / "package.json").read_text())
    assert package["name"] == "lingua-viva-desktop"
    assert package["build"]["productName"] == "Lingua Viva"
    assert package["build"]["mac"]["target"] == ["dmg"]
    assert package["build"]["win"]["target"] == ["nsis"]
    assert package["build"]["linux"]["target"] == ["AppImage", "deb"]
    assert package["build"]["linux"]["maintainer"] == "Lingua Viva <hello@linguaviva.art>"
    assert package["build"]["deb"]["afterInstall"] == "electron/deb-after-install.sh"
    assert package["homepage"] == "https://linguaviva.art"


def test_debian_package_forces_electron_sandbox_helper_setuid():
    script = (DESKTOP / "electron" / "deb-after-install.sh").read_text()
    assert "update-alternatives --install" in script
    assert "chmod 4755 '/opt/${sanitizedProductName}/chrome-sandbox'" in script
    assert "update-desktop-database /usr/share/applications" in script


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


def test_import_copy_describes_preview_first_not_auto_create():
    """F5: the import box must not lie about the creation model."""
    html = (ROOT / "static" / "index.html").read_text()
    # The old auto-create copy must be gone.
    assert "Every student gets a profile automatically" not in html
    assert "one click undoes the whole import" not in html
    # The preview-first truth must be present.
    assert "Nothing is created until you review and confirm" in html
