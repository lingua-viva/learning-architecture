from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from urllib import error, request


# qwen3:* demoted to last resort (2026-08-02): they are thinking models, and
# LV's reasoning path uses the OpenAI-compatible endpoint with no think
# suppression — on CPU-only hardware they burn the whole 60s budget emitting
# <think> tokens. Trace ledger evidence: 3 traces on 2026-08-02 at ~60,073ms
# with qwen3:8b and token_count=0 (the teacher got a timeout, not an answer).
# Keep in sync with LOCAL_PREFERENCE in src/pipeline.py.
LOCAL_MODEL_PREFERENCE = [
    "phi4:14b",
    "qwen2.5:14b",
    "llama3.1:8b",
    "qwen2.5:7b",
    "mistral:7b",
    "qwen2.5:3b",
    "qwen3:14b",
    "qwen3:8b",
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


# Canonical home-resolution seam (MC-lessons §1): every module that stores
# local-first state under ~/.lingua-viva/ resolves its *default* location
# through this function, so one env var (LV_CONFIG_HOME) — or one monkeypatch
# in tests/conftest.py — redirects all of it. Callers still expose their own
# more specific override (LV_TRACE_PATH, LV_PRIVACY_LOG_PATH, ...) which is
# checked first and wins when set explicitly.
def lv_home() -> Path:
    return config_home()


def provider_config_path() -> Path:
    return config_home() / "config" / "providers.json"


# Tier 2 school-configurable display (SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES
# 2026-08-01): labels and visibility only. Category IDs are immutable —
# they are the schema contract existing SQLite lenses depend on, so they
# are never read from config (manifest-is-the-contract principle).
DEFAULT_SCHOOL_PROFILE = {
    "category_labels": {},
    "hidden_categories": ["advanced_enrichment"],
    # Multi-teacher triangulation (operator ruling 2026-08-01): colleague
    # teacher_ids render as full display names in the UI. The names live
    # here in Tier 2 config only — never in ledger filenames or any Drive
    # artifact. Unknown ids fall back to the raw teacher_id.
    "teacher_display_names": {},
    # This machine's teacher identity (operator ruling 2026-08-02, teacher-
    # identity P1): empty means un-provisioned, and every write falls back to
    # UNPROVISIONED_TEACHER_ID. Triangulation across machines requires each
    # machine to set a distinct id here (Settings → Teacher identity) —
    # ledgers authored under the un-provisioned default are never exported
    # to or imported from the shared folder, so two fresh installs can never
    # silently overwrite or misattribute each other's observations.
    "own_teacher_id": "",
}

# Reserved sentinel for a machine that has not set its teacher identity.
# Pre-dates the identity config (every web.py write path defaulted to it),
# so existing rows are backfilled by rename_local_teacher when an id is set.
UNPROVISIONED_TEACHER_ID = "local-teacher"


def own_teacher_id() -> str:
    """This machine's configured teacher id, or "" when un-provisioned."""
    return read_school_profile().get("own_teacher_id") or ""


def school_profile_path() -> Path:
    return config_home() / "config" / "school_profile.json"


def read_school_profile() -> dict:
    """Load per-school display config. Never raises: a missing, unreadable,
    or malformed file degrades to shipped defaults — a broken config file
    must not break the student lens view."""
    default = {
        "category_labels": dict(DEFAULT_SCHOOL_PROFILE["category_labels"]),
        "hidden_categories": list(DEFAULT_SCHOOL_PROFILE["hidden_categories"]),
        "teacher_display_names": dict(DEFAULT_SCHOOL_PROFILE["teacher_display_names"]),
        "own_teacher_id": str(DEFAULT_SCHOOL_PROFILE["own_teacher_id"]),
    }
    try:
        with school_profile_path().open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default
    if not isinstance(data, dict):
        return default
    labels = data.get("category_labels")
    if isinstance(labels, dict):
        default["category_labels"] = {
            str(key): str(value)
            for key, value in labels.items()
            if isinstance(key, str) and isinstance(value, str)
        }
    hidden = data.get("hidden_categories")
    if isinstance(hidden, list):
        default["hidden_categories"] = [
            item for item in hidden if isinstance(item, str)
        ]
    names = data.get("teacher_display_names")
    if isinstance(names, dict):
        default["teacher_display_names"] = {
            str(key): str(value)
            for key, value in names.items()
            if isinstance(key, str) and isinstance(value, str)
        }
    own = data.get("own_teacher_id")
    if isinstance(own, str):
        own = own.strip()
        # A hand-edited file claiming the reserved sentinel stays
        # un-provisioned — the sentinel is never a real identity.
        default["own_teacher_id"] = "" if own == UNPROVISIONED_TEACHER_ID else own
    return default


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


SERVICE_KEY_FIELDS = {
    "perplexity": "perplexity_api_key",
    "rime": "rime_api_key",
}


def service_api_key(service_name: str) -> Optional[str]:
    field = SERVICE_KEY_FIELDS.get(service_name)
    if not field:
        return None
    config = read_provider_config()
    if not config:
        return None
    value = config.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def service_key_status() -> dict:
    return {
        name: {"configured": bool(service_api_key(name))}
        for name in SERVICE_KEY_FIELDS
    }


def save_service_api_keys(keys: dict[str, str]) -> dict:
    """Persist non-reasoning service keys in providers.json.

    This intentionally does not verify the keys over the network: Ask and TTS
    already surface rejected credentials honestly at call time, and Settings
    must work offline for packaged installs.
    """
    allowed = {name: value for name, value in keys.items() if name in SERVICE_KEY_FIELDS}
    if not allowed:
        raise ValueError("No supported service keys were sent.")
    config_path = provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_provider_config() or {}
    for name, value in allowed.items():
        field = SERVICE_KEY_FIELDS[name]
        cleaned = str(value or "").strip()
        if cleaned:
            existing[field] = cleaned
        else:
            existing.pop(field, None)
    tmp_path = config_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(existing, handle)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, config_path)
    return service_key_status()


