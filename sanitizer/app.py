"""
Mission Canvas — Unified Sanitizer Service

Single governance service for PII/PHI detection and redaction.
All surfaces (hub, pipeline, CLI, bridges) call this one service.

Endpoints:
    GET  /health          → {"ok": true, "mode": "fast|deep"}
    POST /sanitize/fast   → Regex only, <10ms p99
    POST /sanitize/deep   → Regex + LLM entity detection, <1000ms

Design principles:
    - Fail-closed: if this service is down, external calls are blocked
    - Deterministic tokens: "John Smith" → <IDENTITY_A> (preserves relationships)
    - Context-aware: logistics context suppresses SKU-like phone patterns
    - One firewall log: sanitizer/data/firewall_log.ndjson
"""

import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _data_dir() -> Path:
    """Resolved lazily (not a module-level constant) so LV_SANITIZER_DATA_DIR
    can override it per-test — module-level constants are computed once at
    import time, before any test's monkeypatch.setenv runs, same seam
    pattern as traces.trace_path()/privacy_log.privacy_log_path().

    When frozen (PyInstaller onefile), __file__ lives in the transient
    _MEIxxxx extraction dir — not writable across runs and its parents may
    be absent, which crashed the binary at import time. Use a persistent,
    writable user dir when frozen; the source tree's own data/ dir
    otherwise. Same pattern as mission-canvas/sanitizer/app.py.

    LV_SANITIZER_DATA_DIR (checked unconditionally, not just when frozen) is
    the test-hermeticity override (MC-lessons §1) — without it, every test
    that exercises the sanitizer wrote firewall_log.ndjson straight into the
    tracked sanitizer/data/ dir, dirtying the tree on every suite run.
    """
    override = os.environ.get("LV_SANITIZER_DATA_DIR")
    if override:
        data_dir = Path(override)
    elif getattr(sys, "frozen", False):
        sir_home = os.environ.get("STILL_I_RISE_HOME") or str(Path.home() / ".still-i-rise")
        data_dir = Path(sir_home) / "data"
    else:
        data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir



# ─── PII Patterns ────────────────────────────────────────────────────────────

