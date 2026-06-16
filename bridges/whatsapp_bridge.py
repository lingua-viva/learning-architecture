"""
Mission Canvas — WhatsApp Bridge

WhatsApp adapter using Baileys (Node.js) as a subprocess.
Personal accounts via QR code pairing (no Meta Business verification needed).

Extracted from Hermes (MIT, Nous Research), adapted for MC governance pipeline.

Environment variables:
    MC_WHATSAPP_ENABLED       — "true" to activate (default: false)
    MC_WHATSAPP_ALLOWED_USERS — Comma-separated phone numbers (empty = all)
    MC_WHATSAPP_SESSION_DIR   — Where to store auth state (default: ~/.mc/whatsapp/)

Setup:
    1. Run: python -m bridges.whatsapp_bridge --pair
    2. Scan QR code with WhatsApp on phone
    3. Session persists in MC_WHATSAPP_SESSION_DIR

Architecture:
    This bridge spawns a small Node.js process that handles the WhatsApp Web
    protocol via Baileys. Communication between Python and Node is via
    newline-delimited JSON over stdin/stdout.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseBridge, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)

# The Node.js bridge script (shipped alongside this file)
_BRIDGE_JS = Path(__file__).parent / "whatsapp_node" / "bridge.mjs"


class WhatsAppBridge(BaseBridge):
    """WhatsApp bridge for Mission Canvas via Baileys subprocess."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("whatsapp", config or {})
        self._enabled = os.getenv("MC_WHATSAPP_ENABLED", "false").lower() == "true"
        self._allowed_users = set()
        allowed_raw = os.getenv("MC_WHATSAPP_ALLOWED_USERS", "").strip()
        if allowed_raw:
            self._allowed_users = {u.strip() for u in allowed_raw.split(",") if u.strip()}
        self._session_dir = Path(os.getenv("MC_WHATSAPP_SESSION_DIR", str(Path.home() / ".mc" / "whatsapp")))
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None

    @classmethod
    def is_configured(cls) -> bool:
        return os.getenv("MC_WHATSAPP_ENABLED", "false").lower() == "true"

    async def connect(self) -> bool:
        if not self._enabled:
            logger.info("[WhatsApp] Not enabled (set MC_WHATSAPP_ENABLED=true)")
            return False

        # Check Node.js available
        if not shutil.which("node"):
            logger.error("[WhatsApp] Node.js not found. Required for Baileys bridge.")
            return False

        if not _BRIDGE_JS.exists():
            logger.error("[WhatsApp] Bridge script not found at %s", _BRIDGE_JS)
            logger.info("[WhatsApp] Run the setup: cd bridges/whatsapp_node && npm install")
            return False

        self._session_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._process = await asyncio.create_subprocess_exec(
                "node", str(_BRIDGE_JS),
                "--session-dir", str(self._session_dir),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._running = True
            self._reader_task = asyncio.create_task(self._read_loop())
            logger.info("[WhatsApp] Bridge process started (pid %d)", self._process.pid)
            return True
        except Exception as e:
            logger.error("[WhatsApp] Failed to start bridge: %s", e)
            return False

    async def disconnect(self) -> None:
        self._running = False
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
        if self._reader_task:
            self._reader_task.cancel()

    async def _read_loop(self) -> None:
        """Read JSON messages from the Node.js subprocess stdout."""
        while self._running and self._process:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break
                data = json.loads(line.decode().strip())
                await self._handle_node_message(data)
            except asyncio.CancelledError:
                break
            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.error("[WhatsApp] Read error: %s", e)

    async def _handle_node_message(self, data: dict) -> None:
        msg_type = data.get("type")

        if msg_type == "qr":
            # Print QR code for pairing
            print(f"\n[WhatsApp] Scan this QR code:\n{data.get('qr', '')}\n")
            return

        if msg_type == "connected":
            logger.info("[WhatsApp] Connected as %s", data.get("user", "unknown"))
            return

        if msg_type == "message":
            sender = data.get("from", "")
            text = data.get("text", "")
            msg_id = data.get("id", "")

            # Strip @c.us/@s.whatsapp.net suffix for matching
            sender_number = sender.split("@")[0]

            if self._allowed_users and sender_number not in self._allowed_users:
                return

            if not text:
                return

            is_group = "@g.us" in sender
            source = self.build_source(
                chat_id=sender,
                chat_name=data.get("pushName", sender_number),
                chat_type="group" if is_group else "dm",
                user_id=sender,
                user_name=data.get("pushName", sender_number),
            )

            event = MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                source=source,
                message_id=msg_id,
            )

            await self.handle_message(event)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if not self._process or not self._process.stdin:
            return SendResult(success=False, error="Bridge process not running")

        try:
            payload = json.dumps({
                "type": "send",
                "to": chat_id,
                "text": content,
                "reply_to": reply_to,
            }) + "\n"
            self._process.stdin.write(payload.encode())
            await self._process.stdin.drain()
            return SendResult(success=True, message_id="")
        except Exception as e:
            logger.error("[WhatsApp] Send failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id.split("@")[0], "type": "dm", "chat_id": chat_id}