# The only providers Lingua Viva knows how to talk to (local Ollama plus
# the external SUPPORTED_PROVIDERS above). Anything else configured in
# providers.json is refused locally (see requested_blocked_provider),
# never silently ignored.
KNOWN_PROVIDER_NAMES = ("ollama", "openai", "groq", "mistral")


def resolve_provider_model() -> Optional[str]:
    config = read_provider_config()
    if not config:
        return None
    default_provider = config.get("default_provider")
    entry = provider_entries(config).get(default_provider)
    model_name = entry.get("model") if isinstance(entry, dict) else None
    if not model_name or not isinstance(model_name, str):
        return None
    if default_provider in KNOWN_PROVIDER_NAMES:
        return f"{default_provider}/{model_name}"
    return None


def requested_blocked_provider() -> Optional[str]:
    """Return the configured provider request when it names a provider that
    is not on the supported list (e.g. {"provider": "anthropic/claude-3.5"}).

    resolve_provider_model() returns None for these shapes, which used to
    mean an unsupported provider was silently ignored and the query fell
    through to normal model resolution with no warning (teacher-readiness
    C10). Surfacing the request lets the reasoning chokepoint refuse it
    locally with an explicit "blocked" message before any model is resolved.
    """
    config = read_provider_config()
    if not config:
        return None
    for key in ("provider", "default_provider"):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        requested = value.strip()
        provider_name = requested.split("/", 1)[0].lower()
        if provider_name not in KNOWN_PROVIDER_NAMES:
            return requested
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


def detect_model(installed_models: list[str] | None = None) -> str | None:
    try:
        installed = set(installed_models if installed_models is not None else list_ollama_models())
    except (error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError):
        return None
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


def ollama_embedding_reachable(model: str = "nomic-embed-text", timeout: int = 3) -> bool:
    payload = json.dumps({"model": model, "prompt": "probe"}).encode("utf-8")
    req = request.Request(
        "http://localhost:11434/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read())
        embedding = body.get("embedding")
        return isinstance(embedding, list) and bool(embedding)
    except (error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError):
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