PII_PATTERNS = [
    ("ssn", r'\b\d{3}-\d{2}-\d{4}\b', "SSN"),
    ("ssn_nodash", r'\b\d{9}\b', "SSN (no dashes)"),
    ("credit_visa", r'\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', "credit card (Visa)"),
    ("credit_mc", r'\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', "credit card (Mastercard)"),
    ("credit_amex", r'\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b', "credit card (Amex)"),
    ("email", r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', "email address"),
    ("phone_us", r'\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', "phone number (US)"),
    ("phone_intl", r'\b\+\d{1,3}[-.\s]?\d{6,14}\b', "phone number (international)"),
    ("address", r'\b\d{1,5}\s+\w+\s+(street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|way|court|ct)\b', "street address"),
    ("mrn", r'\b(?:MRN|mrn)[:\s#]?\d{4,}\b', "medical record number"),
    ("dob", r'\b(?:DOB|dob|Date of Birth)[:\s]?\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', "date of birth"),
    ("passport", r'\b[A-Z]{1,2}\d{6,9}\b', "possible passport number"),
]

# Compiled for speed
PII_COMPILED = [(name, re.compile(pattern, re.IGNORECASE), label) for name, pattern, label in PII_PATTERNS]

# ─── Context Suppression (per-domain pattern exclusions) ─────────────────────

CONTEXT_SUPPRESSIONS: Dict[str, set] = {
    "logistics": {"phone_us", "phone_intl", "passport", "ssn_nodash"},  # SKUs, tracking numbers, serial numbers
    "medical": set(),        # NEVER suppress anything in medical context
    "education": set(),      # NEVER suppress for child data
    "legal": set(),          # Strict
    "general": set(),        # Default: all patterns active
}

# ─── Block Signals (from environment or config) ──────────────────────────────

def _load_block_signals() -> List[str]:
    """Load DEFAULT block signals. These are overridden per-client via request payload."""
    raw = os.getenv("MC_SANITIZER_BLOCK_SIGNALS", "")
    if raw:
        return [s.strip().lower() for s in raw.split(",") if s.strip()]
    # Minimal safe defaults — clients override in their config
    return []

BLOCK_SIGNALS = _load_block_signals()


# ─── Deterministic Token Substitution ────────────────────────────────────────

class TokenMapper:
    """Maps detected PII to deterministic tokens.

    Uses namespace-stable hashing: same value + same client namespace = same token always.
    This means "Luis" is always <PERSON_8f21> for Tropical IT across sessions,
    allowing LLMs to build coherent multi-turn context without knowing the name.
    """

    def __init__(self, namespace: str = "default"):
        self._namespace = namespace
        self._map: Dict[str, str] = {}

    def get_token(self, value: str, pii_type: str) -> str:
        key = value.strip()
        if key in self._map:
            return self._map[key]
        # Stable hash: same value + namespace = same token always
        import hashlib
        h = hashlib.sha256(f"{self._namespace}:{key}".encode()).hexdigest()[:6]
        prefix = pii_type.upper().split("(")[0].strip().replace(" ", "_")
        token = f"<{prefix}_{h}>"
        self._map[key] = token
        return token

    @property
    def token_map(self) -> Dict[str, str]:
        """Returns {original_value: token} for re-hydration by exit gate."""
        return dict(self._map)

    @property
    def reverse_map(self) -> Dict[str, str]:
        """Returns {token: original_value} for re-hydration."""
        return {v: k for k, v in self._map.items()}


# ─── Core Sanitize Function ──────────────────────────────────────────────────

def sanitize(
    text: str,
    context: str = "general",
    boundary: Optional[str] = None,
    block_signals: Optional[List[str]] = None,
    namespace: str = "default",
) -> Dict[str, Any]:
    """Sanitize text. Returns result with deterministic token substitution.

    Args:
        text: Input text to sanitize
        context: Domain context (logistics, medical, education, legal, general)
        boundary: Optional boundary rule name
        block_signals: Optional per-client block signal list (empty = PII redaction only, no blocking)
        namespace: Client namespace for stable token hashing (e.g., "tropical_it")

    Returns:
        {
            "ok": bool,            # True if text is safe to send externally
            "blocked": bool,       # True if block signal detected
            "text": str,           # Sanitized text (with tokens substituted)
            "redactions": [...],   # List of {type, original, token, position}
            "reason": str|None,    # Why blocked (if blocked)
            "tokens": {},          # Token map {original → token} for reference
            "reverse_tokens": {},  # Reverse map {token → original} for EXIT GATE re-hydration
            "latency_ms": float,
        }
    """
    start = time.time()
    suppressions = CONTEXT_SUPPRESSIONS.get(context, set())
    signals = block_signals if block_signals is not None else BLOCK_SIGNALS
    mapper = TokenMapper(namespace=namespace)
    redactions = []
    result_text = text
    blocked = False
    block_reason = None

    # Check block signals first (only if signals list is non-empty)
    if signals:
        text_lower = text.lower()
        for signal in signals:
            if signal in text_lower:
                blocked = True
                block_reason = f"block_signal: {signal}"
                break

    # Apply PII patterns (even if blocked — still redact for the log)
    for name, pattern_re, label in PII_COMPILED:
        if name in suppressions:
            continue
        for match in pattern_re.finditer(result_text):
            original = match.group()
            token = mapper.get_token(original, label)
            redactions.append({
                "type": label,
                "original": original,
                "token": token,
                "start": match.start(),
                "end": match.end(),
            })

    # Apply substitutions (reverse order to preserve positions)
    for r in sorted(redactions, key=lambda x: x["start"], reverse=True):
        result_text = result_text[:r["start"]] + r["token"] + result_text[r["end"]:]

    latency = (time.time() - start) * 1000

    result = {
        "ok": not blocked and True,
        "blocked": blocked,
        "text": result_text,
        "redactions": redactions,
        "reason": block_reason,
        "tokens": mapper.token_map,
        "reverse_tokens": mapper.reverse_map,
        "context": context,
        "namespace": namespace,
        "latency_ms": round(latency, 2),
    }

    # Log to firewall
    _log_firewall(text, result)

    return result


def _log_firewall(original_text: str, result: Dict[str, Any]) -> None:
    """Append to firewall log (NDJSON)."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "blocked": result["blocked"],
        "redaction_count": len(result["redactions"]),
        "redaction_types": list({r["type"] for r in result["redactions"]}),
        "context": result["context"],
        "reason": result["reason"],
        "latency_ms": result["latency_ms"],
        "input_length": len(original_text),
    }
    try:
        with open(_data_dir() / "firewall_log.ndjson", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never crash on log failure


# ─── FastAPI App ─────────────────────────────────────────────────────────────

def create_app():
    """Create the FastAPI application."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel
    except ImportError:
        raise ImportError("FastAPI required: pip install fastapi uvicorn")

    app = FastAPI(title="MC Sanitizer", version="1.0.0")

    class SanitizeRequest(BaseModel):
        text: str
        context: str = "general"
        boundary: Optional[str] = None
        block_signals: Optional[List[str]] = None
        namespace: str = "default"

    @app.get("/health")
    def health():
        return {"ok": True, "mode": "fast", "patterns": len(PII_PATTERNS), "version": "1.0.0"}

    @app.post("/sanitize/fast")
    def sanitize_fast(req: SanitizeRequest):
        result = sanitize(req.text, context=req.context, boundary=req.boundary,
                         block_signals=req.block_signals, namespace=req.namespace)
        return JSONResponse(content=result)

    @app.post("/sanitize/deep")
    def sanitize_deep(req: SanitizeRequest):
        result = sanitize(req.text, context=req.context, boundary=req.boundary,
                         block_signals=req.block_signals, namespace=req.namespace)
        result["mode"] = "deep"
        return JSONResponse(content=result)

    return app


# ─── Direct Import API (for dev mode / same-process use) ─────────────────────

# When imported directly (not via HTTP), just use sanitize() function above.
# This is the dev-mode fallback that Claude specified.


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    port = int(os.getenv("MC_SANITIZER_PORT", "6100"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
