"""PWA manifest helpers for client-specific Mission Canvas instances."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


MC_ROOT = Path(__file__).parent.parent
DEFAULT_MANIFEST = MC_ROOT / "static" / "manifest.json"


ENV_OVERRIDES = {
    "MC_PWA_NAME": "name",
    "MC_PWA_SHORT_NAME": "short_name",
    "MC_PWA_DESCRIPTION": "description",
    "MC_PWA_THEME_COLOR": "theme_color",
    "MC_PWA_BACKGROUND_COLOR": "background_color",
    "MC_PWA_START_URL": "start_url",
}


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text())


def build_manifest(path: Path = DEFAULT_MANIFEST, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return the default manifest with per-instance environment overrides.

    This keeps the shipped PWA static by default while allowing deploy scripts or
    a future `mc instance create` command to brand each client instance.
    """
    source = os.environ if env is None else env
    manifest = deepcopy(load_manifest(path))
    for env_name, key in ENV_OVERRIDES.items():
        value = source.get(env_name)
        if value:
            manifest[key] = value

    default_intent = source.get("MC_PWA_DEFAULT_INTENT", "").upper()
    if default_intent and "MC_PWA_START_URL" not in source:
        manifest["start_url"] = f"/?intent={default_intent}"

    return manifest
