"""
Provider config — write side. Gap 5a, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md.

The read side (`_provider_config_path`, `_read_provider_config`,
`_provider_api_key`) lives in `src/pipeline.py` because `ReasoningEngine
.reason()` needs it on every REASON call, fresh, never cached. This module
is the write side — verify-then-save ("connect") and delete ("disconnect")
— called from the `/api/provider*` routes in `src/web.py`, but kept
importable/unit-testable on its own without spinning up FastAPI, same
separation `mc_cli.ingest_document()` uses for the ingest endpoint.

Only OpenAI, Groq, and Mistral are offered (Gap 5a point 2): those are the
only providers `ReasoningEngine._resolve_endpoint()` actually implements.
"Local" is not something a user *connects* here — it's just the absence
of a connected external provider (or the "ollama" entry install.sh writes
during setup), so it never appears in SUPPORTED_PROVIDERS.
"""

from __future__ import annotations

import json
import os
from typing import Optional
from urllib import error, request

from src.pipeline import _provider_config_path, _read_provider_config, _provider_entries

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


def ollama_reachable() -> bool:
    """Gap 5a point 5 — first-run local-mode health check. A teacher whose
    laptop rebooted and whose Ollama service didn't auto-start must not be
    met with silent empty responses after picking 'local'."""
    try:
        with request.urlopen("http://localhost:11434/api/tags", timeout=3):
            return True
    except (error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def provider_status() -> dict:
    """Current connection state for the onboarding screen."""
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
    """
    One lightweight (1-token) test completion — Gap 5a point 3. Returns
    (ok, reason), where reason distinguishes a rejected key ("bad_key")
    from an unreachable network ("network") so the caller can give the
    two genuinely different messages the spec requires.
    """
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
    except error.HTTPError as e:
        if e.code in (401, 403):
            return False, "bad_key"
        return False, "network"
    except (error.URLError, ConnectionError, TimeoutError, OSError):
        return False, "network"


def connect_provider(provider: str, api_key: str, model: Optional[str] = None) -> dict:
    """
    Verify then save (Gap 5a points 3, 7). A bad key is never written to
    disk at all. An unreachable network still saves the config (so the
    teacher isn't blocked by a flaky connection at setup time) but returns
    a message distinct from success, per point 3's honest-network-failure
    requirement.
    """
    if provider not in SUPPORTED_PROVIDERS:
        return {"status": "rejected", "message": "Unsupported provider."}
    if not (api_key or "").strip():
        return {"status": "rejected", "message": "This key didn't work — check it and try again."}
    # Hardening (15-iteration sweep, 2026-07-14): a non-string `model`
    # (int/list/dict — a malformed JSON body reaching this far) doesn't
    # crash anything downstream, but it silently persists garbage that
    # degrades every future REASON call to the "no model available"
    # placeholder with no visible cause until the teacher manually
    # disconnects. Reject it here instead, at the one place it's created.
    if model is not None and not isinstance(model, str):
        return {"status": "rejected", "message": "Unsupported model value."}

    model = model or SUPPORTED_PROVIDERS[provider]["default_model"]
    ok, reason = verify_key(provider, api_key, model)
    if not ok and reason == "bad_key":
        return {"status": "rejected", "message": "This key didn't work — check it and try again."}

    config_path = _provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_provider_config() or {}
    existing.setdefault("providers", {})[provider] = {
        "model": model,
        "api_key": api_key,
        "verified": ok,
    }
    existing["default_provider"] = provider
    # Atomic write (temp file + os.replace) — hardening found alongside
    # the non-dict-config crash above: a direct `open(path, "w")` can
    # leave a truncated/partial JSON file on disk if two connect calls
    # race (e.g. a double-clicked "Connect" button) or the process is
    # killed mid-write, which is exactly the corruption shape that used
    # to crash every subsequent REASON call. os.replace() is atomic on
    # both POSIX and Windows.
    tmp_path = config_path.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(existing, f)
    # 0600 — owner read/write only (Gap 5a point 7). Windows has no exact
    # equivalent via os.chmod; this is a no-op there, matching the spec's
    # "restricted-ACL intent" phrasing rather than promising true ACLs.
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, config_path)

    if ok:
        return {"status": "connected", "message": f"Connected to {provider}."}
    return {
        "status": "saved_unreachable",
        "message": f"Saved — will use local mode until we can reach {provider}.",
    }


def disconnect_provider() -> None:
    """Delete the config file entirely — Gap 5a points 4 and 7 both require
    the key material to actually be removed from disk, not just marked
    inactive. Reverts to whatever install.sh's own Ollama auto-detection
    would otherwise resolve to (i.e. local-only)."""
    _provider_config_path().unlink(missing_ok=True)
