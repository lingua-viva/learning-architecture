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
