from __future__ import annotations

import os
from pathlib import Path


def runtime_data_dir(component: str = "") -> Path:
    """Return the sanctioned writable runtime directory for local app state.

    Runtime state must never default to a path derived from ``__file__``: in a
    packaged desktop app that can be inside a signed/read-only bundle, and in
    tests it dirties the source tree. ``LV_STATE_HOME`` is the app-wide state
    override; absent that, use the user's Lingua Viva home.
    """
    home = Path(os.environ.get("LV_STATE_HOME") or Path.home() / ".lingua-viva")
    base = home / "runtime"
    if component:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in component)
        base = base / (safe or "app")
    base.mkdir(parents=True, exist_ok=True)
    return base


def memory_data_dir() -> Path:
    """Sanctioned location for the path-memory NDJSON stores.

    Replaces the ``memory/data`` source-tree default (third instance of the
    ``Path(__file__)`` write-location class, closed 2026-08-08). Existing
    dev-machine data must be moved once by the operator:
    ``cp -r memory/data/* ~/.lingua-viva/runtime/memory/``.
    """
    return runtime_data_dir("memory")
