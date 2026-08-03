from __future__ import annotations

import os

from . import config


EXTERNAL_MODEL_PREFIXES = ("openai/", "groq/", "mistral/")
LOCAL_MODEL_PREFIXES = ("ollama/",)


def normalize_model(model: str | None) -> str:
    return (model or "").strip().lower()


def local_model_name(model: str | None) -> str:
    candidate = normalize_model(model)
    return candidate.split("/", 1)[1] if candidate.startswith(LOCAL_MODEL_PREFIXES) else candidate


def is_syntactically_local_model(model: str | None) -> bool:
    candidate = normalize_model(model)
    if not candidate or ":cloud" in candidate:
        return False
    if candidate.startswith(EXTERNAL_MODEL_PREFIXES):
        return False
    if "/" in candidate and not candidate.startswith(LOCAL_MODEL_PREFIXES):
        return False
    return True


def is_external_model(model: str | None) -> bool:
    """Default-deny privacy predicate for non-local provider strings.

    This answers "would this route leave the machine?" for endpoint selection
    and egress logging. Reachability is a stricter question handled by
    is_provably_local_model().
    """
    candidate = normalize_model(model)
    if not candidate:
        return False
    return not is_syntactically_local_model(candidate)


def exit_destination(model: str | None) -> str:
    candidate = normalize_model(model)
    if candidate.startswith("openai/"):
        return "openai"
    if candidate.startswith("groq/"):
        return "groq"
    if candidate.startswith("mistral/"):
        return "mistral"
    if ":cloud" in candidate:
        return "ollama:cloud"
    if "/" in candidate and not candidate.startswith(LOCAL_MODEL_PREFIXES):
        return candidate.split("/", 1)[0] or "unknown-provider"
    return "local"


def _explicit_local_allowlist() -> set[str]:
    raw = os.environ.get("LV_LOCAL_MODEL_ALLOWLIST", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


_installed_models_cache: frozenset[str] | None = None


def _installed_ollama_models() -> frozenset[str]:
    """Live Ollama model list, cached only once non-empty.

    An empty result (Ollama not yet started, transient probe failure) is
    never cached: caching it would deny every student-data query until app
    restart even after Ollama comes up. Re-probing while empty is cheap —
    a refused localhost connection fails in milliseconds.
    """
    global _installed_models_cache
    if _installed_models_cache:
        return _installed_models_cache
    try:
        models = frozenset(name.lower() for name in config.list_ollama_models())
    except Exception:
        return frozenset()
    if models:
        _installed_models_cache = models
    return models


def clear_model_gate_cache() -> None:
    global _installed_models_cache
    _installed_models_cache = None


def is_provably_local_model(model: str | None) -> bool:
    """True only when student data may be sent to this model.

    A model must be local-looking, non-cloud, and either present in the live
    Ollama model list or explicitly allowlisted by the operator/test harness.
    """
    if not is_syntactically_local_model(model):
        return False
    name = local_model_name(model)
    if not name:
        return False
    allowlist = _explicit_local_allowlist()
    if name in allowlist or normalize_model(model) in allowlist:
        return True
    return name in _installed_ollama_models()
