"""
Lingua Viva — Sanitizer Client

Unified client for calling the sanitizer service.
Used by pipeline, hub, bridges, and any other surface.

Behavior:
    - Production: HTTP call to localhost:6100
    - Dev mode: direct import (same code, no network)
    - FAIL-CLOSED: if service unreachable, ALL external calls blocked

Usage:
    from sanitizer.client import sanitize_text, is_service_available

    result = await sanitize_text("Patient John Smith SSN 123-45-6789",
                                  context="medical",
                                  block_signals=["ssn"],
                                  namespace="komodo")
    if not result["ok"]:
        # BLOCKED — do not proceed with external call
        ...
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

SANITIZER_URL = os.getenv("LV_SANITIZER_URL", "http://localhost:6100")

# Cache: is the service reachable?
_service_checked = False
_service_available = False


def _check_service() -> bool:
    """Check if the sanitizer HTTP service is running."""
    global _service_checked, _service_available
    try:
        req = Request(f"{SANITIZER_URL}/health", method="GET")
        resp = urlopen(req, timeout=2)
        data = json.loads(resp.read())
        _service_available = data.get("ok", False)
    except Exception:
        _service_available = False
    _service_checked = True
    return _service_available


def is_service_available() -> bool:
    """Check sanitizer service availability."""
    if not _service_checked:
        return _check_service()
    return _service_available


def sanitize_text(
    text: str,
    context: str = "general",
    block_signals: Optional[List[str]] = None,
    namespace: str = "default",
) -> Dict[str, Any]:
    """Sanitize text through the unified service.

    FAIL-CLOSED: If the service is unreachable AND we're not in dev mode,
    returns blocked=True. External calls MUST NOT proceed.

    In dev mode: falls back to direct import (same code, no HTTP).
    """
    # Try HTTP service first (production path)
    try:
        payload = json.dumps({
            "text": text,
            "context": context,
            "block_signals": block_signals if block_signals is not None else [],
            "namespace": namespace,
        }).encode()

        req = Request(
            f"{SANITIZER_URL}/sanitize/fast",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urlopen(req, timeout=5)
        return json.loads(resp.read())

    except (URLError, OSError, TimeoutError) as e:
        # Service unreachable
        logger.warning("[Sanitizer] Service unreachable: %s", e)

        # Re-read DEV_MODE at call time (not import time) for testability
        dev_mode = os.getenv("LV_DEV_MODE", "1") == "1"

        if dev_mode:
            # Dev mode fallback: direct import
            try:
                from sanitizer.app import sanitize
                return sanitize(text, context=context, block_signals=block_signals, namespace=namespace)
            except ImportError:
                pass

        # FAIL-CLOSED: Service down + not dev mode = block everything
        logger.error("[Sanitizer] FAIL-CLOSED: Service unavailable, blocking all external calls")
        return {
            "ok": False,
            "blocked": True,
            "text": "",
            "redactions": [],
            "reason": "sanitizer_unavailable",
            "tokens": {},
            "reverse_tokens": {},
            "context": context,
            "latency_ms": 0,
        }


def rehydrate(text: str, reverse_tokens: Dict[str, str]) -> str:
    """Re-hydrate tokenized text back to original values.

    Called by the exit gate before showing response to the user.
    The LLM saw tokens; the human sees real values.
    """
    result = text
    for token, original in reverse_tokens.items():
        result = result.replace(token, original)
    return result
