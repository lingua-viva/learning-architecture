from __future__ import annotations

"""Compatibility wrapper for canonical Lingua Viva provider config.

Provider config storage and parsing live in ``src.lingua_viva.config``. This
module keeps the older ``src.provider_config`` import surface patchable for
existing tests and routes.
"""

import json
import os
from typing import Optional
from urllib import error, request

from src.lingua_viva.config import (
    SUPPORTED_PROVIDERS,
    ollama_reachable as _canonical_ollama_reachable,
    provider_config_path as _provider_config_path,
    provider_entries as _provider_entries,
    read_provider_config as _read_provider_config,
)


def ollama_reachable() -> bool:
    return _canonical_ollama_reachable()


def provider_status() -> dict:
    config = _read_provider_config() or {}
    default_provider = config.get("default_provider")
    entry = _provider_entries(config).get(default_provider) if default_provider else None
    if not isinstance(entry, dict):
        entry = None
    is_external = default_provider in SUPPORTED_PROVIDERS
    return {
        "connected": bool(entry and is_external),
        "provider": default_provider if (entry and is_external) else "local",
        "model": entry.get("model") if entry else None,
        "ollama_reachable": ollama_reachable(),
    }


def verify_key(provider: str, api_key: str, model: str) -> tuple[bool, str]:
    if provider not in SUPPORTED_PROVIDERS:
        return False, "unsupported"
    endpoint = SUPPORTED_PROVIDERS[provider]["endpoint"]
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15):
            return True, "ok"
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "bad_key"
        return False, "network"
    except (error.URLError, ConnectionError, TimeoutError, OSError):
        return False, "network"


def connect_provider(provider: str, api_key: str, model: Optional[str] = None) -> dict:
    if provider not in SUPPORTED_PROVIDERS:
        return {"status": "rejected", "message": "Unsupported provider."}
    if not (api_key or "").strip():
        return {"status": "rejected", "message": "This key didn't work — check it and try again."}
    if model is not None and not isinstance(model, str):
        return {"status": "rejected", "message": "Unsupported model value."}

    model = model or SUPPORTED_PROVIDERS[provider]["default_model"]
    ok, reason = verify_key(provider, api_key, model)
    if not ok and reason == "bad_key":
        return {"status": "rejected", "message": "This key didn't work — check it and try again."}

    config_path = _provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_provider_config() or {}
    providers = _provider_entries(existing)
    existing["providers"] = providers
    providers[provider] = {"model": model, "api_key": api_key, "verified": ok}
    existing["default_provider"] = provider

    tmp_path = config_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(existing, handle)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, config_path)

    if ok:
        return {"status": "connected", "message": f"Connected to {provider}."}
    return {"status": "saved_unreachable", "message": f"Saved — will use local mode until we can reach {provider}."}


def disconnect_provider() -> None:
    _provider_config_path().unlink(missing_ok=True)


__all__ = [
    "SUPPORTED_PROVIDERS",
    "_provider_config_path",
    "_read_provider_config",
    "_provider_entries",
    "ollama_reachable",
    "provider_status",
    "verify_key",
    "connect_provider",
    "disconnect_provider",
    "request",
]
