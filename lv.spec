# lv.spec — PyInstaller build spec for the Lingua Viva / Learning Architecture
# engine (Lingua Viva, education fork).
#
# Cloned from Lingua Viva/lv.spec — that spec is the result of a month of
# PyInstaller debugging (App Translocation, frozen-bundle health-check
# crashes, Windows strip.exe DLL corruption — see
# Lingua Viva/dev/INVESTIGATION_NAKED_INSTALL_MACOS.md). Do not redesign
# this from scratch; only adapt datas/hiddenimports to what this repo
# actually ships and imports.
#
# Build: pyinstaller lv.spec --clean --noconfirm
# Output: dist/lv (single binary)
#
# Named 'lv' (Lingua Viva). It installs to ~/.local/bin/lv.

import sys

a = Analysis(
    ['src/lv_cli.py'],
    pathex=['.'],
    datas=[
        ('ontology', 'ontology'),
        ('knowledge', 'knowledge'),
        ('lenses', 'lenses'),
        ('static', 'static'),
        ('config', 'config'),
        # Version stamp — same reasoning as MC's lv.spec: without this,
        # frozen binaries can't report their own version.
        ('pyproject.toml', '.'),
    ],
    hiddenimports=[
        'yaml',
        'redis',
        'fastapi',
        'uvicorn',
        'uvicorn.lifespan.on',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'websockets',
        'pdfplumber',
        'sqlite_vec',
        # This repo's real UI-serving module (FastAPI + WebSocket, serves
        # static/index.html) — the app's FastAPI entry point.
        # src.web. Must be a hidden import: lv_cli.py only imports
        # it lazily inside _start_web_server(), which PyInstaller's static
        # analysis can't see.
        'src.web',
        # Pulled in transitively by pdfplumber's dependency chain through
        # pkg_resources's runtime hook (pyi_rth_pkgres) — modern setuptools
        # de-vendored its pkg_resources.extern names (see
        # pkg_resources/extern/__init__.py's `names` tuple: packaging,
        # platformdirs, jaraco, importlib_resources, more_itertools), so
        # PyInstaller's static analysis misses them unless listed here.
        # Confirmed by two real local build failures: "ImportError: The
        # 'jaraco' package is required", then "...'platformdirs' package
        # is required" at dist/lv runtime.
        'jaraco.text',
        'jaraco.functools',
        'jaraco.context',
        'jaraco.collections',
        'packaging',
        'platformdirs',
        'importlib_resources',
        'more_itertools',
    ],
    excludes=['tkinter', 'matplotlib', 'numpy', 'PIL', 'scipy'],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='lv',
    # Never strip on Windows: a `strip.exe` on PATH (Git for Windows ships
    # one) corrupts the bundled python3xx.dll -> "Failed to load Python
    # DLL". Same fix MC applied. Strip is safe/useful on Linux/macOS.
    strip=(sys.platform != 'win32'),
    onefile=True,
)
