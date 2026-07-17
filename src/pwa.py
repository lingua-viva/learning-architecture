"""PWA manifest helpers for Lingua Viva instances."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


LV_ROOT = Path(__file__).parent.parent
DEFAULT_MANIFEST = LV_ROOT / "static" / "manifest.json"


ENV_OVERRIDES = {
    "LV_PWA_NAME": "name",
    "LV_PWA_SHORT_NAME": "short_name",
    "LV_PWA_DESCRIPTION": "description",
    "LV_PWA_THEME_COLOR": "theme_color",
    "LV_PWA_BACKGROUND_COLOR": "background_color",
    "LV_PWA_START_URL": "start_url",
}


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text())


def build_manifest(path: Path = DEFAULT_MANIFEST, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return the default manifest with per-instance environment overrides.

    This keeps the shipped PWA static by default while allowing deploy scripts or
    a future instance setup command to brand each client instance.
    """
    source = os.environ if env is None else env
    manifest = deepcopy(load_manifest(path))
    for env_name, key in ENV_OVERRIDES.items():
        value = source.get(env_name)
        if value:
            manifest[key] = value

    default_intent = source.get("LV_PWA_DEFAULT_INTENT", "").upper()
    if default_intent and "LV_PWA_START_URL" not in source:
        manifest["start_url"] = f"/?intent={default_intent}"

    return manifest
