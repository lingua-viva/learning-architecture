"""
Exit Gate — Socket Firewall + Response Validation

Controls what leaves the machine and what comes back.

Outbound:
  - Monkey-patches socket.create_connection
  - Only approved hosts can be contacted
  - All attempts logged to NDJSON (Turso-ready)

Inbound:
  - Validates responses for malicious patterns
  - OpenClaw has 150+ instances of malware in its ecosystem
  - Any code/content coming from external sources gets scanned

The exit gate is architectural enforcement, not advisory.
If a host is not in the allowlist, the connection fails. Period.
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Approved hosts — minimal, intentional, explicit
ALLOWLIST: set[str] = {
    # Local services
    "127.0.0.1", "localhost", "0.0.0.0", "::1",
    # Governed external APIs
    "api.perplexity.ai",
    "api.anthropic.com",
    "api.mistral.ai",
    "api.groq.com",
    "generativelanguage.googleapis.com",
    # Local inference
    "ollama", "host.docker.internal",
    # Still I Rise Product A: teacher-facing reply channel only.
    # Never carries student observation content externally — the
    # ontology gate (blocks_external/requires_local on LV-TCH-*/LV-STU-*)
    # keeps observation text local; this host is used only to post
    # already-teacher-approved, non-PII acknowledgement replies back to
    # the teacher's own Slack channel. See src/education/slack_bot.py.
    "slack.com",
}

# Private network ranges (always allowed)
PRIVATE_PREFIXES = ("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
                    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")

# Layer 1: Literal patterns (fast, catches naive attacks)
MALICIOUS_PATTERNS = [
    "eval(", "exec(", "os.system(", "subprocess.call(",
    "__import__('os')", "import os;", "import subprocess;",
    "rm -rf", ":(){ :|:& };:",
    "<script>", "javascript:", "onerror=",
    "curl | bash", "wget | sh", "pip install --",
    "PRIVATE KEY", "BEGIN RSA", "BEGIN EC PRIVATE",
    "password=", "api_key=", "secret_key=",
]

# Layer 2: Obfuscation patterns (catches evasion attempts)
import re as _re
OBFUSCATION_PATTERNS = [
    _re.compile(r'curl\s+\S+\s*\|\s*(?:ba)?sh'),                # curl URL | bash (with URL)
    _re.compile(r'wget\s+\S+\s*\|\s*(?:ba)?sh'),                # wget URL | sh
    _re.compile(r'\\x[0-9a-f]{2}(?:.*\\x[0-9a-f]{2}){3,}'),   # Hex escape chains
    _re.compile(r'[A-Za-z0-9+/]{60,}={0,2}'),                   # Long base64 blobs
    _re.compile(r'e\s+v\s+a\s+l\s*\('),                         # Whitespace-inserted eval
    _re.compile(r'(?:__import__|getattr|globals|setattr)\s*\('), # Dynamic access
    _re.compile(r'chr\s*\(\s*\d+\s*\)\s*\+\s*chr'),             # chr() concatenation
    _re.compile(r'fromCharCode\s*\('),                           # JS char building
    _re.compile(r'\\u[0-9a-f]{4}(?:.*\\u[0-9a-f]{4}){3,}'),    # Unicode escape chains
]

# Layer 3: Code block size threshold
CODE_BLOCK_PATTERN = _re.compile(r'```[\s\S]{500,}?```')


@dataclass
class FirewallEvent:
    """A single firewall event (allowed or blocked)."""
    timestamp: float
    action: str      # ALLOWED, BLOCKED, MALICIOUS_RESPONSE
    host: str
    port: int = 0
    reason: str = ""
    direction: str = "outbound"  # outbound or inbound

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class ExitGate:
    """
    Socket-level firewall with response validation.

    When activated:
    - All outbound connections checked against allowlist
    - Non-allowed connections raise ConnectionError
    - All events logged to NDJSON (persistent audit trail)
    - Inbound responses scanned for malicious patterns
    """

    def __init__(self, log_dir: Optional[Path] = None):
        self._active = False
        self._original_create_connection = None
        self._session_log: list[FirewallEvent] = []
        self._log_dir = log_dir or Path(__file__).parent.parent.parent / "memory" / "data"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "firewall_log.ndjson"
        self._custom_allowlist: set[str] = set()

    @property
    def active(self) -> bool:
        return self._active

    @property
    def allowlist(self) -> set[str]:
        return ALLOWLIST | self._custom_allowlist

    def activate(self) -> None:
        """
        Activate the socket firewall. Monkey-patches socket.create_connection.

        After activation, ANY outbound connection not in the allowlist
        will raise ConnectionError. This is architectural enforcement.
        """
        if self._active:
            return

        self._original_create_connection = socket.create_connection

        def guarded_connection(address, *args, **kwargs):
            host = address[0] if isinstance(address, tuple) else str(address)
            port = address[1] if isinstance(address, tuple) and len(address) > 1 else 0

            if self._is_allowed(host):
                event = FirewallEvent(
                    timestamp=time.time(),
                    action="ALLOWED",
                    host=host,
                    port=port,
                )
                self._log_event(event)
                return self._original_create_connection(address, *args, **kwargs)
            else:
                event = FirewallEvent(
                    timestamp=time.time(),
                    action="BLOCKED",
                    host=host,
                    port=port,
                    reason=f"host not in allowlist: {host}",
                )
                self._log_event(event)
                raise ConnectionError(
                    f"[Mission Canvas Exit Gate] Connection to {host}:{port} BLOCKED. "
                    f"Host not in allowlist. Add with exit_gate.allow('{host}') if authorized."
                )

        socket.create_connection = guarded_connection
        self._active = True

    def deactivate(self) -> None:
        """Restore original socket behavior."""
        if self._active and self._original_create_connection:
            socket.create_connection = self._original_create_connection
            self._active = False

    def allow(self, host: str) -> None:
        """Add a host to the runtime allowlist. Does NOT persist across restarts."""
        self._custom_allowlist.add(host)

    def scan_response(self, content: str, source_host: str) -> tuple[bool, list[str]]:
        """
        3-layer scan of inbound responses for malicious content.

        Layer 1: Literal pattern matching (fast, catches naive attacks)
        Layer 2: Obfuscation pattern detection (regex, catches evasion)
        Layer 3: Large code block detection (flags for review)

        150+ malware instances in OpenClaw's ecosystem. This is the defense.
        """
        threats = []
        content_lower = content.lower()

        # Layer 1: Literal patterns
        for pattern in MALICIOUS_PATTERNS:
            if pattern.lower() in content_lower:
                threats.append(f"L1 literal: '{pattern}' from {source_host}")

        # Layer 2: Obfuscation patterns
        for regex in OBFUSCATION_PATTERNS:
            match = regex.search(content)
            if match:
                snippet = match.group()[:40]
                threats.append(f"L2 obfuscation: '{snippet}...' from {source_host}")

        # Layer 3: Large code blocks (flag, don't auto-block)
        code_blocks = CODE_BLOCK_PATTERN.findall(content)
        if code_blocks:
            for block in code_blocks:
                threats.append(f"L3 large code block: {len(block)} chars from {source_host}")

        if threats:
            event = FirewallEvent(
                timestamp=time.time(),
                action="MALICIOUS_RESPONSE",
                host=source_host,
                reason=f"{len(threats)} threat(s) detected",
                direction="inbound",
            )
            self._log_event(event)

        return len(threats) == 0, threats

    def get_log(self) -> list[FirewallEvent]:
        """Get the session log."""
        return list(self._session_log)

    def get_block_count(self) -> int:
        """Count blocked attempts in this session."""
        return sum(1 for e in self._session_log if e.action == "BLOCKED")

    def _is_allowed(self, host: str) -> bool:
        """Check if a host is in the allowlist."""
        if host in self.allowlist:
            return True
        # Allow private network ranges — resolve first to prevent DNS bypass
        # (e.g., "10.evil.com" starts with "10." but resolves to a public IP)
        try:
            resolved = socket.getaddrinfo(host, None, socket.AF_INET)[0][4][0]
        except (OSError, IndexError):
            resolved = host
        if any(resolved.startswith(prefix) for prefix in PRIVATE_PREFIXES):
            return True
        return False

    def _log_event(self, event: FirewallEvent) -> None:
        """Log to session memory and persistent NDJSON file."""
        self._session_log.append(event)
        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except OSError:
            pass  # Don't crash the app if logging fails
