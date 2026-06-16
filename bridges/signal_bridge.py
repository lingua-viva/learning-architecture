"""
Mission Canvas — Signal Bridge

Signal adapter using signal-cli as a subprocess.
Privacy-focused messaging — no phone number exposure to servers.

Environment variables:
    MC_SIGNAL_ENABLED        — "true" to activate
    MC_SIGNAL_PHONE_NUMBER   — Registered Signal phone number (+1234567890)
    MC_SIGNAL_ALLOWED_USERS  — Comma-separated phone numbers (empty = all)
    MC_SIGNAL_CLI_PATH       — Path to signal-cli binary (default: signal-cli)

Setup:
    1. Install signal-cli: https://github.com/AsamK/signal-cli
    2. Register or link: signal-cli -u +NUMBER register / link
    3. Set env vars
"""

import asyncio
import json
import logging
import os
import shutil
from typing import Any, Dict, Optional

from .base import BaseBridge, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)


class SignalBridge(BaseBridge):
    """Signal bridge for Mission Canvas via signal-cli."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("signal", config or {})
        self._enabled = os.getenv("MC_SIGNAL_ENABLED", "false").lower() == "true"
        self._phone = os.getenv("MC_SIGNAL_PHONE_NUMBER", "")
        self._cli_path = os.getenv("MC_SIGNAL_CLI_PATH", "signal-cli")
        self._allowed_users = set()
        allowed_raw = os.getenv("MC_SIGNAL_ALLOWED_USERS", "").strip()
        if allowed_raw:
            self._allowed_users = {u.strip() for u in allowed_raw.split(",") if u.strip()}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None

    @classmethod
    def is_configured(cls) -> bool:
        return (
            os.getenv("MC_SIGNAL_ENABLED", "false").lower() == "true"
            and bool(os.getenv("MC_SIGNAL_PHONE_NUMBER"))
        )

    async def connect(self) -> bool:
        if not self._enabled:
            return False
        if not shutil.which(self._cli_path):
            logger.error("[Signal] signal-cli not found at %s", self._cli_path)
            return False

        try:
            self._process = await asyncio.create_subprocess_exec(
                self._cli_path, "-u", self._phone, "jsonRpc",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._running = True
            self._reader_task = asyncio.create_task(self._read_loop())
            logger.info("[Signal] Connected as %s", self._phone)
            return True
        except Exception as e:
            logger.error("[Signal] Failed to start: %s", e)
            return False

    async def disconnect(self) -> None:
        self._running = False
        if self._process:
            self._process.terminate()
        if self._reader_task:
            self._reader_task.cancel()

    async def _read_loop(self) -> None:
        while self._running and self._process:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break
                data = json.loads(line.decode().strip())
                await self._handle_signal_message(data)
            except asyncio.CancelledError:
                break
            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.error("[Signal] Read error: %s", e)

    async def _handle_signal_message(self, data: dict) -> None:
        # signal-cli jsonRpc emits various event types
        method = data.get("method", "")
        if method != "receive":
            return
        params = data.get("params", {})
        envelope = params.get("envelope", {})
        source_number = envelope.get("sourceNumber", "")
        data_msg = envelope.get("dataMessage", {})
        text = data_msg.get("message", "")

        if not text or not source_number:
            return
        if self._allowed_users and source_number not in self._allowed_users:
            return

        source = self.build_source(
            chat_id=source_number,
            chat_name=source_number,
            chat_type="dm",
            user_id=source_number,
            user_name=source_number,
        )

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=str(data_msg.get("timestamp", "")),
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
            return SendResult(success=False, error="Process not running")
        try:
            rpc_call = json.dumps({
                "jsonrpc": "2.0",
                "method": "send",
                "params": {"recipient": [chat_id], "message": content},
                "id": 1,
            }) + "\n"
            self._process.stdin.write(rpc_call.encode())
            await self._process.stdin.drain()
            return SendResult(success=True)
        except Exception as e:
            logger.error("[Signal] Send failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id, "type": "dm", "chat_id": chat_id}
