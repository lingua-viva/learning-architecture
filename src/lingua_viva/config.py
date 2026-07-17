from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from urllib import error, request


LOCAL_MODEL_PREFERENCE = [
    "qwen3:14b",
    "qwen3:8b",
    "phi4:14b",
    "qwen2.5:14b",
    "llama3.1:8b",
    "qwen2.5:7b",
    "mistral:7b",
    "qwen2.5:3b",
]
CLOUD_FALLBACK = "kimi-k2.7-code:cloud"

SUPPORTED_PROVIDERS = {
    "openai": {
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
    },
    "groq": {
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.1-8b-instant",
    },
    "mistral": {
        "endpoint": "https://api.mistral.ai/v1/chat/completions",
        "default_model": "mistral-small-latest",
    },
}


def config_home() -> Path:
    home = os.environ.get("LV_CONFIG_HOME") or os.environ.get("SIR_CONFIG_HOME")
    return Path(home) if home else Path.home() / ".lingua-viva"


def provider_config_path() -> Path:
    return config_home() / "config" / "providers.json"


def read_provider_config() -> Optional[dict]:
    try:
        with provider_config_path().open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def provider_entries(config: dict) -> dict:
    providers = config.get("providers")
    return providers if isinstance(providers, dict) else {}


def provider_api_key(provider_name: str) -> Optional[str]:
    config = read_provider_config()
    if not config:
        return None
    entry = provider_entries(config).get(provider_name)
    return entry.get("api_key") if isinstance(entry, dict) else None


def resolve_provider_model() -> Optional[str]:
    config = read_provider_config()
    if not config:
        return None
    default_provider = config.get("default_provider")
    entry = provider_entries(config).get(default_provider)
    model_name = entry.get("model") if isinstance(entry, dict) else None
    if not model_name or not isinstance(model_name, str):
        return None
    if default_provider in ("ollama", "openai", "groq", "mistral"):
        return f"{default_provider}/{model_name}"
    return None


def list_ollama_models(timeout: int = 5) -> list[str]:
    req = request.Request("http://localhost:11434/api/tags", method="GET")
    with request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read())
    models = data.get("models", [])
    if not isinstance(models, list):
        return []
    names = [item.get("name") for item in models if isinstance(item, dict)]
    return [name for name in names if isinstance(name, str)]


def detect_model(installed_models: list[str] | None = None) -> str:
    try:
        installed = set(installed_models if installed_models is not None else list_ollama_models())
    except (error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError):
        return "ollama/qwen2.5:3b"
    for model in LOCAL_MODEL_PREFERENCE:
        if model in installed:
            return f"ollama/{model}"
    return f"ollama/{CLOUD_FALLBACK}"


def ollama_reachable() -> bool:
    try:
        with request.urlopen("http://localhost:11434/api/tags", timeout=3):
            return True
    except (error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def provider_status() -> dict:
    config = read_provider_config() or {}
    default_provider = config.get("default_provider")
    entry = provider_entries(config).get(default_provider) if default_provider else None
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
        return {"status": "rejected", "message": "This key didn't work - check it and try again."}
    if model is not None and not isinstance(model, str):
        return {"status": "rejected", "message": "Unsupported model value."}

    model = model or SUPPORTED_PROVIDERS[provider]["default_model"]
    ok, reason = verify_key(provider, api_key, model)
    if not ok and reason == "bad_key":
        return {"status": "rejected", "message": "This key didn't work - check it and try again."}

    config_path = provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_provider_config() or {}
    providers = provider_entries(existing)
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
    return {"status": "saved_unreachable", "message": f"Saved - will use local mode until we can reach {provider}."}


def disconnect_provider() -> None:
    provider_config_path().unlink(missing_ok=True)
