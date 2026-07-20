"""Service-worker + surface parity (MC-lessons §4).

MC found `docs/sw.js` a full version behind `static/sw.js` — dual-surface
drift that shipped stale caches to the public surface. LV has only one live
surface (`static/index.html` + `static/sw.js`); `runtime/hub/` was a second,
undispositioned surface from the Mission Canvas fork import — archived to
`archive/mc-engine/runtime/hub/` (see ARCHIVED.md there) since it was never
live (only started by the already-broken fork-era `setup.sh`, never
referenced by `src/web.py`/`lv`/`desktop/`).

This test pins both facts so future drift or a resurrected second surface
fails loudly instead of accumulating silently.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_cache_name_defined_in_exactly_one_place():
    sw_files = list(REPO.glob("**/sw.js"))
    # Exclude archived/legacy trees, node_modules, and gitignored build
    # output (desktop/release/ — electron-builder's extraResources copies
    # static/ verbatim into the packaged app, MC-lessons §9) from the
    # live-surface count.
    excluded_parts = {"archive", "node_modules", "release", "dist"}
    live_sw_files = [
        p for p in sw_files
        if excluded_parts.isdisjoint(p.parts)
    ]
    assert live_sw_files == [REPO / "static" / "sw.js"], (
        f"expected exactly one live sw.js at static/sw.js, found: {live_sw_files}"
    )

    text = live_sw_files[0].read_text(encoding="utf-8")
    definitions = re.findall(r'^const CACHE_NAME\s*=\s*"([^"]+)"', text, flags=re.M)
    assert len(definitions) == 1, "CACHE_NAME must be defined exactly once in static/sw.js"


def test_runtime_hub_is_archived_not_live():
    assert not (REPO / "runtime" / "hub").exists(), (
        "runtime/hub/ should stay archived at archive/mc-engine/runtime/hub/ "
        "— see §4 disposition in ARCHIVED.md there"
    )
    assert (REPO / "archive" / "mc-engine" / "runtime" / "hub" / "ARCHIVED.md").is_file()


def test_runtime_package_json_has_no_dangling_hub_scripts():
    import json

    data = json.loads((REPO / "runtime" / "package.json").read_text(encoding="utf-8"))
    scripts = data.get("scripts", {})
    for name, cmd in scripts.items():
        assert "hub/" not in cmd, f"runtime/package.json script {name!r} references archived hub/: {cmd!r}"
