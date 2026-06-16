"""
Mission Canvas — Slack Bridge

Slack adapter using slack-bolt (Socket Mode).
Receives messages from channels/DMs, sends responses back.

Extracted from Hermes (MIT, Nous Research), adapted for MC governance pipeline.

Environment variables:
    MC_SLACK_BOT_TOKEN     — Bot token (xoxb-...) from api.slack.com/apps
    MC_SLACK_APP_TOKEN     — App-level token (xapp-...) for Socket Mode
    MC_SLACK_ALLOWED_CHANNELS — Comma-separated channel IDs (empty = all)
    MC_SLACK_REQUIRE_MENTION — If "true", only respond when @mentioned (default: true)

Setup:
    1. Create app at api.slack.com/apps
    2. Enable Socket Mode
    3. Add Bot Token Scopes: chat:write, channels:history, groups:history,
       im:history, mpim:history, channels:read, users:read
    4. Install to workspace
    5. Copy Bot Token and App Token to env
"""

import asyncio
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from .base import BaseBridge, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)

try:
    from slack_bolt.async_app import AsyncApp
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    from slack_sdk.web.async_client import AsyncWebClient
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False


class SlackBridge(BaseBridge):
    """Slack bridge for Mission Canvas using Socket Mode."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("slack", config or {})
        self._bot_token = os.getenv("MC_SLACK_BOT_TOKEN", "")
        self._app_token = os.getenv("MC_SLACK_APP_TOKEN", "")
        self._require_mention = os.getenv("MC_SLACK_REQUIRE_MENTION", "true").lower() == "true"
        self._allowed_channels = set()
        allowed_raw = os.getenv("MC_SLACK_ALLOWED_CHANNELS", "").strip()
        if allowed_raw:
            self._allowed_channels = {c.strip() for c in allowed_raw.split(",") if c.strip()}

        self._app: Optional[Any] = None
        self._socket_handler: Optional[Any] = None
        self._bot_user_id: str = ""
        self._user_cache: Dict[str, str] = {}

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("MC_SLACK_BOT_TOKEN") and os.getenv("MC_SLACK_APP_TOKEN"))

    async def connect(self) -> bool:
        if not SLACK_AVAILABLE:
            logger.error("[Slack] slack-bolt not installed. Run: pip install slack-bolt")
            return False

        if not self._bot_token or not self._app_token:
            logger.error("[Slack] MC_SLACK_BOT_TOKEN and MC_SLACK_APP_TOKEN required")
            return False

        self._app = AsyncApp(token=self._bot_token)

        # Get bot user ID for mention detection
        try:
            client = AsyncWebClient(token=self._bot_token)
            auth = await client.auth_test()
            self._bot_user_id = auth["user_id"]
            logger.info("[Slack] Connected as bot user %s", self._bot_user_id)
        except Exception as e:
            logger.error("[Slack] Auth failed: %s", e)
            return False

        # Register message handler
        @self._app.event("message")
        async def handle_message(event, say):
            await self._on_message(event)

        # Start Socket Mode
        self._socket_handler = AsyncSocketModeHandler(self._app, self._app_token)
        self._running = True
        asyncio.create_task(self._socket_handler.start_async())
        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._socket_handler:
            await self._socket_handler.close_async()

    async def _get_user_name(self, user_id: str) -> str:
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            client = AsyncWebClient(token=self._bot_token)
            result = await client.users_info(user=user_id)
            name = result["user"].get("real_name") or result["user"].get("name", user_id)
            self._user_cache[user_id] = name
            return name
        except Exception:
            return user_id

    async def _on_message(self, event: dict) -> None:
        # Skip bot messages and message_changed subtypes
        if event.get("bot_id") or event.get("subtype"):
            return

        text = event.get("text", "")
        channel = event.get("channel", "")
        user_id = event.get("user", "")
        thread_ts = event.get("thread_ts")
        ts = event.get("ts", "")

        # Channel filter
        if self._allowed_channels and channel not in self._allowed_channels:
            return

        # Mention filter (in channels, not DMs)
        channel_type = event.get("channel_type", "")
        is_dm = channel_type in ("im", "mpim")
        if self._require_mention and not is_dm:
            if f"<@{self._bot_user_id}>" not in text:
                return

        # Strip bot mention from text
        text = re.sub(rf"<@{self._bot_user_id}>", "", text).strip()

        if not text:
            return

        user_name = await self._get_user_name(user_id)

        source = self.build_source(
            chat_id=channel,
            chat_name=channel,
            chat_type="dm" if is_dm else "channel",
            user_id=user_id,
            user_name=user_name,
            thread_id=thread_ts,
        )

        msg_event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=ts,
            reply_to_message_id=thread_ts,
        )

        await self.handle_message(msg_event)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        try:
            client = AsyncWebClient(token=self._bot_token)
            kwargs: Dict[str, Any] = {"channel": chat_id, "text": content}

            # Thread replies
            thread_ts = (metadata or {}).get("thread_id") or reply_to
            if thread_ts:
                kwargs["thread_ts"] = thread_ts

            result = await client.chat_postMessage(**kwargs)
            return SendResult(success=True, message_id=result.get("ts", ""))
        except Exception as e:
            logger.error("[Slack] Send failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        try:
            client = AsyncWebClient(token=self._bot_token)
            result = await client.conversations_info(channel=chat_id)
            ch = result["channel"]
            return {
                "name": ch.get("name", chat_id),
                "type": "dm" if ch.get("is_im") else "channel",
                "chat_id": chat_id,
            }
        except Exception:
            return {"name": chat_id, "type": "unknown", "chat_id": chat_id}
